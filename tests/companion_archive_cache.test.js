const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const {webcrypto,createHash}=require('node:crypto');
const modulePath=__dirname+'/../tools/companion_archive_cache.js';
const stable=v=>Array.isArray(v)?'['+v.map(stable).join(',')+']':v&&typeof v==='object'?'{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+stable(v[k])).join(',')+'}':JSON.stringify(v);
const hash=v=>createHash('sha256').update(v).digest('hex');
const scope={person:'test',relationship_id:'test_father',viewer:'father',memory_release:null};
class Store {
 constructor(){this.meta={generation:'first',namespace:'',revision:'',disabled:false};this.files=new Map();this.fail=false;}
 async snapshot(){if(this.fail)throw Error('storage');return {...this.meta};}
 async invalidate(){this.meta.generation=String(Math.random());return {...this.meta};}
 async bind(namespace,revision,files,generation,disabled,guard){if(guard)guard();if(this.fail)throw Error('storage');if(generation!==undefined)this.check(generation);if(typeof disabled==='boolean')this.meta.disabled=disabled;if(disabled===true)this.files.clear();if(this.meta.namespace!==namespace||this.meta.revision!==revision){this.meta={...this.meta,generation:String(Math.random()),namespace,revision};for(const [k,v] of this.files)if(v.namespace!==namespace||!files.some(f=>f.path===v.path&&f.sha256===v.sha256))this.files.delete(k);}return {...this.meta};}
 check(g){if(g!==this.meta.generation){let e=Error('stale');e.stale=true;throw e;}}
 async get(path,g){this.check(g);if(this.fail)throw Error('storage');return this.files.get(path);}
 async put(value,g){this.check(g);if(this.fail)throw Error('storage');this.files.set(value.path,structuredClone(value));}
 async remove(path,g){this.check(g);this.files.delete(path);}
 async clear(disabled,guard,generation){if(guard)guard();if(generation!==undefined)this.check(generation);this.meta={...this.meta,generation:String(Math.random()),namespace:'',revision:'',disabled:disabled===undefined?this.meta.disabled:disabled};this.files.clear();return {...this.meta};}
 async current(g,guard,path){this.check(g);return {...this.meta,...(path===undefined?{}:{recordPresent:this.files.has(path)})};}
}
function fixture(store=new Store()){
 const api=require(modulePath);let id='11111111-1111-4111-8111-111111111111',bad=null,invalidated=0,liveScope=structuredClone(scope);
 const bodies={'data/chat_context.json':{...scope,message_shards:['messages-2000.json']},'data/messages-2000.json':[{...scope,text:'synthetic'}],'data/memories.json':{...scope,entries:[]},'data/transcripts.json':{...scope,entries:[]}};
 const bytes=()=>Object.fromEntries(Object.entries(bodies).map(([p,v])=>[p,new TextEncoder().encode(JSON.stringify(v)).buffer]));
 let manifest;function refresh(){const b=bytes();const base={schema_version:1,scope:structuredClone(liveScope),scope_revision:hash(stable(liveScope)),context_path:'data/chat_context.json',files:Object.entries(b).sort(([a],[b])=>a.localeCompare(b)).map(([path,raw])=>({path,bytes:raw.byteLength,sha256:hash(Buffer.from(raw))}))};manifest={...base,revision:hash(stable(base))};}refresh();
 const calls=[],authority=[];
 const options={scope:structuredClone(scope),contextPath:'data/chat_context.json',manifestPath:'data/archive-cache-manifest.json',origin:'https://synthetic.test',crypto:webcrypto,store,
   fetch:async(url,opts)=>{authority.push({url,opts});if(bad==='network')throw Error('offline');return {ok:![401,403].includes(bad),status:bad||200,redirected:bad==='redirect',json:async()=>{if(bad==='json')throw Error('bad');return url.includes('get-identity')?(bad==='missing'?{err:'no app token set'}:{account_id:'a'.repeat(32),user_uuid:id}):manifest;}};},
   transport:async path=>{calls.push(path);return bytes()[path];},
   validate:async(path,data)=>{if(data.person!==scope.person&&!(Array.isArray(data)&&data.every(r=>r.person===scope.person)))throw Error('scope');},
   invalidate:()=>invalidated++,status:()=>{},notify:()=>{}};
 const client=new api.ArchiveDeviceCache(options);
 return {client,options,store,calls,authority,bodies,refresh,get manifest(){return manifest;},set bad(v){bad=v;},set identity(v){id=v;},get invalidated(){return invalidated;},
  release(revision,accept=false){const binding={release_id:'synthetic',release_revision:revision.repeat(64),source_sha256:'c'.repeat(64),card_revisions:{card:'d'.repeat(64)}};liveScope.memory_release=binding;bodies['data/chat_context.json'].memory_release=binding;for(const p of Object.keys(bodies))if(p.startsWith('data/memories'))delete bodies[p];bodies['data/memories-'+binding.release_revision+'.json']={...scope,entries:[],release_revision:binding.release_revision};if(accept)options.scope=structuredClone(liveScope);refresh();}
 };
}
test('cache module exists',()=>assert(fs.existsSync(modulePath),'persistent cache implementation missing'));

