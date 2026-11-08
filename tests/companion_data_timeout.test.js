const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const src=fs.readFileSync(process.argv[2],'utf8');
const code=src.slice(src.indexOf('var scopeError = false;'),src.indexOf('function checkScope('));
async function scenario(body,noAbort){
 let calls=0,release=[];
 const s={setTimeout:(f,n)=>setTimeout(f,n===15000?20:n),clearTimeout,fetch:()=>{calls++;const wait=new Promise(r=>release.push(r));return body?Promise.resolve({ok:true,json:()=>wait}):wait;}};
 if(!noAbort)s.AbortController=AbortController;
 vm.createContext(s);vm.runInContext(code,s);
 const jobs=Array.from({length:33},(_,i)=>s.fetchDataJson('u'+i,'SHARD_'+i));
 const all=Promise.allSettled(jobs);
 const result=await Promise.race([all,new Promise(r=>setTimeout(()=>r('HANG'),120))]);
 assert.notEqual(result,'HANG','all queued requests must settle');
 assert.equal(result.filter(x=>x.status==='rejected').length,33);
 assert.equal(s.dataFailures.SHARD_0,body?'BODY_TIMEOUT':'FETCH_TIMEOUT');
 await assert.rejects(s.fetchDataJson('u0','SHARD_0'));await assert.rejects(s.fetchDataJson('new','NEW'));
 assert.equal(calls,4,'no overlap while expired transports remain');
 release.forEach(r=>r(body?{}:{ok:true,json:()=>Promise.resolve({})}));
 await new Promise(r=>setTimeout(r,5));
 s.fetch=()=>{calls++;return Promise.resolve({ok:true,json:()=>Promise.resolve({fresh:true})});};
 assert.equal((await s.fetchDataJson('u0','SHARD_0')).fresh,true);
 console.log('PASS '+(body?'body':'headers')+' timeout, queued rejection, late isolation, retry; noAbort='+noAbort);
}
(async()=>{for(const b of [false,true])for(const n of [false,true])await scenario(b,n);})().catch(e=>{console.error(e);process.exitCode=1;});
