// Run the actual generated opted-in father page. All requests intercepted; synthetic data only.
const fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_CORE || require('node:path').join(require('node:os').homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright-core'));
const root=path.resolve(process.argv[2]),output=path.resolve(process.argv[3]);
const html=fs.readFileSync(path.join(root,'companion.html'),'utf8');
assert(html.includes('var archiveOptions =')&&html.includes('function sendMessage(event, retryBubble, retryText)'));
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 const report={cases:[],externalRequests:0};
 try{for(const newerDraft of [false,true]){
  const context=await browser.newContext(),page=await context.newPage();let requestId,release,posts=0,tts=0,errors=[];
  page.on('pageerror',e=>errors.push(String(e)));page.setDefaultTimeout(10000);
  await context.route('**/*',async route=>{
   const req=route.request(),url=new URL(req.url()),p=url.pathname;
   const json=x=>route.fulfill({contentType:'application/json',body:JSON.stringify(x)});
   if(url.origin!=='https://synthetic.invalid'){report.externalRequests++;return route.abort();}
   if(p==='/companion.html')return route.fulfill({contentType:'text/html',body:html});
   if(p==='/avatar.html')return route.fulfill({contentType:'text/html',body:'<html></html>'});
   if(p==='/cdn-cgi/access/get-identity')return json({account_id:'a'.repeat(32),user_uuid:'11111111-1111-4111-8111-111111111111'});
   if(p==='/health')return json({status:'ok',model_loaded:true});
   if(p==='/data/sessions_father.json')return json({viewer:'father',sessions:[]});
   if(p.startsWith('/data/')){const f=path.join(root,p);return fs.existsSync(f)?route.fulfill({contentType:'application/json',body:fs.readFileSync(f)}):route.fulfill({status:404,body:'{}'});}
   if(p==='/v1/chat/completions'){
    posts++;requestId=req.headers()['x-request-id'];assert.match(requestId,/^[a-f0-9]{32}$/);
    const body=req.postDataJSON();assert.equal(body.model,'gpt-6.1-terra');assert.equal(body.provider,'openai');
    await new Promise(r=>{release=r;});
    return route.fulfill({status:403,contentType:'application/json',headers:{'X-LLM-Error':'upstream_forbidden','X-Request-ID':requestId,'CF-Ray':'0123456789abcdef-EWR'},body:'{"error":"PRIVATE_ERROR_CANARY"}'});
   }
   if(p==='/tts')tts++;
   return json({ok:true});
  });
  try{
   await page.goto('https://synthetic.invalid/companion.html');await page.locator('#intro-ok').click();
   await page.waitForFunction(()=>document.querySelector('#intro-enter')&&!document.querySelector('#intro-enter').disabled);
   await page.locator('#intro-enter').click();await page.locator('#input-text').fill('Synthetic original question');await page.locator('#send-btn').click();
   await page.waitForFunction(()=>document.querySelector('#send-btn').classList.contains('stop'));
   for(let i=0;!release&&i<100;i++)await page.waitForTimeout(10);assert(release,'synthetic request arrived');
   if(newerDraft)await page.locator('#input-text').fill('Synthetic newer draft');release();
   await page.locator('.send-failure').waitFor();const text=await page.locator('.send-failure').textContent();
   assert(text.includes('模型服务拒绝了这次请求（403），具体原因尚未确认，请联系维护者核查。'));
   assert(text.includes('LLM_UPSTREAM_FORBIDDEN'));assert(text.includes('request_id='+requestId));assert(text.includes('proxy_id='+requestId));
   assert(text.includes('cf_ray=0123456789abcdef-EWR'));assert(!text.includes('PRIVATE_ERROR_CANARY'));
   assert.equal(await page.locator('#input-text').inputValue(),newerDraft?'Synthetic newer draft':'Synthetic original question');
   assert.equal(await page.locator('.send-failed button').textContent(),'重试');
   await page.waitForTimeout(100);assert.equal(posts,1);assert.equal(tts,0);assert.deepEqual(errors,[]);
   report.cases.push({newerDraft,pass:true,posts,tts,safeIds:true,inputRecovery:true});
  }finally{if(release)release();await context.close();}
 }assert.equal(report.externalRequests,0);report.pass=true;
 }catch(e){report.error=e.stack;process.exitCode=1;}finally{fs.writeFileSync(output,JSON.stringify(report,null,2));console.log(JSON.stringify(report));await browser.close();}
})();
