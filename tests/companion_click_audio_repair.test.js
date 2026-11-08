const assert=require('assert/strict');
const {context,tick,Element,mp3,response}=require('./companion_voice_harness');
(async()=>{
 const h=context();h.inputText={value:'draft'};h.inputRevision=0;h.lastInputValue='draft';h.autoGrow=()=>{};
 h.trackDraftInput();assert.equal(h.inputRevision,0,'same input must not cancel');h.inputText.value='changed';h.trackDraftInput();h.inputText.value='draft';h.trackDraftInput();assert.equal(h.inputRevision,2,'A-B-A must cancel');
 let finish,writes=0;const held=new Promise(r=>finish=r);assert.equal(await h.boundedWait(held,10).then(()=>writes++,()=> 'timeout'),'timeout');finish('late');await tick();assert.equal(writes,0);
 console.log('PASS draft revision and bounded late-resolution isolation');
 const host=new Element(),bar=host.appendChild(new Element());bar._voiceUrl='synthetic';let calls=0;h.fetch=async()=>{calls++;return response();};h.document.createElement=t=>{const e=new Element(t);if(t==='audio')e.reject=true;return e;};h.wireHistoryBar(bar);bar.emit('click');bar.emit('click');await tick();assert.equal(calls,1);assert(bar._historyAudio.controls);assert(bar._voiceBlob);assert(bar._historyStatus.textContent.includes('AUDIO_PLAY'));assert(!bar._historyStatus.textContent.includes('PRIVATE'));
 bar._historyAudio.reject=false;bar.emit('click');await tick();assert(!bar._historyAudio.paused);assert.equal(calls,1,'retry uses cached audio');
 const other=host.appendChild(new Element());other._voiceBlob=mp3();h.wireHistoryBar(other);h.document.createElement=t=>new Element(t);h.playHistoryNative(other);await tick();assert(bar._historyAudio.paused);h.playHistoryNative(bar);await tick();assert(other._historyAudio.paused);assert(!bar._historyAudio.paused);
 bar._historyAudio.ended=true;bar._historyAudio.currentTime=1;bar._historyAudio.paused=true;bar._historyAudio.emit('ended');assert.equal(h.replayAudio,null);bar._historyAudio.ended=false;h.playHistoryNative(bar);assert(!bar._historyAudio.paused);
 let rejectOld;bar._historyAudio.pause();bar._historyAudio.play=()=>new Promise((_,r)=>rejectOld=r);h.playHistoryNative(bar);bar._historyAudio.paused=false;bar._historyAudio.emit('playing');rejectOld(Error('PRIVATE_OLD'));await tick();assert(!bar._historyAudio.paused,'late rejection cannot stop confirmed playback');
 other._historyAudio.emit('pointerdown');other._historyAudio.play();assert(bar._historyAudio.paused);assert.equal(h.replayAudio,other._historyAudio);bar._historyAudio.emit('ended');bar._historyAudio.emit('error');bar._historyAudio.emit('playing');assert.equal(h.replayAudio,other._historyAudio);
 console.log('PASS native history cached retry, A-B-A, ended replay, stale promise/events and direct-controls takeover');
})().catch(e=>{console.error(e);process.exitCode=1;});
