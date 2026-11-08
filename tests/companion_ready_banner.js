const assert=require('node:assert/strict'),vm=require('vm'),fs=require('fs');
const html=fs.readFileSync(process.argv[2],'utf8').replace(/\r\n/g,'\n');
const start=html.indexOf("(function(){\n  var card = document.getElementById('intro-card');");
const code=html.slice(start,html.indexOf('})();',start)+5);
function scenario(phase,early){
 const nodes={};function node(){return {hidden:false,isConnected:true,textContent:'',addEventListener(k,f){this[k]=f;},setAttribute(){},appendChild(){},querySelector(){return node();}};}
 for(const id of ['intro-card','intro-ok','intro-preparing','intro-progress','intro-retry','intro-enter','intro-notice','chat'])nodes[id]=node();
 nodes['intro-card'].parentNode={removeChild(n){n.isConnected=false;}};nodes.chat.parentNode={insertBefore(n){nodes[n.id]=n;}};
 let listener;const c={document:{getElementById:id=>nodes[id],createElement:node},introAccepted:false,dataReadyPhase:phase,subscribeDataProgress(f){listener=f;f({phase});},dataProgressText:p=>p.phase,ensureDataReady(){}};
 vm.runInNewContext(code,c);nodes['intro-ok'].click();
 if(early){nodes['intro-enter'].click();assert.equal(nodes['preparation-banner'].hidden,true,'routine preparation stays hidden after early entry');}
 c.dataReadyPhase='ready';listener({phase:'ready'});
 if(!early)nodes['intro-enter'].click();
 assert.equal(nodes['preparation-banner'].hidden,true,'ready banner must be hidden');
 listener({phase:'ready'});assert.equal(nodes['preparation-banner'].hidden,true,'redraw stays hidden');
 listener({phase:'failed'});assert.equal(nodes['preparation-banner'].hidden,false);assert.equal(nodes['preparation-banner'].isConnected,true);
 listener({phase:'loading'});assert.equal(nodes['preparation-banner'].hidden,true,'retry preparation stays hidden');
 listener({phase:'ready'});assert.equal(nodes['preparation-banner'].hidden,true);
}
scenario('loading',true);scenario('ready',false);console.log('PASS ready transitions, ready entry, redraw, failure and loading');
