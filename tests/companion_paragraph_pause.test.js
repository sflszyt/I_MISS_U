// Synthetic final TTS requests; never opens a page or contacts a service.
const assert=require('node:assert/strict'),test=require('node:test');
const {context,Element,tick,response}=require('./companion_voice_harness');
async function present(text,options={}) {
 const h=context(),requests=[];h.VOICE_GROUPS=options.enabled!==false;h.MSG_MAX=30;
 h.fetch=async(url,opts)=>{requests.push(JSON.parse(opts.body));if(options.fail)throw Error('synthetic');return response();};
 h.startTurnPresentation(new Element(),text,1,'neutral');
 for(let i=0;i<6;i++)await tick();
 return {h,requests,finish(){h.cancelVoiceTurn();}};
}
test('empty final presentation preserves legacy fallback without TTS',async()=>{
 const t=await present('');try{assert.equal(t.h.voiceTurn.msgs.join(''),'…');assert.equal(t.h.voiceTurn.speechMsgs.join(''),'…');assert.equal(t.requests.length,0);}finally{t.finish();}
});
for(const [name,source,speech] of [
 ['LF','事情办好了\n\n侬慢慢讲','事情办好了。\n\n侬慢慢讲'],
 ['CRLF and whitespace','事情办好了\r\n \t\r\n\r\n侬慢慢讲','事情办好了。\r\n \t\r\n\r\n侬慢慢讲'],
 ['spaced closing quote','“好了？ ”\n\n继续','“好了？ ”\n\n继续'],
 ['nested spaced closers','（“好了？” ）\n\n继续',' \n\n继续'],
 ['nested spaced inner closer','“好了？ ” ）\n\n继续','“好了？ ” ）\n\n继续'],
 ['soft newline','事情\n办好了','事情\n办好了'],
 ['decimal and abbreviation','v3.14\nDr. Li\n\nNext','v3.14\nDr. Li。\n\nNext'],
 ...['。','！','？','!','?','…','...','。”','？”','?"','！）','。」'].map(end=>['terminal '+end,'好了'+end+'\n\n继续','好了'+end+'\n\n继续']),
 ['quote without terminal','“好了”\n\n继续','“好了。”\n\n继续']
])test(name+' actual payload and unchanged display',async()=>{
 const t=await present(source);try{assert.equal(t.requests.map(x=>x.text).join(''),speech);assert.equal(t.h.voiceTurn.msgs.join(''),source);}finally{t.finish();}
});
test('new audio key maps to original source on reload',()=>{
 const h=context();h.VOICE_GROUPS=true;
 const source='事情办好了\n\n侬慢慢讲',key='事情办好了。\n\n侬慢慢讲';
 const p=h.historyVoiceEntries(source,[{text:key,file:'audio/session_1.wav'}]);
 assert.equal(p.unresolved.length,0);assert.equal(p.positioned[0].text,source);assert.equal(p.positioned[0].audio.text,key);
});
test('120 codepoint requests and 360 budget include inserted pauses; source conserved',async()=>{
 for(const size of [117,118,119,120,121,237,357,358,359,360,361]) {
  const source='甲'.repeat(size)+'\n\n尾巴';const t=await present(source);
  try {
   const v=t.h.voiceTurn;
   assert.equal(v.msgs.join(''),source);
   assert.equal(v.speechMsgs.join(''),'甲'.repeat(size)+'。\n\n尾巴');
   assert(v.speechMsgs.every(x=>Array.from(x).length<=120));
   assert(t.requests.reduce((n,x)=>n+Array.from(x.text).length,0)<=360);
   assert.deepEqual(t.requests.map(x=>x.text),Array.from(v.speechMsgs).slice(0,v.voiceCount));
  }finally{t.finish();}
 }
 const t=await present('😀'.repeat(110)+'\n\n尾巴');try{assert.equal(t.requests.length,1);assert.equal(t.h.voiceTurn.msgs.join(''),'😀'.repeat(110)+'\n\n尾巴');}finally{t.finish();}
});
test('failed request retry uses identical speech and source stays intact',async()=>{
 const t=await present('先喝水\n\n慢慢讲',{fail:true});try{
  assert.equal(t.h.voiceTurn.requests[0],'failed');t.h.synthMsg(t.h.voiceTurn,0,true);await tick();await tick();
  assert.equal(t.requests.length,2);assert.deepEqual(t.requests[0],t.requests[1]);assert.equal(t.requests[1].text,'先喝水。\n\n慢慢讲');
 }finally{t.finish();}
});
test('legacy matching, canonical offsets, duplicate and overlapping safety',()=>{
 const h=context();h.VOICE_GROUPS=true;
 const audio=(text,n)=>({text:text.trim(),file:'audio/session_'+n+'.wav'});
 for(const [source,clips,unresolved] of [
  ['甲\n\n乙',[audio('甲\n\n乙',1)],0],
  ['😀甲\n\n乙尾',[audio('😀甲。\n\n乙',1)],0],
  ['甲\n\n乙 甲\n\n乙',[audio('甲。\n\n乙',1)],1],
  ['甲。\n\n乙 甲\n\n乙',[audio('甲。\n\n乙',1)],1],
  ['甲\n\n乙',[audio('甲。\n\n乙',1),audio('乙',2)],2],
  ['甲\n\n乙',[audio('甲。\n\n乙',1),audio('甲。\n\n乙',1)],0]
 ]) {
  const p=h.historyVoiceEntries(source,clips);assert.equal(p.positioned.map(x=>x.text).join(''),source);
  assert.equal(p.unresolved.length,unresolved);assert.equal(p.unresolved.length+p.positioned.filter(x=>x.audio).length,new Set(clips.map(x=>x.file)).size);
 }
});
test('disabled voice groups retain legacy requests',async()=>{
 const t=await present('甲\n\n乙',{enabled:false});try{assert.equal(t.requests.map(x=>x.text).join(''),'甲乙');}finally{t.finish();}
});
// Actual sendMessage -> SSE parser -> final presentation -> fetchVoiceBlob.
async function send(chunks,ending,options={}) {
 const h=context(),requests=[],logs=[];h.VOICE_GROUPS=true;h.MSG_MAX=30;
 Object.assign(h,{TextDecoder,streaming:false,sendPending:false,inputRevision:0,inputText:{value:'合成测试'},sendBtn:new Element(),history:[],sessionTurn:0,settings:{url:'https://synthetic.invalid',key:'synthetic',model:'synthetic',provider:'openai'},knowledgeCache:{},sessionsData:{},systemPrompt:'synthetic',shards:[],shardStatus:{},dataBlocked:0});
 for(const name of ['settingsComplete','loadContext','loadKnowledge','loadShards'])h[name]=()=>true;
 h.loadContext=async()=>true;
 for(const name of ['maybeReplayHistory','ensureSessionStarted','autoGrow','maybeActivateAutoVoice'])h[name]=()=>{};
 for(const name of ['collectAllRecords','extractTokens','retrieveSnippets','retrieveSessions'])h[name]=()=>[];
 if(options.prompt)h.systemPrompt=options.prompt;
 h.retrieveKnowledge=()=>({memories:[],transcripts:[]});h.buildRetrievalBlock=()=>'';h.detectEmotion=()=> 'neutral';h.logSession=x=>logs.push(x);h.systemNotice=x=>{throw Error(x);};
 const frames=chunks.map(s=>'data: '+JSON.stringify({choices:[{delta:{content:s}}]})+'\n\n');
 if(ending==='done')frames.push('data: [DONE]');
 h.fetch=async(url,opts)=>{
  if(url.endsWith('/tts')){requests.push(JSON.parse(opts.body));return response();}
  h.lastLLMRequest=JSON.parse(opts.body);
  return {ok:true,status:200,headers:{get:()=> 'text/event-stream'},body:{getReader:()=>({read:async()=>{if(frames.length)return {value:Buffer.from(frames.shift()),done:false};if(ending==='cancel')return new Promise(()=>{});if(ending==='error')throw Error('synthetic');return {done:true};},cancel(){},releaseLock(){}})}};
 };
 h.sendMessage();await tick();if(ending==='cancel')h.controller.abort();for(let n=0;n<6;n++)await tick();
 return {h,requests,logs,finish(){h.cancelVoiceTurn();}};
}
test('SSE delta split across paragraph waits for final DONE flush; logs source',async()=>{
 const t=await send(['事情办好了\n','\n侬','慢慢讲'],'done');try{
  assert.equal(t.requests.length,1);assert.equal(t.requests[0].text,'事情办好了。\n\n侬慢慢讲');
  assert.equal(t.h.history[1].content,'事情办好了\n\n侬慢慢讲');
  assert.equal(t.logs.find(x=>x.role==='simulacrum').text,'事情办好了\n\n侬慢慢讲');
 }finally{t.finish();}
});
for(const ending of ['cancel','error','eof'])test(ending+' cannot synthesize partial paragraph',async()=>{
 const t=await send(['事情办好了\n','\n侬慢慢讲'],ending);try{assert.equal(t.requests.length,0);assert.equal(t.h.history.length,0);assert(!t.logs.some(x=>x.role==='simulacrum'));}finally{t.finish();}
});
function backendStrip(text) {
 const script=`import ast,json,re,sys
from pathlib import Path
tree=ast.parse(Path(sys.argv[1]).read_text(encoding='utf8'))
nodes=[n for n in tree.body if (isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='BRACKET_RE' for t in n.targets)) or (isinstance(n,ast.FunctionDef) and n.name=='strip_brackets')]
assert len(nodes)==2
ns={'re':re}
exec(compile(ast.Module(body=nodes,type_ignores=[]),'tts_server.py:selected','exec'),ns)
print(json.dumps(ns['strip_brackets'](json.loads(sys.stdin.read())),ensure_ascii=False))`;
 return JSON.parse(require('child_process').execFileSync('python',['-X','utf8','-c',script,require('path').join(__dirname,'../tools/tts_server.py')],{input:JSON.stringify(text),encoding:'utf8'}));
}
for(const [name,source,payload,spoken] of [
 ['single LF annotation line','先喝水\n（轻声）\n慢慢讲','先喝水\n \n慢慢讲','先喝水 慢慢讲'],
 ['single CRLF annotation line','先喝水\r\n（轻声）\r\n慢慢讲','先喝水\r\n \r\n慢慢讲','先喝水 慢慢讲'],
 ['true blanklines around annotation','先喝水\n\n（轻声）\n\n慢慢讲','先喝水。\n\n \n\n慢慢讲','先喝水。 慢慢讲'],
 ['true CRLF blankline','先喝水（轻声）\r\n \r\n慢慢讲','先喝水。 \r\n \r\n慢慢讲','先喝水。 慢慢讲'],
 ['internal annotation blankline','先喝水（轻声\n\n稍慢）慢慢讲','先喝水 慢慢讲','先喝水 慢慢讲']
])test(name+' uses original blankline provenance in actual payload and backend',async()=>{
 const t=await present(source);try{
  assert.equal(t.requests.map(x=>x.text).join(''),payload);
  assert.equal(backendStrip(t.requests.map(x=>x.text).join('')),spoken);
  assert.equal(t.h.voiceTurn.msgs.join(''),source);
  const clips=t.requests.map((x,n)=>({text:x.text.trim(),file:'audio/session_'+n+'.wav'}));
  const p=t.h.historyVoiceEntries(source,clips);assert.equal(p.positioned.map(x=>x.text).join(''),source);assert.equal(p.unresolved.length,0);
 }finally{t.finish();}
});
test('annotation boundaries never expose action text in individual requests',async()=>{
 for(let n=113;n<=117;n++) {
  const source='甲'.repeat(n)+'（轻声。）\n\n慢慢讲',t=await present(source);
  try {
   assert.equal(t.requests.map(x=>backendStrip(x.text)).join('').replace(/\s/g,''),'甲'.repeat(n)+'。慢慢讲');
   assert.equal(t.h.voiceTurn.msgs.join(''),source);
   assert(t.requests.every(x=>Array.from(x.text).length<=120));
  }finally{t.finish();}
 }
});
test('removed annotation source offsets preserve leading/trailing/emoji/all-action display and history',async()=>{
 for(const source of ['（轻声）😀甲\n\n乙（稍慢）','[注]'+('甲'.repeat(119))+'（轻声。）\n\n乙','（轻声[稍慢]）','甲（'+('轻'.repeat(300))+'）\n\n乙']) {
  const t=await present(source);try{
   assert.equal(t.h.voiceTurn.msgs.join(''),source);
   assert(t.requests.every(x=>Array.from(x.text).length<=120));
   assert(t.requests.reduce((n,x)=>n+Array.from(x.text).length,0)<=360);
   const clips=t.requests.map((x,n)=>({text:x.text.trim(),file:'audio/session_'+n+'.wav'}));
   const p=t.h.historyVoiceEntries(source,clips);assert.equal(p.positioned.map(x=>x.text).join(''),source);assert.equal(p.unresolved.length,0);
   if(source==='（轻声[稍慢]）')assert.equal(t.requests.length,0);
  }finally{t.finish();}
 }
 const h=context();const p=h.historyVoiceEntries('甲（轻声）\n\n乙 甲[慢] 。\n\n乙',[{text:'甲。 \n\n乙',file:'audio/session_1.wav'}]);
 assert.equal(p.positioned.map(x=>x.text).join(''),'甲（轻声）\n\n乙 甲[慢] 。\n\n乙');
});
for(const [name,source,want] of [
 ['annotation','先喝水（轻声）\n\n慢慢讲','先喝水。 慢慢讲'],
 ['question before annotation','先喝水？（轻声）\n\n慢慢讲','先喝水？ 慢慢讲'],
 ['annotation terminal','先喝水（轻声？）\n\n慢慢讲','先喝水。 慢慢讲'],
 ['nested annotation','先喝水（轻声[稍慢]）\n\n慢慢讲','先喝水。 慢慢讲'],
 ['quote then annotation','“先喝水”（轻声）\n\n慢慢讲','“先喝水。” 慢慢讲'],
 ['annotation inside quote','“先喝水（轻声）”\n\n慢慢讲','“先喝水。 ” 慢慢讲'],
 ['only annotation','（轻声）\n\n慢慢讲','慢慢讲'],
 ['annotation-only middle paragraph','先喝水\n\n（轻声）\n\n慢慢讲','先喝水。 慢慢讲'],
 ['emoji annotation offset','😀（轻声）\n\n慢慢讲','😀。 慢慢讲'],
 ['nested question with annotation','（“好了？” ）\n\n继续','继续']
])test(name+' actual payload survives actual backend strip_brackets',async()=>{
 const t=await present(source);try{
  assert.equal(backendStrip(t.requests.map(x=>x.text).join('')),want);
  assert.equal(t.h.voiceTurn.msgs.join(''),source);
  const clips=t.requests.map((x,n)=>({text:x.text.trim(),file:'audio/session_'+n+'.wav'}));
  const plan=t.h.historyVoiceEntries(source,clips);assert.equal(plan.positioned.map(x=>x.text).join(''),source);assert.equal(plan.unresolved.length,0);
 }finally{t.finish();}
});

