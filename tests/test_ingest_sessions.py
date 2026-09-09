import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import ingest_sessions

import unittest
import tempfile
import json
import shutil
from pathlib import Path
from unittest import mock
import io
import contextlib


def _write_session(sessions_dir, session_id, records):
    """把 records（dict 列表）逐行写入 <sessions_dir>/session_<id>.jsonl。"""
    path = Path(sessions_dir) / f'session_{session_id}.jsonl'
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
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


def _sessions_dir_for(tmp, slug='mama'):
    """造 people/<slug>/sessions 目录并返回 Path。"""
    d = tmp / 'people' / slug / 'sessions'
    d.mkdir(parents=True, exist_ok=True)
    return d


class TestIngestSessionsEmpty(unittest.TestCase):
    """空目录与原子写相关用例。"""

    def test_empty_dir_writes_owner_stub(self):
        """sessions 目录不存在时写出空的 owner 桩文件。"""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            person_dir = tmp / 'people' / 'mama'
            out_dir = person_dir / 'archive_out' / 'data'
            result = ingest_sessions.ingest(person_dir, out_dir)
            self.assertIn('sessions_owner.json', result['written'])
            out_file = out_dir / 'sessions_owner.json'
            with open(out_file, encoding='utf-8') as f:
                payload = json.load(f)
            self.assertIsNone(payload['last_card'])
            self.assertEqual(payload['sessions'], [])
            self.assertEqual(payload['viewer'], 'owner')
            self.assertEqual(payload['schema_version'], 1)

    def test_atomic_write_keeps_old_on_failure(self):
        """os.replace 失败时旧文件内容保持不变。"""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            sessions_dir = _sessions_dir_for(tmp)
            (tmp / 'people' / 'mama').mkdir(parents=True, exist_ok=True)
            sid = '20260904-214553-7pZokX'
            _write_session(sessions_dir, sid, [
                _base_record(sid, 1, 'user', '旧内容', '2026-09-04T21:45:59+08:00'),
                _base_record(sid, 1, 'simulacrum', '回', '2026-09-04T21:46:00+08:00'),
            ])
            person_dir = tmp / 'people' / 'mama'
            out_dir = person_dir / 'archive_out' / 'data'
            ingest_sessions.ingest(person_dir, out_dir)
            out_file = out_dir / 'sessions_owner.json'
            with open(out_file, encoding='utf-8') as f:
                old_content = f.read()
            # 改变数据
            _write_session(sessions_dir, sid, [
                _base_record(sid, 1, 'user', '新内容', '2026-09-04T21:45:59+08:00'),
                _base_record(sid, 1, 'simulacrum', '回', '2026-09-04T21:46:00+08:00'),
            ])
            with mock.patch('os.replace', side_effect=OSError('boom')):
                with self.assertRaises(OSError):
                    ingest_sessions.ingest(person_dir, out_dir)
            with open(out_file, encoding='utf-8') as f:
                new_content = f.read()
            self.assertEqual(new_content, old_content)


