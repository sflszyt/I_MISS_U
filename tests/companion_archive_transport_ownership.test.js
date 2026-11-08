const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),{spawnSync}=require('node:child_process');
const generated=spawnSync('python',['-X','utf8','-c',"from tools.build_companion_page import build; print(build('synthetic','.','father',relationship_scope={'person':'synthetic','relationship_id':'synthetic_father'},archive_manifest_path='data/archive-cache-manifest.json'))"],{cwd:__dirname+'/..',encoding:'utf8'});
assert.equal(generated.status,0,generated.stderr);
const html=generated.stdout,code=html.slice(html.indexOf('var scopeError = false;'),html.indexOf('function checkScope('));
const tick=()=>new Promise(r=>setImmediate(r));
function setup(){
 const timers=[],calls=[],releases=new Map();
 const s={AbortController,Set,setTimeout:(fn,ms)=>{const t={fn,ms};timers.push(t);return t;},clearTimeout:()=>{},fetch:async url=>{calls.push(url);return {ok:true,redirected:false,arrayBuffer:()=>new Promise(r=>releases.set(url,r))};}};
 vm.createContext(s);vm.runInContext(code,s);
 const start=(url,resource='CONTEXT')=>{const p=s.fetchDataJson(url,resource,true);p.catch(()=>{});return p;};
 const release=url=>releases.get(url)(new Uint8Array([1]).buffer);
 return {s,timers,calls,start,release};
}
test('generated father stale body timeout preserves B diagnostics and real occupied slot',async()=>{
 const f=setup(),a=f.start('A');await tick();f.s.invalidateDataArchive();f.s.dataFailures=Object.create(null);f.s.dataProgress=Object.create(null);
 const b=f.start('B');await tick();f.release('B');await b;await tick();f.s.dataReadyPhase='ready';f.s.reportDataProgress('CONTEXT','verified');
 const before=JSON.stringify(f.s.dataProgressSnapshot());f.timers[0].fn();await assert.rejects(a,/ARCHIVE_INVALIDATED/);await tick();
 assert.equal(JSON.stringify(f.s.dataProgressSnapshot()),before);assert.equal(f.s.dataBlocked,0);assert.equal(f.s.dataActive,1);
 const pending=['C','D','E','F'].map(u=>f.start(u,u));await tick();assert.equal(f.s.dataActive,4);assert(!f.calls.includes('F'));assert.equal(f.s.dataQueue.length,1);
 f.release('A');await tick();assert(f.calls.includes('F'));assert.equal(f.s.dataBlocked,0);assert.equal(f.s.dataActive,4);
 for(const u of ['C','D','E','F'])f.release(u);await Promise.all(pending);await tick();assert.equal(f.s.dataActive,0);assert.equal(f.s.dataBlocked,0);
});
test('generated father stale queued start cannot publish progress or delete B failure',async()=>{
 const f=setup(),active=['A1','A2','A3','A4'].map(u=>f.start(u,u));await tick();const queued=f.start('old-queued','CONTEXT');
 f.s.invalidateDataArchive();f.s.dataProgress=Object.create(null);f.s.dataFailures={CONTEXT:'B_DIAGNOSTIC'};
 const b=f.start('B','B_CONTEXT');f.release('A1');await tick();await assert.rejects(queued,/ARCHIVE_INVALIDATED/);
 assert(!f.calls.includes('old-queued'));assert.equal(f.s.dataFailures.CONTEXT,'B_DIAGNOSTIC');assert.equal(f.s.dataProgress.CONTEXT,undefined);
 f.release('B');await b;for(const u of ['A2','A3','A4'])f.release(u);await Promise.allSettled(active);await tick();assert.equal(f.s.dataActive,0);
});
test('generated father current timeout cancels stale queue without stale diagnostic and accounts blocked once',async()=>{
 const f=setup(),active=['A1','A2','A3'].map(u=>f.start(u,u));await tick();const current=f.start('current','CURRENT');await tick();
 // Queue A first, invalidate its epoch, then leave current work under the new epoch.
 const queued=f.start('old-queued','CONTEXT');f.s.invalidateDataArchive();f.s.dataFailures={CONTEXT:'B_DIAGNOSTIC'};
 // Start a new B after releasing one stale slot, keeping the queued old job behind MEMORY priority.
 const b=f.start('B','MEMORY');f.release('A1');await tick();assert(f.calls.includes('B'));assert(!f.calls.includes('old-queued'));
 f.timers[4].fn();await assert.rejects(b);await assert.rejects(queued,/ARCHIVE_INVALIDATED/);
 assert.equal(f.s.dataFailures.CONTEXT,'B_DIAGNOSTIC');assert.equal(f.s.dataBlocked,1);assert.equal(f.s.dataActive,4);
 f.release('B');for(const u of ['A2','A3','current'])f.release(u);await Promise.allSettled([...active,current]);await tick();assert.equal(f.s.dataBlocked,0);assert.equal(f.s.dataActive,0);
});
