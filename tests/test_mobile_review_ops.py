"""Windows launcher integration with a wholly synthetic isolated server/repo.

Never invokes start_services.ps1 or any live service/config. Kept opt-in since
this test creates a venv and short-lived listening processes.
"""
import json
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[1]
FAKE_SERVER = '''import argparse,json
from http.server import HTTPServer, BaseHTTPRequestHandler
p=argparse.ArgumentParser(); p.add_argument('--config'); a=p.parse_args()
c=json.load(open(a.config,encoding='utf-8-sig'))
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  self.send_response(c.get('response_status',401)); self.send_header('Content-Type','application/json'); self.end_headers()
  self.wfile.write(b'{"error":{"code":"authentication_required","message":"Login required"}}')
 def log_message(self,*a): pass
HTTPServer((c['host'],c['port']), Handler).serve_forever()
'''


@unittest.skipUnless(os.name == 'nt' and os.environ.get('RUN_MOBILE_REVIEW_OPS') == '1',
                     'opt-in Windows synthetic process integration')
class MobileReviewOpsTest(unittest.TestCase):
    def test_lifecycle_and_foreign_listener(self):
        fixture = ROOT / 'data/work/mobile-review-20261022/ops-fixture' / uuid.uuid4().hex
        # Spaces and Unicode exercise the Windows argument boundary.
        fixture = fixture / 'synthetic repo 空格'
        (fixture / 'scripts').mkdir(parents=True)
        (fixture / 'tools').mkdir()
        launcher = fixture / 'scripts/start_mobile_review.ps1'
        shutil.copy2(ROOT / 'scripts/start_mobile_review.ps1', launcher)
        (fixture / 'tools/mobile_review_server.py').write_text(FAKE_SERVER, encoding='utf-8')
        venv = fixture / 'data/runtime/mobile-review-venv'
        subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(venv)], check=True)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        config = fixture / 'synthetic config.json'
        config.write_text(json.dumps({'host': '127.0.0.1', 'port': port,
                                      'public_origin': 'https://review.example.test'}), encoding='utf-8')
        command = ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy',
                   'Bypass', '-File', str(launcher), '-ConfigPath', str(config), '-TimeoutSeconds', '5']
        evidence = fixture / 'commands.log'

        def run(*args):
            # Detached Windows children can inherit pipe handles even when their
            # output is redirected. Use files so communicate() does not await EOF
            # from the deliberately long-lived service.
            output = fixture / ('output-' + uuid.uuid4().hex + '.log')
            with output.open('w', encoding='utf-8') as stream:
                result = subprocess.run(command + list(args), stdout=stream, stderr=stream, timeout=45)
            result.stdout = output.read_text(encoding='utf-8', errors='replace')
            result.stderr = ''
            with evidence.open('a', encoding='utf-8') as out:
                out.write(f'{args or ("start",)} exit={result.returncode}\n{result.stdout}{result.stderr}\n')
            return result

        try:
            self.assertEqual(run('-Status').returncode, 1)
            with ThreadPoolExecutor(max_workers=2) as pool:
                starts = [pool.submit(run) for _ in range(2)]
                for future in starts:
                    started = future.result()
                    self.assertEqual(started.returncode, 0, started.stdout + started.stderr)
            record_path = next((fixture / 'data/runtime/mobile-review-processes').glob('*.json'))
            first = json.loads(record_path.read_text(encoding='utf-8-sig'))
            self.assertEqual(run().returncode, 0)
            self.assertEqual(json.loads(record_path.read_text(encoding='utf-8-sig')), first)
            self.assertEqual(run('-Status').returncode, 0)
            # A reused PID or modified ownership record must not authorize stop.
            tampered = dict(first, created='0')
            record_path.write_text(json.dumps(tampered), encoding='utf-8')
            try:
                self.assertEqual(run('-Stop').returncode, 1)
            finally:
                record_path.write_text(json.dumps(first), encoding='utf-8')
            self.assertEqual(run('-Status').returncode, 0)
            self.assertEqual(run('-Stop').returncode, 0)
            self.assertEqual(run('-Stop').returncode, 0)
            self.assertEqual(run('-Status').returncode, 1)
            with socket.socket() as foreign:
                foreign.bind(('127.0.0.1', port)); foreign.listen()
                self.assertEqual(run().returncode, 1)
                self.assertEqual(run('-Stop').returncode, 1)
                self.assertEqual(foreign.getsockname()[1], port)
            broken = json.loads(config.read_text(encoding='utf-8'))
            broken['response_status'] = 200
            config.write_text(json.dumps(broken), encoding='utf-8')
            self.assertEqual(run().returncode, 1)
            # A failed readiness probe must clean up the exact launched tree.
            with socket.socket() as released:
                released.bind(('127.0.0.1', port))
            self.assertEqual(run('-Status').returncode, 1)
            missing = config.with_suffix('.missing')
            config.rename(missing)
            try:
                self.assertEqual(run().returncode, 0)
            finally:
                missing.rename(config)
        finally:
            run('-Stop')
        print(f'ops evidence: {evidence.relative_to(ROOT)}')


if __name__ == '__main__':
    unittest.main()
