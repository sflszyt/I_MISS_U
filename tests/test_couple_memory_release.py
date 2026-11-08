import copy
import unittest
from tools.couple_memory_release import digest, text_hash, validate_release


def fixture():
    row = dict(record_id='r1',person='mama',viewpoint='father',relationship_id='mama_father',tier=2,conversation_kind='direct',participant_ids=['mama','father'],content_type='text',sender_person_id='mama',sender='subject',text='synthetic plan not completed',timestamp='2022-01-01T09:00:00+08:00',provenance={'source_record_id':'r1'})
    auth = dict(mode='batch_adoption',source='synthetic-user-authorization',text='synthetic adopt',content_sha256=text_hash('synthetic adopt'),individual_human_confirmed=False,acoustic_listened=False)
    c = dict(id='c1',title='synthetic plan',texts=['synthetic plan; completion unknown'],date='2022-01-01',person='mama',relationship_id='mama_father',tier=2,release_id='release-test',authorization={k:v for k,v in auth.items() if k!='text'},provenance=dict(source_kind='original_text',source_sha256='0'*64,sources=[dict(record_id='r1',timestamp=row['timestamp'],speaker_id='mama',text_sha256=text_hash(row['text']))]))
    c['evidence_revision']=digest(c)
    p=dict(schema_version=1,kind='couple_memory_release',release_id='release-test',person='mama',viewer='father',relationship_id='mama_father',source_sha256='0'*64,authorization=auth,cards=[c])
    p['release_revision']=digest(p)
    return p,[row]


def resign(p):
    for c in p['cards']:
        c['evidence_revision']=digest({k:v for k,v in c.items() if k!='evidence_revision'})
    p['release_revision']=digest({k:v for k,v in p.items() if k!='release_revision'})


