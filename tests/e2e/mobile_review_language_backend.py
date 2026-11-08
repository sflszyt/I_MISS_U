"""Run installed Edge against the real backend, using only freshly synthetic data."""
import json
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests.mobile_review_fixture import fixture, config, credentials
from tools.mobile_review_server import create_server


def main():
    evidence = Path(os.environ['MOBILE_REVIEW_EVIDENCE']).resolve()
    run = evidence / ('signed-synthetic-' + uuid.uuid4().hex)
    fixture(run)
    key, _, token = credentials()
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    settings = config(run, 0)
    settings['public_origin'] = 'http://127.0.0.1:' + str(port)
    server = create_server(settings, test_keys={'synthetic-key': key.public_key()})
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    # 模拟 Access 的逐请求注入，包含浏览器下载请求；只可转发到本次合成后端。
    class Proxy(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def forward(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            headers = dict(self.headers)
            headers['Cf-Access-Jwt-Assertion'] = token
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=20)
            try:
                connection.request(self.command, self.path, body=body, headers=headers)
                response = connection.getresponse()
                data = response.read()
                self.send_response(response.status)
                for name, value in response.getheaders():
                    if name.lower() not in ('server', 'date'):
                        self.send_header(name, value)
                self.end_headers()
                self.wfile.write(data)
            finally:
                connection.close()

        do_GET = do_PUT = do_POST = forward

    proxy = ThreadingHTTPServer(('127.0.0.1', port), Proxy)
    proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
    proxy_thread.start()
    info = run / 'launch-info.json'
    info.write_text(json.dumps({'origin': settings['public_origin']}), encoding='utf-8')
    try:
        result = subprocess.run(['node', str(Path(__file__).with_suffix('.js')), str(info)], cwd=ROOT)
        return result.returncode
    finally:
        proxy.shutdown()
        proxy.server_close()
        proxy_thread.join()
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == '__main__':
    sys.exit(main())
