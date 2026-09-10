import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import ingest_sessions

import unittest
import tempfile
import json
import io
import wave
import hashlib
import subprocess
import contextlib
from pathlib import Path
from unittest import mock


def _make_wav_bytes(seconds=1.0, rate=8000):
    """构造一段合法的定长 WAV 字节流（内容固定，便于断言）。"""
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b'\x00\x00' * int(rate * seconds))
    return buf.getvalue()


AUDIO_BYTES = _make_wav_bytes(1.0)
AUDIO_BYTES_ALT = _make_wav_bytes(0.5)

TS_USER = '2026-09-10T10:00:00+08:00'
TS_SIM = '2026-09-10T10:00:01+08:00'
TS_AUD1 = '2026-09-10T10:00:02+08:00'
TS_AUD2 = '2026-09-10T10:00:03+08:00'


def _write_session(sessions_dir, session_id, records):
    """把 records（dict 列表）逐行写入 <sessions_dir>/session_<id>.jsonl。"""
    path = Path(sessions_dir) / f'session_{session_id}.jsonl'
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    return path


def _append_session(sessions_dir, session_id, records):
    """向已有会话日志追加若干记录。"""
    path = Path(sessions_dir) / f'session_{session_id}.jsonl'
    with open(path, 'a', encoding='utf-8', newline='\n') as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    return path


def _base_record(sid, turn, role, text, ts=None, **kw):
    """构造一条基础记录。"""
    rec = {'session_id': sid, 'turn': turn, 'role': role, 'text': text}
    if ts is not None:
        rec['ts'] = ts
    rec.update(kw)
    return rec


def _audio_record(sid, turn, text, file, ts=None, **kw):
    """构造一条 simulacrum_audio 记录。"""
    rec = {'session_id': sid, 'turn': turn, 'role': 'simulacrum_audio',
           'text': text, 'file': file}
    if ts is not None:
        rec['ts'] = ts
    rec.update(kw)
    return rec


def _wav_name(sid, turn=1, suffix=None):
    """按约定拼出音频文件 basename。"""
    name = f'session_{sid}_t{turn:03d}'
    if suffix is not None:
        name += f'_{suffix}'
    return name + '.wav'


def _make_dir_link(target, link):
    """把 link 建成指向目录 target 的联接/符号链接；成功返回 True。"""
    target = Path(target)
    link = Path(link)
    try:
        if os.path.exists(str(link)) or os.path.islink(str(link)):
            return False
    except OSError:
        return False
    if os.name == 'nt':
        try:
            import _winapi
            _winapi.CreateJunction(str(target), str(link))
            return True
        except Exception:
            pass
    try:
        os.symlink(str(target), str(link), target_is_directory=True)
        return True
    except Exception:
        return False


def _remove_dir_link(link):
    """尽力删除目录联接/符号链接（不触碰目标），失败不抛。"""
    path = str(link)
    for func in (os.rmdir, os.unlink):
        try:
            func(path)
            return
        except Exception:
            continue


class AudioIngestCase(unittest.TestCase):
    """历史语音条用例的公共夹具。"""

    SID = '20260910-100000-aaaaaa'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tmp_path = Path(self.tmp.name)
        self.person_dir = self.tmp_path / 'people' / 'mama'
        self.sessions_dir = self.person_dir / 'sessions'
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        # out_dir 必须位于 person_dir 之内
        self.out_dir = self.person_dir / 'archive_out' / 'sessions_data'
        self.out_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ 工具

    def ingest(self, **kw):
        kw.setdefault('per_viewer_subdir', True)
        return ingest_sessions.ingest(self.person_dir, self.out_dir, **kw)

    def _put_audio_source(self, basename, data=AUDIO_BYTES):
        d = self.sessions_dir / '2026-09' / 'audio'
        d.mkdir(parents=True, exist_ok=True)
        path = d / basename
        path.write_bytes(data)
        return path

    def _rel_audio(self, basename):
        return f'2026-09/audio/{basename}'

    def _load_payload(self, viewer):
        path = self.out_dir / viewer / 'sessions.json'
        self.assertTrue(path.is_file(), f'缺少产物 {path}')
        with open(path, encoding='utf-8') as f:
            return json.load(f)

    def _session(self, payload, sid):
        for s in payload.get('sessions', []):
            if s.get('session_id') == sid:
                return s
        self.fail(f'会话 {sid} 不在产物中: {payload!r}')

    def _turn(self, session, role):
        for t in session.get('turns', []):
            if t.get('role') == role:
                return t
        self.fail(f'{role} 回合不存在: {session!r}')

    def _audio_dir_files(self, viewer):
        d = self.out_dir / viewer / 'audio'
        if not d.exists():
            return []
        return sorted(p.name for p in d.iterdir() if p.is_file())

    def _write_father_session_with_audio(self, sid, basename,
                                         user_text='爸爸你好',
                                         sim_text='爸爸回复',
                                         audio_text='爸爸回复',
                                         duration_s=1.5):
        return _write_session(self.sessions_dir, sid, [
            _base_record(sid, 1, 'user', user_text, TS_USER, viewer='father'),
            _base_record(sid, 1, 'simulacrum', sim_text, TS_SIM, viewer='father'),
            _audio_record(sid, 1, audio_text, self._rel_audio(basename), TS_AUD1,
                          viewer='father', duration_s=duration_s),
        ])

    def _assert_dur_ok(self, value):
        self.assertTrue(value is None or isinstance(value, (int, float)),
                        f'dur 应为数值或 None，实际为 {value!r}')

    # -------------------------------------------------------------- 安全工具

    def _make_file_link(self, target, link):
        """建立指向文件的符号链接；失败返回 False。"""
        try:
            if os.path.exists(str(link)) or os.path.islink(str(link)):
                return False
        except OSError:
            return False
        try:
            os.symlink(str(target), str(link))
            return True
        except (OSError, NotImplementedError, AttributeError):
            return False

    def _make_file_hardlink(self, target, link):
        """建立指向文件的硬链接；失败返回 False。"""
        try:
            if os.path.exists(str(link)) or os.path.islink(str(link)):
                return False
        except OSError:
            return False
        try:
            os.link(str(target), str(link))
            return True
        except (OSError, NotImplementedError, AttributeError):
            return False


