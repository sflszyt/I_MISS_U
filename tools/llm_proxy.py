#!/usr/bin/env python3
"""LLM proxy that holds the API key on the PC side."""

import argparse
import collections
import hmac
import io
import json
import os
import re
import sys
import uuid
import threading
import time
import urllib.error
import urllib.request
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

if __package__:
    from .father_model_policy import load_policy, validate_models, CREDENTIAL_TARGET
    from .windows_credential import read_openai_credential
else:
    from father_model_policy import load_policy, validate_models, CREDENTIAL_TARGET
    from windows_credential import read_openai_credential

TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
VIEWER_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./:-]{0,127}$")
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


def diagnostic_log_line(args, text):
    # Diagnostic loss must not change transport behavior or print raw sink errors.
    try:
        sys.stderr.write(text + "\n")
    except (OSError, ValueError):
        pass
    if args.log_dir:
        try:
            os.makedirs(args.log_dir, exist_ok=True)
            path = os.path.join(args.log_dir, "llm_proxy_" + time.strftime("%Y%m%d") + ".log")
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(text + "\n")
        except (OSError, ValueError):
            pass


def safe_omit_key(text, key):
    if not key:
        return text
    return text.replace(key, "[REDACTED]")


def openai_sse_chunks(upstream, api_key):
    """Forward only complete SSE events; EOF must never manufacture a DONE event."""
    line = bytearray()
    event = bytearray()
    data_lines = []
    skip_lf = False
    prefix = b""  # only the stream-start optional UTF-8 BOM is stripped
    wire_bom = b""
    key = api_key.encode("utf-8")
    reader = getattr(upstream, "read1", upstream.read)
    while True:
        raw = reader(4096)
        if not raw:
            # Do not release partial lines/events on failure.
            raise EOFError("incomplete upstream stream")
        if prefix is not None:
            prefix += raw
            bom = b"\xef\xbb\xbf"
            if len(prefix) < len(bom) and bom.startswith(prefix):
                continue
            wire_bom = bom if prefix.startswith(bom) else b""
            raw = prefix[len(wire_bom):]
            prefix = None
        for byte in raw:
            if skip_lf:
                skip_lf = False
                if byte == 10:
                    continue
            if byte not in (10, 13):
                line.append(byte)
                if len(line) + len(event) > MAX_BODY:
                    raise ValueError("upstream SSE event too large")
                continue
            skip_lf = byte == 13
            value = bytes(line)
            line.clear()
            event.extend(value + b"\n")
            if value:
                if value.startswith(b"data:"):
                    data_lines.append(value[5:].removeprefix(b" "))
                elif value == b"data":
                    data_lines.append(b"")
                if len(event) > MAX_BODY:
                    raise ValueError("upstream SSE event too large")
                continue
            done = b"\n".join(data_lines) == b"[DONE]"
            # Credentials cannot contain CR/LF (validated by ProxyConfig), so a
            # key cannot span SSE events. Assemble TCP chunks first, redact a
            # whole event, then release that entire event without a tail buffer.
            output = bytes(event).replace(key, b"[REDACTED]")
            # Preserve the original optional signature on the wire: both proxy
            # and client ignore exactly one BOM; a second remains ordinary data.
            output = wire_bom + output
            wire_bom = b""
            event.clear()
            data_lines.clear()
            if output:
                yield output
            if done:
                return


class ProxyConfig:
    def __init__(self, args, tokens, api_key, openai_key=""):
        if "\r" in openai_key or "\n" in openai_key:
            fail("invalid OpenAI credential format")
        try:
            self.openai_models = validate_models(getattr(args, "openai_model", []) or [])
        except ValueError:
            fail("invalid father OpenAI policy")
        self.openai_key = openai_key
        self.args = args
        self.tokens = tokens
        self.api_key = api_key
        self.viewer_models = parse_viewer_models(getattr(args, "viewer_model", None) or [], tokens)
        self.limiter = RateLimiter(args.rpm, args.daily)


