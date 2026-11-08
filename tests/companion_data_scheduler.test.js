const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const src=fs.readFileSync(process.argv[2],'utf8');
const code=src.slice(src.indexOf('var scopeError = false;'),src.indexOf('function checkScope('));
let active=0,peak=0;const order=[];
const s={setTimeout:(fn,ms)=>setTimeout(fn,ms===15000?60:ms),clearTimeout,AbortController,fetch:(url)=>{order.push(url);active++;peak=Math.max(peak,active);return Promise.resolve({ok:true,json:()=>new Promise(r=>setTimeout(()=>{active--;r({});},active>4?100:10))});}};
vm.createContext(s);vm.runInContext(code,s);
(async()=>{const jobs=Array.from({length:31},(_,i)=>s.fetchDataJson('shard'+i,'SHARD_'+i));jobs.push(s.fetchDataJson('memory','MEMORY'));const results=await Promise.allSettled(jobs);assert.equal(results.filter(r=>r.status==='rejected').length,0);assert(peak<=4,'bounded network concurrency');assert(order.indexOf('memory')<=4,'memory queued priority');console.log('PASS 31 shards + memory under constrained transport; peak='+peak);})().catch(e=>{console.error(e);process.exitCode=1;});