test('automatic authority cleanup cannot erase another client newer generation',async()=>{
 for(const snapshotUnavailable of [false,true]){
  const a=fixture();await a.client.prepare();let entered,release;const atIdentity=new Promise(r=>entered=r),held=new Promise(r=>release=r);
  if(snapshotUnavailable)a.store.snapshot=async()=>{throw Error('unavailable');};
  a.options.fetch=async()=>{entered();await held;throw Error('expired old request');};
  const pending=a.client.prepare(),rejected=assert.rejects(pending);await atIdentity;
  const b=fixture(a.store);b.store.snapshot=async()=>({...b.store.meta});b.bodies['data/transcripts.json'].changed=7;b.refresh();await b.client.prepare();const generation=b.store.meta.generation;
  release();await rejected;assert.equal(b.store.meta.generation,generation);assert.equal(b.store.files.size,4);assert(b.client.retained);
  assert.equal(a.client.memory.size,0);assert.equal(a.client.retained,false);
 }
});

test('preflight cannot adopt policy changed before it starts with notification withheld',async()=>{
 const f=fixture();let token='old';f.options.invalidationToken=()=>token;await f.client.prepare();token='new';f.authority.length=0;
 assert.equal(f.client.stageForSend(),null);assert.equal(f.authority.length,0);await f.client.finishForSend();assert.equal(f.authority.length,6);
 assert(f.client.stageForSend());
});

test('owned automatic failure returns a terminal feedback proof after internal invalidation',async()=>{
 const f=fixture();await f.client.prepare();f.bad=401;let error;try{await f.client.prepare();}catch(e){error=e;}
 assert(error);assert.deepEqual(error.failureProof,{epoch:f.client.epoch,owner:f.client.operationOwner});assert.equal(f.client.memory.size,0);assert.equal(f.store.files.size,0);
});

test('late successful automatic clear cannot notify after B has rebound its cleared generation',async()=>{
 const a=fixture();await a.client.prepare();let entered,release,notified=0;const atClear=new Promise(r=>entered=r),held=new Promise(r=>release=r),clear=a.store.clear.bind(a.store);
 a.options.notify=()=>notified++;a.store.clear=async(...args)=>{const result=await clear(...args);entered();await held;return result;};
 a.bad=401;const pending=a.client.prepare(),rejected=assert.rejects(pending);await atClear;
 const b=fixture(a.store);await b.client.prepare();const generation=b.store.meta.generation;
 release();await rejected;assert.equal(notified,0);assert.equal(b.store.meta.generation,generation);assert.equal(b.store.files.size,4);assert(b.client.retained);
});

test('D first-phase await boundaries cannot mutate a newer completed owner',async()=>{
 for(const boundary of ['identity1','manifest','identity2','snapshot','get','hash','validate','membership']){
  const f=fixture();await f.client.prepare();let enter,release,n=0,armed=true;
  const entered=new Promise(r=>enter=r),held=new Promise(r=>release=r);
  const obj=['identity1','manifest','identity2','validate'].includes(boundary)?f.options:boundary==='hash'?f.client:f.store;
  const method=['identity1','manifest','identity2'].includes(boundary)?'fetch':boundary==='membership'?'current':boundary;
  const original=obj[method].bind(obj),index={identity1:1,manifest:2,identity2:3}[boundary]||1;
  obj[method]=async(...args)=>{if(armed&&++n===index){enter();await held;}return original(...args);};
  const op=f.client.stageForSend(),rejected=assert.rejects(op.localReady);await entered;armed=false;
  f.client.forget(false);await f.client.prepare();const epoch=f.client.epoch,owner=f.client.operationOwner;
  release();await rejected;assert.equal(f.client.epoch,epoch,boundary);assert.equal(f.client.operationOwner,owner,boundary);
  assert.equal(f.client.memory.size,4,boundary);assert.equal(f.store.files.size,4,boundary);assert(f.client.retained,boundary);
 }
});

test('late failed clear cannot overwrite a newer preparation status',async()=>{
 const f=fixture();await f.client.prepare();let entered,fail;const atClear=new Promise(r=>entered=r),held=new Promise((_,r)=>fail=r),statuses=[];
 f.options.status=s=>statuses.push(s);f.store.clear=async()=>{entered();return held;};
 const a=f.client.clear(),rejected=assert.rejects(a);await atClear;const b=f.client.prepare();fail(Error('clear failed'));await rejected;await b;
 assert(f.client.retained);assert.equal(f.client.memory.size,4);assert.equal(f.store.files.size,4);
 assert(!statuses.some(s=>s.includes('未确认清除')));
});

test('D warm preparation parks after first gate without effects; explicit Send supplies fresh terminal gate',async()=>{
 const f=fixture();await f.client.prepare();f.authority.length=0;f.calls.length=0;let writes=0;
 const put=f.store.put.bind(f.store);f.store.put=async(...a)=>{writes++;return put(...a);};
 assert.equal(typeof f.client.stageForSend,'function');const op=f.client.stageForSend();assert(op);assert.equal(f.client.stageForSend(),op);
 await op.localReady;assert.equal(op.phase,'staged');assert.equal(f.authority.length,3);assert.equal(f.calls.length,0);assert.equal(writes,0);
 const result=await f.client.finishForSend();assert.equal(result.files.size,4);assert.equal(f.authority.length,6);assert.equal(op.phase,'consumed');assert.equal(writes,0);
 await f.client.finishForSend();assert.equal(f.authority.length,12,'completed terminal authorization cannot be reused');
});

