// Real IndexedDB and real HTTP on ephemeral loopback; synthetic data only.
const fs=require('fs'),path=require('path'),http=require('http'),assert=require('node:assert/strict'),{createHash}=require('crypto');
const {chromium}=require(process.env.PLAYWRIGHT_CORE||require('node:path').join(require('node:os').homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright-core'));
const fixture=path.resolve(process.argv[2]);
const nextFixture=process.argv[3]?path.resolve(process.argv[3]):null;
let currentHTML=fs.readFileSync(fixture+'/companion.html');
const stable=v=>Array.isArray(v)?'['+v.map(stable).join(',')+']':v&&typeof v==='object'?'{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+stable(v[k])).join(',')+'}':JSON.stringify(v);
const hash=v=>createHash('sha256').update(v).digest('hex');
const files=new Map(fs.readdirSync(fixture+'/data').filter(n=>n!=='archive-cache-manifest.json').map(n=>['/data/'+n,fs.readFileSync(fixture+'/data/'+n)]));
let manifest=JSON.parse(fs.readFileSync(fixture+'/data/archive-cache-manifest.json'));
function updateManifest(){manifest.files=manifest.files.map(f=>({...f,bytes:files.get('/'+f.path).length,sha256:hash(files.get('/'+f.path))}));const base={...manifest};delete base.revision;manifest.revision=hash(stable(base));}
let counts={},posts=0,authError=null,identity='11111111-1111-4111-8111-111111111111',hold=null,held=[],authCalls=0,allowSend=false,llmBodies=[],holdLLM=false,llmHeld=[];
const server=http.createServer((req,res)=>{
 const url=new URL(req.url,'http://localhost'),p=url.pathname;counts[p]=(counts[p]||0)+1;
 const json=o=>{res.setHeader('content-type','application/json');res.end(JSON.stringify(o));};
 if(req.method!=='GET'){
  posts++;if(!allowSend){res.statusCode=500;return res.end('NO POST ALLOWED');}
  let body='';req.on('data',b=>body+=b);req.on('end',()=>{
   if(p==='/v1/chat/completions'){llmBodies.push(JSON.parse(body));res.setHeader('content-type','text/event-stream');const finish=()=>res.end('data: {"choices":[{"delta":{"content":"synthetic response"}}]}\n\ndata: [DONE]\n\n');if(holdLLM)llmHeld.push(finish);else finish();}
   else json({ok:true});
  });return;
 }
 if(p==='/cdn-cgi/access/get-identity'){
  authCalls++;
  assert(url.searchParams.get('archive_check'));
  res.setHeader('Cache-Control','no-store');
  if(authError==='network'){res.destroy();return;}
  if(authError==='redirect'){res.statusCode=302;res.setHeader('location','/login');return res.end();}
  if(authError===401||authError===403){res.statusCode=authError;return json({});}
  if(authError==='json')return res.end('{broken');
  return json(authError==='missing'?{err:'no app token set'}:{account_id:'a'.repeat(32),user_uuid:identity});
 }
 if(p==='/data/archive-cache-manifest.json'){assert(url.searchParams.get('archive_check'));res.setHeader('Cache-Control','no-store');return json(manifest);}
 if(p==='/companion.html'){res.setHeader('content-type','text/html');return res.end(currentHTML);}
 if(p==='/avatar.html'){res.setHeader('content-type','text/html');return res.end('<html></html>');}
 if(p==='/health'){res.statusCode=503;return json({});}
 if(p.includes('sessions_father'))return json({viewer:'father',sessions:[{session_id:'test-only',date:'2000-01-01',turns:[{role:'user',text:'PRIVATE_REALTIME_SENTINEL',turn:1}]}],recent_dates:[]});
 if(files.has(p)){res.setHeader('content-type','application/json');if(hold===p){held.push(()=>res.end(files.get(p)));return;}return res.end(files.get(p));}
 res.statusCode=404;json({});
});
async function stored(page){return page.evaluate(()=>new Promise((resolve,reject)=>{const r=indexedDB.open('companion-private-archive-v1',1);r.onsuccess=()=>{const db=r.result;if(!db.objectStoreNames.contains('files')){db.close();resolve([]);return;}const tx=db.transaction('files'),q=tx.objectStore('files').getAll();q.onsuccess=()=>resolve(q.result.map(v=>({...v,raw:Array.from(new Uint8Array(v.raw))})));tx.oncomplete=()=>db.close();};r.onerror=()=>reject(r.error);}));}
const bulk=()=>Object.keys(counts).filter(p=>files.has(p)).reduce((n,p)=>n+counts[p],0);
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const origin='http://127.0.0.1:'+server.address().port;
 const browser=await chromium.launch({headless:true,executablePath:process.env.EDGE_EXE||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 const ctx=await browser.newContext(),page=await ctx.newPage(),errors=[];page.on('pageerror',e=>errors.push(String(e)));page.setDefaultTimeout(8000);
 const ready=()=>page.waitForFunction(()=>document.querySelector('#intro-progress').textContent.includes('可以开始聊天'));
 const hidden=()=>page.waitForFunction(()=>document.querySelector('#preparation-banner').hidden);
 try{
  hold='/data/messages-2000.json';await page.goto(origin+'/companion.html');await page.locator('#intro-ok').click();
  await page.waitForTimeout(250);assert(held.length);await page.locator('#intro-enter').click();assert(await page.locator('#preparation-banner').isVisible());
  await page.locator('#input-text').fill('synthetic blocked send');await page.locator('#send-btn').click();await page.waitForTimeout(150);assert.equal(posts,0);
  hold=null;held.splice(0).forEach(f=>f());await hidden();console.log('PASS early enter loading then ready hides banner, loading send gate');
  // The pending synthetic send may proceed after readiness; never permit any external destination.
  await page.reload();await page.locator('#intro-ok').click();await ready();counts={};
  await page.reload();await page.locator('#intro-ok').click();await ready();assert.equal(bulk(),0);assert.equal((await stored(page)).length,5);
  await page.locator('#intro-enter').click();await hidden();console.log('PASS actual IDB cache hit and enter after ready');
  allowSend=true;
  await page.evaluate(()=>{window.loadingFlashes=[];new MutationObserver(()=>{for(const n of document.querySelectorAll('#chat .notice,#preparation-banner'))if(n.getBoundingClientRect().height&&/正在.*校验/.test(n.textContent))window.loadingFlashes.push(n.textContent);}).observe(document.body,{subtree:true,childList:true,characterData:true,attributes:true});});
  for(let i=0;i<2;i++){
   const previous=llmBodies.length,authBefore=authCalls;counts={};
   await page.locator('#input-text').fill('synthetic warm send '+i);await page.locator('#send-btn').click();
   await page.waitForFunction(()=>!document.querySelector('#send-btn').classList.contains('stop')&&!document.querySelector('#input-text').value);
   assert.equal(llmBodies.length,previous+1);assert.equal(bulk(),0);assert(authCalls>authBefore);assert(counts['/data/archive-cache-manifest.json']>0);console.log('warm send '+i+': bulk='+bulk()+', auth='+(authCalls-authBefore)+', manifest='+counts['/data/archive-cache-manifest.json']);
  }
  assert.deepEqual(await page.evaluate(()=>window.loadingFlashes),[],'warm sends must not flash loading UI');console.log('PASS two warm sends: zero bulk, fresh identity/manifest gates, no loading flash');allowSend=false;
  allowSend=true;files.set('/data/messages-2001.json',Buffer.from('[ ]\n'));updateManifest();hold='/data/messages-2001.json';const previous=llmBodies.length;
  await page.locator('#input-text').fill('synthetic new revision');await page.locator('#send-btn').click();
  await page.waitForFunction(()=>!document.querySelector('#preparation-banner').hidden);await page.waitForTimeout(100);assert(held.length);assert.equal(llmBodies.length,previous);
  hold=null;held.splice(0).forEach(f=>f());await page.waitForFunction(()=>!document.querySelector('#send-btn').classList.contains('stop')&&!document.querySelector('#input-text').value);assert.equal(llmBodies.length,previous+1);await hidden();allowSend=false;console.log('PASS changed revision downloads visibly and send waits');
  authError=403;const deniedBefore=llmBodies.length;allowSend=true;
  await page.locator('#input-text').fill('synthetic warm revoked');await page.locator('#send-btn').click();
  await page.waitForFunction(()=>[...document.querySelectorAll('#chat .notice')].some(n=>n.textContent.includes('本次未发送') || n.textContent.includes('输入已保留')));
  assert.equal(llmBodies.length,deniedBefore);assert.equal(await page.locator('#input-text').inputValue(),'synthetic warm revoked');assert(await page.locator('#preparation-banner').isVisible());
  authError=null;await page.locator('#preparation-banner button').click();await hidden();allowSend=false;console.log('PASS warm revoked validation materializes error, preserves draft, blocks LLM');
  await page.locator('#settings-btn').click();await page.locator('#drawer .archive-cache-enabled').uncheck();await page.locator('#drawer-close-btn').click();
  assert(await page.locator('#preparation-banner').isVisible());
  authError=403;await page.locator('#settings-btn').click();await page.locator('#drawer .archive-cache-retry').click();await page.locator('#drawer-close-btn').click();
  await page.waitForFunction(()=>!document.querySelector('#preparation-banner button').hidden);assert(await page.locator('#preparation-banner').isVisible());
  const before=posts;await page.locator('#input-text').fill('synthetic unauthorized');await page.locator('#send-btn').click();await page.waitForTimeout(200);assert.equal(posts,before);
  authError=null;await page.locator('#preparation-banner button').click();await hidden();console.log('PASS failure visible, unauthorized send blocked, retry ready hidden');
  await page.locator('#settings-btn').click();await page.locator('#drawer-close-btn').click();await hidden();
  for(const width of [320,390]){
   await page.setViewportSize({width,height:700});
   await page.waitForFunction(()=>{const d=document.querySelector('#drawer');return d.getBoundingClientRect().left>=innerWidth&&!d.getAnimations().some(a=>a.playState==='running');});
   const geometry=await page.evaluate(()=>{const b=document.querySelector('#preparation-banner'),chat=document.querySelector('#chat');let prev=b.previousElementSibling;while(prev&&(!prev.getBoundingClientRect().height||getComputedStyle(prev).position==='fixed'))prev=prev.previousElementSibling;return {display:getComputedStyle(b).display,height:b.getBoundingClientRect().height,chatTop:chat.getBoundingClientRect().top,previousBottom:prev.getBoundingClientRect().bottom,scroll:document.documentElement.scrollWidth,width:innerWidth};});
   assert.equal(geometry.display,'none');assert.equal(geometry.height,0);assert(Math.abs(geometry.chatTop-geometry.previousBottom)<1,JSON.stringify(geometry));assert(geometry.scroll<=width);
   await page.screenshot({path:path.join(fixture,'ready-'+width+'.png')});console.log('PASS viewport '+width+' '+JSON.stringify(geometry));
  }
  assert.deepEqual(errors,[]);console.log('PASS no browser page errors');
 }finally{await browser.close();server.close();}
})().catch(e=>{console.error(e);server.close();process.exitCode=1;});