class TestAudioAttachAndCopy(AudioIngestCase):
    """有效音频被附到数字人回合并复制到 out_dir/<viewer>/audio/。"""

    def test_simulacrum_turn_gets_audio_and_files_copied(self):
        sid = self.SID
        b1 = _wav_name(sid, 1)
        b2 = _wav_name(sid, 1, suffix=2)
        self._put_audio_source(b1, AUDIO_BYTES)
        self._put_audio_source(b2, AUDIO_BYTES_ALT)
        _write_session(self.sessions_dir, sid, [
            _base_record(sid, 1, 'user', '爸爸你好', TS_USER, viewer='father'),
            _base_record(sid, 1, 'simulacrum', '今天天气不错。明天也是。', TS_SIM,
                         viewer='father'),
            _audio_record(sid, 1, '今天天气不错。', self._rel_audio(b1), TS_AUD1,
                          viewer='father', duration_s=1.5),
            _audio_record(sid, 1, '明天也是。', self._rel_audio(b2), TS_AUD2,
                          viewer='father', duration_s=2.25),
        ])
        result = self.ingest()

        payload = self._load_payload('father')
        turn = self._turn(self._session(payload, sid), 'simulacrum')
        self.assertIn('audio', turn)
        audio = turn['audio']
        self.assertEqual(len(audio), 2)
        self.assertEqual([item['text'] for item in audio],
                         ['今天天气不错。', '明天也是。'])
        self.assertEqual([item['file'] for item in audio],
                         [f'audio/{b1}', f'audio/{b2}'])
        self.assertEqual([item['dur'] for item in audio], [1.5, 2.25])
        for item in audio:
            self.assertEqual(set(item.keys()), {'text', 'file', 'dur'})
            self._assert_dur_ok(item['dur'])

        out1 = self.out_dir / 'father' / 'audio' / b1
        out2 = self.out_dir / 'father' / 'audio' / b2
        self.assertTrue(out1.is_file(), '音频文件未被复制')
        self.assertTrue(out2.is_file(), '音频文件未被复制')
        self.assertEqual(out1.read_bytes(), AUDIO_BYTES)
        self.assertEqual(out2.read_bytes(), AUDIO_BYTES_ALT)

        self.assertEqual(result['audio']['copied'], 2)
        self.assertEqual(result['audio']['unchanged'], 0)
        self.assertEqual(result['audio']['rejected'], 0)


class TestFlatModeUnchanged(AudioIngestCase):
    """关闭 per_viewer_subdir 时保持旧行为。"""

    def test_flat_mode_has_no_audio_anything(self):
        sid = self.SID
        b1 = _wav_name(sid, 1)
        b2 = _wav_name(sid, 1, suffix=2)
        self._put_audio_source(b1, AUDIO_BYTES)
        self._put_audio_source(b2, AUDIO_BYTES_ALT)
        _write_session(self.sessions_dir, sid, [
            _base_record(sid, 1, 'user', '爸爸你好', TS_USER, viewer='father'),
            _base_record(sid, 1, 'simulacrum', '今天天气不错。明天也是。', TS_SIM,
                         viewer='father'),
            _audio_record(sid, 1, '今天天气不错。', self._rel_audio(b1), TS_AUD1,
                          viewer='father', duration_s=1.5),
            _audio_record(sid, 1, '明天也是。', self._rel_audio(b2), TS_AUD2,
                          viewer='father', duration_s=2.25),
        ])
        result = self.ingest(per_viewer_subdir=False)

        self.assertNotIn('audio', result)
        self.assertEqual(list(self.out_dir.rglob('audio')), [],
                         'flat 模式不应产生任何 audio 目录')

        payload_path = self.out_dir / 'sessions_father.json'
        self.assertTrue(payload_path.is_file())
        payload = json.loads(payload_path.read_text(encoding='utf-8'))
        session = self._session(payload, sid)
        self.assertTrue(session.get('turns'), '夹具应产生回合')
        for turn in session['turns']:
            self.assertNotIn('audio', turn)

        for path in self.out_dir.glob('*.json'):
            data = json.loads(path.read_text(encoding='utf-8'))
            for s in data.get('sessions', []):
                for t in s.get('turns', []):
                    self.assertNotIn('audio', t)


class TestViewerIsolation(AudioIngestCase):
    """viewer 隔离：owner 的音频不落进 father 目录；viewer 不一致不匹配。"""

    def test_owner_audio_never_lands_in_father_dir(self):
        father_sid = self.SID
        owner_sid = '20260910-110000-bbbbbb'
        fb = _wav_name(father_sid, 1)
        ob = _wav_name(owner_sid, 1)
        self._put_audio_source(fb, AUDIO_BYTES)
        self._put_audio_source(ob, AUDIO_BYTES_ALT)

        _write_session(self.sessions_dir, father_sid, [
            _base_record(father_sid, 1, 'user', '爸爸你好', TS_USER, viewer='father'),
            _base_record(father_sid, 1, 'simulacrum', '爸爸回复', TS_SIM,
                         viewer='father'),
            _audio_record(father_sid, 1, '爸爸回复', self._rel_audio(fb), TS_AUD1,
                          viewer='father', duration_s=1.5),
        ])
        _write_session(self.sessions_dir, owner_sid, [
            _base_record(owner_sid, 1, 'user', '主人你好', TS_USER),
            _base_record(owner_sid, 1, 'simulacrum', '主人回复', TS_SIM),
            _audio_record(owner_sid, 1, '主人回复', self._rel_audio(ob), TS_AUD1,
                          duration_s=2.25),
        ])
        self.ingest()

        self.assertEqual(self._audio_dir_files('father'), [fb])
        self.assertEqual(self._audio_dir_files('owner'), [ob])

        father_turn = self._turn(self._session(self._load_payload('father'),
                                               father_sid), 'simulacrum')
        owner_turn = self._turn(self._session(self._load_payload('owner'),
                                              owner_sid), 'simulacrum')
        self.assertEqual([a['file'] for a in father_turn['audio']], [f'audio/{fb}'])
        self.assertEqual([a['file'] for a in owner_turn['audio']], [f'audio/{ob}'])

        father_raw = json.dumps(self._load_payload('father'), ensure_ascii=False)
        owner_raw = json.dumps(self._load_payload('owner'), ensure_ascii=False)
        self.assertNotIn(ob, father_raw)
        self.assertNotIn(fb, owner_raw)

    def test_audio_with_mismatched_viewer_is_not_attached(self):
        sid = self.SID
        b = _wav_name(sid, 1)
        self._put_audio_source(b, AUDIO_BYTES)
        _write_session(self.sessions_dir, sid, [
            _base_record(sid, 1, 'user', '爸爸你好', TS_USER, viewer='father'),
            _base_record(sid, 1, 'simulacrum', '爸爸回复', TS_SIM, viewer='father'),
            _audio_record(sid, 1, '爸爸回复', self._rel_audio(b), TS_AUD1,
                          viewer='owner', duration_s=1.5),
        ])
        result = self.ingest()

        payload = self._load_payload('father')
        turn = self._turn(self._session(payload, sid), 'simulacrum')
        self.assertNotIn('audio', turn)
        self.assertEqual(self._audio_dir_files('father'), [])
        self.assertFalse((self.out_dir / 'father' / 'audio' / b).exists())
        self.assertEqual(result['audio']['copied'], 0)


class TestExclusionRetraction(AudioIngestCase):
    """会话被排除后，上一轮复制过去的音频被清理。"""

    def test_excluded_session_audio_is_removed_on_rerun(self):
        sid = self.SID
        b = _wav_name(sid, 1)
        self._put_audio_source(b, AUDIO_BYTES)
        self._write_father_session_with_audio(sid, b)

        result1 = self.ingest()
        self.assertEqual(result1['audio']['copied'], 1)
        target = self.out_dir / 'father' / 'audio' / b
        self.assertTrue(target.is_file())

        _append_session(self.sessions_dir, sid, [
            _base_record(sid, 1, 'event', ingest_sessions.EXCLUDE_EVENT_TEXT,
                         '2026-09-10T10:00:09+08:00', viewer='father'),
        ])
        result2 = self.ingest()
        self.assertFalse(target.exists(), '被排除会话的音频应从 father/audio 删除')
        self.assertIn(f'father/audio/{b}', result2['deleted'])