test('late rejected validator A cannot delete B memory or persistent files',async()=>{
 for(const persistent of [false,true]){
  const f=fixture();await f.client.prepare();let entered,rejectOld;const atValidation=new Promise(r=>entered=r),oldFailure=new Promise((_,r)=>rejectOld=r),validate=f.options.validate;
  f.options.validate=async(p,d)=>{if(p===f.options.contextPath){entered();await oldFailure;}return validate(p,d);};
  const a=f.client.prepare();const rejected=assert.rejects(a);await atValidation;f.client.forget(persistent);f.options.validate=validate;
  await f.client.prepare();const before=[...f.client.memory.keys()];rejectOld(Error('old validation rejected'));await rejected;
  assert.deepEqual([...f.client.memory.keys()],before);assert.equal(f.store.files.size,4);assert.equal(f.client.retained,true);
 }
});

test('D parked descriptor cannot be changed; dormant raw is revalidated; missing storage repaired explicitly',async()=>{
 for(const damage of ['descriptor','raw','missing','corrupt-store']){
  const f=fixture();await f.client.prepare();const op=f.client.stageForSend();await op.localReady;f.calls.length=0;
  if(damage==='descriptor'){const original=op.first.manifest.files[0].sha256;op.first.manifest.files[0].sha256='f'.repeat(64);assert.equal(op.first.manifest.files[0].sha256,original);}
  if(damage==='raw')new Uint8Array(op.raw.get('data/transcripts.json'))[0]=0;
  if(damage==='missing')await f.store.remove('data/transcripts.json',op.meta.generation);
  if(damage==='corrupt-store')f.store.files.get('data/transcripts.json').raw=new Uint8Array([0]).buffer;
  const result=await f.client.finishForSend();assert.equal(result.files.size,4);assert.equal(f.store.files.size,4);assert(f.client.retained);
  assert.equal(f.calls.length,['missing','corrupt-store'].includes(damage)?1:0);
 }
});

test('D idle version or identity changes reject instead of adopting; notifications not needed for policy',async()=>{
 for(const kind of ['identity','version','disable','clear']){
  const f=fixture();let disabled=false;f.options.disabledPreference=()=>disabled;await f.client.prepare();const op=f.client.stageForSend();await op.localReady;
  if(kind==='identity')f.identity='22222222-2222-4222-8222-222222222222';
  if(kind==='version'){f.bodies['data/transcripts.json'].entries=[];f.bodies['data/transcripts.json'].synthetic_revision=2;f.refresh();}
  if(kind==='disable')disabled=true;
  if(kind==='clear')await f.store.clear();
  await assert.rejects(f.client.finishForSend());
 }
});

test('D ordinary retry supersedes parked work and never waits for Send; failure coalesces keystrokes',async()=>{
 const f=fixture();assert.equal(f.client.stageForSend(),null);await f.client.prepare();const op=f.client.stageForSend();await op.localReady;
 await f.client.prepare();assert.equal(op.phase,'invalidated');assert.equal(f.client.deferred,null);
 const get=f.store.get.bind(f.store);f.store.get=async()=>undefined;const bad=f.client.stageForSend();await assert.rejects(bad.localReady);assert.equal(f.client.stageForSend(),null);
 f.store.get=get;await f.client.finishForSend();assert(f.client.retained);assert(f.client.stageForSend());
});

test('D failed speculative corrupt-store check forces later explicit repair instead of healthy-memory shortcut',async()=>{
 const f=fixture();await f.client.prepare();f.store.files.get('data/transcripts.json').raw=new Uint8Array([0]).buffer;f.calls.length=0;
 const op=f.client.stageForSend();await assert.rejects(op.localReady);await f.client.finishForSend();
 assert.deepEqual(f.calls,['data/transcripts.json']);assert(f.store.files.get('data/transcripts.json').raw.byteLength>1);
});

test('D resume identity/manifest gate never begins before Send even with early promotion',async()=>{
 const f=fixture();await f.client.prepare();f.authority.length=0;let entered,release;const atGate=new Promise(r=>entered=r),hold=new Promise(r=>release=r),fetch=f.options.fetch;
 f.options.fetch=async(...args)=>{if(f.authority.length===0){entered();await hold;}return fetch(...args);};
 const op=f.client.stageForSend();await atGate;const done=f.client.finishForSend();release();await done;assert.equal(f.authority.length,6);assert.equal(op.phase,'consumed');
});

test('D Send cannot reuse a normal terminal gate launched before its invocation',async()=>{
 const f=fixture();let entered,release;const atTerminal=new Promise(r=>entered=r),hold=new Promise(r=>release=r),fetch=f.options.fetch;
 f.options.fetch=async(...args)=>{if(f.authority.length===3){entered();await hold;}return fetch(...args);};
 const normal=f.client.prepare();await atTerminal;const send=f.client.finishForSend();release();await normal;await send;
 assert.equal(f.authority.length,12,'must run a new transaction after pre-click normal terminal');
});

test('D parked transaction rejects live auth failures and clears private cache',async()=>{
 for(const bad of ['missing',401,403,'redirect','network','json']){
  const f=fixture();await f.client.prepare();const op=f.client.stageForSend();await op.localReady;f.bad=bad;
  await assert.rejects(f.client.finishForSend());assert.equal(f.store.files.size,0);assert.equal(f.client.retained,false);
 }
});

test('D late speculative validator error cannot alter replacement B state',async()=>{
 const f=fixture();await f.client.prepare();let entered,rejectOld;const atValidation=new Promise(r=>entered=r),hold=new Promise((_,r)=>rejectOld=r),validate=f.options.validate;
 f.options.validate=async(p,d)=>{if(p===f.options.contextPath){entered();await hold;}return validate(p,d);};
 const op=f.client.stageForSend();const rejected=assert.rejects(op.localReady);await atValidation;
 f.client.forget(false);f.options.validate=validate;await f.client.prepare();const identity=f.client.identity;
 rejectOld(Error('late speculative failure'));await rejected;
 assert.equal(f.client.identity,identity);assert.equal(f.client.memory.size,4);assert.equal(f.store.files.size,4);assert(f.client.retained);
});

