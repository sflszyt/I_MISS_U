'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const labels = {unset:'未选择',confirm:'确认',correct:'纠正',reject:'拒绝',defer:'暂缓'};
  const statuses = {unknown:'未知',unverified:'未核实',verified:'已核实',missing:'缺失'};
  const fields = {date:'日期',source_id:'来源编号',boundary:'上下文范围',candidate:'记忆候选（待确认）',original_text:'原始文字',machine_asr:'机器转写（不等同沪语原句）',verbatim_wu:'沪语逐字稿',mandarin_gloss:'普通话释义',inference:'推断（不是事实）',speaker:'说话人',language:'语言',text_review_status:'助手文字 / 上下文读审状态',listening_status:'原音复听状态（与文字读审分开）',asr_status:'机器转写核实状态',wu_status:'沪语逐字稿核实状态',gloss_status:'释义核实状态'};
  let session, decisions, busy=false, pending=null, locked=false, position=0, dirty=false;
  function node(tag,text,cls){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;}
  function notify(text){$('message').textContent=text;}
  function complete(){return Object.values(decisions||{}).every(d=>d.status!=='unset'&&(d.status!=='correct'||d.correction.trim()));}
  function controls(){
    $('save').disabled=!session||busy||locked;
    $('submit').disabled=!session||busy||locked||!complete();
    $('reload').disabled=busy;
    $('previous').disabled=!session||busy||!!pending||position===0;
    $('next').disabled=!session||busy||!!pending||position>=session.items.length-1;
    $('position').textContent=session?`${position+1} / ${session.items.length}`:'';
    document.querySelectorAll('input,textarea').forEach(e=>{e.disabled=!session||busy||locked||!!pending;});
    const list=Object.values(decisions||{});$('progress').textContent=`已选择 ${list.filter(d=>d.status!=='unset').length} / ${list.length} · 暂缓 ${list.filter(d=>d.status==='defer').length}`;
  }
  async function api(path,options={}){const response=await fetch(path,{cache:'no-store',...options});if(!response.ok){const error=new Error('request failed');error.status=response.status;throw error;}return response.json();}
  function showReceipt(receipt){
    const panel=$('receipt');panel.replaceChildren();panel.hidden=!receipt;if(!receipt)return;
    panel.append(node('h2',receipt.fully_confirmed?'已提交：候选全部确认或纠正':'已提交：仍有拒绝或待解决项'));
    panel.append(node('p',`确认 ${receipt.counts.confirm} · 纠正 ${receipt.counts.correct} · 拒绝 ${receipt.counts.reject} · 暂缓 ${receipt.counts.defer} · 未选 ${receipt.counts.unset}`));
    panel.append(node('p',`缺源 / 原音未核实：${receipt.evidence_unresolved} 项。你的文字决定不会改变此状态。`,'warning'));
    panel.append(node('p',`审核人：${receipt.reviewer}`),node('p',`回执：${receipt.id}`),node('p',`时间：${receipt.submitted_at}`),node('p','这是审核记录，未更新正式记忆或训练数据。'));
    const a=node('a','查看原始回执 JSON');a.href='api/receipts/'+receipt.id;panel.append(a);
  }
  function render(){
    $('items').replaceChildren();locked=!!session.receipt;showReceipt(session.receipt);
    [session.items[position]].forEach(item=>{
      const index=position;
      const card=node('article');card.append(node('h2',`${index+1}. ${item.kind==='audio'?'语音候选':item.kind==='missing-source'?'缺失来源':'文字候选'}`));
      card.append(node('p',`${item.date} · 编号 ${item.id}`));
      if(item.kind==='missing-source')card.append(node('p','原始来源缺失；文字决定不能确认不存在的原音。','warning'));
      else if((item.kind==='audio'||item.audio)&&item.listening_status!=='verified')card.append(node('p','原音复听未完成；不能视为助手已核实。','warning'));
      card.append(node('p',`助手文字 / 上下文读审：${statuses[item.text_review_status]}`));
      const main=node('dl'),detail=node('dl');
      const primary=new Set(item.kind==='audio'?['candidate','machine_asr','verbatim_wu','mandarin_gloss']:['candidate','original_text']);
      for(const [key,title]of Object.entries(fields)){
        const target=primary.has(key)?main:detail;
        const value=key.endsWith('_status')?statuses[item[key]]:(['speaker','language'].includes(key)&&item[key]==='unknown'?'未知':item[key]);
        target.append(node('dt',title),node('dd',value||'尚无内容 / 未核实'));
      }
      card.append(main);const details=node('details');details.append(node('summary','查看来源、上下文与详细核实状态'),detail);card.append(details);
      if(item.audio){const audio=node('audio');audio.controls=true;audio.preload='none';audio.src='audio/'+item.audio+'.wav';audio.setAttribute('aria-label','播放对应原声');card.append(audio);}
      const fs=node('fieldset');fs.append(node('legend','对候选 / 转写文字的决定（不改变原音状态）'));
      const correction=node('textarea');correction.maxLength=4000;correction.value=decisions[item.id].correction;correction.id='correction-'+item.id;
      const correctionLabel=node('label','纠正后的内容（必填，保留上方原文）');correctionLabel.htmlFor=correction.id;
      const correctionBox=node('div');correctionBox.append(correctionLabel,correction);correctionBox.hidden=decisions[item.id].status!=='correct';
      for(const status of ['confirm','correct','reject','defer']){
        const label=node('label',undefined,'choice'),input=node('input');input.type='radio';input.name=item.id;input.value=status;input.checked=decisions[item.id].status===status;
        input.addEventListener('change',()=>{decisions[item.id]={status,correction:status==='correct'?correction.value:''};dirty=true;correctionBox.hidden=status!=='correct';notify('有未保存的选择。');controls();});
        label.append(input,node('span',labels[status]));fs.append(label);
      }
      correction.addEventListener('input',()=>{decisions[item.id].correction=correction.value;dirty=true;notify('有未保存的纠正内容。');controls();});
      card.append(fs,correctionBox);$('items').append(card);
    });controls();
  }
  async function load(){
    if(busy)return;
    if((dirty||pending)&&!window.confirm('重新读取将替换本页未保存的编辑。若上次结果未知，将读取服务器实际状态。是否继续？'))return;
    busy=true;controls();
    try{session=await api('api/session');decisions=structuredClone(session.decisions);position=Math.min(position,session.items.length-1);pending=null;dirty=false;render();notify(session.receipt?'已恢复最终回执及逐条决定。':'已读取服务器草稿。');}
    catch(e){notify('读取失败，请检查登录后重试。本页内容尚未替换。');}
    finally{busy=false;controls();}
  }
  async function save(final){
    if(busy||locked)return;
    if(pending&&pending.final!==final){notify('上次保存结果未知，请重试同一个操作或重新读取。');return;}
    if(!pending){
      const invalid=session.items.findIndex(item=>decisions[item.id].status==='correct'&&!decisions[item.id].correction.trim());
      if(invalid>=0){position=invalid;render();notify('请填写纠正内容后保存。');document.querySelector('textarea').focus();return;}
      const body={batch_id:session.batch_id,revision:session.revision,base_revision:session.draft_revision,request_id:crypto.randomUUID().replaceAll('-',''),decisions:structuredClone(decisions)};
      if(new TextEncoder().encode(JSON.stringify(body)).length>256*1024){notify('内容过长，尚未发送。请缩短纠正内容后保存。');return;}
      pending={final,body};
    }
    busy=true;notify('正在保存…');controls();
    try{
      const result=await api(final?'api/submit':'api/draft',{method:final?'POST':'PUT',headers:{'Content-Type':'application/json','X-Review-CSRF':session.csrf_token},body:JSON.stringify(pending.body)});
      pending=null;dirty=false;if(final){session.receipt=result;render();notify('最终审核回执已保存。');}else{session.draft_revision=result.draft_revision;notify('草稿已保存，可关闭后继续。');}
    }catch(e){
      if([401,403,404,409,413,422].includes(e.status))pending=null;
      notify(e.status===409?'版本冲突或已提交，请重新读取保存状态。':e.status===401?'登录已失效。本地内容已保留，请重新登录。':[403,404,413,422].includes(e.status)?'保存被拒绝；本地内容已保留，可修改后重试。':'未能确认保存成功。请重试同一操作，或重新读取服务器状态。');
    }
    finally{busy=false;controls();}
  }
  function move(delta){if(!session||busy||pending)return;position=Math.max(0,Math.min(session.items.length-1,position+delta));render();}
  $('previous').onclick=()=>move(-1);$('next').onclick=()=>move(1);
  window.addEventListener('beforeunload',event=>{if(dirty||pending||busy){event.preventDefault();event.returnValue='';}});
  $('save').onclick=()=>save(false);$('review').onsubmit=e=>{e.preventDefault();save(true);};$('reload').onclick=load;load();
})();
