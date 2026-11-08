import importlib.util
import json
import unittest
from pathlib import Path

from tests import test_import_wechat_viewpoint as fixture_module
from tests.test_voice_upgrade import wav
from tools import build_training_manifest as training
from tools.viewpoint_manifest import sha256
from tools import audit_voice_training_inputs as m

dump = fixture_module.dump


class ContractTests(unittest.TestCase):
    setUp = fixture_module.ImportViewpointTests.setUp
    row = fixture_module.ImportViewpointTests.row
    refresh = fixture_module.ImportViewpointTests.refresh
    run_import = fixture_module.ImportViewpointTests.run_import

    def fixture(self):
        wav(self.source / 'records/conversation-1/a.wav')
        self.refresh()
        dataset = self.run_import()
        pending = self.root / 'pending'
        training.build(person='mama', datasets=[dataset], out=pending)
        c = m.read_jsonl(pending / 'candidates.jsonl')[0]
        review = dict(record_id=c['record_id'], audio_sha256=c['audio_sha256'], revision=c['revision'],
                      speaker_id='mama', speaker_status='confirmed', single_speaker=True,
                      source_kind='real_recording', text='synthetic approved', transcript_status='corrected',
                      quality_status='approved', duration_approved=True, decided_by='synthetic',
                      decided_at='2026-10-22')
        overlay = self.root / 'reviews.json'
        dump(overlay, dict(schema_version=1, reviews=[review]))
        self.checked = self.root / 'checked'
        training.build(person='mama', datasets=[dataset], out=self.checked, reviews=overlay)
        c = m.read_jsonl(self.checked / 'eligible.jsonl')[0]
        self.plan = self.root / 'plan.json'
        self.plan_data = dict(schema_version=1, source_build=str(self.checked),
                              source_eligible_sha256=sha256(self.checked / 'eligible.jsonl'),
                              ready_for_training=False, train=[], validation=[])
        self.plan_data[c['split']] = [{k:c[k] for k in m.PLAN_FIELDS}]
        dump(self.plan, self.plan_data)
        self.legacy_dir = self.root / 'legacy-data'
        wav(self.legacy_dir / 'old.wav', seconds=4)
        (self.legacy_dir / 'text').write_text('old synthetic legacy\n')
        (self.legacy_dir / 'wav.scp').write_text('old old.wav\n')
        (self.legacy_dir / 'utt2spk').write_text('old synthetic\n')
        return c

    def test_complete_chain_and_metadata_only(self):
        c = self.fixture()
        rows, inputs = m.approved_inputs(self.checked, self.plan)
        self.assertEqual(len(rows), 1)
        self.assertTrue(inputs)
        if not m.dependencies_available():
            self.skipTest('numpy/scipy/soundfile unavailable; complete audit requires Cosy environment')
        out = m.audit(self.checked, self.plan, self.legacy_dir, self.root / 'out')
        approved = m.read_jsonl(out / (c['split'] + '-approved.jsonl'))
        self.assertEqual(len(approved), 1)
        self.assertFalse(approved[0]['ready_for_training'])
        self.assertNotIn('text', approved[0])
        report = m.read_json(out / 'audit-report.json')
        self.assertEqual(report['coverage']['new_legacy_expected'], 1)
        self.assertEqual(len(m.read_jsonl(out / 'comparisons.jsonl')), 1)
        self.assertFalse((out / 'text').exists())
        with self.assertRaises(ValueError):
            m.audit(self.checked, self.plan, self.legacy_dir, out)

    def test_plan_tampering(self):
        c = self.fixture()
        for field, value in [('split', 'test'), ('revision', 'bad'), ('audio_file', '../escape.wav')]:
            with self.subTest(field=field):
                d = json.loads(json.dumps(self.plan_data))
                d[c['split']][0][field] = value
                dump(self.plan, d)
                with self.assertRaises(ValueError):
                    m.approved_inputs(self.checked, self.plan)
        for mode in ['missing', 'duplicate', 'cross', 'digest']:
            d = json.loads(json.dumps(self.plan_data))
            if mode == 'missing':
                d[c['split']] = []
            elif mode == 'duplicate':
                d[c['split']] *= 2
            elif mode == 'cross':
                d['validation' if c['split'] == 'train' else 'train'] = d[c['split']]
            else:
                d['source_eligible_sha256'] = '0' * 64
            dump(self.plan, d)
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                m.approved_inputs(self.checked, self.plan)

    def test_absolute_plan_audio_matches_relative_candidate(self):
        c = self.fixture()
        self.plan_data[c['split']][0]['audio_file'] = str((self.checked/c['audio_file']).resolve())
        dump(self.plan, self.plan_data)
        before = self.plan.read_bytes()
        rows, _ = m.approved_inputs(self.checked, self.plan)
        self.assertEqual(rows[0]['audio_file'], c['audio_file'])
        self.assertEqual(self.plan.read_bytes(), before)

    def test_plan_audio_escape_and_different_target(self):
        c = self.fixture()
        other = self.checked/'audio/other.wav'
        other.write_bytes((self.checked/c['audio_file']).read_bytes())
        outside = self.root/'outside.wav'
        outside.write_bytes(other.read_bytes())
        for reference in (str(outside), '../outside.wav',
                          str(self.checked/'..'/'outside.wav'), str(other), 'audio/other.wav'):
            with self.subTest(reference=reference):
                self.plan_data[c['split']][0]['audio_file'] = reference
                dump(self.plan, self.plan_data)
                with self.assertRaises(ValueError):
                    m.approved_inputs(self.checked, self.plan)

    def test_absolute_plan_audio_link_rejected(self):
        c = self.fixture()
        link = self.checked/'audio/link.wav'
        try:
            link.symlink_to(self.checked/c['audio_file'])
        except OSError:
            self.skipTest('host does not permit synthetic symlink creation')
        self.plan_data[c['split']][0]['audio_file'] = str(link)
        dump(self.plan, self.plan_data)
        with self.assertRaises(ValueError):
            m.approved_inputs(self.checked, self.plan)

    def test_missing_approval_and_changed_source(self):
        self.fixture()
        path = self.checked / 'candidates.jsonl'
        rows = m.read_jsonl(path)
        rows[0].pop('review')
        m.write_jsonl(path, rows)
        with self.assertRaises(ValueError):
            m.approved_inputs(self.checked, self.plan)

    def test_anchored_source_mutation(self):
        self.fixture()
        (self.root / 'reviews.json').write_text('{}')
        with self.assertRaises(ValueError):
            m.approved_inputs(self.checked, self.plan)

    def test_raw_source_and_wav_mutation(self):
        self.fixture()
        path = self.checked / m.read_jsonl(self.checked / 'eligible.jsonl')[0]['audio_file']
        old = path.read_bytes()
        path.write_bytes(b'changed')
        with self.assertRaises(ValueError):
            m.approved_inputs(self.checked, self.plan)
        path.write_bytes(old)
        summary = m.read_json(self.checked / 'summary.json')
        dataset = next(Path(e['path']) for e in summary['inputs'] if Path(e['path']).name=='dataset.json')
        manifest, records = m.load_dataset(dataset)
        source = m.safe_path(dataset.parents[4], records[0]['provenance']['source_file'])
        source.write_text('[]')
        with self.assertRaises(ValueError):
            m.approved_inputs(self.checked, self.plan)

    def test_two_groups_full_coverage(self):
        self.fixture()
        # 新建独立合成数据版本，保持真实构建器产生的哈希分组规则。
        from tools.viewpoint_manifest import read_jsonl
        first = read_jsonl(self.checked / 'eligible.jsonl')[0]
        audio = self.source / 'records/conversation-1/b.wav'
        for offset in range(100):
            wav(audio, seconds=2, offset=offset)
            split = 'validation' if int(sha256(audio)[:8], 16)%10==0 else 'train'
            if split != first['split']:
                break
        self.rows[4]['media_status'] = []
        self.rows[4]['media'] = [dict(kind='voice', path='b.wav', format='WAV', duration_check='within_tolerance')]
        self.refresh()
        from tools.import_wechat_viewpoint import import_package
        dataset = import_package(person='mama', viewpoint='father', source=self.source,
                                 legacy_uif=self.legacy, batch='batch2', repo_root=self.root)
        pending = self.root / 'pending2'
        training.build(person='mama', datasets=[dataset], out=pending)
        reviews = []
        template = m.read_json(self.root/'reviews.json')['reviews'][0]
        for c in read_jsonl(pending/'candidates.jsonl'):
            reviews.append(dict(template, **{k:c[k] for k in ('record_id','audio_sha256','revision')}))
        overlay = self.root/'reviews2.json'
        dump(overlay, dict(schema_version=1, reviews=reviews))
        checked = self.root/'checked2'
        training.build(person='mama', datasets=[dataset], out=checked, reviews=overlay)
        rows = read_jsonl(checked/'eligible.jsonl')
        plan = dict(self.plan_data, source_build=str(checked), source_eligible_sha256=sha256(checked/'eligible.jsonl'))
        for group in ('train','validation'):
            plan[group] = [{k:c[k] for k in m.PLAN_FIELDS} for c in rows if c['split']==group]
        self.assertEqual([len(plan[g]) for g in ('train','validation')], [1,1])
        dump(self.plan, plan)
        if not m.dependencies_available():
            self.skipTest('numpy/scipy/soundfile unavailable')
        out = m.audit(checked, self.plan, self.legacy_dir, self.root/'two-out')
        pairs = read_jsonl(out/'comparisons.jsonl')
        self.assertEqual(len(pairs), 3)
        self.assertEqual(sum(p['kind']=='new_new' for p in pairs), 1)
        self.assertEqual(len(read_jsonl(out/'train-approved.jsonl')), 1)
        self.assertEqual(len(read_jsonl(out/'validation-approved.jsonl')), 1)
        self.assertTrue(m.read_json(out/'audit-report.json')['conflicts'])

    def test_legacy_fail_closed(self):
        self.fixture()
        for content in ['old cat file.wav |\n', 'old old.wav\nold old.wav\n', 'wrong old.wav\n']:
            (self.legacy_dir / 'wav.scp').write_text(content)
            with self.assertRaises(ValueError):
                m.legacy_inputs(self.legacy_dir)

    def test_unreadable_legacy_is_counted(self):
        self.fixture()
        if not m.dependencies_available():
            self.skipTest('numpy/scipy/soundfile unavailable')
        (self.legacy_dir/'old.wav').write_bytes(b'broken')
        out = m.audit(self.checked, self.plan, self.legacy_dir, self.root/'error-out')
        report = m.read_json(out/'audit-report.json')
        self.assertEqual(report['coverage']['attempted'], 1)
        self.assertEqual(report['coverage']['indeterminate'], 1)
        self.assertEqual(report['audio_status'][-1]['status'], 'error')
        self.assertEqual(len(m.read_jsonl(out/'conflicts.jsonl')), 1)

    def test_legacy_source_mapping(self):
        self.fixture()
        source = self.root / 'segments.jsonl'
        row = dict(seg_key='old', orig_key='original', wav=str(self.legacy_dir / 'old.wav'),
                   start_s=0, end_s=4)
        m.write_jsonl(source, [row])
        rows, _ = m.legacy_inputs(self.legacy_dir, source)
        self.assertEqual(rows[0]['source_group']['basis'], 'legacy_manifest_orig_key')
        for values in [[], [row, row], [dict(row, seg_key='missing')], [dict(row, end_s=-1)]]:
            m.write_jsonl(source, values)
            with self.assertRaises(ValueError):
                m.legacy_inputs(self.legacy_dir, source)

    def test_native_bridge_is_explicit_and_not_training_authorization(self):
        self.fixture()
        source = self.root/'segments.jsonl'
        m.write_jsonl(source, [dict(seg_key='old', orig_key='original',
            wav=str(self.legacy_dir/'old.wav'), start_s=0, end_s=4)])
        person = self.root/'person'
        original = person/'processed/original.wav'
        wav(original)
        manifest = person/'normalized/wechat_voice_manifest.jsonl'
        manifest.parent.mkdir()
        m.write_jsonl(manifest, [dict(file_ref='processed/original.wav', sha256=sha256(original),
            svr_id=123, sender_wxid='synthetic', provenance=dict(native_id='123'))])
        rows, inputs = m.legacy_inputs(self.legacy_dir, source, manifest, person)
        group = rows[0]['source_group']
        self.assertFalse(group['cross_corpus_bridge_verified'])
        self.assertEqual(group['original_audio_status'], 'original_audio_hash_verified')
        self.assertIn(original, inputs)
        original.write_bytes(b'changed')
        with self.assertRaises(ValueError):
            m.legacy_inputs(self.legacy_dir, source, manifest, person)
        with self.assertRaises(ValueError):
            m.legacy_inputs(self.legacy_dir, source, manifest)

    def test_output_boundaries(self):
        self.fixture()
        for output in [self.checked, self.checked / 'child', self.root / 'people/mama/raw/out']:
            with self.subTest(output=output), self.assertRaises(ValueError):
                m.audit(self.checked, self.plan, self.legacy_dir, output)