test('D refresh A cannot clear B completed in its internally advanced epoch',async()=>{
 const f=fixture();await f.client.prepare();const oldRevision=f.manifest.revision;
 let entered,release,held=false,n=0;const atBind=new Promise(r=>entered=r),hold=new Promise(r=>release=r),bind=f.store.bind.bind(f.store),fetch=f.options.fetch;
 f.options.fetch=async(...args)=>{if(++n===4){f.bodies['data/transcripts.json'].changed=1;f.refresh();}return fetch(...args);};
 f.store.bind=async(...args)=>{if(args[1]!==oldRevision&&!held){held=true;entered();await hold;}return bind(...args);};
 const old=f.client.prepare();const rejection=assert.rejects(old);await atBind;
 f.options.fetch=fetch;await f.client.prepare();const epoch=f.client.epoch;
 release();await rejection;assert.equal(f.client.epoch,epoch);assert.equal(f.store.files.size,4);assert.equal(f.client.memory.size,4);assert(f.client.retained);
});

test('D refresh failure never clears a newer persistent generation from another client',async()=>{
 const a=fixture();await a.client.prepare();let entered,release,n=0,held=false;const atBind=new Promise(r=>entered=r),hold=new Promise(r=>release=r),bind=a.store.bind.bind(a.store),fetch=a.options.fetch,oldRev=a.manifest.revision;
 a.options.fetch=async(...args)=>{if(++n===4){a.bodies['data/transcripts.json'].changed=1;a.refresh();}return fetch(...args);};
 a.store.bind=async(...args)=>{if(args[1]!==oldRev&&!held){held=true;entered();await hold;}return bind(...args);};
 const old=a.client.prepare();const rejection=assert.rejects(old);await atBind;
 const b=fixture(a.store);b.bodies['data/transcripts.json'].changed=1;b.refresh();await b.client.prepare();const generation=b.store.meta.generation;
 release();await rejection;assert.equal(b.store.meta.generation,generation);assert.equal(b.store.files.size,4);assert(b.client.retained);
});

test('normal preparation cannot claim retained after same-generation deletion during terminal gate',async()=>{
 const f=fixture();await f.client.prepare();let n=0,writes=0;const fetch=f.options.fetch,put=f.store.put.bind(f.store);
 f.options.fetch=async(...args)=>{if(++n===4)await f.store.remove('data/transcripts.json',f.store.meta.generation);return fetch(...args);};
 f.store.put=async(...args)=>{writes++;return put(...args);};
 const result=await f.client.prepare();assert.equal(result.files.size,4);assert.equal(f.client.retained,false);assert.equal(f.store.files.size,3);assert.equal(writes,0,'no repair after terminal gate');
});

test('verified warm bytes do not rewrite persistent records but keep all six authority checks',async()=>{
 const f=fixture();await f.client.prepare();let writes=0;const put=f.store.put.bind(f.store);f.store.put=async(...a)=>{writes++;return put(...a);};
 f.authority.length=0;await f.client.prepare();assert.equal(writes,0);assert.equal(f.authority.length,6);
 const next=fixture(f.store);await next.client.prepare();assert.equal(writes,0);assert.equal(next.authority.length,6);
});

