const fs=require('fs'),path=require('path'),http=require('http'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_CORE || require('node:path').join(require('node:os').homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright-core'));
const root=path.resolve(process.argv[2]),output=path.resolve(process.argv[3]);
let source=fs.readFileSync(path.join(root,'companion.html'),'utf8');
assert(source.includes('var archiveOptions ='));
source=source.replace('var archiveOptions =',`window.ownershipState=()=>({pending:sendPending,streaming,history:history.length,ready:voiceTurn&&voiceTurn.bars.length&&voiceTurn.bars.every(b=>!!b._voiceBlob)});var archiveOptions =`);
const wav=Buffer.alloc(3244);wav.write('RIFF');wav.writeUInt32LE(wav.length-8,4);wav.write('WAVEfmt ',8);wav.writeUInt32LE(16,16);wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);wav.writeUInt32LE(8000,24);wav.writeUInt32LE(16000,28);wav.writeUInt16LE(2,32);wav.writeUInt16LE(16,34);wav.write('data',36);wav.writeUInt32LE(wav.length-44,40);
let run;
const server=http.createServer((req,res)=>{const p=new URL(req.url,'http://local').pathname;const json=x=>{res.setHeader('Content-Type','application/json');res.end(JSON.stringify(x));};
 if(p==='/companion.html'){res.setHeader('Content-Type','text/html');return res.end(source);}
 if(p==='/avatar.html')return res.end('<html></html>');
 if(p==='/cdn-cgi/access/get-identity')return json({account_id:'a'.repeat(32),user_uuid:'11111111-1111-4111-8111-111111111111'});
 if(p==='/health')return json({status:'ok',model_loaded:true});
 if(p==='/data/sessions_father.json')return json({viewer:'father',sessions:[]});
 if(p.startsWith('/data/')){const f=path.join(root,p);if(fs.existsSync(f))return res.end(fs.readFileSync(f));res.statusCode=404;return json({});}
 if(req.method==='POST'){let body='';req.on('data',b=>body+=b);req.on('end',()=>{const item={path:p,body:JSON.parse(body)};run.posts.push(item);
  if(p==='/v1/chat/completions'){const n=run.posts.filter(x=>x.path===p).length;if(run.failSecond&&n===2){res.statusCode=503;return json({error:'synthetic'});}const finish=()=>{res.setHeader('Content-Type','text/event-stream');res.end('data: '+JSON.stringify({choices:[{delta:{content:'Synthetic reply '+n+'.'}}]})+'\n\ndata: [DONE]\n\n');};if(run.hold)run.held.push(finish);else finish();return;}
  if(p==='/tts'){res.setHeader('Content-Type','audio/wav');res.setHeader('X-Duration-Seconds','0.2');return res.end(wav);}return json({ok:true});});return;}res.statusCode=404;json({});});
(async()=>{await new Promise(r=>server.listen(0,'127.0.0.1',r));const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'}),origin='http://127.0.0.1:'+server.address().port,report={cases:[]};
try{for(const name of ['previous-audio-after-success','previous-audio-after-failure','duplicate-enter-fast','doubleclick-fast','single-stop']){
 run={posts:[],held:[],hold:name.includes('fast')||name==='single-stop',failSecond:name.endsWith('failure')};const record={name};report.cases.push(record);
 const ctx=await browser.newContext(),page=await ctx.newPage();let errors=[],external=[];page.setDefaultTimeout(10000);page.on('pageerror',e=>errors.push(String(e)));await ctx.route('**/*',r=>new URL(r.request().url()).origin===origin?r.continue():(external.push(r.request().url()),r.abort()));
 await page.addInitScript(()=>{window.replayEvents=[];document.addEventListener('play',e=>replayEvents.push(e.target.src),true);});
 try{await page.goto(origin+'/companion.html');await page.locator('#intro-ok').click();await page.waitForFunction(()=>document.querySelector('#intro-enter')&&!document.querySelector('#intro-enter').disabled);await page.locator('#intro-enter').click();
 await page.locator('#input-text').fill('First question');
 if(name==='doubleclick-fast')await page.locator('#send-btn').dblclick({delay:200});
 else {await page.locator('#send-btn').click();if(run.hold){await page.waitForFunction(()=>ownershipState().streaming);if(name==='duplicate-enter-fast')await page.locator('#input-text').press('Enter');if(name==='single-stop')await page.locator('#send-btn').click();}}
 if(run.hold){await page.waitForTimeout(100);assert.equal(run.posts.filter(x=>x.path==='/v1/chat/completions').length,1);if(name==='single-stop'){assert.equal(await page.locator('.send-failed').count(),1);assert.equal(await page.evaluate(()=>ownershipState().history),0);}else{assert.equal(await page.evaluate(()=>ownershipState().streaming),true,'duplicate must not cancel');run.held.splice(0).forEach(f=>f());await page.waitForFunction(()=>ownershipState().history===2);assert.equal(await page.locator('.send-failed').count(),0);}}
 else {await page.waitForFunction(()=>ownershipState().ready);await page.waitForTimeout(350);const first=page.locator('.voice-bar').first();await first.evaluate(n=>n.dataset.firstAudio='yes');const src=await first.evaluate(n=>n._voiceObjectUrl);assert(src);const before=await page.evaluate(src=>replayEvents.filter(x=>x===src).length,src);
 await page.locator('#input-text').fill('Second question');await page.locator('#send-btn').click();if(run.failSecond)await page.waitForFunction(()=>document.querySelector('.send-failed'));else await page.waitForFunction(()=>ownershipState().history===4&&ownershipState().ready);await page.waitForTimeout(350);
 assert.equal(await page.evaluate(src=>replayEvents.filter(x=>x===src).length,src),before,'old audio must not autoplay after B');await first.click();await page.waitForTimeout(100);assert.equal(await page.evaluate(src=>replayEvents.filter(x=>x===src).length,src),before+1,'A must remain manually playable after B');record.firstAudioReplay=true;
 const tts=run.posts.filter(x=>x.path==='/tts');assert(tts.some(x=>x.body.turn===1));if(!run.failSecond)assert(tts.some(x=>x.body.turn===2));record.ttsTurns=tts.map(x=>x.body.turn);}
 assert.deepEqual(errors,[]);assert.deepEqual(external,[]);record.pass=true;
 }catch(e){record.error=e.stack;process.exitCode=1;}finally{record.posts=run.posts;record.errors=errors;await ctx.close();}
 }report.pass=report.cases.every(x=>x.pass);}finally{fs.writeFileSync(output,JSON.stringify(report,null,2));console.log(JSON.stringify(report));await browser.close();server.closeAllConnections();server.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
