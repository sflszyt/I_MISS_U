// Full generated page in Edge, all network requests fulfilled locally or aborted.
const fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_CORE||require('node:path').join(require('node:os').homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright-core'));
const fixture=path.resolve(__dirname,'../evidence/temp/terra-default');
const origin='http://terra-fixture.invalid',key='companion_' + 'synthetic_byok_father';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.EDGE_EXE||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 const report=[];
 try {
  for(const scenario of [
   {name:'fresh'}, {name:'legacy BYOK',stored:{provider:'openai',url:'https://api.deepseek.com/chat/completions',model:'deepseek-v4-pro',key:'SYNTHETIC'}},
   {name:'profile BYOK',stored:{provider:'deepseek',model:'deepseek-v4-pro',profiles:{deepseek:{url:'https://api.deepseek.com/chat/completions',model:'deepseek-v4-pro',key:'SYNTHETIC'}}}},
   {name:'Terra disabled',disabled:true}, {name:'manual DeepSeek',manual:'deepseek-v4-pro'}, {name:'manual Luna',manual:'gpt-6-luna'}, {name:'manual Sol',manual:'gpt-6.1-sol'},
   {name:'async click snapshot',delay:true}, {name:'missing select fallback',remove:true}
  ]) {
   const ctx=await browser.newContext({serviceWorkers:'block'}),page=await ctx.newPage(),bodies=[],errors=[],blocked=[];
   let releaseShard, shardSeen=false;
   const shardGate=new Promise(r=>releaseShard=r);
   page.on('pageerror',e=>errors.push(String(e)));page.setDefaultTimeout(8000);
   if(scenario.stored) await ctx.addInitScript(({key,stored})=>localStorage.setItem(key,JSON.stringify(stored)),{key,stored:scenario.stored});
   await ctx.route('**/*',async route=>{
    const req=route.request(),url=new URL(req.url());
    if(url.origin!==origin){blocked.push(req.url());return route.abort();}
    const p=url.pathname,json=o=>route.fulfill({contentType:'application/json',body:JSON.stringify(o)});
    if(p==='/page.html')return route.fulfill({contentType:'text/html',body:fs.readFileSync(path.join(fixture,scenario.disabled?'disabled.html':'enabled.html'),'utf8')});
    if(p==='/avatar.html')return route.fulfill({contentType:'text/html',body:'<html></html>'});
    if(p==='/data/chat_context.json')return json({system_prompt:'Synthetic fixture only.',message_shards:['messages-2000.json']});
    if(p==='/data/messages-2000.json'){shardSeen=true;if(scenario.delay)await shardGate;return json([]);}
    if(p==='/data/memories.json'||p==='/data/transcripts.json')return json({entries:[]});
    if(p==='/data/sessions_father.json')return json({viewer:'father',sessions:[],recent_dates:[]});
    if(p==='/health')return route.fulfill({status:503,contentType:'application/json',body:'{}'});
    if(p==='/v1/chat/completions'){
     assert.equal(req.method(),'POST');bodies.push(req.postDataJSON());
     return route.fulfill({contentType:'text/event-stream',body:'data: {"choices":[{"delta":{"content":"Synthetic response."}}]}\n\ndata: [DONE]\n\n'});
    }
    if(req.method()!=='GET')throw Error('Unexpected synthetic POST '+p);
    return route.fulfill({status:404,body:''});
   });
   await page.goto(origin+'/page.html');
   const choice=page.locator('#father-model-choice'),expected='deepseek-v4-pro';
   assert.equal(await choice.inputValue(),expected);
   const options=await choice.locator('option').evaluateAll(xs=>xs.map(x=>({value:x.value,label:x.textContent,disabled:x.disabled})));
   assert.deepEqual(options.filter(x=>x.label.includes('默认')).map(x=>x.value),[expected]);
   assert.equal(options.find(x=>x.value==='gpt-6.1-terra').disabled,!!scenario.disabled);
   if(scenario.manual){await choice.selectOption(scenario.manual);await page.evaluate(()=>window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true})));assert.equal(await choice.inputValue(),scenario.manual);}
   if(scenario.remove)await choice.evaluate(e=>e.remove());
   await page.locator('#input-text').fill('synthetic test');await page.locator('#send-btn').click();
   if(scenario.delay){
    await assertEventually(()=>shardSeen);assert.equal(bodies.length,0);
    await choice.selectOption('deepseek-v4-pro');releaseShard();
   }
   try { await assertEventually(()=>bodies.length===1); } catch(e) { console.error(scenario.name,await page.locator('body').innerText(),errors); throw e; }
   const model=scenario.manual||expected;
   assert.equal(bodies[0].model,model);assert.equal(bodies[0].provider,model==='deepseek-v4-pro'?'deepseek':'openai');
   await page.waitForFunction(()=>!document.querySelector('#send-btn').classList.contains('stop'));
   if(scenario.delay){
    assert.equal(await choice.inputValue(),'deepseek-v4-pro');
    await page.locator('#input-text').fill('synthetic second turn');await page.locator('#send-btn').click();await assertEventually(()=>bodies.length===2);
    assert.equal(bodies[1].model,'deepseek-v4-pro');assert.equal(bodies[1].provider,'deepseek');
   }
   if(scenario.stored)assert.deepEqual(JSON.parse(await page.evaluate(key=>localStorage.getItem(key),key)),scenario.stored);
   if(scenario.manual){
    await page.locator('#settings-btn').click();await page.locator('#save-btn').click();assert.equal(await choice.inputValue(),scenario.manual);
    await page.reload();assert.equal(await choice.inputValue(),expected);
   }
   assert.deepEqual(errors,[]);assert.deepEqual(blocked,[]);
   report.push({scenario:scenario.name,default:expected,requests:bodies.map(x=>({model:x.model,provider:x.provider})),pageErrors:errors,externalRequests:blocked});
   await ctx.close();
  }
  fs.writeFileSync(path.join(fixture,'browser-results.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
async function assertEventually(predicate){for(let i=0;i<160;i++){if(predicate())return;await new Promise(r=>setTimeout(r,50));}assert(predicate(),'condition timed out');}
