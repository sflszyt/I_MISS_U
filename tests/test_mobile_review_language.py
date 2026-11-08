import copy
import json
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from tests.mobile_review_fixture import fixture
from tools.build_mobile_review import Package
from tools.mobile_review_store import Store, ReviewError
from tools.viewpoint_manifest import digest
from tests import test_mobile_review_server as server_tests


class LanguageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.package = Package(fixture(self.root))
        self.store = Store(self.package, self.root/'state')

    def body(self, task='language'):
        draft = self.store.session()['drafts'][task]
        return dict(package_revision=self.package.revision, base_revision=draft['revision'],
                    request_id=str(uuid.uuid4()), values=draft['values'])

    def submission(self, task='language', supersedes=None):
        return dict(package_revision=self.package.revision,
                    draft_revision=self.store.session()['drafts'][task]['revision'],
                    request_id=str(uuid.uuid4()), supersedes=supersedes)

    def label(self, labels=('wu',)):
        body = self.body()
        for state, label in zip(body['values']['items'].values(), labels):
            state.update(language=label, note='synthetic note')
        self.store.save('language', body, 'owner')
        return body

    def test_derived_task_defaults_and_reopen(self):
        before = (self.package.path/'manifest.json').read_bytes()
        session = self.store.session()
        self.assertEqual([t['id'] for t in session['tasks']], ['ab','source','language'])
        for source, language in zip(session['tasks'][1]['items'], session['tasks'][2]['items']):
            self.assertEqual(language, {k:source[k] for k in ('id','number','audio','split')})
        self.assertIsNone(session['latest_receipts']['language'])
        self.assertEqual(set(session['drafts']['language']['values']), {'position','items'})
        self.assertTrue(all(s == dict(language='unlabeled', note='') for s in session['drafts']['language']['values']['items'].values()))
        self.label()
        self.assertEqual(Store(self.package, self.root/'state').session(), self.store.session())
        self.assertEqual(before, (self.package.path/'manifest.json').read_bytes())

    def test_strict_values(self):
        mutations = [lambda b:b['values'].update(reviewer='x'),
                     lambda b:b['values'].update(position=True),
                     lambda b:b['values'].update(position=12),
                     lambda b:b['values']['items'].update(external=dict(language='wu',note='')),
                     lambda b:b['values']['items'].pop(next(iter(b['values']['items']))),
                     lambda b:next(iter(b['values']['items'].values())).update(speaker=True),
                     lambda b:next(iter(b['values']['items'].values())).update(note=1),
                     lambda b:next(iter(b['values']['items'].values())).update(note='x'*2001)]
        for value in ('shanghai', '', None, [], {}, True, 1):
            mutations.append(lambda b,v=value:next(iter(b['values']['items'].values())).update(language=v))
        for mutate in mutations:
            body = self.body(); mutate(body)
            with self.assertRaises(ReviewError) as caught:
                self.store.save('language', body, 'owner')
            self.assertEqual(caught.exception.status, 422)
        with self.assertRaises(ReviewError):
            self.store.submit('language', self.submission(), 'owner')

    def test_overlay_bindings_counts_and_partial_replacement(self):
        self.label(('wu','mandarin','mixed','unknown'))
        first = self.store.submit('language', self.submission(), 'owner')
        self.assertEqual(first['counts'], dict(wu=1,mandarin=1,mixed=1,unknown=1,pending=8,labeled=4))
        export = self.store.receipt(first['receipt_id'], True)
        self.assertEqual(export['decision_kind'], 'source_language_annotation_only')
        self.assertFalse(export['training_approval']); self.assertNotIn('reviews', export)
        self.assertEqual(export['package_revision'], self.package.revision)
        self.assertIsNone(export['source_review_receipt']); self.assertIsNone(export['source_review_payload_sha256'])
        for label, candidate in zip(export['labels'], self.package.manifest['candidates'].values()):
            for key in ('record_id','audio_sha256','revision','split'):
                self.assertEqual(label[key], candidate[key])
            self.assertEqual(label['decided_at'], first['submitted_at'])
        self.assertEqual(first['payload_sha256'], digest(export))
        self.label(('unknown',)*12)
        with self.assertRaises(ReviewError): self.store.submit('language', self.submission(), 'owner')
        second = self.store.submit('language', self.submission(supersedes=first['receipt_id']), 'owner')
        self.assertEqual(second['counts']['unknown'], 12)
        labels = self.store.receipt(second['receipt_id'], True)['labels']
        self.assertEqual(labels[-1]['split'], 'validation')
        self.assertTrue(all(l['language']=='unknown' for l in labels))
        self.assertEqual(self.store.receipt(first['receipt_id'], True), export)
        self.assertEqual(self.store.session()['drafts']['source']['revision'], 0)

    def test_latest_formal_source_reference_and_audit(self):
        source = self.body('source'); source['values']['reviewer'] = 'Synthetic'
        next(iter(source['values']['items'].values()))['disposition'] = 'exclude'
        self.store.save('source', source, 'owner')
        first = self.store.submit('source', self.submission('source'), 'owner')
        self.label(('mixed',))
        second = self.store.submit('source', self.submission('source', first['receipt_id']), 'owner')
        source = self.body('source'); source['values']['reviewer'] = 'Unsubmitted edit'
        self.store.save('source', source, 'owner')
        result = self.store.submit('language', self.submission(), 'owner')
        export = self.store.receipt(result['receipt_id'], True)
        audit = json.loads((self.root/'state'/'audit'/(result['receipt_id']+'.json')).read_text(encoding='utf-8'))
        for payload in (export, audit):
            self.assertEqual(payload['source_review_receipt'], second['receipt_id'])
            self.assertEqual(payload['source_review_payload_sha256'], second['payload_sha256'])
        self.assertEqual(audit['identity'], 'owner')
        self.assertEqual(audit['values'], self.body()['values'])

    def test_idempotency_lost_ack_and_concurrent_writers(self):
        saved = self.label()
        self.assertEqual(self.store.save('language', saved, 'owner')['revision'], 1)
        with self.assertRaises(ReviewError): self.store.save('language', saved, 'another-owner')
        request = self.submission()
        with patch.object(self.store, 'materialize', side_effect=OSError('synthetic loss')):
            with self.assertRaises(OSError): self.store.submit('language', request, 'owner')
        receipt = self.store.submit('language', request, 'owner')
        self.assertEqual(receipt, self.store.submit('language', request, 'owner'))
        stores = [self.store, Store(self.package, self.root/'state')]
        bodies = [self.body(), self.body()]
        def save(pair):
            store, body = pair
            try: return store.save('language', body, 'owner')['revision']
            except ReviewError as error: return error.status
        with ThreadPoolExecutor(2) as pool:
            self.assertEqual(sorted(pool.map(save, zip(stores,bodies))), [2,409])

    def test_existing_two_task_state_is_preserved_byte_for_byte(self):
        # 旧版表结构相同；构造只有两任务、已有保存与正式提交的合成状态。
        with self.store.connect() as db:
            db.execute("DELETE FROM drafts WHERE task='language'")
        for task in ('ab','source'):
            body = self.body(task)
            if task=='ab':
                next(iter(body['values']['items'].values()))['preference'] = 'B'
            else:
                body['values']['reviewer'] = 'Synthetic'
                next(iter(body['values']['items'].values()))['disposition'] = 'exclude'
            self.store.save(task, body, 'owner')
            self.store.submit(task, self.submission(task), 'owner')
        tables = ('drafts','receipts','requests','latest','metadata')
        with self.store.connect() as db:
            before = {t:db.execute('SELECT * FROM '+t).fetchall() for t in tables}
        files = {p:p.read_bytes() for folder in ('receipts','submissions','audit')
                 for p in (self.root/'state'/folder).glob('*.json')}
        reopened = Store(self.package, self.root/'state')
        session = reopened.session()
        with reopened.connect() as db:
            for table in tables:
                query = 'SELECT * FROM '+table
                if table=='drafts': query += " WHERE task!='language'"
                self.assertEqual(db.execute(query).fetchall(), before[table])
        self.assertEqual(files, {p:p.read_bytes() for p in files})
        self.assertEqual(session['drafts']['language']['revision'], 0)
        self.assertIsNone(session['latest_receipts']['language'])


