import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.audit_git_privacy import audit, scan_text


class PrivacyAuditTests(unittest.TestCase):
    def test_values_are_never_in_findings(self):
        value = 'sk-' + 'aB3x' * 10
        result = scan_text('synthetic.py', value)
        self.assertEqual(result, [{'path': 'synthetic.py', 'line': 1, 'category': 'provider_key'}])
        self.assertNotIn(value, str(result))

    def test_private_identifiers_and_synthetic_email(self):
        self.assertEqual(scan_text('fixture', 'fake@example.invalid'), [])
        self.assertEqual(scan_text('fixture', 'person' + '@' + 'private.invalid')[0]['category'], 'email')
        self.assertEqual(scan_text('fixture', 'C:' + '/Users/' + 'sample/home')[0]['category'], 'windows_user_path')

    def test_entire_index_and_tracked_ignored_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                subprocess.run(['git', '-C', directory, *args], check=True, capture_output=True)
            git('init')
            (root / 'old.txt').write_text('sk-' + 'aB3x' * 10)
            (root / 'private.env').write_text('not opened')
            git('add', 'old.txt', 'private.env')
            (root / '.gitignore').write_text('*.env\n')
            (root / 'old.txt').write_text('now safe')
            work = audit(root)
            self.assertEqual(work['errors'], [])
            self.assertEqual([row['category'] for row in work['findings']], ['tracked_ignored_file'])
            index = audit(root, staged=True)
            self.assertEqual({row['category'] for row in index['findings']}, {'provider_key', 'tracked_ignored_file'})

    def test_binary_is_incomplete_not_clean(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(['git', '-C', directory, 'init'], check=True, capture_output=True)
            (root / 'blob').write_bytes(b'\0\xff')
            self.assertEqual(len(audit(root)['errors']), 1)

    def test_escaped_path_encrypted_key_and_generic_token(self):
        samples = [
            ('C:' + '\\\\Users\\\\' + 'synthetic\\\\file', 'windows_user_path'),
            ('-----BEGIN ' + 'ENCRYPTED PRIVATE KEY-----', 'private_key'),
            ('token = "' + 'aB3x' * 10 + '"', 'credential_literal'),
        ]
        for text, category in samples:
            with self.subTest(category=category):
                self.assertIn(category, [row['category'] for row in scan_text('synthetic', text)])
