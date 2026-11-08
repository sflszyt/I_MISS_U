// Actual generated page, Edge and IndexedDB; synthetic loopback only.
const fs=require('fs'),path=require('path'),http=require('http'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_CORE || require('node:path').join(require('node:os').homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright-core'));
const fixture=path.resolve(process.argv[2]),output=path.resolve(process.argv[3]);
let mode=200,hold=false,held=[],posts=0;
let html=fs.readFileSync(path.join(fixture,'companion.html'),'utf8').replace('var archiveOptions =',`
window.failureReports=0;
window.failureState=()=>({phase:dataReadyPhase,pending:sendPending,streaming,owner:archiveCache.operationOwner,epoch:archiveCache.epoch,retained:archiveCache.retained,draft:inputText.value});
window.failureRetry=()=>ensureDataReady();
window.failureSupersede=()=>{archiveCache.forget(false);return ensureDataReady();};
window.failureAwait=()=>archiveCache.deferred?archiveCache.deferred.localReady.then(()=>true,()=>false):Promise.resolve(false);
window.failureCount=()=>archiveCache.store.run((m,s,c,done)=>{const q=s.getAll();q.onsuccess=()=>done(q.result.length);});
var originalFailure=dataFailure;dataFailure=function(...a){failureReports++;return originalFailure(...a);};
var archiveOptions =`);
const server=http.createServer((req,res)=>{
 const p=new URL(req.url,'http://localhost').pathname,json=x=>{res.setHeader('content-type','application/json');res.end(JSON.stringify(x));};
 if(p==='/companion.html'){res.setHeader('content-type','text/html');return res.end(html);}
 if(p==='/avatar.html'){res.setHeader('content-type','text/html');return res.end('<html></html>');}
 if(p==='/cdn-cgi/access/get-identity'){
  const captured=mode,end=()=>{res.statusCode=captured;json(captured===200?{account_id:'a'.repeat(32),user_uuid:'11111111-1111-4111-8111-111111111111'}:{});};
  if(hold)held.push(end);else end();return;
 }
 if(p.startsWith('/data/')){const file=path.join(fixture,p);if(fs.existsSync(file)){res.setHeader('content-type','application/json');return res.end(fs.readFileSync(file));}}
 if(req.method==='POST'){posts++;req.resume();req.on('end',()=>json({ok:true}));return;}
 res.statusCode=404;json({});
});
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const origin='http://127.0.0.1:'+server.address().port;
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 const context=await browser.newContext(),page=await context.newPage(),blocked=[],errors=[],checks=[];
 await context.route('**/*',r=>{if(new URL(r.request().url()).origin===origin)return r.continue();blocked.push(r.request().url());return r.abort();});
 page.on('pageerror',e=>errors.push(String(e)));page.setDefaultTimeout(15000);
 const draft=async t=>{await page.locator('#input-text').fill(t);};
 const release=()=>{const q=held;held=[];q.forEach(f=>f());};
 try{
  await page.goto(origin+'/companion.html');await page.locator('#intro-ok').click();await page.waitForFunction(()=>failureState().phase==='ready');await page.locator('#intro-enter').click();
  mode=401;await draft('synthetic retained draft');await page.evaluate(()=>failureAwait());
  let state=await page.evaluate(()=>failureState());assert.equal(state.phase,'failed','unclaimed preflight must leave failed UI, not idle/loading');
  assert.equal(state.draft,'synthetic retained draft');assert.equal(await page.evaluate(()=>failureReports),1);assert.equal(await page.evaluate(()=>failureCount()),0);assert.equal(posts,0);
  assert(await page.locator('#preparation-banner').isVisible());assert(await page.locator('#preparation-banner button').isVisible());assert((await page.locator('#preparation-banner').innerText()).includes('VALIDATION'));checks.push('unclaimed authority failure publishes once, clears own IDB, preserves input, no POST');
  mode=200;await page.locator('#preparation-banner button').click();await page.waitForFunction(()=>failureState().phase==='ready');assert.equal(await page.evaluate(()=>failureCount()),34);checks.push('explicit retry recovers all 34 actual IDB records');
  // A is held in its first identity request. B supersedes and completes first.
  mode=403;hold=true;await draft('synthetic late A');await page.waitForFunction(()=>!!window.failureState);
  while(!held.length)await new Promise(r=>setTimeout(r,5));
  const old=page.evaluate(()=>failureAwait());mode=200;hold=false;assert(await page.evaluate(()=>failureSupersede()));
  const before=await page.evaluate(()=>({state:failureState(),reports:failureReports}));release();await old;
  const after=await page.evaluate(()=>({state:failureState(),reports:failureReports}));assert.deepEqual(after,before);assert.equal(await page.locator('#preparation-banner').isVisible(),false);assert.equal(await page.evaluate(()=>failureCount()),34);checks.push('late failed unclaimed A cannot clear or replace B ready state');
  // Claimed first phase uses the existing Send catch, never both publication paths.
  mode=401;hold=true;await draft('synthetic claimed draft');while(!held.length)await new Promise(r=>setTimeout(r,5));
  const prior=await page.evaluate(()=>failureReports);await page.locator('#send-btn').click();hold=false;release();
  await page.waitForFunction(()=>!failureState().pending&&!failureState().streaming&&failureState().phase==='failed');
  assert.equal(await page.evaluate(()=>failureReports),prior+1);assert.equal(await page.locator('#input-text').inputValue(),'synthetic claimed draft');assert.equal(posts,0);checks.push('claimed failure publishes exactly once and preserves draft');
  assert.deepEqual(errors,[]);assert.deepEqual(blocked,[]);
  fs.writeFileSync(output,JSON.stringify({checks,posts,errors,blocked},null,2));console.log(JSON.stringify({checks,posts,errors,blocked}));
 }finally{release();await browser.close();server.close();}
})().catch(e=>{console.error(e);process.exitCode=1;server.close();});
