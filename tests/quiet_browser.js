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
.replace('function sendMessage(event, retryBubble, retryText) {','function sendMessage(event, retryBubble, retryText) { window.markTest("click-handler");')
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
const origin='http://127.0.0.1:'+server.address().port,report={cases:[],errors:[],external:[]};
const manifestBefore=hash(fs.readFileSync(path.join(fixture,'data/archive-cache-manifest.json')));
try{for(const width of [320,390]){
 const ctx=await browser.newContext({viewport:{width,height:844}}),page=await ctx.newPage();page.on('pageerror',e=>report.errors.push(String(e)));
 await ctx.route('**/*',r=>new URL(r.request().url()).origin===origin?r.continue():(report.external.push(r.request().url()),r.abort()));
 await page.goto(origin+'/companion.html');
 assert.equal(await page.locator('.archive-cache-revision').first().textContent(),'资料版本待核验');
 assert((await page.locator('#intro-card .archive-cache-controls strong').textContent()).includes('应用 D19-candidate'));
 holdIdentity=true;await page.locator('#intro-ok').click();await page.waitForTimeout(100);assert(await page.locator('#intro-progress').isVisible());holdIdentity=false;heldIdentities.splice(0).forEach(f=>f());await page.waitForFunction(()=>document.querySelector('#intro-progress').textContent.includes('可以开始'));
 const revision=JSON.parse(fs.readFileSync(path.join(fixture,'data/archive-cache-manifest.json'),'utf8')).revision;
 assert.equal(await page.locator('.archive-cache-revision').first().textContent(),'已核验资料版本 '+revision);
 assert(await page.locator('#intro-card .ic-box').evaluate(n=>n.scrollWidth<=n.clientWidth));await page.screenshot({path:output+'-welcome-'+width+'.png'});
 const labels=await page.locator('.archive-cache-controls strong').allTextContents();assert.equal(labels[0],labels[1]);assert((await page.locator('header .subtitle').textContent()).endsWith('应用 D19-candidate'));
 await page.locator('#intro-enter').click();
 await page.locator('#settings-btn').click();
 await page.waitForFunction(()=>{const n=document.querySelector('#drawer'),r=n.getBoundingClientRect();return n.classList.contains('open')&&r.x>=-0.1&&r.right<=innerWidth+0.1&&r.width>=Math.min(300,innerWidth)-1;});
 await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
 const drawerBounds=await page.locator('#drawer').evaluate(n=>{const r=n.getBoundingClientRect();return {x:r.x,right:r.right,width:r.width,viewport:innerWidth,scroll:n.scrollWidth,client:n.clientWidth};});
 assert(drawerBounds.x>=-0.1&&drawerBounds.right<=width+0.1&&drawerBounds.width>=Math.min(300,width)-1);assert(drawerBounds.scroll<=drawerBounds.client);await page.screenshot({path:output+'-drawer-'+width+'.png'});await page.locator('#drawer-close-btn').click();
 await page.evaluate(()=>{window.seen=[];new MutationObserver(records=>records.forEach(r=>r.addedNodes.forEach(n=>{if(n.nodeType===1)seen.push({cls:n.className,text:n.textContent});}))).observe(document.querySelector('#chat'),{childList:true});});
 holdIdentity=true;await page.locator('#input-text').fill('quiet synthetic');const before=bodies.filter(x=>x.path==='/v1/chat/completions').length;
 const sendBefore=await page.locator('#send-btn').boundingBox();
 await page.locator('#send-btn').click();await page.locator('#send-btn').click();await page.locator('#input-text').press('Enter');await page.waitForTimeout(150);
 assert.equal(await page.locator('.user-pending').count(),0);assert.equal(await page.locator('#preparation-banner').isVisible(),false);
 assert.equal(await page.locator('#preparation-banner').evaluate(n=>n.getBoundingClientRect().height),0);
 const sendDuring=await page.locator('#send-btn').boundingBox();assert.deepEqual(sendDuring,sendBefore,'pending controls must not move Send');assert(await page.locator('#input-bar').evaluate(n=>n.scrollWidth<=n.clientWidth));
 assert.equal(await page.evaluate(()=>seen.some(n=>String(n.cls).includes('user-pending')||n.text.includes('正在核验资料'))),false);
 assert.equal(bodies.filter(x=>x.path==='/v1/chat/completions').length,before);assert.equal(await page.locator('#input-text').inputValue(),'');assert.equal(await page.locator('.bubble.user').count(),1);assert.equal(await page.locator('.typing-dots').count(),1);
 await page.screenshot({path:output+'-'+width+'.png'});
 assert(await page.locator('.archive-send-cancel').isVisible());
 await page.locator('.archive-send-cancel').click();holdIdentity=false;heldIdentities.splice(0).forEach(f=>f());await page.waitForTimeout(500);
 assert.equal(bodies.filter(x=>x.path==='/v1/chat/completions').length,before);assert.equal(await page.locator('#input-text').inputValue(),'quiet synthetic');
 assert.equal(await page.locator('.archive-cache-revision').first().textContent(),'资料版本待核验');
 holdIdentity=true;await page.locator('.send-failed button').click();await page.locator('#send-btn').click();await page.locator('#input-text').press('Enter');await page.waitForTimeout(100);holdIdentity=false;heldIdentities.splice(0).forEach(f=>f());await page.waitForFunction(()=>!testFeedback().pending&&!testFeedback().streaming);assert.equal(bodies.filter(x=>x.path==='/v1/chat/completions').length,before+1);assert.equal(await page.evaluate(()=>(window.testLogs||[]).filter(x=>x.rec.role==='user').length),1);
 assert.equal(await page.locator('.archive-send-cancel').count(),0);assert.equal(await page.locator('.bubble.user').count(),1);
 // Real authority failure remains actionable and the user's draft survives.
 authMode=401;await page.locator('#input-text').fill('failure draft');await page.locator('#send-btn').click();await page.waitForFunction(()=>testFeedback().phase==='failed');
 assert.equal(await page.locator('#preparation-banner').isVisible(),true);assert.equal(await page.locator('.send-failed').last().evaluate(n=>n.firstChild.textContent),'failure draft');assert.equal(bodies.filter(x=>x.path==='/v1/chat/completions').length,before+1);
 await page.screenshot({path:output+'-failure-'+width+'.png'});
 assert((await page.locator('#preparation-banner').textContent()).includes('重试'));authMode=null;await page.locator('#preparation-banner button').click();await page.waitForFunction(()=>testFeedback().phase==='ready');assert.equal(bodies.filter(x=>x.path==='/v1/chat/completions').length,before+1);assert.equal(await page.locator('.send-failed').last().evaluate(n=>n.firstChild.textContent),'failure draft');
 report.cases.push({width,drawerBounds,normalBubbleImmediate:true,bannerVisibleWhilePending:false,cancelRetainedDraft:true,doubleClickEnterPosts:1,failureBlocked:true,revision});await ctx.close();
}assert.deepEqual(report.errors,[]);assert.deepEqual(report.external,[]);assert.equal(hash(fs.readFileSync(path.join(fixture,'data/archive-cache-manifest.json'))),manifestBefore);report.manifestSha256=manifestBefore;fs.writeFileSync(output+'.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));
}finally{await browser.close();server.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
