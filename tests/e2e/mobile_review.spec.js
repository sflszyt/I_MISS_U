/* 纯合成数据，不访问 people/，不产生真人决定。
 * node tests/e2e/mobile_review.spec.js --serve  启动合成 HTTP fixture，供共享浏览器验收。
 * node tests/e2e/mobile_review.spec.js          已有 playwright 时运行下列场景。
 * MOBILE_REVIEW_TEST_PORT 可指定测试端口（默认随机）。
 */
'use strict';
const http=require('node:http');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../..');
const clone=x=>JSON.parse(JSON.stringify(x));
function makeFixture(language=false){
  const tasks=[{id:'ab',title:'声音对比',items:Array.from({length:14},(_,i)=>({id:'ab'+i,number:i+1,text:'合成测试句 '+(i+1),audio_a:'/review/audio/a.wav',audio_b:'/review/audio/b.wav'}))},
    {id:'source',title:'原声核验',items:Array.from({length:12},(_,i)=>({id:'source'+i,number:i+1,text:'测试转写 '+(i+1),audio:'/review/audio/s.wav',source_label:'合成来源 '+(i+1),split:i===11?'validation':'train',actual_duration_ms:1000,expected_duration_ms:1000,duration_requires_confirmation:i===0}))}];
  const state={schema_version:1,package_revision:'synthetic-package-v1',csrf_token:'synthetic-csrf',tasks,
    drafts:{ab:{revision:0,updated_at:null,values:{position:0,items:{}}},source:{revision:0,updated_at:null,values:{position:0,reviewer:'',items:{}}}},latest_receipts:{ab:null,source:null}};
  tasks[0].items.forEach(i=>state.drafts.ab.values.items[i.id]={preference:'unheard',note:'',played_a:false,played_b:false});
  tasks[1].items.forEach(i=>state.drafts.source.values.items[i.id]={text:i.text,speaker:false,single:false,transcript:false,transcript_confirmed_text:null,quality:false,duration:false,include:false,disposition:'pending',note:''});
  if(language){tasks.push({id:'language',title:'语言标注',items:tasks[1].items.map(({id,number,audio,split})=>({id,number,audio,split}))});state.drafts.language={revision:0,updated_at:null,values:{position:0,items:Object.fromEntries(tasks[1].items.map(i=>[i.id,{language:'unlabeled',note:''}]))}};state.latest_receipts.language=null;}
  return state;
}
function wave(){const b=Buffer.alloc(44+16000);b.write('RIFF');b.writeUInt32LE(b.length-8,4);b.write('WAVEfmt ',8);b.writeUInt32LE(16,16);b.writeUInt16LE(1,20);b.writeUInt16LE(1,22);b.writeUInt32LE(8000,24);b.writeUInt32LE(16000,28);b.writeUInt16LE(2,32);b.writeUInt16LE(16,34);b.write('data',36);b.writeUInt32LE(16000,40);return b;}
async function fixtureServer(){
  const fixture={state:makeFixture(),requests:[],receipts:new Map(),seen:new Map(),mode:null,delay:0};
  const server=http.createServer(async(req,res)=>{
    const json=(status,value)=>{res.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify(value));};
    const fail=(status,message)=>json(status,{error:{code:'test',message}});
    const assets={'/review/':['mobile_review_ui.html','text/html; charset=utf-8'],'/review/app.js':['mobile_review_ui.js','text/javascript; charset=utf-8'],'/review/app.css':['mobile_review_ui.css','text/css; charset=utf-8']};
    if(assets[req.url]){const [name,type]=assets[req.url];res.writeHead(200,{'Content-Type':type,'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; media-src 'self'; object-src 'none'; base-uri 'none'"});res.end(fs.readFileSync(path.join(root,'tools',name)));return;}
    if(req.url.startsWith('/review/audio/')){res.writeHead(200,{'Content-Type':'audio/wav'});res.end(wave());return;}
    if(req.url==='/review/api/session'){json(200,fixture.state);return;}
    if(req.url.startsWith('/review/api/receipts/')){const id=req.url.split('/')[4];const receipt=fixture.receipts.get(id);if(!receipt){fail(404,'未找到');return;}json(200,receipt);return;}
    const match=req.url.match(/^\/review\/api\/tasks\/(ab|source|language)\/(draft|submit)$/);if(!match){fail(404,'未找到');return;}
    let body='';for await(const chunk of req)body+=chunk;const data=JSON.parse(body);fixture.requests.push({path:req.url,body:clone(data)});
    if(fixture.mode==='401'){fail(401,'请重新登录');return;}
    if(fixture.mode==='html'){res.writeHead(200,{'Content-Type':'text/html'});res.end('<h1>Login</h1>');return;}
    if(fixture.mode==='offline'){req.socket.destroy();return;}
    if(data.package_revision!==fixture.state.package_revision){fail(409,'批次变化');return;}
    const replay=fixture.seen.get(data.request_id);if(replay){if(replay.body!==body){fail(409,'请求不一致');return;}json(200,replay.result);return;}
    const [,id,action]=match;const draft=fixture.state.drafts[id];let result;
    if(action==='draft'){
      if(data.base_revision!==draft.revision){fail(409,'草稿版本冲突');return;}
      if(id==='source'&&Object.values(data.values.items).some(v=>v.transcript&&!v.text.trim())){fail(422,'空文本不能确认');return;}
      Object.assign(draft,{revision:draft.revision+1,updated_at:new Date().toISOString(),values:data.values});result=clone(draft);
    }else{
      if(data.draft_revision!==draft.revision || data.supersedes!==(fixture.state.latest_receipts[id]?.receipt_id||null)){fail(409,'提交版本冲突');return;}
      const values=Object.values(draft.values.items);const counts=id==='ab'?{judged:values.filter(v=>v.preference!=='unheard').length,unheard:values.filter(v=>v.preference==='unheard').length}:{train:values.filter((v,i)=>i!==11&&v.include&&v.disposition==='review').length,validation:values.filter((v,i)=>i===11&&v.include&&v.disposition==='review').length,pending:values.filter(v=>v.disposition==='pending').length,excluded:values.filter(v=>v.disposition==='exclude').length};
      result={receipt_id:'synthetic-receipt-'+(fixture.receipts.size+1),task_id:id,submitted_at:new Date().toISOString(),counts,payload_sha256:'synthetic-hash',supersedes:data.supersedes};fixture.receipts.set(result.receipt_id,result);fixture.state.latest_receipts[id]=result;
      if(id==='language'){result.counts={wu:0,mandarin:0,mixed:0,unknown:0,pending:0,labeled:0};for(const v of values){if(v.language==='unlabeled')result.counts.pending++;else{result.counts[v.language]++;result.counts.labeled++;}}}
    }
    fixture.seen.set(data.request_id,{body,result});
    if((fixture.mode==='drop-submit'&&action==='submit')||(fixture.mode==='drop-draft'&&action==='draft')){fixture.mode=action==='draft'?'offline':null;req.socket.destroy();return;}
    if(fixture.delay)await new Promise(r=>setTimeout(r,fixture.delay));json(200,result);
  });
  await new Promise(resolve=>server.listen(Number(process.env.MOBILE_REVIEW_TEST_PORT)||0,'127.0.0.1',resolve));
  fixture.url=`http://127.0.0.1:${server.address().port}/review/`;fixture.close=()=>new Promise(resolve=>server.close(resolve));return fixture;
}
async function run(){
 const fixture=await fixtureServer();
 if(process.argv.includes('--serve')){console.log(JSON.stringify({synthetic_only:true,url:fixture.url}));return;}
 let browser;
 try{
  const {chromium}=require('playwright');browser=await chromium.launch({headless:true,...(process.env.MOBILE_REVIEW_BROWSER_CHANNEL?{channel:process.env.MOBILE_REVIEW_BROWSER_CHANNEL}:{})});const context=await browser.newContext({viewport:{width:390,height:844}});const page=await context.newPage();page.on('dialog',d=>d.accept());
  const waitSaved=async p=>p.locator('#status-ab').filter({hasText:'已保存到电脑'}).waitFor();
  await page.goto(fixture.url);await page.getByRole('button',{name:/声音对比/}).click();
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=390),true);
  await page.getByRole('button',{name:'A 更好',exact:true}).click();await waitSaved(page);
  assert.equal(fixture.state.drafts.ab.values.items.ab0.preference,'A');console.log('PASS mobile choice/save');
  fixture.delay=700;await page.locator('#note').fill('first');await page.waitForTimeout(700);await page.locator('#note').fill('newer');await waitSaved(page);fixture.delay=0;
  assert.equal(fixture.state.drafts.ab.values.items.ab0.note,'newer');console.log('PASS delayed ack preserves edit');
  fixture.mode='offline';await page.locator('#note').fill('offline draft');await page.locator('#status-ab').filter({hasText:'尚未同步'}).waitFor();await page.waitForTimeout(800);await page.reload();await page.getByRole('button',{name:/声音对比/}).click();assert.equal(await page.locator('#note').inputValue(),'offline draft');fixture.mode=null;await page.getByRole('button',{name:'重新连接并同步'}).click();await waitSaved(page);console.log('PASS offline/reload/retry');
  fixture.mode='401';await page.locator('#note').fill('login interrupted');await page.locator('#status-ab').filter({hasText:'重新登录'}).waitFor();fixture.mode=null;await page.getByRole('button',{name:'重新连接并同步'}).click();await waitSaved(page);console.log('PASS login expiry preserves draft');
  fixture.mode='html';await page.locator('#note').fill('html login');await page.locator('#status-ab').filter({hasText:'登录可能已过期'}).waitFor();fixture.mode=null;await page.getByRole('button',{name:'重新连接并同步'}).click();await waitSaved(page);console.log('PASS HTML login is not save success');
  const tab=await context.newPage();tab.on('dialog',d=>d.accept());await tab.goto(fixture.url);await tab.getByRole('button',{name:/声音对比/}).click();
  await page.locator('#note').fill('tab one');await waitSaved(page);await tab.locator('#note').fill('tab two');await tab.locator('#status-ab').filter({hasText:'冲突'}).waitFor();await tab.getByRole('button',{name:'查看并处理版本冲突'}).click();await tab.getByRole('button',{name:'采用电脑草稿',exact:true}).click();assert.equal(await tab.locator('#note').inputValue(),'tab one');await tab.close();console.log('PASS two tab explicit conflict');
  fixture.mode='drop-submit';await page.getByRole('button',{name:'提交本次结果',exact:true}).click();await page.getByRole('button',{name:'确认提交',exact:true}).click();await page.locator('#recover-submit').waitFor({state:'visible'});await page.waitForTimeout(200);const frozen=fixture.requests.filter(r=>r.path.endsWith('/submit')).at(-1).body;
  await page.reload();await page.getByText('电脑已收到正式提交').waitFor();assert.equal(fixture.receipts.size,1);assert.deepEqual(fixture.requests.filter(r=>r.path.endsWith('/submit')).at(-1).body,frozen);console.log('PASS lost submit ack reload same id exactly once');
  await page.getByRole('button',{name:/原声核验/}).click();await page.locator('#check-transcript').check();await page.locator('#transcript-text').fill('改后的合成转写');assert.equal(await page.locator('#check-transcript').isChecked(),false);await page.waitForTimeout(800);assert.equal(fixture.state.drafts.source.values.items.source0.transcript_confirmed_text,null);console.log('PASS text change resets confirmation');
  fixture.state.package_revision='synthetic-package-v2';fixture.state.drafts.source.values.items.source0.text='新批次文字';fixture.state.drafts.source.revision=0;await page.reload();await page.getByRole('button',{name:/原声核验/}).click();assert.equal(await page.locator('#transcript-text').inputValue(),'新批次文字');console.log('PASS package cache isolation');
  await context.close();
  fixture.state=makeFixture();fixture.seen.clear();fixture.receipts.clear();
  const recoveryContext=await browser.newContext({viewport:{width:390,height:844}});
  const open=async()=>{const p=await recoveryContext.newPage();p.on('dialog',d=>d.accept());await p.goto(fixture.url);await p.getByRole('button',{name:/声音对比/}).click();return p;};
  const a=await open();fixture.mode='drop-draft';await a.locator('#note').fill('A old request');await a.locator('#status-ab').filter({hasText:'尚未同步：'}).waitFor();await a.close();fixture.mode=null;
  const b=await open();await b.getByRole('button',{name:/恢复其他页面/}).click();await b.getByRole('button',{name:'恢复草稿 1',exact:true}).click();await b.getByRole('dialog').waitFor({state:'hidden'});await waitSaved(b);await b.locator('#note').fill('B newest saved');await waitSaved(b);assert.equal(fixture.state.drafts.ab.values.items.ab0.note,'B newest saved');await b.close();
  const c=await open();assert.equal(await c.locator('#note').inputValue(),'B newest saved');assert.equal(await c.getByRole('button',{name:/恢复其他页面/}).count(),0);console.log('PASS A/B/C closed tab recovery retires old snapshot');
  await c.getByRole('button',{name:'‹ 返回任务'}).click();await c.getByRole('button',{name:/原声核验/}).click();await c.locator('#transcript-text').fill('');await c.locator('#check-transcript').check();await c.locator('#status-source').filter({hasText:'空文本不能确认'}).waitFor();
  const invalid=fixture.requests.at(-1).body.request_id;await c.locator('#transcript-text').fill('修正后的合成文字');await c.locator('#status-source').filter({hasText:'已保存到电脑'}).waitFor();assert.notEqual(fixture.requests.at(-1).body.request_id,invalid);assert.equal(fixture.state.drafts.source.values.items.source0.text,'修正后的合成文字');console.log('PASS 422 invalid draft corrected with new request');
  const d=await open(),e=await open();fixture.mode='offline';await d.locator('#note').fill('first independent offline draft');await d.locator('#status-ab').filter({hasText:'尚未同步：'}).waitFor();await e.locator('#note').fill('second independent offline draft');await e.locator('#status-ab').filter({hasText:'尚未同步：'}).waitFor();await d.close();await e.close();fixture.mode=null;
  await c.reload();await c.getByRole('button',{name:/声音对比/}).click();assert.equal(await c.locator('#note').inputValue(),'B newest saved');await c.getByRole('button',{name:'恢复其他页面的未同步草稿（2 份）'}).click();assert.equal(await c.getByRole('button',{name:/^恢复草稿 /}).count(),2);await c.getByRole('button',{name:'暂不恢复',exact:true}).click();console.log('PASS multiple unsynced drafts require explicit selection');
  await recoveryContext.close();
  fixture.state=makeFixture();fixture.seen.clear();const conflictContext=await browser.newContext({viewport:{width:390,height:844}});
  const conflictPage=await conflictContext.newPage();conflictPage.on('dialog',dialog=>dialog.accept());await conflictPage.goto(fixture.url);await conflictPage.getByRole('button',{name:/声音对比/}).click();
  fixture.mode='drop-draft';await conflictPage.locator('#note').fill('old pending value');await conflictPage.locator('#status-ab').filter({hasText:'尚未同步：'}).waitFor();fixture.mode=null;
  fixture.state.drafts.ab.revision=2;fixture.state.drafts.ab.values.items.ab0.note='new server value';
  await conflictPage.reload();await conflictPage.getByRole('button',{name:/声音对比/}).click();await conflictPage.locator('#status-ab').filter({hasText:'冲突'}).waitFor();const beforeReload=fixture.requests.length;
  await conflictPage.reload();await conflictPage.getByRole('button',{name:/声音对比/}).click();await conflictPage.locator('#status-ab').filter({hasText:'冲突'}).waitFor();await conflictPage.waitForTimeout(900);
  assert.equal(fixture.requests.length,beforeReload);assert.equal(fixture.state.drafts.ab.values.items.ab0.note,'new server value');assert.equal(await conflictPage.locator('#note').inputValue(),'old pending value');
  await conflictPage.getByRole('button',{name:'查看并处理版本冲突'}).click();await conflictPage.getByRole('button',{name:'采用电脑草稿',exact:true}).click();await conflictPage.getByRole('dialog').waitFor({state:'hidden'});await conflictPage.reload();await conflictPage.getByRole('button',{name:/声音对比/}).click();await waitSaved(conflictPage);assert.equal(await conflictPage.locator('#note').inputValue(),'new server value');
  console.log('PASS old ack conflict survives reload without silent save, explicit resolution clears gate');await conflictContext.close();console.log('PASS all 13 synthetic browser scenarios');
 }finally{if(browser)await browser.close();await fixture.close();}
}
module.exports={fixtureServer,makeFixture};
if(require.main===module)run().catch(e=>{console.error(e);process.exitCode=1;});