class TestRedactedTurn(AudioIngestCase):
    """被敏感省略的数字人回合不附音频、不复制文件。"""

    def test_redacted_simulacrum_turn_has_no_audio(self):
        repo_root = Path(__file__).resolve().parent.parent
        patterns_path = repo_root / 'tools' / 'sensitive_patterns.json'
        if not patterns_path.exists():
            self.skipTest('sensitive_patterns.json 不存在')

        sid = self.SID
        b = _wav_name(sid, 1)
        self._put_audio_source(b, AUDIO_BYTES)
        _write_session(self.sessions_dir, sid, [
            _base_record(sid, 1, 'user', '你好', TS_USER, viewer='father'),
            _base_record(sid, 1, 'simulacrum', '我的密码123是', TS_SIM,
                         viewer='father'),
            _audio_record(sid, 1, '我的密码123是', self._rel_audio(b), TS_AUD1,
                          viewer='father', duration_s=1.5),
        ])
        self.ingest(patterns_path=patterns_path)

        payload = self._load_payload('father')
        turn = self._turn(self._session(payload, sid), 'simulacrum')
        self.assertEqual(turn['text'], ingest_sessions.REDACTED_TEXT)
        self.assertNotIn('audio', turn)
        self.assertFalse((self.out_dir / 'father' / 'audio' / b).exists())


class TestRejectedAudio(AudioIngestCase):
    """非法音频记录被丢弃并计入 rejected，且不抛异常。"""

    def test_cross_session_reference_rejected(self):
        sid_a = self.SID
        sid_b = '20260910-120000-cccccc'
        b_b = _wav_name(sid_b, 1)
        # 会话 B 的文件真实存在，但它不属于会话 A
        self._put_audio_source(b_b, AUDIO_BYTES)
        _write_session(self.sessions_dir, sid_a, [
            _base_record(sid_a, 1, 'user', '爸爸你好', TS_USER, viewer='father'),
            _base_record(sid_a, 1, 'simulacrum', '爸爸回复', TS_SIM, viewer='father'),
            _audio_record(sid_a, 1, '爸爸回复', self._rel_audio(b_b), TS_AUD1,
                          viewer='father', duration_s=1.5),
        ])
        result = self.ingest()

        payload = self._load_payload('father')
        turn = self._turn(self._session(payload, sid_a), 'simulacrum')
        self.assertNotIn('audio', turn)
        self.assertFalse((self.out_dir / 'father' / 'audio' / b_b).exists())
        self.assertGreaterEqual(result['audio']['rejected'], 1)

    def test_path_traversal_rejected(self):
        sid = self.SID
        b = _wav_name(sid, 1)
        raw_dir = self.person_dir / 'raw'
        raw_dir.mkdir(parents=True, exist_ok=True)
        (raw_dir / b).write_bytes(AUDIO_BYTES)

        _write_session(self.sessions_dir, sid, [
            _base_record(sid, 1, 'user', '爸爸你好', TS_USER, viewer='father'),
            _base_record(sid, 1, 'simulacrum', '爸爸回复', TS_SIM, viewer='father'),
            _audio_record(sid, 1, '爸爸回复', f'../../raw/{b}', TS_AUD1,
                          viewer='father', duration_s=1.5),
        ])
        result = self.ingest()

        payload = self._load_payload('father')
        turn = self._turn(self._session(payload, sid), 'simulacrum')
        self.assertNotIn('audio', turn)
        self.assertFalse((self.out_dir / 'father' / 'audio' / b).exists())
        self.assertGreaterEqual(result['audio']['rejected'], 1)

    def test_missing_source_file_rejected(self):
        sid = self.SID
        b = _wav_name(sid, 1)  # 故意不创建源文件
        _write_session(self.sessions_dir, sid, [
            _base_record(sid, 1, 'user', '爸爸你好', TS_USER, viewer='father'),
            _base_record(sid, 1, 'simulacrum', '爸爸回复', TS_SIM, viewer='father'),
            _audio_record(sid, 1, '爸爸回复', self._rel_audio(b), TS_AUD1,
                          viewer='father', duration_s=1.5),
        ])
        result = self.ingest()  # 不应抛异常

        payload = self._load_payload('father')
        turn = self._turn(self._session(payload, sid), 'simulacrum')
        self.assertNotIn('audio', turn)
        self.assertGreaterEqual(result['audio']['rejected'], 1)


class TestStaleAudioCleanup(AudioIngestCase):
    """陈旧音频被删除，无关文件保留。"""

    def test_stale_audio_deleted_and_other_files_kept(self):
        sid = self.SID
        b = _wav_name(sid, 1)
        stale = _wav_name(sid, 9)
        self._put_audio_source(b, AUDIO_BYTES)
        self._write_father_session_with_audio(sid, b)

        audio_dir = self.out_dir / 'father' / 'audio'
        audio_dir.mkdir(parents=True, exist_ok=True)
        notes = audio_dir / 'notes.txt'
        notes.write_text('keep me', encoding='utf-8')
        stale_path = audio_dir / stale
        stale_path.write_bytes(AUDIO_BYTES_ALT)

        result = self.ingest()

        self.assertFalse(stale_path.exists(), '陈旧音频应被删除')
        self.assertTrue(notes.is_file(), '不匹配正则的文件应保留')
        self.assertEqual(notes.read_text(encoding='utf-8'), 'keep me')
        self.assertTrue((audio_dir / b).is_file())
        self.assertIn(f'father/audio/{stale}', result['deleted'])
        self.assertNotIn(f'father/audio/{b}', result['deleted'])


class TestIdempotency(AudioIngestCase):
    """重复运行：第二次不复制、计 unchanged、mtime 不变。"""

    def test_second_run_copies_nothing(self):
        sid = self.SID
        b1 = _wav_name(sid, 1)
        b2 = _wav_name(sid, 1, suffix=2)
        self._put_audio_source(b1, AUDIO_BYTES)
        self._put_audio_source(b2, AUDIO_BYTES_ALT)
        _write_session(self.sessions_dir, sid, [
            _base_record(sid, 1, 'user', '爸爸你好', TS_USER, viewer='father'),
            _base_record(sid, 1, 'simulacrum', '爸爸回复', TS_SIM, viewer='father'),
            _audio_record(sid, 1, '爸爸回复', self._rel_audio(b1), TS_AUD1,
                          viewer='father', duration_s=1.5),
            _audio_record(sid, 1, '爸爸回复', self._rel_audio(b2), TS_AUD2,
                          viewer='father', duration_s=2.25),
        ])

        result1 = self.ingest()
        self.assertEqual(result1['audio']['copied'], 2)

        targets = [self.out_dir / 'father' / 'audio' / b1,
                   self.out_dir / 'father' / 'audio' / b2]
        before = {p: p.stat().st_mtime_ns for p in targets}

        with mock.patch('ingest_sessions.shutil.copy2') as copy2_mock:
            result2 = self.ingest()
            self.assertFalse(copy2_mock.called,
                             '第二次运行不应调用 shutil.copy2')

        self.assertEqual(result2['audio']['copied'], 0)
        self.assertEqual(result2['audio']['unchanged'], len(targets))
        for p in targets:
            self.assertTrue(p.is_file())
            self.assertEqual(p.stat().st_mtime_ns, before[p],
                             '幂等运行时不应改写目标文件')


