import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import audit_legacy_voice_sources as m


AVAILABLE = all(importlib.util.find_spec(x) for x in ('numpy', 'soundfile'))


@unittest.skipUnless(AVAILABLE, 'existing numpy/soundfile required; use CosyVoice environment')
class SourceBridgeTests(unittest.TestCase):
    def setUp(self):
        import numpy as np
        import soundfile as sf
        self.np, self.sf = np, sf
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.person = self.root / 'person'
        self.legacy = self.root / 'legacy'
        self.legacy.mkdir()
        self.native = self.person / 'normalized/wechat_voice_manifest.jsonl'
        self.native.parent.mkdir(parents=True)
        self.source = self.person / 'processed/original.wav'
        self.source.parent.mkdir()
        # 包含正负、满幅和小样本，原PCM子数组与历史重新量化必须不同。
        self.pcm = np.array([-32768, -30000, -100, -1, 0, 1, 100, 30000, 32767, 1234], dtype=np.int16)
        sf.write(str(self.source), self.pcm, 10, subtype='PCM_16')
        self.target = self.legacy / 'segment.wav'
        sf.write(str(self.target), np.array([-29999, -99, 0, 0, 0, 99, 29999], dtype=np.int16),
                 10, subtype='PCM_16')
        self.native_rows = [dict(record_id=hashlib.sha256(b'wechat_voice:123').hexdigest(),
            record_type='media_item', person='person', source='wechat', tier=2, media_type='audio',
            file_ref='processed/original.wav', sha256=m.sha256(self.source), size_bytes=self.source.stat().st_size,
            duration_ms=1000, svr_id=123, provenance={'native_id':'123'}, sender_wxid='synthetic')]
        self.rows = [dict(seg_key='direct', orig_key='original', wav=str(self.source),
                         start_s=0, end_s=1, duration_s=1, segmented=False),
                     dict(seg_key='segment', orig_key='original', wav=str(self.target),
                         start_s=.1, end_s=.8, duration_s=.7, segmented=True)]
        self.segments = self.root / 'segments.jsonl'
        self.recipe = self.root / 'recipe.py'
        self.recipe.write_text('raise RuntimeError("must never execute")\n')
        self.refresh()

    def refresh(self):
        for path, rows in ((self.native, self.native_rows), (self.segments, self.rows)):
            path.write_text(''.join(json.dumps(r)+'\n' for r in rows), encoding='utf-8')
        for name, values in [('text', ['synthetic']*len(self.rows)),
                             ('utt2spk', ['speaker']*len(self.rows)),
                             ('wav.scp', [r['wav'] for r in self.rows])]:
            (self.legacy / name).write_text(''.join(r['seg_key']+' '+v+'\n' for r,v in zip(self.rows,values)),
                                           encoding='utf-8')

    def run_audit(self, name='out', **kw):
        args = dict(legacy_data_dir=self.legacy, segment_manifest=self.segments,
                    native_manifest=self.native, person_root=self.person,
                    recipe_path=self.recipe, out=self.root/name)
        args.update(kw)
        out = m.audit(**args)
        return m.read_json(out/'report.json'), m.read_jsonl(out/'items.jsonl')

    def test_direct_quantized_segment_and_immutable_inputs(self):
        before = {p:m.sha256(p) for p in self.root.rglob('*') if p.is_file()}
        report, items = self.run_audit()
        self.assertEqual(report['counts'], dict(verified_direct=1, verified_segment=1, excluded_missing=0, mismatch=0))
        self.assertFalse(report['ready_for_training'])
        self.assertTrue(report['input_stable'])
        self.assertEqual(items[1]['expected_pcm_sha256'], items[1]['target_pcm_sha256'])
        self.assertEqual(items[1]['requested_frames'], [1, 8])
        self.assertTrue(all(not i['ready_for_training'] for i in items))
        self.assertEqual(before, {p:m.sha256(p) for p in before})
        self.assertNotIn('synthetic', json.dumps(items))

    def test_raw_pcm_slice_is_not_accepted(self):
        self.sf.write(str(self.target), self.pcm[1:8], 10, subtype='PCM_16')
        report, items = self.run_audit()
        self.assertEqual(report['counts']['mismatch'], 1)
        self.assertEqual(items[1]['reason'], 'pcm_mismatch')

    def test_missing_metadata_is_excluded_not_inferred(self):
        self.native_rows = []
        self.refresh()
        report, items = self.run_audit()
        self.assertEqual(report['counts']['excluded_missing'], 2)
        self.assertTrue(all(i['status']=='excluded_missing_current_metadata' for i in items))
        self.assertTrue(all(i['native_identity_sha256'] is None for i in items))

    def test_stereo_mean_and_finite_tail_truncation(self):
        stereo = self.np.column_stack((self.pcm, self.pcm[::-1]))
        self.sf.write(str(self.source), stereo, 10, subtype='PCM_16')
        self.native_rows[0].update(sha256=m.sha256(self.source), size_bytes=self.source.stat().st_size, duration_ms=1200)
        self.rows = [dict(self.rows[1], start_s=.25, end_s=1.2, duration_s=.95)]
        self.sf.write(str(self.target), self.np.full(8, 616, dtype=self.np.int16), 10, subtype='PCM_16')
        # 独立数值期望：镜像两声道的每帧均值不全相等。
        expected = self.np.array([14949, 49, 0, 0, 49, 14949, 1383, -15766], dtype=self.np.int16)
        self.sf.write(str(self.target), expected, 10, subtype='PCM_16')
        self.refresh()
        report, items = self.run_audit()
        self.assertEqual(report['counts']['verified_segment'], 1)
        self.assertEqual(items[0]['requested_frames'], [2, 12])
        self.assertEqual(items[0]['effective_frames'], [2, 10])
        self.assertTrue(items[0]['tail_truncated'])
        self.assertEqual(items[0]['source_channels'], 2)

    def test_wrong_rate_channels_frames_and_sample(self):
        correct, rate = self.sf.read(str(self.target), dtype='int16')
        cases = [(correct, 11, 'sample_rate_mismatch'),
                 (self.np.column_stack((correct,correct)), rate, 'target_not_mono'),
                 (correct[:-1], rate, 'frame_count_mismatch'),
                 (correct+1, rate, 'pcm_mismatch')]
        for index, (data, sr, reason) in enumerate(cases):
            self.sf.write(str(self.target), data, sr, subtype='PCM_16')
            report, items = self.run_audit('out'+str(index))
            self.assertEqual(report['counts']['mismatch'], 1)
            self.assertEqual(items[1]['reason'], reason)

    def test_identity_hash_path_and_duplicate_rejected(self):
        original = json.loads(json.dumps(self.native_rows))
        changes = [dict(sha256='0'*64), dict(svr_id=999), dict(record_id='0'*64),
                   dict(source='other'), dict(person='other'), dict(file_ref='../original.wav'),
                   dict(provenance={}), dict(sender_wxid=''), dict(file_ref='')]
        for index, change in enumerate(changes):
            self.native_rows = [dict(original[0], **change)]
            self.refresh()
            with self.subTest(change=list(change)), self.assertRaises(ValueError):
                self.run_audit('invalid-native-'+str(index))
        self.native_rows = original*2
        self.refresh()
        with self.assertRaises(ValueError):
            self.run_audit()

    def test_segment_schema_coverage_and_path_errors(self):
        original = json.loads(json.dumps(self.rows))
        changes = [dict(start_s=-1), dict(end_s=float('nan')), dict(segmented='true'),
                   dict(wav=str(self.recipe)), dict(orig_key=''), dict(start_s=True),
                   dict(orig_key='../original'), dict(duration_s=500)]
        for index, change in enumerate(changes):
            self.rows = [original[0], dict(original[1], **change)]
            self.refresh()
            # wav.scp 固定原始路径，manifest篡改不能一起绕过。
            (self.legacy/'wav.scp').write_text('direct '+str(self.source)+'\nsegment '+str(self.target)+'\n')
            with self.subTest(change=list(change)), self.assertRaises(ValueError):
                self.run_audit('invalid-segment-'+str(index))
        self.rows = original
        self.refresh()
        (self.legacy/'utt2spk').write_text('direct speaker\n')
        with self.assertRaises(ValueError):
            self.run_audit()

    def test_unbounded_tail_and_empty_segment_fail(self):
        for index, change in enumerate([dict(end_s=900), dict(start_s=1, end_s=1.1)]):
            self.rows[1].update(change)
            self.rows[1]['duration_s'] = self.rows[1]['end_s']-self.rows[1]['start_s']
            self.refresh()
            report, items = self.run_audit('out'+str(index))
            self.assertEqual(report['counts']['mismatch'], 1)
            self.assertEqual(items[1]['reason'], 'invalid_frame_boundary')

    def test_backup_manifest_and_output_overlap_or_overwrite_rejected(self):
        backup = self.root/'backup.jsonl'
        backup.write_bytes(self.native.read_bytes())
        with self.assertRaises(ValueError):
            self.run_audit(native_manifest=backup)
        for out in (self.person/'out', self.legacy/'out', self.root/'raw'/'out'):
            with self.assertRaises(ValueError):
                self.run_audit(out=out)
        self.run_audit()
        with self.assertRaises(ValueError):
            self.run_audit()

    def test_mutation_during_comparison_rejected(self):
        real = m.compare_segment
        def mutate(*args, **kw):
            result = real(*args, **kw)
            self.recipe.write_text('changed')
            return result
        with patch.object(m, 'compare_segment', side_effect=mutate), self.assertRaisesRegex(ValueError, 'input changed'):
            self.run_audit()
        self.assertFalse((self.root/'out').exists())

    def test_duplicate_and_incomplete_segment_manifest_rejected(self):
        for rows in ([self.rows[0], self.rows[0]], [self.rows[0]]):
            self.segments.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            with self.assertRaises(ValueError):
                self.run_audit()

    def test_direct_copy_is_not_original_reference(self):
        copy = self.legacy/'copy.wav'
        copy.write_bytes(self.source.read_bytes())
        self.rows[0]['wav'] = str(copy)
        self.refresh()
        report, items = self.run_audit()
        self.assertEqual(report['counts']['mismatch'], 1)
        self.assertEqual(items[0]['reason'], 'direct_reference_mismatch')

    def test_cli_content_failure_emits_evidence_and_nonzero(self):
        self.sf.write(str(self.target), self.pcm[1:8], 10, subtype='PCM_16')
        args = ['--legacy-data-dir', str(self.legacy), '--segment-manifest', str(self.segments),
                '--native-manifest', str(self.native), '--person-root', str(self.person),
                '--recipe-path', str(self.recipe), '--out', str(self.root/'cli')]
        with patch('builtins.print'):
            self.assertEqual(m.main(args), 1)
        report = m.read_json(self.root/'cli/report.json')
        self.assertEqual(report['status'], 'failed')
        self.assertFalse(report['ready_for_training'])

    def test_manifest_mutated_during_parse_rejected(self):
        real = m.read_jsonl
        def mutate(path):
            result = real(path)
            if path == self.native:
                self.native.write_text('[]')
            return result
        with patch.object(m, 'read_jsonl', side_effect=mutate), self.assertRaisesRegex(ValueError, 'input changed'):
            self.run_audit()

    def test_missing_source_file_fails_not_excluded(self):
        self.rows = [self.rows[1]]
        self.refresh()
        self.source.unlink()
        with self.assertRaises(ValueError):
            self.run_audit()

    def test_input_change_during_items_write_revokes_completion(self):
        real = m.write_jsonl
        def mutate(*args, **kw):
            result = real(*args, **kw)
            self.recipe.write_text('changed during items output')
            return result
        with patch.object(m, 'write_jsonl', side_effect=mutate), self.assertRaisesRegex(ValueError, 'input changed'):
            self.run_audit()
        self.assertFalse((self.root/'out/report.json').exists())

    def test_input_change_during_report_write_revokes_completion(self):
        real = m.write_json
        def mutate(*args, **kw):
            result = real(*args, **kw)
            self.recipe.write_text('changed during report output')
            return result
        with patch.object(m, 'write_json', side_effect=mutate), self.assertRaisesRegex(ValueError, 'input changed'):
            self.run_audit()
        self.assertFalse((self.root/'out/report.json').exists())

    def test_symlink_source_rejected(self):
        link = self.source.parent/'link.wav'
        try:
            link.symlink_to(self.source)
        except OSError:
            self.skipTest('host does not permit synthetic symlink creation')
        self.native_rows[0]['file_ref'] = 'processed/link.wav'
        self.refresh()
        with self.assertRaises(ValueError):
            self.run_audit()


if __name__ == '__main__':
    unittest.main()
