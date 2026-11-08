/* Pure synthetic fixtures; existing Playwright and Edge only. */
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {fixtureServer,makeFixture}=require('./mobile_review.spec.js');
async function run(){
 const fixture=await fixtureServer();fixture.state=makeFixture(true);
 const oldDrafts=JSON.stringify({ab:fixture.state.drafts.ab,source:fixture.state.drafts.source});
 const {chromium}=require('playwright');let browser;
 try{
  browser=await chromium.launch({headless:true,channel:process.env.MOBILE_REVIEW_BROWSER_CHANNEL||'msedge'});
  const context=await browser.newContext({viewport:{width:320,height:740}});
  const open=async()=>{const p=await context.newPage();p.on('dialog',d=>d.accept());await p.goto(fixture.url+'#language');await p.getByRole('heading',{name:/录音 1 /}).waitFor();return p;};
  const saved=async p=>p.locator('#status-language').filter({hasText:'已保存到电脑'}).waitFor();
  const choose=async(p,label)=>{await p.getByRole('button',{name:label,exact:true}).click();await saved(p);};
  const submit=async p=>{await p.getByRole('button',{name:'提交本次结果',exact:true}).click();await p.getByRole('button',{name:'确认提交',exact:true}).click();await p.getByText('电脑已收到正式提交').waitFor();};
  let p=await open();assert.equal(await p.locator('#reviewer,#transcript-text').count(),0);
  assert.equal(await p.locator('[aria-pressed=true]').count(),0);
  await p.getByRole('button',{name:'提交本次结果',exact:true}).click();assert.equal(fixture.receipts.size,0);
  assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth<=320),true);
  for(const [label,value]of [['上海话','wu'],['普通话','mandarin'],['两种都有','mixed'],['不确定','unknown']]){await choose(p,label);assert.equal(fixture.state.drafts.language.values.items.source0.language,value);assert.equal(await p.getByRole('button',{name:label,exact:true}).getAttribute('aria-pressed'),'true');}
  await choose(p,'清除本条标注');assert.equal(fixture.state.drafts.language.values.items.source0.language,'unlabeled');
  await choose(p,'不确定');await p.locator('#note').fill('合成语言备注');await saved(p);await p.reload();await saved(p);assert.equal(await p.locator('#note').inputValue(),'合成语言备注');
  await p.close();p=await open();assert.equal(await p.getByRole('button',{name:'不确定',exact:true}).getAttribute('aria-pressed'),'true');console.log('PASS four labels / clear / initial unlabeled / refresh / closed reopen');
  await p.getByRole('button',{name:'▶ 播放原声',exact:true}).click();assert.equal(await p.locator('audio').evaluate(a=>a.paused),false);
  await p.getByRole('button',{name:'下一项 ›',exact:true}).click();await p.getByRole('heading',{name:/录音 2 /}).waitFor();assert.equal(await p.locator('audio').evaluate(a=>a.paused),true);
  await p.getByRole('button',{name:'‹ 上一项',exact:true}).click();await saved(p);
  await submit(p);assert.deepEqual(fixture.state.latest_receipts.language.counts,{wu:0,mandarin:0,mixed:0,unknown:1,pending:11,labeled:1});
  const downloadPromise=p.waitForEvent('download');await p.getByRole('link',{name:'下载 JSON 备用副本'}).click();const download=await downloadPromise;const receipt=JSON.parse(fs.readFileSync(await download.path(),'utf8'));assert.equal(receipt.task_id,'language');
  await p.getByRole('button',{name:'下一项 ›',exact:true}).click();await choose(p,'两种都有');await submit(p);assert.equal(fixture.receipts.size,2);assert.equal(fixture.state.latest_receipts.language.supersedes,'synthetic-receipt-1');assert.equal(fixture.state.latest_receipts.language.counts.labeled,2);console.log('PASS synthetic audio / numbering / partial unknown submit / download / supersedes');
  fixture.mode='offline';await p.locator('#note').fill('离线合成备注');await p.locator('#status-language').filter({hasText:'尚未同步：'}).waitFor();await p.reload();assert.equal(await p.locator('#note').inputValue(),'离线合成备注');fixture.mode=null;await p.getByRole('button',{name:'重新连接并同步'}).click();await saved(p);
  const tab=await context.newPage();tab.on('dialog',d=>d.accept());await tab.goto(fixture.url+'#language');await tab.locator('#note').waitFor();await p.locator('#note').fill('first tab');await saved(p);await tab.locator('#note').fill('second tab');await tab.locator('#status-language').filter({hasText:'冲突'}).waitFor();await tab.reload();await tab.locator('#status-language').filter({hasText:'冲突'}).waitFor();await tab.getByRole('button',{name:'查看并处理版本冲突'}).click();await tab.getByRole('button',{name:'采用电脑草稿',exact:true}).click();assert.equal(await tab.locator('#note').inputValue(),'first tab');await tab.close();
  fixture.mode='drop-submit';await p.getByRole('button',{name:'提交本次结果',exact:true}).click();await p.getByRole('button',{name:'确认提交',exact:true}).click();await p.locator('#recover-submit').waitFor({state:'visible'});await p.waitForTimeout(100);const frozen=fixture.requests.filter(r=>r.path.endsWith('/submit')).at(-1).body;
  await p.reload();await p.locator('#recover-submit').waitFor({state:'hidden'});assert.equal(fixture.receipts.size,3);assert.deepEqual(fixture.requests.filter(r=>r.path.endsWith('/submit')).at(-1).body,frozen);console.log('PASS language offline / conflict survives reload / lost submit ack exactly once');
  assert.equal(JSON.stringify({ab:fixture.state.drafts.ab,source:fixture.state.drafts.source}),oldDrafts);assert.equal(fixture.state.drafts.source.values.items.source6.disposition,'pending');assert.equal(await p.locator('body').innerText().then(x=>x.includes('undefined')),false);
  if(process.env.MOBILE_REVIEW_EVIDENCE){fs.mkdirSync(process.env.MOBILE_REVIEW_EVIDENCE,{recursive:true});await p.screenshot({path:path.join(process.env.MOBILE_REVIEW_EVIDENCE,'language-synthetic-320.png'),fullPage:true});}
  await p.getByRole('button',{name:'‹ 返回任务',exact:true}).click();assert.equal(await p.locator('button.task').count(),3);await p.getByRole('button',{name:/声音对比/}).click();await p.getByRole('button',{name:'▶ 播放 A',exact:true}).click();await p.getByRole('button',{name:'▶ 播放 B',exact:true}).click();await p.waitForFunction(()=>{const a=document.querySelectorAll('audio');return a[0].paused&&!a[1].paused;});assert.deepEqual(await p.locator('audio').evaluateAll(a=>a.map(x=>x.paused)),[true,false]);console.log('PASS old drafts unchanged / source 7 pending / three tasks / narrow screen / audio mutual exclusion');
  await context.close();
  fixture.state=makeFixture();fixture.seen.clear();fixture.receipts.clear();const reconnectContext=await browser.newContext({viewport:{width:390,height:844}});const reconnect=await reconnectContext.newPage();
  await reconnect.goto(fixture.url);assert.equal(await reconnect.locator('button.task').count(),2);
  const upgraded=makeFixture(true);fixture.state.tasks=upgraded.tasks;fixture.state.drafts.language=upgraded.drafts.language;fixture.state.latest_receipts.language=null;
  await reconnect.evaluate(()=>window.dispatchEvent(new Event('online')));await reconnect.getByRole('button',{name:/语言标注/}).waitFor();assert.equal(await reconnect.locator('button.task').count(),3);
  await reconnect.getByRole('button',{name:/语言标注/}).click();await choose(reconnect,'上海话');assert.equal(fixture.state.drafts.language.values.items.source0.language,'wu');
  fixture.state.tasks=fixture.state.tasks.filter(t=>t.id!=='language');delete fixture.state.drafts.language;delete fixture.state.latest_receipts.language;
  await reconnect.evaluate(()=>window.dispatchEvent(new Event('online')));await reconnect.getByRole('button',{name:/声音对比/}).waitFor();assert.equal(await reconnect.locator('button.task').count(),2);assert.equal(await reconnect.getByRole('button',{name:/语言标注/}).count(),0);
  console.log('PASS reconnect adds language without reload and removed active task returns to available tasks');await reconnectContext.close();
 }finally{if(browser)await browser.close();await fixture.close();}
}
if(require.main===module)run().catch(e=>{console.error(e);process.exitCode=1;});
