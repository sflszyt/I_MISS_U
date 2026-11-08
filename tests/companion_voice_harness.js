// Regression: generated segments must remain available when autoplay fails,
// cancellation/profile changes must isolate late responses, and stale media
// events must never take ownership or advance a different segment.
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const source=fs.readFileSync(process.argv[2]||__dirname+'/../tools/build_companion_page.py','utf8');
const functions=[...source.matchAll(/^function \w+\([^\n]*\) \{.*?^\}/gms)].map(m=>m[0]).join('\n').replace(/__TTS_HEADERS_\w+__/g,"headers: {'Content-Type':'application/json'}").replace(/__[A-Z_]+__/g,'');
class Element {
 constructor(tag='div'){this.tagName=tag;this.children=[];this.listeners={};this.style={};this.classes=new Set();this.classList={add:n=>this.classes.add(n),remove:n=>this.classes.delete(n)};this.paused=true;this.ended=false;this.currentTime=0;this.duration=1;this.textContent='';}
 appendChild(c){c.parentNode=this;this.children.push(c);return c;}
 insertBefore(c,b){c.parentNode=this;const n=this.children.indexOf(b);this.children.splice(n<0?this.children.length:n,0,c);}
 removeChild(c){this.children.splice(this.children.indexOf(c),1);c.parentNode=null;}
 set innerHTML(s){this.children=[];if(s.includes('voice-bar')){this.bar=this.appendChild(new Element());this.bar.className='voice-bar';}}
 querySelector(s){if(s==='.voice-bar')return this.bar;return this.children.find(c=>'.'+c.className===s)||null;}
 querySelectorAll(){return [];}
 addEventListener(n,f){(this.listeners[n]??=[]).push(f);}
 emit(n){for(const f of this.listeners[n]||[])f({stopPropagation(){},preventDefault(){},key:'Enter'});}
 pause(){this.paused=true;this.emit('pause');}
 play(){this.plays=(this.plays||0)+1;if(this.reject)return Promise.reject(Error('PRIVATE_ERROR'));if(this.pending)return new Promise(()=>{});this.paused=false;this.emit('play');this.emit('playing');return Promise.resolve();}
}
const mp3=()=>new Blob([Buffer.from([0x49,0x44,0x33,4,0,0,0,0,0,0,0xff,0xfb,0x90,0])],{type:'audio/mpeg'});
const response=(blob=mp3(),type=blob.type)=>({ok:true,headers:{get:n=>n==='Content-Type'?type:'1'},blob:async()=>blob});
const tick=()=>new Promise(r=>setTimeout(r,10));
function context(){let urls=0;const root=new Element();const h={console,Blob,Uint8Array,ArrayBuffer,AbortController,Promise,Error,JSON,Math,Date,isNaN,isFinite,parseFloat,setTimeout:(f,t)=>setTimeout(f,Math.min(t,50)),clearTimeout,document:{hidden:false,createTextNode:text=>({textContent:text}),createElement:t=>new Element(t)},URL:{createObjectURL:()=>`blob:synthetic-${++urls}`,revokeObjectURL(){}},nativeEpoch:0,voiceBars:[],companionVoiceUrls:[],VOICE_BLOB_KEEP:60,voiceTurn:null,replayAudio:null,replayingBar:null,activePlay:null,settings:{provider:'synthetic'},sendGeneration:0,EXPECTED_SCOPE:null,ttsBase:'synthetic',sessionId:'synthetic',TTS_FETCH_TIMEOUT_MS:1000,MSG_MAX_VOICE:12,ttsAvailable:true,chat:root,showEmotion(){},logSession(){},setTypingIndicator(){},fetch:async()=>response(),addBubble(){const b=new Element();const c=b.appendChild(new Element());c.className='bubble-content';root.appendChild(b);return b;},frame:{contentWindow:{document:{getElementById(){throw Error('IFRAME_MUST_NOT_BE_USED');}}}}};vm.createContext(h);vm.runInContext(functions,h);h.showEmotion=()=>{};h.logSession=()=>{};h.setTypingIndicator=()=>{};h.addBubble=()=>{const b=new Element();const c=b.appendChild(new Element());c.className='bubble-content';root.appendChild(b);return b;};h.urls=()=>urls;return h;}
function turn(h,msgs=['first','second']){const v={turn:1,msgs,blobs:[],durs:[],contents:[],bars:[],playIdx:0,playing:false,waiting:false,canceled:false,voiceCount:msgs.length,mode:'voice',emo:'neutral',generation:h.sendGeneration,profile:JSON.stringify(h.settings),scope:JSON.stringify(h.EXPECTED_SCOPE),requests:[]};h.voiceTurn=v;return v;}

const baseContext=context;
context=function(){const h=baseContext();Object.assign(h,{introAccepted:true,dataReadyPromise:null,dataReadyPhase:'idle',dataProgress:Object.create(null),dataProgressListeners:[],dataFailures:Object.create(null),contextLoaded:false,shards:[],shardStatus:{},knowledgePieces:Object.create(null)});return h;};
module.exports={context,turn,tick,Element,mp3,response};