class TestIngestSessionsExclusion(unittest.TestCase):
    """排除规则相关用例。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tmp_path = Path(self.tmp.name)
        self.person_dir = self.tmp_path / 'people' / 'mama'
        self.sessions_dir = _sessions_dir_for(self.tmp_path)
        self.out_dir = self.person_dir / 'archive_out' / 'data'

    def _ingest(self):
        return ingest_sessions.ingest(self.person_dir, self.out_dir)

    def test_exclude_by_flag(self):
        """会话含 exclude=true 记录时被排除。"""
        ok_sid = '20260904-100000-aaaaaa'
        bad_sid = '20260904-110000-bbbbbb'
        _write_session(self.sessions_dir, ok_sid, [
            _base_record(ok_sid, 1, 'user', '正常', '2026-09-04T10:00:00+08:00'),
            _base_record(ok_sid, 1, 'simulacrum', '正常回复', '2026-09-04T10:00:01+08:00'),
        ])
        _write_session(self.sessions_dir, bad_sid, [
            _base_record(bad_sid, 1, 'user', '秘密', '2026-09-04T11:00:00+08:00', exclude=True),
        ])
        result = self._ingest()
        with open(self.out_dir / 'sessions_owner.json', encoding='utf-8') as f:
            payload = json.load(f)
        sids = [s['session_id'] for s in payload['sessions']]
        self.assertIn(ok_sid, sids)
        self.assertNotIn(bad_sid, sids)
        self.assertEqual(payload['source_stats']['excluded_sessions'], 1)

    def test_exclude_by_event(self):
        """含 exclude_session 事件记录的会话被排除。"""
        ok_sid = '20260904-100000-aaaaaa'
        bad_sid = '20260904-110000-bbbbbb'
        _write_session(self.sessions_dir, ok_sid, [
            _base_record(ok_sid, 1, 'user', '正常', '2026-09-04T10:00:00+08:00'),
            _base_record(ok_sid, 1, 'simulacrum', '回复', '2026-09-04T10:00:01+08:00'),
        ])
        _write_session(self.sessions_dir, bad_sid, [
            _base_record(bad_sid, 1, 'event', 'exclude_session', '2026-09-04T11:00:00+08:00'),
        ])
        self._ingest()
        with open(self.out_dir / 'sessions_owner.json', encoding='utf-8') as f:
            payload = json.load(f)
        sids = [s['session_id'] for s in payload['sessions']]
        self.assertIn(ok_sid, sids)
        self.assertNotIn(bad_sid, sids)
        self.assertEqual(payload['source_stats']['excluded_sessions'], 1)

    def test_exclude_by_file(self):
        """exclude.txt 中列出的会话被排除。"""
        # 先造 exclude.txt，含注释和空行
        excl_dir = self.person_dir / 'sessions'
        # 已由 _sessions_dir_for 创建
        excl_lines = ['# 注释', '', '20260904-110000-bbbbbb', '', '   ']
        # 注意：测试约定存放在 sessions 目录下
        # 但默认 exclude-file 是 people/<slug>/sessions/exclude.txt
        # 所以直接写在这里
        with open(self.person_dir / 'sessions' / 'exclude.txt', 'w', encoding='utf-8') as f:
            f.write('\n'.join(excl_lines) + '\n')
        ok_sid = '20260904-100000-aaaaaa'
        bad_sid = '20260904-110000-bbbbbb'
        _write_session(self.sessions_dir, ok_sid, [
            _base_record(ok_sid, 1, 'user', '正常', '2026-09-04T10:00:00+08:00'),
            _base_record(ok_sid, 1, 'simulacrum', '回复', '2026-09-04T10:00:01+08:00'),
        ])
        _write_session(self.sessions_dir, bad_sid, [
            _base_record(bad_sid, 1, 'user', '被文件排除', '2026-09-04T11:00:00+08:00'),
        ])
        self._ingest()
        with open(self.out_dir / 'sessions_owner.json', encoding='utf-8') as f:
            payload = json.load(f)
        sids = [s['session_id'] for s in payload['sessions']]
        self.assertIn(ok_sid, sids)
        self.assertNotIn(bad_sid, sids)


class TestIngestSessionsProcessing(unittest.TestCase):
    """处理规则（去重、过滤、脱敏、卡片）。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tmp_path = Path(self.tmp.name)
        self.person_dir = self.tmp_path / 'people' / 'mama'
        self.sessions_dir = _sessions_dir_for(self.tmp_path)
        self.out_dir = self.person_dir / 'archive_out' / 'data'

    def _ingest(self):
        return ingest_sessions.ingest(self.person_dir, self.out_dir)

    def test_dedupe_first_wins(self):
        """同 (session_id, turn, role) 只保留第一条。"""
        sid = '20260904-100000-aaaaaa'
        _write_session(self.sessions_dir, sid, [
            _base_record(sid, 1, 'user', 'first', '2026-09-04T10:00:00+08:00'),
            _base_record(sid, 1, 'user', 'second', '2026-09-04T10:00:01+08:00'),
            _base_record(sid, 1, 'simulacrum', '回复', '2026-09-04T10:00:02+08:00'),
        ])
        self._ingest()
        with open(self.out_dir / 'sessions_owner.json', encoding='utf-8') as f:
            payload = json.load(f)
        self.assertEqual(len(payload['sessions']), 1)
        turns = payload['sessions'][0]['turns']
        user_turns = [t for t in turns if t['role'] == 'user']
        self.assertEqual(len(user_turns), 1)
        self.assertEqual(user_turns[0]['text'], 'first')

    def test_roles_filtered(self):
        """simulacrum_audio、event、空文本的 user 不进 turns。"""
        sid = '20260904-100000-aaaaaa'
        _write_session(self.sessions_dir, sid, [
            _base_record(sid, 1, 'user', '正常', '2026-09-04T10:00:00+08:00'),
            _base_record(sid, 1, 'simulacrum', '正常回复', '2026-09-04T10:00:01+08:00'),
            _base_record(sid, 2, 'user', '', '2026-09-04T10:00:02+08:00'),
            _base_record(sid, 2, 'simulacrum_audio', '音频', '2026-09-04T10:00:03+08:00'),
            _base_record(sid, 2, 'event', 'some_event', '2026-09-04T10:00:04+08:00'),
        ])
        self._ingest()
        with open(self.out_dir / 'sessions_owner.json', encoding='utf-8') as f:
            payload = json.load(f)
        turns = payload['sessions'][0]['turns']
        self.assertEqual(len(turns), 2)
        roles = {t['role'] for t in turns}
        self.assertEqual(roles, {'user', 'simulacrum'})

    def test_sensitive_redaction(self):
        """high/medium 模式命中被脱敏，low 不处理。"""
        # 用仓库根推导 tools/sensitive_patterns.json
        repo_root = Path(__file__).resolve().parent.parent
        patterns_path = repo_root / 'tools' / 'sensitive_patterns.json'
        # 如果文件不存在则跳过（但测试假定存在）
        if not patterns_path.exists():
            self.skipTest('sensitive_patterns.json 不存在')
        # 临时造一个包含 low 模式工资 的配置文件？直接使用真实文件，假定有对应模式
        # 构造三条记录，一条含密码，一条含验证码，一条含工资
        sid = '20260904-100000-aaaaaa'
        _write_session(self.sessions_dir, sid, [
            _base_record(sid, 1, 'user', '我的密码123是', '2026-09-04T10:00:00+08:00'),
            _base_record(sid, 2, 'user', '验证码是多少', '2026-09-04T10:00:01+08:00'),
            _base_record(sid, 3, 'user', '这个月工资', '2026-09-04T10:00:02+08:00'),
            _base_record(sid, 1, 'simulacrum', '回复', '2026-09-04T10:00:03+08:00'),
        ])
        ingest_sessions.ingest(self.person_dir, self.out_dir, patterns_path=patterns_path)
        with open(self.out_dir / 'sessions_owner.json', encoding='utf-8') as f:
            payload = json.load(f)
        self.assertEqual(payload['source_stats']['redacted_turns'], 2)
        turns = payload['sessions'][0]['turns']
        user_turns = [t for t in turns if t['role'] == 'user']
        # 第1、2条被脱敏，第3条保留
        texts = [t['text'] for t in user_turns]
        self.assertIn(ingest_sessions.REDACTED_TEXT, texts)
        self.assertIn('这个月工资', texts)
        # last_card 不应包含脱敏文本
        if payload['last_card'] is not None:
            for line in payload['last_card'].get('user_lines', []):
                self.assertNotEqual(line, ingest_sessions.REDACTED_TEXT)

    def test_card_truncation(self):
        """user_lines 超过 12 条时取首4+末8 并截断到 121 字。"""
        sid = '20260904-100000-aaaaaa'
        records = []
        for i in range(1, 16):
            text = f'{i:02d}' + '啊' * 128
            records.append(_base_record(sid, i, 'user', text, f'2026-09-04T10:{i:02d}:00+08:00'))
        # 最后加一条 simulacrum
        records.append(_base_record(sid, 16, 'simulacrum', '回复', '2026-09-04T10:16:00+08:00'))
        _write_session(self.sessions_dir, sid, records)
        self._ingest()
        with open(self.out_dir / 'sessions_owner.json', encoding='utf-8') as f:
            payload = json.load(f)
        self.assertIsNotNone(payload['last_card'])
        lines = payload['last_card']['user_lines']
        self.assertEqual(len(lines), 12)
        self.assertTrue(payload['last_card']['user_lines_truncated'])
        # 前4条对应 01 02 03 04
        self.assertTrue(lines[0].startswith('01'))
        self.assertTrue(lines[3].startswith('04'))
        # 后8条对应 08..15
        self.assertTrue(lines[4].startswith('08'))
        self.assertTrue(lines[11].startswith('15'))
        for line in lines:
            self.assertLessEqual(len(line), 121)
            self.assertTrue(line.endswith('…'))

    def test_card_requires_both_roles(self):
        """只有 user 的会话不成卡但仍在 sessions。"""
        sid = '20260904-100000-aaaaaa'
        _write_session(self.sessions_dir, sid, [
            _base_record(sid, 1, 'user', '只有我', '2026-09-04T10:00:00+08:00'),
            _base_record(sid, 2, 'user', '还是我', '2026-09-04T10:00:01+08:00'),
        ])
        self._ingest()
        with open(self.out_dir / 'sessions_owner.json', encoding='utf-8') as f:
            payload = json.load(f)
        self.assertIsNone(payload['last_card'])
        sids = [s['session_id'] for s in payload['sessions']]
        self.assertIn(sid, sids)

    def test_last_exchange(self):
        """取最后 user 与其后最后 simulacrum，超长截断。"""
        sid = '20260904-100000-aaaaaa'
        _write_session(self.sessions_dir, sid, [
            _base_record(sid, 1, 'user', '第一个问题', '2026-09-04T10:00:00+08:00'),
            _base_record(sid, 1, 'simulacrum', '第一个回答', '2026-09-04T10:00:01+08:00'),
            _base_record(sid, 2, 'user', '第二个问题', '2026-09-04T10:00:02+08:00'),
            _base_record(sid, 2, 'simulacrum', '长' * 300, '2026-09-04T10:00:03+08:00'),
        ])
        self._ingest()
        with open(self.out_dir / 'sessions_owner.json', encoding='utf-8') as f:
            payload = json.load(f)
        lc = payload['last_card']
        self.assertEqual(lc['last_exchange']['user'], '第二个问题')
        self.assertEqual(len(lc['last_exchange']['simulacrum']), 201)  # 200 + …
        self.assertTrue(lc['last_exchange']['simulacrum'].endswith('…'))

    def test_recent_dates(self):
        """recent_dates 为除 last_card 外最近 5 个日期降序无重复。"""
        dates = ['2026-09-01', '2026-09-02', '2026-09-03', '2026-09-04',
                 '2026-09-05', '2026-09-06', '2026-09-07']
        for i, d in enumerate(dates):
            sid = f'2026{ d[5:7] }{ d[8:10] }-{1000+i:04d}-aaaaaa'
            # 造符合格式的 id：YYYMMDD-HHMMSS-xxxxxx
            # 直接用 d 拼
            sid = d.replace('-', '') + f'-{1000+i:04d}-abcdef'
            _write_session(self.sessions_dir, sid, [
                _base_record(sid, 1, 'user', f'问题{i}', f'{d}T10:00:00+08:00'),
                _base_record(sid, 1, 'simulacrum', '回复', f'{d}T10:00:01+08:00'),
            ])
        self._ingest()
        with open(self.out_dir / 'sessions_owner.json', encoding='utf-8') as f:
            payload = json.load(f)
        lc_date = payload['last_card']['date']
        self.assertEqual(lc_date, '2026-09-07')
        rd = payload['recent_dates']
        self.assertEqual(len(rd), 5)
        self.assertEqual(rd, sorted(rd, reverse=True))
        self.assertNotIn(lc_date, rd)

    def test_date_fallback(self):
        """ts 缺失用 server_ts，再缺用文件名里的日期。"""
        # 会话 P：有 server_ts
        p_sid = '20260904-100000-aaaaaa'
        _write_session(self.sessions_dir, p_sid, [
            _base_record(p_sid, 1, 'user', '问题', None, server_ts='2026-09-03T10:00:00+08:00'),
            _base_record(p_sid, 1, 'simulacrum', '回复', None, server_ts='2026-09-03T10:00:01+08:00'),
        ])
        # 会话 Q：无 ts 无 server_ts
        q_sid = '20260901-120000-abcdef'
        _write_session(self.sessions_dir, q_sid, [
            _base_record(q_sid, 1, 'user', '问题2'),
            _base_record(q_sid, 1, 'simulacrum', '回复2'),
        ])
        self._ingest()
        with open(self.out_dir / 'sessions_owner.json', encoding='utf-8') as f:
            payload = json.load(f)
        for s in payload['sessions']:
            if s['session_id'] == p_sid:
                self.assertEqual(s['date'], '2026-09-03')
            elif s['session_id'] == q_sid:
                self.assertEqual(s['date'], '2026-09-01')

    def test_deterministic(self):
        """同样输入产生同样输出（除 generated_at）。"""
        sid = '20260904-100000-aaaaaa'
        _write_session(self.sessions_dir, sid, [
            _base_record(sid, 1, 'user', '问题', '2026-09-04T10:00:00+08:00'),
            _base_record(sid, 1, 'simulacrum', '回复', '2026-09-04T10:00:01+08:00'),
        ])
        payloads, _ = ingest_sessions.build_sessions(self.person_dir)
        payloads2, _ = ingest_sessions.build_sessions(self.person_dir)
        for viewer in payloads:
            p1 = dict(payloads[viewer])
            p2 = dict(payloads2[viewer])
            p1.pop('generated_at', None)
            p2.pop('generated_at', None)
            self.assertEqual(
                json.dumps(p1, sort_keys=True, ensure_ascii=False),
                json.dumps(p2, sort_keys=True, ensure_ascii=False)
            )


