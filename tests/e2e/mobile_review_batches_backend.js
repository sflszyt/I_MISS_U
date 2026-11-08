/* Real server + ephemeral signed identity; packages and WAVs generated locally by helper. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const BASE='/review/batches/voice-pilot-20261023/';
async function run(){
 const {origin}=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));assert.match(origin,/^http:\/\/127\.0\.0\.1:\d+$/);
 const browser=await require('playwright').chromium.launch({headless:true,channel:'msedge'});
 try{
  const c=await browser.newContext({viewport:{width:390,height:844}}),p=await c.newPage();p.on('dialog',d=>d.accept());
  const session=async(base=BASE)=>{const r=await c.request.get(origin+base+'api/session');assert.equal(r.status(),200);return r.json();};
  const beforeOld=await session('/review/'),beforeNew=await session();assert.equal(beforeOld.tasks.length,3);assert.equal(beforeNew.tasks.length,1);assert.equal(beforeNew.tasks[0].items.length,12);
  assert.doesNotMatch(JSON.stringify(beforeNew),/answer.?key|checkpoint|condition|model_name|source_take|baseline/);
  const saved=async()=>p.locator('#status-ab').filter({hasText:'已保存到电脑'}).waitFor();
  const open=async(base=BASE)=>{await p.goto(origin+base);await p.getByRole('button',{name:/声音对比/}).click();};
  const submit=async()=>{await p.getByRole('button',{name:'提交本次结果',exact:true}).click();await p.getByRole('button',{name:'确认提交',exact:true}).evaluate(b=>{b.click();b.click();});};
  await open();await p.locator('.audio button').nth(0).click();await p.waitForFunction(()=>document.querySelectorAll('audio')[0].readyState>=2&&!document.querySelectorAll('audio')[0].paused);
  await p.locator('.audio button').nth(1).click();await p.waitForFunction(()=>document.querySelectorAll('audio')[0].paused&&!document.querySelectorAll('audio')[1].paused);
  assert.equal(await p.locator('audio').nth(1).evaluate(a=>a.duration),3);
  for(let i=0;i<3;i++)await p.getByRole('button',{name:'A 更好',exact:true}).click();await saved();
  await c.setOffline(true);await p.locator('#note').fill('synthetic offline new batch');await p.locator('#status-ab').filter({hasText:'尚未同步：'}).waitFor();await c.setOffline(false);await p.reload();await p.getByRole('button',{name:/声音对比/}).click();await saved();assert.equal(await p.locator('#note').inputValue(),'synthetic offline new batch');
  let acknowledgeLost;const lost=new Promise(resolve=>acknowledgeLost=resolve);
  await p.route('**/api/tasks/ab/submit',async route=>{const r=await route.fetch();assert.equal(r.status(),200);await route.abort();acknowledgeLost();},{times:1});await submit();await lost;await p.locator('#recover-submit').waitFor({state:'visible'});
  const persisted=await session();const first=persisted.latest_receipts.ab.receipt_id;
  await p.reload();await p.getByText('电脑已收到正式提交').waitFor();assert.equal((await session()).latest_receipts.ab.receipt_id,first);
  const link=p.getByRole('link',{name:'下载 JSON 备用副本'});assert.equal(await link.getAttribute('href'),BASE+'api/receipts/'+first+'/export');
  const promise=p.waitForEvent('download');await link.click();const download=await promise;const result=JSON.parse(fs.readFileSync(await download.path(),'utf8'));
  assert.equal(result.training_approval,false);assert.equal(result.generated_audio_tier,3);assert.equal(result.decision_kind,'listening_preference_only');assert.equal(result.choices.length,12);assert.equal(result.choices.filter(x=>x.preference!=='unheard').length,1);assert.doesNotMatch(JSON.stringify(result),/answer.?key|checkpoint|condition|model_name|source_take|baseline/);
  await p.getByRole('button',{name:/声音对比/}).click();await p.getByRole('button',{name:'B 更好',exact:true}).click();await saved();const submitted=p.waitForResponse(r=>r.url().endsWith('/tasks/ab/submit')&&r.status()===200);await submit();await submitted;await p.getByText('电脑已收到正式提交').waitFor();const second=(await session()).latest_receipts.ab;
  const receipt=await (await c.request.get(origin+BASE+'api/receipts/'+second.receipt_id)).json();assert.equal(receipt.supersedes,first);assert.deepEqual(receipt.counts,{judged:1,unheard:11});
  const afterOld=await session('/review/');assert.deepEqual(afterOld.drafts,beforeOld.drafts);assert.deepEqual(afterOld.latest_receipts,beforeOld.latest_receipts);
  await open('/review/');await p.getByRole('button',{name:'A 更好',exact:true}).click();await saved();await p.locator('#note').fill('old-only note');await saved();await open();assert.equal(await p.locator('#note').inputValue(),'synthetic offline new batch');assert.equal(await p.getByRole('button',{name:'B 更好',exact:true}).getAttribute('aria-pressed'),'true');
  for(const width of [320,390]){await p.setViewportSize({width,height:844});assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);await p.screenshot({path:path.join(process.env.MOBILE_REVIEW_EVIDENCE,`signed-batch-${width}.png`),fullPage:true});}
  for(const file of ['manifest.json','answer-key.json','frozen/answer-key.json']){const r=await c.request.get(origin+BASE+file);assert.equal(r.status(),404);}
  const wrongReceipt=await c.request.get(origin+'/review/api/receipts/'+first);assert.equal(wrongReceipt.status(),404);
  console.log('PASS real signed synthetic backend: AB-only12/24; old3 tasks; decoded WAVs/mutual exclusion; repeated choice/submit; offline reload; persisted lost-ack recovery; partial JSON Tier3/no approval; supersedes; independent drafts/receipts; mapping 404; cross-batch receipt 404; 320/390 layout');
  await c.close();
 }finally{await browser.close();}
}
run().catch(e=>{console.error(e);process.exitCode=1;});
