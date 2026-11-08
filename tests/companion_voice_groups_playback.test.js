const assert=require('assert/strict');
const {context,Element,tick,response}=require('./companion_voice_harness');
const text=('甲'.repeat(90)+'。').repeat(3);
function setup(){const h=context();h.VOICE_GROUPS=true;h.MSG_MAX=30;return h;}
(async()=>{
 for(const kind of ['reject','pending','retry']) {
  const h=setup();let requests=[];
  h.document.createElement=t=>{const e=new Element(t);if(t==='audio')e[kind]=true;return e;};
  h.fetch=async(u,o)=>{requests.push(JSON.parse(o.body).text);return kind==='retry'&&requests.length===1?{ok:false,status:503}:response();};
  h.startTurnPresentation(new Element(),text,1,'neutral');
  await new Promise(r=>setTimeout(r,100));
  const v=h.voiceTurn;
  assert.equal(v.bars.filter(Boolean).length,3);
  assert.equal(requests.join(''),text);
  if(kind==='retry') {
   v.bars[0]._historyRetry.emit('click');v.bars[0]._historyRetry.emit('click');await tick();
   assert.equal(requests.length,4);assert.equal(requests[3],v.msgs[0]);assert(v.bars[0]._voiceBlob);
  }
  h.cancelVoiceTurn();
 }
 const h=setup();let resolve;
 h.fetch=()=>new Promise(r=>resolve=r);
 h.startTurnPresentation(new Element(),text,1,'neutral');await tick();const old=h.voiceTurn;
 h.cancelVoiceTurn();h.ttsAvailable=false;
 h.startTurnPresentation(new Element(),'新回复。',2,'neutral');
 resolve(response());await tick();
 assert(old.bars[0]._voiceBlob);assert(!old.bars[1]);assert.equal(old.bars[0]._historyAudio.plays,undefined);
 h.cancelVoiceTurn();
 console.log('enabled grouped refusal/pending/retry/newturn/late retention pass');
})().catch(e=>{console.error(e);process.exitCode=1;});
