import importlib
import json
import unittest
import wave
import re
import subprocess
import copy
from tests import test_import_wechat_viewpoint as fixtures
from tests.test_relationship_data import run_retrieval_js


class TrainingTests(unittest.TestCase):
    setUp = fixtures.ImportViewpointTests.setUp
    row = fixtures.ImportViewpointTests.row
    refresh = fixtures.ImportViewpointTests.refresh
    run_import = fixtures.ImportViewpointTests.run_import

    def test_duration_pending_reason_without_review(self):
        from tools.build_training_manifest import exclusion_reasons
        self.assertIn('duration_unresolved', exclusion_reasons(dict(audio_valid=True,duration_check='mismatch'), None))

    def test_actual_training_to_knowledge_to_final_js(self):
        from tools import build_training_manifest as m
        from tools.build_chat_knowledge import build_transcript_entries
        self.valid_audio()
        self.rows[3]['media'][0]['duration_check'] = 'mismatch'
        self.refresh()
        dataset = self.run_import()
        first = self.root / 'first'
        m.build(person='mama',datasets=[dataset],out=first)
        c = next(json.loads(x) for x in (first / 'candidates.jsonl').read_text().splitlines() if json.loads(x)['audio_valid'])
        review = dict(record_id=c['record_id'],audio_sha256=c['audio_sha256'],revision=c['revision'],speaker_id='mama',
                      speaker_status='confirmed',transcript_status='corrected',text='synthetic corrected text',
                      source_kind='real_recording',single_speaker=True,quality_status='approved',duration_approved=True,
                      decided_by='tester',decided_at='2026-10-20')
        fixture = self.root / 'reviews.json'
        fixtures.dump(fixture,dict(schema_version=1,reviews=[review]))
        second = self.root / 'second'
        m.build(person='mama',datasets=[dataset],out=second,reviews=fixture)
        verified = [json.loads(x) for x in (second / 'verified_transcripts.jsonl').read_text().splitlines()]
        entries = build_transcript_entries(verified,'voice')
        self.assertEqual(len(entries),1)
        e = entries[0]
        self.assertEqual(e['text'],'synthetic corrected text')
        for page in ['build_chat_page.py','build_companion_page.py']:
            result = run_retrieval_js(page, [], entries)
            for value in [c['record_id'], 'mama_father', 'mama', 'father', e['evidence_revision'],c['provenance']['source_file_sha256'], e['date']]:
                self.assertIn(value,result)
            self.assertEqual(run_retrieval_js(page,[],[dict(e,speaker_id='unknown')]).strip(),'')
            self.assertEqual(run_retrieval_js(page,[],[dict(e,single_speaker=False)]).strip(),'')
        from tools.build_relationship_data import build as relationship_build
        relation = self.root / 'relationship'
        relationship_build(person='mama',datasets=[dataset],viewer='father',out=relation,
                           language='mandarin',verified_transcripts=second / 'verified_transcripts.jsonl')
        consumed = json.loads((relation / 'relationship/transcripts.json').read_text())['entries']
        self.assertEqual(consumed[0]['evidence_revision'], e['evidence_revision'])
        for page in ['build_chat_page.py','build_companion_page.py']:
            final_prompt = run_retrieval_js(page, [], consumed)
            for value in [e['text'], e['record_id'], e['evidence_revision'], 'mama_father',
                          e['provenance']['source_file_sha256'], 'speaker=mama']:
                self.assertIn(value, final_prompt)

    def test_verified_transcript_tampering_rejected_before_writes(self):
        from tools.build_relationship_data import build as relationship_build, write_jsonl
        self.test_actual_training_to_knowledge_to_final_js()
        original = json.loads((self.root / 'second/verified_transcripts.jsonl').read_text().splitlines()[0])
        dataset = self.root / 'people/mama/normalized/wechat/father/batch1/dataset.json'
        for mode in ['text', 'missing_review', 'audio_hash', 'speaker', 'segment', 'single', 'quality']:
            with self.subTest(mode=mode):
                changed = copy.deepcopy(original)
                if mode == 'text': changed['text'] = 'unreviewed replacement'
                if mode == 'missing_review':
                    changed.pop('review', None)
                    changed['evidence_revision'] = 'not-a-hash'
                if mode == 'audio_hash': changed['audio_sha256'] = '0'*64
                if mode == 'speaker': changed['speaker_id'] = 'father'
                if mode == 'segment': changed['segment_end_ms'] = 500
                if mode == 'single': changed['single_speaker'] = False
                if mode == 'quality': changed['quality_status'] = 'pending'
                path = self.root / ('bad-' + mode + '.jsonl')
                write_jsonl(path, [changed])
                out = self.root / ('bad-' + mode)
                with self.assertRaises(ValueError):
                    relationship_build(person='mama',datasets=[dataset],viewer='father',out=out,verified_transcripts=path)
                self.assertFalse(out.exists())

    def test_self_consistent_forgery_still_checked_against_dataset_media(self):
        from tools.build_relationship_data import build as relationship_build, write_jsonl
        from tools.transcript_evidence import make_verified_transcript
        from tools.viewpoint_manifest import digest
        self.test_actual_training_to_knowledge_to_final_js()
        original = json.loads((self.root / 'second/verified_transcripts.jsonl').read_text().splitlines()[0])
        dataset = self.root / 'people/mama/normalized/wechat/father/batch1/dataset.json'
        for mode in ['audio', 'segment', 'speaker', 'source', 'timestamp', 'position']:
            with self.subTest(mode=mode):
                base = copy.deepcopy(original['candidate_evidence'])
                review = copy.deepcopy(original['review'])
                if mode == 'audio':
                    base.update(audio_sha256='0'*64,dedup_group='0'*64,audio_file='audio/'+('0'*64)+'.wav',split='validation')
                    review['audio_sha256'] = base['audio_sha256']
                if mode == 'segment':
                    base.update(segment_end_ms=500,actual_duration_ms=500)
                if mode == 'speaker':
                    base['person'] = 'father'
                    review['speaker_id'] = 'father'
                if mode == 'source': base['provenance']['source_file_sha256'] = '0'*64
                if mode == 'timestamp': base['timestamp'] = '2001-01-01T00:00:00+08:00'
                if mode == 'position': base['source_row_number'] += 1
                review['revision'] = digest(base)
                forged = make_verified_transcript(dict(base,revision=digest(base),review=review,exclusion_reasons=[]))
                path = self.root / ('forged-' + mode + '.jsonl')
                write_jsonl(path, [forged])
                out = self.root / ('forged-' + mode)
                with self.assertRaises(ValueError):
                    relationship_build(person='mama',datasets=[dataset],viewer='father',out=out,verified_transcripts=path)
                self.assertFalse(out.exists())

    def test_missing_native_ids_full_asr_review_relationship_chain(self):
        from tools import build_training_manifest as m
        from tools.build_relationship_data import build as relationship_build
        from tools.viewpoint_manifest import sha256
        self.valid_audio()
        del self.rows[3]['server_id']
        self.rows[3]['source_row'] = 'fallback-a'
        positions = [(4, None, 'a.wav')]
        for offset, native in enumerate([None, 0, '0', '']):
            name = 'fallback-%d.wav' % offset
            audio = self.source / 'records/conversation-1' / name
            with wave.open(str(audio), 'wb') as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
                w.writeframes(b'\x01\x00' * (16001 + offset))
            row = copy.deepcopy(self.rows[3])
            row.update(server_id=native, source_row='fallback-%d' % offset)
            row['media'] = [dict(kind='voice',path=name,format='WAV',duration_check='within_tolerance')]
            self.rows.append(row)
            positions.append((len(self.rows), native, name))
        self.refresh()
        dataset = self.run_import()
        drafts, mapping = self.root / 'drafts.json', self.root / 'map.json'
        fixtures.dump(drafts, [dict(id=str(i),asr_text='synthetic draft '+str(i)) for i,_,_ in positions])
        fixtures.dump(mapping, [dict(id=str(i),source_file='records/conversation-1/messages.json',source_row_number=i,
                                    native_id=native,wav_sha256=sha256(self.source / 'records/conversation-1' / name))
                               for i,native,name in positions])
        mapping_rows = json.loads(mapping.read_text())
        mapping_rows[0].pop('native_id')
        fixtures.dump(mapping, mapping_rows)
        first = self.root / 'fallback-pending'
        m.build(person='mama',datasets=[dataset],out=first,asr_drafts=drafts,asr_mapping=mapping)
        candidates = [json.loads(x) for x in (first / 'candidates.jsonl').read_text().splitlines() if json.loads(x)['audio_valid']]
        self.assertEqual({c['source_row_number'] for c in candidates}, {i for i,_,_ in positions})
        reviews = [dict(record_id=c['record_id'],audio_sha256=c['audio_sha256'],revision=c['revision'],speaker_id='mama',
                        speaker_status='confirmed',transcript_status='corrected',text='synthetic corrected '+str(c['source_row_number']),
                        source_kind='real_recording',single_speaker=True,quality_status='approved',duration_approved=True,
                        decided_by='tester',decided_at='2026-10-20') for c in candidates]
        review_path = self.root / 'reviews.json'
        fixtures.dump(review_path,dict(schema_version=1,reviews=reviews))
        second = self.root / 'fallback-reviewed'
        m.build(person='mama',datasets=[dataset],out=second,asr_drafts=drafts,asr_mapping=mapping,reviews=review_path)
        relation = self.root / 'fallback-relationship'
        relationship_build(person='mama',datasets=[dataset],viewer='father',out=relation,
                           verified_transcripts=second / 'verified_transcripts.jsonl')
        entries = json.loads((relation / 'relationship/transcripts.json').read_text())['entries']
        self.assertEqual(len(entries),5)
        for page in ['build_chat_page.py','build_companion_page.py']:
            self.assertIn('synthetic corrected',run_retrieval_js(page,[],entries))
        invalid_mapping = json.loads(mapping.read_text())
        invalid_mapping[0]['source_row_number'] = 1
        fixtures.dump(mapping,invalid_mapping)
        with self.assertRaises(ValueError):
            m.build(person='mama',datasets=[dataset],out=self.root / 'wrong-position',asr_drafts=drafts,asr_mapping=mapping)
        self.assertFalse((self.root / 'wrong-position').exists())

    def test_fallback_duplicate_and_wrong_source_row_rejected(self):
        from tools.transcript_evidence import locate_source_row
        from tools.viewpoint_manifest import load_dataset
        self.valid_audio()
        self.rows[3].pop('server_id')
        self.rows[3]['source_row'] = 'original-source-row'
        self.refresh()
        dataset = self.run_import()
        _, records = load_dataset(dataset)
        parent = next(r for r in records if r['content_type']=='voice' and not r['quality']['media_missing'])
        self.assertEqual(locate_source_row(parent,dataset.parents[4]),4)
        parent['provenance']['source_row'] = 'nonexistent-source-row'
        with self.assertRaises(ValueError): locate_source_row(parent,dataset.parents[4])
        # 独立源包加入规范化后同一fallback键；导入入口须拒绝。
        self.rows.append(dict(self.rows[3],server_id=0))
        self.refresh()
        self.root = self.root / 'duplicate-import'
        with self.assertRaises(ValueError): self.run_import()
        self.assertFalse((self.root / 'people').exists())

    def test_locator_rejects_ambiguous_fallback_even_with_matching_file_hash(self):
        from tools.transcript_evidence import locate_source_row
        from tools.viewpoint_manifest import sha256
        source = self.root / 'ambiguous.json'
        fixtures.dump(source,[{'server_id':None,'source_row':'same'},{'server_id':'0','source_row':'same'}])
        parent = {'provenance':{'source_file':source.name,'source_file_sha256':sha256(source),'source_row':'same'}}
        with self.assertRaises(ValueError): locate_source_row(parent,self.root)

    def test_training_dedup_keeps_each_independently_reviewed_source(self):
        from tools import build_training_manifest as m
        from tools.build_relationship_data import build as relationship_build
        self.valid_audio()
        group = copy.deepcopy(self.rows[3])
        group.update(server_id='7',source_row=7,conversation_id='group',chat_room='group',
                     conversation_type='group',is_group_chat=True)
        self.rows.insert(3,group)
        self.refresh()
        dataset = self.run_import()
        first = self.root / 'pending'
        m.build(person='mama',datasets=[dataset],out=first)
        candidates = [json.loads(x) for x in (first / 'candidates.jsonl').read_text().splitlines() if json.loads(x)['audio_valid']]
        self.assertEqual([c['conversation_kind'] for c in candidates],['group','direct'])
        reviews = [dict(record_id=c['record_id'],audio_sha256=c['audio_sha256'],revision=c['revision'],
                        speaker_id='mama',speaker_status='confirmed',transcript_status='corrected',text='synthetic source '+c['conversation_kind'],
                        source_kind='real_recording',single_speaker=True,quality_status='approved',duration_approved=True,
                        decided_by='tester',decided_at='2026-10-20') for c in candidates]
        for mode, chosen, verified_count, father_count in [('both',reviews,2,1),('group',[reviews[0]],1,0),('direct',[reviews[1]],1,1)]:
            with self.subTest(mode=mode):
                review_path = self.root / (mode+'.json')
                fixtures.dump(review_path,dict(schema_version=1,reviews=chosen))
                trained = self.root / ('training-'+mode)
                m.build(person='mama',datasets=[dataset],out=trained,reviews=review_path)
                eligible = [json.loads(x) for x in (trained / 'eligible.jsonl').read_text().splitlines()]
                verified = [json.loads(x) for x in (trained / 'verified_transcripts.jsonl').read_text().splitlines()]
                self.assertEqual(len(eligible),1)
                self.assertEqual(len(verified),verified_count)
                self.assertIs(eligible[0]['training_eligible'],True)
                self.assertEqual(json.loads((trained / 'summary.json').read_text())['verified_transcripts'],verified_count)
                if mode == 'both':
                    excluded = [json.loads(x) for x in (trained / 'excluded.jsonl').read_text().splitlines()]
                    self.assertEqual(sum('duplicate_audio' in r['exclusion_reasons'] for r in excluded),1)
                self.assertTrue(all('training_eligible' not in r and r['transcript_verified'] is True for r in verified))
                self.assertEqual({r['record_id'] for r in verified},{r['record_id'] for r in chosen})
                self.assertEqual(len({r['dedup_group'] for r in verified}),1)
                self.assertEqual(len({r['split'] for r in verified}),1)
                relation = self.root / ('relationship-'+mode)
                relationship_build(person='mama',datasets=[dataset],viewer='father',out=relation,
                                   verified_transcripts=trained / 'verified_transcripts.jsonl')
                entries = json.loads((relation / 'relationship/transcripts.json').read_text())['entries']
                self.assertEqual(len(entries),father_count)
                if father_count:
                    for page in ['build_chat_page.py','build_companion_page.py']:
                        self.assertIn('synthetic source direct',run_retrieval_js(page,[],entries))

    def test_review_page_duration_dom(self):
        from tools import build_training_manifest as m
        self.valid_audio()
        self.rows[3]['media'][0]['duration_check'] = 'mismatch'
        self.refresh()
        dataset = self.run_import()
        out = self.root / 'duration'
        m.build(person='mama',datasets=[dataset],out=out)
        script = re.search(r'<script>(.*?)</script>', (out / 'review.html').read_text(), re.S).group(1)
        stub = "const elements=[];function el(tag){const x={tag,textContent:'',append(){},setAttribute(){}};elements.push(x);return x;}const ids={};global.document={createElement:el,createTextNode:t=>t,getElementById:id=>ids[id]||(ids[id]=el(id))};\n"
        proc = subprocess.run(['node','-'],input=stub+script+"\nconsole.log(elements.filter(e=>e.className==='duration').map(e=>e.textContent).join('\\n'));",text=True,encoding='utf-8',capture_output=True)
        self.assertEqual(proc.returncode,0,proc.stderr)
        self.assertIn('有差异',proc.stdout)
        self.assertIn('1000 ms',proc.stdout)
        self.assertIn('原期望 未知',proc.stdout)
        self.assertIn('差值 未知',proc.stdout)

    def test_review_page_readable_labels_and_trace_details(self):
        from tools.build_training_manifest import review_page
        candidate = dict(record_id='a'*64, audio_sha256='b'*64, revision='c'*64,
                         person='mama',viewpoint='father',relationship_id='mama_father',
                         timestamp='2020-01-02T03:04:05+08:00',draft_text='',audio_file=None,
                         duration_check='missing',actual_duration_ms=None,expected_duration_ms=None,
                         duration_delta_ms=None,exclusion_reasons=['speaker_pending','transcript_pending','audio_missing_or_invalid'])
        script = re.search(r'<script>(.*?)</script>',review_page([candidate]),re.S).group(1)
        stub = "const elements=[];function el(tag){const x={tag,textContent:'',append(){},setAttribute(){}};elements.push(x);return x;}const ids={};global.document={createElement:el,createTextNode:t=>t,getElementById:id=>ids[id]||(ids[id]=el(id))};\n"
        proc = subprocess.run(['node','-'],input=stub+script+"\nconsole.log(JSON.stringify(elements.map(e=>({tag:e.tag,text:e.textContent,placeholder:e.placeholder,type:e.type,checked:!!e.checked}))));",text=True,encoding='utf-8',capture_output=True)
        self.assertEqual(proc.returncode,0,proc.stderr)
        elements = json.loads(proc.stdout)
        heading = next(e['text'] for e in elements if e['tag']=='h2')
        self.assertIn('原声第 1 条',heading)
        self.assertIn('2020-01-02',heading)
        self.assertNotIn(candidate['record_id'],heading)
        text = '\n'.join(e['text'] for e in elements)
        for value in ['父亲微信','夫妻私聊','说话人待确认','转写待校对','缺失','来源详情',candidate['record_id'],candidate['audio_sha256']]:
            self.assertIn(value,text)
        self.assertTrue(any(e.get('placeholder') and '没有可用草稿' in e['placeholder'] for e in elements))
        boxes = [e for e in elements if e.get('type')=='checkbox']
        self.assertEqual(len(boxes),6)
        self.assertTrue(all(not e['checked'] for e in boxes))
    def test_pending_voice_never_eligible(self):
        dataset = self.run_import()
        module = importlib.import_module('tools.build_training_manifest')
        out = self.root / 'training'
        module.build(person='mama', datasets=[dataset], out=out)
        summary = json.loads((out / 'summary.json').read_text())
        self.assertEqual(summary['candidates'], 2)
        self.assertEqual(summary['eligible'], 0)
        self.assertTrue((out / 'review.html').exists())

    def test_eligibility_requires_all_reviews(self):
        m = importlib.import_module('tools.build_training_manifest')
        c = {'person':'mama','audio_sha256':'a'*64,'revision':'b'*64,
             'audio_valid':True,'duration_check':'mismatch'}
        review = dict(audio_sha256='a'*64, revision='b'*64, speaker_id='mama',
                      speaker_status='confirmed', transcript_status='corrected', text='hello',
                      source_kind='real_recording', single_speaker=True, quality_status='approved',
                      duration_approved=True, decided_by='tester', decided_at='2026-10-20')
        self.assertEqual(m.exclusion_reasons(c, review), [])
        for key, value in [('speaker_id','unknown'),('transcript_status','draft'),
                           ('source_kind','synthetic'),('duration_approved',False),('revision','old')]:
            self.assertTrue(m.exclusion_reasons(c, dict(review, **{key:value})))

    def valid_audio(self):
        with wave.open(str(self.source / 'records/conversation-1/a.wav'), 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(b'\x01\x00' * 16000)
        self.refresh()

    def test_asr_review_exact_revision_and_duplicate_audio(self):
        from tools import build_training_manifest as m
        from tools.viewpoint_manifest import sha256
        self.valid_audio()
        self.rows.append(dict(self.rows[3], server_id='7', source_row='source-row-string'))
        self.refresh()
        dataset = self.run_import()
        audio_hash = sha256(self.source / 'records/conversation-1/a.wav')
        drafts = self.root / 'drafts.json'
        mapping = self.root / 'map.json'
        fixtures.dump(drafts, [{'id':'one','asr_text':'draft one','cer':0}, {'id':'two','asr_text':'draft two','cer':0}])
        fixtures.dump(mapping, [dict(id=key, source_file='records/conversation-1/messages.json',
                                     source_row_number=n, native_id=native, wav_sha256=audio_hash)
                                for key,n,native in [('one',4,'4'),('two',7,'7')]])
        first = self.root / 'first'
        m.build(person='mama', datasets=[dataset], out=first, asr_drafts=drafts, asr_mapping=mapping)
        candidates = [json.loads(x) for x in (first / 'candidates.jsonl').read_text().splitlines()]
        audio_candidates = [c for c in candidates if c['audio_valid']]
        self.assertEqual(len(audio_candidates), 2)
        self.assertEqual({c['draft_text'] for c in audio_candidates}, {'draft one','draft two'})
        self.assertEqual(len({c['split'] for c in audio_candidates}), 1)
        reviews = [dict(record_id=c['record_id'],audio_sha256=c['audio_sha256'],revision=c['revision'],
                        speaker_id='mama',speaker_status='confirmed',transcript_status='corrected',text='corrected',
                        source_kind='real_recording',single_speaker=True,quality_status='approved',
                        duration_approved=True,decided_by='tester',decided_at='2026-10-20') for c in audio_candidates]
        review_path = self.root / 'review.json'
        fixtures.dump(review_path, {'schema_version':1,'reviews':reviews})
        second = self.root / 'second'
        m.build(person='mama', datasets=[dataset], out=second, asr_drafts=drafts, asr_mapping=mapping, reviews=review_path)
        eligible = [json.loads(x) for x in (second / 'eligible.jsonl').read_text().splitlines()]
        self.assertEqual(len(eligible), 1)
        self.assertEqual(eligible[0]['text'], 'corrected')
        self.assertEqual(eligible[0]['speaker_status'], 'confirmed')
        fixtures.dump(drafts, [{'id':'one','asr_text':'changed draft'}, {'id':'two','asr_text':'draft two'}])
        with self.assertRaises(ValueError):
            m.build(person='mama', datasets=[dataset], out=self.root / 'bad', asr_drafts=drafts, asr_mapping=mapping, reviews=review_path)
        self.assertFalse((self.root / 'bad').exists())

    def test_wrong_asr_source_and_output_overlap_fail_before_writes(self):
        from tools import build_training_manifest as m
        self.valid_audio()
        dataset = self.run_import()
        fixtures.dump(self.root / 'drafts.json', [{'id':'one','asr_text':'draft'}])
        fixtures.dump(self.root / 'map.json', [dict(id='one',source_file='wrong.json',source_row_number=1,native_id='4',wav_sha256='a'*64)])
        with self.assertRaises(ValueError):
            m.build(person='mama',datasets=[dataset],out=self.root / 'bad',asr_drafts=self.root / 'drafts.json',asr_mapping=self.root / 'map.json')
        self.assertFalse((self.root / 'bad').exists())
        with self.assertRaises(ValueError):
            m.build(person='mama',datasets=[dataset],out=dataset.parent)


if __name__ == '__main__':
    unittest.main()
