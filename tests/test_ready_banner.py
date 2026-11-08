"""Opt-in preparation presentation contract; synthetic inputs only."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from tools.build_companion_page import build


class ReadyBannerTests(unittest.TestCase):
    def test_opt_in_runs_actual_intro_state_transitions(self):
        html = build('synthetic', '.', 'father', intro_card=True,
                     relationship_scope={'person':'synthetic','relationship_id':'synthetic_father'},
                     archive_manifest_path='data/archive-cache-manifest.json', hide_ready_banner=True)
        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp)/'page.html'
            page.write_text(html, encoding='utf-8')
            result = subprocess.run(['node', str(Path(__file__).with_name('companion_ready_banner.js')), str(page)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_default_remains_explicitly_opt_out(self):
        for viewer in ('owner', 'father'):
            self.assertEqual(build('synthetic', '.', viewer, intro_card=True),
                             build('synthetic', '.', viewer, intro_card=True, hide_ready_banner=False))

    def test_rejects_non_father_or_missing_intro_or_missing_cache(self):
        for viewer, intro, manifest in [('owner',True,'data/archive-cache-manifest.json'),
                                       ('father',False,'data/archive-cache-manifest.json'),('father',True,'')]:
            with self.assertRaises(ValueError):
                build('synthetic','.',viewer,intro_card=intro,archive_manifest_path=manifest,hide_ready_banner=True)
