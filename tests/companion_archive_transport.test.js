const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync(__dirname+'/../tools/build_companion_page.py','utf8');
const code=source.slice(source.indexOf('var scopeError = false;'),source.indexOf('function checkScope('));
function harness(fetch){const timers=[];const s={AbortController,Set,setTimeout:(fn,ms)=>{const h=setTimeout(fn,ms);if(ms===15000)timers.push({fn,h});return h;},clearTimeout,fetch};vm.createContext(s);vm.runInContext(code,s);return {s,timers};}
test('raw response scheduler keeps four complete-body slots and inflight dedup',async()=>{
 let active=0,peak=0,calls=0;const t=harness(async()=>{calls++;active++;peak=Math.max(peak,active);return {ok:true,redirected:false,arrayBuffer:async()=>{await new Promise(r=>setTimeout(r,5));active--;return new Uint8Array([1,2,3]).buffer;}};});
 const a=t.s.fetchDataJson('same','MEMORY',true),b=t.s.fetchDataJson('same','MEMORY',true);assert.strictEqual(a,b);
 const list=Array.from({length:20},(_,i)=>t.s.fetchDataJson('file'+i,'SHARD_'+i,true));assert.equal((await Promise.all([a,...list])).length,21);assert.equal(calls,21);assert.equal(peak,4);
});
test('raw body timeout rejects late bytes and never releases slot before transport settles',async()=>{
 let release,calls=0;const gate=new Promise(r=>release=r);const t=harness(async()=>{calls++;return {ok:true,redirected:false,arrayBuffer:async()=>{await gate;return new Uint8Array([1]).buffer;}};});
 const p=t.s.fetchDataJson('slow','CONTEXT',true);await new Promise(r=>setTimeout(r,5));clearTimeout(t.timers[0].h);t.timers[0].fn();await assert.rejects(p);assert.equal(t.s.dataActive,1);assert.equal(t.s.dataBlocked,1);await assert.rejects(t.s.fetchDataJson('slow','CONTEXT',true));assert.equal(calls,1);release();await new Promise(r=>setTimeout(r,5));assert.equal(t.s.dataActive,0);assert.notEqual(t.s.dataProgress.CONTEXT.state,'checking');
});
test('clear epoch rejects old raw response even when abort is ignored',async()=>{
 let release;const gate=new Promise(r=>release=r);const t=harness(async()=>({ok:true,redirected:false,arrayBuffer:async()=>{await gate;return new Uint8Array([1]).buffer;}}));
 const p=t.s.fetchDataJson('slow','CONTEXT',true);await new Promise(r=>setTimeout(r,5));t.s.invalidateDataArchive();release();await assert.rejects(p);assert.notEqual(t.s.dataProgress.CONTEXT.state,'checking');
});
