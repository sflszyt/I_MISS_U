"""Private agent documents must not be required for a source checkout."""
import tempfile
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import collect_wechat_video


class PublicRepoRootTests(unittest.TestCase):
    def test_video_reaches_config_validation_without_private_document(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'tools').mkdir()
            (root / 'schema').mkdir()
            (root / 'schema/uif.schema.json').write_text('{}')
            with patch('sys.argv', ['collect', '--person', 'sample', '--db-dir', directory,
                    '--video-dir', directory, '--repo-root', directory]), \
                    patch.object(collect_wechat_video, 'load_config', side_effect=RuntimeError('reached_config')):
                with self.assertRaisesRegex(RuntimeError, 'reached_config'):
                    collect_wechat_video.main()

    def test_voice_reaches_database_validation_without_private_document(self):
        if importlib.util.find_spec('pysilk') is None:
            self.skipTest('pysilk not installed; voice CLI requires its existing audio environment')
        from tools import extract_wechat_voice
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'tools').mkdir()
            (root / 'schema').mkdir()
            (root / 'schema/uif.schema.json').write_text('{}')
            with patch.object(extract_wechat_voice, 'fatal', side_effect=RuntimeError) as fatal:
                with self.assertRaises(RuntimeError):
                    extract_wechat_voice.main(['--person', 'sample', '--db-dir', str(root / 'missing'), '--repo-root', directory])
                self.assertIn('db-dir', fatal.call_args.args[0])