class TestLinkedAudioDir(AudioIngestCase):
    """目标 audio 目录是联接/符号链接时不写穿。"""

    def test_linked_audio_dir_is_not_written_through(self):
        sid = self.SID
        b = _wav_name(sid, 1)
        self._put_audio_source(b, AUDIO_BYTES)
        self._write_father_session_with_audio(sid, b)

        target = self.tmp_path / 'audio_target'
        target.mkdir(parents=True, exist_ok=True)
        link = self.out_dir / 'father' / 'audio'
        link.parent.mkdir(parents=True, exist_ok=True)
        if not _make_dir_link(target, link):
            self.skipTest('无法创建目录联接/符号链接（需 Windows 联接或 symlink 权限）')
        self.addCleanup(_remove_dir_link, link)

        self.ingest()

        self.assertEqual(list(target.iterdir()), [],
                         '不应写穿到联接目标目录')
        self.assertFalse((target / b).exists())

        payload = self._load_payload('father')
        turn = self._turn(self._session(payload, sid), 'simulacrum')
        self.assertNotIn('audio', turn)


class TestOutputRootAlias(AudioIngestCase):
    """输出根内的别名目录不会导致真实音频被误删。"""

    def test_alias_dir_does_not_delete_real_audio(self):
        sid = self.SID
        b = _wav_name(sid, 1)
        self._put_audio_source(b, AUDIO_BYTES)
        self._write_father_session_with_audio(sid, b)

        self.ingest()
        real = self.out_dir / 'father' / 'audio' / b
        self.assertTrue(real.is_file())

        ghost = self.out_dir / 'ghost'
        if not _make_dir_link(self.out_dir / 'father', ghost):
            self.skipTest('无法创建目录联接/符号链接（需 Windows 联接或 symlink 权限）')
        self.addCleanup(_remove_dir_link, ghost)

        self.ingest()

        self.assertTrue(real.is_file(), '别名目录存在时真实音频不应被删除')
        self.assertEqual(self._audio_dir_files('father'), [b])


# ================================================================ 新增安全用例


class TestSymlinkedSourceRejected(AudioIngestCase):
    """源文件是符号链接、指向另一个会话文件时被拒绝。"""

    def test_symlink_source_pointing_elsewhere_is_rejected(self):
        sid_a = self.SID
        sid_b = '20260910-130000-dddddd'
        b_b = _wav_name(sid_b, 1)
        link_name = _wav_name(sid_a, 1)

        real = self._put_audio_source(b_b, AUDIO_BYTES)
        link = real.parent / link_name
        if not self._make_file_link(real, link):
            self.skipTest('无法创建符号链接（Windows 常无权限）')

        _write_session(self.sessions_dir, sid_a, [
            _base_record(sid_a, 1, 'user', '爸爸你好', TS_USER, viewer='father'),
            _base_record(sid_a, 1, 'simulacrum', '爸爸回复', TS_SIM, viewer='father'),
            _audio_record(sid_a, 1, '爸爸回复', self._rel_audio(link_name), TS_AUD1,
                          viewer='father', duration_s=1.5),
        ])
        result = self.ingest()

        payload = self._load_payload('father')
        turn = self._turn(self._session(payload, sid_a), 'simulacrum')
        self.assertNotIn('audio', turn)

        leaked = [p for p in self.out_dir.rglob(f'session_{sid_b}*') if p.is_file()]
        self.assertEqual(leaked, [],
                         f'out 下不应出现会话 B 的文件: {leaked}')
        self.assertFalse((self.out_dir / 'father' / 'audio' / b_b).exists())
        self.assertGreaterEqual(result['audio']['rejected'], 1)


class TestUnsafeFilenameRejected(AudioIngestCase):
    """file 含反斜杠或冒号字符一律被拒绝。"""

    def test_backslash_and_colon_in_file_are_rejected(self):
        sid = self.SID
        b = _wav_name(sid, 1)
        self._put_audio_source(b, AUDIO_BYTES)
        bad_backslash = '2026-09\\..\\2026-09/audio/' + b
        bad_colon = 'C:/x/' + b
        _write_session(self.sessions_dir, sid, [
            _base_record(sid, 1, 'user', '爸爸你好', TS_USER, viewer='father'),
            _base_record(sid, 1, 'simulacrum', '爸爸回复', TS_SIM, viewer='father'),
            _audio_record(sid, 1, '爸爸回复', bad_backslash, TS_AUD1,
                          viewer='father', duration_s=1.5),
            _audio_record(sid, 1, '爸爸回复', bad_colon, TS_AUD2,
                          viewer='father', duration_s=1.5),
        ])
        result = self.ingest()

        payload = self._load_payload('father')
        turn = self._turn(self._session(payload, sid), 'simulacrum')
        self.assertNotIn('audio', turn)
        self.assertEqual(self._audio_dir_files('father'), [])
        self.assertGreaterEqual(result['audio']['rejected'], 2)


class TestHardlinkedTargetNotReused(AudioIngestCase):
    """目标文件是硬链接（st_nlink > 1）时必须重新独立复制。"""

    def test_hardlinked_existing_target_is_recopied(self):
        sid = self.SID
        b = _wav_name(sid, 1)
        src = self._put_audio_source(b, AUDIO_BYTES)
        self._write_father_session_with_audio(sid, b)

        self.ingest()
        target = self.out_dir / 'father' / 'audio' / b
        self.assertTrue(target.is_file())

        victim = self.tmp_path / 'victim.wav'
        victim.write_bytes(AUDIO_BYTES)
        st = src.stat()
        os.utime(str(victim), ns=(st.st_atime_ns, st.st_mtime_ns))

        target.unlink()
        if not self._make_file_hardlink(victim, target):
            self.skipTest('无法创建硬链接')

        self.ingest()

        self.assertTrue(target.is_file())
        self.assertNotEqual(target.stat().st_ino, victim.stat().st_ino,
                            '硬链接目标应被重新独立复制')
        self.assertEqual(victim.read_bytes(), AUDIO_BYTES, '受害文件内容不应被改动')
        self.assertEqual(target.read_bytes(), AUDIO_BYTES)


class TestPreexistingTmpNotWrittenThrough(AudioIngestCase):
    """预先存在的 .tmp 硬链接不被写穿。"""

    def test_preexisting_tmp_hardlink_is_not_written_through(self):
        sid = self.SID
        b = _wav_name(sid, 1)
        self._put_audio_source(b, AUDIO_BYTES)
        self._write_father_session_with_audio(sid, b)

        audio_dir = self.out_dir / 'father' / 'audio'
        audio_dir.mkdir(parents=True, exist_ok=True)
        sentinel = self.tmp_path / 'sentinel.bin'
        sentinel.write_bytes(b'SENTINEL')
        tmp_link = audio_dir / (b + '.tmp')
        if not self._make_file_hardlink(sentinel, tmp_link):
            self.skipTest('无法创建硬链接')

        result = self.ingest()

        self.assertEqual(sentinel.read_bytes(), b'SENTINEL',
                         '预先存在的 .tmp 不应被写穿')
        target = audio_dir / b
        self.assertTrue(target.is_file())
        self.assertEqual(target.read_bytes(), AUDIO_BYTES)
        self.assertGreaterEqual(result['audio']['copied'], 1)