// Break caught: missing stop on a completed source line/EOF, not display or SSE cuts.
for(const phrase of ['请帖发出去就好','晓得了就好','还是就跟我讲一声晓得了']) {
 for(const separator of ['\n','\r\n','\n\n',''])test('completed expression '+phrase+JSON.stringify(separator),async()=>{
  const source=phrase+separator+(separator?'后面的安排慢慢商量。':''),want=phrase+'。'+separator+(separator?'后面的安排慢慢商量。':'');
  const t=await present(source);try {
   assert.equal(t.requests.map(x=>x.text).join(''),want);
   assert.equal(backendStrip(want),want.replace(/\s+/g,' ').trim());
   assert.equal(t.h.voiceTurn.msgs.join(''),source);
   assert.equal(t.h.voiceTurn.speechMsgs.join(''),want);
   console.log('SENTENCE_TRACE '+JSON.stringify({source,sourceGroups:t.h.voiceTurn.msgs,speechGroups:t.h.voiceTurn.speechMsgs,payloads:t.requests.map(x=>x.text),backend:backendStrip(want)}));
  }finally{t.finish();}
 });
}
for(const source of [
 '如果晓得了\n就告诉我。','要是请帖发出去就好\n后面的事还要再讲。','只要晓得了\n就行。',
 '如果请帖发出去就好\n那就再等等','请帖发出去就好\n还是要再确认','我不晓得\n了',
 '我想\n晓得了','请帖发出去就好\n的话再说。','请帖发出去就好\n还是要等回复？',
 '是不是晓得了','怎么晓得了','侬晓得了伐','“晓得了？”','“是不是晓得了”',
 '请帖发出去就好？','晓得了就好……','晓得了就好，','晓得了就好...',
 '比如晓得了','等晓得了','“晓得了\n就回答”。','前半句\n接后半句',
 '先喝水\n（动作）\n再说话','事情\n办好了'
])test('uncertain continuation or punctuation untouched '+source,async()=>{
 const t=await present(source);try{assert.equal(backendStrip(t.requests.map(x=>x.text).join('')),backendStrip(source));}finally{t.finish();}
});
test('completed quote and annotation preserve source offsets and terminal question',async()=>{
 for(const [source,want] of [['“晓得了就好”\n继续。','“晓得了就好。”\n继续。'],['请帖发出去就好（点头）\n继续。','请帖发出去就好。 \n继续。'],['“晓得了就好？”（点头）\n继续。','“晓得了就好？” \n继续。']]) {
  const t=await present(source);try{assert.equal(t.requests.map(x=>x.text).join(''),want);assert.equal(t.h.voiceTurn.msgs.join(''),source);}finally{t.finish();}
 }
});
test('D12 audio and new sentence audio both map without rewriting source; ambiguity remains unresolved',()=>{
 const h=context();h.VOICE_GROUPS=true;
 const source='晓得了就好\n后面的安排\n\n还是就跟我讲一声晓得了';
 const keys=[source,'晓得了就好\n后面的安排。\n\n还是就跟我讲一声晓得了','晓得了就好。\n后面的安排。\n\n还是就跟我讲一声晓得了。'];
 for(const key of keys){const p=h.historyVoiceEntries(source,[{text:key,file:'audio/synthetic_1.wav'}]);assert.equal(p.unresolved.length,0);assert.equal(p.positioned.map(x=>x.text).join(''),source);assert.equal(p.positioned[0].audio.text,key);}
 const p=h.historyVoiceEntries('晓得了就好\n晓得了就好',[{text:'晓得了就好。',file:'audio/synthetic_1.wav'}]);assert.equal(p.unresolved.length,1);
});
for(const ending of ['done','cancel','error','eof'])test('sentence SSE '+ending+' cannot use delta boundaries',async()=>{
 const source='请帖发出去就好\n后面的安排。\n晓得了就好';
 for(const chunks of [[source],['请帖发出去','就好\n后面的安排。\n晓得了','就好']]) {
  const t=await send(chunks,ending);try{if(ending==='done') {assert.equal(t.requests.map(x=>x.text).join(''),'请帖发出去就好。\n后面的安排。\n晓得了就好。');assert.equal(t.h.history[1].content,source);assert.equal(t.logs.find(x=>x.role==='simulacrum').text,source);}else{assert.equal(t.requests.length,0);assert.equal(t.h.history.length,0);}}finally{t.finish();}
 }
});
test('sentence punctuation is never inserted at 30 display or 120 synthesis cuts and counts toward 360',async()=>{
 for(const n of [29,30,119,120,238,239,357,358,359,360]){
  const source='甲'.repeat(n)+'请帖发出去就好',t=await present(source);
  try{assert.equal(t.h.voiceTurn.msgs.join(''),source);assert.equal(t.h.voiceTurn.speechMsgs.join(''),source+'。');assert(t.h.voiceTurn.speechMsgs.every(x=>Array.from(x).length<=120));assert(t.requests.reduce((n,x)=>n+Array.from(x.text).length,0)<=360);assert.equal((t.h.voiceTurn.speechMsgs.join('').match(/。/g)||[]).length,1);assert(t.h.displayGroupHtml(source).includes('display-chunk'));}finally{t.finish();}
 }
});