class TestIngestSessionsViewerAndFiles(unittest.TestCase):
    """viewer 分桶与文件清理。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tmp_path = Path(self.tmp.name)
        self.person_dir = self.tmp_path / 'people' / 'mama'
        self.sessions_dir = _sessions_dir_for(self.tmp_path)
        self.out_dir = self.person_dir / 'archive_out' / 'data'

    def test_viewer_partition(self):
        """不同 viewer 的内容互不泄漏。"""
        dad_sid = '20260904-100000-aaaaaa'
        owner_sid = '20260904-110000-bbbbbb'
        _write_session(self.sessions_dir, dad_sid, [
            _base_record(dad_sid, 1, 'user', 'DADONLY', '2026-09-04T10:00:00+08:00', viewer='dad'),
            _base_record(dad_sid, 1, 'simulacrum', 'DAD回复', '2026-09-04T10:00:01+08:00', viewer='dad'),
        ])
        _write_session(self.sessions_dir, owner_sid, [
            _base_record(owner_sid, 1, 'user', 'OWNERONLY', '2026-09-04T11:00:00+08:00'),
            _base_record(owner_sid, 1, 'simulacrum', 'OWNER回复', '2026-09-04T11:00:01+08:00'),
        ])
        ingest_sessions.ingest(self.person_dir, self.out_dir)
        with open(self.out_dir / 'sessions_owner.json', encoding='utf-8') as f:
            owner_payload = json.load(f)
        with open(self.out_dir / 'sessions_dad.json', encoding='utf-8') as f:
            dad_payload = json.load(f)
        self.assertEqual(owner_payload['viewer'], 'owner')
        self.assertEqual(dad_payload['viewer'], 'dad')
        self.assertNotIn('DADONLY', json.dumps(owner_payload, ensure_ascii=False))
        self.assertNotIn('OWNERONLY', json.dumps(dad_payload, ensure_ascii=False))

    def test_invalid_viewer_to_owner(self):
        """非法 viewer 归入 owner。"""
        sid = '20260904-100000-aaaaaa'
        _write_session(self.sessions_dir, sid, [
            _base_record(sid, 1, 'user', '内容', '2026-09-04T10:00:00+08:00', viewer='Dad!'),
            _base_record(sid, 1, 'simulacrum', '回复', '2026-09-04T10:00:01+08:00', viewer='Dad!'),
        ])
        ingest_sessions.ingest(self.person_dir, self.out_dir)
        self.assertTrue((self.out_dir / 'sessions_owner.json').exists())
        self.assertFalse((self.out_dir / 'sessions_Dad!.json').exists())
        with open(self.out_dir / 'sessions_owner.json', encoding='utf-8') as f:
            payload = json.load(f)
        self.assertEqual(payload['viewer'], 'owner')

    def test_stale_file_deleted(self):
        """过期 sessions_*.json 被删除，其它文件保留。"""
        # 构造数据
        sid = '20260904-100000-aaaaaa'
        _write_session(self.sessions_dir, sid, [
            _base_record(sid, 1, 'user', '内容', '2026-09-04T10:00:00+08:00'),
            _base_record(sid, 1, 'simulacrum', '回复', '2026-09-04T10:00:01+08:00'),
        ])
        self.out_dir.mkdir(parents=True, exist_ok=True)
        (self.out_dir / 'sessions_ghost.json').write_text('{}', encoding='utf-8')
        (self.out_dir / 'other.json').write_text('{}', encoding='utf-8')
        result = ingest_sessions.ingest(self.person_dir, self.out_dir)
        self.assertIn('sessions_ghost.json', result['deleted'])
        self.assertFalse((self.out_dir / 'sessions_ghost.json').exists())
        self.assertTrue((self.out_dir / 'other.json').exists())

    def test_bad_line_counted(self):
        """坏行计入 bad_lines 且不影响其它行。"""
        sid = '20260904-100000-aaaaaa'
        path = _write_session(self.sessions_dir, sid, [
            _base_record(sid, 1, 'user', '第一行', '2026-09-04T10:00:00+08:00'),
            _base_record(sid, 3, 'user', '占位（下方会整体重写本文件）', '2026-09-04T10:00:03+08:00'),
            _base_record(sid, 2, 'user', '第二行', '2026-09-04T10:00:01+08:00'),
            _base_record(sid, 1, 'simulacrum', '回复', '2026-09-04T10:00:02+08:00'),
        ])
        # 手动插入坏行（上面 json.dumps 会把 dict 写成合法 JSON）
        # 用文本方式重写
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(json.dumps(_base_record(sid, 1, 'user', '第一行', '2026-09-04T10:00:00+08:00'), ensure_ascii=False) + '\n')
            f.write('{not json\n')
            f.write(json.dumps(_base_record(sid, 2, 'user', '第二行', '2026-09-04T10:00:01+08:00'), ensure_ascii=False) + '\n')
            f.write(json.dumps(_base_record(sid, 1, 'simulacrum', '回复', '2026-09-04T10:00:02+08:00'), ensure_ascii=False) + '\n')
        result = ingest_sessions.ingest(self.person_dir, self.out_dir)
        with open(self.out_dir / 'sessions_owner.json', encoding='utf-8') as f:
            payload = json.load(f)
        self.assertEqual(payload['source_stats']['bad_lines'], 1)
        turns = payload['sessions'][0]['turns']
        user_texts = [t['text'] for t in turns if t['role'] == 'user']
        self.assertIn('第一行', user_texts)
        self.assertIn('第二行', user_texts)


class TestIngestSessionsCli(unittest.TestCase):
    """CLI 参数校验相关。"""

    def test_out_dir_escape_rejected(self):
        """--out-dir 指向 people 目录外时 main 返回 2。"""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            person_dir = tmp / 'people' / 'mama'
            sessions_dir = person_dir / 'sessions'
            sessions_dir.mkdir(parents=True)
            outside = tmp / 'outside'
            outside.mkdir()
            sid = '20260904-100000-aaaaaa'
            _write_session(sessions_dir, sid, [
                _base_record(sid, 1, 'user', '内容', '2026-09-04T10:00:00+08:00'),
                _base_record(sid, 1, 'simulacrum', '回复', '2026-09-04T10:00:01+08:00'),
            ])
            # 打补丁到 PEOPLE_DIR
            with mock.patch.object(ingest_sessions, 'PEOPLE_DIR', tmp / 'people'):
                rc = ingest_sessions.main(['--person', 'mama', '--out-dir', str(outside)])
            self.assertEqual(rc, 2)


class TestIngestSessionsHardening(unittest.TestCase):
    """新增加固用例：脱敏字面量、大小写不敏感、路径校验、时间戳、dry-run 统计。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tmp_path = Path(self.tmp.name)
        self.person_dir = self.tmp_path / 'people' / 'mama'
        self.sessions_dir = _sessions_dir_for(self.tmp_path)
        self.out_dir = self.person_dir / 'archive_out' / 'data'

    def _ingest(self):
        return ingest_sessions.ingest(self.person_dir, self.out_dir)

    def test_redacted_text_literal(self):
        """REDACTED_TEXT 恰好等于硬编码字面量。"""
        self.assertEqual(ingest_sessions.REDACTED_TEXT, '〔含敏感信息，已省略〕')
        sid = '20260904-100000-aaaaaa'
        _write_session(self.sessions_dir, sid, [
            _base_record(sid, 1, 'user', '密码123', '2026-09-04T10:00:00+08:00'),
            _base_record(sid, 1, 'simulacrum', '回复', '2026-09-04T10:00:01+08:00'),
        ])
        repo_root = Path(__file__).resolve().parent.parent
        patterns_path = repo_root / 'tools' / 'sensitive_patterns.json'
        self._ingest() if not patterns_path.exists() else ingest_sessions.ingest(
            self.person_dir, self.out_dir, patterns_path=patterns_path)
        with open(self.out_dir / 'sessions_owner.json', encoding='utf-8') as f:
            payload = json.load(f)
        self.assertEqual(payload['sessions'][0]['turns'][0]['text'], '〔含敏感信息，已省略〕')

    def test_redaction_case_insensitive(self):
        """脱敏对大小写不敏感且两个命中都计入 redacted_turns。"""
        sid = '20260904-100000-aaaaaa'
        _write_session(self.sessions_dir, sid, [
            _base_record(sid, 1, 'user', 'wifi PASSWORD is hunter2', '2026-09-04T10:00:00+08:00'),
            _base_record(sid, 2, 'user', 'my PWD is hunter3', '2026-09-04T10:00:01+08:00'),
            _base_record(sid, 1, 'simulacrum', '回复', '2026-09-04T10:00:02+08:00'),
        ])
        repo_root = Path(__file__).resolve().parent.parent
        patterns_path = repo_root / 'tools' / 'sensitive_patterns.json'
        ingest_sessions.ingest(self.person_dir, self.out_dir, patterns_path=patterns_path)
        with open(self.out_dir / 'sessions_owner.json', encoding='utf-8') as f:
            raw = f.read()
        payload = json.loads(raw)
        self.assertEqual(payload['source_stats']['redacted_turns'], 2)
        for s in payload['sessions']:
            for t in s['turns']:
                if t['role'] == 'user':
                    self.assertEqual(t['text'], '〔含敏感信息，已省略〕')
        self.assertNotIn('hunter2', raw)
        self.assertNotIn('hunter3', raw)

    def test_ingest_rejects_raw_out_dir(self):
        """raw 目录不存在时也必须拦截，且不会创建 raw。"""
        raw_out = self.person_dir / 'raw' / 'x'
        with self.assertRaises(ValueError):
            ingest_sessions.ingest(self.person_dir, raw_out)
        self.assertFalse((self.person_dir / 'raw').exists())

    def test_ingest_rejects_outside_person_dir(self):
        """out_dir 在 people 目录外时抛错且不创建该目录。"""
        outside = self.tmp_path / 'outside'
        with self.assertRaises(ValueError):
            ingest_sessions.ingest(self.person_dir, outside)
        self.assertFalse(outside.exists())

    def test_ingest_rejects_parent_traversal(self):
        """out_dir 含 .. 路径穿越时抛错。"""
        evil = self.out_dir / '..' / '..' / '..' / 'evil'
        with self.assertRaises(ValueError):
            ingest_sessions.ingest(self.person_dir, evil)

    def test_last_card_timestamps(self):
        """last_card 的 started_at/ended_at 取首末非空 ts；全空则为 None。"""
        sid = '20260904-214553-aaaaaa'
        _write_session(self.sessions_dir, sid, [
            _base_record(sid, 1, 'user', '问题1', '2026-09-04T21:45:59+08:00'),
            _base_record(sid, 1, 'simulacrum', '回复1', '2026-09-04T21:46:10+08:00'),
            _base_record(sid, 2, 'user', '问题2', '2026-09-04T22:05:00+08:00'),
            _base_record(sid, 2, 'simulacrum', '回复2', '2026-09-04T22:06:26+08:00'),
        ])
        self._ingest()
        with open(self.out_dir / 'sessions_owner.json', encoding='utf-8') as f:
            payload = json.load(f)
        lc = payload['last_card']
        self.assertEqual(lc['started_at'], '2026-09-04T21:45:59+08:00')
        self.assertEqual(lc['ended_at'], '2026-09-04T22:06:26+08:00')

        # 第二个会话：更早日期，无 ts 无 server_ts → started/ended 为 None
        with tempfile.TemporaryDirectory() as td2:
            tmp2 = Path(td2)
            person_dir2 = tmp2 / 'people' / 'baba'
            sessions_dir2 = person_dir2 / 'sessions'
            sessions_dir2.mkdir(parents=True)
            out_dir2 = person_dir2 / 'archive_out' / 'data'
            old_sid = '20260901-120000-bbbbbb'
            _write_session(sessions_dir2, old_sid, [
                _base_record(old_sid, 1, 'user', '老问题'),
                _base_record(old_sid, 1, 'simulacrum', '老回复'),
            ])
            ingest_sessions.ingest(person_dir2, out_dir2)
            with open(out_dir2 / 'sessions_owner.json', encoding='utf-8') as f:
                payload2 = json.load(f)
            lc2 = payload2['last_card']
            self.assertIsNone(lc2['started_at'])
            self.assertIsNone(lc2['ended_at'])

    def test_dry_run_reports_full_stats(self):
        """--dry-run 输出完整 source_stats 且不写文件。"""
        sid_ok = '20260904-100000-aaaaaa'
        sid_bad = '20260904-110000-bbbbbb'
        _write_session(self.sessions_dir, sid_ok, [
            _base_record(sid_ok, 1, 'user', '正常', '2026-09-04T10:00:00+08:00'),
            _base_record(sid_ok, 1, 'simulacrum', '回复', '2026-09-04T10:00:01+08:00'),
        ])
        _write_session(self.sessions_dir, sid_bad, [
            _base_record(sid_bad, 1, 'user', '排除', '2026-09-04T11:00:00+08:00', exclude=True),
        ])
        people_dir = self.tmp_path / 'people'
        out_arg = self.out_dir
        out_arg.mkdir(parents=True, exist_ok=True)
        buf = __import__('io').StringIO()
        with mock.patch.object(ingest_sessions, 'PEOPLE_DIR', people_dir):
            with __import__('contextlib').redirect_stdout(buf):
                rc = ingest_sessions.main([
                    '--person', 'mama', '--dry-run', '--out-dir', str(out_arg)
                ])
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())
        self.assertIn('global', data)
        self.assertIn('viewers', data)
        self.assertIn('owner', data['viewers'])
        stats = data['viewers']['owner']
        for key in ('files', 'records', 'bad_lines', 'excluded_sessions', 'redacted_turns', 'sessions_kept'):
            self.assertIn(key, stats)
        self.assertEqual(stats['excluded_sessions'], 1)
        self.assertFalse((out_arg / 'sessions_owner.json').exists())

    def test_all_excluded_viewer_stats(self):
        """全部会话被排除时 excluded_sessions 正确计数且输出空 owner 桩。"""
        sid = '20260904-100000-aaaaaa'
        _write_session(self.sessions_dir, sid, [
            _base_record(sid, 1, 'user', '内容', '2026-09-04T10:00:00+08:00', exclude=True),
            _base_record(sid, 1, 'simulacrum', '回复', '2026-09-04T10:00:01+08:00', exclude=True),
        ])
        self._ingest()
        out_file = self.out_dir / 'sessions_owner.json'
        self.assertTrue(out_file.exists())
        with open(out_file, encoding='utf-8') as f:
            payload = json.load(f)
        self.assertEqual(payload['source_stats']['excluded_sessions'], 1)
        self.assertEqual(payload['source_stats']['sessions_kept'], 0)
        self.assertEqual(payload['sessions'], [])
        self.assertIsNone(payload['last_card'])

    def test_validate_paths_rejects_raw_side_files(self):
        """exclude_file 与 patterns_path 不允许指向 raw 之内（即使 raw 不存在）。"""
        person_dir = self.person_dir
        out_dir = person_dir / 'archive_out' / 'data'
        self.assertIsNone(ingest_sessions.validate_paths(person_dir, out_dir))
        err = ingest_sessions.validate_paths(
            person_dir, out_dir, exclude_file=person_dir / 'raw' / 'e.txt')
        self.assertIsNotNone(err)
        if isinstance(err, str):
            self.assertNotEqual(err, '')
        err2 = ingest_sessions.validate_paths(
            person_dir, out_dir, patterns_path=person_dir / 'raw' / 'p.json')
        self.assertIsNotNone(err2)
        if isinstance(err2, str):
            self.assertNotEqual(err2, '')

    def test_invalid_severity_treated_as_high(self):
        """非法 severity（大写 High）按 high 处理，不静默降级。"""
        # 在独立临时目录写自定义 patterns，避免放进仓库
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            patterns_path = td_path / 'custom_patterns.json'
            patterns_path.write_text(
                json.dumps({"patterns": [{"name": "pw", "regex": "hunter2", "severity": "High"}]}),
                encoding='utf-8'
            )
            # 用另一个临时 person 目录避免与 setUp 共享状态
            with tempfile.TemporaryDirectory() as td2:
                tmp2 = Path(td2)
                person_dir2 = tmp2 / 'people' / 'mama'
                sessions_dir2 = person_dir2 / 'sessions'
                sessions_dir2.mkdir(parents=True)
                out_dir2 = person_dir2 / 'archive_out' / 'data'
                sid2 = '20260904-120000-cccccc'
                _write_session(sessions_dir2, sid2, [
                    _base_record(sid2, 1, 'user', 'my token is hunter2', '2026-09-04T12:00:00+08:00'),
                    _base_record(sid2, 1, 'simulacrum', '回复', '2026-09-04T12:00:01+08:00'),
                ])
                stderr_buf = io.StringIO()
                with contextlib.redirect_stderr(stderr_buf):
                    ingest_sessions.ingest(
                        person_dir2, out_dir2, patterns_path=patterns_path)
                with open(out_dir2 / 'sessions_owner.json', encoding='utf-8') as f:
                    raw2 = f.read()
                payload2 = json.loads(raw2)
                self.assertEqual(payload2['source_stats']['redacted_turns'], 1)
                turns2 = payload2['sessions'][0]['turns']
                user_turns2 = [t for t in turns2 if t['role'] == 'user']
                self.assertEqual(user_turns2[0]['text'], ingest_sessions.REDACTED_TEXT)
                self.assertNotIn('hunter2', raw2)


if __name__ == '__main__':
    unittest.main()