class TestOutputOverlapsSourceRejected(AudioIngestCase):
    """per-viewer 模式下 out_dir 与 sessions 目录重叠时拒绝运行。"""

    def test_out_dir_overlapping_sessions_is_rejected(self):
        sid = self.SID
        b = _wav_name(sid, 1)
        self._put_audio_source(b, AUDIO_BYTES)
        self._write_father_session_with_audio(sid, b)

        before = {}
        for p in sorted(self.sessions_dir.rglob('*')):
            if p.is_file():
                before[p] = p.read_bytes()
        self.assertTrue(before, '夹具应至少有一个源文件')

        candidates = [self.person_dir / 'sessions',
                      self.person_dir / 'sessions' / 'out']
        for out in candidates:
            with self.assertRaises(ValueError):
                ingest_sessions.ingest(self.person_dir, out, per_viewer_subdir=True)

        for p, data in before.items():
            self.assertTrue(p.is_file(), f'源文件被删除: {p}')
            self.assertEqual(p.read_bytes(), data, f'源文件被改动: {p}')


class TestCrossProcessLock(AudioIngestCase):
    """跨进程排他锁：另一进程持锁时本进程超时失败。"""

    def test_out_lock_is_cross_process(self):
        tools_dir = str(Path(__file__).resolve().parent.parent / 'tools')
        code = (
            "import sys, time\n"
            f"sys.path.insert(0, {tools_dir!r})\n"
            "import ingest_sessions\n"
            f"with ingest_sessions._acquire_out_lock({str(self.person_dir)!r}, "
            f"{str(self.out_dir)!r}):\n"
            "    sys.stdout.write('LOCKED\\n')\n"
            "    sys.stdout.flush()\n"
            "    time.sleep(4)\n"
        )
        proc = subprocess.Popen([sys.executable, '-c', code],
                                stdout=subprocess.PIPE, text=True)
        try:
            line = proc.stdout.readline()
            self.assertEqual(line.strip(), 'LOCKED',
                             f'子进程未能持锁，输出为 {line!r}')
            with self.assertRaises(ingest_sessions.IngestLockTimeout):
                with ingest_sessions._acquire_out_lock(self.person_dir,
                                                       self.out_dir,
                                                       timeout_s=1.0):
                    self.fail('子进程持锁时不应取得锁')
            proc.wait(timeout=15)
        finally:
            if proc.poll() is None:
                proc.kill()
            try:
                proc.wait(timeout=10)
            except Exception:
                pass
            if proc.stdout is not None:
                proc.stdout.close()

        actual_lock = Path(ingest_sessions._out_lock_path(self.person_dir,
                                                          self.out_dir))
        lock_dir = self.person_dir / '.ingest_locks'
        self.assertEqual(actual_lock.parent.resolve(), lock_dir.resolve(),
                         '锁文件应位于 person_dir/.ingest_locks/ 下')
        self.assertTrue(actual_lock.name.endswith('.lock'),
                        f'锁文件名应以 .lock 结尾: {actual_lock.name}')
        resolved_lock = actual_lock.resolve()
        self.assertNotEqual(resolved_lock, self.out_dir.resolve(),
                            '锁文件不应就是 out_dir 本身')
        self.assertNotIn(self.out_dir.resolve(), resolved_lock.parents,
                         '锁文件不应落在 out_dir 之内')
        self.assertEqual(len(actual_lock.name), len('.lock') + 40,
                         f'锁文件名应为 40 位十六进制摘要 + .lock: {actual_lock.name}')

        with ingest_sessions._acquire_out_lock(self.person_dir, self.out_dir):
            pass
        self.assertTrue(actual_lock.exists(), '锁文件应存在于 person_dir 下')


class TestCopyFailureNotPublished(AudioIngestCase):
    """复制失败时不发布引用，也不留临时文件。"""

    def test_copy_failure_leaves_no_reference_or_tmp(self):
        sid = self.SID
        b = _wav_name(sid, 1)
        self._put_audio_source(b, AUDIO_BYTES)
        self._write_father_session_with_audio(sid, b)

        with mock.patch('ingest_sessions.shutil.copy2',
                        side_effect=OSError('boom')):
            result = self.ingest()

        payload = self._load_payload('father')
        turn = self._turn(self._session(payload, sid), 'simulacrum')
        self.assertNotIn('audio', turn)
        self.assertFalse((self.out_dir / 'father' / 'audio' / b).exists(),
                         '复制失败时不应生成目标文件')
        self.assertGreaterEqual(result['audio']['rejected'], 1)

        audio_dir = self.out_dir / 'father' / 'audio'
        leftovers = []
        if audio_dir.exists():
            leftovers = [p.name for p in audio_dir.iterdir()
                         if p.name.endswith('.tmp')]
        self.assertEqual(leftovers, [],
                         f'复制失败后不应残留 .tmp 文件: {leftovers}')


class TestSourceFilesNeverModified(AudioIngestCase):
    """源会话文件在 ingest 全过程中永不被改动或删除。"""

    def _hash_sources(self):
        result = {}
        for p in sorted(self.sessions_dir.rglob('*')):
            if p.is_file() and p.suffix in ('.wav', '.jsonl'):
                result[p] = hashlib.sha256(p.read_bytes()).hexdigest()
        return result

    def _assert_same_sources(self, before, after):
        self.assertEqual(set(after.keys()), set(before.keys()),
                         '源文件集合发生变化')
        for p, digest in before.items():
            self.assertTrue(p.is_file(), f'源文件被删除: {p}')
            self.assertEqual(after[p], digest, f'源文件被改动: {p}')

    def test_source_files_unchanged_across_runs(self):
        sid = self.SID
        b = _wav_name(sid, 1)
        self._put_audio_source(b, AUDIO_BYTES)
        self._write_father_session_with_audio(sid, b)

        snap0 = self._hash_sources()
        self.assertTrue(snap0, '夹具应至少有一个源文件')

        self.ingest()
        snap1 = self._hash_sources()
        self._assert_same_sources(snap0, snap1)

        _append_session(self.sessions_dir, sid, [
            _base_record(sid, 1, 'event', ingest_sessions.EXCLUDE_EVENT_TEXT,
                         '2026-09-10T10:00:09+08:00', viewer='father'),
        ])
        snap2 = self._hash_sources()
        self.ingest()  # 触发陈旧清理
        snap3 = self._hash_sources()
        self._assert_same_sources(snap2, snap3)


# ============================================================ 大小写变体与锁位置