test('two clients: same-generation removal with failed replacement is repaired from healthy memory',async()=>{
 const a=fixture();await a.client.prepare();const generation=a.store.meta.generation;
 const b=fixture(a.store);a.store.files.get('data/transcripts.json').raw=new Uint8Array([0]).buffer;
 b.options.transport=async()=>{throw Error('replacement offline');};
 await assert.rejects(b.client.prepare());assert.equal(a.store.meta.generation,generation);
 assert.equal(a.store.files.has('data/transcripts.json'),false);
 let writes=0;const put=a.store.put.bind(a.store);a.store.put=async(...args)=>{writes++;return put(...args);};
 await a.client.prepare();assert.equal(a.store.files.size,4,'retained must include the deleted file');
 assert.equal(writes,1);assert.equal(a.client.retained,true);
});
test('semantic validation result is committed with the same fully authorized snapshot',async()=>{
 const f=fixture();f.options.validate=async path=>({validated:path});const result=await f.client.prepare();
 assert.equal(result.validations.get('data/memories.json').validated,'data/memories.json');
});
test('first load stores only allowlist; refresh reads local without bulk transfer',async()=>{
 const f=fixture();await f.client.prepare();assert.equal(f.calls.length,4);assert.equal(f.store.files.size,4);
 const second=fixture(f.store);await second.client.prepare();assert.equal(second.calls.length,0);assert.equal(second.authority.length,6);
 for(const a of second.authority){assert.equal(a.opts.cache,'no-store');assert.equal(a.opts.redirect,'error');assert.equal(a.opts.credentials,'same-origin');assert(a.url.includes('?'));}
 assert(!JSON.stringify([...f.store.files.values()]).includes('11111111-1111'));assert(![...f.store.files.keys()].some(p=>/session|audio/.test(p)));
});
test('one file change, eviction and damaged bytes download only required file',async()=>{
 const f=fixture();await f.client.prepare();f.calls.length=0;f.bodies['data/messages-2000.json'][0].text='new';f.refresh();await f.client.prepare();assert.deepEqual(f.calls,['data/messages-2000.json']);
 const second=fixture(f.store);await second.client.prepare();second.calls.length=0;second.client.forget();second.store.files.get('data/transcripts.json').raw=new Uint8Array([1]).buffer;await second.client.prepare();assert.deepEqual(second.calls,['data/transcripts.json']);
 second.client.forget();second.store.files.delete('data/memories.json');second.calls.length=0;await second.client.prepare();assert.deepEqual(second.calls,['data/memories.json']);
});
test('online authority failures reject even warm cache and clear private entries',async()=>{
 for(const bad of ['missing',401,403,'redirect','network','json']){const f=fixture();await f.client.prepare();f.bad=bad;await assert.rejects(f.client.prepare());assert.equal(f.store.files.size,0);assert(f.invalidated>0);}
});
test('malformed/wrong-scope/extra-path manifest fails closed',async()=>{
 for(const mutate of [m=>m.schema_version=2,m=>m.scope.viewer='owner',m=>m.files.push({...m.files[0],path:'data/sessions_father.json'}),m=>m.files[0].sha256='x']){
  const f=fixture();mutate(f.manifest);await assert.rejects(f.client.prepare());assert.equal(f.calls.length,0);
 }
});
test('identity changes during gate are rejected; a new stable identity cannot reuse old entries',async()=>{
 const f=fixture();await f.client.prepare();f.calls.length=0;f.identity='22222222-2222-4222-8222-222222222222';await assert.rejects(f.client.prepare());assert.equal(f.store.files.size,0);
 await f.client.prepare();assert.equal(f.calls.length,4);
 const g=fixture();const original=g.options.fetch;let n=0;g.options.fetch=async(...args)=>{if(++n===3)g.identity='22222222-2222-4222-8222-222222222222';return original(...args);};await assert.rejects(g.client.prepare());
});
test('clear/disable invalidate delayed response and cannot repopulate; retry works',async()=>{
 for(const disabled of [undefined,true]){const f=fixture();let release;const gate=new Promise(r=>release=r),transport=f.options.transport;f.options.transport=async p=>{await gate;return transport(p);};const pending=f.client.prepare();await new Promise(r=>setTimeout(r,20));await f.client.clear(disabled);release();await assert.rejects(pending);assert.equal(f.store.files.size,0);await f.client.prepare();assert.equal(f.store.files.size,disabled?0:4);}
});
test('cross-tab persistent generation prevents delayed stale writes',async()=>{
 const f=fixture();await f.client.prepare();const second=fixture(f.store);let release;const gate=new Promise(r=>release=r);second.options.validate=async()=>gate;const pending=second.client.prepare();await new Promise(r=>setTimeout(r,20));await f.client.clear(true);release();await assert.rejects(pending);assert.equal(f.store.files.size,0);
});
test('storage unavailable/quota is online-only, never an authority fallback',async()=>{
 const f=fixture();f.store.fail=true;await f.client.prepare();assert.equal(f.calls.length,4);assert.equal(f.store.files.size,0);assert.equal(f.client.retained,false);f.bad='missing';await assert.rejects(f.client.prepare());
});
test('quota during writes preserves online validation but never claims retained',async()=>{
 const f=fixture();f.store.put=async()=>{throw Error('QuotaExceededError');};await f.client.prepare();assert.equal(f.client.retained,false);assert.equal(f.store.files.size,0);assert.equal(f.calls.length,4);
});
test('persistent generation read failure cannot unblock a stale preparation',async()=>{
 const f=fixture();f.store.current=async()=>{throw Error('storage unavailable');};await assert.rejects(f.client.prepare());assert.equal(f.store.files.size,0);
});
test('inflight dedup and partial retry reuse validated successful pieces',async()=>{
 const f=fixture();let fail=true;const original=f.options.transport;f.options.transport=async p=>{if(p.includes('transcripts')&&fail)throw Error('temporary');return original(p);};const a=f.client.prepare(),b=f.client.prepare();assert.strictEqual(a,b);await assert.rejects(a);fail=false;await f.client.prepare();assert.equal(f.calls.length,4);
});
test('review R1: cross-tab clear during authority gate cannot adopt new generation and repopulate',async()=>{
 const f=fixture();await f.client.prepare();f.calls.length=0;let release;const gate=new Promise(r=>release=r),fetch=f.options.fetch;f.options.fetch=async(...a)=>{await gate;return fetch(...a);};
 const pending=f.client.prepare();await new Promise(r=>setTimeout(r,10));await f.store.clear();release();await assert.rejects(pending);assert.equal(f.store.files.size,0);assert.equal(f.calls.length,0);
});
test('review R2: failed bind cannot authorize stale in-memory content after a clear',async()=>{
 const f=fixture();await f.client.prepare();f.calls.length=0;let release;const gate=new Promise(r=>release=r),fetch=f.options.fetch;f.options.fetch=async(...a)=>{await gate;return fetch(...a);};
 const pending=f.client.prepare();await new Promise(r=>setTimeout(r,10));await f.store.clear();f.store.bind=async()=>{throw Error('storage');};release();await assert.rejects(pending);assert.equal(f.store.files.size,0);
});
test('review R3: lifecycle invalidation prevents a delayed persistent put',async()=>{
 const f=fixture();let release;const gate=new Promise(r=>release=r),put=f.store.put.bind(f.store);f.store.put=async(...a)=>{await gate;return put(...a);};
 const pending=f.client.prepare();await new Promise(r=>setTimeout(r,10));f.client.forget();await new Promise(r=>setTimeout(r,10));release();await assert.rejects(pending);assert.equal(f.store.files.size,0);
});
test('review R4: failed disable remains disabled when storage recovers',async()=>{
 const f=fixture();await f.client.prepare();let disabled=false;f.options.disabledPreference=()=>disabled;const clear=f.store.clear.bind(f.store);f.store.clear=async()=>{throw Error('storage');};await f.client.clear(true);disabled=true;f.store.clear=clear;
 await f.client.prepare();assert.equal(f.client.disabled,true);assert.equal(f.client.retained,false);assert.equal(f.store.files.size,0);
});
test('review R5: page invalidation completely settles active reply state',()=>{
 const vm=require('node:vm'),src=fs.readFileSync(__dirname+'/../tools/companion_archive_cache_page.js','utf8');const body=src.match(/^function updateArchiveRevision\(revision\) \{.*?^\}/ms)[0]+'\n'+src.slice(src.indexOf('function invalidateArchivePage()'),src.indexOf('function notifyArchiveChange'));
 let cancelled=0,aborted=0;const revisionNode={textContent:'previous verified revision'};const s={archiveLifecycleInvalidation:false,archiveReplyPaused:false,archiveDiscardReplies(){},document:{querySelectorAll:()=>[revisionNode]},archiveVerifiedRevision:'old',archivePageOperation:0,archiveSendProof:null,invalidateDataArchive(){},Map,reportDataProgress(){},sendGeneration:1,streaming:true,sendPending:true,cancelVoiceTurn(){},cancelActiveSend(){cancelled++;},controller:{abort(){aborted++;}},sendBtn:{classList:{remove(){}},textContent:'stop'},settingsComplete:()=>true};vm.runInNewContext(body,s);s.invalidateArchivePage();assert.equal(s.streaming,false);assert.equal(s.controller,null);assert.equal(s.sendPending,false);assert.equal(cancelled,1);assert.equal(aborted,1);assert.equal(s.cancelActiveSend,null);assert.equal(s.archiveVerifiedRevision,'');assert.equal(revisionNode.textContent,'资料版本待核验');
});
test('review corrupt record is removed before a failing replacement download',async()=>{
 const f=fixture();await f.client.prepare();f.client.forget();await new Promise(r=>setTimeout(r,10));f.store.files.get('data/transcripts.json').raw=new Uint8Array([0]).buffer;const fetch=f.options.transport;f.options.transport=async p=>{if(p.includes('transcripts'))throw Error('network');return fetch(p);};await assert.rejects(f.client.prepare());assert.equal(f.store.files.has('data/transcripts.json'),false);
});
test('service-token status with an apparent user UUID is rejected',async()=>{
 const f=fixture(),fetch=f.options.fetch;f.options.fetch=async(...args)=>{const r=await fetch(...args);if(args[0].includes('get-identity')){const json=r.json;r.json=async()=>({...await json(),service_token_status:true});}return r;};await assert.rejects(f.client.prepare());assert.equal(f.calls.length,0);
});
test('cached semantic scope failure removes the invalid stored path',async()=>{
 const f=fixture();await f.client.prepare();f.options.validate=async path=>{if(path.includes('chat_context'))throw Error('scope');};await assert.rejects(f.client.prepare());assert.equal(f.store.files.has('data/chat_context.json'),false);
});
test('R3 overlapping failed disable dominates delayed binding, writing and final gate',async()=>{
 for(const boundary of ['bind','put','final']){const f=fixture();let disabled=false;f.options.disabledPreference=()=>disabled;await f.client.prepare();let release,entered;const gate=new Promise(r=>release=r),atGate=new Promise(r=>entered=r);
  if(boundary==='put'){f.bodies['data/messages-2000.json'][0].text='changed synthetic';f.refresh();}
  if(boundary==='bind'||boundary==='put'){const orig=f.store[boundary].bind(f.store);f.store[boundary]=async(...a)=>{entered();await gate;return orig(...a);};}
  else {let n=0;const orig=f.options.fetch;f.options.fetch=async(...a)=>{if(++n===4){entered();await gate;}return orig(...a);};}
  const pending=f.client.prepare();await atGate;disabled=true;release();await assert.rejects(pending,boundary);assert.equal(f.client.retained,false);assert.equal(f.store.files.size,0,boundary);
 }
});
test('R3 disable preference is published before delayed or failed clear completes',async()=>{
 const f=fixture();let observed=false,release;const gate=new Promise(r=>release=r);f.options.notify=d=>{observed=d;};f.store.clear=async()=>{await gate;throw Error('failed');};const pending=f.client.clear(true);assert.equal(observed,true);release();await pending;
});
test('R3 new memory release reuses unchanged same-relationship shards and deletes obsolete memory',async()=>{
 const old=fixture();await old.client.prepare();const fresh=fixture(old.store);fresh.release('a',true);await fresh.client.prepare();assert.deepEqual(fresh.calls.sort(),['data/chat_context.json','data/memories-'+'a'.repeat(64)+'.json'].sort());assert.equal(fresh.store.files.has('data/memories.json'),false);
});
test('R3 old page rejects trusted new release but prunes only obsolete raw before refresh',async()=>{
 const old=fixture();await old.client.prepare();old.calls.length=0;old.release('b');await assert.rejects(old.client.prepare());assert.equal(old.calls.length,0);assert.equal(old.store.files.has('data/memories.json'),false);assert.equal(old.store.files.has('data/messages-2000.json'),true);assert.equal(old.store.files.has('data/chat_context.json'),false);
 const fresh=fixture(old.store);fresh.release('b',true);await fresh.client.prepare();assert.equal(fresh.calls.length,2);
});
test('R3 explicit re-enable is not locked by stale true DB metadata',async()=>{
 const f=fixture();let disabled=false;f.options.disabledPreference=()=>disabled;f.options.notify=d=>{if(d!==undefined)disabled=d;};await f.client.clear(true);const clear=f.store.clear.bind(f.store);f.store.clear=async()=>{throw Error('temporary');};await f.client.clear(false);f.store.clear=clear;await f.client.prepare();assert.equal(f.client.disabled,false);assert.equal(f.client.retained,true);
});
const malformedBindings=[
 ['numeric release_id',b=>b.release_id=123],['array release_id',b=>b.release_id=['synthetic']],
 ['boolean release_id',b=>b.release_id=true],['null release_id',b=>b.release_id=null],
 ['array release_revision',b=>b.release_revision=['a'.repeat(64)]],['numeric release_revision',b=>b.release_revision=123],
 ['array source_sha256',b=>b.source_sha256=['c'.repeat(64)]],['object source_sha256',b=>b.source_sha256={}],
 ['boolean source_sha256',b=>b.source_sha256=true],['null source_sha256',b=>b.source_sha256=null],
 ['array card digest',b=>b.card_revisions.card=['d'.repeat(64)]],['numeric card digest',b=>b.card_revisions.card=123],
 ['null card digest',b=>b.card_revisions.card=null],['boolean card digest',b=>b.card_revisions.card=true],
 ['array card_revisions',b=>b.card_revisions=['d'.repeat(64)]],['string card_revisions',b=>b.card_revisions='bad'],
 ['empty card_revisions',b=>b.card_revisions={}],['extra binding key',b=>b.extra='bad'],['missing binding key',b=>delete b.source_sha256]
];
for(const [name,mutate] of malformedBindings)test('R4 self-consistently hashed malformed '+name+' is authority failure and clears all',async()=>{
 const f=fixture();f.release('a',true);await f.client.prepare();assert.equal(f.store.files.size,4);mutate(f.manifest.scope.memory_release);
 f.manifest.scope_revision=hash(stable(f.manifest.scope));const base={...f.manifest};delete base.revision;f.manifest.revision=hash(stable(base));
 await assert.rejects(f.client.prepare(),e=>e.authority===true&&!e.refresh);assert.equal(f.store.files.size,0);
});
const malformedManifestFields=[
 ['file hash array',m=>m.files[0].sha256=[m.files[0].sha256]],['file hash number',m=>m.files[0].sha256=123],
 ['file path array',m=>m.files[0].path=[m.files[0].path]],['context path array',m=>m.context_path=[m.context_path]],
 ['scope hash array',m=>m.scope_revision=[m.scope_revision]],['file bytes string',m=>m.files[0].bytes=String(m.files[0].bytes)],
 ['files object',m=>m.files={0:m.files[0]}],['version string',m=>m.schema_version='1']
];
for(const [name,mutate] of malformedManifestFields)test('R4 self-consistently hashed malformed '+name+' is authority failure and clears all',async()=>{
 const f=fixture();f.release('a',true);await f.client.prepare();mutate(f.manifest);const base={...f.manifest};delete base.revision;f.manifest.revision=hash(stable(base));
 await assert.rejects(f.client.prepare(),e=>e.authority===true&&!e.refresh);assert.equal(f.store.files.size,0);
});
test('R4 array manifest revision is rejected as authority failure and clears all',async()=>{
 const f=fixture();f.release('a',true);await f.client.prepare();f.manifest.revision=[f.manifest.revision];await assert.rejects(f.client.prepare(),e=>e.authority===true&&!e.refresh);assert.equal(f.store.files.size,0);
});
test('R4 array shard names cannot pass regex coercion with valid content hashes',async()=>{
 const f=fixture();await f.client.prepare();f.bodies['data/chat_context.json'].message_shards=[['messages-2000.json']];f.refresh();await assert.rejects(f.client.prepare(),e=>e.authority===true);assert.equal(f.store.files.size,0);
});


