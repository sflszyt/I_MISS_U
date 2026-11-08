// Media state changes synchronously; DOM media events are queued tasks.
// Catch obsolete queued events stopping a new play or stealing another owner,
// and missing watchdog coverage when the browser's own controls start playback.
const assert=require('assert/strict');
const {context,turn,Element,mp3}=require('./companion_voice_harness');
class QueuedAudio extends Element {
 constructor(){super('audio');this.events=[];}
 queue(n){this.events.push(n);}
 flush(){while(this.events.length)super.emit(this.events.shift());}
 pause(){if(this.paused)return;this.paused=true;this.queue('pause');}
 play(){if(!this.paused)return Promise.resolve();this.paused=false;this.queue('play');if(!this.pending)this.queue('playing');return this.pending?new Promise(()=>{}):Promise.resolve();}
}
function fixture(){const h=context();h.document.createElement=t=>t==='audio'?new QueuedAudio():new Element(t);const vt=turn(h);const a=h.showVoiceMsg(vt,0,mp3(),1),b=h.showVoiceMsg(vt,1,mp3(),1);return {h,a,b,aa:a._historyAudio,ba:b._historyAudio};}
const wait=()=>new Promise(r=>setTimeout(r,75));
const cases={
 async delayed_pause(){const {h,a,aa}=fixture();h.replayBar(a);aa.flush();aa.pause();h.replayBar(a);aa.flush();a._historyAudio.flush();assert.equal(h.replayAudio,a._historyAudio,'queued old pause must not clear replacement owner');assert(!a._historyAudio.paused,'queued old pause must not pause new replay');},
 async delayed_play(){const {h,a,b,aa,ba}=fixture();aa.emit('pointerdown');aa.play();h.replayBar(b);aa.flush();ba.flush();assert.equal(h.replayAudio,ba,'queued play with superseded gesture must not steal B');assert(!ba.paused);assert(aa.paused);},
 async native_pending(){const {h,a,aa}=fixture();aa.pending=true;aa.emit('pointerdown');aa.play();aa.flush();assert.equal(h.replayAudio,aa);await wait();assert(a._historyStatus.textContent.includes('AUDIO_PLAY_PENDING'),'direct native controls need bounded pending diagnostic');assert(aa.paused);assert.equal(h.replayAudio,null);assert(!a._historyRetry.hidden);},
 async native_pending_same_owner(){const {h,a,aa}=fixture();h.replayBar(a);aa.flush();aa.pause();aa.pending=true;aa.emit('pointerdown');aa.play();aa.flush();await wait();assert(a._historyStatus.textContent.includes('AUDIO_PLAY_PENDING'),'native pause/replay before queued pause needs a new watchdog');assert(aa.paused);},
 async pending_canceled(){const {h,a,b,aa,ba}=fixture();aa.pending=true;aa.emit('pointerdown');aa.play();aa.flush();h.replayBar(b);aa.flush();ba.flush();await wait();assert.equal(h.replayAudio,ba);assert(!ba.paused);assert(!a._historyStatus.textContent.includes('PENDING'),'superseded deadline must be canceled');},
 async pending_confirmed(){const {h,a,aa}=fixture();aa.pending=true;aa.emit('pointerdown');aa.play();aa.flush();aa.queue('playing');aa.flush();await wait();assert.equal(h.replayAudio,aa);assert(!aa.paused);assert.equal(a._historyStatus.textContent,'');},
 async pending_hidden(){const {h,a,aa}=fixture();aa.pending=true;aa.emit('pointerdown');aa.play();aa.flush();h.document.hidden=true;h.suspendNativeVoice(false);aa.flush();await wait();h.document.hidden=false;aa.queue('playing');aa.flush();assert(aa.paused);assert.equal(h.replayAudio,null);assert(!a._historyStatus.textContent.includes('PENDING'));}
};
(async()=>{let failures=0;for(const [name,run] of Object.entries(cases)){try{await run();console.log('PASS '+name);}catch(e){failures++;console.error('FAIL '+name+': '+e.message.split('\n')[0]);}}if(failures)process.exitCode=1;})();
