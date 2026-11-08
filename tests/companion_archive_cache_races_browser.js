// Actual Edge IndexedDB transactions; all identity/archive responses are synthetic.
const fs=require('fs'),http=require('http'),path=require('path');
const {chromium}=require(process.env.PLAYWRIGHT_CORE||require('node:path').join(require('node:os').homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright-core'));
const moduleText=fs.readFileSync(process.argv[2]||__dirname+'/../tools/companion_archive_cache.js','utf8');
const server=http.createServer((req,res)=>{if(req.url==='/cache.js'){res.setHeader('content-type','text/javascript');res.end(moduleText);}else {res.setHeader('content-type','text/html');res.end('<script src="/cache.js"></script>');}});
(async()=>{await new Promise(r=>server.listen(0,'127.0.0.1',r));const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try {const page=await browser.newPage();await page.goto('http://127.0.0.1:'+server.address().port);const result=await page.evaluate(async()=>{
  const api=globalThis.ArchiveDeviceCache,scope={person:'test',relationship_id:'test_father',viewer:'father',memory_release:null},reports=[];
  const assert=(v,m)=>{if(!v)throw Error(m);},sleep=()=>new Promise(r=>setTimeout(r,20));
  const sha=async raw=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',raw)),n=>n.toString(16).padStart(2,'0')).join('');
  const enc=v=>new TextEncoder().encode(JSON.stringify(v)).buffer;
  const bodies={'data/chat_context.json':enc({...scope,message_shards:['messages-2000.json']}),'data/messages-2000.json':enc([]),'data/memories.json':enc({...scope,entries:[]}),'data/transcripts.json':enc({...scope,entries:[]})};
  const manifest={schema_version:1,scope,scope_revision:await sha(new TextEncoder().encode(api.stable(scope))),context_path:'data/chat_context.json',files:[]};
  for(const p of Object.keys(bodies).sort())manifest.files.push({path:p,bytes:bodies[p].byteLength,sha256:await sha(bodies[p])});manifest.revision=await sha(new TextEncoder().encode(api.stable(manifest)));
  function fixture(){const f={downloads:0,gate:null,entered:null,failDownload:false};const store=new api.IndexedArchiveStore(indexedDB,()=>localStorage.disabled==='true');f.store=store;
   f.client=new api.ArchiveDeviceCache({scope,origin:location.origin,contextPath:manifest.context_path,manifestPath:'data/archive-cache-manifest.json',crypto,store,status(){},invalidate(){},disabledPreference:()=>localStorage.disabled==='true',invalidationToken:()=>localStorage.invalidation||'',notify(d){if(d!==undefined)localStorage.disabled=JSON.stringify(d);localStorage.invalidation=String(Math.random());},
    fetch:async url=>{if(f.gate){if(f.entered)f.entered();await f.gate;}return {ok:true,redirected:false,json:async()=>url.includes('get-identity')?{account_id:'a'.repeat(32),user_uuid:'11111111-1111-4111-8111-111111111111'}:structuredClone(manifest)};},
    transport:async p=>{f.downloads++;if(f.failDownload&&p.includes('transcripts'))throw Error('offline');return bodies[p].slice(0);},validate:async()=>{}});return f;}
  async function count(f){return f.store.run((m,s,c,done)=>{const q=s.getAll();q.onsuccess=()=>done(q.result.length);});}
  async function fresh(){localStorage.disabled='false';const f=fixture();await f.store.clear(false);await f.client.prepare();return f;}
  async function reject(p){let failed=false;try{await p;}catch(_){failed=true;}assert(failed,'must reject');}
  for(const fallback of [false,true]){
   const f=await fresh();f.downloads=0;let release,entered;f.gate=new Promise(r=>release=r);const atGate=new Promise(r=>entered=r);f.entered=entered;const pending=f.client.prepare();await atGate;
   await fixture().store.clear();if(fallback)f.store.bind=async()=>{throw Error('unavailable');};release();await reject(pending);assert(await count(f)===0,'prebind repopulated');assert(f.downloads===0,'prebind downloaded');reports.push(fallback?'R2 prebind storage fallback rejects stale generation':'R1 prebind cross-tab clear rejects stale generation');
  }
  {
   const f=await fresh();f.store.snapshot=async()=>{throw Error('unavailable');};f.downloads=0;await f.client.prepare();assert(f.downloads===4,'fallback reused old memory');assert(!f.client.retained,'fallback retained');reports.push('R2 unavailable snapshot downloads fresh bytes, no old memory');
  }
  {
   const f=fixture();await f.store.clear(false);let release,entered;const gate=new Promise(r=>release=r),atPut=new Promise(r=>entered=r),put=f.store.put.bind(f.store);f.store.put=async(...a)=>{entered();await gate;return put(...a);};
   const pending=f.client.prepare();await atPut;f.client.forget();await f.client.barrier;release();await reject(pending);assert(await count(f)===0,'lifecycle late write');reports.push('R3 lifecycle guards delayed actual IndexedDB write');
  }
  {
   const f=await fresh();f.store.clear=async()=>{throw Error('unavailable');};await f.client.clear(true);assert(localStorage.disabled==='true','disable not persisted');const recovered=fixture();await recovered.client.prepare();assert(recovered.client.disabled&&!recovered.client.retained,'disable recovery');assert(await count(recovered)===0,'disable retained records');reports.push('R4 failed disable persists across new client/storage recovery');
  }
  {
   const f=await fresh();f.client.forget();await f.client.barrier;await f.store.run((m,s)=>{const q=s.get('data/transcripts.json');q.onsuccess=()=>s.put({...q.result,raw:new Uint8Array([0]).buffer});});f.failDownload=true;await reject(f.client.prepare());const exists=await f.store.run((m,s,c,done)=>{const q=s.get('data/transcripts.json');q.onsuccess=()=>done(!!q.result);});assert(!exists,'corrupt record retained after failed refetch');reports.push('corrupt IndexedDB record removed before failed replacement');
  }
  {
   const a=await fresh(),before=await a.store.snapshot();
   await a.store.run((m,s)=>{const q=s.get('data/transcripts.json');q.onsuccess=()=>s.put({...q.result,raw:new Uint8Array([0]).buffer});});
   const b=fixture();b.failDownload=true;await reject(b.client.prepare());
   assert((await a.store.snapshot()).generation===before.generation,'single-file removal unexpectedly changed generation');
   assert(await count(a)===3,'failed replacement did not remove damaged record');
   let writes=0;const put=a.store.put.bind(a.store);a.store.put=async(...args)=>{writes++;return put(...args);};
   await a.client.prepare();assert(await count(a)===4&&a.client.retained,'healthy-memory client did not restore removed record');
   assert(writes===1,'expected exactly one replacement put');
   reports.push('R2 two-client same-generation removal + failed replacement repaired from healthy memory');
  }
  for(const persistent of [false,true]){
   const f=await fresh();let entered,rejectOld;const atValidation=new Promise(r=>entered=r),oldFailure=new Promise((_,r)=>rejectOld=r),validate=f.client.o.validate;
   f.client.o.validate=async(p,d)=>{if(p===manifest.context_path){entered();await oldFailure;}return validate(p,d);};
   const pending=f.client.prepare();const rejected=reject(pending);await atValidation;
   f.client.forget(persistent);f.client.o.validate=validate;await f.client.prepare();rejectOld(Error('old validator'));await rejected;
   assert(f.client.memory.size===4&&await count(f)===4&&f.client.retained,'old error changed successful B');
   reports.push('D old validator error preserves B memory/storage with generation change='+persistent);
  }
  {
   const f=await fresh();let writes=0;const put=f.store.put.bind(f.store);f.store.put=async(...a)=>{writes++;return put(...a);};
   const op=f.client.stageForSend();await op.localReady;assert(op.phase==='staged'&&writes===0,'warm stage wrote or did not park');
   await f.store.remove('data/transcripts.json',op.meta.generation);await f.client.finishForSend();
   assert(await count(f)===4&&writes===1&&f.client.retained,'resume missed same-generation deletion');
   reports.push('D parked missing record repaired explicitly with exactly one write');
  }
  {
   const f=await fresh(),op=f.client.stageForSend();await op.localReady;localStorage.disabled='true';
   await reject(f.client.finishForSend());assert(await count(f)===0,'deferred disable notifications escaped final direct check');
   reports.push('D parked disable detected without event delivery');
  }
  for(const boundary of ['bind','put','final']){
   const f=await fresh();let release,entered;const gate=new Promise(r=>release=r),atGate=new Promise(r=>entered=r);
   // Unchanged verified records no longer write. Force a missing record to retain
   // coverage of the real replacement-write race.
   if(boundary==='put'){f.client.memory.delete('data/transcripts.json');await f.store.remove('data/transcripts.json',f.client.memoryGeneration);}
   if(boundary==='bind'||boundary==='put'){const original=f.store[boundary].bind(f.store);f.store[boundary]=async(...args)=>{entered();await gate;return original(...args);};}
   else {let n=0;const original=f.client.o.fetch;f.client.o.fetch=async(...args)=>{if(++n===4){entered();await gate;}return original(...args);};}
   const pending=f.client.prepare();await atGate;const other=fixture();other.store.clear=async()=>{throw Error('temporarily unavailable');};await other.client.clear(true);assert(localStorage.disabled==='true','decision was not published');release();await reject(pending);assert(!f.client.retained,'overlap retained');assert(await count(f)===0,'overlap records remain');reports.push('R3 failed-disable overlap at '+boundary+' with notifications withheld');
  }
  {
   const f=await fresh(),state=await f.store.snapshot();localStorage.disabled='true';const bound=await f.store.bind(state.namespace,state.revision,manifest.files,state.generation,false);assert(bound.disabled,'direct bind ignored live preference');
   await f.store.put({path:'data/chat_context.json',sha256:manifest.files[0].sha256,namespace:state.namespace,raw:bodies['data/chat_context.json']},bound.generation);assert(await count(f)===0,'direct put ignored live preference');const racedClear=await f.store.clear(false);assert(racedClear.disabled,'stale enable transaction overrides newer disable');reports.push('R3 actual bind/put/clear honor current preference without client guard');
  }
  {
   const f=await fresh();await f.client.clear(true);f.store.clear=async()=>{throw Error('temporary');};await f.client.clear(false);await f.client.prepare();assert(!f.client.disabled&&f.client.retained,'explicit enable locked by old metadata');reports.push('R3 explicit re-enable recovers from failed transaction and old true metadata');
  }
  // Refresh cleanup must belong to its operation AND its original persistent generation.
  for(const mode of ['same-client-reject','same-client-resolve','other-client-reject','other-client-storage-error']){
   const originalManifest=structuredClone(manifest),originalBody=bodies['data/transcripts.json'];
   const a=await fresh(),oldRev=manifest.revision;let entered,release,held=false,n=0;
   const atBind=new Promise(r=>entered=r),hold=new Promise(r=>release=r),bind=a.store.bind.bind(a.store),fetch=a.client.o.fetch;
   a.client.o.fetch=async(...args)=>{if(++n===4){bodies['data/transcripts.json']=enc({...scope,entries:[],changed:1});const f=manifest.files.find(f=>f.path==='data/transcripts.json');f.bytes=bodies[f.path].byteLength;f.sha256=await sha(bodies[f.path]);delete manifest.revision;manifest.revision=await sha(new TextEncoder().encode(api.stable(manifest)));}return fetch(...args);};
   a.store.bind=async(...args)=>{if(args[1]!==oldRev&&!held){held=true;let result;if(mode==='same-client-resolve')result=await bind(...args);entered();await hold;if(mode==='other-client-storage-error')throw Error('storage failed');return result||bind(...args);}return bind(...args);};
   const pending=a.client.prepare(),rejected=reject(pending);await atBind;
   a.client.o.fetch=fetch;const b=mode.startsWith('same-client')?a:fixture();await b.client.prepare();const state=await b.store.snapshot(),epoch=b.client.epoch;
   release();await rejected;const after=await b.store.snapshot();
   assert(after.generation===state.generation&&await count(b)===4&&b.client.retained&&b.client.memory.size===4&&b.client.epoch===epoch,'late refresh damaged B '+mode);
   reports.push('R2 real IDB refresh ownership '+mode);
   Object.keys(manifest).forEach(k=>delete manifest[k]);Object.assign(manifest,originalManifest);bodies['data/transcripts.json']=originalBody;
  }
  {
   const a=await fresh(),other=fixture();let n=0,writes=0;const fetch=a.client.o.fetch,put=a.store.put.bind(a.store);
   a.store.put=async(...args)=>{writes++;return put(...args);};
   a.client.o.fetch=async(...args)=>{if(++n===4)await other.store.remove('data/transcripts.json',a.client.memoryGeneration);return fetch(...args);};
   const result=await a.client.prepare();assert(result.files.size===4&&!a.client.retained&&await count(a)===3&&writes===0,'final membership incorrectly retained/repaired');
   reports.push('R2 real IDB terminal same-generation removal truthfully not retained, no post-gate repair');
  }
  {
   const a=await fresh();a.client.memory.clear();await a.store.run((m,s)=>{const q=s.get('data/transcripts.json');q.onsuccess=()=>s.put({...q.result,raw:new Uint8Array([0]).buffer});});
   let entered,release,held=false;const atRemove=new Promise(r=>entered=r),hold=new Promise(r=>release=r),remove=a.store.remove.bind(a.store);
   a.store.remove=async(...args)=>{if(!held){held=true;entered();await hold;}return remove(...args);};
   const pending=a.client.prepare(),rejected=reject(pending);await atRemove;a.client.forget(false);await a.client.prepare();
   release();await rejected;assert(await count(a)===4&&a.client.retained&&a.client.memory.size===4,'late guarded deletion removed B');
   reports.push('R2 held actual IDB remove checks operation ownership before deleting repaired B');
  }
  for(const mode of ['authority','policy','unknown-generation']){
   const originalManifest=structuredClone(manifest),originalBody=bodies['data/transcripts.json'];
   const a=await fresh();let entered,release;const atIdentity=new Promise(r=>entered=r),hold=new Promise(r=>release=r),fetch=a.client.o.fetch;
   if(mode==='unknown-generation')a.store.snapshot=async()=>{throw Error('snapshot unavailable');};
   a.client.o.fetch=async(...args)=>{entered();await hold;if(mode!=='policy')throw Error('expired A');return fetch(...args);};
   const pending=a.client.prepare(),rejected=reject(pending);await atIdentity;
   if(mode==='policy')localStorage.invalidation=String(Math.random());
   bodies['data/transcripts.json']=enc({...scope,entries:[],changed:9});const f=manifest.files.find(f=>f.path==='data/transcripts.json');f.bytes=bodies[f.path].byteLength;f.sha256=await sha(bodies[f.path]);delete manifest.revision;manifest.revision=await sha(new TextEncoder().encode(api.stable(manifest)));
   const b=fixture();await b.client.prepare();const state=await b.store.snapshot();release();await rejected;
   assert((await b.store.snapshot()).generation===state.generation&&await count(b)===4&&b.client.retained,'automatic cleanup erased newer B '+mode);
   assert(!a.client.retained&&a.client.memory.size===0,'A remains authorized '+mode);
   reports.push('R3 actual IDB automatic '+mode+' cleanup preserves B newer generation and revokes A');
   Object.keys(manifest).forEach(k=>delete manifest[k]);Object.assign(manifest,originalManifest);bodies['data/transcripts.json']=originalBody;
  }
  {
   const a=await fresh();localStorage.invalidation=String(Math.random());
   assert(a.client.stageForSend()===null,'preflight adopted unvalidated policy');await a.client.finishForSend();
   const op=a.client.stageForSend();assert(op,'fresh explicit preparation did not restore eligibility');await op.localReady;
   reports.push('R3 actual IDB preflight rejects token changed before staging with notifications withheld');
  }
  {
   const a=await fresh();let entered,release,notified=0;const atClear=new Promise(r=>entered=r),hold=new Promise(r=>release=r),clear=a.store.clear.bind(a.store);
   a.client.o.notify=()=>{notified++;localStorage.invalidation=String(Math.random());};
   a.store.clear=async(...args)=>{const meta=await clear(...args);entered();await hold;return meta;};
   a.client.o.fetch=async()=>{throw Error('expired');};const pending=a.client.prepare(),rejected=reject(pending);await atClear;
   const b=fixture();await b.client.prepare();const state=await b.store.snapshot(),policy=localStorage.invalidation;
   release();await rejected;
   assert(notified===0&&localStorage.invalidation===policy&&(await b.store.snapshot()).generation===state.generation&&await count(b)===4&&b.client.retained,'late successful clear invalidated B');
   reports.push('R3 actual IDB clear commits then B rebinds before A resumes: no late token/broadcast');
  }
  for(const mode of ['own-disabled','reenable-rebind','new-owner','owner-only','new-generation-disabled']){
   const a=await fresh(),before=await a.store.snapshot(),db=await a.store.open();
   const epoch=a.client.epoch,owner=a.client.operationOwner;let enter,release,once=true;
   const entered=new Promise(r=>enter=r),held=new Promise(r=>release=r);
   a.store.open=async()=>({transaction(...args){
    const tx=db.transaction(...args);
    if(once){once=false;tx.addEventListener('complete',()=>{
     localStorage.disabled='true';a.store.open=()=>{enter();return held;};
    });}
    return tx;
   }});
   // The bind changes generation while preserving same-namespace healthy files.
   const pending=a.store.bind(before.namespace,'r5-new-revision',manifest.files,before.generation,false,()=>a.client.check(epoch,owner));
   const rejected=reject(pending);await entered;
   if(mode==='own-disabled'){
    release(db);await rejected;localStorage.disabled='false';
    const state=await fixture().store.snapshot();assert(state.disabled&&await count(a)===0,'same owner disable failed to clean just-committed generation');
   }else if(mode==='owner-only'){
    a.client.forget(false);release(db);await rejected;
    // Read raw IDB so disabledPreference's intentional read cleanup cannot mask
    // whether old A's automatic repair improperly cleared the new local owner.
    const rows=await new Promise((resolve,reject)=>{const tx=db.transaction(['files'],'readonly'),q=tx.objectStore('files').getAll();q.onsuccess=()=>resolve(q.result);q.onerror=()=>reject(q.error);});
    assert(rows.length===4,'owner-only stale repair cleared records');localStorage.disabled='false';
   }else{
    localStorage.disabled='false';
    if(mode==='new-owner')a.client.forget(false);
    const b=fixture();await b.client.prepare();const state=await b.store.snapshot();
    if(mode==='new-generation-disabled')localStorage.disabled='true';
    release(db);await rejected;localStorage.disabled='false';assert((await b.store.snapshot()).generation===state.generation&&await count(b)===4&&b.client.retained,'delayed postcommit repair erased B '+mode);
   }
   reports.push('R5 actual IDB postcommit repair '+mode);
  }
  return {pass:true,checks:reports,realPosts:0};
 });console.log(JSON.stringify(result,null,2));}finally{await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);server.close();process.exitCode=1;});
