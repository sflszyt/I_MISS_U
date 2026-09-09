#!/usr/bin/env python3
"""LLM proxy that holds the API key on the PC side."""

import argparse
import collections
import hmac
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
VIEWER_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
MAX_BODY = 256 * 1024
ALLOWED_FIELDS = {"model", "messages", "stream", "temperature", "top_p", "max_tokens", "thinking"}


def fail(msg, code=2):
    sys.stderr.write(f"llm_proxy: {msg}\n")
    sys.exit(code)


def log_line(args, text):
    sys.stderr.write(text + "\n")
    if args.log_dir:
        try:
            os.makedirs(args.log_dir, exist_ok=True)
            path = os.path.join(args.log_dir, "llm_proxy_" + time.strftime("%Y%m%d") + ".log")
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(text + "\n")
        except OSError as exc:
            sys.stderr.write(f"llm_proxy: cannot write log: {exc}\n")


def safe_omit_key(text, key):
    if not key:
        return text
    return text.replace(key, "[REDACTED]")


class ProxyConfig:
    def __init__(self, args, tokens, api_key):
        self.args = args
        self.tokens = tokens
        self.api_key = api_key
        self.limiter = RateLimiter(args.rpm, args.daily)


class RateLimiter:
    def __init__(self, rpm, daily):
        self.rpm = rpm
        self.daily = daily
        self.lock = threading.Lock()
        self.window = collections.defaultdict(list)
        self.day = collections.defaultdict(list)

    def check(self, viewer):
        now = time.time()
        with self.lock:
            day_key = time.strftime("%Y-%m-%d", time.localtime(now))
            self.window[viewer] = [t for t in self.window[viewer] if now - t < 60]
            self.day[viewer] = [t for t in self.day[viewer] if time.strftime("%Y-%m-%d", time.localtime(t)) == day_key]
            if len(self.day[viewer]) >= self.daily:
                return False, "daily quota exceeded", None
            if len(self.window[viewer]) >= self.rpm:
                oldest = min(self.window[viewer]) if self.window[viewer] else now
                retry_after = int(60 - (now - oldest))
                if retry_after < 1:
                    retry_after = 1
                return False, "rate limited", retry_after
            self.window[viewer].append(now)
            self.day[viewer].append(now)
            return True, None, None


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "llm_proxy/1.0"

    def log_message(self, format, *args):
        pass

    @property
    def proxy(self):
        return self.server.proxy

    @property
    def args(self):
        return self.proxy.args

    def _send_json(self, status, obj, close=False):
        data = json.dumps(obj).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            if close:
                self.send_header("Connection", "close")
                self.close_connection = True
            self.end_headers()
            self.wfile.write(data)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            self.close_connection = True

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "content-type, x-tts-token")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if self.path.split("?", 1)[0] != "/health":
            self._send_json(404, {"error": "not found"}, close=True)
            return
        self._send_json(200, {
            "status": "ok",
            "model": self.args.model,
            "viewers": len(self.proxy.tokens)
        })

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/v1/chat/completions":
            self._send_json(404, {"error": "not found"}, close=True)
            return

        viewer = self._authenticate()
        if viewer is None:
            return

        ok, msg, retry_after = self.proxy.limiter.check(viewer)
        if not ok:
            if retry_after is not None:
                self.send_response(429)
                self.send_header("Content-Type", "application/json")
                self.send_header("Retry-After", str(retry_after))
                body = json.dumps({"error": msg, "retry_after": retry_after}).encode("utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                self.close_connection = True
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                    self.close_connection = True
            else:
                self._send_json(429, {"error": msg}, close=True)
            return

        start = time.time()
        status_out = 500
        stream_out = False
        bytes_out = 0
        headers_sent = False

        try:
            try:
                if self.headers.get("Transfer-Encoding"):
                    self._send_json(400, {"error": "chunked transfer-encoding not supported"}, close=True)
                    return
                content_length = int(self.headers.get("Content-Length", "0"))
            except (ValueError, TypeError):
                self._send_json(400, {"error": "missing or invalid Content-Length"}, close=True)
                return
            if content_length <= 0:
                self._send_json(400, {"error": "missing or invalid Content-Length"}, close=True)
                return
            if content_length > MAX_BODY:
                self._send_json(413, {"error": "payload too large"}, close=True)
                return
            raw = self.rfile.read(content_length)
            if len(raw) != content_length:
                self._send_json(400, {"error": "incomplete body"}, close=True)
                return

            try:
                data = json.loads(raw.decode("utf-8"))
            except Exception:
                self._send_json(400, {"error": "bad json"}, close=True)
                return

            data["model"] = self.args.model
            client_max = data.get("max_tokens")
            try:
                client_max_int = int(client_max) if client_max is not None else self.args.max_tokens
            except Exception:
                client_max_int = self.args.max_tokens
            data["max_tokens"] = min(client_max_int, self.args.max_tokens)

            if "deepseek" in self.args.upstream.lower():
                data["thinking"] = {"type": "disabled"}

            filtered = {k: v for k, v in data.items() if k in ALLOWED_FIELDS}
            body = json.dumps(filtered).encode("utf-8")
            stream_out = bool(filtered.get("stream", False))

            req = urllib.request.Request(
                self.args.upstream,
                data=body,
                method="POST",
                headers={
                    "Authorization": "Bearer " + self.proxy.api_key,
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream" if stream_out else "application/json"
                }
            )
            with urllib.request.urlopen(req, timeout=self.args.timeout) as upstream:
                if stream_out:
                    # Streaming path: we deliberately skip API key redaction here
                    # because redaction requires buffering the entire response, which
                    # defeats the purpose of streaming. The API key never appears in
                    # a normal streaming response body (it's only in the request header).
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Connection", "close")
                    self.close_connection = True
                    self.end_headers()
                    headers_sent = True
                    while True:
                        chunk = upstream.read(4096)
                        if not chunk:
                            break
                        try:
                            self.wfile.write(chunk)
                            self.wfile.flush()
                        except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError):
                            log_line(self.args, f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} viewer={viewer} status=200 stream=True error=client_disconnected")
                            return
                        bytes_out += len(chunk)
                    status_out = 200
                else:
                    upstream_body = upstream.read()
                    safe_body = upstream_body
                    if self.proxy.api_key:
                        safe_body = safe_body.replace(self.proxy.api_key.encode("utf-8"), b"[REDACTED]")

                    self.send_response(upstream.status)
                    self.send_header("Content-Type", upstream.headers.get("Content-Type", "application/json"))
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Content-Length", str(len(safe_body)))
                    self.end_headers()
                    headers_sent = True
                    try:
                        self.wfile.write(safe_body)
                    except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError):
                        log_line(self.args, f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} viewer={viewer} status={upstream.status} stream=False error=client_disconnected")
                        return
                    bytes_out = len(safe_body)
                    status_out = upstream.status
        except urllib.error.HTTPError as exc:
            status_out = exc.code
            err_body = exc.read()
            if self.proxy.api_key:
                err_body = err_body.replace(self.proxy.api_key.encode("utf-8"), b"[REDACTED]")
            try:
                self.send_response(exc.code)
                self.send_header("Content-Type", exc.headers.get("Content-Type", "application/json"))
                self.send_header("Content-Length", str(len(err_body)))
                self.end_headers()
                self.wfile.write(err_body)
                bytes_out = len(err_body)
            except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError):
                log_line(self.args, f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} viewer={viewer} status={exc.code} stream={stream_out} error=client_disconnected")
            except Exception:
                pass
        except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError):
            log_line(self.args, f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} viewer={viewer} status={status_out} stream={stream_out} error=client_disconnected")
        except Exception as exc:
            status_out = 502
            if not headers_sent:
                try:
                    self._send_json(502, {"error": "upstream unavailable"}, close=True)
                except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError):
                    pass
            log_line(self.args, f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} viewer={viewer} status=502 stream={stream_out} error=upstream_failure")

        dur_ms = int((time.time() - start) * 1000)
        log_line(self.args, f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} viewer={viewer} status={status_out} stream={stream_out} dur_ms={dur_ms} bytes={bytes_out}")

    def _authenticate(self):
        supplied = self.headers.get("X-TTS-Token", "")
        if TOKEN_RE.fullmatch(supplied):
            for candidate_token, candidate_viewer in self.proxy.tokens.items():
                if hmac.compare_digest(supplied, candidate_token):
                    return candidate_viewer
        self._send_json(401, {"error": "unauthorized"}, close=True)
        return None


