/* Real backend, synthetic signed identity and generated tone WAV only. */
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
async function run(){
 const info=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
 assert.match(info.origin,/^http:\/\/127\.0\.0\.1:\d+$/);
 const {chromium}=require('playwright');const browser=await chromium.launch({headless:true,channel:'msedge'});
 try{
  const context=await browser.newContext({viewport:{width:390,height:844}});
  const session=async()=>{const response=await context.request.get(info.origin+'/review/api/session');assert.equal(response.status(),200);return response.json();};
  const before=await session();assert.equal(before.tasks.length,3);const task=before.tasks.find(t=>t.id==='language');assert.equal(task.items.length,12);
  let p=await context.newPage();p.on('dialog',d=>d.accept());p.on('response',r=>{if(r.url().endsWith('/export'))console.log('Export HTTP status',r.status());});await p.goto(info.origin+'/review/#language');
  const saved=()=>p.locator('#status-language').filter({hasText:'已保存到电脑'}).waitFor();
  const choose=async label=>{await p.getByRole('button',{name:label,exact:true}).click();await saved();};
  const submit=async()=>{await p.getByRole('button',{name:'提交本次结果',exact:true}).click();await p.getByRole('button',{name:'确认提交',exact:true}).click();await p.getByText('电脑已收到正式提交').waitFor();};
  await p.getByRole('heading',{name:/录音 1 /}).waitFor();await p.getByRole('button',{name:'▶ 播放原声',exact:true}).click();await p.waitForFunction(()=>!document.querySelector('audio').paused);
  await choose('不确定');await p.locator('#note').fill('合成未知语言');await saved();await submit();const first=(await session()).latest_receipts.language;
  const downloadPromise=p.waitForEvent('download');await p.getByRole('link',{name:'下载 JSON 备用副本'}).click();const download=await downloadPromise;const exported=JSON.parse(fs.readFileSync(await download.path(),'utf8'));
  assert.equal(exported.training_approval,false);assert.equal(exported.decision_kind,'source_language_annotation_only');assert.equal(exported.labels.length,1);assert.equal(exported.labels[0].language,'unknown');assert.equal(exported.source_review_receipt,null);assert.equal('reviews' in exported,false);
  await p.reload();await p.getByRole('button',{name:'不确定',exact:true}).waitFor();assert.equal(await p.getByRole('button',{name:'不确定',exact:true}).getAttribute('aria-pressed'),'true');
  await p.close();p=await context.newPage();p.on('dialog',d=>d.accept());await p.goto(info.origin+'/review/#language');assert.equal(await p.locator('#note').inputValue(),'合成未知语言');
  await p.getByRole('button',{name:'下一项 ›',exact:true}).click();await choose('两种都有');await submit();const after=await session();assert.deepEqual(after.drafts.ab,before.drafts.ab);assert.deepEqual(after.drafts.source,before.drafts.source);assert.deepEqual(after.latest_receipts.ab,before.latest_receipts.ab);assert.deepEqual(after.latest_receipts.source,before.latest_receipts.source);
  const latest=await (await context.request.get(info.origin+'/review/api/receipts/'+after.latest_receipts.language.receipt_id)).json();assert.equal(latest.supersedes,first.receipt_id);assert.equal(latest.counts.labeled,2);assert.equal(latest.counts.pending,10);
  assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth<=390),true);await p.screenshot({path:path.join(process.env.MOBILE_REVIEW_EVIDENCE,'language-signed-synthetic-390.png'),fullPage:true});
  console.log('PASS real backend + signed synthetic JWT: 12 original numbers, audio, unknown-only partial submit, JSON export without training approval, refresh/reopen, mixed superseding submit, old AB/source drafts and receipts untouched, mobile layout');
  await context.close();
 }finally{await browser.close();}
}
run().catch(e=>{console.error(e);process.exitCode=1;});
