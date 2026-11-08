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
html=html.replace('var archiveOptions =',instrument+'\nvar archiveOptions =')
.replace('function sendMessage(event) {','function sendMessage(event) { window.markTest("click-handler");')
.replace("pendingUser.className = 'bubble user';", "window.markTest('user-bubble'); pendingUser.className = 'bubble user';")
.replace("addBubble({type:'user', text: userText});","window.markTest('user-bubble'); addBubble({type:'user', text: userText});")
.replace('accText += delta;',"window.markTest('first-token'); accText += delta;")
.replace('function logSession(rec, requestSettings) {', 'function logSession(rec, requestSettings) { (window.testLogs||(window.testLogs=[])).push({rec:structuredClone(rec),exclude:requestSettings?requestSettings.exclude:noMemoryEnabled});')
.replace('var archiveCache =',"const testValidate=archiveOptions.validate;archiveOptions.validate=async function(...a){const t=performance.now();try{return await testValidate.apply(this,a);}finally{measurements.spans.push({name:'scope-validation',t,ms:performance.now()-t});}};\nvar archiveCache =")
.replace('var archiveOptions =', 'window.testState=()=>({sendPending,streaming,history:history.length,noMemoryEnabled});window.testOverlap=()=>{const p=ensureDataReady();return p===loadContext()&&p===loadShards();};window.testChangeSetting=()=>{settings.model+="-changed";};\nvar archiveOptions =');
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
 if(process.argv.includes('--policy-boundaries')){
  report.boundaries=[];
  const snap=()=>page.evaluate(()=>({users:document.querySelectorAll('.bubble.user').length,subjects:document.querySelectorAll('.bubble.subject').length,userLogs:(window.testLogs||[]).filter(x=>x.rec.role==='user').length,assistantLogs:(window.testLogs||[]).filter(x=>x.rec.role==='simulacrum').length,draft:document.querySelector('#input-text').value}));
  for(const boundary of ['commit','fetch','commit-disabled','fetch-disabled','fetch-edited']){
   const before=await snap(),posts=bodies.filter(x=>x.path==='/v1/chat/completions').length;
   await page.locator('#input-text').fill('synthetic boundary '+boundary);
   await page.evaluate(x=>window.testBoundary=x,boundary);await page.locator('#send-btn').click();
   await page.waitForFunction(()=>!testState().sendPending&&!testState().streaming);
   const after=await snap(),delta={};for(const k of ['users','subjects','userLogs','assistantLogs'])delta[k]=after[k]-before[k];
   report.boundaries.push({boundary,...delta,draft:after.draft,chat:bodies.filter(x=>x.path==='/v1/chat/completions').length-posts});
   await page.evaluate(()=>localStorage.setItem('companion_archive_disabled','false'));
  }
  fs.writeFileSync(output,JSON.stringify(report,null,2));
  for(const r of report.boundaries){assert.equal(r.chat,0,r.boundary+' POST');assert.equal(r.assistantLogs,0);assert.equal(r.draft,r.boundary==='fetch-edited'?'newer synthetic draft':'synthetic boundary '+r.boundary);for(const k of ['users','subjects','userLogs'])assert.equal(r[k],r.boundary.startsWith('commit')?0:1,r.boundary+' '+k);}
  return;
 }
 for(let i=0;i<3;i++){await page.locator('#input-text').fill('synthetic latency '+i);counts={};bodies=[];
 await page.evaluate(()=>{measurements={events:[],spans:[]};if(window.testObserver)window.testObserver.disconnect();window.testObserver=new MutationObserver(records=>{const notices=records.flatMap(r=>[...r.addedNodes]).filter(n=>n.nodeType===1&&/准备|核验|加载|校验/.test(n.textContent));if(notices.length&&!measurements.events.some(e=>e.name==='visible-feedback')){markTest('visible-feedback');requestAnimationFrame(()=>markTest('feedback-animation-frame'));}});window.testObserver.observe(document.querySelector('#chat'),{childList:true,subtree:true,characterData:true});});
 await page.locator('#send-btn').click();await page.waitForFunction(()=>measurements.events.some(e=>e.name==='first-token'));await page.waitForFunction(()=>!document.querySelector('#send-btn').classList.contains('stop'));
 const m=await page.evaluate(()=>measurements);report.runs.push({...m,counts:{...counts},chatRequests:bodies.filter(b=>b.path==='/v1/chat/completions').length});}
 if(process.argv.includes('--regression')){
  report.scenarios=[];const chats=()=>bodies.filter(b=>b.path==='/v1/chat/completions').length;
  const settled=()=>page.waitForFunction(()=>!testState().sendPending&&!testState().streaming);
  const draft=async s=>{await page.locator('#input-text').fill(s);await page.locator('#send-btn').click();};
  const snapshot=async()=>({...await page.evaluate(()=>({users:document.querySelectorAll('.bubble.user').length,subjects:document.querySelectorAll('.bubble.subject').length,userLogs:(window.testLogs||[]).filter(x=>x.rec.role==='user').length,assistantLogs:(window.testLogs||[]).filter(x=>x.rec.role==='simulacrum').length})),requests:chats()});
  const exactTurns=async(before,n,label)=>{const after=await snapshot();for(const key of Object.keys(before))assert.equal(after[key]-before[key],n,label+' '+key);return after;};
  let exact=await snapshot();await page.locator('#input-text').fill('synthetic double');await page.locator('#send-btn').dblclick();await settled();await exactTurns(exact,1,'double click');report.scenarios.push('double click exactly one request/user+subject bubble/user+assistant log');
  exact=await snapshot();await page.locator('#input-text').fill('synthetic Enter');for(let i=0;i<3;i++)await page.locator('#input-text').press('Enter');await settled();await exactTurns(exact,1,'rapid Enter');report.scenarios.push('three rapid Enter presses exactly one request/user+subject bubble/user+assistant log');
  const cancelled=chats();await draft('synthetic cancelled');await page.locator('.archive-send-cancel:not([disabled])').click();assert.equal(await page.locator('#input-text').inputValue(),'synthetic cancelled');await draft('synthetic after cancel');await settled();assert.equal(chats(),cancelled+1);assert(await page.locator('.bubble.notice').filter({hasText:'已取消本次发送，输入已保留。'}).count());report.scenarios.push('cancel then new send one request no stale dispatch; terminal cancelled notice preserved');
  for(const width of [320,390]){await page.setViewportSize({width,height:700});await draft('synthetic screenshot');const visible=await page.locator('.archive-send-cancel:not([disabled])').evaluate(e=>{const b=e.getBoundingClientRect(),c=document.querySelector('#chat').getBoundingClientRect();return b.top>=c.top&&b.bottom<=c.bottom&&b.left>=0&&b.right<=innerWidth;});assert(visible,'pending cancel must be fully inside chat viewport at '+width);await page.screenshot({path:path.join(path.dirname(output),'pending-'+width+'.png')});await page.locator('.archive-send-cancel:not([disabled])').click();}
  for(const mode of [401,'offline','timeout']){authMode=mode;const before=chats();await draft('synthetic recover '+mode);await settled();assert.equal(chats(),before);assert.equal(await page.locator('#input-text').inputValue(),'synthetic recover '+mode);authMode=null;await draft('synthetic retry '+mode);await settled();assert.equal(chats(),before+1);report.scenarios.push(mode+' blocked preserves draft; retry succeeds');}
  const toggle=async value=>{await page.evaluate(v=>{const e=document.querySelector('#cfg-no-memory');e.checked=v;e.dispatchEvent(new Event('change',{bubbles:true}));},value);};
  let before=chats();await draft('synthetic changed exclude');await toggle(true);await settled();assert.equal(chats(),before);assert.equal(await page.locator('#input-text').inputValue(),'synthetic changed exclude');report.scenarios.push('pending exclude change blocks dispatch and preserves draft');
  llmDelay=400;await draft('synthetic exclude snapshot');await page.waitForFunction(()=>testState().streaming);await toggle(false);await settled();const logs=await page.evaluate(()=>testLogs.filter(x=>x.rec.text==='synthetic exclude snapshot'||x.rec.role==='simulacrum').slice(-2));assert.equal(logs.length,2);assert(logs.every(x=>x.exclude===true));report.scenarios.push('dispatched turn logs preserve exclude snapshot');llmDelay=40;
  const held=async count=>{for(let i=0;i<250&&heldIdentities.length<count;i++)await page.waitForTimeout(20);assert.equal(heldIdentities.length,count,'controlled identity request did not arrive');};
  for(const change of ['edit-back','settings']){
   const before=await snapshot();holdIdentity=true;await draft('synthetic pending '+change);await held(1);
   if(change==='edit-back'){await page.locator('#input-text').fill('synthetic temporary');await page.locator('#input-text').fill('synthetic pending '+change);}
   else await page.evaluate(()=>testChangeSetting());
   holdIdentity=false;heldIdentities.shift()();await settled();await exactTurns(before,0,change);
   assert.equal(await page.locator('#input-text').inputValue(),'synthetic pending '+change);report.scenarios.push(change+' invalidates pending send despite restored text');
  }
  {
   const before=await snapshot(),idBefore=counts['/cdn-cgi/access/get-identity']||0,manifestBefore=counts['/data/archive-cache-manifest.json']||0;
   holdIdentity=true;assert(await page.evaluate(()=>testOverlap()),'ordinary load/retry promise identity');await held(1);
   await draft('synthetic ordinary overlap send');holdIdentity=false;heldIdentities.shift()();await settled();await exactTurns(before,1,'ordinary overlap');
   assert.equal((counts['/cdn-cgi/access/get-identity']||0)-idBefore,8);assert.equal((counts['/data/archive-cache-manifest.json']||0)-manifestBefore,4);
   report.scenarios.push('ordinary ensure/load/retry coalesce; concurrent Send requires own fresh full tail');
  }
  const other=await page.context().newPage();await other.goto(fixtureOrigin+'/control.html');
  for(const action of ['cancel','foreground','bfcache','cross-tab-disable']){
   const before=await snapshot(),outcomes=await page.evaluate(()=>testPreparationOutcomes.length);
   holdIdentity=true;await draft('synthetic A '+action);await held(1);
   if(action==='cancel')await page.locator('.archive-send-cancel:not([disabled])').click();
   else if(action==='cross-tab-disable'){await other.evaluate(()=>{localStorage.setItem('companion_archive_disabled','true');localStorage.setItem('companion_archive_invalidation',String(Math.random()));});await page.waitForFunction(()=>!testState().sendPending);}
   else await page.evaluate(kind=>{if(kind==='foreground')document.dispatchEvent(new Event('visibilitychange'));else window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));},action);
   assert.equal(await page.locator('#input-text').inputValue(),'synthetic A '+action);
   await draft('synthetic B '+action);await held(2);
   heldIdentities.shift()();await page.waitForFunction(n=>testPreparationOutcomes.length>n,outcomes);
   assert.equal(await page.evaluate(()=>testState().sendPending),true,'A settlement unlocked B '+action);
   await exactTurns(before,0,'A settled while B pending '+action);
   holdIdentity=false;heldIdentities.shift()();await settled();await exactTurns(before,1,'only B commits '+action);
   assert.equal(await page.locator('.bubble.user').filter({hasText:'synthetic A '+action}).count(),0);
   if(action==='cancel')assert(await page.locator('.bubble.notice').filter({hasText:'已取消本次发送，输入已保留。'}).count());
   report.scenarios.push('controlled '+action+': A settles while B pending; B remains locked; only B request/bubbles/logs commit');
   if(action==='cross-tab-disable'){await other.evaluate(()=>{localStorage.setItem('companion_archive_disabled','false');localStorage.setItem('companion_archive_invalidation',String(Math.random()));});await page.waitForTimeout(100);}
  }
  await other.close();
  {
   const before=await snapshot();holdIdentityNumber=identityNumber+3;
   await draft('synthetic changed archive pending');await held(1);
   const m=JSON.parse(fs.readFileSync(path.join(fixture,'data/archive-cache-manifest.json'))),file=m.files.find(f=>f.path.includes('messages-'));
   const rows=JSON.parse(fs.readFileSync(path.join(fixture,file.path)));rows[0].text+=' synthetic updated';const bytes=Buffer.from(JSON.stringify(rows));
   overrides.set('/'+file.path,bytes);file.bytes=bytes.length;file.sha256=hash(bytes);delete m.revision;m.revision=hash(stable(m));overrides.set('/data/archive-cache-manifest.json',Buffer.from(JSON.stringify(m)));
   holdIdentityNumber=0;heldIdentities.shift()();await settled();await exactTurns(before,0,'archive changed between gates');
   assert.equal(await page.locator('#input-text').inputValue(),'synthetic changed archive pending');
   await draft('synthetic retry changed archive');await settled();await exactTurns(before,1,'changed archive explicit retry');
   report.scenarios.push('archive revision changes between gates: no predispatch commit, draft retained, explicit retry exactly one turn');
  }
  await page.screenshot({path:path.join(path.dirname(output),'ready-390.png')});
 }
 report.errors=errors;report.blockedOrigins=blocked;fs.writeFileSync(output,JSON.stringify(report,null,2));assert.equal(errors.length,0);assert.equal(blocked.length,0);assert(report.runs.every(r=>r.chatRequests===1));
 if(process.argv.includes('--assert-feedback'))assert(report.runs.every(r=>{const c=r.events.find(e=>e.name==='click-handler'),v=r.events.find(e=>e.name==='visible-feedback');return v&&v.t-c.t<150;}),'pending feedback must appear within 150 ms');
 console.log(JSON.stringify({output,bytes:report.bytes,runs:report.runs.map(r=>({events:r.events,counts:r.counts,puts:r.spans.filter(s=>s.name==='put').length}))},null,2));
 }finally{await browser.close();server.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