@unittest.skipUnless(all(importlib.util.find_spec(x) for x in ('numpy', 'scipy', 'soundfile')),
                     'numpy/scipy/soundfile unavailable')
class WaveTests(unittest.TestCase):
    def test_wave_transformations_and_non_matches(self):
        import numpy as np
        from scipy.signal import resample_poly
        import soundfile as sf
        import tempfile
        rng = np.random.default_rng(123)
        x = rng.normal(0, .08, 24000)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            sf.write(root / 'base.wav', x, 8000, subtype='PCM_16')
            base = m.load_audio(root / 'base.wav')
            variants = [('header', x, 8000, 'PCM_24'), ('gain', x*.3, 8000, 'PCM_16'),
                        ('inverse', -x, 8000, 'PCM_16'),
                        ('resampled', resample_poly(x, 2, 1), 16000, 'PCM_16'),
                        ('offset', np.r_[np.zeros(4000), x], 8000, 'PCM_16'),
                        ('crop', x[4000:16000], 8000, 'PCM_16')]
            for name, values, rate, subtype in variants:
                sf.write(root / (name+'.wav'), values, rate, subtype=subtype)
                with self.subTest(name=name):
                    self.assertTrue(m.compare_audio(base, m.load_audio(root / (name+'.wav')))['suspected_duplicate'])
            sf.write(root / 'noise.wav', rng.normal(0, .08, len(x)), 8000)
            self.assertFalse(m.compare_audio(base, m.load_audio(root / 'noise.wav'))['suspected_duplicate'])
            for name, values in [('silent', np.zeros(len(x))), ('dc', np.ones(len(x))*.2),
                                 ('short', x[:1000])]:
                sf.write(root / (name+'.wav'), values, 8000)
                a = m.load_audio(root / (name+'.wav'))
                result = m.compare_audio(a, a)
                self.assertEqual(result['status'], 'indeterminate')
                self.assertFalse(result['suspected_duplicate'])
            (root / 'bad.wav').write_bytes(b'broken')
            self.assertEqual(m.load_audio(root / 'bad.wav')['status'], 'error')
