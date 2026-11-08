/* Synthetic WAVs/state only. Existing installed Playwright/Edge; no downloads. */
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {batchesFixture,NEW}=require('./mobile_review_batches_fixture');
const {DraftCache}=require('../../tools/mobile_review_ui');
async function run(){
 const memory=new Map(),storage={getItem:k=>memory.get(k)||null,setItem:(k,v)=>memory.set(k,v),key:i=>[...memory.keys()][i],get length(){return memory.size;}};
 const legacy=new DraftCache(storage,'same-package','same-tab'),named=new DraftCache(storage,'same-package','same-tab',NEW);
 legacy.save('ab',{dirty:true,pending:{request_id:'old'},submitIntent:{request_id:'old-submit'}});
 assert.equal(named.own('ab'),null);assert.deepEqual(named.candidates('ab'),[]);
 named.save('ab',{dirty:true,pending:{request_id:'new'},submitIntent:{request_id:'new-submit'}});
 assert.equal(legacy.own('ab').submitIntent.request_id,'old-submit');assert.equal(named.own('ab').pending.request_id,'new');
 console.log('PASS equal package revisions and tab IDs cannot cross batch cache or pending submit intent');
 const f=await batchesFixture();let browser;
 try{
  browser=await require('playwright').chromium.launch({headless:true,channel:'msedge'});
  const context=await browser.newContext({viewport:{width:320,height:740}});
  const p=await context.newPage();p.on('dialog',d=>d.accept());
  const open=async(base=NEW)=>{await p.goto(f.origin+base);await p.getByRole('button',{name:/声音对比/}).click();};
  const saved=async(page=p)=>page.locator('#status-ab').filter({hasText:'已保存到电脑'}).waitFor();
  const submit=async()=>{await p.getByRole('button',{name:'提交本次结果',exact:true}).click();await p.getByRole('button',{name:'确认提交',exact:true}).click();};
  f.fresh.state.batches=[...f.batches,{title:'unsafe remote',base_path:'https://example.invalid/'},{title:'unsafe script',base_path:'javascript:alert(1)'},{title:'unsafe traversal',base_path:'/review/batches/../escape/'}];
  await open();assert.equal(await p.getByRole('link',{name:/unsafe/}).count(),0);assert.equal(await p.getByRole('heading',{name:f.batches[1].title,exact:true}).count(),1);
  assert.equal(await p.locator('a[href="/review/"]').count(),1);
  assert.equal(await p.getByRole('button',{name:/原声核验|语言标注/}).count(),0);
  for(const width of [320,390]){await p.setViewportSize({width,height:844});assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);if(process.env.MOBILE_REVIEW_EVIDENCE)await p.screenshot({path:path.join(process.env.MOBILE_REVIEW_EVIDENCE,`batch-${width}.png`),fullPage:true});}
  await p.locator('.audio button').nth(0).click();await p.waitForFunction(()=>document.querySelectorAll('audio')[0].readyState>=2&&!document.querySelectorAll('audio')[0].paused);
  await p.locator('.audio button').nth(1).click();await p.waitForFunction(()=>!document.querySelectorAll('audio')[1].paused&&document.querySelectorAll('audio')[1].readyState>=2);assert.equal(await p.locator('audio').nth(0).evaluate(a=>a.paused),true);assert.equal(await p.locator('audio').nth(1).evaluate(a=>a.duration),1);
  console.log('PASS new AB-only title, navigation, 320/390 layout, real WAV decoding and mutual exclusion');
  for(let i=0;i<3;i++)await p.getByRole('button',{name:'A 更好',exact:true}).click();await saved();
  assert.equal(f.fresh.state.drafts.ab.values.items.ab0.preference,'A');assert.equal(f.old.state.drafts.ab.values.items.ab0.preference,'unheard');
  await open('/review/');await p.getByRole('button',{name:'B 更好',exact:true}).click();await saved();
  await p.getByRole('button',{name:'‹ 返回任务'}).click();assert.equal(await p.getByRole('button',{name:/原声核验|语言标注/}).count(),2);
  await p.getByRole('link',{name:f.batches[1].title,exact:true}).click();await p.getByRole('button',{name:/声音对比/}).click();assert.equal(await p.getByRole('button',{name:'A 更好',exact:true}).getAttribute('aria-pressed'),'true');
  f.fresh.mode='offline';await p.locator('#note').fill('new-only offline');await p.locator('#status-ab').filter({hasText:'尚未同步：'}).waitFor();
  await open('/review/');assert.equal(await p.locator('#note').inputValue(),'');assert.equal(await p.getByRole('button',{name:/恢复其他页面/}).count(),0);
  f.fresh.mode=null;await open();await saved();assert.equal(await p.locator('#note').inputValue(),'new-only offline');
  console.log('PASS repeated choice, independent old/new ratings, offline drafts and reload');
  await p.route('**/api/tasks/ab/submit',async route=>{await route.fetch();await route.abort();},{times:1});await submit();await p.locator('#recover-submit').waitFor({state:'visible'});const intent=f.fresh.requests.filter(r=>r.path.endsWith('/submit')).at(-1).body;
  await p.reload();await p.getByText('电脑已收到正式提交').waitFor();assert.equal(f.fresh.receipts.size,1);assert.deepEqual(f.fresh.requests.filter(r=>r.path.endsWith('/submit')).at(-1).body,intent);
  assert.equal(f.old.receipts.size,0);const link=p.getByRole('link',{name:'下载 JSON 备用副本'});assert.equal(await link.getAttribute('href'),NEW+'api/receipts/synthetic-receipt-1/export');
  const downloadPromise=p.waitForEvent('download');await link.click();const download=await downloadPromise;const exported=JSON.parse(fs.readFileSync(await download.path(),'utf8'));assert.deepEqual(exported.counts,{judged:1,unheard:11});
  assert.doesNotMatch(JSON.stringify(exported),/answer.?key|checkpoint|condition|model_name/);
  await p.getByRole('button',{name:/声音对比/}).click();await p.getByRole('button',{name:'B 更好',exact:true}).click();await saved();
  await p.getByRole('button',{name:'提交本次结果',exact:true}).click();await p.getByRole('button',{name:'确认提交',exact:true}).evaluate(b=>{b.click();b.click();});await p.getByText('电脑已收到正式提交').waitFor();assert.equal(f.fresh.receipts.size,2);assert.equal(f.fresh.state.latest_receipts.ab.supersedes,'synthetic-receipt-1');
  console.log('PASS lost-ack same intent recovery, partial JSON download, repeated submit and supersedes');
  const tab=await context.newPage();tab.on('dialog',d=>d.accept());await tab.goto(f.origin+NEW);await tab.getByRole('button',{name:/声音对比/}).click();await p.locator('#note').fill('new server note');await saved();await tab.locator('#note').fill('conflicting note');await tab.locator('#status-ab').filter({hasText:'冲突'}).waitFor();await tab.getByRole('button',{name:'查看并处理版本冲突'}).click();await tab.getByRole('button',{name:'采用电脑草稿',exact:true}).click();assert.equal(await tab.locator('#note').inputValue(),'new server note');await tab.close();
  f.sessionFailure=true;await p.reload();assert.equal(await p.getByRole('link',{name:'重新登录',exact:true}).getAttribute('href'),NEW);f.sessionFailure=false;
  delete f.old.state.batch;delete f.old.state.batches;await open('/review/');assert.equal(await p.getByRole('button',{name:'B 更好',exact:true}).getAttribute('aria-pressed'),'true');
  console.log('PASS named-batch conflict, base-correct login, metadata-absent old compatibility');
  await context.close();
 }finally{if(browser)await browser.close();await f.close();}
}
run().catch(error=>{console.error(error);process.exitCode=1;});
