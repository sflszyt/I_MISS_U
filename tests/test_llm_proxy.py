import contextlib
import importlib.util
import io
import json
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools import llm_proxy as proxy

def args(**changes):
    values = dict(rpm=100, daily=200, log_dir='', model='deepseek-v4-flash',
                  viewer_model=['father=deepseek-v4-pro'], max_tokens=100,
                  upstream='https://api.deepseek.com/chat/completions', timeout=1)
    values.update(changes)
    return SimpleNamespace(**values)

TOKENS = {'synthetic_father': 'father', 'synthetic_owner': 'owner', 'synthetic_default': 'default'}

class ModelRoutes(unittest.TestCase):
    def invoke(self, token, body, config=None):
        captured = []
        class Upstream:
            status = 200
            headers = {'Content-Type': 'application/json'}
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def read(self, *a):
                if getattr(self, 'read_once', False): return b''
                self.read_once = True
                return b'data: [DONE]\n\n' if body.get('stream') else b'{"ok":true}'
        def upstream(request, **kwargs):
            captured.append(json.loads(request.data))
            return Upstream()
        h = proxy.ProxyHandler.__new__(proxy.ProxyHandler)
        h.server = SimpleNamespace(proxy=config or proxy.ProxyConfig(args(), TOKENS, 'SYNTHETIC_KEY'))
        data = json.dumps(body).encode()
        h.headers = Message()
        h.headers['Content-Length'] = str(len(data))
        h.headers['X-TTS-Token'] = token
        h.headers['X-Viewer'] = 'father'
        h.rfile, h.wfile = io.BytesIO(data), io.BytesIO()
        h.path = '/v1/chat/completions?viewer=father'
        h.request_version = 'HTTP/1.1'
        h.requestline = 'POST /v1/chat/completions HTTP/1.1'
        h.command = 'POST'
        with patch.object(proxy.urllib.request, 'urlopen', side_effect=upstream), contextlib.redirect_stderr(io.StringIO()):
            h.do_POST()
        return captured, h.wfile.getvalue()

    def test_authenticated_routes_ignore_body_query_and_header_claims(self):
        for token, expected in [('synthetic_father', 'deepseek-v4-pro'), ('synthetic_owner', 'deepseek-v4-flash')]:
            for stream in (False, True):
                with self.subTest(token=token, stream=stream):
                    sent, response = self.invoke(token, {'viewer': 'father', 'model': 'proxy' if token == 'synthetic_father' else 'attacker-model', 'messages': [], 'stream': stream})
                    self.assertEqual(sent[0]['model'], expected)
                    self.assertNotIn('viewer', sent[0])
                    self.assertEqual(sent[0]['thinking'], {'type': 'disabled'})
                    self.assertIn(b'HTTP/1.1 200', response)

    def test_bad_auth_never_contacts_upstream(self):
        sent, response = self.invoke('synthetic_unknown', {'viewer': 'father', 'model': 'deepseek-v4-pro'})
        self.assertEqual(sent, [])
        self.assertIn(b'HTTP/1.1 401', response)

    def test_no_routes_preserves_old_default(self):
        old_args = args()
        del old_args.viewer_model
        config = proxy.ProxyConfig(old_args, TOKENS, 'SYNTHETIC_KEY')
        sent, _ = self.invoke('synthetic_father', {}, config)
        self.assertEqual(sent[0]['model'], 'deepseek-v4-flash')

    def test_invalid_routes_fail_closed_without_echoing_values(self):
        for routes in [['father='], ['father= '], ['father=has space'], ['father=SECRET\nVALUE'], ['unknown=pro'], ['Father=pro'], ['father'], ['=pro'], ['father=pro', 'father=other'], ['father=pro=extra']]:
            with self.subTest(routes=routes), contextlib.redirect_stderr(io.StringIO()) as errors:
                with self.assertRaises(SystemExit): proxy.ProxyConfig(args(viewer_model=routes), TOKENS, 'SYNTHETIC_KEY')
                self.assertNotIn('SECRET', errors.getvalue())

    def test_health_exposes_default_and_overrides_only(self):
        h = proxy.ProxyHandler.__new__(proxy.ProxyHandler)
        h.server = SimpleNamespace(proxy=proxy.ProxyConfig(args(), TOKENS, 'SYNTHETIC_KEY'))
        h.path = '/health'
        with patch.object(h, '_send_json') as send:
            h.do_GET()
        status, body = send.call_args.args
        self.assertEqual(status, 200)
        self.assertEqual(body, {'status':'ok', 'model':'deepseek-v4-flash', 'default_model':'deepseek-v4-flash', 'viewer_models': {'father':'deepseek-v4-pro'}, 'viewers':3})
        self.assertNotIn('SYNTHETIC', json.dumps(body))

