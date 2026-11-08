import copy
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from tests.mobile_review_fixture import fixture
from tools.build_mobile_review import Package
from tools.mobile_review_store import Store, ReviewError


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.store=Store(Package(fixture(self.root)),self.root/'state')

    def body(self,task='ab'):
        draft=self.store.session()['drafts'][task]
        return dict(package_revision=self.store.package.revision,base_revision=draft['revision'],request_id=str(uuid.uuid4()),values=draft['values'])

    def submit_body(self,revision=1,supersedes=None):
        return dict(package_revision=self.store.package.revision,draft_revision=revision,request_id=str(uuid.uuid4()),supersedes=supersedes)

    def judged(self):
        body=self.body()
        next(iter(body['values']['items'].values()))['preference']='A'
        self.store.save('ab',body,'owner')

    def test_defaults_and_task_isolation(self):
        s=self.store.session()
        self.assertEqual(len(s['tasks'][0]['items']),14)
        for item in s['drafts']['source']['values']['items'].values():
            self.assertFalse(item['include']);self.assertFalse(item['speaker']);self.assertFalse(item['transcript'])
        self.store.save('ab',self.body(),'owner')
        self.assertEqual(self.store.session()['drafts']['source']['revision'],0)

    def test_save_idempotency_and_conflict(self):
        body=self.body()
        first=self.store.save('ab',body,'owner')
        self.assertEqual(self.store.save('ab',body,'owner'),first)
        body['values']['position']=1
        with self.assertRaises(ReviewError) as c:self.store.save('ab',body,'owner')
        self.assertEqual(c.exception.status,409)

    def test_concurrent_revision(self):
        bodies=[self.body(),self.body()]
        def save(body):
            try:return self.store.save('ab',body,'owner')['revision']
            except ReviewError as e:return e.status
        with ThreadPoolExecutor(2) as pool:
            self.assertEqual(sorted(pool.map(save,bodies)),[1,409])

    def test_partial_export_loss_retry_and_replacement(self):
        self.judged();body=self.submit_body()
        original=self.store.write_immutable
        def fail(path,content):
            if path.parent.name=='submissions':raise OSError('synthetic failure')
            return original(path,content)
        with patch.object(self.store,'write_immutable',side_effect=fail):
            with self.assertRaises(OSError):self.store.submit('ab',body,'owner')
        self.assertEqual(len(list((self.root/'state'/'receipts').glob('*.json'))),1)
        receipt=self.store.submit('ab',body,'owner')
        self.assertEqual(receipt,self.store.submit('ab',body,'owner'))
        export=self.store.receipt(receipt['receipt_id'],True)
        self.assertEqual(len(export['choices']),14);self.assertFalse(export['training_approval'])
        with self.assertRaises(ReviewError):self.store.submit('ab',self.submit_body(),'owner')
        replacement=self.store.submit('ab',self.submit_body(supersedes=receipt['receipt_id']),'owner')
        self.assertEqual(replacement['supersedes'],receipt['receipt_id'])
        self.assertEqual(self.store.receipt(receipt['receipt_id']),receipt)

    def test_source_contract_split_and_transcript(self):
        body=self.body('source');body['values']['reviewer']='测试审核者'
        states=list(body['values']['items'].values())
        for s in (states[0],states[-1]):
            s.update(include=True,disposition='review',speaker=True,single=True,transcript=True,quality=True,duration=True,transcript_confirmed_text=s['text'])
        states[1]['disposition']='exclude'
        self.store.save('source',body,'owner')
        receipt=self.store.submit('source',self.submit_body(),'owner')
        self.assertEqual(receipt['counts'],dict(train=1,validation=1,pending=9,excluded=1))
        export=self.store.receipt(receipt['receipt_id'],True)
        self.assertEqual(len(export['reviews']),2)
        self.assertTrue(all(r['decided_by']=='测试审核者' for r in export['reviews']))
        body=self.body('source');next(iter(body['values']['items'].values()))['text']='改变文字'
        with self.assertRaises(ReviewError):self.store.save('source',body,'owner')

    def test_strict_fields_and_empty_submit(self):
        for mutate in (lambda b:b.update(extra=1),lambda b:b.update(base_revision=True),lambda b:b['values'].update(position=-1),lambda b:next(iter(b['values']['items'].values())).update(played_a=1)):
            body=self.body();mutate(body)
            with self.assertRaises(ReviewError):self.store.save('ab',body,'owner')
        with self.assertRaises(ReviewError):self.store.submit('ab',self.submit_body(0),'owner')
        body=self.body();body['package_revision']='old'
        with self.assertRaises(ReviewError):self.store.save('ab',body,'owner')

    def test_incomplete_included_source_remains_pending(self):
        body=self.body('source');body['values']['reviewer']='Synthetic reviewer'
        items=list(body['values']['items'].values())
        items[0].update(include=True,disposition='review',speaker=True,single=True,transcript=True,
                        transcript_confirmed_text=items[0]['text'],quality=True,duration=False)
        items[1].update(include=True,disposition='review',speaker=True,single=True,transcript=False,quality=True)
        items[2]['disposition']='exclude'
        self.store.save('source',body,'owner')
        receipt=self.store.submit('source',self.submit_body(),'owner')
        self.assertEqual(receipt['counts'],dict(train=0,validation=0,pending=11,excluded=1))
        self.assertEqual(self.store.receipt(receipt['receipt_id'],True)['reviews'],[])


if __name__=='__main__':unittest.main()
