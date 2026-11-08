"""Named listening batches use synthetic media and isolated temporary state only."""
import copy
import json
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from tests.mobile_review_fixture import fixture, config, credentials, wav
from tools.build_mobile_review import Package, write_json, inventory
from tools.viewpoint_manifest import digest, sha256
from tools.mobile_review_store import Store, ReviewError

BASE = '/review/batches/voice-pilot-20261023/'


def comparison_fixture(root):
    from tools import compare_voice_training as upstream
    from tools.viewpoint_manifest import sha256
    root.mkdir(parents=True)
    training = root.parent/'training'
    training.mkdir()
    checkpoint = training/'candidate_step20.pt'
    checkpoint.write_bytes(b'synthetic checkpoint, never loaded')
    steps = [dict(step=i+1, loss=1., gradient_norm=1., lr=1e-6, epoch=i//10, batch_index=i%10) for i in range(20)]
    step_path = training/'steps.jsonl'
    step_path.write_text('\n'.join(json.dumps(x) for x in steps), encoding='utf-8')
    report = dict(success=True, successful_updates=20, optimizer_steps=[20], weights_changed=True,
                  holdout_used_for_training=False, holdout_loss_computed=False, live_voice_changed=False,
                  checkpoint=str(checkpoint), checkpoint_sha256=sha256(checkpoint), step_log_sha256=sha256(step_path))
    write_json(training/'report.json', report)
    frozen = {str(p):sha256(p) for p in (training/'report.json', step_path, checkpoint)}
    manifest = dict(run_id='123456789abcdef0123456789abcdef0', tier=3, targets=upstream.TARGETS, seeds=list(upstream.SEEDS),
                    settings=dict(pad_ms=200, fade_ms=30, speed=1., fp16=False, stream=False, retries=0, timeout_seconds=180),
                    frozen=frozen, reference={}, reference_provenance={}, holdout={}, limitations=upstream.LIMITATIONS,
                    implementation_sha256=sha256(Path(upstream.__file__)))
    write_json(root/'manifest.json', manifest)
    rows = []
    for i,item in enumerate(upstream.schedule()):
        row = dict(item, id=f'take-{i+1:02}', status='ok', reason=None, elapsed_seconds=1.)
        row.update(upstream.save_wav(root/(row['id']+'.wav'), [0.01*(i+1),-0.01*(i+1)]*800, 24000))
        rows.append(row)
    (root/'results.jsonl').write_text('\n'.join(json.dumps(r) for r in rows), encoding='utf-8')
    upstream.material(root, rows, manifest['run_id'])
    write_json(root/'summary.json', dict(success=True, planned=24, successful=24, run_id=manifest['run_id'], formal_approval=False, live_voice_changed=False))
    evaluations = {c:dict(loss=1., evaluations=1, eval=True, no_grad=True, seed=1986, missing_keys=[], unexpected_keys=[], checkpoint_metadata={}) for c in ('baseline','candidate')}
    write_json(root/'evaluations.json', evaluations)
    for c,v in evaluations.items():
        write_json(root/(c+'-evaluation.json'), v)
    write_json(root/'common-dependencies.json', {'synthetic':'metadata only'})
    return root


class BuilderTests(unittest.TestCase):
    def test_builder_exists_and_validates_upstream_chain(self):
        import importlib.util
        self.assertIsNotNone(importlib.util.find_spec('tools.build_training_listening_review'))
        from tools.build_training_listening_review import build
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = comparison_fixture(root/'comparison')
            before = inventory(source)
            out = build(source, root/'package', BASE)
            self.assertEqual(before, inventory(source))
            p = Package(out)
            self.assertEqual([t['id'] for t in p.tasks], ['ab'])
            self.assertEqual(len(p.tasks[0]['items']), 12)
            self.assertEqual(len(p.manifest['media']), 24)
            public = json.dumps(p.tasks)
            for key in ('baseline','candidate','take-','seed','condition','checkpoint'):
                self.assertNotIn(key, public)
            self.assertTrue(all(i['audio_a'].startswith(BASE+'audio/') for i in p.tasks[0]['items']))
            (out/'frozen'/'answer-key.json').write_text('[]', encoding='utf-8')
            with self.assertRaises(ValueError): p.verify()

    def test_builder_rejects_tamper_and_overlaps(self):
        from tools.build_training_listening_review import build
        for mutation in ('missing','duplicate','seed','target','wav','swap-key','html','implementation','report','base','overlap','extra-wav'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = comparison_fixture(root/'comparison')
                rows = [json.loads(line) for line in (source/'results.jsonl').read_text().splitlines()]
                if mutation == 'missing': rows.pop()
                elif mutation == 'duplicate': rows[-1] = rows[0]
                elif mutation == 'seed': rows[0]['seed'] = 999
                elif mutation == 'target': rows[0]['target_id'] = 'invented'
                elif mutation == 'wav': (source/rows[0]['wav']).write_bytes(b'RIFFbroken')
                elif mutation == 'swap-key':
                    key = json.loads((source/'answer-key.json').read_text())
                    key[0]['A'],key[0]['B'] = key[0]['B'],key[0]['A']
                    write_json(source/'answer-key.json',key)
                elif mutation == 'html': (source/'listen.html').write_text('empty')
                elif mutation == 'implementation':
                    value = json.loads((source/'manifest.json').read_text(encoding='utf-8'))
                    value['implementation_sha256'] = '0'*64
                    write_json(source/'manifest.json', value)
                elif mutation == 'report': (root/'training'/'report.json').write_text('{}')
                elif mutation == 'extra-wav': (source/'extra.wav').write_bytes(b'RIFFextra')
                (source/'results.jsonl').write_text('\n'.join(json.dumps(r) for r in rows), encoding='utf-8')
                out = source/'nested' if mutation == 'overlap' else root/'package'
                base = '/review/batches/../escape/' if mutation == 'base' else BASE
                with self.assertRaises(ValueError): build(source, out, base)
                self.assertFalse(out.exists())

    def test_builder_detects_input_change_during_copy_and_raw_output(self):
        import shutil
        from tools.build_training_listening_review import build
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = comparison_fixture(root/'comparison')
            with self.assertRaises(ValueError): build(source, root/'raw'/'package', BASE)
            original = shutil.copyfile
            changed = False
            def mutate(src, dst):
                nonlocal changed
                result = original(src, dst)
                if not changed:
                    changed = True
                    (source/'summary.json').write_text('{}', encoding='utf-8')
                return result
            with patch('tools.build_training_listening_review.shutil.copyfile', side_effect=mutate):
                with self.assertRaises(ValueError): build(source, root/'package', BASE)
            with self.assertRaises(ValueError): Package(root/'package')


def ab_fixture(root):
    path = fixture(root)
    value = json.loads((path/'manifest.json').read_text(encoding='utf-8'))
    value['tasks'] = value['tasks'][:1]
    value['tasks'][0]['items'] = value['tasks'][0]['items'][:12]
    value['candidates'] = {}
    used = set()
    for item in value['tasks'][0]['items']:
        for field in ('audio_a', 'audio_b'):
            used.add(item[field].split('/')[-1][:-4])
            item[field] = item[field].replace('/review/', BASE)
    value['media'] = {k:v for k,v in value['media'].items() if k in used}
    # Deliberately collide with root media IDs, but not with their bytes.
    first = next(iter(value['media'].values()))
    wav(path/first['file'], 500)
    first['sha256'] = sha256(path/first['file'])
    value['package_revision'] = digest({k:v for k,v in value.items() if k != 'package_revision'})
    write_json(path/'manifest.json', value)
    return path


class BatchStoreTests(unittest.TestCase):
    def test_ab_only_replay_reload_replacement_and_export_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = Package(ab_fixture(root))
            store = Store(package, root/'state')
            session = store.session()
            self.assertEqual(set(session['drafts']), {'ab'})
            values = session['drafts']['ab']['values']
            next(iter(values['items'].values()))['preference'] = 'B'
            save = dict(package_revision=package.revision, base_revision=0, request_id=str(uuid.uuid4()), values=values)
            self.assertEqual(store.save('ab', save, 'owner'), store.save('ab', save, 'owner'))
            submit = dict(package_revision=package.revision, draft_revision=1, request_id=str(uuid.uuid4()), supersedes=None)
            original = store.write_immutable
            def fail(path, content):
                if path.parent.name == 'submissions':
                    raise OSError('synthetic export interruption')
                return original(path, content)
            with patch.object(store, 'write_immutable', side_effect=fail):
                with self.assertRaises(OSError):
                    store.submit('ab', submit, 'owner')
            store = Store(package, root/'state')
            receipt = store.submit('ab', submit, 'owner')
            self.assertEqual(receipt, store.submit('ab', submit, 'owner'))
            self.assertEqual(receipt['counts'], {'judged':1, 'unheard':11})
            before = inventory(root/'state')
            with self.assertRaises(ReviewError):
                store.submit('source', submit, 'owner')
            self.assertEqual(before, inventory(root/'state'))
            replacement = store.submit('ab', dict(submit, request_id=str(uuid.uuid4()), supersedes=receipt['receipt_id']), 'owner')
            self.assertEqual(replacement['supersedes'], receipt['receipt_id'])
            exported = store.receipt(receipt['receipt_id'], True)
            self.assertEqual(len(exported['choices']), 12)
            self.assertFalse(exported['training_approval'])
            for forbidden in ('candidate', 'baseline', 'checkpoint', 'source_take', 'frozen'):
                self.assertNotIn(forbidden, json.dumps(exported))


try:
    from tools.mobile_review_server import create_server, validate_config
    import jwt
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False


@unittest.skipUnless(JWT_AVAILABLE, 'PyJWT crypto unavailable')
class BatchServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        fixture(self.root)
        self.new = self.root/'new'
        ab_fixture(self.new)
        self.config = config(self.root)
        self.config['batches'] = {'voice-pilot-20261023':dict(package_dir=str(self.new/'package'), state_dir=str(self.new/'state'), title='New listening batch')}
        self.key, _, self.token = credentials()

    def start(self):
        self.server = create_server(self.config, test_keys={'synthetic-key':self.key.public_key()})
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, path, method='GET', body=None, headers=None, auth=True):
        import http.client
        h = {'Host':'127.0.0.1:0'}
        if auth:
            h['Cf-Access-Jwt-Assertion'] = self.token
        if body is not None:
            body = json.dumps(body).encode()
            h['Content-Type'] = 'application/json'
        h.update(headers or {})
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        c.request(method, path, body, h)
        r = c.getresponse()
        result = r.status, r.read()
        c.close()
        return result

    def test_routes_csrf_receipts_requests_and_old_state_are_isolated(self):
        old_store = Store(Package(self.root/'package'), self.root/'state')
        old_values = old_store.session()['drafts']['ab']['values']
        next(iter(old_values['items'].values()))['preference'] = 'same'
        old_store.save('ab', dict(package_revision=old_store.package.revision, base_revision=0,
                                request_id=str(uuid.uuid4()), values=old_values), 'synthetic-owner')
        old_store.submit('ab', dict(package_revision=old_store.package.revision, draft_revision=1,
                                  request_id=str(uuid.uuid4()), supersedes=None), 'synthetic-owner')
        self.start()
        old = json.loads(self.request('/review/api/session')[1])
        new = json.loads(self.request(BASE+'api/session')[1])
        self.assertEqual([t['id'] for t in old['tasks']], ['ab','source','language'])
        self.assertEqual([t['id'] for t in new['tasks']], ['ab'])
        self.assertEqual(new['batch'], dict(id='voice-pilot-20261023', title='New listening batch', base_path=BASE))
        self.assertEqual(old['batch']['id'], 'default')
        self.assertNotEqual(old['csrf_token'], new['csrf_token'])
        old_inventory = inventory(self.root/'state')
        values = new['drafts']['ab']['values']
        next(iter(values['items'].values()))['preference'] = 'A'
        body = dict(package_revision=new['package_revision'], base_revision=0, request_id=str(uuid.uuid4()), values=values)
        headers = {'Origin':self.config['public_origin'], 'X-Review-CSRF':old['csrf_token']}
        self.assertEqual(self.request(BASE+'api/tasks/ab/draft', 'PUT', body, headers)[0], 403)
        headers['X-Review-CSRF'] = new['csrf_token']
        first = self.request(BASE+'api/tasks/ab/draft', 'PUT', body, headers)
        self.assertEqual(first[0], 200)
        self.assertEqual(first, self.request(BASE+'api/tasks/ab/draft', 'PUT', body, headers))
        submit = dict(package_revision=new['package_revision'], draft_revision=1, request_id=str(uuid.uuid4()), supersedes=None)
        status, raw = self.request(BASE+'api/tasks/ab/submit', 'POST', submit, headers)
        self.assertEqual(status, 200)
        rid = json.loads(raw)['receipt_id']
        self.assertEqual(self.request('/review/api/receipts/'+rid)[0], 404)
        self.assertEqual(self.request(BASE+'api/receipts/'+rid+'/export')[0], 200)
        # The same client request UUID may be used independently in the old store.
        old_body = dict(body, package_revision=old['package_revision'], base_revision=1, values=old['drafts']['ab']['values'])
        headers['X-Review-CSRF'] = old['csrf_token']
        self.assertEqual(old_inventory, inventory(self.root/'state'))
        self.assertEqual(self.request('/review/api/tasks/ab/draft', 'PUT', old_body, headers)[0], 200)
        self.assertEqual(json.loads(self.request(BASE+'api/session')[1])['drafts']['ab']['revision'], 1)
        for word in ('baseline','candidate','checkpoint','source_take','source_hashes','answer-key'):
            self.assertNotIn(word, json.dumps(new))

    def test_unknown_paths_media_head_and_auth(self):
        self.start()
        s = json.loads(self.request(BASE+'api/session')[1])
        audio = s['tasks'][0]['items'][0]['audio_a']
        self.assertNotEqual(self.request(audio)[1], self.request(audio.replace(BASE, '/review/'))[1])
        for path in (BASE, BASE+'api/session', audio):
            self.assertEqual(self.request(path, auth=False)[0], 401)
        self.assertEqual(self.request(audio, 'HEAD', headers={'Range':'bytes=0-43'}, auth=False)[0], 401)
        self.assertEqual(self.request(audio, headers={'Range':'bytes=0-43'})[0], 206)
        self.assertEqual(self.request(BASE)[0], 200)
        for path in (BASE+'manifest.json', BASE+'frozen/answer-key.json', BASE+'../api/session', BASE+'%2e%2e/api/session', '/review/batches/unknown/api/session', BASE+'api/receipts/'+'0'*32):
            self.assertEqual(self.request(path)[0], 404, path)
        # Old source media has no corresponding entry in the new AB-only store.
        old = json.loads(self.request('/review/api/session')[1])
        source_audio = old['tasks'][1]['items'][0]['audio'].replace('/review/', BASE)
        self.assertEqual(self.request(source_audio)[0], 404)

    def test_invalid_batch_paths_rejected_before_any_state_write(self):
        for mutation in ('id','relative','overlap','package_overlap','title','extra'):
            cfg = copy.deepcopy(self.config)
            entry = cfg['batches']['voice-pilot-20261023']
            if mutation == 'id':
                cfg['batches']['../bad'] = cfg['batches'].pop('voice-pilot-20261023')
            elif mutation == 'relative': entry['state_dir'] = 'relative'
            elif mutation == 'overlap': entry['state_dir'] = str(self.root/'state'/'nested')
            elif mutation == 'package_overlap': entry['state_dir'] = str(self.root/'package'/'new')
            elif mutation == 'title': entry['title'] = ''
            else: entry['auth'] = 'off'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                create_server(cfg, test_keys={'synthetic-key':self.key.public_key()})
            self.assertFalse((self.root/'state').exists())
            self.assertFalse((self.new/'state').exists())


if __name__ == '__main__':
    unittest.main()
