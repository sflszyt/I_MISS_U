const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict'),test=require('node:test'),{webcrypto}=require('crypto');
const source=fs.readFileSync(__dirname+'/../tools/build_companion_page.py','utf8');
const funcs=[...source.matchAll(/^function \w+\([^\n]*\) \{.*?^\}/gms)].map(m=>m[0]).join('\n').replace('__LLM_PROXY_BRANCH__','');
const tick=()=>new Promise(r=>setTimeout(r,20));
test('proxy diagnostic is bounded per attempt and HTML/error secrets never escape',async()=>{
 const logs=[],errors=[];const h={crypto:webcrypto,Uint8Array,AbortController,TextDecoder,Promise,JSON,console:{info:(...x)=>logs.push(x)},fetch:async()=>new Response('SECRET_BODY',{status:520,headers:{'CF-Ray':'0123456789abcdef-LHR','X-Request-ID':'<script>SECRET</script>'}})};
 vm.createContext(h);vm.runInContext(funcs,h);
 assert.equal(typeof h.newRequestDiagnostic,'function');
 const a=h.newRequestDiagnostic(),b=h.newRequestDiagnostic();assert.match(a.request_id,/^[a-f0-9]{32}$/);assert.notEqual(a.request_id,b.request_id);
 h.companionStream('/proxy',{}, {},'openai',new AbortController(),()=>{},()=>{},e=>errors.push(e),a);await tick();
 assert.match(errors[0],/LLM_HTTP_520/);assert(errors[0].includes(a.request_id));assert(errors[0].includes('0123456789abcdef-LHR'));assert(!JSON.stringify(logs).includes('SECRET'));assert(!errors[0].includes('SECRET'));
});
test('late response and old cancellation retain independent attempt metadata',async()=>{
 const logs=[],done=[],errors=[],pending=[];const h={crypto:webcrypto,Uint8Array,AbortController,TextDecoder,Promise,JSON,console:{info:(...x)=>logs.push(x)},fetch:()=>new Promise(resolve=>pending.push(resolve))};vm.createContext(h);vm.runInContext(funcs,h);
 const a=h.newRequestDiagnostic(),b=h.newRequestDiagnostic(),ca=new AbortController(),cb=new AbortController();
 h.companionStream('/proxy',{}, {},'openai',ca,()=>{},(...x)=>done.push(x),e=>errors.push(e),a);await tick();ca.abort();
 h.companionStream('/proxy',{}, {},'openai',cb,()=>{},(...x)=>done.push(x),e=>errors.push(e),b);await tick();
 pending[0](new Response('SECRET_OLD',{status:520,headers:{'CF-Ray':'0123456789abcdef-LHR'}}));
 pending[1](new Response('data: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n',{headers:{'Content-Type':'text/event-stream'}}));await tick();
 assert.equal(logs.length,2);assert.equal(logs[0][1].request_id,a.request_id);assert.equal(logs[0][1].stage,'CANCELLED');assert.equal(logs[1][1].request_id,b.request_id);assert.equal(logs[1][1].stage,'COMPLETE');assert.equal(errors.length,0);assert.equal(done.length,2);assert(!JSON.stringify(logs).includes('SECRET'));
});
test('malformed metadata is dropped and diagnostics remain under session detail limit',()=>{
 const logs=[];const h={console:{info:(...x)=>logs.push(x)}};vm.createContext(h);vm.runInContext(funcs,h);
 for(const value of ['<script>SECRET</script>','a'.repeat(10000),'\r\nSECRET']){
  assert.equal(h.requestDiagnosticText({request_id:value},'FETCH'),'');
  const out=h.requestDiagnosticText({request_id:'a'.repeat(32),proxy_id:value,cf_ray:value,status:value},value);assert(out.length<500);assert(!out.includes('SECRET'));assert.equal(Object.keys(logs.at(-1)[1]).join(','),'request_id');
 }
});