test('unclaimed preflight publishes exactly one owned failure and explicit retry recovers',async()=>{
 const f=fixture(),failures=[];f.options.failed=(error,proof)=>failures.push({error,proof});await f.client.prepare();f.bad=401;
 const op=f.client.stageForSend();await assert.rejects(op.localReady);
 assert.equal(failures.length,1);assert.deepEqual(failures[0].proof,{epoch:f.client.epoch,owner:f.client.operationOwner});
 assert.equal(f.client.retained,false);assert.equal(f.store.files.size,0);
 f.bad=null;await f.client.finishForSend();assert(f.client.retained);assert.equal(failures.length,1);
});

test('claimed preflight failure is returned to Send without duplicate callback',async()=>{
 const f=fixture(),failures=[];f.options.failed=(...args)=>failures.push(args);await f.client.prepare();f.bad=403;
 const op=f.client.stageForSend();await assert.rejects(f.client.finishForSend());await assert.rejects(op.localReady);
 assert.equal(failures.length,0);
});

test('unclaimed A late failure cannot publish against newer B',async()=>{
 for(const boundary of ['identity','cleanup','notify']){
  const f=fixture(),failures=[];f.options.failed=(...args)=>failures.push(args);await f.client.prepare();
  let enter,release;const entered=new Promise(r=>enter=r),held=new Promise(r=>release=r);
  if(boundary==='identity') {const fetch=f.options.fetch;let once=true;f.options.fetch=async(...args)=>{if(once){once=false;enter();await held;throw Error('old authority');}return fetch(...args);};}
  if(boundary==='cleanup'){const clear=f.store.clear.bind(f.store);f.store.clear=async(...args)=>{enter();await held;return clear(...args);};f.bad=401;}
  if(boundary==='notify'){f.options.notify=()=>{f.client.forget(false);enter();};f.bad=401;}
  const op=f.client.stageForSend(),rejected=assert.rejects(op.localReady);await entered;f.bad=null;
  if(boundary!=='notify')f.client.forget(false);
  release();await f.client.prepare();const owner=f.client.operationOwner;await rejected;
  assert.equal(failures.length,0,boundary);assert.equal(f.client.operationOwner,owner);assert(f.client.retained);assert.equal(f.store.files.size,4);
 }
});