for(const source of ['侬晓得了伐\n\n后续事项明天再确认。','是不是晓得了\n\n后续事项明天再确认。','“是不是晓得了”\n\n后续事项明天再确认。'])test('overt question at real blankline is not converted to statement '+source,async()=>{
 const t=await present(source);try{
  assert.equal(t.requests.map(x=>x.text).join(''),source);
  const old=source.replace(/(”?)\n\n/,'。$1\n\n');
  const p=t.h.historyVoiceEntries(source,[{text:old,file:'audio/old-question.wav'}]);assert.equal(p.unresolved.length,0);assert.equal(p.positioned.map(x=>x.text).join(''),source);
 }finally{t.finish();}
});

for(const source of ['晓得了\n？','晓得了就好\n……','请帖发出去就好\n。','晓得了\r\n!','晓得了\n\n？'])test('review next-line punctuation '+JSON.stringify(source),async()=>{
 const t=await present(source);try{assert.equal(t.requests.map(x=>x.text).join(''),source);}finally{t.finish();}
});
for(const source of ['她说：“前头说过了。\n晓得了\n就来找我。”','“前头说过了。\n晓得了','她说：“前头说过了。\n晓得了\n\n就来找我。”','她说：「前头说过了。\n晓得了\n就来找我。」','她说："前头说过了。\n晓得了\n就来找我。"'])test('review multiline quote '+JSON.stringify(source),async()=>{
 const t=await present(source);try{assert.equal(t.requests.map(x=>x.text).join(''),source);assert.equal(t.h.voiceTurn.msgs.join(''),source);
 const old=t.h.paragraphSpeech(source,true).text;const p=t.h.historyVoiceEntries(source,[{text:old,file:'audio/d12-quote.wav'}]);assert.equal(p.unresolved.length,0);
 }finally{t.finish();}
});
for(const total of [119,120,121,239,240,241,359,360,361])test('review exact total length '+total+' preserves emitted stop within budget',async()=>{
 for(const wrap of ['plain','emoji','annotation','quote']){
  const end='请帖发出去就好',lead=wrap==='emoji'?'😀':wrap==='annotation'?'（注）':wrap==='quote'?'“':'',trail=wrap==='quote'?'”':'';
  const source=lead+'甲'.repeat(total-Array.from(lead+end+trail).length)+end+trail;
  assert.equal(Array.from(source).length,total);
  const t=await present(source);try{
   const groups=Array.from(t.h.voiceTurn.speechMsgs),raw=Array.from(t.h.voiceTurn.msgs);
   assert.equal(raw.join(''),source);assert(raw.every(Boolean),'no empty source bubble');assert(groups.every(x=>Array.from(x).length<=120));
   assert(groups.every(x=>/[\p{L}\p{N}]/u.test(x)),'no punctuation-only speech group');
   const expected=source.replace('（注）',' ').replace(/(”?)$/,'。$1');
   assert.equal(groups.join(''),expected);
   let budget=0,count=0;for(const group of groups){if(budget+Array.from(group).length>360)break;budget+=Array.from(group).length;count++;}
   assert.deepEqual(t.requests.map(x=>x.text),groups.slice(0,count));
   assert(budget<=360);if(Array.from(expected).length<=360)assert.equal(t.requests.map(x=>x.text).join(''),expected);
   assert.equal(backendStrip(t.requests.map(x=>x.text).join('')),backendStrip(groups.slice(0,count).join('')));
  }finally{t.finish();}
 }
});

