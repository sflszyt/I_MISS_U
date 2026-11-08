const assert=require('assert/strict');
// Exercise the generated opt-in page, not the unchanged default template.
if (!process.argv[2]) {
 const fs=require('fs'),os=require('os'),path=require('path'),{spawnSync}=require('child_process');
 const temp=fs.mkdtempSync(path.join(os.tmpdir(),'companion-defaults-'));
 const result=spawnSync('python',['-X','utf8','-c',"from tools.build_companion_page import build; print(build('synthetic', '.', 'father', reset_ui_prefs=True))"],{cwd:path.resolve(__dirname,'..'),encoding:'utf8'});
 assert.equal(result.status,0,result.stderr);
 process.argv[2]=path.join(temp,'companion.html');fs.writeFileSync(process.argv[2],result.stdout);
 process.on('exit',()=>{fs.unlinkSync(process.argv[2]);fs.rmdirSync(temp);});
}
const {context,Element}=require('./companion_voice_harness');
for (const old of [null, '{"voiceText":false,"autoVoiceEnabled":false}']) {
const h=context(), drawer=new Element();
h.AUTO_VOICE_SESSION=true;h.AUTO_VOICE_CUE='cue';h.document.body=new Element();
h.document.getElementById=id=>id==='drawer'?drawer:null;
h.document.createElement=t=>{const a=new Element(t);a.setAttribute=()=>{};a.load=()=>{};return a;};
let writes=0;
h.localStorage={getItem:()=>old,setItem:()=>writes++};h.uiPrefsKey='prefs';
h.pageUiPrefs={voiceText:true,autoVoiceEnabled:true};h.showVoiceText=true;h.cfgVoiceText={checked:true};
h.loadUiPrefs();const s=h.initAutoVoiceSession();
assert.equal(s.enabled,true,'page defaults must ignore previous stored auto voice off');
assert.equal(h.showVoiceText,true);assert.equal(s.ready,false);assert.equal(s.job,null);
s.checkbox.checked=false;s.checkbox.emit('change');h.cfgVoiceText.checked=false;h.onVoiceTextToggle();
h.loadUiPrefs();assert.equal(s.enabled,false);assert.equal(h.showVoiceText,false);assert.equal(writes,0);
}
console.log('PASS page defaults ignore storage; same-page choices survive repeated loading; no writes or audio activation');
