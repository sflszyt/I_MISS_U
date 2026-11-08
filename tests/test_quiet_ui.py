import base64
import hashlib
import inspect
import io
import re
import unittest
import wave
from tools.build_companion_page import build

def page(**kw):
    return build('synthetic', '.', 'father', relationship_scope={'person':'synthetic','relationship_id':'synthetic_father'}, archive_manifest_path='data/archive-cache-manifest.json', intro_card=True, auto_voice_session=True, hide_ready_banner=True, **kw)

class QuietUI(unittest.TestCase):
    def test_unlock_pcm_is_silent(self):
        raw=base64.b64decode(re.search(r"var AUTO_VOICE_CUE = 'data:audio/wav;base64,([^']+)'",page())[1])
        with wave.open(io.BytesIO(raw)) as w:
            self.assertGreater(w.getnframes(), 0)
            self.assertEqual(w.getsampwidth(), 2)
            self.assertEqual(set(w.readframes(w.getnframes())), {0})

    def test_normal_bubble_attached_before_gate_and_banner_only_failure(self):
        html=page()
        self.assertLess(html.index("var pendingUser = retryBubble || addBubble"), html.index("  ensureDataReady(true).then(function(ready)"))
        self.assertIn("banner.hidden = card.isConnected || p.phase !== 'failed';",html)

    def test_release_single_safe_source(self):
        kw={'app_release':'D18-candidate'} if 'app_release' in inspect.signature(build).parameters else {}
        html=page(**kw)
        self.assertIn('应用 D18-candidate',html)
        self.assertNotIn('设备档案副本 · D15',html)
        self.assertIn('资料版本以当前已核验清单为准',html)
        with self.assertRaises(ValueError): page(app_release='</script>')
        with self.assertRaises(ValueError): page(app_release='D__PERSON__')

    def test_release_does_not_rewrite_scope_binding(self):
        binding=dict(release_id='D15',release_revision='0'*64,source_sha256='1'*64,card_revisions={'card':'2'*64})
        html=build('synthetic','.','father',relationship_scope={'person':'synthetic','relationship_id':'synthetic_father','memory_release':binding},archive_manifest_path='data/archive-cache-manifest.json',intro_card=True,auto_voice_session=True,hide_ready_banner=True,app_release='D18-candidate')
        self.assertIn('"release_id": "D15"', html)
        self.assertNotIn('"release_id": "D18-candidate"',html)

if __name__=='__main__':unittest.main()
