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
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 const results=[];
 try{for(const width of [320,390]){
  const origin='http://127.0.0.1:'+server.address().port,ctx=await browser.newContext({viewport:{width,height:844}});
  await ctx.route('**/*',r=>new URL(r.request().url()).origin===origin?r.continue():r.abort());
  const page=await ctx.newPage();await page.goto(origin+'/companion.html');await page.locator('#intro-ok').click();
  await page.waitForFunction(()=>document.querySelector('#intro-progress').textContent.includes('可以开始'));await page.locator('#intro-enter').click();
  await page.locator('#input-text').fill('First explicit line\nSecond explicit line\nThird explicit line');const initial=await page.locator('#send-btn').boundingBox();
  const before=bodies.filter(x=>x.path==='/v1/chat/completions').length;
  holdIdentity=true;await page.mouse.dblclick(initial.x+initial.width/2,initial.y+initial.height/2,{delay:100});await page.waitForTimeout(150);
  const pending=await page.locator('#send-btn').boundingBox();assert.deepEqual(pending,initial,'fixed-coordinate target must remain stable');
  await page.screenshot({path:output+'-pending-'+width+'.png'});
  holdIdentity=false;heldIdentities.splice(0).forEach(f=>f());await page.waitForFunction(()=>!testFeedback().pending&&!testFeedback().streaming);
  const result={width,initial,pending,posts:bodies.filter(x=>x.path==='/v1/chat/completions').length-before,draft:await page.locator('#input-text').inputValue(),notices:await page.locator('.bubble.notice').allTextContents(),userLogs:await page.evaluate(()=>(window.testLogs||[]).filter(x=>x.rec.role==='user').length)};
  results.push(result);fs.writeFileSync(output+'.json',JSON.stringify(results,null,2));console.log(JSON.stringify(result));
  assert.equal(result.posts,1,'fixed-coordinate double click must send once, never hit a moved Cancel button');assert.equal(result.userLogs,1);assert(!result.notices.some(s=>s.includes('已取消')));await ctx.close();
 }}finally{await browser.close();server.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