def parse_viewer_models(specs, tokens):
    """Resolve only operator-configured models for authenticated viewer names."""
    routes = {}
    viewers = set(tokens.values())
    for spec in specs:
        viewer, separator, model = spec.partition("=")
        if not separator or not VIEWER_RE.fullmatch(viewer) or not MODEL_RE.fullmatch(model):
            fail("invalid --viewer-model; expected VIEWER=MODEL without whitespace")
        if viewer not in viewers:
            fail("--viewer-model viewer is not configured in authentication tokens")
        if viewer in routes:
            fail("duplicate --viewer-model viewer")
        routes[viewer] = model
    return routes


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
            if getattr(self, "_request_id", None): self._diagnostic("downstream_complete", status)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            if getattr(self, "_request_id", None): self._diagnostic("downstream_disconnected")
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
            "default_model": self.args.model,
            "viewer_models": dict(self.proxy.viewer_models),
            "viewers": len(self.proxy.tokens)
        })

    def _diagnostic(self, stage, status=None):
        # Fixed schema: never include request bodies, credentials, URLs or exceptions.
        # downstream_complete means writes finished here, never proof of client delivery.
        event = {"request_id": self._request_id, "stage": stage}
        if isinstance(status, int) and 100 <= status <= 599:
            event["status"] = status
        if self._request_ray:
            event["cf_ray"] = self._request_ray
        diagnostic_log_line(self.args, "request_diag " + json.dumps(event, separators=(",", ":")))

    def send_response(self, code, message=None):
        super().send_response(code, message)
        if getattr(self, "_request_id", None):
            self.send_header("X-Request-ID", self._request_id)
            self._diagnostic("downstream_headers", code)

    def _diagnostic_route(self, provider, model):
        # Enumerated routing metadata only; never echo arbitrary client values.
        allowed = {"openai": ("gpt-6-luna", "gpt-6.1-terra", "gpt-6.1-sol"),
                   "deepseek": ("deepseek-v4-pro",)}
        if model not in allowed.get(provider, ()):
            return
        event = {"request_id": self._request_id, "stage": "upstream_route",
                 "provider": provider, "model": model}
        diagnostic_log_line(self.args, "request_diag " + json.dumps(event, separators=(",", ":")))

    def do_POST(self):
        supplied = self.headers.get("X-Request-ID", "")
        self._request_id = supplied if re.fullmatch(r"[a-f0-9]{32}", supplied) else uuid.uuid4().hex
        ray = self.headers.get("CF-Ray", "")
        self._request_ray = ray if re.fullmatch(r"[a-fA-F0-9]{16}-[A-Z]{3}", ray) else ""
        try:
            self._diagnostic("request_received")
            self._handle_post()
        except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError):
            self._diagnostic("error")
        except Exception:
            self._diagnostic("error")
            raise
        finally:
            self._request_id = None

    def _handle_post(self):
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
                    self._diagnostic("downstream_complete", 429)
                except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                    if getattr(self, "_request_id", None): self._diagnostic("downstream_disconnected")
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

            if not isinstance(data, dict):
                self._send_json(400, {"error": "invalid request"}, close=True)
                return
            upstream_url, upstream_key = self.args.upstream, self.proxy.api_key
            openai_route = False
            selection = data.get("model", "proxy")
            if viewer == "father" and (selection in ("gpt-6-luna", "gpt-6.1-terra", "gpt-6.1-sol", "deepseek-v4-pro") or "provider" in data):
                provider = "deepseek" if selection == "deepseek-v4-pro" else "openai"
                if selection not in ("gpt-6-luna", "gpt-6.1-terra", "gpt-6.1-sol", "deepseek-v4-pro") or data.get("provider", provider) != provider:
                    self._send_json(400, {"error": "unknown model selection"}, close=True)
                    return
                openai_route = provider == "openai"
                if openai_route:
                    if selection not in self.proxy.openai_models or not self.proxy.openai_key:
                        self._send_json(409, {"error": "model not configured; availability unverified"}, close=True)
                        return
                    upstream_url = "https://api.openai.com/v1/chat/completions"
                    upstream_key = self.proxy.openai_key
                data["model"] = selection
            elif viewer == "father" and selection != "proxy":
                self._send_json(400, {"error": "unknown model selection"}, close=True)
                return
            else:
                data["model"] = self.proxy.viewer_models.get(viewer, self.args.model)
            client_max = data.get("max_tokens")
            try:
                client_max_int = int(client_max) if client_max is not None else self.args.max_tokens
            except Exception:
                client_max_int = self.args.max_tokens
            data["max_tokens"] = min(client_max_int, self.args.max_tokens)

            if not openai_route and "deepseek" in upstream_url.lower():
                data["thinking"] = {"type": "disabled"}

            filtered = {k: v for k, v in data.items() if k in ALLOWED_FIELDS}
            if openai_route:
                filtered = {k: v for k, v in filtered.items() if k in {"model", "messages", "stream", "max_tokens"}}
                filtered["max_completion_tokens"] = filtered.pop("max_tokens")
            body = json.dumps(filtered).encode("utf-8")
            stream_out = bool(filtered.get("stream", False))

            req = urllib.request.Request(
                upstream_url,
                data=body,
                method="POST",
                headers={
                    "Authorization": "Bearer " + upstream_key,
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream" if stream_out else "application/json"
                }
            )
            self._diagnostic("upstream_attempt")
            if viewer == "father" and selection != "proxy":
                self._diagnostic_route("openai" if openai_route else "deepseek", selection)
            with urllib.request.urlopen(req, timeout=self.args.timeout) as upstream:
                self._diagnostic("upstream_headers", upstream.status)
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
                    chunks = (openai_sse_chunks(upstream, upstream_key) if openai_route
                              else iter(lambda: upstream.read(4096), b""))
                    for chunk in chunks:
                        try:
                            self.wfile.write(chunk)
                            self.wfile.flush()
                        except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError):
                            if getattr(self, "_request_id", None): self._diagnostic("downstream_disconnected")
                            log_line(self.args, f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} viewer={viewer} status=200 stream=True error=client_disconnected")
                            return
                        bytes_out += len(chunk)
                    status_out = 200
                    self._diagnostic("downstream_complete", 200)
                else:
                    upstream_body = upstream.read()
                    safe_body = upstream_body
                    if self.proxy.api_key:
                        safe_body = safe_body.replace(self.proxy.api_key.encode("utf-8"), b"[REDACTED]")
                    if openai_route:
                        safe_body = safe_body.replace(upstream_key.encode("utf-8"), b"[REDACTED]")

                    self.send_response(upstream.status)
                    self.send_header("Content-Type", upstream.headers.get("Content-Type", "application/json"))
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Content-Length", str(len(safe_body)))
                    self.end_headers()
                    headers_sent = True
                    try:
                        self.wfile.write(safe_body)
                    except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError):
                        if getattr(self, "_request_id", None): self._diagnostic("downstream_disconnected")
                        log_line(self.args, f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} viewer={viewer} status={upstream.status} stream=False error=client_disconnected")
                        return
                    bytes_out = len(safe_body)
                    status_out = upstream.status
                    self._diagnostic("downstream_complete", upstream.status)
        except urllib.error.HTTPError as exc:
            self._diagnostic("upstream_headers", exc.code)
            # 跨组件约定：424 = 我活着、但我依赖的上游失败了。
            # Worker 的 ORIGIN_DOWN_STATUS = {502,503,504,521,522,523,524,530} 故意不含 424，
            # 不要把 424 加进那张表，否则真实错误会再次被吞掉。
            # 上游返回那张表里的码时，对外一律改发 424，避免被 Worker 误判成「家里 PC 关机」；
            # 其余状态码（401 鉴权失败 / 429 限流 / 400 参数错等）原样透传不变，那些码 Worker 不会误判。
            status_out = exc.code
            if openai_route:
                # Never wait for or relay an untrusted error body on this route.
                exc.close()
                err_body = b'{"error":"upstream_failure"}'
            else:
                err_body = exc.read()
            if self.proxy.api_key:
                err_body = err_body.replace(self.proxy.api_key.encode("utf-8"), b"[REDACTED]")
            if exc.code in (502, 503, 504, 521, 522, 523, 524, 530):
                status_out = 424
                # 上游 body 刻意不外传：424 会被 Worker 原样透传给页面，而 body 里可能以
                # 转义形式（\uXXXX、URL-encoded、raw/escaped 混合等）含有 API key，
                # 脱敏无法穷尽所有编码形式，所以只回结构化字段，诊断靠状态码与本地日志。
                payload = json.dumps({
                    "error": "upstream_failure",
                    "upstream_status": exc.code
                }).encode("utf-8")
                try:
                    self.send_response(424)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    bytes_out = len(payload)
                    self._diagnostic("downstream_complete", 424)
                except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError):
                    if getattr(self, "_request_id", None): self._diagnostic("downstream_disconnected")
                    log_line(self.args, f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} viewer={viewer} status=424 upstream_status={exc.code} stream={stream_out} error=client_disconnected")
                    return
                except Exception:
                    self._diagnostic("error")
                log_line(self.args, f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} viewer={viewer} status=424 upstream_status={exc.code} stream={stream_out} error=upstream_failure")
            else:
                try:
                    self.send_response(exc.code)
                    if exc.code == 403:
                        self.send_header("X-LLM-Error", "upstream_forbidden")
                    self.send_header("Content-Type", "application/json" if openai_route else exc.headers.get("Content-Type", "application/json"))
                    self.send_header("Content-Length", str(len(err_body)))
                    self.end_headers()
                    self.wfile.write(err_body)
                    bytes_out = len(err_body)
                    self._diagnostic("downstream_complete", exc.code)
                except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError):
                    if getattr(self, "_request_id", None): self._diagnostic("downstream_disconnected")
                    log_line(self.args, f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} viewer={viewer} status={exc.code} stream={stream_out} error=client_disconnected")
                except Exception:
                    self._diagnostic("error")
        except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError):
            # This broad catch can also be an upstream read failure.
            self._diagnostic("error")
            log_line(self.args, f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} viewer={viewer} status={status_out} stream={stream_out} error=client_disconnected")
        except Exception as exc:
            self._diagnostic("error")
            # 跨组件约定：424 = 上游失败（这里是我自己调用上游时炸了）。
            # Worker 的 ORIGIN_DOWN_STATUS 故意不含 424，不要把 424 加进那张表，
            # 否则真实错误会再次被吞掉。detail 只放异常类名，不放异常字符串，避免 API key 外泄。
            status_out = 424
            if not headers_sent:
                try:
                    self._send_json(424, {"error": "upstream_failure", "detail": type(exc).__name__}, close=True)
                except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError):
                    if getattr(self, "_request_id", None): self._diagnostic("downstream_disconnected")
                    pass
            log_line(self.args, f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} viewer={viewer} status=424 stream={stream_out} error=upstream_failure")

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


