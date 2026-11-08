import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import re
import os
import io
from contextlib import redirect_stdout
from unittest.mock import patch

from tools import merge_candidate_state as merge
from tools.memory_evidence import scope_candidate, dataset_fingerprint, evidence_revision, guard_output

ROOT = Path(__file__).resolve().parents[1]


def legacy():
    return {'candidate_id': 'old-id', 'kind': 'burst_day', 'title': 'original',
            'date': '2020-01-01', 'excerpts': [{'text': 'original'}],
            'provenance': {'source_records': ['r1']}, 'status': 'pending'}


def scoped(viewpoint='owner', text='original', count=1):
    sources = [{'record_id': 'r' + str(i+1), 'person': 'synthetic', 'viewpoint': viewpoint,
                'text': text, 'provenance': {'extracted_at': 'now'}} for i in range(count)]
    candidate = legacy()
    candidate['provenance']['source_records'] = [s['record_id'] for s in sources]
    return scope_candidate(candidate, 'synthetic', 'synthetic_' + viewpoint, sources)


class ContractTests(unittest.TestCase):
    def test_extractor_real_entry_preserves_all_sources_and_rejects_unspecified_viewpoint(self):
        from tools import extract_memory_candidates as extract
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            inputs = p/'messages.jsonl'
            rows = [{'record_id': 'r'+str(i), 'record_type': 'message', 'content_type': 'text',
                     'person': 'synthetic', 'viewpoint': 'father', 'sender': 'subject',
                     'chat_room': 'direct', 'timestamp': '2020-01-01T12:00:00+08:00',
                     'text': 'synthetic text ' + str(i), 'tier': 2} for i in range(25)]
            inputs.write_text('\n'.join(json.dumps(r) for r in rows), encoding='utf-8')
            output = p/'people/synthetic/memories/scoped.jsonl'
            argv = ['extract', '--person', 'synthetic', '--uif', str(inputs), '--out', str(output),
                    '--keywords', str(ROOT/'tools/persona_keywords.zh.json'), '--kw-groups', '']
            with patch.object(extract, '__file__', str(p/'tools/extract_memory_candidates.py')), patch.object(sys, 'argv', argv), redirect_stdout(io.StringIO()):
                self.assertEqual(extract.main(), 2)
            self.assertFalse(output.exists())
            with patch.object(extract, '__file__', str(p/'tools/extract_memory_candidates.py')), patch.object(sys, 'argv', argv + ['--relationship-id', 'synthetic_father']), redirect_stdout(io.StringIO()):
                self.assertEqual(extract.main(), 0)
            result = [json.loads(line) for line in output.read_text(encoding='utf-8').splitlines()]
            self.assertEqual(len(result), 1)
            self.assertEqual(len(result[0]['evidence_records']), 25)
            self.assertEqual(len(result[0]['provenance']['source_records']), 25)
            dataset_fingerprint(result)

    def test_keyword_groups_do_not_collide(self):
        a = scoped()
        b = copy.deepcopy(a)
        a['group'], b['group'] = 'health', 'family'
        a = scope_candidate(a, a['person'], a['relationship_id'], a['evidence_records'])
        b = scope_candidate(b, b['person'], b['relationship_id'], b['evidence_records'])
        self.assertNotEqual(a['candidate_id'], b['candidate_id'])

    def test_scope_and_complete_evidence(self):
        a = scoped(count=25)
        b = scoped('father', count=25)
        self.assertNotEqual(a['candidate_id'], b['candidate_id'])
        changed = copy.deepcopy(a['evidence_records'])
        changed[-1]['text'] = 'new transcript'
        c = scope_candidate(a, 'synthetic', 'synthetic_owner', changed)
        self.assertEqual(a['candidate_id'], c['candidate_id'])
        self.assertNotEqual(a['evidence_revision'], c['evidence_revision'])
        changed = copy.deepcopy(a['evidence_records'])
        changed[0]['provenance']['extracted_at'] = 'later'
        self.assertEqual(a['evidence_revision'], scope_candidate(a, 'synthetic', 'synthetic_owner', changed)['evidence_revision'])

    def test_dataset_rejects_mixed_duplicate_and_tampering(self):
        for items in ([scoped(), scoped()], [scoped(), scoped('father')], [scoped(), legacy()]):
            with self.assertRaises(ValueError):
                dataset_fingerprint(items)
        c = scoped()
        c['title'] = 'tampered'
        with self.assertRaises(ValueError):
            dataset_fingerprint([c])

    def apply(self, candidate, payload, *, frozen=False):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            source = p/'c.jsonl'
            records = candidate if isinstance(candidate, list) else [candidate]
            source.write_text(''.join(json.dumps(c)+'\n' for c in records), encoding='utf-8')
            original = source.read_bytes()
            decision = p/'d.json'
            decision.write_text(json.dumps(payload), encoding='utf-8')
            command = [sys.executable, str(ROOT/'tools/apply_gate_decisions.py'),
                       '--person', 'synthetic', '--relationship-id', 'synthetic_owner',
                       '--decided-by', 'synthetic-reviewer', '--candidates', str(source),
                       '--decisions', str(decision), '--out', str(p/'out.md')]
            if frozen:
                freeze = p/'freeze.json'
                freeze.write_text(json.dumps({'schema_version': 1, 'person': 'synthetic',
                    'relationship_id': 'synthetic_owner', 'source_sha256': 'wrong' if frozen == 'bad' else hashlib.sha256(original).hexdigest(),
                    'source_dataset': dataset_fingerprint([candidate], legacy=True)}))
                command += ['--legacy-freeze', str(freeze)]
            proc = subprocess.run(command, capture_output=True, text=True)
            if proc.returncode:
                self.assertEqual(source.read_bytes(), original)
                self.assertFalse((p/'out.md').exists())
            return proc.returncode, json.loads(source.read_text(encoding='utf-8').splitlines()[0])

    def payload(self, c):
        return {'v': 2, 'person': c['person'], 'relationship_id': c['relationship_id'],
                'source_dataset': dataset_fingerprint([c]), 'decisions': [
                    {'id': c['candidate_id'], 'evidence_revision': c['evidence_revision'],
                     'action': 'confirm', 'title': 'human title', 'note': 'human note'}]}

    def test_v2_apply_and_user_edits_revision(self):
        c = scoped()
        rc, result = self.apply(c, self.payload(c))
        self.assertEqual(rc, 0)
        self.assertEqual(result['status'], 'confirmed')
        self.assertEqual(result['user_note'], 'human note')
        self.assertEqual(result['user_title'], 'human title')
        self.assertNotEqual(c['evidence_revision'], result['evidence_revision'])
        self.assertEqual(result['decision']['evidence_revision'], result['evidence_revision'])
        self.assertEqual(result['decision']['decided_by'], 'synthetic-reviewer')
        self.assertEqual(result['decision']['based_on_revision'], c['evidence_revision'])
        dataset_fingerprint([result])
        injected = copy.deepcopy(result)
        injected['user_note'] = 'unreviewed injection'
        with self.assertRaises(ValueError):
            dataset_fingerprint([injected])
        merged, _ = merge.merge_candidates([result], [scoped(text='changed')])
        self.assertEqual(merged[0]['status'], 'pending')
        self.assertEqual(merged[0]['previous_versions'][0], result)
        unchanged, _ = merge.merge_candidates([result], [c])
        self.assertEqual(unchanged[0]['user_note'], 'human note')
        self.assertEqual(unchanged[0]['status'], 'confirmed')
        older, _ = merge.merge_candidates(merged, [c])
        self.assertEqual(older[0]['evidence_revision'], merged[0]['evidence_revision'])

    def test_bad_pastes_rejected(self):
        c = scoped()
        payload = self.payload(c)
        variants = []
        for key, value in [('v', 1), ('v', 3), ('relationship_id', 'synthetic_father'), ('source_dataset', 'wrong')]:
            item = copy.deepcopy(payload)
            item[key] = value
            variants.append(item)
        item = copy.deepcopy(payload)
        del item['decisions'][0]['evidence_revision']
        variants.append(item)
        item = copy.deepcopy(payload)
        item['decisions'] *= 2
        variants.append(item)
        for item in variants:
            with self.subTest(payload=item):
                self.assertNotEqual(self.apply(c, item)[0], 0)
        self.assertNotEqual(self.apply(scoped(text='changed'), payload)[0], 0)
        self.assertNotEqual(self.apply([c, c], payload)[0], 0)
        self.assertNotEqual(self.apply([c, legacy()], payload)[0], 0)

    def test_frozen_legacy_keeps_id(self):
        c = legacy()
        payload = {'v': 1, 'source_dataset': dataset_fingerprint([c], legacy=True),
                   'decisions': [{'id': c['candidate_id'], 'action': 'confirm'}]}
        rc, result = self.apply(c, payload, frozen=True)
        self.assertEqual(rc, 0)
        self.assertEqual(result['candidate_id'], c['candidate_id'])
        self.assertNotEqual(self.apply(c, payload)[0], 0)
        self.assertNotEqual(self.apply(c, payload, frozen='bad')[0], 0)

    def test_cross_person_raw_output_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                guard_output(Path(temp)/'people'/'other'/'RAW'/'output.md')

    def test_gate_js_restores_only_matching_scope_and_revision(self):
        from tools.make_gate_page import build_card, render_page
        c = scoped()
        page = render_page('synthetic', [build_card(c, [], 'pending')], dataset_fingerprint([c]), 1)
        script = re.search(r'<script>(.*?)</script>', page, re.S).group(1)
        script = script.replace('initState();\nrender();', '')
        harness = '''
const vm = require('vm');
const assert = require('assert');
let saved = null;
const ctx = {document:{addEventListener(){}}, localStorage:{getItem(){return saved},setItem(k,v){saved=v}}};
vm.createContext(ctx);
vm.runInContext(SCRIPT,ctx);
ctx.showToast = function(){};
const c = ctx.DATA[0];
function draft(revision, dataset=ctx.DATASET, relationship=ctx.RELATIONSHIP){
  return JSON.stringify({v:2,person:'synthetic',relationship_id:relationship,dataset:dataset,
    state:{[c.id]:{action:'confirm',title:'human title',note:'human note',evidence_revision:revision}}});
}
for (const bad of [draft('old'),draft(c.evidence_revision,'old'),draft(c.evidence_revision,ctx.DATASET,'synthetic_father')]) {
  saved=bad;ctx.state={};ctx.initState();assert.equal(ctx.cardState(c.id),'pending');
}
saved=draft(c.evidence_revision);ctx.state={};ctx.initState();assert.equal(ctx.cardState(c.id),'confirm');
const decisions=ctx.computeDecisions();
assert.equal(decisions[0].note,'human note');assert.equal(decisions[0].title,'human title');
assert.equal(decisions[0].evidence_revision,c.evidence_revision);
ctx.saveDraft();assert.equal(JSON.parse(saved).relationship_id,'synthetic_owner');
console.log(JSON.stringify({v:2,person:ctx.SLUG,relationship_id:ctx.RELATIONSHIP,source_dataset:ctx.DATASET,decisions}));
'''.replace('SCRIPT', json.dumps(script))
        proc = subprocess.run(['node', '-e', harness], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        rc, confirmed = self.apply(c, json.loads(proc.stdout))
        self.assertEqual(rc, 0)
        dataset_fingerprint([confirmed])
        from tools.build_chat_knowledge import build_memories
        entry = build_memories([confirmed], 'synthetic')['entries'][0]
        self.assertEqual(entry['title'], 'human title')
        self.assertEqual(entry['note'], 'human note')


class RegressionTests(unittest.TestCase):
    def test_changed_body_does_not_inherit_confirmation(self):
        old = legacy()
        old['status'] = 'confirmed'
        new = legacy()
        new['excerpts'][0]['text'] = 'changed'
        result, _ = merge.merge_candidates([old], [new])
        self.assertEqual(result[0]['status'], 'pending')
        self.assertEqual(result[0]['previous_versions'][0], old)

    def test_new_unverified_confirmed_is_reset(self):
        new = legacy()
        new['status'] = 'confirmed'
        result, _ = merge.merge_candidates([], [new])
        self.assertEqual(result[0]['status'], 'pending')

    def test_unfrozen_legacy_paste_rejected_without_writes(self):
        from tools.apply_gate_decisions import compute_source_dataset
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            source = p / 'c.jsonl'
            original = json.dumps(legacy()) + '\n'
            source.write_text(original, encoding='utf-8')
            decision = p / 'd.json'
            decision.write_text(json.dumps({'v': 1, 'source_dataset': compute_source_dataset([legacy()]),
                                           'decisions': [{'id': 'old-id', 'action': 'confirm'}]}))
            proc = subprocess.run([sys.executable, str(ROOT / 'tools/apply_gate_decisions.py'),
                                   '--person', 'synthetic', '--candidates', str(source),
                                   '--decisions', str(decision), '--out', str(p/'out.md')],
                                  capture_output=True, text=True)
            self.assertNotEqual(proc.returncode, 0)
            self.assertEqual(source.read_text(encoding='utf-8'), original)
            self.assertFalse((p/'out.md').exists())


class ReviewRegressionTests(unittest.TestCase):
    def test_merge_drops_new_unreviewed_title_and_note(self):
        from tools.memory_evidence import decision_is_current
        for status, action in [('confirmed', 'confirm'), ('rejected', 'reject')]:
            old = scoped()
            old.update(status=status, decision={'action': action, 'person': old['person'],
                'relationship_id': old['relationship_id'], 'evidence_revision': old['evidence_revision'],
                'decided_by': 'synthetic-reviewer', 'decided_at': '2020-01-01'})
            new = scoped()
            new.update(user_title='unreviewed title', user_note='unreviewed note')
            new['evidence_revision'] = evidence_revision(new)
            result, _ = merge.merge_candidates([old], [new])
            self.assertNotIn('user_title', result[0])
            self.assertNotIn('user_note', result[0])
            self.assertTrue(decision_is_current(result[0]))
            self.assertEqual(result[0]['evidence_revision'], old['evidence_revision'])

    def test_apply_preflight_preserves_all_files(self):
        for mode in ('file_ancestor', 'directory_output', 'freeze_alias'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temp:
                p = Path(temp)
                is_legacy = mode == 'freeze_alias'
                c = legacy() if is_legacy else scoped()
                source, decision, freeze = p/'c.jsonl', p/'d.json', p/'freeze.json'
                source.write_text(json.dumps(c)+'\n', encoding='utf-8')
                ds = dataset_fingerprint([c], legacy=is_legacy)
                payload = {'v': 1, 'source_dataset': ds, 'decisions': [{'id': c['candidate_id'], 'action': 'confirm'}]} if is_legacy else ContractTests().payload(c)
                decision.write_text(json.dumps(payload), encoding='utf-8')
                freeze.write_text(json.dumps({'schema_version': 1, 'person': 'synthetic',
                    'relationship_id': 'synthetic_owner', 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                    'source_dataset': ds}), encoding='utf-8')
                output = source/'memories.md' if mode == 'file_ancestor' else freeze if is_legacy else p/'directory'
                if mode == 'directory_output':
                    output.mkdir()
                before = {f: f.read_bytes() for f in (source, decision, freeze)}
                command = [sys.executable, '-X', 'utf8', str(ROOT/'tools/apply_gate_decisions.py'),
                    '--person', 'synthetic', '--relationship-id', 'synthetic_owner',
                    '--decided-by', 'synthetic-reviewer', '--candidates', str(source),
                    '--decisions', str(decision), '--out', str(output)]
                if is_legacy:
                    command += ['--legacy-freeze', str(freeze)]
                proc = subprocess.run(command, capture_output=True, text=True)
                self.assertNotEqual(proc.returncode, 0)
                self.assertEqual({f: f.read_bytes() for f in before}, before)
                self.assertEqual({f: hashlib.sha256(f.read_bytes()).hexdigest() for f in before},
                                 {f: hashlib.sha256(data).hexdigest() for f, data in before.items()})

    def test_gate_cannot_overwrite_candidate(self):
        for mode in ('same', 'case', 'hardlink'):
            with self.subTest(mode=mode):
                self.check_gate_alias(mode)

    def check_gate_alias(self, mode):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)/'c.jsonl'
            source.write_text(json.dumps(scoped())+'\n', encoding='utf-8')
            before = source.read_bytes()
            target = source
            if mode == 'case':
                target = source.with_name('C.JSONL')
            elif mode == 'hardlink':
                target = source.with_name('alias.jsonl')
                os.link(source, target)
            proc = subprocess.run([sys.executable, '-X', 'utf8', str(ROOT/'tools/make_gate_page.py'),
                '--person', 'synthetic', '--relationship-id', 'synthetic_owner',
                '--candidates', str(source), '--out', str(target)], capture_output=True, text=True)
            self.assertNotEqual(proc.returncode, 0)
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), hashlib.sha256(before).hexdigest())

    def test_merge_cli_allows_old_inplace_but_protects_new_input(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root/'people/synthetic/memories'
            folder.mkdir(parents=True)
            old, new = folder/'old.jsonl', folder/'new.jsonl'
            old.write_text(json.dumps(scoped())+'\n', encoding='utf-8')
            new.write_text(json.dumps(scoped(text='changed'))+'\n', encoding='utf-8')
            before = {f: f.read_bytes() for f in (old, new)}
            argv = ['merge', '--person', 'synthetic', '--relationship-id', 'synthetic_owner',
                    '--old', str(old), '--new', str(new)]
            with patch.object(merge, '__file__', str(root/'tools/merge_candidate_state.py')), patch.object(sys, 'argv', argv+['--out', str(new)]), redirect_stdout(io.StringIO()):
                self.assertEqual(merge.main(), 2)
            self.assertEqual({f: f.read_bytes() for f in before}, before)
            with patch.object(merge, '__file__', str(root/'tools/merge_candidate_state.py')), patch.object(sys, 'argv', argv+['--out', str(old)]), redirect_stdout(io.StringIO()):
                self.assertEqual(merge.main(), 0)
            self.assertEqual(new.read_bytes(), before[new])
            self.assertEqual(json.loads(old.read_text(encoding='utf-8'))['status'], 'pending')

    def test_merge_cli_stage_cannot_replace_old_input(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root/'people/synthetic/memories'
            folder.mkdir(parents=True)
            old, new, output = folder/'merged.jsonl.part', folder/'new.jsonl', folder/'merged.jsonl'
            old.write_text(json.dumps(scoped())+'\n', encoding='utf-8')
            new.write_text(json.dumps(scoped(text='changed'))+'\n', encoding='utf-8')
            output.write_text('existing output must survive\n', encoding='utf-8')
            before = {f: f.read_bytes() for f in (old, new, output)}
            argv = ['merge', '--person', 'synthetic', '--relationship-id', 'synthetic_owner',
                    '--old', str(old), '--new', str(new), '--out', str(output)]
            with patch.object(merge, '__file__', str(root/'tools/merge_candidate_state.py')), patch.object(sys, 'argv', argv), redirect_stdout(io.StringIO()):
                result = merge.main()
            self.assertEqual(result, 2)
            self.assertTrue(all(f.exists() for f in before))
            self.assertEqual({f: f.read_bytes() for f in before}, before)
            self.assertEqual({f: hashlib.sha256(f.read_bytes()).hexdigest() for f in before},
                             {f: hashlib.sha256(data).hexdigest() for f, data in before.items()})

    def test_preflight_ancestor_and_links(self):
        from tools.memory_evidence import preflight_outputs
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            source = p/'source.json'
            source.write_text('source')
            for target in (source/'child', p, p/'new'/'..'/'SOURCE.JSON'):
                with self.subTest(target=target), self.assertRaises(ValueError):
                    preflight_outputs([target], [source])
            link = p/'alias.json'
            os.link(source, link)
            with self.assertRaises(ValueError):
                preflight_outputs([link], [], inplace_inputs=[source])

    def test_extract_cli_cannot_overwrite_uif(self):
        from tools import extract_memory_candidates as extract
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root/'people/synthetic/memories/input.jsonl'
            source.parent.mkdir(parents=True)
            row = {'record_id': 'r1', 'record_type': 'message', 'content_type': 'text',
                   'person': 'synthetic', 'viewpoint': 'owner', 'sender': 'subject',
                   'chat_room': 'direct', 'timestamp': '2020-01-01T12:00:00+08:00', 'text': 'original'}
            source.write_text(json.dumps(row)+'\n', encoding='utf-8')
            before = source.read_bytes()
            argv = ['extract', '--person', 'synthetic', '--uif', str(source), '--out', str(source),
                    '--keywords', str(ROOT/'tools/persona_keywords.zh.json'), '--kw-groups', '']
            with patch.object(extract, '__file__', str(root/'tools/extract_memory_candidates.py')), patch.object(sys, 'argv', argv), redirect_stdout(io.StringIO()):
                self.assertEqual(extract.main(), 2)
            self.assertEqual(source.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
