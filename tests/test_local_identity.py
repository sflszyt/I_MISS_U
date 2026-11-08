import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.local_identity import owner_participant


class LocalIdentityTests(unittest.TestCase):
    def test_missing_file_and_private_compatibility(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            path = Path(directory) / 'identity.json'
            self.assertEqual(owner_participant(config_path=path), 'owner')
            path.write_text(json.dumps({'owner_participant': 'legacy_synthetic'}), encoding='utf-8')
            self.assertEqual(owner_participant(config_path=path), 'legacy_synthetic')
            self.assertEqual(owner_participant('explicit_synthetic', config_path=path), 'explicit_synthetic')
            with patch.dict(os.environ, {'IMISSU_OWNER_ID': 'environment_synthetic'}):
                self.assertEqual(owner_participant(config_path=path), 'environment_synthetic')
                self.assertEqual(owner_participant('explicit_synthetic', config_path=path), 'explicit_synthetic')

    def test_validation_and_errors_do_not_expose_values(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            path = Path(directory) / 'identity.json'
            for value in ('../escape', 'father', 'mama', 'self', 'CON', '', 2):
                path.write_text(json.dumps({'owner_participant': value}), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, '^Invalid owner participant identifier$'):
                    owner_participant(config_path=path)
            for payload in ('{', '[]', '{"unexpected":"synthetic"}'):
                path.write_text(payload, encoding='utf-8')
                with self.assertRaises(ValueError):
                    owner_participant(config_path=path)

    def test_generated_javascript_and_context_use_same_explicit_identity(self):
        from tools.build_training_manifest import review_page
        from tools.build_chat_context import scoped_context
        with patch.dict(os.environ, {'IMISSU_OWNER_ID': 'legacy_synthetic'}):
            page = review_page([])
            self.assertIn('c.viewpoint==="legacy_synthetic"', page)
            self.assertIn("c.person+'_'+\"legacy_synthetic\"", page)
            context = scoped_context(dict(schema_version=2, viewer='owner', person='mama',
                counts={'selected': 1}, relationship_id='mama_legacy_synthetic',
                language='mandarin', coverage_status='partial'))
            self.assertEqual(context['relationship_id'], 'mama_legacy_synthetic')
