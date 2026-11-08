// Real loopback HTTP + Edge, generated full page. No external requests, real LLM/TTS, or production writes.
const http=require('http'),fs=require('fs'),assert=require('assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_CORE);
const root=process.argv[2];
const delta='data: {"choices":[{"delta":{"content":"synthetic reply"}}]}\n\n';
(async()=>{
 let scenario='hold',requests=[],events=[],tts=0,bodyClosed=0;
 const server=http.createServer((req,res)=>{
  const path=req.url.split('?')[0]; const json=x=>{res.setHeader('Content-Type','application/json');res.end(JSON.stringify(x));};
  if(path==='/proxy.html'||path==='/byok.html'){res.setHeader('Content-Type','text/html');return res.end(fs.readFileSync(root+path,'utf8').replace(/\}\)\(\);\s*<\/script>/, `window.fixture = {state:()=>({ready:contextLoaded, streaming, pending:sendPending, history:history.map(x=>({...x})),input:inputText.value,text:chat.textContent}), byok:url=>{settings.url=url+'/v1/chat/completions';settings.key='synthetic';settings.model='synthetic';}};})();</script>`));}
  if(path==='/avatar.html'){res.setHeader('Content-Type','text/html');return res.end('<html></html>');}
  if(path==='/data/chat_context.json')return json({system_prompt:'Synthetic Tier-3 only',message_shards:[]});
  if(path.includes('sessions_'))return json({sessions:[],recent_dates:[]});
  if(path==='/data/memories.json'||path==='/data/transcripts.json')return json({entries:[]});
  if(path==='/health')return json({status:'unavailable'});
  if(path==='/tts'){tts++;res.statusCode=500;return res.end();}
  if(path==='/session'){let b='';req.on('data',x=>b+=x);req.on('end',()=>{events.push(JSON.parse(b));json({ok:true});});return;}
  if(path==='/v1/chat/completions'){
   let body='';req.on('data',x=>body+=x);req.on('end',()=>{
    requests.push(JSON.parse(body));
    if(scenario==='http-reject'||scenario==='mime-reject'){
     res.statusCode=scenario==='http-reject'?403:200;res.setHeader('Content-Type','text/html');res.on('close',()=>bodyClosed++);res.write('PRIVATE_BODY');return;
    }
    if(scenario==='empty-json'){res.setHeader('Content-Type','application/json');return res.end(JSON.stringify({choices:[{message:{content:'  \n '}}]}));}
    res.setHeader('Content-Type','text/event-stream');
    if(scenario==='empty-sse')return res.end('data: [DONE]\n\n');
    res.write(delta);
    if(scenario==='hold'){res.write('data: [DONE]\n\n');return;}
    if(scenario==='reset-after-done'){res.write('data: [DONE]\n\n');setTimeout(()=>res.destroy(),80);return;}
    if(scenario==='partial')return res.end();
    if(scenario==='reset-partial'){setTimeout(()=>res.destroy(),50);return;}
    if(scenario==='cancel')return;
    if(scenario==='multiline'){res.write('data: {"choices":\r\ndata: [{"delta":{"content":"你好"}}]}\r\n\r\ndata: [DONE]');return res.end();}
   });return;
  }
  res.statusCode=404;res.end();
 });
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const origin='http://127.0.0.1:'+server.address().port;
 const browser=await chromium.launch({executablePath:process.env.EDGE_EXE||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 try{
 for(const mode of ['proxy','byok'])for(const kind of ['hold','reset-after-done','partial','reset-partial','cancel','multiline','empty-sse','empty-json','http-reject','mime-reject']){
  scenario=kind;requests=[];events=[];tts=0;bodyClosed=0;
  const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(String(e)));
  await page.route('**/*',route=>route.request().url().startsWith(origin)?route.continue():route.abort());
  await page.goto(origin+'/'+mode+'.html',{waitUntil:'domcontentloaded'});
  // Synthetic BYOK endpoint; both actual generated streamRequest branches run.
  if(mode==='byok')await page.evaluate(url=>window.fixture.byok(url),origin);
  await page.waitForFunction(()=>window.fixture.state().ready);
  await page.locator('#input-text').fill('synthetic question');await page.locator('#send-btn').click();
  for(let i=0;i<100 && !requests.length;i++) await page.waitForTimeout(20);
  assert.equal(requests.length,1);
  if(kind==='cancel'){await page.waitForTimeout(100);await page.locator('#send-btn').click();}
  await page.waitForFunction(()=>!window.fixture.state().streaming && !window.fixture.state().pending,{},{timeout:2500});
  const state=await page.evaluate(()=>window.fixture.state());
  assert.equal(requests.length,1);assert.equal(requests[0].messages.filter(x=>x.role==='user').length,1);
  if(['hold','reset-after-done','multiline'].includes(kind)){assert.equal(state.history.length,2);assert.equal(state.input,'');}
  else{assert.equal(state.history.length,0);assert.equal(state.input,'synthetic question');assert(state.text.includes('未完成'));if(['partial','reset-partial','cancel'].includes(kind))assert(state.text.includes('synthetic reply'));assert.equal(tts,0);assert(!state.text.includes('PRIVATE_BODY'));
   if(kind.startsWith('empty'))assert(state.text.includes('LLM_EMPTY'));
   if(kind.endsWith('reject')){await page.waitForTimeout(80);assert.equal(bodyClosed,1);}
   scenario='hold';await page.locator('#send-btn').click();await page.waitForFunction(()=>window.fixture.state().history.length===2);
   assert.equal(requests.length,2);assert.equal(requests[1].messages.filter(x=>x.role==='user').length,1);
  }
  assert.deepEqual(errors,[]);console.log(JSON.stringify({mode,kind,pass:true,requests:requests.length,tts}));await page.close();
 }
 }finally{await browser.close();server.closeAllConnections();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
