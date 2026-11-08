import importlib.util
from pathlib import Path
import tempfile
import unittest
from tools.build_companion_page import build

class PageDefaultsTests(unittest.TestCase):
    def test_father_opt_in_only(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                build('synthetic', directory, 'owner', reset_ui_prefs=True)
            page = build('synthetic', directory, 'father', reset_ui_prefs=True)
            self.assertIn('var pageUiPrefs = {voiceText:true, autoVoiceEnabled:true}', page)
            self.assertIn('cfgNoMemory.checked = noMemoryEnabled', page)
            self.assertIn('autocomplete="off"', page)

    def test_default_and_owner_bytes_identical_to_current_source_baseline(self):
        baseline = Path(__file__).resolve().parents[2] / 'baseline/tools/build_companion_page.py'
        if not baseline.exists():
            self.skipTest('candidate byte baseline exists only in staging validation directory')
        spec = importlib.util.spec_from_file_location('baseline_companion', baseline)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            for viewer in ('owner', 'father'):
                for opts in ({}, {'auto_voice_session': True, 'voice_groups': True, 'llm_proxy': '/v1/chat/completions', 'intro_card': True}):
                    with self.subTest(viewer=viewer, opts=opts):
                        self.assertEqual(build('synthetic', directory, viewer, **opts).encode(), module.build('synthetic', directory, viewer, **opts).encode())

if __name__ == '__main__':
    unittest.main()
