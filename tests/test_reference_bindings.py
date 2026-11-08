import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.reference_bindings import load_reference_bindings


class ReferenceBindingsTests(unittest.TestCase):
    def test_missing_or_malformed_binding_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'binding.json'
            with self.assertRaises(ValueError):
                load_reference_bindings(path)
            for payload in ('{}', '{', '{"REFERENCE_AUDIO":"not-a-hash"}'):
                path.write_text(payload)
                with self.assertRaises(ValueError):
                    load_reference_bindings(path)

    def test_explicit_binding_preserves_all_hashes_and_overrides_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'binding.json'
            values = {key: hashlib.sha256(('synthetic-' + key).encode()).hexdigest()
                      for key in ('REFERENCE_AUDIO', 'REFERENCE_TEXT', 'REFERENCE_SOURCE')}
            path.write_text(json.dumps(values))
            with patch.dict(os.environ, {'IMISSU_REFERENCE_BINDINGS': str(path)}):
                self.assertEqual(load_reference_bindings(), values)
            with patch.dict(os.environ, {'IMISSU_REFERENCE_BINDINGS': str(path / 'missing')}):
                self.assertEqual(load_reference_bindings(path), values)
