// Synthetic-only browser contract. Every request is intercepted; no server/model is contacted.
const {chromium} = require(process.env.PLAYWRIGHT_CORE);
const fs = require('fs');
const assert = require('assert/strict');
const html = fs.readFileSync(process.argv[2], 'utf8');
const scope = {person:'mama', relationship_id:'mama_father'};
const context = {...scope, viewer:'father', coverage_status:'partial', language:'mandarin',
  system_prompt:'Synthetic only Tier-3', message_shards:['messages-2000.json','messages-2001.json']};
const row = {...scope, viewpoint:'father', conversation_kind:'direct', content_type:'text', tier:2,
  record_id:'fixture', provenance:{source_record_id:'fixture'}, sender_person_id:'mama',
  sender:'subject', participant_ids:['mama','father'], text:'synthetic archive', date:'2000-01-01'};
(async()=>{
 const browser = await chromium.launch({executablePath:process.env.EDGE_EXE || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless:true});
 const results=[];
 async function scenario(name, options, action) {
  const page=await browser.newPage(); page.setDefaultTimeout(4000); page.setDefaultNavigationTimeout(30000); const state={llm:[],sessions:[],counts:{}, errors:[], release:null};
  page.on('pageerror',e=>state.errors.push(String(e)));
  await page.route('**/*', async route=>{
   const request=route.request(), path=new URL(request.url()).pathname;
   state.counts[path]=(state.counts[path]||0)+1;
   const json=body=>route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
   if(path==='/companion.html') return route.fulfill({contentType:'text/html',body:options.byok ? fs.readFileSync(process.argv[2]+'.byok','utf8') : options.owner ? fs.readFileSync(process.argv[2]+'.owner','utf8') : html});
   if(path==='/avatar.html') return route.fulfill({contentType:'text/html',body:'<html></html>'});
   if(path==='/other') return route.fulfill({contentType:'text/html',body:'<html>Synthetic navigation target</html>'});
   if(path==='/session'){state.sessions.push(JSON.parse(request.postData()));return json({ok:true});}
   if(path==='/health') return json({status:'unavailable'});
   if(path==='/v1/chat/completions') {state.llm.push(JSON.parse(request.postData()));if(options.holdResponse)await new Promise(resolve=>state.release=resolve);return route.fulfill({contentType:'text/event-stream',body:'data: {"choices":[{"delta":{"content":"Synthetic reply"}}]}\n\ndata: [DONE]\n\n'});}
   if(path===options.fail && state.counts[path]===1) return options.offline ? route.abort('internetdisconnected') : route.fulfill({status:503,body:'unavailable'});
   if(path===options.delay) await new Promise(resolve=>state.release=resolve);
   let body;
   if(path==='/data/chat_context.json') body=structuredClone(context);
   if(path.startsWith('/data/messages-')) body=[structuredClone(row)];
   if(['/data/memories.json','/data/transcripts.json'].includes(path)) body={...scope,entries:[]};
   if(path==='/data/sessions_father.json') body={person:'mama',viewer:'father',sessions:[{session_id:'fixture-old',date:'2020-01-01',turns:[{role:'user',text:'SYNTHETIC HISTORY',turn:1},{role:'simulacrum',text:'SYNTHETIC HISTORY REPLY',turn:1}]}],recent_dates:[]};
   if(body && options.corrupt) options.corrupt(path,body);
   return body ? json(body) : route.fulfill({status:404,body:''});
  });
  try {await page.goto('http://synthetic.test/companion.html',{waitUntil:'domcontentloaded',timeout:30000});await action(page,state);assert.deepEqual(state.errors,[]);results.push({name,pass:true,counts:state.counts,llm:state.llm.length});}
  catch(e){results.push({name,pass:false,error:String(e),counts:state.counts,llm:state.llm.length});}
  finally {if(state.release)state.release();await page.close();console.log(JSON.stringify(results[results.length-1]));}
 }
 const send=async(page,text='synthetic')=>{await page.locator('#input-text').fill(text);await page.locator('#send-btn').click({timeout:1500});};
 const settled=page=>page.waitForTimeout(350);
 for(const fail of ['/data/messages-2001.json','/data/memories.json','/data/transcripts.json','/data/chat_context.json']) {
  await scenario('retry '+fail,{fail},async(p,s)=>{
   await settled(p);await send(p);await settled(p);
   // Context has already failed on startup, so this first send is its retry.
   if(fail.endsWith('chat_context.json')) {assert.equal(s.llm.length,1);return;}
   assert.equal(s.llm.length,0);const preserved=await p.locator('#input-text').inputValue();
   const logged=s.sessions.filter(x=>x.role==='user').length;
   await send(p);await settled(p);assert.equal(s.llm.length,1);assert.equal(s.counts[fail],2);
   assert.equal(preserved,'synthetic');assert.equal(logged,0);assert((await p.locator('#chat').innerText()).includes('SYNTHETIC HISTORY'));
  });
 }
 await scenario('offline retry',{fail:'/data/messages-2001.json',offline:true},async(p,s)=>{await settled(p);await send(p);await settled(p);assert.equal(s.llm.length,0);await p.locator('#send-btn').click();await settled(p);assert.equal(s.llm.length,1);});
 await scenario('inflight and duplicate send',{delay:'/data/memories.json'},async(p,s)=>{
  await settled(p);await p.evaluate(()=>{void window.loadKnowledge();});
  await send(p);await p.locator('#send-btn').click();await settled(p);assert.equal(s.llm.length,0);assert.equal(s.counts['/data/memories.json'],1);
  s.release();await settled(p);assert.equal(s.llm.length,1);
 });
 await scenario('profile change cancels pending send',{delay:'/data/messages-2001.json',byok:true},async(p,s)=>{
  await settled(p);await send(p);await settled(p);
  await p.locator('#settings-btn').click();await p.locator('#cfg-provider').selectOption('openai');
  await p.locator('#cfg-key').fill('synthetic-key');await p.locator('#save-btn').click();
  s.release();await settled(p);assert.equal(s.llm.length,0);assert.equal(await p.locator('#input-text').inputValue(),'synthetic');
  await p.locator('#send-btn').click();await settled(p);assert.equal(s.llm.length,1);
 });
 await scenario('incomplete settings cancel active response',{byok:true,holdResponse:true},async(p,s)=>{
  await settled(p);await send(p);await settled(p);assert.equal(s.llm.length,1);
  await p.locator('#settings-btn').click();await p.locator('#cfg-key').fill('');await p.locator('#save-btn').click();
  s.release();await settled(p);
  assert.equal(await p.locator('#send-btn').isDisabled(),true);
  assert.equal(s.sessions.filter(x=>x.role==='simulacrum').length,0);
  assert(!(await p.locator('#chat').innerText()).includes('Synthetic reply'));
  assert.equal(s.counts['/tts']||0,0);
  await p.locator('#settings-btn').click();await p.locator('#cfg-key').fill('synthetic-replacement');await p.locator('#cfg-model').fill('synthetic-model');await p.locator('#save-btn').click();
  await send(p,'next message');await settled(p);assert.equal(s.llm.length,2);
  assert(!s.llm[1].messages.some(x=>x.role==='assistant'&&x.content==='Synthetic reply'));
  s.release();await settled(p);
  const response=s.sessions.find(x=>x.role==='simulacrum');assert(response);assert.equal(response.model,'synthetic-model');
 });
 await scenario('restored draft cancels pending send',{delay:'/data/messages-2001.json'},async(p,s)=>{
  await settled(p);await send(p);await settled(p);await p.locator('#input-text').fill('new draft');await p.locator('#input-text').fill('synthetic');s.release();await settled(p);
  assert.equal(s.llm.length,0);assert.equal(await p.locator('#input-text').inputValue(),'synthetic');
 });
 await scenario('next draft preserves active reply',{byok:true,holdResponse:true},async(p,s)=>{
  await settled(p);await send(p);await settled(p);assert.equal(s.llm.length,1);
  await p.locator('#input-text').fill('next draft');s.release();await settled(p);
  assert.equal(await p.locator('#input-text').inputValue(),'next draft');
  assert((await p.locator('#chat').innerText()).includes('Synthetic reply'));
  const response=s.sessions.find(x=>x.role==='simulacrum');assert(response);assert.equal(response.provider,'openai');assert.equal(response.model,'gpt-5.6');
 });
 await scenario('missing both provenance identifiers blocked',{corrupt:(path,b)=>{if(path==='/data/messages-2001.json'){delete b[0].record_id;b[0].provenance={};}}},async(p,s)=>{
  await settled(p);await send(p);await settled(p);assert.equal(s.llm.length,0);
 });
 await scenario('unscoped owner optional knowledge failure',{owner:true,fail:'/data/memories.json'},async(p,s)=>{
  await settled(p);await send(p);await settled(p);assert.equal(s.llm.length,1);
 });
 await scenario('edited draft cancels pending send',{delay:'/data/messages-2001.json'},async(p,s)=>{
  await settled(p);await send(p);await settled(p);await p.locator('#input-text').fill('new draft');s.release();await settled(p);
  assert.equal(s.llm.length,0);assert.equal(await p.locator('#input-text').inputValue(),'new draft');
 });
 await scenario('late sessions do not cancel valid send',{delay:'/data/sessions_father.json'},async(p,s)=>{
  await settled(p);await send(p);await settled(p);assert.equal(s.llm.length,0);s.release();await settled(p);assert.equal(s.llm.length,1);
  assert((await p.locator('#chat').innerText()).includes('SYNTHETIC HISTORY'));
 });
 await scenario('reload and back validate fresh scope',{},async(p,s)=>{
  await settled(p);await send(p);await settled(p);assert.equal(s.llm.length,1);
  await p.reload({waitUntil:'domcontentloaded'});await settled(p);await send(p);await settled(p);assert.equal(s.llm.length,2);
  await p.goto('http://synthetic.test/other',{waitUntil:'domcontentloaded'});await p.goBack({waitUntil:'domcontentloaded'});await settled(p);await send(p);await settled(p);assert.equal(s.llm.length,3);
  assert(s.llm.every(x=>!JSON.stringify(x).includes('FORBIDDEN')));
 });
 for(const target of ['context','knowledge']) {
  await scenario('wrong '+target+' remains blocked',{corrupt:(path,b)=>{if(path===(target==='context'?'/data/chat_context.json':'/data/memories.json'))b.person='FORBIDDEN';}},async(p,s)=>{
   await settled(p);await send(p);await settled(p);await p.locator('#send-btn').click();await settled(p);assert.equal(s.llm.length,0);
  });
 }
 for(const field of ['person','viewpoint','relationship_id','provenance','malformed']) {
  await scenario('reject '+field,{corrupt:(path,b)=>{if(path==='/data/messages-2001.json'){if(field==='malformed')b.push(null);else b[0][field]=field==='provenance'?{}:'wrong';}}},async(p,s)=>{
   await settled(p);await send(p);await settled(p);await p.locator('#send-btn').click();await settled(p);assert.equal(s.llm.length,0);
  });
 }
 await browser.close();console.log(JSON.stringify(results,null,2));if(results.some(x=>!x.pass))process.exitCode=1;
})().catch(e=>{console.error(e);process.exitCode=1;});