class TestCaseVariantLockAlias(AudioIngestCase):
    """Windows：同一目录的大小写变体必须共用同一把锁（目录尚不存在时也一样）。"""

    def test_case_variant_out_dirs_share_one_lock(self):
        if os.name != 'nt':
            self.skipTest('只有大小写不敏感的文件系统（Windows）需要该保证')

        upper_out = self.person_dir / 'archive_out' / 'Sess_Out'
        lower_out = self.person_dir / 'archive_out' / 'sess_out'
        self.assertFalse(upper_out.exists(), '夹具要求该输出目录尚不存在')
        self.assertFalse(lower_out.exists(), '夹具要求该输出目录尚不存在')

        tools_dir = str(Path(__file__).resolve().parent.parent / 'tools')
        code = (
            "import sys, time\n"
            f"sys.path.insert(0, {tools_dir!r})\n"
            "import ingest_sessions\n"
            f"with ingest_sessions._acquire_out_lock({str(self.person_dir)!r}, "
            f"{str(upper_out)!r}):\n"
            "    sys.stdout.write('LOCKED\\n')\n"
            "    sys.stdout.flush()\n"
            "    time.sleep(4)\n"
        )
        proc = subprocess.Popen([sys.executable, '-c', code],
                                stdout=subprocess.PIPE, text=True)
        try:
            line = proc.stdout.readline()
            self.assertEqual(line.strip(), 'LOCKED',
                             f'子进程未能持锁，输出为 {line!r}')
            self.assertEqual(
                ingest_sessions._out_lock_path(self.person_dir, upper_out),
                ingest_sessions._out_lock_path(self.person_dir, lower_out),
                '同一目录的不同大小写写法应得到同一个锁文件路径')
            with self.assertRaises(ingest_sessions.IngestLockTimeout):
                with ingest_sessions._acquire_out_lock(self.person_dir, lower_out,
                                                       timeout_s=1.0):
                    self.fail('大写变体持锁时小写变体不应取得锁')
            proc.wait(timeout=15)
        finally:
            if proc.poll() is None:
                proc.kill()
            try:
                proc.wait(timeout=10)
            except Exception:
                pass
            if proc.stdout is not None:
                proc.stdout.close()


# ==================================================== 无特权的「源侧换名」用例


class TestRenamedSourceWithoutSymlink(AudioIngestCase):
    """无需符号链接权限的换名复刻：解析后 basename 变成别的会话时必须拒绝。"""

    def test_source_resolving_to_other_session_is_rejected(self):
        sid_a = self.SID
        sid_b = '20260910-140000-eeeeee'
        b_a = _wav_name(sid_a, 1)
        b_b = _wav_name(sid_b, 1)

        real_a = self._put_audio_source(b_a, AUDIO_BYTES)
        real_b = self._put_audio_source(b_b, AUDIO_BYTES_ALT)

        _write_session(self.sessions_dir, sid_a, [
            _base_record(sid_a, 1, 'user', '爸爸你好', TS_USER, viewer='father'),
            _base_record(sid_a, 1, 'simulacrum', '爸爸回复', TS_SIM, viewer='father'),
            _audio_record(sid_a, 1, '爸爸回复', self._rel_audio(b_a), TS_AUD1,
                          viewer='father', duration_s=1.5),
        ])

        original_resolve = Path.resolve
        key_a = os.path.normcase(str(real_a))

        def fake_resolve(path_self, *args, **kwargs):
            if os.path.normcase(str(path_self)) == key_a:
                return original_resolve(real_b, *args, **kwargs)
            return original_resolve(path_self, *args, **kwargs)

        with mock.patch.object(Path, 'resolve', autospec=True,
                               side_effect=fake_resolve):
            result = self.ingest()

        payload = self._load_payload('father')
        turn = self._turn(self._session(payload, sid_a), 'simulacrum')
        self.assertNotIn('audio', turn)
        leaked = [p for p in self.out_dir.rglob(f'session_{sid_b}*') if p.is_file()]
        self.assertEqual(leaked, [], f'out 下不应出现会话 B 的文件: {leaked}')
        self.assertFalse((self.out_dir / 'father' / 'audio' / b_b).exists())
        self.assertGreaterEqual(result['audio']['rejected'], 1)


# ============================================================== 重叠：祖先方向


class TestOutDirAboveSessionsRejected(AudioIngestCase):
    """out_dir 位于 sessions 之上（person_dir 本身）时也必须被拒。"""

    def test_out_dir_ancestor_of_sessions_is_rejected(self):
        sid = self.SID
        b = _wav_name(sid, 1)
        self._put_audio_source(b, AUDIO_BYTES)
        self._write_father_session_with_audio(sid, b)

        before = {}
        for p in sorted(self.sessions_dir.rglob('*')):
            if p.is_file():
                before[p] = p.read_bytes()
        self.assertTrue(before, '夹具应至少有一个源文件')

        with self.assertRaises(ValueError):
            ingest_sessions.ingest(self.person_dir, self.person_dir,
                                   per_viewer_subdir=True)

        for p, data in before.items():
            self.assertTrue(p.is_file(), f'源文件被删除: {p}')
            self.assertEqual(p.read_bytes(), data, f'源文件被改动: {p}')


# ============================================================= CLI 重叠返回码


class TestCliOverlapReturnsTwo(AudioIngestCase):
    """CLI 在 per-viewer 模式遇到重叠时返回 2，而不是抛栈。"""

    def test_cli_overlapping_out_dir_returns_two(self):
        sid = self.SID
        b = _wav_name(sid, 1)
        self._put_audio_source(b, AUDIO_BYTES)
        self._write_father_session_with_audio(sid, b)

        before = {}
        for p in sorted(self.sessions_dir.rglob('*')):
            if p.is_file():
                before[p] = p.read_bytes()
        self.assertTrue(before, '夹具应至少有一个源文件')

        people_dir = self.tmp_path / 'people'
        argv = ['ingest_sessions.py', '--person', 'mama',
                '--out-dir', str(self.person_dir / 'sessions'),
                '--per-viewer-subdir']
        stderr = io.StringIO()
        with mock.patch.object(ingest_sessions, 'PEOPLE_DIR', people_dir), \
                mock.patch.object(sys, 'argv', argv), \
                contextlib.redirect_stderr(stderr):
            code = ingest_sessions.main()

        self.assertEqual(code, 2, '重叠时应返回 2')
        for p, data in before.items():
            self.assertTrue(p.is_file(), f'源文件被删除: {p}')
            self.assertEqual(p.read_bytes(), data, f'源文件被改动: {p}')


# ================================================ SID 大小写变体（仅 Windows）