def read_tokens_file(path, key):
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                file_key, value = line.split("=", 1)
                file_key = file_key.strip()
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                    value = value[1:-1]
                if file_key == key:
                    return value
    except FileNotFoundError:
        fail(f'tokens file not found: {path} (looking for key "{key}")')
    except IsADirectoryError:
        fail(f'tokens file path is a directory: {path} (looking for key "{key}")')
    except UnicodeDecodeError:
        fail(f'tokens file is not valid UTF-8: {path} (looking for key "{key}")')
    except OSError:
        fail(f'cannot read tokens file: {path} (looking for key "{key}")')
    fail(f'key "{key}" not found in tokens file: {path}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8023)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--upstream", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--viewer-model", action="append", default=[], metavar="VIEWER=MODEL",
                        help="Override the default model for an authenticated viewer; repeatable")
    parser.add_argument("--openai-policy", default=None, help="Non-secret father model policy JSON")
    parser.add_argument("--openai-credential-target", default="", choices=[CREDENTIAL_TARGET],
                        help="Explicit Windows Generic credential target; disabled policy never reads it")
    parser.add_argument("--key-env", default="DEEPSEEK_API_KEY")
    parser.add_argument("--tokens", default="")
    parser.add_argument("--tokens-file", default="", help="从文件读取 viewer token；文件内一行 TTS_TOKENS=viewer:token[,viewer2:token2]")
    parser.add_argument("--rpm", type=int, default=10)
    parser.add_argument("--daily", type=int, default=200)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--log-dir", default="")
    args = parser.parse_args()

    api_key = os.environ.get(args.key_env)
    if not api_key:
        fail(f"environment variable {args.key_env} not set")

    if args.tokens and args.tokens_file:
        fail("--tokens and --tokens-file are mutually exclusive")

    tokens = {}
    if args.tokens_file:
        raw_tokens = read_tokens_file(args.tokens_file, "TTS_TOKENS")
        if not raw_tokens or not raw_tokens.strip():
            fail(f'key "TTS_TOKENS" is empty in tokens file: {args.tokens_file}')
        for part in raw_tokens.split(","):
            if part != part.strip() or not part:
                fail(f"invalid TTS_TOKENS value in tokens file: {args.tokens_file}")
        parse_failed = False
        old_stderr = sys.stderr
        try:
            sys.stderr = io.StringIO()
            parse_tokens(raw_tokens, tokens)
        except SystemExit:
            parse_failed = True
        finally:
            sys.stderr = old_stderr
        if parse_failed or not tokens:
            fail(f"invalid TTS_TOKENS value in tokens file: {args.tokens_file}")
    else:
        parse_tokens(args.tokens, tokens)
        if not tokens:
            fail("no valid tokens parsed")

    try:
        args.openai_model = list(load_policy(args.openai_policy))
        openai_key = read_openai_credential(args.openai_credential_target) if args.openai_model else ""
    except ValueError as exc:
        fail(str(exc))
    config = ProxyConfig(args, tokens, api_key, openai_key=openai_key)
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