class CandidateRoutes(ModelRoutes):
    def test_unknown_and_owner_denied(self):
        for token, body, code in [('synthetic_father', {'model':'unknown'},400), ('synthetic_father', {'model':'gpt-6-luna','provider':'evil'},400)]:
            sent,response=self.invoke(token,body)
            self.assertEqual(sent,[])
            self.assertIn(('HTTP/1.1 '+str(code)).encode(),response)
    def test_owner_default_preserve_legacy_override(self):
        config=proxy.ProxyConfig(args(openai_model=['gpt-6-luna','gpt-6.1-terra','gpt-6.1-sol']),TOKENS,'SYNTHETIC_KEY',openai_key='SYNTHETIC_OPENAI')
        for token in ['synthetic_owner','synthetic_default']:
            for model in ['gpt-6-luna','gpt-6.1-terra','gpt-6.1-sol','deepseek-v4-pro','attacker-model','proxy']:
                for provider in ['openai','deepseek','attacker']:
                    sent,response=self.invoke(token,{'model':model,'provider':provider,'stream':True},config)
                    self.assertEqual(sent[0]['model'],'deepseek-v4-flash')
                    self.assertEqual(sent[0]['thinking'],{'type':'disabled'})
                    self.assertNotIn('provider',sent[0])
                    self.assertNotIn('max_completion_tokens',sent[0])
                    self.assertIn(b'HTTP/1.1 200',response)
    def test_openai_credentials_reject_newlines_without_echo(self):
        for key in ['SYNTHETIC_SECRET\nTAIL','SYNTHETIC_SECRET\rTAIL']:
            with contextlib.redirect_stderr(io.StringIO()) as errors:
                with self.assertRaises(SystemExit):proxy.ProxyConfig(args(),TOKENS,'SYNTHETIC_KEY',openai_key=key)
            self.assertEqual(errors.getvalue(),'llm_proxy: invalid OpenAI credential format\n')
            self.assertNotIn('SYNTHETIC_SECRET',errors.getvalue())
    def test_missing_credentials(self):
        sent,response=self.invoke('synthetic_father',{'model':'gpt-6-luna'})
        self.assertEqual(sent,[])
        self.assertIn(b'HTTP/1.1 409',response)
    def test_openai_payload_stream_and_injection(self):
        config=proxy.ProxyConfig(args(openai_model=['gpt-6-luna','gpt-6.1-terra','gpt-6.1-sol']),TOKENS,'SYNTHETIC_KEY',openai_key='SYNTHETIC_OPENAI')
        for model in ['gpt-6-luna','gpt-6.1-terra','gpt-6.1-sol']:
            for stream in [False,True]:
                sent,response=self.invoke('synthetic_father',{'model':model,'stream':stream,'messages':[], 'url':'https://evil.invalid', 'key':'EVIL', 'temperature':0.5,'thinking':{'type':'enabled'}},config)
                self.assertEqual(sent[0],{'model':model,'stream':stream,'messages':[],'max_completion_tokens':100})
                self.assertIn(b'HTTP/1.1 200',response)
                self.assertNotIn(b'SYNTHETIC',response)

if __name__ == '__main__': unittest.main(verbosity=2)
