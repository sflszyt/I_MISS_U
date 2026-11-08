// Real Edge DOM/layout, synthetic only. No HTTP server or external requests.
const fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_CORE||require('node:path').join(require('node:os').homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright-core'));
const source=fs.readFileSync(path.join(__dirname,'../tools/build_companion_page.py'),'utf8');
const names=['displayGroupHtml','voiceBarHtml','showTextMsg','renderGroupedHistory','historyVoiceEntries','paragraphSpeech','continuedSpeechQuotes','completedSpeechLine','overtSpeechQuestion'];
const functions=[...source.matchAll(/^function (\w+)\([^\n]*\) \{.*?^\}/gms)].filter(m=>names.includes(m[1])).map(m=>m[0]).join('\n');
const example='疑似还不是确诊，先勿要自己吓自己。尽快带着检查报告去看甲状腺外科或内分泌科，让医生看看要不要做穿刺。\n\n侬是做了什么检查，说疑似的？';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.EDGE_EXE||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{
  const ctx=await browser.newContext();await ctx.route('**/*',r=>r.abort());
  const page=await ctx.newPage(),errors=[];page.on('pageerror',e=>errors.push(String(e)));
  const results=[];
  for(const width of [320,390,900]){
   await page.setViewportSize({width,height:1100});
   await page.setContent('<meta charset="utf-8"><style>body{margin:16px;background:#141414;color:#eee;font:16px/1.6 sans-serif}.bubble-content{white-space:pre-wrap;word-wrap:break-word;background:#303030;padding:12px;margin:8px 0}.voice-text{white-space:pre-wrap;word-wrap:break-word}.voice-bar{background:#52745b}h3{margin:10px 0;font-size:16px}</style><main id="chat"></main>');
   await page.addScriptTag({content:functions});
   const result=await page.evaluate(text=>{
    window.VOICE_GROUPS=true;window.chat=document.querySelector('#chat');window.SESSIONS_BASE='synthetic/';
    window.showEmotion=()=>{};window.wireHistoryBar=bar=>{bar.dataset.savedAudio=bar._voiceUrl||'';};
    window.addBubble=()=>{const b=document.createElement('section');b.innerHTML='<div class="bubble-content"></div>';chat.append(b);return b;};
    const heading=t=>{const h=document.createElement('h3');h.textContent=t;chat.append(h);};
    heading('Live text');const live=addBubble().firstChild;window.takePending=()=>live;
    showTextMsg({msgs:[text],firstShown:false,emo:'neutral'},0);
    heading('Voice transcript / replay');const voice=addBubble().firstChild;voice.innerHTML=voiceBarHtml(text,4);
    heading('Restored history');renderGroupedHistory(text,[{text,file:'audio/legacy.wav',dur:4}]);
    const history=chat.lastChild.firstChild;
    const same=[live.textContent,voice.querySelector('.voice-text').textContent,history.querySelector('.voice-text').textContent];
    const boxes=[live,voice,history].map(e=>e.querySelectorAll('.display-chunk').length);
    const audio=history.querySelector('.voice-bar').dataset.savedAudio;
    heading('Real paragraphs, mixed Latin, escaping');const raw='“保留段落。”\r\n\r\nTSH 2.5 mIU/L & <report>\n下一行。';const extra=addBubble().firstChild;extra.innerHTML=displayGroupHtml(raw);
    const range=document.createRange();range.selectNodeContents(live.querySelector('.display-chunk'));
    return {same,boxes,audio,width:innerWidth,rects:range.getClientRects().length,overflow:document.documentElement.scrollWidth>innerWidth,paragraphText:extra.textContent};
   },example);
   assert.deepEqual(result.same,[example,example,example]);assert.deepEqual(result.boxes,[1,1,1]);
   assert.equal(result.audio,'synthetic/audio/legacy.wav');assert.equal(result.overflow,false);
   assert.equal(result.paragraphText,'“保留段落。”\n\nTSH 2.5 mIU/L & <report>\n下一行。');
   assert(result.rects>1);results.push(result);
   await page.screenshot({path:path.join(__dirname,`../evidence/lines-${width}.png`),fullPage:true});
  }
  assert.deepEqual(errors,[]);assert(results[0].rects>results[2].rects);
  console.log(JSON.stringify({browser:'Edge',network:'all requests blocked',results},null,2));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
