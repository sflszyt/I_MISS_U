"""Catch lost opt-ins or altered default output during candidate composition."""
import importlib.util
from pathlib import Path
import unittest
import sys
from tools.build_companion_page import build, quiet_archive_preparation, guard_archive_transport

class MergedUiTests(unittest.TestCase):
    def test_independent_flags_and_composition(self):
        opts=dict(intro_card=True,archive_manifest_path='data/archive-cache-manifest.json',
                  relationship_scope={'person':'synthetic','relationship_id':'synthetic_father'},
                  auto_voice_session=True,voice_groups=True)
        base=build('synthetic','.','father',**opts)
        prefs=build('synthetic','.','father',reset_ui_prefs=True,**opts)
        banner=build('synthetic','.','father',hide_ready_banner=True,**opts)
        both=build('synthetic','.','father',reset_ui_prefs=True,hide_ready_banner=True,**opts)
        self.assertNotEqual(base,prefs)
        self.assertNotEqual(base,banner)
        self.assertNotEqual(prefs,both)
        self.assertNotEqual(banner,both)
        self.assertEqual(quiet_archive_preparation(prefs),both)

    def test_no_opt_in_byte_identity_including_archive_cache(self):
        baseline=Path(__file__).resolve().parents[2]/'baseline/tools/build_companion_page.py'
        if not baseline.exists(): self.skipTest('staging baseline unavailable')
        spec=importlib.util.spec_from_file_location('merge_baseline',baseline)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
        for viewer in ('owner','father'):
            for cache in (False,True):
                if viewer=='owner' and cache: continue
                opts=dict(intro_card=True,auto_voice_session=True,voice_groups=True)
                if cache: opts.update(archive_manifest_path='data/archive-cache-manifest.json',relationship_scope={'person':'synthetic','relationship_id':'synthetic_'+viewer})
                with self.subTest(viewer=viewer,cache=cache):
                    if cache: opts['app_release'] = 'D15'
                    actual = build('synthetic','.',viewer,**opts)
                    expected = module.build('synthetic','.',viewer,**opts)
                    self.assertEqual(actual.encode(),expected.encode())
