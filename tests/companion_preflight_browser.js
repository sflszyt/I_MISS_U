// Full-transaction timing starts BEFORE focus/input. Synthetic exact-origin only.
const fs=require('fs'),path=require('path'),http=require('http'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_CORE || require('node:path').join(require('node:os').homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright-core'));
const fixture=path.resolve(process.argv[2]),output=path.resolve(process.argv[3]),delay=Number(process.argv[4]||100);
let html=fs.readFileSync(path.join(fixture,'companion.html'),'utf8'),requests=[],authFailure=null,held=[],hold=false;
html=html.replace('var archiveOptions =',`window.testEvents=[];
function markD(name){testEvents.push({name,at:Date.now(),t:performance.now()});}
window.markD=markD;
window.dState=()=>({phase:archiveCache.deferred&&archiveCache.deferred.phase,epoch:archiveCache.epoch,pending:sendPending,streaming,history:history.length,scopeError});
window.dLocal=()=>archiveCache.deferred?archiveCache.deferred.localReady.then(()=>true,()=>false):Promise.resolve(false);
window.dReset=()=>{testEvents=[];};
window.dCancel=()=>archiveCache.forget();
window.dCold=()=>archiveCache.clear(false);
var archiveOptions =`)
.replace('function sendMessage(event) {',"function sendMessage(event) { markD('click');")
.replace('systemPrompt = context.system_prompt;',"markD('page-commit'); systemPrompt = context.system_prompt;")
.replace("pendingUser.className = 'bubble user';", "markD('user-bubble'); pendingUser.className = 'bubble user';")
.replace("pendingUser.className = 'bubble user-pending';", "markD('pending-user-bubble');requestAnimationFrame(()=>markD('pending-user-next-raf')); pendingUser.className = 'bubble user-pending';")
.replace("addBubble({type:'user', text: userText});","markD('user-bubble'); addBubble({type:'user', text: userText});")
.replace('function logSession(rec, requestSettings) {',"function logSession(rec, requestSettings) { markD('log-'+rec.role);")
.replace('pendingNotice.appendChild(pendingLabel); pendingNotice.appendChild(pendingCancel);',"pendingNotice.appendChild(pendingLabel); pendingNotice.appendChild(pendingCancel);markD('feedback-dom');requestAnimationFrame(()=>markD('feedback-frame'));")
.replace('accText += delta;',"markD('first-token'); accText += delta;");
const server=http.createServer((req,res)=>{const p=new URL(req.url,'http://localhost').pathname;requests.push({path:p,method:req.method,at:Date.now()});
 const json=x=>{res.setHeader('content-type','application/json');res.end(JSON.stringify(x));};
 if(p==='/companion.html'){res.setHeader('content-type','text/html');return res.end(html);}
 if(p==='/avatar.html'){res.setHeader('content-type','text/html');return res.end('<html></html>');}
 if(p==='/cdn-cgi/access/get-identity'){const end=()=>{if(authFailure){res.statusCode=authFailure;return json({});}json({account_id:'a'.repeat(32),user_uuid:'11111111-1111-4111-8111-111111111111'});};if(hold)held.push(end);else setTimeout(end,delay);return;}
 if(p.startsWith('/data/'))return setTimeout(()=>{const f=path.join(fixture,p);if(fs.existsSync(f)){res.setHeader('content-type','application/json');res.end(fs.readFileSync(f));}else{res.statusCode=404;json({});}},p.includes('manifest')?delay:0);
 if(req.method==='POST'){req.resume();req.on('end',()=>{if(p==='/v1/chat/completions'){res.setHeader('content-type','text/event-stream');return setTimeout(()=>res.end('data: {"choices":[{"delta":{"content":"synthetic reply"}}]}\n\ndata: [DONE]\n\n'),40);}json({ok:true});});return;}
 res.statusCode=503;json({});
});
(async()=>{await new Promise(r=>server.listen(0,'127.0.0.1',r));const origin='http://127.0.0.1:'+server.address().port;
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'}),context=await browser.newContext(),page=await context.newPage();
 page.setDefaultTimeout(30000);const errors=[],blocked=[];page.on('pageerror',e=>errors.push(String(e)));
 await context.route('**/*',r=>{if(new URL(r.request().url()).origin===origin)return r.continue();blocked.push(r.request().url());return r.abort();});
 await page.addInitScript(()=>{const fetchOriginal=fetch;window.fetch=function(url,...args){if(String(url).includes('/v1/chat/completions'))markD('chat-fetch');return fetchOriginal.call(this,url,...args);};});
 const result={fixture,delay,runnerSHA256:require('crypto').createHash('sha256').update(fs.readFileSync(__filename)).digest('hex'),runs:[],checks:[]};
 const ready=()=>page.waitForFunction(()=>document.querySelector('#intro-progress').textContent.includes('可以开始'));
 const finish=()=>page.waitForFunction(()=>!dState().pending&&!dState().streaming&&testEvents.some(e=>e.name==='first-token'));
 const quietDraft=async text=>page.evaluate(t=>{document.querySelector('#input-text').blur();const e=document.querySelector('#input-text');e.value=t;e.dispatchEvent(new Event('input',{bubbles:true}));},text);
 try{
  await page.goto(origin+'/companion.html');await page.locator('#input-text').evaluate(e=>{e.focus();e.value='synthetic before consent';e.dispatchEvent(new Event('input',{bubbles:true}));});await page.waitForTimeout(80);assert.equal(requests.filter(r=>r.path.includes('get-identity')).length,0);result.checks.push('no preflight authority before consent');
  await page.locator('#intro-ok').click();await ready();await page.locator('#intro-enter').click();
  const supports=await page.evaluate(()=>typeof archiveCache==='undefined'?false:!!archiveCache.stageForSend).catch(()=>false);
  // archiveCache is lexical inside the generated page; dState exposes feature state.
  const feature=html.includes('prototype.stageForSend =');result.supportsPreflight=feature;
  for(const mode of (process.env.D_MODES||'cold,no-preflight,in-flight,staged,long-idle').split(',')){
   for(let repetition=0;repetition<3;repetition++){
    if(mode==='cold')await page.evaluate(()=>dCold());
    await page.evaluate(()=>{document.querySelector('#input-text').blur();dReset();});requests=[];const started=Date.now();
    if(mode==='no-preflight'||mode==='cold')await quietDraft('synthetic archive '+mode+' '+repetition);
    else{
     await page.locator('#input-text').fill('synthetic archive '+mode+' '+repetition);
     if(mode==='staged'||mode==='long-idle'){
      if(feature){assert(await page.evaluate(()=>dLocal()));assert.equal(await page.evaluate(()=>dState().phase),'staged');}
      else await page.waitForTimeout(delay*3+150);
      assert.equal(await page.evaluate(()=>testEvents.filter(e=>/page-commit|log-|user-bubble|chat-fetch/.test(e.name)).length),0,'preflight must not publish');
      if(feature){assert.equal(requests.filter(r=>r.path.includes('get-identity')).length,2);assert.equal(requests.filter(r=>r.path.includes('manifest')).length,1);}
      if(mode==='long-idle')await page.waitForTimeout(1200);
     }
    }
    await page.locator('#send-btn').click();await finish();
    const events=await page.evaluate(()=>testEvents),click=events.find(e=>e.name==='click'),fetch=events.find(e=>e.name==='chat-fetch'),token=events.find(e=>e.name==='first-token');
    const authority=requests.filter(r=>r.path.includes('get-identity')||r.path.includes('manifest'));
    assert.equal(authority.filter(r=>r.path.includes('get-identity')).length,4);assert.equal(authority.filter(r=>r.path.includes('manifest')).length,2);
    assert.equal(requests.filter(r=>r.path==='/v1/chat/completions').length,1);assert.equal(events.filter(e=>e.name==='user-bubble').length,1);assert.equal(events.filter(e=>e.name==='log-user').length,1);assert.equal(events.filter(e=>e.name==='log-simulacrum').length,1);
    if(feature&&['staged','long-idle'].includes(mode)){assert(authority.slice(3).every(r=>r.at>=click.at),'terminal request started before Send');assert.equal(authority.filter(r=>r.at<click.at).length,3);}
    const feedback=events.find(e=>e.name==='feedback-dom'),frame=events.find(e=>e.name==='feedback-frame');
    const pendingUser=events.find(e=>e.name==='pending-user-bubble'),pendingFrame=events.find(e=>e.name==='pending-user-next-raf'),committedUser=events.find(e=>e.name==='user-bubble');
    result.runs.push({mode,repetition,started,clickToPendingUser:pendingUser?pendingUser.at-click.at:null,clickToPendingUserFrame:pendingFrame?pendingFrame.at-click.at:null,clickToCommittedUser:committedUser?committedUser.at-click.at:null,clickToFeedback:feedback?feedback.at-click.at:null,clickToFeedbackFrame:frame?frame.at-click.at:null,clickToFetch:fetch.at-click.at,clickToFirstToken:token.at-click.at,totalToFetch:fetch.at-started,events,requests:[...requests],preClickAuthority:authority.filter(r=>r.at<click.at).length,postClickAuthority:authority.filter(r=>r.at>=click.at).length});
   }
  }
  if(html.includes("pendingCancel.className = 'archive-send-cancel'")){
   await page.evaluate(()=>{document.querySelector('#input-text').blur();dReset();});requests=[];
   await page.locator('#input-text').fill('synthetic cancelled attempt');
   if(feature)assert(await page.evaluate(()=>dLocal()));
   hold=true;await page.locator('#send-btn').click();
   for(let i=0;i<200&&!held.length;i++)await page.waitForTimeout(10);assert.equal(held.length,1);
   await page.locator('.archive-send-cancel:not([disabled])').click();assert.equal(await page.locator('#input-text').inputValue(),'synthetic cancelled attempt');
   const cancelledRequests=[...requests];assert.equal(cancelledRequests.filter(r=>r.path==='/v1/chat/completions').length,0);
   hold=false;held.shift()();await page.evaluate(()=>dReset());requests=[];const started=Date.now();
   await quietDraft('synthetic cancellation recovery');await page.locator('#send-btn').click();await finish();
   const events=await page.evaluate(()=>testEvents),click=events.find(e=>e.name==='click'),fetch=events.find(e=>e.name==='chat-fetch'),token=events.find(e=>e.name==='first-token');
   const authority=requests.filter(r=>r.path.includes('get-identity')||r.path.includes('manifest'));
   assert.equal(authority.length,6);assert.equal(requests.filter(r=>r.path==='/v1/chat/completions').length,1);assert.equal(events.filter(e=>e.name==='log-user').length,1);
   result.runs.push({mode:'cancel-recovery',started,clickToFetch:fetch.at-click.at,clickToFirstToken:token.at-click.at,totalToFetch:fetch.at-started,events,requests:[...requests],cancelledRequests,preClickAuthority:authority.filter(r=>r.at<click.at).length,postClickAuthority:authority.filter(r=>r.at>=click.at).length});
  }else result.checks.push('baseline has no distinct pending cancellation control; cancellation scenario unavailable');
  result.errors=errors;result.blocked=blocked;assert.deepEqual(errors,[]);assert.deepEqual(blocked,[]);
  fs.writeFileSync(output,JSON.stringify(result,null,2));console.log(JSON.stringify(result.runs.map(({mode,clickToFetch,totalToFetch,preClickAuthority,postClickAuthority})=>({mode,clickToFetch,totalToFetch,preClickAuthority,postClickAuthority})),null,2));
 }catch(error){fs.writeFileSync(output+'.failure.json',JSON.stringify({error:String(error),requests,errors,blocked,state:await page.evaluate(()=>({state:dState(),events:testEvents,chat:document.querySelector('#chat').textContent,input:document.querySelector('#input-text').value}))},null,2));throw error;}
 finally{held.splice(0).forEach(f=>f());await browser.close();server.close();}
})().catch(e=>{console.error(e);server.close();process.exitCode=1;});
