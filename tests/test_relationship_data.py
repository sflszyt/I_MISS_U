import importlib
import json
import unittest
import re
import subprocess
from pathlib import Path
from tests import test_import_wechat_viewpoint as fixtures


def run_retrieval_js(filename, records, transcripts):
    source = (Path(__file__).parents[1] / 'tools' / filename).read_text(encoding='utf-8')
    names = ['scoreText','retrieveSnippets','retrieveKnowledge','buildRetrievalBlock']
    functions = '\n'.join(re.search(r'^function ' + name + r'\([^\n]*\) \{.*?^\}', source, re.M | re.S).group() for name in names)
    script = functions + '\nconst records=' + json.dumps(records) + ';const transcripts=' + json.dumps(transcripts) + ';\n'
    script += "console.log(buildRetrievalBlock(retrieveSnippets(['synthetic'],records,{}).concat(retrieveKnowledge(['synthetic'],[],transcripts,{}).transcripts)));"
    result = subprocess.run(['node','-'],input=script,text=True,encoding='utf-8',capture_output=True)
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout


class RelationshipTests(unittest.TestCase):
    setUp = fixtures.ImportViewpointTests.setUp
    row = fixtures.ImportViewpointTests.row
    refresh = fixtures.ImportViewpointTests.refresh
    run_import = fixtures.ImportViewpointTests.run_import

    def test_same_second_source_order_and_missing_timestamp(self):
        dataset = self.run_import()
        out = self.root / 'ordered'
        self.builder().build(person='mama',datasets=[dataset],viewer='father',out=out)
        examples = [json.loads(x) for x in (out / 'relationship/examples.jsonl').read_text().splitlines()]
        self.assertEqual(examples[0]['context'][0]['sender_person_id'], 'father')
        self.assertEqual(json.loads((out / 'relationship/rhythm.json').read_text())['reply_latency']['sample_count'], 1)

    def test_unknown_timestamp_preserved_without_context(self):
        self.rows[1]['ts'] = None
        self.refresh()
        dataset = self.run_import()
        out = self.root / 'unknown'
        self.builder().build(person='mama',datasets=[dataset],viewer='father',out=out)
        examples = [json.loads(x) for x in (out / 'relationship/examples.jsonl').read_text().splitlines()]
        self.assertIsNone(examples[0]['target']['timestamp'])
        self.assertEqual(examples[0]['context'], [])
        self.assertEqual(json.loads((out / 'relationship/rhythm.json').read_text())['reply_latency']['sample_count'], 0)

    def test_new_messages_reach_final_js_prompt_with_sources(self):
        dataset = self.run_import()
        out = self.root / 'js'
        self.builder().build(person='mama',datasets=[dataset],viewer='father',out=out)
        rows = json.loads((out / 'relationship/messages.json').read_text())
        mother = next(r for r in rows if r['content_type']=='text' and r['sender_person_id']=='mama')
        for page in ['build_chat_page.py','build_companion_page.py']:
            result = run_retrieval_js(page, rows, [])
            for value in ['mama_father', 'mama', 'father', mother['record_id'], mother['provenance']['source_file_sha256'], 'Tier-2']:
                self.assertIn(value, result)

    def test_explicit_language_context(self):
        from tools.build_chat_context import scoped_context
        base = dict(schema_version=2,person='mama',viewer='owner',relationship_id='mama_owner',
                    counts={'selected':1},coverage_status='partial')
        self.assertEqual(scoped_context(dict(base,language='wu'))['language'],'wu')
        self.assertEqual(scoped_context(dict(base,language='mandarin'))['language'],'mandarin')
        with self.assertRaises(ValueError):
            scoped_context(dict(base,viewer='father',relationship_id='mama_father',language='wu'))
    def builder(self):
        return importlib.import_module('tools.build_relationship_data')

    def test_relationship_build_is_scoped_and_offline(self):
        dataset = self.run_import()
        out = self.root / 'build'
        self.builder().build(person='mama', datasets=[dataset], viewer='father', out=out)
        manifest = json.loads((out / 'build.json').read_text())
        self.assertEqual(manifest['language'], 'mandarin')
        selected = [json.loads(x) for x in (out / 'relationship/messages.jsonl').read_text().splitlines()]
        self.assertEqual(len(selected), 4)
        self.assertTrue(all(r['relationship_id'] == 'mama_father' for r in selected))
        self.assertEqual(len(json.loads((out / 'local_archive/messages.json').read_text())), 6)
        examples = [json.loads(x) for x in (out / 'relationship/examples.jsonl').read_text().splitlines()]
        self.assertEqual(len(examples), 1)
        self.assertEqual(examples[0]['target']['sender_person_id'], 'mama')
        all_text = '\n'.join(p.read_text(encoding='utf-8') for p in (out / 'relationship').rglob('*') if p.is_file())
        self.assertNotIn('wx_m', all_text)
        self.assertNotIn('sender_wxid', all_text)
        self.assertTrue((out / 'relationship/gate.html').exists())

    def test_invalid_viewer_and_empty_selection_fail_without_output(self):
        dataset = self.run_import()
        for viewer in ['other', 'owner']:
            out = self.root / viewer
            with self.assertRaises(ValueError):
                self.builder().build(person='mama', datasets=[dataset], viewer=viewer, out=out)
            self.assertFalse(out.exists())

    def test_legacy_requires_explicit_complete_mapping(self):
        with self.assertRaises(ValueError):
            self.builder().adapt_legacy(self.legacy, {})

    def test_raw_and_existing_outputs_refused(self):
        dataset = self.run_import()
        for out in [self.root / 'people/mama/raw/new', dataset.parent]:
            with self.assertRaises(ValueError):
                self.builder().build(person='mama', datasets=[dataset], viewer='father', out=out)

    def test_v2_memories_do_not_trust_status(self):
        from tools.build_chat_knowledge import build_memories
        from tools.memory_evidence import scope_candidate
        c = scope_candidate({'kind':'text','title':'sample','excerpts':[{'text':'sample'}]},
                            'mama', 'mama_father', [{'record_id':'a','person':'mama','viewpoint':'father'}])
        c['status'] = 'confirmed'
        self.assertEqual(build_memories([c], 'mama')['entries'], [])

    def test_legacy_owner_ids_preserved_and_father_excluded(self):
        from tools.viewpoint_manifest import sha256
        dataset = self.run_import()
        rows = [{'record_id':'old1', 'person':'mama','viewpoint':'owner','sender_wxid':'wx_m',
                 'chat_room':'direct-old','record_type':'message','source':'wechat','tier':2,
                 'content_type':'text','text':'owner only','timestamp':'2020-01-01T12:00:00+08:00'}]
        self.legacy.write_text(json.dumps(rows[0]), encoding='utf-8')
        mapping = {'schema_version':1,'person':'mama','viewpoint':'owner','source_batch_id':'old',
                   'source_sha256':sha256(self.legacy),'senders':{'wx_m':'mama'},
                   'conversations':{'direct-old':{'conversation_id':'old-direct','kind':'direct','participant_ids':['mama','owner']}}}
        path = self.root / 'mapping.json'
        fixtures.dump(path, mapping)
        out = self.root / 'owner-build'
        self.builder().build(person='mama', datasets=[dataset], viewer='owner', out=out,
                             legacy_uif=self.legacy, legacy_registry=path, language='wu')
        self.assertEqual(json.loads((out / 'relationship/chat_context.json').read_text())['language'], 'wu')
        selected = json.loads((out / 'relationship/messages.json').read_text())
        self.assertEqual([r['record_id'] for r in selected], ['old1'])
        self.assertEqual(selected[0]['relationship_id'], 'mama_owner')
        mapping['conversations'] = {}
        with self.assertRaises(ValueError): self.builder().adapt_legacy(self.legacy, mapping)

    def test_package_has_no_full_archive_or_private_manifest(self):
        dataset = self.run_import()
        out = self.root / 'build'
        self.builder().build(person='mama', datasets=[dataset], viewer='father', out=out)
        package = self.root / 'package'
        self.builder().package_relationship(out / 'build.json', package, 'mama')
        self.assertFalse((package / 'build.json').exists())
        self.assertFalse((package / 'local_archive').exists())
        self.assertFalse((package / 'sessions').exists())
        (out / 'relationship/chat_context.json').write_text('{}')
        with self.assertRaises(ValueError):
            self.builder().package_relationship(out / 'build.json', self.root / 'bad-package', 'mama')
        self.assertFalse((self.root / 'bad-package').exists())

    def test_speaker_gating_and_actual_attribution(self):
        from tools.build_chat_knowledge import build_transcript_entries
        row = dict(schema_version=2, record_id='voice', person='mama', speaker_id='father',
                   speaker_status='confirmed', single_speaker=True, transcript_status='corrected',
                   source_kind='real_recording', text='father words', relationship_id='mama_father',
                   viewpoint='father', evidence_revision='revision')
        result = build_transcript_entries([row], 'voice')
        self.assertEqual(result[0]['speaker_id'], 'father')
        self.assertFalse(result[0]['is_subject'])
        self.assertEqual(build_transcript_entries([dict(row, speaker_id='unknown')], 'voice'), [])
        self.assertEqual(build_transcript_entries([dict(row, transcript_status='draft')], 'voice'), [])

    def test_memory_overlay_requires_current_selected_evidence(self):
        from tools.build_relationship_data import write_jsonl
        dataset = self.run_import()
        first = self.root / 'first'
        self.builder().build(person='mama',datasets=[dataset],viewer='father',out=first)
        candidates = [json.loads(x) for x in (first / 'relationship/candidates.jsonl').read_text().splitlines()]
        c = candidates[0]
        c['status'] = 'confirmed'
        c['decision'] = dict(action='confirm',person='mama',relationship_id='mama_father',
                             evidence_revision=c['evidence_revision'],decided_by='tester',decided_at='2026-10-20')
        overlay = self.root / 'memories.jsonl'
        write_jsonl(overlay, candidates)
        second = self.root / 'second'
        self.builder().build(person='mama',datasets=[dataset],viewer='father',out=second,memory_candidates=overlay)
        entries = json.loads((second / 'relationship/memories.json').read_text())['entries']
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['evidence_revision'], c['evidence_revision'])
        self.assertEqual(entries[0]['relationship_id'], 'mama_father')
        c['excerpts'][0]['text'] = 'tampered'
        write_jsonl(overlay, candidates)
        with self.assertRaises(ValueError):
            self.builder().build(person='mama',datasets=[dataset],viewer='father',out=self.root / 'bad',memory_candidates=overlay)
        self.assertFalse((self.root / 'bad').exists())


if __name__ == '__main__':
    unittest.main()