@unittest.skipUnless(server_tests.JWT_AVAILABLE, 'PyJWT crypto unavailable; run mobile-review-venv')
class LanguageServerTests(unittest.TestCase):
    setUp = server_tests.ServerTests.setUp
    stop = server_tests.ServerTests.stop
    request = server_tests.ServerTests.request

    def test_language_route_auth_and_roundtrip(self):
        session = json.loads(self.request()[2])
        save = dict(package_revision=session['package_revision'], base_revision=0,
                    request_id=str(uuid.uuid4()), values=session['drafts']['language']['values'])
        next(iter(save['values']['items'].values()))['language'] = 'mandarin'
        submit = dict(package_revision=session['package_revision'], draft_revision=1,
                      request_id=str(uuid.uuid4()), supersedes=None)
        h = {'Origin':self.config['public_origin'], 'X-Review-CSRF':session['csrf_token']}
        for action, method, body in (('draft','PUT',save),('submit','POST',submit)):
            url = '/review/api/tasks/language/'+action
            self.assertEqual(self.request(url,method,body,h,auth=False)[0], 401)
            self.assertEqual(self.request(url,method,body,dict(h,Origin='https://other.invalid'))[0], 403)
            self.assertEqual(self.request(url,method,body,dict(h,**{'X-Review-CSRF':'invalid'}))[0], 403)
            self.assertEqual(self.request(url,method,body,dict(h,Host='other.invalid'))[0], 403)
            status, _, raw = self.request(url,method,body,h)
            self.assertEqual(status, 200)
        receipt = json.loads(raw)
        url = '/review/api/receipts/'+receipt['receipt_id']+'/export'
        self.assertEqual(self.request(url,auth=False)[0], 401)
        export = json.loads(self.request(url)[2])
        self.assertEqual(export['labels'][0]['language'], 'mandarin')
        self.assertNotIn('reviews', export)


if __name__ == '__main__':
    unittest.main()