test('review balanced tail has real speech and whole-group budget leaves explicit raw remainder',async()=>{
 for(const [total,lengths,voiced,remainder] of [[120,[61,60],121,0],[240,[120,61,60],241,0],[359,[120,120,120],360,0],[360,[120,120,61,60],301,59]]){
  const source='甲'.repeat(total-7)+'请帖发出去就好',t=await present(source);
  try{
   assert.deepEqual(Array.from(t.h.voiceTurn.speechMsgs,x=>Array.from(x).length),lengths);
   assert.equal(t.requests.reduce((n,x)=>n+Array.from(x.text).length,0),voiced);
   assert.equal(Array.from(t.h.voiceTurn.msgs.slice(t.h.voiceTurn.voiceCount).join('')).length,remainder);
   console.log('REVIEW_BOUNDARY_TRACE '+JSON.stringify({sourceLength:total,sourceGroups:t.h.voiceTurn.msgs,speechGroups:t.h.voiceTurn.speechMsgs,payloads:t.requests.map(x=>x.text),unvoicedSource:t.h.voiceTurn.msgs.slice(t.h.voiceTurn.voiceCount).join('')}));
  }finally{t.finish();}
 }
});

for(const source of ['晓得了\n就告诉我。','侬晓得了\n才好办后头的事。','侬晓得了\n再告诉我。','晓得了\n就好'])test('review v3 explicit continuation '+JSON.stringify(source),async()=>{
 const t=await present(source);try{assert.equal(t.requests.map(x=>x.text).join(''),source);assert.equal(t.h.voiceTurn.msgs.join(''),source);}finally{t.finish();}
});
for(const sep of ['\n','\r\n','\n\n'])for(const wrap of ['plain','annotation','quote'])for(const total of (wrap==='annotation'?[119,120,121,123]:[119,120,121]))test('review v3 interior inserted stop '+JSON.stringify(sep)+wrap+total,async()=>{
 const first=(wrap==='quote'?'“':'')+'甲'.repeat(total-7-(wrap==='quote'?2:wrap==='annotation'?3:0))+'请帖发出去就好'+(wrap==='quote'?'”':wrap==='annotation'?'（注）':'');
 assert.equal(Array.from(first).length,total);
 const source=first+sep+'乙'.repeat(121)+'。';const want=first.replace('（注）',' ').replace(/(”?)( ?)$/,'。$1$2')+sep+'乙'.repeat(121)+'。';
 const t=await present(source);try{
  assert.equal(t.h.voiceTurn.msgs.join(''),source);assert(Array.from(t.h.voiceTurn.msgs).every(Boolean));
  assert.equal(t.h.voiceTurn.speechMsgs.join(''),want);
  assert(t.h.voiceTurn.speechMsgs.every(x=>Array.from(x).length<=120));
  assert.equal(t.requests.map(x=>x.text).join(''),want,'every inserted stop must reach actual TTS');
  assert(t.requests.reduce((n,x)=>n+Array.from(x.text).length,0)<=360);
  assert.equal(backendStrip(t.requests.map(x=>x.text).join('')),backendStrip(want));
  console.log('INTERIOR_TRACE '+JSON.stringify({source,sourceGroups:t.h.voiceTurn.msgs,speechGroups:t.h.voiceTurn.speechMsgs,payloads:t.requests.map(x=>x.text)}));
 }finally{t.finish();}
});