class ReleaseTests(unittest.TestCase):
    def test_invalid_packet(self):
        with self.assertRaises(ValueError):validate_release({}, [], '0'*64)

    def test_valid(self):
        p,r=fixture();result=validate_release(p,r,'0'*64)
        self.assertEqual(result['entries'][0]['tier'],2)
        self.assertFalse(result['entries'][0]['authorization']['individual_human_confirmed'])

    def test_reject_semantically_invalid_even_resigned(self):
        for mutation in [lambda p,r:p['cards'][0].update(tier=3),lambda p,r:p['cards'][0]['authorization'].update(acoustic_listened=True),lambda p,r:p['cards'][0]['authorization'].update(individual_human_confirmed=True),lambda p,r:p['cards'][0]['provenance'].update(source_kind='session'),lambda p,r:p['cards'][0]['provenance']['sources'][0].update(speaker_id='unknown'),lambda p,r:p['cards'][0]['provenance']['sources'][0].update(timestamp='2023-01-01T09:00:00+08:00'),lambda p,r:p['cards'][0]['provenance']['sources'][0].update(record_id='absent'),lambda p,r:r[0].update(relationship_id='mama_owner'),lambda p,r:r[0].update(text='changed'),lambda p,r:p['cards'].append(copy.deepcopy(p['cards'][0])),lambda p,r:p['cards'][0].update(decision='confirmed'),lambda p,r:p['cards'][0].update(date='1999-01-01')]:
            p,r=fixture();mutation(p,r);resign(p)
            with self.assertRaises(ValueError):validate_release(p,r,'0'*64)

    def test_stale_hashes(self):
        p,r=fixture();p['cards'][0]['texts']=['changed']
        with self.assertRaises(ValueError):validate_release(p,r,'0'*64)
        p,r=fixture()
        with self.assertRaises(ValueError):validate_release(p,r,'1'*64)

    def test_runtime_fetch_request_and_render_stub(self):
        import json, re, subprocess
        from tools import build_companion_page
        from tools.couple_memory_release import runtime_binding
        p,rows=fixture()
        for i in range(2,5):
            row=copy.deepcopy(rows[0]);row['record_id']='r'+str(i);row['provenance']['source_record_id']=row['record_id'];rows.append(row)
            ref=copy.deepcopy(p['cards'][0]['provenance']['sources'][0]);ref['record_id']=row['record_id'];p['cards'][0]['provenance']['sources'].append(ref)
        resign(p);container=validate_release(p,rows,'0'*64);binding=runtime_binding(container)
        html=build_companion_page.build('mama','unused','father',tts_origin='same',tts_token='synthetic-token',llm_proxy='/v1/chat/completions',relationship_scope={'person':'mama','relationship_id':'mama_father','memory_release':binding})
        names=['dataProgressSnapshot','reportDataProgress','drainDataQueue','boundedWait','dataFailure','dataError','fetchDataJson','checkScope','validateMemoryRelease','scoreText','retrieveKnowledge','buildRetrievalBlock','buildMessages','loadKnowledge','streamRequest','companionStream', 'newRequestDiagnostic', 'requestDiagnosticText','sseCreate','sseFeed','sseFinish','sseProcessLine','settingsComplete']
        functions='\n'.join(re.search(r'^(?:async )?function '+name+r'\([^\n]*\) \{.*?^\}|^function '+name+r'\([^\n]*\) \{[^\n]*\}',html,re.M|re.S).group() for name in names)
        script=r"""
const assert=require('assert'); const crypto=require('crypto').webcrypto;var dataReadyPhase='idle',dataProgress=Object.create(null),dataProgressListeners=[],knowledgePieces=Object.create(null);var memorySourceDigests=new Map();var dataFailures=Object.create(null);var dataQueue=[],dataActive=0,dataBlocked=0,dataRequests=Object.create(null);
var EXPECTED_SCOPE=FIXTURE_SCOPE, VIEWER='father',scopeError=false,contextLoaded=true,shards=[],shardStatus={};
var knowledgeLoading=false,knowledgeCache=null,LLM_PROXY='/v1/chat/completions',TTS_TOKEN='synthetic',settings={};
var location={origin:'https://fixture.invalid'},controller=null,streaming=false,sendBtn={textContent:'',classList:{add(){}}};
function loadSessionsData(){return Promise.resolve();} function applySessionsCard(){}
var memory=FIXTURE_MEMORY, requests=[],rendered='',memoryUrls=[];const trustedMemoryURL='data/memories-'+EXPECTED_SCOPE.memory_release.release_revision+'.json';
global.fetch=async function(url,opts){
 if(String(url).startsWith('data/memories'))memoryUrls.push(url);
 if(url==='data/memories-'+EXPECTED_SCOPE.memory_release.release_revision+'.json')return new Response(JSON.stringify(memory),{headers:{'Content-Type':'application/json'}});
 if(url==='data/transcripts.json')return new Response(JSON.stringify({person:'mama',relationship_id:'mama_father',entries:[]}),{headers:{'Content-Type':'application/json'}});
 if(String(url).endsWith('/v1/chat/completions')) {requests.push(JSON.parse(opts.body));return new Response('data: '+JSON.stringify({choices:[{delta:{content:'synthetic rendered reply'}}]})+'\n\ndata: [DONE]\n\n',{headers:{'Content-Type':'text/event-stream'}});}
 throw new Error('forbidden outbound '+url);
};
""".replace('FIXTURE_SCOPE',json.dumps(dict(person='mama',relationship_id='mama_father',memory_release=binding))).replace('FIXTURE_MEMORY',json.dumps(container))+functions+r"""
(async()=>{
 await loadKnowledge(); assert(knowledgeCache);
 let hit=retrieveKnowledge(['synthetic'],knowledgeCache.memories,[],{});
 let block=buildRetrievalBlock(hit.memories);assert(block.length<=2200);assert(block.includes('full_sources_digest=EXPECTED_SOURCE_DIGEST'));assert(block.includes('source_count=4'));assert(block.includes('sources_EXCERPT=r1,r2,r3'));assert(block.includes('release_id=release-test'));assert(block.includes('Tier-2'));assert(block.includes('completion unknown'));assert(block.includes('r1'));
 let messages=buildMessages('wife husband partial',[],block,'synthetic');
 await new Promise((resolve,reject)=>streamRequest(messages,x=>{rendered+=x;},()=>resolve(),reject,{provider:'deepseek',model:'deepseek-v4-pro'}));
 assert.equal(requests.length,1);assert.equal(rendered,'synthetic rendered reply');assert(!requests[0].messages.at(-1).content.includes('Tier-1'));
 for (let mutate of [m=>m.entries[0].texts[0]='changed',m=>m.entries[0].tier=1,m=>m.entries[0].authorization.acoustic_listened=true,m=>m.release_revision='stale',m=>m.entries.push(m.entries[0])]) {
   memory=JSON.parse(JSON.stringify(FIXTURE_GOOD)); mutate(memory);knowledgeCache=null;knowledgePieces=Object.create(null);scopeError=false;await loadKnowledge();assert.equal(knowledgeCache,null);assert(scopeError);
 }
 for (const key of ['record_id','timestamp','speaker_id','text_sha256','count']) {
 memory=JSON.parse(JSON.stringify(FIXTURE_GOOD));const card=memory.entries[0];
 if(key==='count')card.provenance.sources.pop();else card.provenance.sources[3][key]='tampered';
 const clean={...card};delete clean.evidence_revision;
 const canonical=v=>Array.isArray(v)?'['+v.map(canonical).join(',')+']':v&&typeof v==='object'?'{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}':JSON.stringify(v);
 card.evidence_revision=require('crypto').createHash('sha256').update(canonical(clean)).digest('hex');
 knowledgeCache=null;knowledgePieces=Object.create(null);scopeError=false;await loadKnowledge();assert.equal(knowledgeCache,null);assert(scopeError);
 }
 const beforeInvalid=memoryUrls.length;
 const mixed={person:'mama',relationship_id:'mama_father',viewer:'father',language:'mandarin',coverage_status:'partial',system_prompt:'synthetic',message_shards:['messages-0000.json'],memory_release:{...EXPECTED_SCOPE.memory_release,release_revision:'0'.repeat(64)}};
 let mixedRejected=false;try{checkScope(mixed,'context');}catch(e){mixedRejected=true;}assert(mixedRejected);
 memory=JSON.parse(JSON.stringify(FIXTURE_GOOD));knowledgeCache=null;knowledgePieces=Object.create(null);scopeError=false;EXPECTED_SCOPE.memory_release.release_revision='../escape';await loadKnowledge();assert.equal(knowledgeCache,null);assert(scopeError);
 assert.equal(memoryUrls.length,beforeInvalid);assert(memoryUrls.every(u=>u===trustedMemoryURL));assert.equal(requests.length,1);console.log('PASS local fetch, retrieval, request, response accumulation; all outbound intercepted');
})().catch(e=>{console.error(e);process.exitCode=1;});
""".replace('FIXTURE_GOOD',json.dumps(container)).replace('EXPECTED_SOURCE_DIGEST',digest(container['entries'][0]['provenance']['sources']))
        result=subprocess.run(['node','-'],input=script,text=True,encoding='utf-8',capture_output=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_strict_authorization_and_version(self):
        for value in (0, 0.0):
            for field in ('individual_human_confirmed','acoustic_listened'):
                p,r=fixture();p['cards'][0]['authorization'][field]=value;resign(p)
                with self.assertRaises(ValueError):validate_release(p,r,'0'*64)
        p,r=fixture();p['schema_version']=True;resign(p)
        with self.assertRaises(ValueError):validate_release(p,r,'0'*64)

    def test_raw_codepoint_length(self):
        p,r=fixture();p['cards'][0]['texts']=['😀'*900];resign(p)
        validate_release(p,r,'0'*64)
        for value in ('😀'*901, ' '+('x'*900), ('x'*900)+' '):
            p,r=fixture();p['cards'][0]['texts']=[value];resign(p)
            with self.assertRaises(ValueError):validate_release(p,r,'0'*64)

    def test_runtime_unicode_special_ids_and_unbound(self):
        import json,re,subprocess
        from tools import build_companion_page,build_chat_page
        from tools.couple_memory_release import runtime_binding
        for cid in ('constructor','toString','__proto__'):
            p,r=fixture();p['cards'][0]['id']=cid;p['cards'][0]['texts']=['😀'*900];resign(p)
            container=validate_release(p,r,'0'*64);binding=runtime_binding(container)
            html=build_companion_page.build('mama','unused','father',relationship_scope=dict(person='mama',relationship_id='mama_father',memory_release=binding))
            names=['dataProgressSnapshot','reportDataProgress','drainDataQueue','boundedWait','dataFailure','dataError','fetchDataJson','checkScope','validateMemoryRelease','scoreText','retrieveKnowledge']
            functions='\n'.join(re.search(r'^(?:async )?function '+n+r'\([^\n]*\) \{.*?^\}',html,re.M|re.S).group() for n in names)
            scope=re.search(r'^var EXPECTED_SCOPE = .*?;$',html,re.M).group()
            script="const assert=require('assert');const crypto=require('crypto').webcrypto;var dataReadyPhase='idle',dataProgress=Object.create(null),dataProgressListeners=[],knowledgePieces=Object.create(null);var memorySourceDigests=new Map();var dataFailures=Object.create(null);var dataQueue=[],dataActive=0,dataBlocked=0,dataRequests=Object.create(null);var VIEWER='father',scopeError=false;"+scope+functions+"const data=JSON.parse("+json.dumps(json.dumps(container))+ ");"+r"""
(async()=>{
 await validateMemoryRelease(data);
 assert(Object.prototype.hasOwnProperty.call(EXPECTED_SCOPE.memory_release.card_revisions,data.entries[0].id));
 let bad=JSON.parse(JSON.stringify(data));bad.entries[0].texts[0]+=' ';let rejected=false;
 try{await validateMemoryRelease(bad);}catch(e){rejected=true;}assert(rejected);
 EXPECTED_SCOPE=null;
 const old={id:'old',title:'synthetic',texts:['synthetic old'],tier:1};
 assert.equal(retrieveKnowledge(['synthetic'],[data.entries[0],old],[],{}).memories.length,1);
})().catch(e=>{console.error(e);process.exitCode=1;});
"""
            result=subprocess.run(['node','-'],input=script,text=True,encoding='utf-8',capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
        source=build_chat_page.__file__
        from pathlib import Path
        text=Path(source).read_text(encoding='utf-8')
        functions='\n'.join(re.search(r'^function '+n+r'\([^\n]*\) \{.*?^\}',text,re.M|re.S).group() for n in ['scoreText','retrieveKnowledge'])
        script="const assert=require('assert');"+functions+"const cards="+json.dumps([fixture()[0]['cards'][0],dict(id='old',title='synthetic',texts=['synthetic'],tier=1)])+";assert.equal(retrieveKnowledge(['synthetic'],cards,[],{}).memories.length,1);"
        result=subprocess.run(['node','-'],input=script,text=True,encoding='utf-8',capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
