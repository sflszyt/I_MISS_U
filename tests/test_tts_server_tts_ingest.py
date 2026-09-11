# -*- coding: utf-8 -*-
"""回归测试：/tts 写音频记录（simulacrum_audio）时必须触发会话摄入调度。

此前的 bug 是 /tts 分支只写日志、不调用 sessions_ingest.schedule()，
导致会话最后一轮的后几段语音在历史回放里缺失。
运行方式（项目 venv）：
    C:\\Users\\justin\\venvs\\cosyvoice\\Scripts\\python.exe -X utf8 -m unittest tests.test_tts_server_tts_ingest -v
"""

import glob
import io
import json
import os
import sys
import tempfile
import threading
import types
import unittest
import unittest.mock
import urllib.error
import urllib.request
import wave
from http.server import ThreadingHTTPServer

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'tools'))

try:
    import tts_server
except ImportError as e:
    raise unittest.SkipTest(f'tts_server deps unavailable: {e}')


SESSION_ID = '20260911-001150-TestAb'
TEXT = '记得呀，哪能会不记得'


def _silence_wav_bytes(duration_s=0.1, rate=24000):
    """用标准库 wave 生成一小段合法的单声道 16-bit 静音 WAV。"""
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b'\x00' * (int(rate * duration_s) * 2))
    return buf.getvalue()


class FakeService:
    """替代 tts_server.TTSService（绝不能真的实例化它，会加载多 GB 模型到 GPU）。"""

    def __init__(self, session_log, sessions_ingest):
        self.args = types.SimpleNamespace(
            max_chars=400,
            default_lang='wu',
            sec_per_char=0.32,
            dur_slack=2.0,
            max_retries=0,
            token=None,
        )
        self.viewer_tokens = {}
        self.session_log = session_log
        self.sessions_ingest = sessions_ingest
        self.wav_bytes = _silence_wav_bytes()
        self.synth_calls = []

    def synthesize(self, text, lang):
        self.synth_calls.append((text, lang))
        return b'ID3' + b'\x00' * 32, 1.0, self.wav_bytes

    def health_data(self):
        return {'status': 'ok'}


class TestTtsTriggersIngest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tempdir = self._tmp.name
        self.schedule_count_at_send = []

    # ---------- helpers ----------

    def _make_fake(self, sessions_ingest):
        return FakeService(tts_server.SessionLog(self.tempdir), sessions_ingest)

    def _start_server(self, fake):
        handler_cls = tts_server.build_handler(fake)
        orig_send_audio = handler_cls._send_audio

        def spy(handler_self, *args, **kwargs):
            ing = fake.sessions_ingest
            self.schedule_count_at_send.append(ing.schedule.call_count if ing is not None else None)
            return orig_send_audio(handler_self, *args, **kwargs)

        handler_cls._send_audio = spy
        httpd = ThreadingHTTPServer(('127.0.0.1', 0), handler_cls)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        # addCleanup 是 LIFO：先注册的 join 最后跑，所以顺序是 shutdown -> server_close -> join
        self.addCleanup(thread.join, 5)
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        return httpd.server_address[1]

    def _post(self, port, payload):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        req = urllib.request.Request(
            f'http://127.0.0.1:{port}/tts',
            data=body,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, resp.headers, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def _records(self):
        out = []
        for path in sorted(glob.glob(os.path.join(self.tempdir, '**', '*.jsonl'), recursive=True)):
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        out.append(json.loads(line))
        return out

    # ---------- tests ----------

    def test_tts_with_session_schedules_ingest(self):
        ingest = unittest.mock.Mock()
        fake = self._make_fake(ingest)
        port = self._start_server(fake)

        status, headers, body = self._post(port, {
            'text': TEXT,
            'session_id': SESSION_ID,
            'turn': 1,
        })

        # 关键断言：schedule 必须在开始发送响应之前调用（spy 在 _send_audio 入口快照计数）。
        self.assertEqual(len(self.schedule_count_at_send), 1)
        self.assertGreaterEqual(
            self.schedule_count_at_send[0], 1,
            'schedule 必须在开始发送响应之前调用',
        )

        # 响应读完的这一刻，schedule 必须已经被调用（不允许 sleep 等待）。
        self.assertGreaterEqual(ingest.schedule.call_count, 1)

        self.assertEqual(status, 200)
        self.assertEqual(headers.get('Content-Type'), 'audio/mpeg')
        self.assertIsNotNone(headers.get('X-Session-Audio'))

        records = self._records()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['role'], 'simulacrum_audio')
        self.assertEqual(records[0]['file'], headers.get('X-Session-Audio'))

    def test_tts_without_session_does_not_schedule(self):
        ingest = unittest.mock.Mock()
        fake = self._make_fake(ingest)
        port = self._start_server(fake)

        status, headers, body = self._post(port, {'text': TEXT})

        self.assertEqual(status, 200)
        self.assertEqual(headers.get('Content-Type'), 'audio/mpeg')
        self.assertIsNone(headers.get('X-Session-Audio'))
        self.assertEqual(ingest.schedule.call_count, 0)
        self.assertEqual(self.schedule_count_at_send, [0])
        self.assertEqual(
            glob.glob(os.path.join(self.tempdir, '**', '*.jsonl'), recursive=True), []
        )
        self.assertEqual(self._records(), [])

    def test_schedule_failure_does_not_drop_audio_log(self):
        ingest = unittest.mock.Mock()
        ingest.schedule.side_effect = RuntimeError('boom')
        fake = self._make_fake(ingest)
        port = self._start_server(fake)

        status, headers, body = self._post(port, {
            'text': TEXT,
            'session_id': SESSION_ID,
            'turn': 1,
        })

        self.assertEqual(status, 200)
        self.assertIsNotNone(headers.get('X-Session-Audio'))
        records = self._records()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['role'], 'simulacrum_audio')

    def test_ingest_disabled_still_logs_audio(self):
        fake = self._make_fake(None)
        port = self._start_server(fake)

        status, headers, body = self._post(port, {
            'text': TEXT,
            'session_id': SESSION_ID,
            'turn': 1,
        })

        self.assertEqual(status, 200)
        self.assertEqual(headers.get('Content-Type'), 'audio/mpeg')
        self.assertIsNotNone(headers.get('X-Session-Audio'))
        records = self._records()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['role'], 'simulacrum_audio')


if __name__ == '__main__':
    unittest.main()
