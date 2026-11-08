"""Synthetic upstream failures only: no sockets, credentials or provider calls."""
import contextlib
import io
import json
import unittest
import urllib.error
from email.message import Message
from types import SimpleNamespace
from unittest.mock import patch

from tools import llm_proxy as proxy
from tests.test_llm_proxy import args, TOKENS


class ForbiddenTests(unittest.TestCase):
    def invoke(self, status=403, model='gpt-6.1-terra', token='synthetic_father'):
        config = proxy.ProxyConfig(args(openai_model=['gpt-6.1-terra']), TOKENS,
                                   'SYNTHETIC_KEY', openai_key='SYNTHETIC_OPENAI')
        h = proxy.ProxyHandler.__new__(proxy.ProxyHandler)
        h.server = SimpleNamespace(proxy=config)
        body = json.dumps({'model': model, 'messages': [{'role': 'user', 'content': 'PRIVATE_CANARY'}], 'stream': True}).encode()
        h.headers = Message()
        h.headers['Content-Length'] = str(len(body))
        h.headers['X-TTS-Token'] = token
        h.headers['X-Request-ID'] = 'a' * 32
        h.rfile, h.wfile = io.BytesIO(body), io.BytesIO()
        h.path = '/v1/chat/completions'
        h.request_version = 'HTTP/1.1'
        h.requestline = 'POST /v1/chat/completions HTTP/1.1'
        h.command = 'POST'
        class UnreadableBody(io.BytesIO):
            def read(self, *args):
                raise AssertionError('OpenAI error body must not be read')
        error_body = UnreadableBody(b'PRIVATE_CANARY SYNTHETIC_OPENAI')
        error = urllib.error.HTTPError('https://synthetic.invalid', status, 'DENIAL_CANARY',
                                      {'Content-Type': 'text/html'}, error_body)
        logs = io.StringIO()
        with patch.object(proxy.urllib.request, 'urlopen', side_effect=error) as upstream, contextlib.redirect_stderr(logs):
            h.do_POST()
        return h.wfile.getvalue(), logs.getvalue(), upstream.call_count, error_body.closed

    def test_openai_403_fixed_header_no_body_read_retry_or_leak(self):
        wire, logs, count, closed = self.invoke()
        self.assertIn(b'HTTP/1.1 403', wire)
        self.assertIn(b'X-LLM-Error: upstream_forbidden', wire)
        self.assertIn(b'Content-Type: application/json', wire)
        self.assertIn(b'X-Request-ID: ' + b'a' * 32, wire)
        self.assertEqual(wire.split(b'\r\n\r\n', 1)[1], b'{"error":"upstream_failure"}')
        self.assertEqual(count, 1)
        self.assertTrue(closed)
        for canary in ('PRIVATE_CANARY', 'SYNTHETIC_OPENAI', 'DENIAL_CANARY'):
            self.assertNotIn(canary, logs + wire.decode())
        records = [json.loads(line.split(' ', 1)[1]) for line in logs.splitlines() if line.startswith('request_diag ')]
        self.assertIn({'request_id': 'a' * 32, 'stage': 'upstream_route', 'provider': 'openai', 'model': 'gpt-6.1-terra'}, records)
        self.assertTrue(any(x['stage'] == 'downstream_complete' and x.get('status') == 403 for x in records))

    def test_other_failures_do_not_claim_forbidden(self):
        for status, downstream in ((401, 401), (429, 429), (503, 424)):
            with self.subTest(status=status):
                wire, _, count, closed = self.invoke(status)
                self.assertIn(('HTTP/1.1 %d' % downstream).encode(), wire)
                self.assertNotIn(b'X-LLM-Error:', wire)
                self.assertEqual(count, 1)
                self.assertTrue(closed)

    def test_auth_and_unknown_model_never_contact_upstream(self):
        for token, model, expected in (('invalid', 'gpt-6.1-terra', 401), ('synthetic_father', 'PRIVATE_CANARY', 400)):
            wire, logs, count, _ = self.invoke(token=token, model=model)
            self.assertIn(('HTTP/1.1 %d' % expected).encode(), wire)
            self.assertEqual(count, 0)
            self.assertNotIn('upstream_route', logs)
            self.assertNotIn(b'X-LLM-Error:', wire)

    def test_route_metadata_rejects_arbitrary_values(self):
        h = proxy.ProxyHandler.__new__(proxy.ProxyHandler)
        h.server = SimpleNamespace(proxy=proxy.ProxyConfig(args(), TOKENS, 'SYNTHETIC_KEY'))
        h._request_id = 'b' * 32
        logs = io.StringIO()
        with contextlib.redirect_stderr(logs):
            for provider, model in [('PRIVATE_CANARY', 'gpt-6.1-terra'), ('openai', 'PRIVATE_CANARY'), ('openai', 'deepseek-v4-pro')]:
                h._diagnostic_route(provider, model)
        self.assertEqual(logs.getvalue(), '')
