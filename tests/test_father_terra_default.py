"""Synthetic father default regression tests; never read people/ or call services."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from tools.build_companion_page import build

ROOT = Path(__file__).resolve().parents[1]

class FatherTerraDefault(unittest.TestCase):
    def test_owner_and_nonproxy_bytes_unchanged(self):
        baseline = ROOT / 'evidence/build_companion_page.before.py'
        if not baseline.exists():
            self.skipTest('staging source baseline unavailable; functional tests remain active')
        spec = importlib.util.spec_from_file_location('tools.baseline_companion', baseline)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for viewer, proxy in [('owner', ''), ('owner', '/v1/chat/completions'), ('father', ''), ('son', '/v1/chat/completions')]:
            with self.subTest(viewer=viewer, proxy=proxy):
                opts = dict(llm_proxy=proxy, voice_groups=True, auto_voice_session=True)
                self.assertEqual(build('synthetic', '.', viewer, **opts), module.build('synthetic', '.', viewer, **opts))

    def test_explicit_proxy_routes_and_legacy_defaults(self):
        from unittest.mock import patch
        from tests.test_llm_proxy import ModelRoutes, args, TOKENS
        from tools import llm_proxy as proxy
        config = proxy.ProxyConfig(args(openai_model=['gpt-6-luna', 'gpt-6.1-terra', 'gpt-6.1-sol']), TOKENS, 'SYNTHETIC_KEY', openai_key='SYNTHETIC_OPENAI')
        real_request = proxy.urllib.request.Request
        for token, body, model, upstream in [
            ('synthetic_father', {'model':'gpt-6.1-terra','provider':'openai'}, 'gpt-6.1-terra', 'https://api.openai.com/v1/chat/completions'),
            ('synthetic_father', {'model':'gpt-6-luna','provider':'openai'}, 'gpt-6-luna', 'https://api.openai.com/v1/chat/completions'),
            ('synthetic_father', {'model':'gpt-6.1-sol','provider':'openai'}, 'gpt-6.1-sol', 'https://api.openai.com/v1/chat/completions'),
            ('synthetic_father', {'model':'deepseek-v4-pro','provider':'deepseek'}, 'deepseek-v4-pro', 'https://api.deepseek.com/chat/completions'),
            ('synthetic_father', {'model':'proxy'}, 'deepseek-v4-pro', 'https://api.deepseek.com/chat/completions'),
            ('synthetic_father', {}, 'deepseek-v4-pro', 'https://api.deepseek.com/chat/completions'),
            ('synthetic_owner', {'model':'gpt-6.1-terra','provider':'openai'}, 'deepseek-v4-flash', 'https://api.deepseek.com/chat/completions'),
        ]:
            with self.subTest(token=token, body=body), patch.object(proxy.urllib.request, 'Request', wraps=real_request) as request:
                sent, response = ModelRoutes().invoke(token, dict(body, messages=[], stream=True), config)
                self.assertEqual(request.call_args.args[0], upstream)
                self.assertEqual(sent[0]['model'], model)
                self.assertIn(b'HTTP/1.1 200', response)

    def test_generate_synthetic_browser_pages(self):
        target = ROOT / 'evidence/temp/terra-default'
        target.mkdir(parents=True, exist_ok=True)
        for name, models in [('enabled', ['gpt-6-luna', 'gpt-6.1-terra', 'gpt-6.1-sol']), ('disabled', ['gpt-6-luna'])]:
            policy = target / (name + '-policy.json')
            policy.write_text(json.dumps({'version': 1, 'enabled_models': models}), encoding='utf-8')
            page = build('synthetic', '.', 'father', llm_proxy='/v1/chat/completions', tts_origin='same', tts_token='SYNTHETIC_TOKEN', openai_policy_path=str(policy))
            (target / (name + '.html')).write_text(page, encoding='utf-8')
            expected = 'deepseek-v4-pro'
            self.assertIn('var defaultModel = ' + json.dumps(expected), page)
            self.assertIn("|| {}).value || " + json.dumps(expected), page)

if __name__ == '__main__':
    unittest.main(verbosity=2)
