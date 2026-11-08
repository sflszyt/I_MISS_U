const {context}=require('./companion_voice_harness');
const assert=require('assert/strict');
const h=context();h.MSG_MAX=30;h.VOICE_GROUPS=true;
assert.equal(typeof h.splitVoiceGroups,'function');
for(const text of ['好。','甲'.repeat(100)+'。短句。','😀'.repeat(130),'甲'.repeat(500),'甲。\n乙。']){
 const groups=Array.from(h.splitVoiceGroups(text));
 assert.equal(groups.join(''),text);
 assert.ok(groups.every(x=>Array.from(x).length<=120));
}
assert.deepEqual(Array.from(h.splitVoiceGroups('甲'.repeat(100)+'。短句。')),['甲'.repeat(100)+'。短句。']);
console.log('voice group conservation passed');

(async()=>{
 const {Element,tick}=require('./companion_voice_harness');
 const v=context();v.MSG_MAX=30;v.VOICE_GROUPS=true;
 const requests=[];v.fetch=async(url,opts)=>{requests.push(JSON.parse(opts.body).text);return require('./companion_voice_harness').response();};
 const text=('甲'.repeat(100)+'。').repeat(5);
 v.startTurnPresentation(new Element(),text,1,'neutral');
 for(let n=0;n<20;n++) await tick();
 assert.equal(requests.length,3);
 assert.equal(requests.join(''),text.slice(0,303));
 assert.equal(v.voiceTurn.msgs.join(''),text);
 assert.equal(v.voiceTurn.voiceCount,3);
 assert.equal(v.voiceTurn.bars.filter(Boolean).length,3);
 assert.equal(v.voiceTurn.contents.filter(Boolean).length,5);
 const html=v.displayGroupHtml('😀'.repeat(61));
 assert.equal((html.match(/display-chunk/g)||[]).length,1);
 assert.equal(html.replace(/<[^>]+>/g,''),'😀'.repeat(61));
 v.cancelVoiceTurn();
 console.log('enabled grouped requests/budget/display/history passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
