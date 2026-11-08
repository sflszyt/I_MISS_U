/* Synthetic-only multi-batch HTTP adapter over the existing recovery fixture. */
'use strict';
const http=require('node:http');
const {fixtureServer,makeFixture}=require('./mobile_review.spec.js');
const NEW='/review/batches/voice-pilot-20261023/';
async function batchesFixture(){
  const old=await fixtureServer(),fresh=await fixtureServer();
  old.state=makeFixture(true);fresh.state=makeFixture();
  fresh.state.tasks=fresh.state.tasks.slice(0,1);fresh.state.tasks[0].items=fresh.state.tasks[0].items.slice(0,12);
  fresh.state.drafts={ab:fresh.state.drafts.ab};fresh.state.latest_receipts={ab:null};
  delete fresh.state.drafts.ab.values.items.ab12;delete fresh.state.drafts.ab.values.items.ab13;
  fresh.state.package_revision='synthetic-new-package-v1';
  const batches=[{id:'default',title:'既有三项评测',base_path:'/review/'},{id:'voice-pilot-20261023',title:'新训练声音试听 · 12 组',base_path:NEW}];
  for(const [fixture,batch]of [[old,batches[0]],[fresh,batches[1]]]){
    fixture.state.batch=batch;fixture.state.batches=batches;
    for(const task of fixture.state.tasks)for(const item of task.items)for(const key of ['audio','audio_a','audio_b'])if(item[key])item[key]=item[key].replace('/review/',batch.base_path);
  }
  const fixture={old,fresh,batches,requests:[],sessionFailure:false};
  const server=http.createServer((req,res)=>{
    fixture.requests.push(req.url);
    if(fixture.sessionFailure&&req.url.endsWith('/api/session')){res.writeHead(401,{'Content-Type':'application/json'});res.end(JSON.stringify({error:{message:'请重新登录'}}));return;}
    const selected=req.url.startsWith(NEW)?fresh:old;
    const url=new URL(req.url.startsWith(NEW)?req.url.replace(NEW,'/review/'):req.url,selected.url);
    const upstream=http.request(url,{method:req.method,headers:req.headers},response=>{res.writeHead(response.statusCode,response.headers);response.pipe(res);});
    upstream.on('error',()=>res.destroy());req.pipe(upstream);
  });
  await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});
  fixture.origin=`http://127.0.0.1:${server.address().port}`;
  fixture.close=async()=>{await new Promise(resolve=>server.close(resolve));await old.close();await fresh.close();};
  return fixture;
}
module.exports={batchesFixture,NEW};
