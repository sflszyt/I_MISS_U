// Real IndexedDB and real HTTP on ephemeral loopback; synthetic data only.
const fs=require('fs'),path=require('path'),http=require('http'),assert=require('node:assert/strict'),{createHash}=require('crypto');
const {chromium}=require(process.env.PLAYWRIGHT_CORE||require('node:path').join(require('node:os').homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright-core'));
const fixture=path.resolve(process.argv[2]);
const nextFixture=process.argv[3]?path.resolve(process.argv[3]):null;
let currentHTML=fs.readFileSync(fixture+'/companion.html','utf8').replace(/\r?\ninit\(\);\r?\n/, `
window.__prefsTest={snapshot:function(){return {voice:autoVoiceSession.enabled,text:showVoiceText,memory:noMemoryEnabled,checked:cfgNoMemory.checked,ready:autoVoiceSession.ready,job:autoVoiceSession.job};},reload:loadUiPrefs,choose:function(){autoVoiceSession.checkbox.checked=false;autoVoiceSession.checkbox.dispatchEvent(new Event('change'));cfgVoiceText.checked=false;onVoiceTextToggle();cfgNoMemory.checked=true;onNoMemoryToggle();},queue:function(){ttsAvailable=false;logSession({role:'user',text:'synthetic-default'});cfgNoMemory.checked=true;onNoMemoryToggle();logSession({role:'user',text:'synthetic-on'});cfgNoMemory.checked=false;onNoMemoryToggle();logSession({role:'user',text:'synthetic-off'});return readSessionQueue().filter(r=>r.text.startsWith('synthetic-')||r.text==='exclude_session').map(r=>({text:r.text,exclude:r.exclude===true}));}};
init();
`);
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
 await ctx.route('**/*',route=>new URL(route.request().url()).origin===origin?route.continue():route.abort());
 await ctx.addInitScript(()=>{localStorage.setItem('companion_synthetic_byok_father_ui',JSON.stringify({voiceText:false,autoVoiceEnabled:false}));sessionStorage.setItem('companion_synthetic_byok_father_ui','old');localStorage.setItem('unrelated-history-sentinel','keep');});
 const defaults=async p=>assert.deepEqual(await p.evaluate(()=>window.__prefsTest.snapshot()),{voice:true,text:true,memory:false,checked:false,ready:false,job:null});
 const report=[];
 const ready=p=>p.waitForFunction(()=>document.querySelector('.archive-cache-status').textContent.includes('已校验 5/5')&&document.querySelector('#intro-progress').textContent.includes('可以开始聊天'));
 const consent=async p=>{await p.locator('#intro-ok').click();await ready(p);};
 const reload=async()=>{counts={};await page.reload();await defaults(page);await consent(page);await defaults(page);};
 try{
  await page.goto(origin+'/companion.html');await page.waitForTimeout(150);assert.equal(bulk(),0);assert.equal(authCalls,0);await consent(page);
  await defaults(page);
  const queued=await page.evaluate(()=>window.__prefsTest.queue());
  assert.deepEqual(queued,[{text:'synthetic-default',exclude:false},{text:'exclude_session',exclude:true},{text:'synthetic-on',exclude:true},{text:'synthetic-off',exclude:false}]);
  const ui=await ctx.newPage();await ui.goto(origin+'/companion.html');await consent(ui);await ui.locator('#intro-enter').click();
  await ui.locator('#settings-btn').click();
  for(const width of [320,390]){await ui.setViewportSize({width,height:900});for(const id of ['cfg-auto-voice','cfg-voice-text','cfg-no-memory']){const el=ui.locator('#'+id);await el.scrollIntoViewIfNeeded();assert(await el.isVisible());const box=await el.boundingBox();assert(box.x>=0&&box.x+box.width<=width);}await ui.screenshot({path:path.join(fixture,'settings-'+width+'.png')});}
  await ui.locator('#cfg-auto-voice').uncheck();await ui.locator('#cfg-voice-text').uncheck();await ui.locator('#cfg-no-memory').check();
  await ui.evaluate(()=>{window.__prefsTest.reload();window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));});
  await ui.waitForTimeout(300);
  assert.deepEqual(await ui.evaluate(()=>{const s=window.__prefsTest.snapshot();return [s.voice,s.text,s.memory,s.checked,localStorage.getItem('unrelated-history-sentinel')];}),[false,false,true,true,'keep']);
  await ui.reload();await defaults(ui);await ui.close();
  report.push('old local/session prefs ignored; default/on/off records preserve exclude event; repeated load and BFCache preserve current choices; unrelated storage retained');
  assert.equal(bulk(),5);let entries=await stored(page);assert.equal(entries.length,5);assert(!JSON.stringify(entries).includes('PRIVATE_REALTIME'));assert(!entries.some(v=>/sessions|audio/.test(v.path)));report.push('first load + consent + allowlist');
  await reload();assert.equal(bulk(),0);assert((await page.locator('.archive-cache-status').first().innerText()).includes('本地读取 5'));report.push('actual refresh: zero bulk transfers');
  files.set('/data/messages-2001.json',Buffer.from('[ ]\n'));updateManifest();await reload();assert.equal(bulk(),1);assert.equal(counts['/data/messages-2001.json'],1);report.push('revision migration: one changed file');
  await page.evaluate(()=>new Promise(resolve=>{const r=indexedDB.open('companion-private-archive-v1',1);r.onsuccess=()=>{const db=r.result,tx=db.transaction('files','readwrite'),s=tx.objectStore('files'),q=s.get('data/transcripts.json');q.onsuccess=()=>s.put({...q.result,raw:new Uint8Array([0]).buffer});tx.oncomplete=()=>{db.close();resolve();};};}));
  await reload();assert.equal(bulk(),1);assert.equal(counts['/data/transcripts.json'],1);report.push('damaged IndexedDB bytes refetched');
  const contrasts=[];
  for(const width of [320,390]){await page.setViewportSize({width,height:700});const clear=page.locator('#intro-card .archive-cache-clear');await clear.scrollIntoViewIfNeeded();const box=await clear.boundingBox();assert(box.x>=0&&box.x+box.width<=width);assert(await clear.isVisible());
   const colors=await page.evaluate(()=>['#intro-card .archive-cache-status','#intro-card .archive-cache-controls p','#intro-card .archive-cache-controls label','#intro-progress'].map(selector=>({selector,foreground:getComputedStyle(document.querySelector(selector)).color,background:getComputedStyle(document.querySelector('#intro-card')).backgroundColor})));
   const luminance=s=>s.match(/[\d.]+/g).slice(0,3).map(Number).map(n=>{n/=255;return n<=.04045?n/12.92:((n+.055)/1.055)**2.4;}).reduce((sum,n,i)=>sum+n*[.2126,.7152,.0722][i],0);
   for(const c of colors){const a=luminance(c.foreground),b=luminance(c.background),ratio=(Math.max(a,b)+.05)/(Math.min(a,b)+.05);assert(ratio>=4.5,JSON.stringify(c));contrasts.push({width,...c,ratio});}
   await page.screenshot({path:path.join(fixture,'viewport-'+width+'.png')});
  }report.push('320/390 controls reachable and foreground contrast >=4.5:1');fs.writeFileSync(path.join(fixture,'contrast.json'),JSON.stringify(contrasts,null,2));
  await page.locator('#intro-card .archive-cache-clear').click();await page.waitForFunction(()=>document.querySelector('.archive-cache-status').textContent.includes('已清除'));assert.equal((await stored(page)).length,0);
  hold='/data/messages-2000.json';await page.evaluate(()=>window.__prefsTest.choose());await page.locator('#intro-card .archive-cache-retry').click();await page.waitForTimeout(250);assert(held.length);await page.locator('#intro-card .archive-cache-clear').click();hold=null;held.splice(0).forEach(fn=>fn());await page.waitForTimeout(300);assert.equal((await stored(page)).length,0);assert(!(await page.locator('#intro-progress').innerText()).includes('已经准备好'));assert.deepEqual(await page.evaluate(()=>{const s=window.__prefsTest.snapshot();return [s.voice,s.text,s.memory,s.checked];}),[false,false,true,true]);report.push('clear cancels delayed response and readiness; manual preferences survive delayed load/clear');
  await page.locator('#intro-card .archive-cache-retry').click();await ready(page);
  const other=await ctx.newPage();await other.goto(origin+'/companion.html');await consent(other);
  await other.locator('#intro-card .archive-cache-clear').click();await page.waitForTimeout(100);assert((await page.locator('.archive-cache-status').first().innerText()).includes('另一页面'));assert.equal((await stored(page)).length,0);
  await other.locator('#intro-card .archive-cache-enabled').uncheck();await page.waitForFunction(()=>!document.querySelector('.archive-cache-enabled').checked&&document.querySelector('.archive-cache-status').textContent.includes('停用'));
  await other.locator('#intro-card .archive-cache-enabled').check();await page.waitForFunction(()=>document.querySelector('.archive-cache-enabled').checked);
  await other.close();report.push('cross-tab invalidation and immediate disable/enable checkbox/status');
  await page.locator('#intro-card .archive-cache-enabled').uncheck();await page.waitForTimeout(150);await reload();assert.equal(bulk(),5);assert.equal((await stored(page)).length,0);await reload();assert.equal(bulk(),5);report.push('disable retained across actual refresh; online downloads');
  await page.locator('#intro-card .archive-cache-enabled').check();await page.waitForTimeout(100);await page.locator('#intro-card .archive-cache-retry').click();await ready(page);assert.equal((await stored(page)).length,5);
  for(const bad of ['missing',401,403,'redirect','network','json']){
   authError=bad;await page.locator('#intro-card .archive-cache-retry').click();await page.waitForFunction(()=>document.querySelector('.archive-cache-status').textContent.includes('无法验证'));assert.equal((await stored(page)).length,0);assert.equal(posts,0);authError=null;await page.locator('#intro-card .archive-cache-retry').click();await ready(page);
  }report.push('live authority rejects missing identity/401/403/redirect/network/malformed');
  authError='missing';await page.locator('#intro-enter').click();await page.locator('#input-text').fill('do not send while unauthorized');await page.locator('#send-btn').click();await page.waitForTimeout(300);assert.equal(posts,0);assert.equal(await page.locator('#input-text').inputValue(),'do not send while unauthorized');report.push('warm cached send rechecks authority and preserves draft');authError=null;
  const memoryPath=[...files.keys()].find(p=>/\/memories-/.test(p));
  if(memoryPath){
   await page.reload();await consent(page);const original=files.get(memoryPath),bad=JSON.parse(original);bad.entries[0].provenance.sources[0].text_sha256='f'.repeat(64);files.set(memoryPath,Buffer.from(JSON.stringify(bad)));updateManifest();
   await page.locator('#intro-card .archive-cache-retry').click();await page.waitForFunction(()=>document.querySelector('#intro-progress').textContent.includes('重试'));assert(!(await page.locator('#intro-progress').innerText()).includes('可以开始聊天'));
   await page.locator('#intro-enter').click();await page.locator('#input-text').fill('synthetic plan');await page.locator('#send-btn').click();await page.waitForTimeout(250);assert.equal(posts,0);report.push('corrupted bound card/source hash blocks readiness/send');
   files.set(memoryPath,original);updateManifest();await page.reload();await consent(page);await page.locator('#intro-enter').click();allowSend=true;
   await page.locator('#input-text').fill('synthetic plan');await page.locator('#send-btn').click();await page.waitForTimeout(800);
   assert.equal(llmBodies.length,1);const payload=JSON.stringify(llmBodies[0]);assert(payload.includes('completion unknown'));assert(payload.includes(hash(stable(JSON.parse(original).entries[0].provenance.sources))));
   report.push('valid card survives cached refresh and source digest reaches synthetic LLM retrieval');allowSend=false;
  }
  for(const action of ['clear','disable','foreground','bfcache']){
   allowSend=true;await page.reload();await consent(page);await page.locator('#intro-enter').click();holdLLM=true;const before=llmBodies.length;
   await page.locator('#input-text').fill('synthetic plan active '+action);await page.locator('#send-btn').click();
   for(let i=0;i<100&&llmBodies.length===before;i++)await page.waitForTimeout(20);assert.equal(llmBodies.length,before+1);assert(await page.locator('#send-btn').evaluate(e=>e.classList.contains('stop')));
   if(action==='clear'||action==='disable'){await page.locator('#settings-btn').click();if(action==='clear')await page.locator('#drawer .archive-cache-clear').click();else await page.locator('#drawer .archive-cache-enabled').uncheck();await page.locator('#drawer-close-btn').click();}
   else await page.evaluate(kind=>{if(kind==='foreground')document.dispatchEvent(new Event('visibilitychange'));else window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));},action);
   await page.waitForFunction(()=>!document.querySelector('#send-btn').classList.contains('stop'));holdLLM=false;llmHeld.splice(0).forEach(fn=>fn());
   await page.locator('#input-text').fill('synthetic plan recovery '+action);await page.locator('#send-btn').click();
   for(let i=0;i<100&&llmBodies.length<before+2;i++)await page.waitForTimeout(20);assert.equal(llmBodies.length,before+2);await page.waitForFunction(()=>!document.querySelector('#send-btn').classList.contains('stop'));
  }report.push('active send clear/disable/foreground/BFCache cleanup allows immediate next send');
  if(nextFixture){
   allowSend=false;await page.reload();await consent(page);await page.locator('#intro-card .archive-cache-enabled').check();await page.waitForTimeout(100);await page.locator('#intro-card .archive-cache-retry').click();await ready(page);
   const oldManifest=structuredClone(manifest),oldHTML=currentHTML,oldFiles=new Map(files),oldMemory=manifest.files.find(f=>f.path.startsWith('data/memories-')).path;
   function upgrade(){manifest=JSON.parse(fs.readFileSync(nextFixture+'/data/archive-cache-manifest.json'));currentHTML=fs.readFileSync(nextFixture+'/companion.html');for(const p of [...files.keys()])if(p.includes('/memories-'))files.delete(p);for(const f of manifest.files)if(f.path.includes('/memories-')||f.path===manifest.context_path)files.set('/'+f.path,fs.readFileSync(path.join(nextFixture,f.path)));updateManifest();}
   const directCtx=await browser.newContext(),direct=await directCtx.newPage();await direct.goto(origin+'/companion.html');await consent(direct);counts={};upgrade();await direct.reload();await consent(direct);assert.equal(bulk(),2);assert.equal(counts['/data/chat_context.json'],1);assert.equal((await stored(direct)).some(r=>r.path===oldMemory),false);await directCtx.close();report.push('new page memory-release upgrade downloads context+memory only');
   manifest=oldManifest;currentHTML=oldHTML;files.clear();for(const [k,v] of oldFiles)files.set(k,v);counts={};upgrade();const postsBefore=posts;
   await page.locator('#intro-card .archive-cache-retry').click();await page.waitForFunction(()=>document.querySelector('.archive-cache-status').textContent.includes('档案版本已更新'));assert.equal(bulk(),0);const kept=await stored(page);assert.equal(kept.length,3);assert(!kept.some(r=>r.path===oldMemory||r.path==='data/chat_context.json'));
   await page.locator('#intro-enter').click();await page.locator('#input-text').fill('old page must not send');await page.locator('#send-btn').click();await page.waitForTimeout(200);assert.equal(posts,postsBefore);
   counts={};await page.reload();await consent(page);assert.equal(bulk(),2);const memoryName=manifest.files.find(f=>f.path.startsWith('data/memories-')).path;assert.equal(counts['/'+memoryName],1);assert.equal((await stored(page)).length,5);report.push('old page rejects new binding, prunes obsolete raw, refreshed page reuses unchanged shards');
  }
  await page.reload();await consent(page);await defaults(page);
  await page.evaluate(()=>{const proto=globalThis.ArchiveDeviceCache.ArchiveDeviceCache.prototype,original=proto.prepare;proto.prepare=function(){return original.call(this).then(result=>{localStorage.setItem('companion_archive_disabled','true');proto.prepare=original;return result;});};});
  await page.locator('#intro-card .archive-cache-retry').click();await page.waitForTimeout(250);assert.equal((await stored(page)).length,0,'policy change between module readiness and page commit must clear retained bytes');assert.equal(await page.locator('#intro-card .archive-cache-enabled').isChecked(),false);report.push('policy change after module readiness but before page commit rejects and cleans cache');
  assert.deepEqual(errors,[]);console.log(JSON.stringify({pass:true,checks:report,syntheticPosts:posts,realPosts:0,pageErrors:errors},null,2));
 }finally{held.splice(0).forEach(fn=>fn());await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);server.close();process.exitCode=1;});