test('cleanup final handoff cannot publish A failure status under new B owner',async()=>{
 const f=fixture();await f.client.prepare();const statuses=[];let b;
 f.options.status=text=>statuses.push({text,owner:f.client.operationOwner});
 f.options.notify=()=>{queueMicrotask(()=>{f.bad=null;b=f.client.prepare();statuses.push({text:'B STARTED',owner:f.client.operationOwner});});};
 f.bad=401;await assert.rejects(f.client.prepare());await b;
 const start=statuses.findIndex(x=>x.text==='B STARTED');assert(start>=0);
 const late=statuses.slice(start+1).filter(x=>x.text.includes('无法验证'));
 assert.equal(late.length,0,JSON.stringify(statuses));assert(f.client.retained);assert.equal(f.store.files.size,4);
});

test('manifest progress reports exact cold and warm counts only for current ownership',async()=>{
 const f=fixture(),seen=[];f.options.progress=(p,e,o)=>{assert.equal(e,f.client.epoch);assert.equal(o,f.client.operationOwner);seen.push({...p});};
 await f.client.prepare();assert.deepEqual(seen[0],{total:4,downloaded:0,verified:0});assert.deepEqual(seen.at(-1),{total:4,downloaded:4,verified:4});assert(seen.every(p=>p.total===4&&p.downloaded>=p.verified&&p.downloaded<=4));
 seen.length=0;const downloads=f.calls.length;await f.client.prepare();assert.equal(f.calls.length,downloads);assert.deepEqual(seen.at(-1),{total:4,downloaded:4,verified:4});
});

