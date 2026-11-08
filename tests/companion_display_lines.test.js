// Synthetic only: transport fetch and TTS fetch are replaced by local mocks.
const assert=require('node:assert/strict'),test=require('node:test');
const {setup}=require('./companion_stream_completion.test');
const {context,Element,tick,response}=require('./companion_voice_harness');
const example='疑似还不是确诊，先勿要自己吓自己。尽快带着检查报告去看甲状腺外科或内分泌科，让医生看看要不要做穿刺。\n\n侬是做了什么检查，说疑似的？';
const fixtures=[example,example.replace('甲状腺','甲状腺\n').replace('检查，说','检查\n，说'),
 '“第一句。”\r\n\r\n「第二句？」\r\n下一行。','甲\n乙\n\n丙。',
 'Report TSH 2.5 mIU/L, next appointment tomorrow.\n\nOK?',
 '甲'.repeat(260),'😀'.repeat(130)+'。','<script>&"\'\n\n安全。'];
test('display has one flow box; preserves actual newlines, paragraphs and escaping',()=>{
 const h=context();
 for(const text of fixtures){
  const html=h.displayGroupHtml(text);
  assert.equal((html.match(/<div /g)||[]).length,1);
  const decoded=html.replace(/^<div[^>]*>|<\/div>$/g,'').replaceAll('&lt;','<').replaceAll('&gt;','>').replaceAll('&quot;','"').replaceAll('&#39;',"'").replaceAll('&amp;','&');
  assert.equal(decoded,text);
  const plan=h.paragraphVoicePlan(text);
  assert.equal(plan.source.join(''),text);
  const pool=plan.speech.map((s,i)=>({text:s.trim(),file:`audio/synthetic_${i}.wav`,dur:1}));
  const history=h.historyVoiceEntries(text,pool);
  assert.equal(history.positioned.map(x=>x.text).join(''),text);
  assert.equal(history.positioned.filter(x=>x.audio).length+history.unresolved.length,pool.length);
 }
 // The original UI defect was exactly the reported two word/punctuation cuts.
 const oldBlocks=Array.from(example).reduce((a,c,i)=>(i%30===0?a.push(c):a[a.length-1]+=c,a),[]);
 assert.equal(oldBlocks[0].slice(-3),'甲状腺');
 assert.equal(oldBlocks[1].slice(-2),'检查');
 assert.equal(oldBlocks[2][0],'，');
 console.log('baseline 30-character breaks reproduced at 甲状腺|外科 and 检查|，');
});
test('every possible SSE byte cut and every content delta cut preserve source',async()=>{
 let byteCuts=0,deltaCuts=0;
 for(const text of fixtures){
  const event=s=>'data: '+JSON.stringify({choices:[{delta:{content:s}}]})+'\r\n\r\n';
  const wire=Buffer.from(event(text)+'data: [DONE]\r\n\r\n');
  async function check(chunks){
   const t=setup(chunks);await new Promise(setImmediate);
   assert.deepEqual(t.errors,[]);assert.equal(t.done[0]?.[0],text);assert.equal(t.deltas.join(''),text);
  }
  for(let i=0;i<=wire.length;i++){await check([wire.subarray(0,i),wire.subarray(i)]);byteCuts++;}
  // UTF-16 cuts include surrogate-pair splits, as callbacks may contain either half.
  for(let i=0;i<=text.length;i++){await check([event(text.slice(0,i)),event(text.slice(i))+'data: [DONE]\n\n']);deltaCuts++;}
  await check(Array.from(wire,b=>Buffer.from([b])));
 }
 console.log(JSON.stringify({byteCuts,deltaCuts,oneByteStreams:fixtures.length}));
});
test('live presentation sends unchanged speech; history/replay retain original audio association',async()=>{
 const h=context();h.VOICE_GROUPS=true;h.MSG_MAX=30;
 const requests=[];h.fetch=async(u,o)=>{requests.push(JSON.parse(o.body).text);return response();};
 h.startTurnPresentation(new Element(),example,1,'neutral');
 for(let i=0;i<12;i++)await tick();
 const vt=h.voiceTurn;
 assert.equal(vt.msgs.join(''),example);assert.equal(requests.join(''),example);
 const bar=vt.bars[0],blob=bar._voiceBlob;assert(blob);
 h.replayBar(bar);await tick();assert.equal(bar._voiceBlob,blob);assert.equal(requests.length,1);
 const plan=h.historyVoiceEntries(example,[{text:requests[0],file:'audio/legacy.wav',dur:1}]);
 assert.equal(plan.unresolved.length,0);assert.equal(plan.positioned[0].audio.file,'audio/legacy.wav');
 h.cancelVoiceTurn();
});
