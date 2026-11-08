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
html=html.replace('var archiveOptions =', 'window.testProof=async()=>{await ensureDataReady(true);window.savedProof=archiveSendProof;checkArchiveSendProof(savedProof);};window.testProofValid=()=>{try{checkArchiveSendProof(savedProof);return true;}catch(_){return false;}};\nvar archiveOptions =');
html=html.replace("pendingUser.className = 'bubble user';","window.markTest('committed-user-bubble'); pendingUser.className = 'bubble user';").replace("pendingUser.className = 'bubble user-pending';","window.markTest('pending-user-bubble');requestAnimationFrame(()=>window.markTest('pending-next-raf')); pendingUser.className = 'bubble user-pending';");
html=html.replace('var archiveOptions =',instrument+'\nvar archiveOptions =')
.replace('function sendMessage(event) {','function sendMessage(event) { window.markTest("click-handler");')
.replace("addBubble({type:'user', text: userText});","window.markTest('user-bubble'); addBubble({type:'user', text: userText});")
.replace('accText += delta;',"window.markTest('first-token'); accText += delta;")
.replace('function logSession(rec, requestSettings) {', 'function logSession(rec, requestSettings) { (window.testLogs||(window.testLogs=[])).push({rec:structuredClone(rec),exclude:requestSettings?requestSettings.exclude:noMemoryEnabled});')
.replace('var archiveCache =',"const testValidate=archiveOptions.validate;archiveOptions.validate=async function(...a){const t=performance.now();try{return await testValidate.apply(this,a);}finally{measurements.spans.push({name:'scope-validation',t,ms:performance.now()-t});}};\nvar archiveCache =")
.replace('var archiveOptions =', 'window.testSeedHistory=()=>{sessionsData={sessions:[{session_id:"old-synthetic",turns:[{role:"user",turn:1,text:"old synthetic history",ts:"2020-01-01T00:00:00Z"},{role:"simulacrum",turn:1,text:"old synthetic reply"}]}]};sessionsLoaded=true;historyReplayed=false;};window.testClearArchive=()=>archiveCache.clear();window.testRemoteArchive=()=>remoteArchiveChange();window.testFeedback=()=>({phase:dataReadyPhase,pending:sendPending,streaming,history:history.length,epoch:archiveCache.epoch,owner:archiveCache.operationOwner});window.testState=()=>({sendPending,streaming,history:history.length,noMemoryEnabled});window.testOverlap=()=>{const p=ensureDataReady();return p===loadContext()&&p===loadShards();};window.testChangeSetting=()=>{settings.model+="-changed";};\nvar archiveOptions =');
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
 try{await page.goto('http://127.0.0.1:'+server.address().port+'/companion.html');const noConsentBefore=identityNumber, noConsentManifest=counts['/data/archive-cache-manifest.json']||0;
 const noConsent=await page.evaluate(()=>{const epoch=testFeedback().epoch;Object.defineProperty(document,'hidden',{configurable:true,value:true});window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));return {before:epoch,after:testFeedback().epoch,hidden:document.hidden};});
 await page.waitForTimeout(200);assert(noConsent.hidden);assert(noConsent.after>noConsent.before);assert.equal(identityNumber,noConsentBefore);assert.equal(counts['/data/archive-cache-manifest.json']||0,noConsentManifest);assert.equal(bodies.length,0);
 report.noConsentHiddenPersisted=noConsent;
 await page.evaluate(()=>Object.defineProperty(document,'hidden',{configurable:true,value:false}));await page.locator('#intro-ok').click();await page.waitForFunction(()=>document.querySelector('#intro-progress').textContent.includes('可以开始'));await page.locator('#intro-enter').click();

 report.scenarios=[];
 const state=()=>page.evaluate(()=>testFeedback());
 const gateCounts=()=>({identity:identityNumber,manifest:counts['/data/archive-cache-manifest.json']||0,chat:bodies.filter(x=>x.path==='/v1/chat/completions').length});
 const assertGates=(before,n=1)=>{const now=gateCounts();assert.equal(now.identity-before.identity,4*n);assert.equal(now.manifest-before.manifest,2*n);};
 const ready=()=>page.waitForFunction(()=>testFeedback().phase==='ready');
 const event=kind=>page.evaluate(kind=>{Object.defineProperty(document,'hidden',{configurable:true,value:false});if(kind==='visible')document.dispatchEvent(new Event('visibilitychange'));else window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));},kind);
 {
  await page.evaluate(()=>testProof());assert(await page.evaluate(()=>testProofValid()));
  const proofBefore=await state(),proofGates=gateCounts();
  await page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:true});window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));});
  assert.equal((await state()).epoch,proofBefore.epoch+1);assert.equal(await page.evaluate(()=>testProofValid()),false);await page.waitForTimeout(200);assertGates(proofGates,0);assert.equal(gateCounts().chat,proofGates.chat);
  await event('visible');await ready();assertGates(proofGates);report.scenarios.push('hidden persisted invalidates a valid send proof without automatic gates');
  holdIdentity=true;await page.locator('#input-text').fill('hidden persisted draft');await page.locator('#send-btn').click();
  for(let i=0;i<100&&heldIdentities.length<1;i++)await page.waitForTimeout(20);assert.equal(heldIdentities.length,1);
  const before=await state(),g=gateCounts();assert(before.pending);
  const immediate=await page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:true});window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));return {...testFeedback(),hidden:document.hidden,proofValid:testProofValid(),draft:document.querySelector('#input-text').value};});
  assert(immediate.hidden);assert.equal(immediate.epoch,before.epoch+1);assert.equal(immediate.pending,false);assert.equal(immediate.proofValid,false);assert.equal(immediate.draft,'hidden persisted draft');
  await page.waitForTimeout(200);assertGates(g,0);assert.equal(gateCounts().chat,g.chat);
  holdIdentity=false;heldIdentities.splice(0).forEach(f=>f());await page.waitForTimeout(200);
  assert.equal((await state()).phase,'idle');assert.equal((await state()).pending,false);assert.equal(await page.locator('#input-text').inputValue(),'hidden persisted draft');assertGates(g,0);assert.equal(gateCounts().chat,g.chat);
  await event('visible');await ready();assertGates(g);assert.equal(gateCounts().chat,g.chat);
  report.hiddenPersisted={before,immediate,after:await state()};report.scenarios.push('hidden persisted cancels active A and proof, unlocks send, preserves draft, no automatic gates; visible runs fresh 4I/2M');
  await page.locator('#input-text').fill('');
 }
 for(const kind of ['visible','persisted','visible','persisted']){
  const before=await state(),g=gateCounts();await event(kind);await ready();const after=await state();assert(after.epoch>before.epoch);assertGates(g);report.scenarios.push(kind+' standalone always invalidates and prepares');
 }
 for(const order of [['visible','persisted'],['persisted','visible']]){
  const before=await state(),g=gateCounts();const immediate=await page.evaluate(order=>{for(const kind of order){if(kind==='visible')document.dispatchEvent(new Event('visibilitychange'));else window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));}return testFeedback();},order);
  assert.equal(immediate.epoch-before.epoch,2,'every event invalidates synchronously');await ready();assertGates(g);report.scenarios.push(order.join('+')+' coalesces only automatic preparation');
 }
 {
  const g=gateCounts();await page.evaluate(()=>{document.dispatchEvent(new Event('visibilitychange'));const input=document.querySelector('#input-text');input.value='manual before timer';input.dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('#send-btn').click();});
  await page.waitForFunction(()=>!testFeedback().pending&&!testFeedback().streaming);assertGates(g);assert.equal(gateCounts().chat-g.chat,1);report.scenarios.push('manual Send takes timer ownership; no second preparation');
 }
 for(const action of ['remote-disable','clear','hidden','pagehide']){
  const g=gateCounts();await page.evaluate(action=>{
   document.dispatchEvent(new Event('visibilitychange'));
   if(action==='remote-disable'){localStorage.setItem('companion_archive_disabled','true');window.dispatchEvent(new StorageEvent('storage',{key:'companion_archive_disabled',newValue:'true'}));}
   if(action==='clear')testClearArchive();
   if(action==='hidden'){Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'));}
   if(action==='pagehide')window.dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}));
  },action);await page.waitForTimeout(200);assertGates(g,0);assert.equal(gateCounts().chat,g.chat);assert.equal((await state()).phase,'idle');
  await page.evaluate(()=>{localStorage.setItem('companion_archive_disabled','false');Object.defineProperty(document,'hidden',{configurable:true,value:false});});await event('visible');await ready();report.scenarios.push(action+' before timer prevents stale auto prepare');
 }
 {
  holdIdentity=true;await event('visible');for(let i=0;i<100&&heldIdentities.length<1;i++)await page.waitForTimeout(20);assert.equal(heldIdentities.length,1);
  const old=await state();await event('persisted');for(let i=0;i<100&&heldIdentities.length<2;i++)await page.waitForTimeout(20);assert.equal(heldIdentities.length,2);const current=await state();assert(current.epoch>old.epoch);
  heldIdentities.shift()();await page.waitForTimeout(150);assert.equal((await state()).epoch,current.epoch);assert.equal((await state()).phase,'loading');
  holdIdentity=false;heldIdentities.splice(0).forEach(f=>f());await ready();report.scenarios.push('resume during active preparation supersedes A; late A cannot alter B');
 }
 report.pass=true;
 }catch(e){report.error=String(e);process.exitCode=1;}finally{report.errors=errors;report.blocked=blocked;fs.writeFileSync(output,JSON.stringify(report,null,2));console.log(JSON.stringify(report));await browser.close();server.closeAllConnections();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
