'use strict';
// Private-data DOM acceptance: local fulfillment only; never forwards a request.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
function canonical(v){if(Array.isArray(v))return '['+v.map(canonical).join(',')+']';if(v&&typeof v==='object')return '{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}';return JSON.stringify(v);}
function digest(v){return crypto.createHash('sha256').update(canonical(v),'utf8').digest('hex');}
const {chromium}=require(process.env.PLAYWRIGHT_CORE || require('node:path').join(require('node:os').homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright-core'));
const EDGE='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const ORIGIN='https://father-memory-test.invalid';
function check(ok,code){if(!ok){const e=new Error(code);e.safeCode=code;throw e;}}
function args(){const a=process.argv.slice(2);check((a.length===4||(a.length===6&&a[4]==='--context'))&&a[0]==='--site'&&a[2]==='--packet'&&path.isAbsolute(a[1])&&path.isAbsolute(a[3]),'absolute_site_packet_required');return {site:fs.realpathSync(a[1]),packet:fs.realpathSync(a[3]),context:a[5]};}
function load(site,rel){check(!rel.includes('..')&&!path.isAbsolute(rel),'unsafe_relative_file');const file=path.join(site,rel);const real=fs.realpathSync(file);check(real.toLowerCase().startsWith((site+path.sep).toLowerCase()),'linked_file_outside_site');check(fs.statSync(real).size<5000000,'file_too_large');return fs.readFileSync(real);}
function json(site,rel){return JSON.parse(load(site,rel));}
async function main(){
 const options=args(),site=options.site,packet=JSON.parse(fs.readFileSync(options.packet,'utf8')), contextPath=options.context||'data/chat_context.json';
 check(/^data\/chat_context[a-zA-Z0-9_.-]*\.json$/.test(contextPath)&&!contextPath.includes('..'),'safe_context_path');
 const contextData=json(site,contextPath);
 check(/^[0-9a-f]{64}$/.test(contextData.memory_release?.release_revision||''),'versioned_revision');
 const memoryPath='/data/memories-'+contextData.memory_release.release_revision+'.json',memory=json(site,memoryPath.slice(1));
 check(json(site,'data/memories.json').entries.length===0,'legacy_memory_not_empty');
 check(contextData.person==='mama'&&contextData.viewer==='father'&&contextData.relationship_id==='mama_father'&&contextData.language==='mandarin','scope_preflight');
 check(contextData.memory_release&&memory.release_revision===contextData.memory_release.release_revision,'release_preflight');
 const unsignedPacket={...packet};delete unsignedPacket.release_revision;
 check(digest(unsignedPacket)===packet.release_revision&&packet.release_revision===memory.release_revision,'trusted_packet_revision');
 check(canonical(packet.cards)===canonical(memory.entries),'packet_cards_mismatch');
 check(packet.cards.every(c=>canonical(c.provenance.sources)===canonical(memory.entries.find(e=>e.id===c.id).provenance.sources)),'full_sources_mismatch');
 const fourthSourceCard=memory.entries.findIndex(c=>c.provenance.sources.length>=4);check(fourthSourceCard>=0,'fourth_source_fixture_required');
 const chatSource=fs.readFileSync(path.join(__dirname,'../tools/build_chat_page.py'),'utf8');
 const chatFunctions=['scoreText','retrieveKnowledge'].map(n=>{const match=chatSource.match(new RegExp('^function '+n+'\\([^\\n]*\\) \\{.*?^\\}','ms'));check(match,'chat_function_missing');return match[0];}).join('\n');
 const vm=require('node:vm'),chatRuntime=vm.createContext({});vm.runInContext(chatFunctions,chatRuntime);
 for(const card of memory.entries)check(chatRuntime.retrieveKnowledge([card.title],[card],[],{}).memories.length===0,'unbound_chat_accepted_release');
 check(chatRuntime.retrieveKnowledge(['synthetic'],[{title:'synthetic',texts:['synthetic'],tier:1}],[],{}).memories.length===1,'legacy_tier1_regression');
 const html=load(site,'companion.html');
 check(/lang: 'mandarin', session_id: sessionId/.test(html.toString('utf8')),'mandarin_preserved');
 const shardPaths=new Set(contextData.message_shards.map(n=>{check(/^messages-\d{4}\.json$/.test(n),'shard_name');return '/data/'+n;}));
 const queryCases=['西餐','油条'].map(query=>({query,candidates:memory.entries.filter(c=>c.tier===2&&(c.title+' '+c.texts.join(' ')).includes(query))}));
 check(queryCases.every(x=>x.candidates.length),'query_cards_missing');
 const browser=await chromium.launch({executablePath:EDGE,headless:true,proxy:{server:'http://127.0.0.1:9',bypass:''},args:['--disable-background-networking','--disable-component-update','--disable-sync','--no-first-run','--disable-default-apps','--disable-features=MediaRouter,OptimizationHints','--host-resolver-rules=MAP * ~NOTFOUND','--proxy-bypass-list=<-loopback>']});
 let report={status:'pending',viewport:390,forwarded_requests:0,persisted_sessions:0,real_model_calls:0,raw_audio_reads:0,backend_e14_not_exercised:true,real_phone_not_tested:true,cases:[]};
 try{
  const scenarios=[...queryCases.map(item=>({kind:'positive',item})),...memory.entries.map(c=>({kind:'positive',item:{query:c.title+' '+c.texts[0],candidates:[c],card_id:c.id}})),...['tampered_body','tampered_scope','mixed_context','mixed_payload','fourth_id','fourth_timestamp','fourth_speaker','fourth_sha','source_count'].map(kind=>({kind}))];
  for(const scenario of scenarios){
   const kind=scenario.kind;
   let completions=0,sessionPosts=0,ttsRequests=0,unknownBlocked=0,wsBlocked=0,verifiedQueries=0;
   const ctx=await browser.newContext({viewport:{width:390,height:844},serviceWorkers:'block',acceptDownloads:false});
   check(typeof ctx.routeWebSocket==='function','websocket_block_unavailable');
   await ctx.routeWebSocket('**/*',ws=>{wsBlocked++;ws.close();});
   let currentQuery=null;
   await ctx.route('**/*',async route=>{
    try{
     const req=route.request(),u=new URL(req.url());
     if(u.origin!==ORIGIN){unknownBlocked++;return route.abort();}
     if(req.method()==='POST'&&u.pathname==='/v1/chat/completions'){
      completions++;
      check(kind==='positive'&&currentQuery,'unexpected_completion');
      const payload=req.postDataJSON();
      const finalContent=String(payload.messages.at(-1).content||'');
      check(finalContent.endsWith('\n\n'+currentQuery.query),'final_request_structure');
      const content=finalContent.slice(0,-currentQuery.query.length-2);
      check(content.length<=2200,'retrieval_budget');
      const found=currentQuery.candidates.find(c=>content.includes(c.texts[0])&&content.includes('record='+c.id)&&content.includes('release_id='+c.release_id)&&content.includes('source_count='+c.provenance.sources.length)&&content.includes('full_sources_digest='+digest(c.provenance.sources))&&content.includes('sources_EXCERPT='+c.provenance.sources.slice(0,3).map(ref=>ref.record_id).join(','))&&content.includes('source_snapshot_sha256='+c.provenance.source_sha256)&&content.includes('revision='+c.evidence_revision));
      check(found&&content.includes('mama_father')&&content.includes('[来源派生记忆 Tier-2；批量采用，非逐条人审]'),'request_evidence_missing');
      check(!content.includes('[家人确认记忆 Tier-1]'),'wrong_tier_label');
      verifiedQueries++;
      return route.fulfill({status:200,contentType:'text/event-stream',body:'data: '+JSON.stringify({choices:[{delta:{content:'合成验收回复。'}}]})+'\n\ndata: [DONE]\n\n'});
     }
     if(req.method()==='POST'&&u.pathname==='/session'){sessionPosts++;return route.fulfill({status:200,contentType:'application/json',body:'{"ok":true}'});}
     if(u.pathname.includes('sessions')&&req.method()==='GET')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({viewer:'father',sessions:[],recent_dates:[],last_card:null})});
     if(u.pathname==='/health'||u.pathname==='/tts'||u.pathname.startsWith('/tts/')){ttsRequests++;return route.fulfill({status:503,contentType:'application/json',body:'{"error":"synthetic offline TTS"}'});}
     if(req.method()!=='GET'){unknownBlocked++;return route.abort();}
     if(u.pathname==='/'+contextPath&&kind==='mixed_context'){
      const changed=JSON.parse(JSON.stringify(contextData));changed.memory_release.release_revision='0'.repeat(64);
      return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(changed)});
     }
     if(u.pathname===memoryPath){
      const m=JSON.parse(JSON.stringify(memory));
      if(kind==='tampered_body')m.entries[0].texts[0]+=' tampered';
      if(kind==='mixed_payload')m.release_revision='0'.repeat(64);
      if(kind==='tampered_scope')m.entries[0].relationship_id='mama_owner';
      if(kind.startsWith('fourth_')||kind==='source_count'){
       const c=m.entries[fourthSourceCard],ref=c.provenance.sources[3];
       if(kind==='fourth_id')ref.record_id+='changed';
       if(kind==='fourth_timestamp')ref.timestamp='1999-01-01T00:00:00+08:00';
       if(kind==='fourth_speaker')ref.speaker_id=ref.speaker_id==='mama'?'father':'mama';
       if(kind==='fourth_sha')ref.text_sha256='0'.repeat(64);
       if(kind==='source_count')c.provenance.sources.pop();
       const unsigned={...c};delete unsigned.evidence_revision;c.evidence_revision=digest(unsigned);
      }
      return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(m)});
     }
     let relative;
     if(['/companion.html','/avatar.html','/'+contextPath,'/data/transcripts.json'].includes(u.pathname)||shardPaths.has(u.pathname))relative=u.pathname.slice(1);
     else if(/^\/data\/avatar\/[a-zA-Z0-9_-]+\.(png|json)$/.test(u.pathname))relative=u.pathname.slice(1);
     else {unknownBlocked++;return route.abort();}
     const bytes=load(site,relative);
     const contentType=relative.endsWith('.html')?'text/html; charset=utf-8':relative.endsWith('.json')?'application/json': 'image/png';
     return route.fulfill({status:200,contentType,body:bytes});
    }catch(e){routeErrors.push(e.safeCode||'route_failure');await route.abort().catch(()=>{});}
   });
   const routeErrors=[];
   const page=await ctx.newPage();
   await page.goto(ORIGIN+'/companion.html',{waitUntil:'domcontentloaded'});
   if(await page.locator('#intro-ok').isVisible())await page.locator('#intro-ok').click();
   check(await page.evaluate(()=>isSecureContext&&!!crypto.subtle),'secure_crypto_unavailable');
   if(kind==='positive'){
    for(const item of [scenario.item]){
     currentQuery=item;
     const before=await page.locator('.bubble.subject .bubble-content').filter({hasText:'合成验收回复。'}).count();
     await page.locator('#input-text').fill(item.query);
     await page.locator('#send-btn').click();
     await page.waitForFunction(n=>Array.from(document.querySelectorAll('.bubble.subject .bubble-content')).filter(x=>x.textContent.includes('合成验收回复。')).length>n,before,{timeout:20000});
     check(routeErrors.length===0,'route_assertion_failed');
    }
    check(completions===1&&verifiedQueries===1,'completion_count');
   }else{
    currentQuery=queryCases[0];
    await page.locator('#input-text').fill(currentQuery.query);
    await page.locator('#send-btn').click();
    await page.waitForFunction(()=>Array.from(document.querySelectorAll('.bubble.notice')).some(e=>e.textContent.includes('关系资料暂时未能完整加载或校验')),{},{timeout:20000});
    check(completions===0,'failclosed_completion');
    check(await page.locator('#input-text').inputValue()===currentQuery.query,'input_not_preserved');
   }
   check(routeErrors.length===0,'route_error');
   check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'horizontal_overflow');
   report.cases.push({kind,card_id:scenario.item?.card_id||null,passed:true,completions,verified_queries:verifiedQueries,session_posts_intercepted:sessionPosts,tts_requests_stubbed:ttsRequests,unknown_requests_blocked:unknownBlocked,websockets_blocked:wsBlocked,secure_crypto:true,no_overflow:true});
   await ctx.close();
  }
  report.actual_cards_tested=memory.entries.length;report.unbound_chat_cards_rejected=memory.entries.length;report.legacy_tier1_preserved=true;report.all_full_sources_match_trusted_packet=true;report.status='passed';console.log(JSON.stringify(report));
 }finally{await browser.close();}
}
main().catch(e=>{console.log(JSON.stringify({status:'failed',code:e.safeCode||'browser_operation_failed',private_diagnostics_suppressed:true,forwarded_requests:0,persisted_sessions:0}));process.exitCode=1;});
