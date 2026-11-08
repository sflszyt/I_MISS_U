import json
import tempfile
import unittest
from pathlib import Path

from tools.tts_defaults import load_local_defaults, LOCAL_DEFAULT_KEYS


class LocalDefaultsTests(unittest.TestCase):
    def test_missing_file_requires_explicit_cli_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(load_local_defaults(Path(directory) / 'missing.json'), {})

    def test_local_paths_preserved_exactly(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'defaults.json'
            values = {key: str(Path(directory) / key) for key in LOCAL_DEFAULT_KEYS}
            path.write_text(json.dumps(values), encoding='utf-8')
            self.assertEqual(load_local_defaults(path), values)

    def test_reject_unknown_keys_invalid_types_and_malformed_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'defaults.json'
            for payload in ['[]', '{', '{"API_KEY": "synthetic"}', '{"REF_DEFAULT": 42}', '{"REF_DEFAULT": ""}']:
                with self.subTest(payload=payload):
                    path.write_text(payload, encoding='utf-8')
                    with self.assertRaises(ValueError):
                        load_local_defaults(path)
