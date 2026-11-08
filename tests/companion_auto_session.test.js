const assert=require('assert/strict');
const {context,turn,mp3,Element,tick}=require('./companion_voice_harness');
const renderedCue=process.argv[2]&&require('fs').readFileSync(process.argv[2],'utf8').match(/var AUTO_VOICE_CUE = '([^']+)'/)[1];
function fixture(){const h=context();h.AUTO_VOICE_SESSION=true;h.AUTO_VOICE_CUE='data:audio/wav;base64,cue';h.document.body=new Element();h.document.getElementById=()=>new Element();let gesture=false;
h.document.createElement=t=>{const a=new Element(t);a.setAttribute=()=>{};if(t==='audio'){a.load=()=>{a.currentSrc=a.src;a.currentTime=0;a.readyState=3;};a.play=function(){if(gesture)this.allowed=true;if(!this.allowed)return Promise.reject(Object.assign(new Error(),{name:'NotAllowedError'}));this.paused=false;return Promise.resolve();};}return a;};
if(renderedCue){h.AUTO_VOICE_CUE=renderedCue;h.pageUiPrefs={voiceText:true,autoVoiceEnabled:true};}
return {h,activate(){gesture=true;h.initAutoVoiceSession().button.listeners.click[0]({isTrusted:true});gesture=false;},progress(){h.autoVoiceSession.audio.currentTime=1;h.autoVoiceSession.audio.ended=true;h.autoVoiceSession.audio.paused=true;}};}
(async()=>{
const {h,activate,progress}=fixture();const v=turn(h),a=h.showVoiceMsg(v,0,mp3(),1),b=h.showVoiceMsg(v,1,mp3(),1);
h.playHistoryNative(a,v);await tick();assert.equal(h.replayAudio,null,'no automatic attempt before activation');assert(!h.autoVoiceSession.ready);
activate();await tick();assert(!h.autoVoiceSession.ready,'promise alone cannot establish readiness');progress();await new Promise(r=>setTimeout(r,60));assert(h.autoVoiceSession.ready);const stable=h.autoVoiceSession.audio;
h.stopReplay();h.playHistoryNative(a,v);assert(h.replayAudio===stable);h.stopReplay();h.playHistoryNative(b,v);assert(h.replayAudio===stable);assert(a._historyAudio!==b._historyAudio);assert(a._historyAudio!==stable);
const oldSrc=a._historyAudio.src;assert(oldSrc!==b._historyAudio.src);
const next=turn(h);const c=h.showVoiceMsg(next,0,mp3(),1);h.playHistoryNative(c,next);assert(h.replayAudio===stable);
h.document.hidden=true;h.suspendNativeVoice(false);assert(stable.paused);assert(!h.autoVoiceSession.ready);h.document.hidden=false;h.playHistoryNative(c,next);assert.equal(h.replayAudio,null);h.suspendNativeVoice(false);activate();h.stopReplay();progress();await new Promise(r=>setTimeout(r,60));assert(!h.autoVoiceSession.ready);
// Queued source events have no authority over a newly assigned source.
activate();progress();await new Promise(r=>setTimeout(r,60));h.stopReplay();h.playHistoryNative(c,next);
const job=h.autoVoiceSession.job;stable.emit('playing');stable.emit('ended');stable.emit('pause');
assert(h.autoVoiceSession.job===job);assert(!job.started);
h.stopReplay();
// Rapid activation taps preserve the pending cue owner.
h.suspendNativeVoice(false);activate();const pending=h.autoVoiceSession.job;activate();assert.equal(h.autoVoiceSession.job,pending);assert(!h.autoVoiceSession.ready);h.stopReplay();
// A pending cue is bounded and its visible status is truthful.
h.suspendNativeVoice(false);let now=1000;h.Date={now:()=>now};activate();now=12000;await new Promise(r=>setTimeout(r,60));
assert.equal(h.autoVoiceSession.job,null);assert(h.autoVoiceSession.status.textContent.includes('PENDING'));assert(!h.autoVoiceSession.ready);
// Native manual takeover cancels shared ownership without rebinding native clips.
activate();h.stopReplay();h.playHistoryNative(c,next);c._historyAudio.allowed=true;c._historyAudio.emit('pointerdown');
c._historyAudio.paused=false;c._historyAudio.emit('play');assert(h.replayAudio===c._historyAudio);assert(stable.paused);h.stopReplay();
// Profile invalidation cancels current source on the next bounded observation.
h.playHistoryNative(c,next);h.settings={provider:'changed'};await new Promise(r=>setTimeout(r,60));assert.equal(h.replayAudio,null);
console.log('PASS queued events, rapid tap, pending deadline, native ownership, profile invalidation');
console.log('PASS activation gate, activation progress, stable groups/replies, native clip isolation, background and canceled cue');
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
