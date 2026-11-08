import copy
import json
import subprocess
import sys
import time
import unittest
from unittest import mock

from tests import test_voice_upgrade as fixtures
from tools import benchmark_voice_references as m
from tools.viewpoint_manifest import sha256


def hanging_worker(connection, plan):
    connection.send(('ready', None))
    connection.recv()
    time.sleep(30)


class FakeModel:
    def synthesize(self, *args):
        return [.1]*1600, 16000


class BenchmarkTests(unittest.TestCase):
    setUp = fixtures.PrepareTests.setUp
    save = fixtures.PrepareTests.save
    def plan(self):
        refs = []
        for i in range(2):
            audio = self.root / f'ref{i}.wav'
            text = self.root / f'ref{i}.txt'
            fixtures.wav(audio, offset=i)
            text.write_text('synthetic reference', encoding='utf-8')
            refs.append(dict(id=f'ref{i}', audio=str(audio), audio_sha256=sha256(audio),
                             transcript=str(text), transcript_sha256=sha256(text),
                             basis=dict(kind='existing_reference', authorization='synthetic fixture')))
        model = self.root / 'model'
        model.mkdir(exist_ok=True)
        weights = self.root / 'weights.pt'
        weights.write_bytes(b'synthetic')
        return dict(schema_version=1, model_dir=str(model), checkpoint=str(weights),
                    references=refs, language='mandarin', seeds=[123], pad_ms=200,
                    fade_ms=30, timeout_seconds=10,
                    targets=[dict(id='s1', text='你好'), dict(id='s2', text='今天出去散步好吗'),
                             dict(id='s3', text='我们明天早上一起出去走走然后再回来吃饭吧'),
                             dict(id='s4', text='合成测试'*9)])

    def test_reject_invalid_plan(self):
        plan = self.plan()
        for mutate in [
            lambda p: p['references'][0].update(audio_sha256='0'*64),
            lambda p: p['references'][0].update(transcript_sha256='0'*64),
            lambda p: p['references'][0].update(basis=dict(kind='pending')),
            lambda p: p.pop('seeds'),
            lambda p: p.update(pad_ms=300),
            lambda p: p['references'].__setitem__(1, dict(p['references'][0], id='other')),
        ]:
            bad = copy.deepcopy(plan)
            mutate(bad)
            with self.assertRaises(ValueError):
                m.validate_plan(bad)

    def test_paired_first_takes_and_failures(self):
        plan = self.plan()
        calls, loads = [], []
        class Fake:
            def synthesize(self, text, reference, seed, language):
                calls.append((text, reference['id'], seed, language))
                if reference['id'] == 'ref1':
                    raise RuntimeError('private target must never leak')
                return [0.1]*1600, 16000
        def factory(p):
            loads.append(1)
            return Fake()
        out = self.root / 'experiment'
        m.run(plan, out, factory=factory, postprocess=lambda data, rate: data)
        rows = [json.loads(s) for s in (out / 'results.jsonl').read_text().splitlines()]
        self.assertEqual(len(loads), 1)
        self.assertEqual(len(calls), 8)
        self.assertEqual(sum(r['status'] == 'error' for r in rows), 4)
        self.assertNotIn('private target', (out / 'results.jsonl').read_text())
        self.assertNotIn('ref0', (out / 'listen.html').read_text())
        self.assertEqual(len(json.loads((out / 'asr-jobs.json').read_text())), 4)
        with self.assertRaises(ValueError):
            m.run(plan, out, factory=factory)

    def test_oom_stops_and_retains_denominator(self):
        plan = self.plan()
        class Fake:
            def synthesize(self, *args):
                raise RuntimeError('CUDA out of memory')
        out = self.root / 'oom'
        m.run(plan, out, factory=lambda p: Fake(), postprocess=lambda d, r: d)
        rows = [json.loads(s) for s in (out / 'results.jsonl').read_text().splitlines()]
        self.assertEqual(len(rows), 8)
        self.assertEqual(rows[0]['status'], 'oom')
        self.assertTrue(all(r['status'] == 'not_run' for r in rows[1:]))

    def test_smoke_timeout_and_paired_asr(self):
        plan = self.plan()
        class Fake:
            def synthesize(self, *args):
                raise TimeoutError()
        out = self.root / 'timeout'
        rows = m.run(plan, out, smoke=True, factory=lambda p: Fake())
        self.assertEqual(len(rows), 2)
        self.assertEqual([r['status'] for r in rows], ['timeout', 'not_run'])
        asr = self.root / 'asr.json'
        asr.write_text('[]')
        report = m.analyze(out, asr, self.root / 'analysis')
        self.assertEqual(report['total'], 2)
        self.assertEqual(report['usable_asr'], 0)
        self.assertFalse(report['pairs'][0]['complete_pair'])

    def test_live_postprocess(self):
        try:
            import torch
            import numpy as np
            from tools.tts_server import soften_onsets
        except ImportError:
            self.skipTest('CosyVoice dependencies required')
        data = [.2]*3200
        expected = soften_onsets(np.pad(np.asarray(data, dtype=np.float32), (3200, 3200)), 16000, fade_ms=30)
        self.assertTrue(np.array_equal(expected, np.asarray(m.postprocess_live(data, 16000))))

    def test_analysis_rejects_missing_duplicate_and_changed_evidence(self):
        plan = self.plan()
        experiment = self.root / 'complete'
        m.run(plan, experiment, factory=lambda p: FakeModel(), postprocess=lambda d,r: d)
        results = experiment / 'results.jsonl'
        summary = experiment / 'summary.json'
        jobs = experiment / 'asr-jobs.json'
        originals = {p:p.read_bytes() for p in (results, summary, jobs)}
        rows = [json.loads(s) for s in results.read_text().splitlines()]
        asr = self.root / 'asr.json'
        asr.write_text(json.dumps([dict(id=r['id'], asr_text='合成', cer=.5) for r in rows]))
        for mode in ['one_row', 'duplicate', 'missing_condition', 'summary', 'wav', 'job_text', 'job_wav']:
            with self.subTest(mode=mode):
                for p, data in originals.items():
                    p.write_bytes(data)
                audio = experiment / rows[0]['wav']
                audio_original = audio.read_bytes()
                if mode in ('one_row', 'duplicate', 'missing_condition'):
                    changed = rows[:1] if mode == 'one_row' else rows+[rows[0]] if mode == 'duplicate' else rows[:-1]
                    results.write_text('\n'.join(json.dumps(r) for r in changed))
                    # 即使攻击者同步更新摘要哈希，计划行数/唯一性仍须核验。
                    changed_summary = json.loads(summary.read_text())
                    changed_summary['results_sha256'] = sha256(results)
                    summary.write_text(json.dumps(changed_summary))
                elif mode == 'summary':
                    changed = json.loads(summary.read_text())
                    changed['total'] = 1
                    summary.write_text(json.dumps(changed))
                elif mode == 'wav':
                    audio.write_bytes(b'replaced')
                else:
                    changed = json.loads(jobs.read_text())
                    changed[0]['text' if mode == 'job_text' else 'wav'] = 'wrong'
                    jobs.write_text(json.dumps(changed))
                    changed_summary = json.loads(summary.read_text())
                    changed_summary['asr_jobs_sha256'] = sha256(jobs)
                    summary.write_text(json.dumps(changed_summary))
                with self.assertRaises(ValueError):
                    m.analyze(experiment, asr, self.root / ('bad-'+mode))
                audio.write_bytes(audio_original)
                self.assertFalse((self.root / ('bad-'+mode)).exists())

    def test_cross_experiment_asr_rejected_and_cer_recomputed(self):
        plan = self.plan()
        first, second = self.root / 'first', self.root / 'second'
        for out in (first, second):
            m.run(plan, out, factory=lambda p: FakeModel(), postprocess=lambda d,r: d)
        jobs = json.loads((first / 'asr-jobs.json').read_text())
        asr = self.root / 'asr.json'
        asr.write_text(json.dumps([dict(id=j['id'], asr_text=j['text'], cer=42) for j in jobs]), encoding='utf-8')
        report = m.analyze(first, asr, self.root / 'good')
        self.assertEqual(report['total'], 8)
        self.assertTrue(all(p['complete_pair'] for p in report['pairs']))
        self.assertEqual(report['pairs'][0]['conditions'][0]['cer'], 0)
        with self.assertRaises(ValueError):
            m.analyze(second, asr, self.root / 'wrong')

    def test_spawn_timeout_terminates_only_experiment_worker(self):
        plan = self.plan()
        plan['timeout_seconds'] = 1
        processes = []
        def factory(p):
            model = m.ModelProcess(p, worker_target=hanging_worker)
            processes.append(model.process)
            return model
        rows = m.run(plan, self.root / 'hang', smoke=True, factory=factory)
        self.assertEqual([r['status'] for r in rows], ['timeout', 'not_run'])
        self.assertFalse(processes[0].is_alive())

    def test_offline_guards_force_cache_and_deny_network_in_child_only(self):
        script = r'''
import os, socket
from tools.benchmark_voice_references import OfflinePolicy, OfflineDependencyError
policy = OfflinePolicy()
policy.install()
assert os.environ['HF_HUB_OFFLINE'] == '1'
assert os.environ['MODELSCOPE_OFFLINE'] == '1'
calls = []
def fake_download(model_id, local_files_only=False):
    if not local_files_only:
        calls.append('network')
    if model_id == 'missing':
        raise ValueError('private path')
    return 'local-cache'
assert policy.cached_only(fake_download)('present', local_files_only=False) == 'local-cache'
assert calls == []
try:
    policy.cached_only(fake_download)('missing')
except OfflineDependencyError as exc:
    assert exc.kind == 'offline_cache_missing'
else:
    raise AssertionError('cache miss accepted')
try:
    socket.getaddrinfo('example.invalid', 443)
except OfflineDependencyError as exc:
    assert exc.kind == 'offline_network_blocked'
else:
    raise AssertionError('network not denied')
print('cache-only and network-denial passed')
'''
        result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_offline_missing_cache_is_retained_as_diagnostic(self):
        plan = self.plan()
        def factory(p):
            raise m.OfflineDependencyError('offline_cache_missing')
        rows = m.run(plan, self.root / 'offline', smoke=True, factory=factory)
        self.assertTrue(all(r.get('reason') == 'offline_cache_missing' for r in rows))

    def test_missing_cache_fails_before_model_load_and_swallowed_errors_survive(self):
        policy = m.OfflinePolicy()
        with self.assertRaises(m.OfflineDependencyError):
            policy.fail('offline_cache_missing')
        with self.assertRaises(m.OfflineDependencyError):
            policy.check()
        connection = mock.Mock()
        with mock.patch.object(m, 'OfflinePolicy') as policy_class, mock.patch.object(m, 'LocalModel') as model:
            policy_class.return_value.preflight_wetext.side_effect = m.OfflineDependencyError('offline_cache_missing')
            m._worker(connection, {})
            model.assert_not_called()
        self.assertEqual(connection.send.call_args.args[0][0], 'offline_cache_missing')
        connection.close.assert_called_once()
