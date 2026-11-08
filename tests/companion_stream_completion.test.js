const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict'),test=require('node:test');
const source=fs.readFileSync(__dirname+'/../tools/build_companion_page.py','utf8');
const shared=fs.readFileSync(__dirname+'/../tools/build_chat_page.py','utf8');
const funcs=s=>[...s.matchAll(/^function \w+\([^\n]*\) \{.*?^\}/gms)].map(m=>m[0]).join('\n');
function setup(chunks,options={}) {
 let reads=0,cancels=0,releases=0,done=[],errors=[],deltas=[];
 const reader={read(){reads++;if(chunks.length){const x=chunks.shift();if(x instanceof Error)return Promise.reject(x);return Promise.resolve({value:typeof x==='string'?Buffer.from(x):x,done:false});}return options.hold?new Promise(()=>{}):Promise.resolve({done:true});},cancel(){cancels++;return new Promise(()=>{});},releaseLock(){releases++;}};
 const h={AbortController,TextDecoder,Promise,JSON,console,EXPECTED_SCOPE:null,settings:{url:'https://synthetic.invalid',key:'synthetic',model:'synthetic',provider:options.provider||'openai'},sendBtn:{classList:{add(){}}},fetch:async()=>({ok:options.status?false:true,status:options.status||200,headers:{get:()=>options.mime||'text/event-stream'},body:{getReader:()=>reader},text:async()=> 'PRIVATE_BODY_SENTINEL'}),settingsComplete:()=>true};
 vm.createContext(h);vm.runInContext(funcs(shared)+'\n'+funcs(source).replace('__LLM_PROXY_BRANCH__',''),h);h.settingsComplete=()=>true;
 h.streamRequest([],x=>deltas.push(x),(s,a)=>done.push([s,a]),e=>errors.push(e));
 return {h,done,errors,deltas,stats:()=>({reads,cancels,releases})};
}
const tick=()=>new Promise(r=>setTimeout(r,25));
const delta='data: {"choices":[{"delta":{"content":"hello"}}]}\n\n';
test('DONE settles without EOF or waiting for cancel',async()=>{const t=setup([delta+'data: [DONE]\n\n'],{hold:true});await tick();assert.equal(t.done.length,1);assert.equal(t.stats().reads,1);assert.equal(t.stats().cancels,1);assert.equal(t.stats().releases,1);});
test('premature EOF never completes partial',async()=>{const t=setup([delta]);await tick();assert.equal(t.done.length,0);assert.equal(t.errors.length,1);});
test('multiline frame and split UTF8 final DONE',async()=>{const b=Buffer.from('data: {"choices":\r\ndata: [{"delta":{"content":"你好"}}]}\r\n\r\ndata: [DONE]');const n=b.indexOf(Buffer.from('你'))+1;const t=setup([b.subarray(0,n),b.subarray(n)]);await tick();assert.equal(t.done[0]?.[0],'你好');});
test('HTTP diagnostics never echo upstream',async()=>{const t=setup([],{status:403});await tick();assert.equal(t.errors.length,1);assert.match(t.errors[0],/^LLM_HTTP_403$/);});
test('complete JSON fallback',async()=>{const t=setup(['{"choices":[{"message":{"content":"json"}}]}'],{mime:'application/json'});await tick();assert.equal(t.done[0]?.[0],'json');});
test('reader error does not complete partial',async()=>{const t=setup([delta,Error('PRIVATE_ERROR')]);await tick();assert.equal(t.done.length,0);assert.equal(t.errors[0],'LLM_READ');});
module.exports={setup,tick,delta};
// Additional protocol boundaries: all bytes synthetic, no network.
test('CRLF split and trailing data after DONE ignored',async()=>{const t=setup([delta.replaceAll('\n','\r\n').slice(0,-1),'\n'+'data: [DONE]\r','\n\r\ndata: INVALID\n\n'],{hold:true});await tick();assert.equal(t.done[0]?.[0],'hello');assert.equal(t.errors.length,0);assert.equal(t.stats().reads,3);});
test('malformed SSE must fail even when followed by DONE',async()=>{const t=setup([delta+'data: NOT_JSON\n\ndata: [DONE]\n\n']);await tick();assert.equal(t.done.length,0);assert.equal(t.errors[0],'LLM_PROTOCOL');});
test('HTML and invalid JSON never complete',async()=>{for(const mime of ['text/html','application/json']){const t=setup(['<html>PRIVATE</html>'],{mime});await tick();assert.equal(t.done.length,0);assert.equal(t.errors.length,1);assert(!t.errors[0].includes('PRIVATE'));}});
test('Anthropic semantic stop settles held socket',async()=>{const t=setup(['event: content_block_delta\ndata: {"type":"content_block_delta","delta":{"type":"text_delta","text":"anthropic"}}\n\nevent: message_stop\ndata: {"type":"message_stop"}\n\n'],{provider:'anthropic',hold:true});await tick();assert.equal(t.done[0]?.[0],'anthropic');assert.equal(t.stats().reads,1);});
test('explicit cancel settles once even if read remains pending',async()=>{const t=setup([delta],{hold:true});await tick();t.h.controller.abort();await tick();assert.deepEqual(t.done,[['hello',true]]);assert.equal(t.errors.length,0);});
test('network AbortError is read failure, not user cancellation',async()=>{const e=Error('PRIVATE');e.name='AbortError';const t=setup([delta,e]);await tick();assert.equal(t.done.length,0);assert.equal(t.errors[0],'LLM_READ');});
test('empty SSE/Anthropic and whitespace JSON reject with EMPTY',async()=>{
 for(const [chunks,options] of [[['data: [DONE]\n\n'],{}],[['data: {"type":"message_stop"}\n\n'],{provider:'anthropic'}],[['{"choices":[{"message":{"content":"  \\n "}}]}'],{mime:'application/json'}]]){
  const t=setup(chunks,options);await tick();assert.equal(t.done.length,0);assert.equal(t.errors[0],'LLM_EMPTY');
 }
});
test('held rejected bodies cancelled without waiting or leaking rejection; next request independent',async()=>{
 for(const status of [403,200])for(const rejectCancel of [false,true]){
  const t=setup([],{hold:true});await tick();t.h.controller.abort();let cancelled=0,errors=[],done=[];
  t.h.fetch=async()=>({ok:status===200,status,headers:{get:()=> 'text/html'},body:{cancel(){cancelled++;return rejectCancel?Promise.reject(Error('PRIVATE_CANCEL')):new Promise(()=>{});}}});
  t.h.streamRequest([],()=>{},(...x)=>done.push(x),e=>errors.push(e));await tick();assert.equal(cancelled,1);assert.deepEqual(errors,[status===403?'LLM_HTTP_403':'LLM_MIME']);assert.equal(done.length,0);
  const oldController=t.h.controller;
  t.h.fetch=async()=>new Response(new ReadableStream({start(c){c.enqueue(Buffer.from(delta+'data: [DONE]\n\n'));}}),{headers:{'Content-Type':'text/event-stream'}});
  t.h.streamRequest([],()=>{},(...x)=>done.push(x),e=>errors.push(e));oldController.abort();await tick();assert.equal(done.length,1);assert.equal(done[0][0],'hello');assert.equal(t.h.controller.signal.aborted,false);assert.equal(errors.length,1);
 }
});