class ProxyServer(ThreadingHTTPServer):
    daemon_threads = True
    protocol_version = "HTTP/1.1"

    def __init__(self, addr, handler_cls, proxy_config):
        self.proxy = proxy_config
        super().__init__(addr, handler_cls)


def parse_tokens(spec, tokens_out):
    if not spec:
        fail("--tokens required; refusing to run without auth")
    seen = set()
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" not in item:
            fail(f"invalid token spec: {item!r}")
        viewer, token = item.split(":", 1)
        if not VIEWER_RE.fullmatch(viewer):
            fail(f"invalid viewer name: {viewer!r}")
        if not TOKEN_RE.fullmatch(token):
            fail(f"invalid token format for viewer {viewer!r}")
        if token in seen:
            fail(f"duplicate token for viewer {viewer!r}")
        seen.add(token)
        tokens_out[token] = viewer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8023)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--upstream", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--key-env", default="DEEPSEEK_API_KEY")
    parser.add_argument("--tokens", default="")
    parser.add_argument("--rpm", type=int, default=10)
    parser.add_argument("--daily", type=int, default=200)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--log-dir", default="")
    args = parser.parse_args()

    api_key = os.environ.get(args.key_env)
    if not api_key:
        fail(f"environment variable {args.key_env} not set")

    tokens = {}
    parse_tokens(args.tokens, tokens)
    if not tokens:
        fail("no valid tokens parsed")

    config = ProxyConfig(args, tokens, api_key)
    server = ProxyServer((args.host, args.port), ProxyHandler, config)
    upstream_host = urllib.parse.urlparse(args.upstream).netloc

    sys.stderr.write(
        f"llm_proxy ready: http://{args.host}:{args.port} model={args.model} "
        f"upstream={upstream_host} viewers={len(tokens)} rpm={args.rpm} daily={args.daily}\n"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
