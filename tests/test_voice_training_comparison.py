"""冻结比较合同；仅合成 fixture，不读取 people。"""
import json
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from tools import compare_voice_training as c


class ComparisonTests(unittest.TestCase):
    def test_common_dependencies_change_between_conditions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model, cache, package = [root/name for name in ('model', 'cache', 'wetext')]
            for directory in (model, cache, package, model/'CosyVoice-BlankEN'):
                directory.mkdir(parents=True)
            for name in ('cosyvoice2.yaml', 'llm.pt', 'flow.pt', 'hift.pt', 'campplus.onnx', 'speech_tokenizer_v2.onnx'):
                (model/name).write_bytes(b'fixture')
            (model/'CosyVoice-BlankEN'/'config.json').write_bytes(b'{}')
            (package/'__init__.py').write_bytes(b'')
            for lang in ('en', 'zh'):
                (cache/lang/'tn').mkdir(parents=True)
                for name in ('tagger.fst', 'verbalizer.fst'):
                    (cache/lang/'tn'/name).write_bytes(b'fst')
            frozen = c.common_dependencies(model, cache, package)
            c.verify_common_dependencies(frozen)
            (model/'flow.pt').write_bytes(b'changed between phases')
            with self.assertRaisesRegex(ValueError, 'common inference dependencies changed'):
                c.verify_common_dependencies(frozen)
            (model/'flow.pt').write_bytes(b'fixture')
            (model/'spk2info.pt').write_bytes(b'appeared')
            with self.assertRaisesRegex(ValueError, 'common inference dependencies changed'):
                c.verify_common_dependencies(frozen)
            (model/'spk2info.pt').unlink()
            (cache/'zh/tn/tagger.fst').write_bytes(b'changed cache')
            with self.assertRaisesRegex(ValueError, 'common inference dependencies changed'):
                c.verify_common_dependencies(frozen)

    def test_frozen_schedule(self):
        self.assertEqual(len(c.schedule()), 24)
        self.assertEqual({r['seed'] for r in c.schedule()}, {1986, 20261023})
        self.assertEqual(c.inference_text(c.TARGETS[0]), '<|wuyu|>慢慢来，勿要急。')
        self.assertEqual(c.inference_text(c.TARGETS[3]), '先喝口水吧。')

    def test_dependency_failure_prevents_material_publication(self):
        for failure_check in (2, 3):
            with self.subTest(failure_check=failure_check), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                inputs = dict(config=dict(model_root=str(root/'model'), vendor=str(root/'vendor'),
                                          state_dir=str(root/'state'), upstream=str(root/'upstream'), checkpoint='baseline'),
                              report=dict(checkpoint='candidate'), prepared_dir=str(root/'prepared'), frozen={},
                              reference=dict(audio=str(root/'reference'/'audio.wav')), reference_provenance={},
                              holdout=dict(record_id='heldout', audio_sha256='hash', feature_file='heldout.pt',
                                           feature_sha256='hash', provenance={}))
                fake = SimpleNamespace(evaluation={}, close=lambda: None,
                                       synthesize=lambda *args: ([0., .1, 0.], 24000))
                checks = [None]*(failure_check-1) + [ValueError('common inference dependencies changed')]
                args = SimpleNamespace(report='report', report_sha256='hash', reference_plan='reference', out=root/'out')
                with patch.object(c, 'validate_inputs', return_value=inputs), \
                     patch.object(c, 'ComparisonProcess', return_value=fake), \
                     patch.object(c, 'verify_common_dependencies', side_effect=checks), \
                     patch.object(c.training, 'verify_hashes'), \
                     patch.object(c.training, 'experiment_lock', return_value=nullcontext()), \
                     patch.object(c.benchmark, 'postprocess_live', side_effect=lambda data, rate: data):
                    with self.assertRaisesRegex(ValueError, 'common inference dependencies changed'):
                        c.run(args)
                self.assertTrue((args.out/'failure.json').is_file())
                self.assertFalse((args.out/'listen.html').exists())
                self.assertFalse((args.out/'summary.json').exists())

    def test_novelty_normalized(self):
        with self.assertRaises(ValueError):
            c.check_novelty([{'text': ' 慢慢来 勿要急！'}])

    def test_report_gate(self):
        good = dict(success=True, successful_updates=20, optimizer_steps=[20],
                    weights_changed=True, holdout_used_for_training=False,
                    holdout_loss_computed=False)
        c.check_report(good)
        for key, value in [('success', False), ('successful_updates', 19),
                           ('optimizer_steps', [19]), ('weights_changed', False),
                           ('holdout_used_for_training', True), ('holdout_loss_computed', True)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                c.check_report(dict(good, **{key: value}))

    def test_material_privacy_failures_and_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)/'fixture'
            c.fixture(out)
            page = (out/'listen.html').read_text(encoding='utf-8')
            self.assertEqual(page.count('<audio '), 23)
            self.assertIn('失败', page)
            self.assertIn('data:audio/wav;base64,', page)
            self.assertNotIn('candidate', page)
            self.assertNotIn('baseline', page)
            self.assertNotIn(str(out), page)
            self.assertIn('experimental-not-formal', page)
            self.assertEqual(len(json.loads((out/'answer-key.json').read_text())), 12)
            with self.assertRaises(ValueError):
                c.fixture(out)

    def test_reject_raw_output(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                c.fixture(Path(temp)/'raw'/'new')

    def test_audio_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            for data, rate in [([float('nan')], 24000), ([], 24000), ([0], 0)]:
                with self.assertRaises(ValueError):
                    c.save_wav(Path(temp)/'bad.wav', data, rate)

    def test_report_and_checkpoint_hash_binding(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report_path = root/'report.json'
            candidate = root/'candidate_step20.pt'
            candidate.write_bytes(b'fake checkpoint')
            (root/'config.json').write_text('{}')
            report = dict(success=True, successful_updates=20, optimizer_steps=[20],
                          weights_changed=True, holdout_used_for_training=False,
                          holdout_loss_computed=False, prepared_dir=str(root), prepared_sha256='seal',
                          config_sha256=c.sha256(root/'config.json'), checkpoint=str(candidate),
                          checkpoint_sha256=c.sha256(candidate))
            c.write_json(report_path, report)
            with self.assertRaisesRegex(ValueError, 'training report changed'):
                c.validate_inputs(report_path, 'wrong', root/'refs.json')
            candidate.write_bytes(b'tampered')
            with patch.object(c.training, 'validate_prepared', return_value=({}, [])):
                with self.assertRaisesRegex(ValueError, 'candidate checkpoint changed'):
                    c.validate_inputs(report_path, c.sha256(report_path), root/'refs.json')

    def test_material_rejects_result_membership_and_audio_tamper(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)/'fixture'
            c.fixture(out)
            rows = c.read_json(out/'results.json')
            with self.assertRaisesRegex(ValueError, 'all planned takes'):
                c.material(out, rows[:-1], 'bad')
            (out/rows[1]['wav']).write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError, 'audio binding'):
                c.material(out, rows, 'bad')


if __name__ == '__main__':
    unittest.main()
