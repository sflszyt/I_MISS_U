'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {DraftSync, DraftCache} = require('../../tools/mobile_review_ui.js');
const clone = x => JSON.parse(JSON.stringify(x));
function setup() {
  let cache; const calls=[]; const pending=[];
  const sync = new DraftSync('ab','pkg',{revision:0,values:{position:0,items:{x:{note:''}}}},
    (path,body)=>{calls.push(clone(body)); return new Promise((resolve,reject)=>pending.push({resolve,reject}));},
    value=>{cache=clone(value);},()=>{});
  return {sync,calls,pending,get cache(){return cache;}};
}
test('late save ack preserves newer edits and serializes requests',async()=>{
 const t=setup();t.sync.edit(v=>v.items.x.note='first');const p=t.sync.flush();
 t.sync.edit(v=>v.items.x.note='second');assert.equal(t.calls.length,1);
 t.pending.shift().resolve({revision:1,values:t.calls[0].values});await new Promise(r=>setImmediate(r));
 assert.equal(t.calls[1].values.items.x.note,'second');
 t.pending.shift().resolve({revision:2,values:t.calls[1].values});await p;
 assert.equal(t.sync.values.items.x.note,'second');assert.equal(t.sync.revision,2);
});
test('lost save response retries immutable request after reload',async()=>{
 const t=setup();t.sync.edit(v=>v.items.x.note='first');const p=t.sync.flush();
 t.pending.shift().reject(new Error('offline'));await p;
 const cache=t.cache;let received;
 const next=new DraftSync('ab','pkg',{revision:1,values:t.calls[0].values},async(path,body)=>{received=body;return {revision:1};},()=>{},()=>{},cache);
 await next.flush();assert.deepEqual(received,t.calls[0]);assert.equal(next.dirty,false);
});
test('lost submit response keeps exact revision and id despite edits',async()=>{
 const t=setup();const p=t.sync.submit(null);t.sync.edit(v=>v.items.x.note='newer');
 t.pending.shift().reject(new Error('lost'));await p; const intent=clone(t.sync.submitIntent);
 const retry=t.sync.submit(null);assert.deepEqual(t.calls[1],intent);
 t.pending.shift().resolve({receipt_id:'receipt',counts:{judged:1}});await retry;
 assert.equal(t.sync.values.items.x.note,'newer');assert.equal(t.sync.dirty,true);
});
test('submit intent survives reload and precedes later autosave',async()=>{
 const t=setup();const p=t.sync.submit('old-receipt');t.sync.edit(v=>v.items.x.note='newer');
 t.pending.shift().reject(new Error('lost'));await p;let received;
 const next=new DraftSync('ab','pkg',{revision:0,values:{position:0,items:{x:{note:''}}}},async(path,body)=>{received=body;return {receipt_id:'recovered',counts:{judged:1}};},()=>{},()=>{},t.cache);
 await next.flush();assert.equal(received,undefined);
 await next.submit(null);assert.deepEqual(received,t.calls[0]);assert.equal(next.dirty,true);assert.equal(next.values.items.x.note,'newer');
});
test('409 save needs explicit resolution and retains both versions',async()=>{
 const t=setup();t.sync.edit(v=>v.items.x.note='local');const p=t.sync.flush();
 const e=new Error('conflict');e.status=409;t.pending.shift().reject(e);await p;
 assert.ok(t.sync.conflict);assert.equal(t.sync.values.items.x.note,'local');
 await t.sync.flush();assert.equal(t.calls.length,1);
 await t.sync.resolve({revision:5,values:{position:0,items:{x:{note:'remote'}}}},false);
 assert.equal(t.sync.values.items.x.note,'remote');assert.equal(t.sync.revision,5);assert.equal(t.sync.dirty,false);
});
test('package change never imports old draft or submit intention',()=>{
 const t=setup();t.sync.edit(v=>v.items.x.note='old package');
 const next=new DraftSync('ab','different',{revision:0,values:{position:0,items:{x:{note:'new package'}}}},()=>{},()=>{},()=>{},t.cache);
 assert.equal(next.values.items.x.note,'new package');assert.equal(next.dirty,false);
});
test('definite rejected submit unlocks correction, uncertain failure keeps id',async()=>{
 const t=setup();const p=t.sync.submit(null);const e=new Error('invalid');e.status=422;t.pending.shift().reject(e);await p;assert.equal(t.sync.submitIntent,null);
 const p2=t.sync.submit(null);t.pending.shift().reject(new Error('offline'));await p2;assert.ok(t.sync.submitIntent);
});
test('old idempotent ack cannot regress a newer observed server revision',async()=>{
 const t=setup();t.sync.edit(v=>v.items.x.note='old');const p=t.sync.flush();t.pending.shift().reject(new Error('lost'));await p;
 const s=new DraftSync('ab','pkg',{revision:2,values:{position:0,items:{x:{note:'new server'}}}},async()=>({revision:1,values:t.calls[0].values}),()=>{},()=>{},t.cache);
 await s.flush();assert.ok(s.conflict);assert.equal(s.revision,2);assert.equal(s.dirty,true);assert.equal(s.values.items.x.note,'old');
});
test('draft 422 releases invalid request and corrected edit saves with new id',async()=>{
 const t=setup();t.sync.edit(v=>v.items.x.note='invalid');const p=t.sync.flush();const e=new Error('invalid');e.status=422;t.pending.shift().reject(e);await p;
 assert.equal(t.sync.pending,null);assert.equal(t.sync.dirty,true);t.sync.edit(v=>v.items.x.note='corrected');const p2=t.sync.flush();
 assert.notEqual(t.calls[0].request_id,t.calls[1].request_id);assert.equal(t.calls[1].values.items.x.note,'corrected');t.pending.shift().resolve({revision:1});await p2;assert.equal(t.sync.dirty,false);
});
test('cache A to B to C retires exact recovered snapshot, never arbitrary recovery',()=>{
 const map=new Map();const storage={get length(){return map.size;},key:i=>[...map.keys()][i],getItem:k=>map.get(k)||null,setItem:(k,v)=>map.set(k,v)};
 const a=new DraftCache(storage,'pkg','A'),b=new DraftCache(storage,'pkg','B'),c=new DraftCache(storage,'pkg','C');
 const draft={package_revision:'pkg',dirty:true,pending:{body:{request_id:'R'}},values:{note:'old'}};a.save('ab',draft);
 assert.equal(b.own('ab'),null);assert.equal(b.candidates('ab').length,1);b.claim('ab',b.candidates('ab')[0]);
 b.save('ab',{...draft,dirty:false,pending:null,values:{note:'new'}});assert.equal(c.candidates('ab').length,0);assert.equal(a.own('ab'),null);
 a.save('ab',{...draft,values:{note:'still active new edit'}});assert.equal(c.candidates('ab').length,1);
 b.save('ab',{...draft,values:{note:'other unsynced'}});assert.equal(c.candidates('ab').length,2);assert.equal(c.own('ab'),null);
});
test('401 and 500 retain identical pending request after later edits',async()=>{
 for(const status of [401,500]){
  const t=setup();t.sync.edit(v=>v.items.x.note='first');const p=t.sync.flush();const error=new Error('retry later');error.status=status;t.pending.shift().reject(error);await p;
  t.sync.edit(v=>v.items.x.note='later');const p2=t.sync.flush();assert.deepEqual(t.calls[1],t.calls[0]);t.pending.shift().reject(error);await p2;
 }
});
test('old ack conflict survives reload and gates writes until explicit local or server choice',async()=>{
 for(const keepLocal of [true,false]){
  const t=setup();t.sync.edit(v=>v.items.x.note='old');const p=t.sync.flush();t.pending.shift().reject(new Error('lost'));await p;
  const server={revision:2,values:{position:0,items:{x:{note:'new server'}}}};let cached;
  const first=new DraftSync('ab','pkg',server,async()=>({revision:1,values:t.calls[0].values}),v=>cached=clone(v),()=>{},t.cache);
  await first.flush();assert.ok(first.conflict);
  const calls=[];const reloaded=new DraftSync('ab','pkg',server,async(path,body)=>{calls.push(clone(body));return {revision:3};},v=>cached=clone(v),()=>{},cached);
  assert.ok(reloaded.conflict);assert.equal(reloaded.values.items.x.note,'old');await reloaded.flush();assert.equal(calls.length,0);
  reloaded.edit(v=>v.items.x.note='local corrected');await reloaded.flush();assert.equal(calls.length,0);
  await reloaded.resolve(server,keepLocal);assert.equal(cached.conflict,false);
  const again=new DraftSync('ab','pkg',server,async(path,body)=>{calls.push(clone(body));return {revision:3};},()=>{},()=>{},cached);
  assert.equal(again.conflict,null);await again.flush();assert.equal(calls.length,keepLocal?1:0);
  assert.equal(again.values.items.x.note,keepLocal?'local corrected':'new server');
 }
});