class TestCaseInsensitiveSidCollision(AudioIngestCase):
    """Windows：SID 只差大小写时，复用判断与陈旧清理都必须按 normcase 比较。"""

    def setUp(self):
        super().setUp()
        if os.name != 'nt':
            self.skipTest('只有大小写不敏感的文件系统（Windows）需要该保证')

    def test_sid_case_variant_reuse_is_not_deleted(self):
        import shutil

        sid = self.SID
        b = _wav_name(sid, 1)
        b_upper = _wav_name(sid.upper(), 1)
        self.assertNotEqual(b, b_upper)

        src = self._put_audio_source(b, AUDIO_BYTES)
        self._write_father_session_with_audio(sid, b)

        audio_dir = self.out_dir / 'father' / 'audio'
        audio_dir.mkdir(parents=True, exist_ok=True)
        # 只有 SID 部分大写的同内容文件：copy2 保证大小与 mtime 一致，满足
        # 「可复用」条件；但若清理用区分大小写的字符串比较，它会被当成陈旧产物删掉，
        # 而 JSON 里的引用随即悬空。
        shutil.copy2(str(src), str(audio_dir / b_upper))

        expected_key = os.path.normcase(f'father/audio/{b}')
        for round_no in (1, 2):
            result = self.ingest()

            self.assertTrue((audio_dir / b).exists(),
                            f'第 {round_no} 轮：复用的目标文件被删除')
            for deleted in result['deleted']:
                self.assertNotEqual(os.path.normcase(deleted), expected_key,
                                    f'第 {round_no} 轮：复用文件被当作陈旧产物删除: {deleted}')

            payload = self._load_payload('father')
            turn = self._turn(self._session(payload, sid), 'simulacrum')
            self.assertIn('audio', turn, f'第 {round_no} 轮：回合丢失了音频引用')
            refs = [item['file'] for item in turn['audio']]
            self.assertIn(f'audio/{b}', refs)
            for ref in refs:
                self.assertTrue((self.out_dir / 'father' / ref).is_file(),
                                f'第 {round_no} 轮：引用在磁盘上不存在: {ref}')

    def test_case_variant_sids_do_not_share_one_target(self):
        sid_lower = self.SID
        sid_upper = self.SID.upper()
        b_lower = _wav_name(sid_lower, 1)
        b_upper = _wav_name(sid_upper, 1)
        self.assertNotEqual(b_lower, b_upper)

        # Windows 不区分大小写：两个会话的日志与音频源必须放在不同的月份子目录，
        # 否则会互相覆盖，根本测不到「目标 basename 冲突」。
        dir_lower = self.sessions_dir / '2026-09'
        dir_upper = self.sessions_dir / '2026-10'
        audio_lower = dir_lower / 'audio'
        audio_upper = dir_upper / 'audio'
        audio_lower.mkdir(parents=True, exist_ok=True)
        audio_upper.mkdir(parents=True, exist_ok=True)
        (audio_lower / b_lower).write_bytes(b'RIFF-S1' + AUDIO_BYTES)
        (audio_upper / b_upper).write_bytes(b'RIFF-S2' + AUDIO_BYTES_ALT)

        _write_session(dir_lower, sid_lower, [
            _base_record(sid_lower, 1, 'user', '爸爸你好', TS_USER, viewer='father'),
            _base_record(sid_lower, 1, 'simulacrum', '爸爸回复', TS_SIM,
                         viewer='father'),
            _audio_record(sid_lower, 1, '爸爸回复',
                          f'2026-09/audio/{b_lower}', TS_AUD1,
                          viewer='father', duration_s=1.5),
        ])
        _write_session(dir_upper, sid_upper, [
            _base_record(sid_upper, 1, 'user', '爸爸你好', TS_USER, viewer='father'),
            _base_record(sid_upper, 1, 'simulacrum', '爸爸回复', TS_SIM,
                         viewer='father'),
            _audio_record(sid_upper, 1, '爸爸回复',
                          f'2026-10/audio/{b_upper}', TS_AUD2,
                          viewer='father', duration_s=2.25),
        ])

        result = self.ingest()

        payload = self._load_payload('father')
        for sid in (sid_lower, sid_upper):
            turn = self._turn(self._session(payload, sid), 'simulacrum')
            self.assertNotIn('audio', turn,
                             f'{sid} 的音频必须整组拒绝，绝不附进回合')
        self.assertEqual(result['audio']['rejected'], 2)

        audio_dir = self.out_dir / 'father' / 'audio'
        wanted = os.path.normcase(b_lower)
        collisions = []
        if audio_dir.exists():
            collisions = [p.name for p in audio_dir.iterdir()
                          if os.path.normcase(p.name) == wanted]
        self.assertEqual(collisions, [],
                         f'两个会话不得共用同一个目标文件: {collisions}')


# ======================================== 大小写 viewer 目录与同名文件文本冲突


class TestNormcaseViewerAndDuplicateTextConflict(AudioIngestCase):
    """Windows 大写 viewer 目录的陈旧清理，以及同文件不同文本引用的整体拒绝。"""

    def test_uppercase_viewer_audio_is_deleted_on_rerun(self):
        if os.name != 'nt':
            self.skipTest('只有大小写不敏感的文件系统（Windows）需要该保证')

        sid = self.SID
        b = _wav_name(sid, 1)
        self._put_audio_source(b, AUDIO_BYTES)

        # 第一次运行之前就存在的大写 viewer 目录
        upper_audio = self.out_dir / 'FATHER' / 'audio'
        upper_audio.mkdir(parents=True, exist_ok=True)

        self._write_father_session_with_audio(sid, b)

        result1 = self.ingest()
        self.assertEqual(result1['audio']['copied'], 1)
        lower_target = self.out_dir / 'father' / 'audio' / b
        self.assertTrue(lower_target.is_file(), '音频应复制到 father/audio/')
        self.assertTrue((upper_audio / b).exists(),
                        '大写写法的 viewer 目录里也应看到同一文件')

        _append_session(self.sessions_dir, sid, [
            _base_record(sid, 1, 'event', ingest_sessions.EXCLUDE_EVENT_TEXT,
                         '2026-09-10T10:00:09+08:00', viewer='father'),
        ])
        result2 = self.ingest()

        self.assertFalse(lower_target.exists(), '被排除会话的音频应被删除')
        self.assertFalse((self.out_dir / 'FATHER' / 'audio' / b).exists(),
                         '大写 viewer 目录里的同一文件也应不存在')

        expected_tail = os.path.normcase('audio/' + b)
        deleted_keys = [os.path.normcase(p) for p in result2['deleted']]
        self.assertTrue(
            any(key.endswith(expected_tail) for key in deleted_keys),
            f"deleted 中应有一条以 {expected_tail!r} 结尾: {result2['deleted']!r}")

    def test_duplicate_refs_same_file_conflict_by_text(self):
        sid = self.SID
        b = _wav_name(sid, 1)

        # ---- 情形 a：同一文件、文本不同 → 全部引用被整体拒绝
        self._put_audio_source(b, AUDIO_BYTES)
        _write_session(self.sessions_dir, sid, [
            _base_record(sid, 1, 'user', '爸爸你好', TS_USER, viewer='father'),
            _base_record(sid, 1, 'simulacrum', '第一段。第二段。', TS_SIM,
                         viewer='father'),
            _audio_record(sid, 1, '第一段。', self._rel_audio(b), TS_AUD1,
                          viewer='father', duration_s=1.5),
            _audio_record(sid, 1, '第二段。', self._rel_audio(b), TS_AUD2,
                          viewer='father', duration_s=1.5),
        ])
        result = self.ingest()

        payload = self._load_payload('father')
        turn = self._turn(self._session(payload, sid), 'simulacrum')
        self.assertNotIn('audio', turn, '文本冲突的同文件引用应被整体移除')
        self.assertEqual(result['audio']['rejected'], 2)
        self.assertEqual(self._audio_dir_files('father'), [])
        self.assertFalse((self.out_dir / 'father' / 'audio' / b).exists(),
                         '冲突文件不应被复制到 out_dir')

        # ---- 情形 b：另起一个临时目录，同一文件、文本相同 → 照常附加
        with tempfile.TemporaryDirectory() as tmp2:
            person2 = Path(tmp2) / 'people' / 'mama'
            sessions2 = person2 / 'sessions'
            sessions2.mkdir(parents=True, exist_ok=True)
            out2 = person2 / 'archive_out' / 'sessions_data'
            out2.mkdir(parents=True, exist_ok=True)

            src2 = sessions2 / '2026-09' / 'audio'
            src2.mkdir(parents=True, exist_ok=True)
            (src2 / b).write_bytes(AUDIO_BYTES)

            dup_text = '爸爸回复'
            _write_session(sessions2, sid, [
                _base_record(sid, 1, 'user', '爸爸你好', TS_USER, viewer='father'),
                _base_record(sid, 1, 'simulacrum', dup_text, TS_SIM,
                             viewer='father'),
                _audio_record(sid, 1, dup_text, f'2026-09/audio/{b}', TS_AUD1,
                              viewer='father', duration_s=1.5),
                _audio_record(sid, 1, dup_text, f'2026-09/audio/{b}', TS_AUD2,
                              viewer='father', duration_s=1.5),
            ])

            result2 = ingest_sessions.ingest(person2, out2,
                                             per_viewer_subdir=True)

            payload2_path = out2 / 'father' / 'sessions.json'
            self.assertTrue(payload2_path.is_file(), f'缺少产物 {payload2_path}')
            with open(payload2_path, encoding='utf-8') as f:
                payload2 = json.load(f)

            session2 = next((s for s in payload2.get('sessions', [])
                             if s.get('session_id') == sid), None)
            self.assertIsNotNone(session2, f'会话 {sid} 不在产物中')
            turn2 = next((t for t in session2.get('turns', [])
                          if t.get('role') == 'simulacrum'), None)
            self.assertIsNotNone(turn2, 'simulacrum 回合不存在')

            self.assertIn('audio', turn2, '文本相同的重复引用不应算冲突')
            self.assertTrue(turn2['audio'])
            for item in turn2['audio']:
                self.assertEqual(item['file'], f'audio/{b}')
                self.assertEqual(item['text'], dup_text)
            self.assertTrue((out2 / 'father' / 'audio' / b).is_file(),
                            '内容相同的重复引用应正常复制文件')
            self.assertEqual(result2['audio']['rejected'], 0)


