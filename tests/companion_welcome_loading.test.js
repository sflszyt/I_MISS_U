const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const {test}=require('node:test');
// Reuse the existing real loader/send sandbox, without executing its suite.
const fixture=fs.readFileSync(__dirname+'/companion_loading_diagnostics.test.js','utf8').split('(async()=>{')[0];
const sandbox={require,console,process:{argv:['node','test',__dirname+'/../tools/build_companion_page.py']},__dirname,setTimeout,clearTimeout,structuredClone,TextEncoder};
vm.runInNewContext(fixture+'\nglobalThis.setup=setup;globalThis.tick=tick;',sandbox);
const {setup,tick}=sandbox;
test('intro gates send; accepted preload and send share one operation and actual file progress',async()=>{
 const t=setup();t.s.introAccepted=false;t.s.sendMessage({key:'Enter'});await tick();assert.equal(Object.keys(t.fetchCounts).length,0);
 t.s.introAccepted=true;const a=t.s.ensureDataReady(),b=t.s.ensureDataReady();assert.strictEqual(a,b);t.s.sendMessage();assert.equal(await a,true);await tick();
 assert.equal(t.calls.length,1);assert(Object.values(t.fetchCounts).every(n=>n===1));
 const p=t.s.dataProgressSnapshot();assert.equal(p.verified,5);assert.equal(p.downloaded,5);assert.equal(p.total,5);assert.equal(p.phase,'ready');
});
test('preload alone does not create model or session; retry reuses validated pieces',async()=>{
 const t=setup((u,r)=>{if(u.includes('transcripts')){r.ok=false;r.status=503;}return r;});
 assert.equal(await t.s.ensureDataReady(),false);assert.equal(t.calls.length,0);assert.equal(t.logs.length,0);assert.equal(t.s.sessionTurn,0);
 assert.equal(t.s.dataProgressSnapshot().phase,'failed');t.recover();assert.equal(await t.s.ensureDataReady(),true);
 assert.equal(t.fetchCounts['data/transcripts.json'],2);assert(Object.entries(t.fetchCounts).filter(([u])=>!u.includes('transcripts')).every(([,n])=>n===1));
});
test('input or profile edits during preparation never send or lose draft',async()=>{
 for(const change of [s=>{s.inputText.value='new draft';s.inputRevision++;},s=>{s.settings.model='new';}]){
  let release;const gate=new Promise(r=>release=r);const t=setup((u,r)=>{if(u.includes('messages-0001')){const json=r.json;r.json=async()=>{await gate;return json();};}return r;});
  const p=t.s.ensureDataReady();t.s.sendMessage();change(t.s);release();await p;await tick();assert.equal(t.calls.length,0);assert(t.s.inputText.value);assert.equal(t.s.dataProgressSnapshot().phase,'ready');
 }
});
test('no Content-Length reports completed files and waits for full body verification',async()=>{
 let release;const gate=new Promise(r=>release=r);const t=setup((u,r)=>{r.headers.get=()=>null;if(u.includes('messages-0001')){const json=r.json;r.json=async()=>{await gate;return json();};}return r;});
 const p=t.s.ensureDataReady();await tick();let v=t.s.dataProgressSnapshot();assert.equal(v.total,5);assert.equal(v.downloaded,4);assert.equal(v.verified,4);assert.equal(v.phase,'loading');release();assert.equal(await p,true);
});
test('late body after timeout cannot validate, unblock a send, or overlap retry',async()=>{
 let release;const gate=new Promise(r=>release=r),timers=[];
 const t=setup((u,r)=>{if(u.includes('messages-0001')){const json=r.json;r.json=async()=>{await gate;return json();};}return r;},s=>{s.setTimeout=(fn,ms)=>{const h=setTimeout(fn,ms);if(ms===15000 && String(fn).includes('dataBlocked++'))timers.push({fn,h});return h;};});
 const p=t.s.ensureDataReady();await tick();const timer=timers[timers.length-1];clearTimeout(timer.h);timer.fn();
 assert.equal(await p,false);assert.equal(t.s.dataProgressSnapshot().phase,'failed');assert.equal(await t.s.ensureDataReady(),false);assert.equal(t.fetchCounts['data/messages-0001.json'],1);
 release();await tick();assert.notEqual(t.s.shardStatus['messages-0001.json'],true);assert.equal(t.s.dataProgressSnapshot().phase,'failed');assert.equal(t.calls.length,0);
 t.recover();assert.equal(await t.s.ensureDataReady(),true);assert.equal(t.fetchCounts['data/messages-0001.json'],2);
});
test('preparation is isolated from no-memory and realtime conversation state',async()=>{
 const t=setup();t.s.noMemoryEnabled=true;t.s.history=[{role:'user',content:'PRIVATE_REALTIME'}];
 assert.equal(await t.s.ensureDataReady(),true);assert.equal(t.logs.length,0);assert.equal(t.s.sessionTurn,0);assert.equal(t.calls.length,0);
 assert(!JSON.stringify(t.s.knowledgeCache).includes('PRIVATE_REALTIME'));assert(!JSON.stringify(t.s.shardCache).includes('PRIVATE_REALTIME'));assert.equal(t.s.history[0].content,'PRIVATE_REALTIME');
});
