// Runs actual generated JS loaders/send gate with synthetic data and no network.
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict'),{webcrypto,createHash}=require('crypto');
const src=fs.readFileSync(process.argv[2]||__dirname+'/build_companion_page.py','utf8');
const part=(a,b)=>src.slice(src.indexOf(a),src.indexOf(b,src.indexOf(a)));
const code=part('var scopeError = false;','var SESSIONS_PATH =')+part('function ensureDataReady()','function collectAllRecords()')+part('function maybeActivateAutoVoice(', 'function readUiPrefs(')+part('function sendMessage(event)','/* ===== 输入框自动增长');
const scope={person:'synthetic-person',relationship_id:'synthetic-relation'};
const canonical=v=>Array.isArray(v)?'['+v.map(canonical).join(',')+']':v&&typeof v==='object'?'{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}':JSON.stringify(v);
function setup(modify,capability){
 let bad=true;const notices=[],calls=[],logs=[],fetchCounts={};
 const c={...scope,id:'private-card-id',tier:2,release_id:'private-release-id',authorization:{mode:'batch_adoption',individual_human_confirmed:false,acoustic_listened:false},provenance:{source_kind:'original_text',source_sha256:'c'.repeat(64),sources:[{record_id:'private-record',timestamp:'2000',text_sha256:'d'.repeat(64),speaker_id:'father'}]},texts:['PRIVATE_CONTENT_SENTINEL']};
 c.evidence_revision=createHash('sha256').update(canonical(c)).digest('hex');
 const binding={release_id:c.release_id,release_revision:'a'.repeat(64),source_sha256:c.provenance.source_sha256,card_revisions:{[c.id]:c.evidence_revision}};
 const context={...scope,viewer:'father',coverage_status:'partial',language:'mandarin',system_prompt:'PRIVATE_PROMPT',message_shards:['messages-0000.json','messages-0001.json'],memory_release:binding};
 const row={...scope,record_id:'private-record',provenance:{source_record_id:'private-record'},viewpoint:'father',conversation_kind:'direct',content_type:'text',tier:2,sender_person_id:'father',sender:'viewpoint_owner',participant_ids:['synthetic-person','father']};
 const sandbox={setTimeout,clearTimeout,EXPECTED_SCOPE:{...scope,memory_release:binding},VIEWER:'father',crypto:webcrypto,TextEncoder,isSecureContext:true,contextLoading:null,contextLoaded:false,shardsLoading:false,shards:[],shardStatus:{},shardCache:{},knowledgeLoading:false,knowledgeCache:null,sessionsDataPromise:Promise.resolve(),applySessionsCard(){},updateChatState(){},streaming:false,sendPending:false,settings:{provider:'synthetic',model:'synthetic'},settingsComplete:()=>true,inputText:{value:'PRIVATE_DRAFT'},inputRevision:0,sendGeneration:0,unlockAudio(){},systemNotice:s=>notices.push(s),maybeReplayHistory(){},autoGrow(){},cancelVoiceTurn(){},addBubble:()=>({set textContent(v){notices.push(v);},querySelector:()=>({})}),history:[],ensureSessionStarted(){},sessionTurn:0,logSession:r=>logs.push(r),setTypingIndicator(){},collectAllRecords:()=>[],extractTokens:()=>[],retrieveSnippets:()=>[],retrieveKnowledge:()=>({memories:[],transcripts:[]}),retrieveSessions:()=>[],sessionsData:{},buildRetrievalBlock:()=>'',buildMessages:()=>[],streamRequest:()=>calls.push('model'),fetch:async(url)=>{
  fetchCounts[url]=(fetchCounts[url]||0)+1;
  let body=url.includes('CONTEXT_PATH')?structuredClone(context):url.includes('messages-')?[structuredClone(row)]:url.includes('memories-')?{...scope,schema_version:3,release_id:binding.release_id,release_revision:binding.release_revision,source_sha256:binding.source_sha256,entries:[structuredClone(c)]}:{...scope,entries:[]};
  const response={ok:true,status:200,redirected:false,headers:{get:()=> 'application/json'},text:async()=>"",json:async()=>body};
  return bad&&modify?modify(url,response,body):response;
 }};
 if(capability)capability(sandbox);vm.createContext(sandbox);vm.runInContext(code,sandbox);
 return {s:sandbox,notices,calls,logs,fetchCounts,recover:()=>{bad=false;sandbox.crypto=webcrypto;sandbox.TextEncoder=TextEncoder;}};
}
const tick=()=>new Promise(resolve=>setTimeout(resolve,25));
async function check(name,modify,want,capability){const t=setup(modify,capability);t.s.sendMessage();t.s.sendMessage();await tick();assert(Object.values(t.fetchCounts).every(n=>n===1),name+' duplicate in-flight fetch');assert.equal(t.calls.length,0,name+' must fail closed');assert.equal(t.logs.length,0);assert.equal(t.s.inputText.value,'PRIVATE_DRAFT');assert(t.notices.length>0);const note=t.notices.join('\n');assert(note.includes(want),name+': '+note);assert(note.includes('D20261026-1'));assert(!/PRIVATE|private-|synthetic-person|synthetic-relation|https?:/.test(note),name+' leaked private data');t.recover();t.s.sendMessage();t.s.sendMessage();await tick();assert.equal(t.calls.length,1,name+' recovery');assert.equal(t.s.inputText.value,'');assert.equal(Object.keys(t.s.dataFailures).length,0,name+' stale failure cleared');console.log('PASS '+name);}
(async()=>{
 for(const status of [401,403,404,429,500,503])await check('context HTTP '+status,(u,r)=>{if(u.includes('CONTEXT_PATH')){r.ok=false;r.status=status;}return r;},'CONTEXT:HTTP_'+status);
 await check('network',(u,r)=>{if(u.includes('CONTEXT_PATH'))throw Error('PRIVATE_TOKEN https://secret');return r;},'CONTEXT:NETWORK');
 await check('redirected HTML',(u,r)=>{if(u.includes('CONTEXT_PATH')){r.redirected=true;r.headers.get=()=> 'text/html';r.json=async()=>{throw Error('PRIVATE_BODY');};}return r;},'CONTEXT:REDIRECT_NON_JSON');
 await check('nonJSON',(u,r)=>{if(u.includes('CONTEXT_PATH')){r.headers.get=()=> 'text/html';r.json=async()=>{throw Error('PRIVATE_BODY');};}return r;},'CONTEXT:NON_JSON');
 await check('broken JSON',(u,r)=>{if(u.includes('CONTEXT_PATH'))r.json=async()=>{throw Error('PRIVATE_BODY');};return r;},'CONTEXT:JSON');
 await check('context scope',(u,r,b)=>{if(u.includes('CONTEXT_PATH'))b.viewer='wrong';return r;},'CONTEXT:SCOPE');
 await check('context binding',(u,r,b)=>{if(u.includes('CONTEXT_PATH'))b.memory_release.release_revision='b'.repeat(64);return r;},'CONTEXT:BINDING');
 await check('shard failure',(u,r)=>{if(u.includes('messages-0001')){r.ok=false;r.status=503;}return r;},'SHARD_2:HTTP_503');
 await check('memory release',(u,r,b)=>{if(u.includes('memories-'))b.release_revision='b'.repeat(64);return r;},'MEMORY:RELEASE');
 await check('memory hash',(u,r,b)=>{if(u.includes('memories-'))b.entries[0].texts=['changed'];return r;},'MEMORY:CARD_HASH');
 await check('crypto missing',null,'MEMORY:CRYPTO_UNAVAILABLE',s=>s.crypto={});
 await check('encoder missing',null,'MEMORY:CRYPTO_UNAVAILABLE',s=>s.TextEncoder=undefined);
 await check('digest reject',null,'MEMORY:CRYPTO_FAILED',s=>s.crypto={subtle:{digest:async()=>{throw Error('PRIVATE_EXCEPTION');}}});
 await check('transcripts HTTP',(u,r)=>{if(u.includes('transcripts')){r.ok=false;r.status=403;}return r;},'TRANSCRIPTS:HTTP_403');
})().catch(e=>{console.error(e);process.exitCode=1;});