test('late validator cannot publish progress into newer ready preparation',async()=>{
 const f=fixture(),seen=[];let entered,release,hold=true;const at=new Promise(r=>entered=r),gate=new Promise(r=>release=r),validate=f.options.validate;
 f.options.progress=(p,e,o)=>seen.push({p:{...p},e,o});f.options.validate=async(...a)=>{if(hold){hold=false;entered();await gate;}return validate(...a);};
 const a=f.client.prepare(),rejected=assert.rejects(a);await at;f.client.forget(false);await f.client.prepare();const before=JSON.stringify(seen);release();await rejected;assert.equal(JSON.stringify(seen),before);assert.equal(seen.at(-1).o,f.client.operationOwner);
});


test('authority failures retain safe exact resource and failure labels',async()=>{
 for(const [bad,code] of [[401,'HTTP_401'],[403,'HTTP_403'],['network','NETWORK'],['json','JSON'],['redirect','REDIRECT']]){
  const f=fixture();await f.client.prepare();f.bad=bad;
  await assert.rejects(f.client.prepare(),e=>e.authority && e.dataResource==='IDENTITY' && e.dataCode===code);
  assert.equal(f.store.files.size,0);assert.equal(f.client.memory.size,0);
 }
 const f=fixture(),fetch=f.options.fetch;
 f.options.fetch=async(url,opts)=>url.includes('get-identity')?fetch(url,opts):{ok:false,status:403,redirected:false};
 await assert.rejects(f.client.prepare(),e=>e.authority && e.dataResource==='MANIFEST' && e.dataCode==='HTTP_403');
 assert.equal(f.calls.length,0);assert.equal(f.store.files.size,0);
});

test('versioned context transition rejects old page and accepts freshly bound page',async()=>{
 const f=fixture();await f.client.prepare();const oldManifest=f.manifest;
 const contextPath='data/chat_context.language-lines-20261105-v1.json';
 const raw=new TextEncoder().encode(JSON.stringify(f.bodies['data/chat_context.json']));
 const base={...oldManifest,context_path:contextPath,files:oldManifest.files.map(x=>x.path===oldManifest.context_path?{...x,path:contextPath}:x)};
 delete base.revision;const next={...base,revision:hash(stable(base))},fetch=f.options.fetch;
 f.options.fetch=async(url,opts)=>url.includes('get-identity')?fetch(url,opts):{ok:true,redirected:false,json:async()=>next};
 await assert.rejects(f.client.prepare(),e=>!!e.refresh);
 assert.equal(f.client.retained,false);
 f.options.contextPath=contextPath;const transport=f.options.transport;
 f.options.transport=async path=>path===contextPath?raw.buffer:transport(path);
 const result=await f.client.prepare();assert(result.files.has(contextPath));assert(!result.files.has(oldManifest.context_path));
 assert.equal(f.store.files.size,4);assert(!f.store.files.has(oldManifest.context_path));
});


test('identity schema rejection retains authority and fixed IDENTITY:SCHEMA diagnosis',async()=>{
 const f=fixture();await f.client.prepare();f.bad='missing';
 await assert.rejects(f.client.prepare(),e=>e.authority && e.dataResource==='IDENTITY' && e.dataCode==='SCHEMA');
 assert.equal(f.store.files.size,0);assert.equal(f.client.memory.size,0);assert.equal(f.client.retained,false);
});
