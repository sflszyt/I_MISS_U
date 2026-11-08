const {context}=require('./companion_voice_harness');
const assert=require('assert/strict');
const h=context();h.VOICE_GROUPS=true;h.MSG_MAX=30;
const audio=(text,i)=>({text:text.trim(),file:'audio/session_'+i+'.wav',dur:1});
const natural='甲'.repeat(79)+'，'+'乙'.repeat(39)+'。';
assert.equal(h.splitVoiceGroups(natural+'\n丙。')[0],natural);
assert.equal(typeof h.historyVoiceEntries,'function');
for(const [text,clips] of [
 ['甲'.repeat(118)+'。\n'+'乙'.repeat(118)+'。\n好。',null],
 ['甲。乙。丙。',[audio('甲。',1),audio('乙。丙。',2)]],
 ['好。中间。好。',[audio('好。',1)]],
 ['  甲。\n乙。  ',[audio('  甲。\n乙。  ',1)]],
 ['\n甲。\n乙。\n',[]]
]) {
 const pool=clips||Array.from(h.splitMessages(text)).map(audio);
 const plan=h.historyVoiceEntries(text,pool);
 assert.equal(plan.positioned.map(x=>x.text).join(''),text);
 const rendered=[...plan.positioned.filter(x=>x.audio),...plan.unresolved];
 assert.equal(rendered.length,pool.length);
 assert.equal(new Set(rendered.map(x=>x.audio.file)).size,pool.length);
 if(text==='好。中间。好。') {assert.equal(plan.unresolved.length,1);assert.equal(plan.positioned.filter(x=>x.audio).length,0);}
}
console.log('history mixed/legacy/partial/repeated/trim/noaudio and 120 boundary pass');

const text='甲。乙。丙。';
for(const pool of [[audio('甲。',1)],[audio(text,1)],[audio(text,1),audio('甲。',2)],[audio('甲。',1),audio('甲。',1)]]) {
 const p=h.historyVoiceEntries(text,pool);
 assert.equal(p.positioned.map(x=>x.text).join(''),text);
 assert.equal([...p.positioned.filter(x=>x.audio),...p.unresolved].length,new Set(pool.map(x=>x.file)).size);
}
h.SESSIONS_BASE='synthetic/';
const pool=[audio('好。',1),audio('好。',2)];
assert.equal(h.renderGroupedHistory('好。中间。好。',pool),3);
assert.equal(h.voiceBars.length,2);
assert.deepEqual(h.voiceBars.map(b=>b._voiceUrl),pool.map(x=>'synthetic/'+x.file));
console.log('history rendered ambiguous entries exactly once without positioning');
