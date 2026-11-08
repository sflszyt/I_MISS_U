"""合成正式提交及真实构建合同；不读取生产 state 或 people。"""
import copy
import json
import sqlite3
import tempfile
import unittest
import uuid
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from tests.mobile_review_fixture import sources
from tools import build_mobile_review as package_builder
from tools import build_training_manifest as training
from tools.mobile_review_store import Store, encode
from tools.viewpoint_manifest import digest, read_json, read_jsonl, sha256
from tools.audit_voice_training_inputs import PLAN_FIELDS


class ReviewedLanguageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        ab, prep = sources(self.root)
        self.package = package_builder.Package(package_builder.build(ab, prep, self.root/'package'))
        self.state = self.root/'state'
        self.store = Store(self.package, self.state)
        self.items = self.store.tasks['source']['items']
        # 真构建器按身份排序；临时根会改变排序，不能假设某编号必是 train。
        train_items = [item for item in self.items if item['split'] == 'train']
        self.unapproved = train_items[6]['id']
        self.mandarin = train_items[2]['id']
        values = self.store.session()['drafts']['source']['values']
        values['reviewer'] = 'synthetic-only'
        for index, item in enumerate(self.items):
            s = values['items'][item['id']]
            s.update(speaker=True, single=True, transcript=True, transcript_confirmed_text=s['text'],
                     quality=True, duration=True, include=True, disposition='review')
            if item['id'] == self.unapproved:
                s.update(transcript=False, transcript_confirmed_text=None)
        self.source = self.submit('source', values)
        values = self.store.session()['drafts']['language']['values']
        for index, item in enumerate(self.items):
            values['items'][item['id']]['language'] = 'mandarin' if item['id'] == self.mandarin else 'wu'
        self.language = self.submit('language', values)
        summary = read_json(self.root/'training-authoritative/summary.json')
        dataset = next(Path(e['path']) for e in summary['inputs'] if Path(e['path']).name == 'dataset.json')
        self.training = self.root/'reviewed'
        training.build(person='mama', datasets=[dataset], out=self.training,
                       asr_drafts=self.root/'dataset-chain/drafts.json',
                       asr_mapping=self.root/'dataset-chain/mapping.json',
                       reviews=self.state/'submissions'/(self.source['receipt_id']+'.json'))
        self.plan = self.root/'plan.json'
        rows = read_jsonl(self.training/'eligible.jsonl')
        plan = dict(schema_version=1, source_build=str(self.training),
                    source_eligible_sha256=sha256(self.training/'eligible.jsonl'), ready_for_training=False)
        for split in ('train', 'validation'):
            plan[split] = [{k:r[k] for k in PLAN_FIELDS} for r in rows if r['split'] == split]
        package_builder.write_json(self.plan, plan)

    def submit(self, task, values):
        session = self.store.session()
        saved = self.store.save(task, dict(package_revision=self.package.revision,
                                base_revision=session['drafts'][task]['revision'],
                                request_id=str(uuid.uuid4()), values=values), 'synthetic-owner')
        latest = session['latest_receipts'][task]
        return self.store.submit(task, dict(package_revision=self.package.revision,
                                 draft_revision=saved['revision'], request_id=str(uuid.uuid4()),
                                 supersedes=latest['receipt_id'] if latest else None), 'synthetic-owner')

    def build(self, out=None):
        from tools.build_reviewed_language_inputs import build
        return build(self.package.path, self.state, self.training, self.plan, out or self.root/'out')

    def mutate(self, rid, column, change, sidecar=True):
        with closing(sqlite3.connect(self.state/'state.sqlite3')) as db, db:
            value = json.loads(db.execute('SELECT '+column+' FROM receipts WHERE id=?', (rid,)).fetchone()[0])
            change(value)
            raw = encode(value)
            db.execute('UPDATE receipts SET '+column+'=? WHERE id=?', (raw, rid))
        if sidecar:
            folder = dict(receipt='receipts', export='submissions', audit='audit')[column]
            (self.state/folder/(rid+'.json')).write_bytes((raw+'\n').encode('utf-8'))

    def resign_export(self, rid):
        export = read_json(self.state/'submissions'/(rid+'.json'))
        self.mutate(rid, 'receipt', lambda d: d.update(payload_sha256=digest(export)))
        with closing(sqlite3.connect(self.state/'state.sqlite3')) as db, db:
            raw = db.execute('SELECT receipt FROM receipts WHERE id=?', (rid,)).fetchone()[0]
            db.execute('UPDATE requests SET response=? WHERE receipt=?', (raw, rid))

    def sync_request(self, rid):
        with closing(sqlite3.connect(self.state/'state.sqlite3')) as db, db:
            raw, audit = db.execute('SELECT receipt,audit FROM receipts WHERE id=?', (rid,)).fetchone()
            receipt, audit = json.loads(raw), json.loads(audit)
            request_id = db.execute('SELECT id FROM requests WHERE receipt=?', (rid,)).fetchone()[0]
            body = dict(package_revision=audit['package_revision'], draft_revision=audit['draft_revision'],
                        request_id=request_id, supersedes=receipt['supersedes'])
            fingerprint = digest([receipt['task_id'], 'submit', body, audit['identity']])
            db.execute('UPDATE requests SET response=?,fingerprint=? WHERE receipt=?', (raw, fingerprint, rid))

    def test_full_chain_two_languages_and_validation(self):
        before = {str(p):sha256(p) for p in self.root.rglob('*') if p.is_file()}
        with patch.object(Store, '__init__', side_effect=AssertionError('consumer must be read only')):
            out = self.build()
        report = read_json(out/'report.json')
        self.assertFalse(report['ready_for_training'])
        self.assertFalse(report['training_started'])
        self.assertEqual(report['legacy_samples_added'], 0)
        self.assertEqual(report['language_counts']['labeled'], 12)
        self.assertEqual(len(read_jsonl(out/'wu/train.jsonl')), 9)
        self.assertEqual(len(read_jsonl(out/'mandarin/train.jsonl')), 1)
        self.assertEqual(len(read_jsonl(out/'wu/validation.jsonl')), 1)
        self.assertEqual(read_jsonl(out/'mandarin/validation.jsonl'), [])
        excluded = read_jsonl(out/'excluded.jsonl')
        self.assertEqual(len(excluded), 1)
        self.assertIn('not_source_approved', excluded[0]['exclusion_reasons'])
        row = read_jsonl(out/'mandarin/train.jsonl')[0]
        self.assertEqual(row['language'], 'unknown')
        self.assertEqual(row['effective_language'], 'mandarin')
        self.assertTrue(Path(row['audio_file']).is_absolute())
        self.assertTrue(row['text'])
        self.assertEqual(row['actual_duration_ms'], 3000)
        self.assertEqual(before, {p:sha256(Path(p)) for p in before})

    def test_replacement_is_snapshot_and_ambiguous_excluded(self):
        values = self.store.session()['drafts']['language']['values']
        for index, label in enumerate(('unlabeled', 'mixed', 'unknown')):
            values['items'][self.items[index]['id']]['language'] = label
        self.language = self.submit('language', values)
        out = self.build()
        reasons = {reason for row in read_jsonl(out/'excluded.jsonl') for reason in row['exclusion_reasons']}
        self.assertTrue({'unlabeled', 'mixed', 'unknown', 'not_source_approved'} <= reasons)
        self.assertEqual(read_json(out/'report.json')['language_counts']['labeled'], 11)

    def test_replaced_source_requires_fresh_reviewed_build(self):
        self.source = self.submit('source', self.store.session()['drafts']['source']['values'])
        with self.assertRaises(ValueError):
            self.build()
        self.language = self.submit('language', self.store.session()['drafts']['language']['values'])
        with self.assertRaises(ValueError):
            self.build()

    def test_language_identity_or_payload_tampering(self):
        rid = self.language['receipt_id']
        original = (self.state/'submissions'/(rid+'.json')).read_bytes()
        other_split = 'train' if json.loads(original)['labels'][0]['split'] == 'validation' else 'validation'
        for field, value in [('record_id', 'unknown'), ('audio_sha256', '0'*64), ('revision', 'bad'),
                             ('split', other_split), ('language', 'illegal'), ('note', 'changed'),
                             ('decided_at', 'yesterday')]:
            with self.subTest(field=field):
                self.mutate(rid, 'export', lambda d: d['labels'][0].update({field:value}))
                with self.assertRaises(ValueError):
                    self.build()
                with closing(sqlite3.connect(self.state/'state.sqlite3')) as db, db:
                    db.execute('UPDATE receipts SET export=? WHERE id=?', (original.decode().rstrip('\n'), rid))
                (self.state/'submissions'/(rid+'.json')).write_bytes(original)
        self.mutate(rid, 'export', lambda d: d['labels'].append(copy.deepcopy(d['labels'][0])))
        with self.assertRaises(ValueError):
            self.build()

    def test_request_fingerprint_rejected(self):
        with closing(sqlite3.connect(self.state/'state.sqlite3')) as db, db:
            db.execute('UPDATE requests SET fingerprint=? WHERE receipt=?', ('bad', self.language['receipt_id']))
        with self.assertRaises(ValueError):
            self.build()

    def test_sidecar_bytes_rejected(self):
        path = self.state/'audit'/(self.language['receipt_id']+'.json')
        path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaises(ValueError):
            self.build()

    def test_audit_values_rejected(self):
        self.mutate(self.language['receipt_id'], 'audit',
                    lambda d: d['values']['items'][self.items[0]['id']].update(language='mandarin'))
        with self.assertRaises(ValueError):
            self.build()

    def test_self_consistent_overlay_forgery_rejected(self):
        # 重签 payload 与回包仍不能代替 audit 的逐条人审值。
        rid = self.language['receipt_id']
        self.mutate(rid, 'export', lambda d: d['labels'][0].update(language='mandarin'))
        self.resign_export(rid)
        with self.assertRaisesRegex(ValueError, 'audited human values'):
            self.build()

    def test_source_reference_forgery_rejected(self):
        rid = self.language['receipt_id']
        self.mutate(rid, 'export', lambda d: d.update(source_review_receipt='0'*32))
        self.resign_export(rid)
        with self.assertRaises(ValueError):
            self.build()

    def test_draft_only_change_does_not_invalidate_formal_snapshot(self):
        from tools import build_reviewed_language_inputs as m
        original = m.approved_inputs
        def changing(*args):
            result = original(*args)
            session = self.store.session()
            values = session['drafts']['language']['values']
            values['items'][self.items[0]['id']]['language'] = 'unknown'
            self.store.save('language', dict(package_revision=self.package.revision,
                            base_revision=session['drafts']['language']['revision'],
                            request_id=str(uuid.uuid4()), values=values), 'synthetic-owner')
            return result
        with patch.object(m, 'approved_inputs', side_effect=changing):
            out = self.build()
        self.assertEqual(read_json(out/'report.json')['language_counts']['wu'], 11)

    def test_formal_latest_change_during_build_rejected(self):
        from tools import build_reviewed_language_inputs as m
        original = m.approved_inputs
        def changing(*args):
            result = original(*args)
            self.submit('language', self.store.session()['drafts']['language']['values'])
            return result
        with patch.object(m, 'approved_inputs', side_effect=changing), self.assertRaises(ValueError):
            self.build()
        self.assertFalse((self.root/'out/report.json').exists())

    def test_cross_task_and_broken_chain_rejected(self):
        for parent, error in ((self.source['receipt_id'], 'cross-task'), ('0'*32, 'broken receipt chain'),
                              (self.language['receipt_id'], 'receipt chain cycle')):
            self.mutate(self.language['receipt_id'], 'receipt', lambda d: d.update(supersedes=parent))
            self.sync_request(self.language['receipt_id'])
            with self.assertRaisesRegex(ValueError, error):
                self.build()

    def test_sidecar_change_before_baseline_rejected(self):
        from tools import build_reviewed_language_inputs as m
        original = m.hashes
        first = True
        def changing(paths):
            nonlocal first
            if first:
                first = False
                path = self.state/'audit'/(self.language['receipt_id']+'.json')
                path.write_bytes(path.read_bytes()+b' ')
            return original(paths)
        with patch.object(m, 'hashes', side_effect=changing), self.assertRaisesRegex(ValueError, 'sidecar bytes mismatch'):
            self.build()
        self.assertFalse((self.root/'out/report.json').exists())

    def test_overlap_and_existing_output_rejected(self):
        for out in (self.state/'out', self.training/'out', self.package.path/'out', self.root, self.root/'RAW/out'):
            with self.subTest(out=out), self.assertRaises(ValueError):
                self.build(out)

    def test_input_change_during_build_rejected_without_report(self):
        from tools import build_reviewed_language_inputs as m
        original = m.approved_inputs
        def changing(*args):
            result = original(*args)
            self.plan.write_text(self.plan.read_text()+' ')
            return result
        with patch.object(m, 'approved_inputs', side_effect=changing), self.assertRaises(ValueError):
            self.build()
        self.assertFalse((self.root/'out/report.json').exists())

    def test_link_output_rejected(self):
        link = self.root/'linked'
        try:
            link.symlink_to(self.state, target_is_directory=True)
        except OSError:
            self.skipTest('host does not permit synthetic symlink creation')
        with self.assertRaises(ValueError):
            self.build(link/'out')


if __name__ == '__main__':
    unittest.main()