# ================================ basename 同名不同源 + 部分大小写陈旧清理


class TestBasenameCollisionAndCaseVariantCleanup(AudioIngestCase):
    """同名不同源整组拒绝；Windows 大小写变体目标在排除后必须被清理。"""

    def test_same_basename_in_two_month_dirs_is_rejected_as_group(self):
        sid = self.SID
        b = _wav_name(sid, 1)
        sep_src = self._put_audio_source(b, b'RIFF-SEPT' + AUDIO_BYTES)
        oct_dir = self.sessions_dir / '2026-10' / 'audio'
        oct_dir.mkdir(parents=True, exist_ok=True)
        oct_src = oct_dir / b
        oct_src.write_bytes(b'RIFF-OCT' + AUDIO_BYTES_ALT)
        self.assertNotEqual(sep_src.read_bytes(), oct_src.read_bytes(),
                            '两个源文件内容必须不同')

        _write_session(self.sessions_dir / '2026-09', sid, [
            _base_record(sid, 1, 'user', '爸爸你好', TS_USER, viewer='father'),
            _base_record(sid, 1, 'simulacrum', '一句话。', TS_SIM, viewer='father'),
            _audio_record(sid, 1, '一句话。', f'2026-09/audio/{b}', TS_AUD1,
                          viewer='father', duration_s=1.5),
            _audio_record(sid, 1, '一句话。', f'2026-10/audio/{b}', TS_AUD2,
                          viewer='father', duration_s=2.5),
        ])
        result = self.ingest()

        payload = self._load_payload('father')
        turn = self._turn(self._session(payload, sid), 'simulacrum')
        self.assertNotIn('audio', turn, '同名不同源的引用必须整组拒绝')
        self.assertEqual(result['audio']['rejected'], 2)

        audio_dir = self.out_dir / 'father' / 'audio'
        wanted = os.path.normcase(b)
        collisions = []
        if audio_dir.exists():
            collisions = [p.name for p in audio_dir.iterdir()
                          if os.path.normcase(p.name) == wanted]
        self.assertEqual(collisions, [],
                         f'同名源冲突时不应产生任何目标文件: {collisions}')

    def test_partially_uppercase_preexisting_target_is_cleaned_on_exclusion(self):
        if os.name != 'nt':
            self.skipTest('只有大小写不敏感的文件系统（Windows）需要该保证')

        import shutil

        sid = self.SID
        base_name = f'session_{sid}_t001.wav'
        variants = [
            f'SESSION_{sid}_t001.wav',
            f'session_{sid}_T001.wav',
            f'session_{sid}_t001.WAV',
        ]
        expected_tail = os.path.normcase('audio/' + base_name)

        for index, variant in enumerate(variants):
            with self.subTest(variant=variant):
                root = self.tmp_path / f'case_{index}'
                person_dir = root / 'people' / 'mama'
                sessions_dir = person_dir / 'sessions'
                out_dir = person_dir / 'archive_out' / 'sessions_data'
                sessions_dir.mkdir(parents=True, exist_ok=True)
                out_dir.mkdir(parents=True, exist_ok=True)

                src_dir = sessions_dir / '2026-09' / 'audio'
                src_dir.mkdir(parents=True, exist_ok=True)
                src = src_dir / base_name
                src.write_bytes(AUDIO_BYTES)

                _write_session(sessions_dir, sid, [
                    _base_record(sid, 1, 'user', '爸爸你好', TS_USER,
                                 viewer='father'),
                    _base_record(sid, 1, 'simulacrum', '爸爸回复', TS_SIM,
                                 viewer='father'),
                    _audio_record(sid, 1, '爸爸回复',
                                  f'2026-09/audio/{base_name}', TS_AUD1,
                                  viewer='father', duration_s=1.5),
                ])

                audio_dir = out_dir / 'father' / 'audio'
                audio_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(src), str(audio_dir / variant))

                ingest_sessions.ingest(person_dir, out_dir,
                                       per_viewer_subdir=True)
                self.assertTrue((audio_dir / base_name).exists(),
                                '大小写不敏感的文件系统上应看到预先放置的目标文件')

                _append_session(sessions_dir, sid, [
                    _base_record(sid, 1, 'event',
                                 ingest_sessions.EXCLUDE_EVENT_TEXT,
                                 '2026-09-10T10:00:09+08:00', viewer='father'),
                ])
                result2 = ingest_sessions.ingest(person_dir, out_dir,
                                                 per_viewer_subdir=True)

                wanted = os.path.normcase(base_name)
                leftovers = [p.name for p in audio_dir.iterdir()
                             if p.is_file()
                             and os.path.normcase(p.name) == wanted]
                self.assertEqual(leftovers, [],
                                 f'排除后残留的大小写变体文件: {leftovers}')

                deleted_keys = [os.path.normcase(p) for p in result2['deleted']]
                self.assertTrue(
                    any(key.endswith(expected_tail) for key in deleted_keys),
                    f"deleted 中应有一条以 {expected_tail!r} 结尾: "
                    f"{result2['deleted']!r}")


if __name__ == '__main__':
    unittest.main()
