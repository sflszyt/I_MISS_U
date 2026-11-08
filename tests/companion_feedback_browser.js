// Real Edge, loopback HTTP and IndexedDB. No real data or remote API.
const fs=require('fs'),path=require('path'),http=require('http'),assert=require('node:assert/strict'),{createHash}=require('crypto');
const {chromium}=require(process.env.PLAYWRIGHT_CORE||require('node:path').join(require('node:os').homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright-core'));
const fixture=path.resolve(process.argv[2]),output=path.resolve(process.argv[3]),delay=Number(process.argv[4]||0);
let html=fs.readFileSync(path.join(fixture,'companion.html'),'utf8'), counts={},bodies=[],authMode=null,llmDelay=40,holdIdentity=false,heldIdentities=[],identityNumber=0,holdIdentityNumber=0;
const overrides=new Map();
const stable=v=>Array.isArray(v)?'['+v.map(stable).join(',')+']':v&&typeof v==='object'?'{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+stable(v[k])).join(',')+'}':JSON.stringify(v);
const hash=v=>createHash('sha256').update(v).digest('hex');
const instrument=`
window.measurements={events:[],spans:[]};
window.markTest=function(name){window.measurements.events.push({name,t:performance.now()});};
const proto=globalThis.ArchiveDeviceCache.ArchiveDeviceCache.prototype;
window.testPreparationOutcomes=[];
for(const name of ['prepare','finishForSend']){if(typeof proto[name]!=='function')continue;const testPrepare=proto[name];proto[name]=function(...a){return testPrepare.apply(this,a).then(v=>{testPreparationOutcomes.push(name+':resolved');return v;},e=>{testPreparationOutcomes.push(name+':rejected');throw e;});};}
for(const name of ['gate','hash','prepareOnce']){const old=proto[name];proto[name]=async function(...a){const t=performance.now();try{return await old.apply(this,a);}finally{window.measurements.spans.push({name,t,ms:performance.now()-t});}};}
const sp=globalThis.ArchiveDeviceCache.IndexedArchiveStore.prototype;
for(const name of ['snapshot','bind','current','get','put']){const old=sp[name];sp[name]=async function(...a){const t=performance.now();try{return await old.apply(this,a);}finally{window.measurements.spans.push({name,t,ms:performance.now()-t});}};}
const parse=JSON.parse;JSON.parse=function(...a){const t=performance.now();try{return parse.apply(this,a);}finally{window.measurements.spans.push({name:'parse',t,ms:performance.now()-t});}};
function timedTest(name,fn){return function(...a){const t=performance.now();try{return fn.apply(this,a);}finally{measurements.spans.push({name,t,ms:performance.now()-t});}};}
collectAllRecords=timedTest('collectAllRecords',collectAllRecords);retrieveSnippets=timedTest('retrieveSnippets',retrieveSnippets);retrieveKnowledge=timedTest('retrieveKnowledge',retrieveKnowledge);retrieveSessions=timedTest('retrieveSessions',retrieveSessions);
`;
html=html.replace("pendingUser.className = 'bubble user';","window.markTest('committed-user-bubble'); pendingUser.className = 'bubble user';").replace("pendingUser.className = 'bubble user-pending';","window.markTest('pending-user-bubble');requestAnimationFrame(()=>window.markTest('pending-next-raf')); pendingUser.className = 'bubble user-pending';");
html=html.replace('var archiveOptions =',instrument+'\nvar archiveOptions =')
.replace('function sendMessage(event) {','function sendMessage(event) { window.markTest("click-handler");')
.replace("addBubble({type:'user', text: userText});","window.markTest('user-bubble'); addBubble({type:'user', text: userText});")
.replace('accText += delta;',"window.markTest('first-token'); accText += delta;")
.replace('function logSession(rec, requestSettings) {', 'function logSession(rec, requestSettings) { (window.testLogs||(window.testLogs=[])).push({rec:structuredClone(rec),exclude:requestSettings?requestSettings.exclude:noMemoryEnabled});')
.replace('var archiveCache =',"const testValidate=archiveOptions.validate;archiveOptions.validate=async function(...a){const t=performance.now();try{return await testValidate.apply(this,a);}finally{measurements.spans.push({name:'scope-validation',t,ms:performance.now()-t});}};\nvar archiveCache =")
.replace('var archiveOptions =', 'window.testSeedHistory=()=>{sessionsData={sessions:[{session_id:"old-synthetic",turns:[{role:"user",turn:1,text:"old synthetic history",ts:"2020-01-01T00:00:00Z"},{role:"simulacrum",turn:1,text:"old synthetic reply"}]}]};sessionsLoaded=true;historyReplayed=false;};window.testFeedback=()=>({phase:dataReadyPhase,pending:sendPending,streaming,history:history.length,epoch:archiveCache.epoch,owner:archiveCache.operationOwner});window.testState=()=>({sendPending,streaming,history:history.length,noMemoryEnabled});window.testOverlap=()=>{const p=ensureDataReady();return p===loadContext()&&p===loadShards();};window.testChangeSetting=()=>{settings.model+="-changed";};\nvar archiveOptions =');
html=html.replace("dataReadyPhase = 'ready'; reportDataProgress(); applySessionsCard(); updateChatState();", "dataReadyPhase = 'ready'; reportDataProgress(); applySessionsCard(); updateChatState(); if((window.testBoundary||'').startsWith('commit')){const mode=window.testBoundary;window.testBoundary=null;queueMicrotask(()=>{localStorage.setItem('companion_archive_invalidation',String(Math.random()));if(mode.includes('disabled'))localStorage.setItem('companion_archive_disabled','true');});}")
.replace('function companionStream(endpoint, headers, body, mode, requestController, onDelta, onDone, onError, diagnostic) {', "function companionStream(endpoint, headers, body, mode, requestController, onDelta, onDone, onError, diagnostic) { if((window.testBoundary||'').startsWith('fetch')){const mode=window.testBoundary;window.testBoundary=null;queueMicrotask(()=>{localStorage.setItem('companion_archive_invalidation',String(Math.random()));if(mode.includes('disabled'))localStorage.setItem('companion_archive_disabled','true');if(mode.includes('edited')){inputText.value='newer synthetic draft';inputText.dispatchEvent(new Event('input',{bubbles:true}));}});}");
const server=http.createServer((req,res)=>{const p=new URL(req.url,'http://localhost').pathname;counts[p]=(counts[p]||0)+1;
 const json=x=>{res.setHeader('Content-Type','application/json');res.end(JSON.stringify(x));};
 if(p==='/companion.html'){res.setHeader('Content-Type','text/html');return res.end(html);}
 if(p==='/avatar.html'){res.setHeader('Content-Type','text/html');return res.end('<html></html>');}
 if(p==='/control.html'){res.setHeader('Content-Type','text/html');return res.end('<html></html>');}
 if(p==='/cdn-cgi/access/get-identity'){identityNumber++;if(authMode==='timeout')return;const finish=()=>{if(authMode==='offline'){res.destroy();return;}if(authMode===401){res.statusCode=401;return json({});}json({account_id:'a'.repeat(32),user_uuid:'11111111-1111-4111-8111-111111111111'});};if(holdIdentity||identityNumber===holdIdentityNumber){heldIdentities.push(finish);return;}return setTimeout(finish,delay);}
 if(p.startsWith('/data/'))return setTimeout(()=>{const file=path.join(fixture,p);if(overrides.has(p)||fs.existsSync(file)){res.setHeader('Content-Type','application/json');res.end(overrides.get(p)||fs.readFileSync(file));}else{res.statusCode=404;json({});}},p.includes('manifest')?delay:0);
 if(req.method==='POST'){let body='';req.on('data',b=>body+=b);req.on('end',()=>{bodies.push({path:p,body:JSON.parse(body)});if(p==='/v1/chat/completions'){res.setHeader('Content-Type','text/event-stream');return setTimeout(()=>res.end('data: {"choices":[{"delta":{"content":"synthetic response"}}]}\n\ndata: [DONE]\n\n'),llmDelay);}json({ok:true});});return;}
 res.statusCode=503;json({});
});
(async()=>{await new Promise(r=>server.listen(0,'127.0.0.1',r));const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 const context=await browser.newContext(),page=await context.newPage();page.setDefaultTimeout(30000);let errors=[],blocked=[];page.on('pageerror',e=>errors.push(String(e)));
 const fixtureOrigin='http://127.0.0.1:'+server.address().port;
 await context.route('**/*',route=>{const u=new URL(route.request().url());if(u.origin===fixtureOrigin)return route.continue();blocked.push(u.origin);return route.abort();});
 await page.addInitScript(()=>{const old=window.fetch;window.fetch=function(url,...a){if(String(url).includes('/v1/chat/completions'))window.markTest('chat-fetch');return old.call(this,url,...a);};});
 const report={delay,fixture,bytes:fs.readdirSync(path.join(fixture,'data')).filter(n=>!n.includes('manifest')).reduce((n,f)=>n+fs.statSync(path.join(fixture,'data',f)).size,0),runs:[]};
 try{await page.goto('http://127.0.0.1:'+server.address().port+'/companion.html');await page.locator('#intro-ok').click();await page.waitForFunction(()=>document.querySelector('#intro-progress').textContent.includes('可以开始'));await page.locator('#intro-enter').click();
 report.cases=[];
 const state=()=>page.evaluate(()=>({...testFeedback(),users:document.querySelectorAll('.bubble.user').length,provisional:document.querySelectorAll('.user-pending').length,text:document.querySelector('#preparation-banner').textContent}));
 if(process.argv.includes('--lifecycle')){
  await page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'));window.dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}));Object.defineProperty(document,'hidden',{configurable:true,value:false});document.dispatchEvent(new Event('visibilitychange'));window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));});
  await page.waitForTimeout(2500);report.state=await state();assert.equal(report.state.phase,'ready','foreground must actively converge without Send');
 }else{
  holdIdentity=true;await page.locator('#input-text').fill('synthetic immediate user text');
  const sync=await page.evaluate(()=>{const start=performance.now();document.querySelector('#send-btn').click();const b=document.querySelector('.user-pending');return {ms:performance.now()-start,present:!!b,text:b&&b.textContent,users:document.querySelectorAll('.bubble.user').length,history:testFeedback().history};});report.sync=sync;
  assert(sync.present,'click must synchronously insert provisional user text');assert(sync.text.includes('synthetic immediate user text'));assert.equal(sync.users,0);assert.equal(sync.history,0);assert.equal(bodies.filter(b=>b.path==='/v1/chat/completions').length,0);
  await page.locator('.archive-send-cancel:not([disabled])').click();holdIdentity=false;heldIdentities.splice(0).forEach(f=>f());await page.waitForTimeout(1000);assert.equal(bodies.filter(b=>b.path==='/v1/chat/completions').length,0);assert.equal(await page.locator('#input-text').inputValue(),'synthetic immediate user text');
 }

 if(process.argv.includes('--suite')||process.argv.includes('--early-only')){
  const chats=()=>bodies.filter(x=>x.path==='/v1/chat/completions').length;
  const settled=()=>page.waitForFunction(()=>!testFeedback().pending&&!testFeedback().streaming);
  const ready=()=>page.waitForFunction(()=>testFeedback().phase==='ready');
  const resume=()=>page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'));window.dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}));Object.defineProperty(document,'hidden',{configurable:true,value:false});document.dispatchEvent(new Event('visibilitychange'));window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));});
  const logs=()=>page.evaluate(()=>({u:(window.testLogs||[]).filter(x=>x.rec.role==='user').length,a:(window.testLogs||[]).filter(x=>x.rec.role==='simulacrum').length,history:testFeedback().history,users:document.querySelectorAll('.bubble.user').length}));
  const held=async()=>{for(let i=0;i<100&&!heldIdentities.length;i++)await page.waitForTimeout(20);assert(heldIdentities.length,'held identity');};
  const release=()=>{holdIdentity=false;heldIdentities.splice(0).forEach(f=>f());};
  const send=async text=>{await page.locator('#input-text').fill(text);await page.locator('#send-btn').click();};
  const record=(name,data={})=>report.cases.push({name,...data});
  if(!process.argv.includes('--early-only')){
  await page.locator('#input-text').fill('');
  let beforeId=identityNumber,beforeManifest=counts['/data/archive-cache-manifest.json']||0;
  await resume();await ready();assert.equal(identityNumber-beforeId,4);assert.equal((counts['/data/archive-cache-manifest.json']||0)-beforeManifest,2);record('paired resume one full preparation 4identity/2manifest');
  await page.evaluate(()=>window.measurements={events:[],spans:[]});const prior=await logs(),postBefore=chats();
  await page.locator('#input-text').fill('synthetic timing');await page.locator('#send-btn').dblclick();await settled();
  assert.equal(chats()-postBefore,1);const after=await logs();assert.equal(after.u-prior.u,1);assert.equal(after.a-prior.a,1);assert.equal(after.users-prior.users,1);assert.equal(after.history-prior.history,2);
  const events=await page.evaluate(()=>measurements.events),t=events.find(e=>e.name==='click-handler').t;
  record('double click exact one committed turn',{timing:Object.fromEntries(['pending-user-bubble','pending-next-raf','committed-user-bubble','chat-fetch'].map(name=>[name,events.find(e=>e.name===name).t-t]))});
  const enterBefore=chats();await page.locator('#input-text').fill('synthetic Enter');await page.locator('#input-text').press('Enter');await settled();assert.equal(chats()-enterBefore,1);record('Enter one turn');
  for(const mode of ['edit-back','settings','exclude','cancel-new','resume-send']){
   const before=await logs(),posts=chats();holdIdentity=true;await send('synthetic '+mode);await held();
   assert.deepEqual(await logs(),before,'no premature effects '+mode);
   if(mode==='edit-back'){await page.locator('#input-text').fill('new draft');await page.locator('#input-text').fill('synthetic '+mode);}
   if(mode==='settings')await page.evaluate(()=>testChangeSetting());
   if(mode==='exclude')await page.evaluate(()=>{const e=document.querySelector('#cfg-no-memory');e.checked=!e.checked;e.dispatchEvent(new Event('change',{bubbles:true}));});
   if(mode==='cancel-new'){await page.locator('.archive-send-cancel:not([disabled])').click();await send('synthetic replacement');}
   if(mode==='resume-send')await resume();
   release();await settled();if(mode==='resume-send')await ready();
   assert.equal(chats()-posts,mode==='cancel-new'?1:0,mode);const final=await logs();assert.equal(final.u-before.u,mode==='cancel-new'?1:0);assert.equal(final.users-before.users,mode==='cancel-new'?1:0);record(mode+' stale turn cannot commit');
  }
  for(const mode of [401,'offline','timeout']){
   const before=await logs(),posts=chats();authMode=mode;await resume();await page.waitForFunction(()=>testFeedback().phase==='failed');
   assert.deepEqual(await logs(),before);assert.equal(chats(),posts);assert(await page.locator('#preparation-banner button').isVisible());
   authMode=null;await page.evaluate(()=>window.dispatchEvent(new Event('online')));await ready();assert.equal(chats(),posts);record(mode+' resume fails visibly; online retry no auto send');
  }
  await page.locator('#input-text').fill('synthetic preserved draft');const draftPosts=chats();await resume();await ready();assert.equal(await page.locator('#input-text').inputValue(),'synthetic preserved draft');assert.equal(chats(),draftPosts);record('resume during input preserves draft without auto send');

  // Same-tab clear must leave an honest idle state and usable explicit retry.
  const clearPosts=chats();await page.locator('#drawer .archive-cache-clear').evaluate(e=>e.click());
  await page.waitForFunction(()=>testFeedback().phase==='idle');assert(await page.locator('#preparation-banner button').isVisible());
  assert(!/0\/0|正在确认/.test(await page.locator('#preparation-banner').textContent()));
  await page.locator('#preparation-banner button').click();await ready();assert.equal(chats(),clearPosts);record('clear idle honest and explicit retry available');
  const other=await context.newPage();await other.goto(fixtureOrigin+'/control.html');
  for(const disabled of [true,false]){
   const previous=await logs(),posts=chats();holdIdentity=true;await send('synthetic cross-tab '+disabled);await held();
   await other.evaluate(v=>{localStorage.setItem('companion_archive_disabled',JSON.stringify(v));localStorage.setItem('companion_archive_invalidation',String(Math.random()));},disabled);
   await page.waitForFunction(()=>!testFeedback().pending);release();await settled();assert.deepEqual(await logs(),previous);assert.equal(chats(),posts);
   await page.locator('#preparation-banner button').click();await ready();assert.equal(chats(),posts);record('cross-tab '+disabled+' invalidates old turn; explicit preparation settles');
  }
  await other.close();
  {
   const previous=await logs(),posts=chats();holdIdentityNumber=identityNumber+3;await resume();await held();
   const m=JSON.parse(fs.readFileSync(path.join(fixture,'data/archive-cache-manifest.json'))),file=m.files.find(f=>f.path.includes('messages-'));
   const rows=JSON.parse(fs.readFileSync(path.join(fixture,file.path)));rows[0].text+=' synthetic updated';const bytes=Buffer.from(JSON.stringify(rows));
   overrides.set('/'+file.path,bytes);file.bytes=bytes.length;file.sha256=hash(bytes);delete m.revision;m.revision=hash(stable(m));overrides.set('/data/archive-cache-manifest.json',Buffer.from(JSON.stringify(m)));
   holdIdentityNumber=0;release();await page.waitForFunction(()=>testFeedback().phase==='failed');assert.deepEqual(await logs(),previous);assert.equal(chats(),posts);
   await page.locator('#preparation-banner button').click();await ready();assert.equal(chats(),posts);record('version changed between resume gates fails; explicit retry loads new bound version');
  }
  const fresh=await context.newPage();await fresh.goto(fixtureOrigin+'/companion.html');assert(!/正在确认|0\/0/.test(await fresh.locator('.archive-cache-status').first().textContent()));const id=identityNumber;
  await fresh.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'));Object.defineProperty(document,'hidden',{configurable:true,value:false});document.dispatchEvent(new Event('visibilitychange'));window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));});await fresh.waitForTimeout(250);assert.equal(identityNumber,id);await fresh.close();record('unaccepted intro resume no private preload');
  }
  const early=await context.newPage();await early.goto(fixtureOrigin+'/companion.html');holdIdentity=true;
  await early.locator('#intro-ok').click();await held();await early.locator('#intro-enter').click();await early.evaluate(()=>testSeedHistory());
  await early.locator('#input-text').fill('early synthetic <script>not executable</script>');await early.locator('#send-btn').click();
  await early.evaluate(()=>window.pendingRef=document.querySelector('.user-pending'));
  assert.equal(await early.locator('.user-pending script').count(),0);
  assert(!/DATA:INCOMPLETE/.test(await early.locator('#chat').textContent()),'preparing is not a DATA:INCOMPLETE failure');
  for(const width of [320,390]){await early.setViewportSize({width,height:700});await early.screenshot({path:output.replace('.json','-pending-'+width+'.png')});}
  release();await early.waitForFunction(()=>!testFeedback().pending&&!testFeedback().streaming);
  const order=await early.evaluate(()=>({same:window.pendingRef===document.querySelectorAll('.bubble.user')[1],texts:[...document.querySelectorAll('.bubble.user')].map(e=>e.textContent),userLogs:(window.testLogs||[]).filter(e=>e.rec.role==='user').length}));
  assert.deepEqual(order.texts,['old synthetic history','early synthetic <script>not executable</script>']);assert(order.same);assert.equal(order.userLogs,1);assert(!/DATA:INCOMPLETE/.test(await early.locator('#chat').textContent()),'ready leaves no stale preparation failure');await early.close();record('early enter pending promotes same node after historical replay with safe text');
  assert.equal(errors.length,0);assert.equal(blocked.length,0);
 }
 report.pass=true;
 }catch(e){report.error=String(e);process.exitCode=1;}finally{report.errors=errors;report.blocked=blocked;fs.writeFileSync(output,JSON.stringify(report,null,2));console.log(JSON.stringify(report));await browser.close();server.closeAllConnections();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
