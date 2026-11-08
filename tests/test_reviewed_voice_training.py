"""Synthetic pilot gates; never read private production inputs."""
import copy
import importlib.util
import tempfile
import unittest
from contextlib import ExitStack, contextmanager, nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools import train_reviewed_voice as pilot


def rows():
    return [dict(record_id=str(i), audio_sha256=str(i), dedup_group=str(i),
                 parent_record_id=str(i), provenance=dict(source_record_id=str(i)),
                 split='train' if i < 10 else 'validation',
                 effective_language='mandarin' if i == 2 else 'wu', speaker_id='mama',
                 text='synthetic', training_eligible=True, exclusion_reasons=[])
            for i in range(11)]


class Gates(unittest.TestCase):
    def test_membership(self):
        pilot.validate_rows(rows())

    def test_overlap_and_unknown_provenance(self):
        for field in ('record_id', 'audio_sha256', 'dedup_group', 'parent_record_id', 'provenance'):
            sample = rows()
            sample[-1][field] = copy.deepcopy(sample[0][field])
            with self.subTest(field=field), self.assertRaises(ValueError):
                pilot.validate_rows(sample)
        sample = rows()
        sample[0]['provenance'] = {}
        with self.assertRaises(ValueError):
            pilot.validate_rows(sample)

    def test_empty_wrong_language_and_prefix(self):
        for sample in ([], rows()[:-1]):
            with self.assertRaises(ValueError):
                pilot.validate_rows(sample)
        for key, value in [('effective_language', 'unknown'), ('text', '<|wuyu|>bad'),
                           ('speaker_id', 'other'), ('training_eligible', False)]:
            sample = rows()
            sample[0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                pilot.validate_rows(sample)

    def test_hash_and_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'file'
            path.write_text('first')
            frozen = pilot.hashes([path])
            pilot.verify_hashes(frozen)
            path.write_text('changed')
            with self.assertRaises(ValueError):
                pilot.verify_hashes(frozen)
            with self.assertRaises(ValueError):
                pilot.fresh_output(Path(tmp), [])

    def test_latest_and_ledger(self):
        snapshot = dict(latest=pilot.LATEST, receipts=[])
        pilot.validate_snapshot(snapshot, pilot.digest(snapshot))
        changed = copy.deepcopy(snapshot)
        changed['latest']['language'] = 'stale'
        with self.assertRaises(ValueError):
            pilot.validate_snapshot(changed, pilot.digest(changed))
        with self.assertRaises(ValueError):
            pilot.validate_snapshot(snapshot, 'wrong')


class ArtifactGates(unittest.TestCase):
    def setUp(self):
        from tests.test_reviewed_language_inputs import ReviewedLanguageTests
        self.fixture = ReviewedLanguageTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.upstream = self.fixture.build()
        self.root = self.fixture.root
        self.latest = pilot.ledger(self.fixture.state)['latest']
        self.patch = patch.object(pilot, 'LATEST', self.latest)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.pins = self.root/'pins.json'
        pilot.write_json(self.pins, [dict(path=str(self.upstream/n), sha256=pilot.sha256(self.upstream/n))
                                     for n in pilot.UPSTREAM_NAMES])
        self.pin_hash = pilot.sha256(self.pins)

    def validate(self):
        return pilot.validate_upstream(self.upstream, self.fixture.state, self.pins, self.pin_hash)

    def test_real_receipt_contract(self):
        data, _ = self.validate()
        self.assertEqual(len(data), 11)

    def test_prepared_text_tamper(self):
        path = self.upstream/'wu/train.jsonl'
        with path.open('a') as stream:
            stream.write('\n')
        with self.assertRaises(ValueError):
            self.validate()

    def test_replaced_pin_file(self):
        self.pins.write_text('[]')
        with self.assertRaises(ValueError):
            self.validate()

    def test_new_formal_submission_rejected(self):
        values = self.fixture.store.session()['drafts']['language']['values']
        self.fixture.submit('language', values)
        with self.assertRaises(ValueError):
            self.validate()

    def test_changed_approval_sidecar_rejected(self):
        path = self.fixture.state/'submissions'/(self.latest['source']+'.json')
        with path.open('a') as stream:
            stream.write(' ')
        with self.assertRaises(ValueError):
            self.validate()

    def make_prepared(self):
        data, report = self.validate()
        out = self.root/'features'
        out.mkdir()
        entries = []
        for row in data:
            relative = row['split']+'/'+row['record_id']+'.pt'
            path = out/relative
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(b'synthetic-feature-placeholder')
            entries.append(dict(row, feature_file=relative, feature_sha256=pilot.sha256(path)))
        dependency = self.root/'dependency'
        dependency.write_text('synthetic')
        config = dict(recipe=pilot.RECIPE, implementation_sha256=pilot.sha256(Path(pilot.__file__)),
                      upstream=str(self.upstream), state_dir=str(self.fixture.state),
                      pins=str(self.pins), pins_sha256=self.pin_hash,
                      dependency_sha256=pilot.hashes([dependency]), checkpoint=str(dependency),
                      checkpoint_sha256=pilot.sha256(dependency), vendor=str(self.root/'vendor'),
                      model_root=str(self.root/'model'))
        pilot.write_json(out/'config.json', config)
        pilot.write_json(out/'manifest.json', dict(items=entries, speaker_embeddings_used=False,
                                                 inference_references=[]))
        pilot.write_json(out/'prepared.json', dict(success=True, training_started=False,
                         output_sha256=pilot.hashes([p for p in out.rglob('*') if p.is_file()])))
        return out, pilot.sha256(out/'prepared.json')

    def test_feature_and_seal_tamper(self):
        root, seal = self.make_prepared()
        pilot.validate_prepared(root, seal)
        next((root/'train').glob('*.pt')).write_bytes(b'tampered')
        with self.assertRaises(ValueError):
            pilot.validate_prepared(root, seal)
        with self.assertRaises(ValueError):
            pilot.validate_prepared(root, 'wrong')

    def test_failed_run_never_publishes_report(self):
        root, seal = self.make_prepared()
        args = SimpleNamespace(prepared=root, prepared_sha256=seal,
                               checkpoint=self.root/'dependency', out=self.root/'failed')
        with patch.object(pilot, 'experiment_lock', return_value=nullcontext()), \
                patch.object(pilot, 'offline', side_effect=RuntimeError('synthetic failure')):
            with self.assertRaises(RuntimeError):
                pilot.train(args)
        self.assertTrue((args.out/'failure.json').is_file())
        self.assertFalse((args.out/'report.json').exists())
        self.assertFalse((args.out/'candidate_step20.pt').exists())


@unittest.skipUnless(importlib.util.find_spec('torch'), 'torch unavailable')
class Optimization(unittest.TestCase):
    def setUp(self):
        import torch
        self.torch = torch
        class Toy(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.weight = torch.nn.Parameter(torch.tensor([1.0]))
            def forward(self, batch, device):
                return dict(loss=(self.weight * batch['factor']).sum())
        self.model = Toy()
        self.batches = [dict(factor=1.0) for _ in range(10)]

    def run_loop(self, batches=None, optimizer_factory=None):
        records = []
        result = pilot.optimize(self.model, self.batches if batches is None else batches,
                                self.torch.device('cpu'), records.append, lambda: None,
                                optimizer_factory=optimizer_factory)
        return result, records

    def test_exact_fresh_steps_and_weight_change(self):
        self.model.epoch = 14
        result, records = self.run_loop()
        self.assertEqual(result['successful_updates'], 20)
        self.assertEqual(len(records), 20)
        self.assertEqual(result['optimizer_steps'], [20])
        self.assertTrue(result['weights_changed'])
        self.assertEqual([r['epoch'] for r in records], [0]*10+[1]*10)

    def test_zero_steps_rejected(self):
        with self.assertRaises(ValueError):
            self.run_loop([])

    def test_nonfinite_loss_and_gradient(self):
        self.batches[0]['factor'] = float('nan')
        with self.assertRaises(ValueError):
            self.run_loop()
        self.batches[0]['factor'] = 1.0
        self.model.weight.register_hook(lambda g: g * float('inf'))
        with self.assertRaises((ValueError, RuntimeError)):
            self.run_loop()

    def test_skipped_optimizer_rejected(self):
        torch = self.torch
        class Skips(torch.optim.Adam):
            def step(self, *args, **kwargs):
                pass
        with self.assertRaises(ValueError):
            self.run_loop(optimizer_factory=Skips)

    def test_empty_and_bad_feature(self):
        torch = self.torch
        valid = dict(text_token=torch.tensor([[1, 2]], dtype=torch.int32),
                     text_token_len=torch.tensor([2], dtype=torch.int32),
                     speech_token=torch.tensor([[3]], dtype=torch.int32),
                     speech_token_len=torch.tensor([1], dtype=torch.int32))
        pilot.validate_feature(valid)
        for value in (torch.empty((1, 0), dtype=torch.int32), torch.tensor([[7000]]),
                      torch.tensor([[float('nan')]])):
            bad = dict(valid, speech_token=value)
            with self.assertRaises(ValueError):
                pilot.validate_feature(bad)


@unittest.skipUnless(importlib.util.find_spec('torch'), 'torch unavailable')
class Publication(unittest.TestCase):
    """Run real finalization control flow with synthetic CPU tensors and no GPU work."""
    def run_synthetic(self, root, cleanup_fails=False, publication_fails=False):
        import torch
        checkpoint = root/'initial.pt'
        checkpoint.write_bytes(b'synthetic')
        prepared = root/'prepared'
        prepared.mkdir()
        (prepared/'config.json').write_text('{}')
        config = dict(checkpoint=str(checkpoint), checkpoint_sha256=pilot.sha256(checkpoint),
                      upstream=str(root/'upstream'), state_dir=str(root/'state'),
                      vendor=str(root/'vendor'), model_root=str(root/'model'))
        args = SimpleNamespace(prepared=prepared, prepared_sha256='mocked',
                               checkpoint=checkpoint, out=root/'run')
        events = []
        @contextmanager
        def lock():
            yield
            events.append('cleanup')
            if cleanup_fails:
                raise PermissionError('synthetic late lock cleanup failure')
        model = SimpleNamespace(state_dict=lambda: {'weight': torch.tensor([1.0])})
        model.to = lambda device: model
        original_write = pilot.write_json
        def write(path, value):
            if path.name.startswith('report'):
                events.append('publication')
                if publication_fails:
                    original_write(path, value)
                    raise OSError('synthetic close failure after writing JSON')
            return original_write(path, value)
        with ExitStack() as stack:
            patches = [patch.object(pilot, 'validate_prepared', return_value=(config, [])),
                       patch.object(pilot, 'experiment_lock', lock),
                       patch.object(pilot, 'offline', return_value=SimpleNamespace(check=lambda: None)),
                       patch.object(pilot, 'native_model', return_value=(model, {})),
                       patch.object(pilot, 'optimize', return_value=dict(successful_updates=20)),
                       patch.object(pilot, 'write_json', write),
                       patch.object(torch.cuda, 'is_available', return_value=True),
                       patch.object(torch.cuda, 'mem_get_info', return_value=(16*1024**3, 24*1024**3)),
                       patch.object(torch.cuda, 'max_memory_reserved', return_value=0),
                       patch.object(torch.cuda, 'set_per_process_memory_fraction'),
                       patch.object(torch.cuda, 'reset_peak_memory_stats'),
                       patch.object(torch.cuda, 'manual_seed_all')]
            for p in patches:
                stack.enter_context(p)
            if cleanup_fails or publication_fails:
                with self.assertRaises((PermissionError, OSError)):
                    pilot.train(args)
                self.assertFalse((args.out/'report.json').exists())
                self.assertTrue((args.out/'failure.json').exists())
                self.assertTrue((args.out/'candidate_step20.pt').exists())
            else:
                pilot.train(args)
                self.assertTrue(pilot.read_json(args.out/'report.json')['success'])
                self.assertFalse((args.out/'failure.json').exists())
                self.assertEqual(events, ['cleanup', 'publication'])

    def test_late_lock_cleanup_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.run_synthetic(Path(tmp), cleanup_fails=True)

    def test_publication_close_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.run_synthetic(Path(tmp), publication_fails=True)

    def test_success_after_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.run_synthetic(Path(tmp))


if __name__ == '__main__':
    unittest.main()
