/* 同源手机审核；缓存只含当前批次草稿和幂等请求，不存登录凭据。 */
'use strict';
(function () {
  const copy = value => JSON.parse(JSON.stringify(value));
  const uuid = () => globalThis.crypto.randomUUID();
  class DraftSync {
    constructor(id, pkg, server, request, persist, changed, cached) {
      Object.assign(this, {id, pkg, request, persist, changed, revision:server.revision,
        values:copy(server.values), generation:0, dirty:false, pending:null,
        submitIntent:null, receipt:null, conflict:null, error:null, busy:null, submitting:null, server:copy(server)});
      if (cached && cached.package_revision === pkg) {
        Object.assign(this, {revision:cached.revision, values:cached.values, generation:cached.generation || 0,
          dirty:!!cached.dirty, pending:cached.pending, submitIntent:cached.submitIntent});
        // 未知结果的同 ID 请求先重放；不能凭服务器版本增加就判为冲突。
        if (cached.conflict || (!this.pending && this.dirty && server.revision !== this.revision)) this.conflict = copy(server);
        if (!this.conflict && !this.dirty && !this.pending) {this.revision=server.revision;this.values=copy(server.values);}
      }
    }
    snapshot() {return {package_revision:this.pkg,revision:this.revision,values:this.values,
      generation:this.generation,dirty:this.dirty,pending:this.pending,submitIntent:this.submitIntent,conflict:!!this.conflict};}
    notify() {this.persist(this.snapshot());this.changed(this);}
    observe(server) {if(server.revision>=this.server.revision)this.server=copy(server);}
    edit(fn) {fn(this.values);this.generation++;this.dirty=true;this.notify();}
    flush() {
      if (this.busy) return this.busy;
      this.busy=this.saveLoop().finally(()=>{this.busy=null;this.notify();});return this.busy;
    }
    async saveLoop() {
      while ((this.dirty || this.pending) && !this.conflict && !this.submitIntent) {
        if (!this.pending) this.pending={generation:this.generation, body:{package_revision:this.pkg,
          base_revision:this.revision, request_id:uuid(), values:copy(this.values)}};
        this.error=null;this.notify();const pending=this.pending;
        try {
          const result=await this.request(`/tasks/${this.id}/draft`,pending.body,'PUT');
          if (!Number.isInteger(result.revision)) throw new Error('电脑未返回有效的保存确认');
          if(result.revision<this.server.revision){
            this.pending=null;this.revision=this.server.revision;this.dirty=true;
            this.conflict=copy(this.server);this.notify();return;
          }
          this.observe({revision:result.revision,values:result.values||pending.body.values});
          this.revision=result.revision;this.pending=null;
          this.dirty=this.generation!==pending.generation;
          this.notify();
        } catch (error) {
          this.error=error;if(error.status===409)this.conflict={unknown:true};
          // 422 表示字段校验明确未执行；网络/5xx/401 等仍保留原请求重放。
          if(error.status===422){this.pending=null;this.dirty=true;}
          this.notify();return;
        }
      }
    }
    async resolve(server, keepLocal) {
      if (this.submitIntent) throw new Error('请先恢复本次提交回执');
      this.observe(server);this.pending=null;this.conflict=null;this.revision=server.revision;this.error=null;
      if(!keepLocal){this.values=copy(server.values);this.dirty=false;}else this.dirty=true;
      this.notify();
    }
    submit(supersedes) {
      if(this.submitting)return this.submitting;
      this.submitting=this.sendSubmit(supersedes).finally(()=>{this.submitting=null;this.notify();});
      return this.submitting;
    }
    async sendSubmit(supersedes) {
      if(!this.submitIntent){
        if(this.dirty || this.pending || this.busy || this.conflict)throw new Error('请先把草稿保存到电脑');
        this.submitIntent={package_revision:this.pkg,draft_revision:this.revision,request_id:uuid(),supersedes};
      }
      this.error=null;this.notify();
      try {
        const result=await this.request(`/tasks/${this.id}/submit`,this.submitIntent,'POST');
        if(!result.receipt_id || !result.counts)throw new Error('电脑未返回有效回执');
        this.receipt=result;this.submitIntent=null;this.notify();return result;
      }catch(error){
        this.error=error;
        // 明确拒绝与“结果未知”不同；允许修订后重新确认，不困在旧提交里。
        if(error.status===409){this.submitIntent=null;this.conflict={unknown:true};}
        if(error.status===422)this.submitIntent=null;
        this.notify();return null;
      }
    }
  }
  class DraftCache {
    constructor(storage,pkg,tab,base='/review/'){Object.assign(this,{storage,pkg,tab,prefix:`voice-review:${base==='/review/'?'':base+':'}${pkg}:`});}
    key(id){return `${this.prefix}${id}:${this.tab}`;}
    claimed(key,raw){const marker=this.storage.getItem('voice-review-claim:'+key);return marker&&JSON.parse(marker).raw===raw;}
    own(id){const key=this.key(id),raw=this.storage.getItem(key);return raw&&!this.claimed(key,raw)?JSON.parse(raw):null;}
    save(id,value){this.storage.setItem(this.key(id),JSON.stringify(value));}
    candidates(id){const choices=[];for(let i=0;i<this.storage.length;i++){
      const key=this.storage.key(i);if(!key.startsWith(`${this.prefix}${id}:`)||key===this.key(id))continue;
      const raw=this.storage.getItem(key);if(!raw||this.claimed(key,raw))continue;
      const value=JSON.parse(raw);if(value.dirty||value.pending||value.submitIntent||value.conflict)choices.push({key,raw,value});
    }return choices;}
    claim(id,choice){
      if(this.storage.getItem(choice.key)!==choice.raw||this.claimed(choice.key,choice.raw))throw new Error('这份草稿刚有变化，请重新选择。');
      // 先持久化新副本，再标记这一份精确快照已领用；不删除活跃标签的数据。
      this.save(id,choice.value);
      this.storage.setItem('voice-review-claim:'+choice.key,JSON.stringify({raw:choice.raw,recovered_to:this.key(id)}));
      return copy(choice.value);
    }
  }
  if(typeof module!=='undefined' && module.exports){module.exports={DraftSync,DraftCache};return;}
  const validBase=path=>typeof path==='string' && /^\/review\/(?:batches\/[a-z0-9][a-z0-9-]{0,63}\/)?$/.test(path);
  const base=validBase(location.pathname)?location.pathname:null;
  const app=document.getElementById('app');
  let session, active=null, syncs={}, timers={}, storageWarning='', tabId, draftCache;
  try {tabId=sessionStorage.getItem('review-tab')||uuid();sessionStorage.setItem('review-tab',tabId);}catch(_){tabId=uuid();storageWarning='浏览器禁止本机缓存，请保持页面打开直到保存成功。';}
  const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  const button=(text,fn,cls)=>{const b=el('button',text,cls);b.type='button';b.addEventListener('click',fn);return b;};
  function cache(id,value){try{draftCache.save(id,value);}catch(_){storageWarning='本机缓存不可用或空间不足。离开前请确认已保存到电脑。';}}
  function readCache(id){try{return draftCache.own(id);}catch(_){storageWarning='无法读取本机草稿缓存。请勿关闭仍有未同步内容的旧页面。';return null;}}
  function recoveryChoices(id){try{return draftCache.candidates(id);}catch(_){storageWarning='无法读取其他页面的草稿。';return [];}}
  function recoveryButton(id){const choices=recoveryChoices(id);if(!choices.length)return;app.append(button(`恢复其他页面的未同步草稿（${choices.length} 份）`,()=>chooseRecovery(id),'wide'));}
  async function chooseRecovery(id){
    const s=syncs[id];if(s.dirty||s.pending||s.submitIntent||s.busy){alert('请先保存或处理本页草稿，再恢复另一份。');return;}
    const d=modal('选择要恢复的草稿');d.append(el('p','每份草稿都保留在本机。恢复后会核对电脑版本；若旧页面仍打开，请先停止在那一页编辑。'));
    for(const [index,choice]of recoveryChoices(id).entries()){
      const details=el('details');details.append(el('summary',`草稿 ${index+1}`),el('pre',JSON.stringify(choice.value.values,null,2)));d.append(details);
      d.append(button(`恢复草稿 ${index+1}`,async()=>{try{
        const fresh=await request('/session');if(fresh.package_revision!==session.package_revision)throw new Error('批次已变化，请重新打开页面。');
        if(s.dirty||s.pending||s.submitIntent||s.busy||syncs[id]!==s)throw new Error('本页草稿刚有变化，请先处理本页修改。');
        session.csrf_token=fresh.csrf_token;const recovered=draftCache.claim(id,choice);
        syncs[id]=new DraftSync(id,session.package_revision,fresh.drafts[id],request,value=>cache(id,value),updateStatus,recovered);
        syncs[id].receipt=fresh.latest_receipts[id];d.close();active=id;render();
        if(syncs[id].submitIntent)await recoverSubmit(id);else await syncs[id].flush();
      }catch(e){alert(e.message);d.close();render();}}));
    }d.append(button('暂不恢复',()=>d.close()));
  }
  async function request(path,body,method='GET') {
    if(!base)throw new Error('试听批次地址无效，请从个人站重新打开。');
    const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),20000);
    try {
      const response=await fetch(base+'api'+path,{method,credentials:'same-origin',redirect:'error',cache:'no-store',
        headers:body?{'Content-Type':'application/json','X-Review-CSRF':session.csrf_token}:{},
        body:body?JSON.stringify(body):undefined,signal:controller.signal});
      const type=response.headers.get('Content-Type')||'';
      if(!type.includes('application/json')){const e=new Error('登录可能已过期，请重新登录后重试。');e.status=401;throw e;}
      const result=await response.json();
      if(!response.ok){const e=new Error(result.error?.message||'电脑暂时无法保存');e.status=response.status;throw e;}
      return result;
    }catch(e){if(e.name==='TypeError')e.message='连接中断或需要重新登录；草稿仍保留在本机。';throw e;}
    finally{clearTimeout(timeout);}
  }
  function counts(id,values){const task=session.tasks.find(t=>t.id===id);if(id==='ab'){
    const judged=task.items.filter(i=>values.items[i.id].preference!=='unheard').length;return {judged,unheard:task.items.length-judged};}
    if(id==='language'){const c={wu:0,mandarin:0,mixed:0,unknown:0,pending:0,labeled:0};for(const item of task.items){const language=values.items[item.id].language;if(language==='unlabeled')c.pending++;else{c[language]++;c.labeled++;}}return c;}
    let train=0,validation=0,excluded=0,pending=0;
    for(const item of task.items){const v=values.items[item.id];if(v.disposition==='exclude')excluded++;
      else if(v.disposition==='review'&&v.include&&v.speaker&&v.single&&v.transcript&&v.transcript_confirmed_text===v.text&&v.quality&&(!item.duration_requires_confirmation||v.duration)){if(item.split==='train')train++;else validation++;}else pending++;}
    return {train,validation,pending,excluded};
  }
  const countText=(id,c)=>id==='ab'?`已判断 ${c.judged} · 未判断 ${c.unheard}`:id==='language'?`已标注 ${c.labeled} · 上海话 ${c.wu} · 普通话 ${c.mandarin} · 两种都有 ${c.mixed} · 不确定 ${c.unknown} · 未标注 ${c.pending}`:`训练候选 ${c.train} · 留出评估 ${c.validation} · 待定 ${c.pending} · 暂不采用 ${c.excluded}`;
  const decidedCount=(id,c)=>id==='ab'?c.judged:id==='language'?c.labeled:c.train+c.validation+c.excluded;
  const taskTitle=task=>task.title||({ab:'声音对比',source:'原声核验',language:'语言标注'})[task.id];
  function openTask(id){active=id;history.replaceState(null,'',location.pathname+location.search+(id==='language'?'#language':''));render();}
  function edit(id,fn){syncs[id].edit(fn);clearTimeout(timers[id]);timers[id]=setTimeout(()=>syncs[id].flush(),650);updateStatus();}
  function statusText(s){if(s.conflict)return '发现另一台设备或标签页的修改，请处理冲突';if(s.submitIntent)return '提交结果尚未确认，请恢复回执';if(s.error)return `尚未同步：${s.error.message}`;if(s.busy)return '正在保存到电脑…';return s.dirty?'尚未同步 · 草稿在本机':'已保存到电脑';}
  function updateStatus(){for(const id of Object.keys(syncs)){const node=document.getElementById('status-'+id);if(node){node.textContent=statusText(syncs[id]);node.className='status'+((syncs[id].error||syncs[id].conflict)?' warning':'');}}
    const retry=document.getElementById('retry');if(retry&&active)retry.hidden=!(syncs[active].error||syncs[active].dirty||syncs[active].submitIntent);
    const conflict=document.getElementById('conflict-open');if(conflict&&active)conflict.hidden=!syncs[active].conflict;
    const recovery=document.getElementById('recover-submit');if(recovery&&active)recovery.hidden=!syncs[active].submitIntent;
    const warning=document.getElementById('storage-warning');if(warning){warning.textContent=storageWarning;warning.hidden=!storageWarning;}}
  function header(){app.replaceChildren();app.setAttribute('aria-busy','false');const h=el('header');h.append(el('span','声音档案 / 私人评测','eyebrow'),el('h1',session?.batch?.title||'慢慢听，慢慢确认。'),el('p','每次做一点，也会好好留下。'));app.append(h);if(session){const nav=el('nav',undefined,'batch-links');nav.setAttribute('aria-label','其他试听批次');for(const batch of session.batches||[]){if(!validBase(batch.base_path)||batch.base_path===base)continue;const link=el('a',batch.title||'其他试听批次','link');link.href=batch.base_path;nav.append(link);}if(nav.childNodes.length)app.append(nav);}const w=el('p',storageWarning,'warning');w.id='storage-warning';w.hidden=!storageWarning;app.append(w);}
  function render(){document.querySelectorAll('audio').forEach(a=>a.pause());header();if(!active){
    for(const task of session.tasks){const s=syncs[task.id],c=counts(task.id,s.values);const done=decidedCount(task.id,c);
      const description=task.id==='ab'?'听 A、B，留下你的真实感受':task.id==='language'?'逐段听原声，标注语言；可以分批提交':`${task.items.filter(i=>i.split==='train').length} 段训练候选 · ${task.items.filter(i=>i.split==='validation').length} 段留出评估`;
      const b=button('',()=>openTask(task.id),'card task');b.append(el('span',`${done} / ${task.items.length}`,'count'),el('strong',taskTitle(task)),el('span',description,'muted'));
      app.append(b);const status=el('p',statusText(s),'status');status.id='status-'+task.id;app.append(status);recoveryButton(task.id);if(s.receipt)showReceipt(task.id,s.receipt);}
    app.append(el('footer','音频与结果经现有个人站传输，保存到你的电脑。草稿不等于批准，提交也不会自动训练或更换声音。'));return;}
    const id=active,s=syncs[id],task=session.tasks.find(t=>t.id===id),position=s.values.position,item=task.items[position],v=s.values.items[item.id];
    app.append(button('‹ 返回任务',()=>openTask(null)));
    recoveryButton(id);
    const status=el('p',statusText(s),'status');status.id='status-'+id;status.setAttribute('role','status');app.append(status);
    const retry=button('重新连接并同步',retryAll);retry.id='retry';app.append(retry);
    const login=el('a','重新登录（草稿保留）','link');login.href=base;app.append(login);
    const conflict=button('查看并处理版本冲突',()=>resolveConflict(id));conflict.id='conflict-open';app.append(conflict);
    const recover=button('恢复本次提交回执',()=>recoverSubmit(id),'primary wide');recover.id='recover-submit';app.append(recover);
    const card=el('section',undefined,'card');card.append(el('span',`${taskTitle(task)} · ${position+1} / ${task.items.length}`,'eyebrow'));
    const progress=el('progress');progress.max=task.items.length;progress.value=position+1;progress.setAttribute('aria-label','当前位置');card.append(progress);
    if(id==='ab')renderAB(card,item,v);else if(id==='source')renderSource(card,item,v);else if(id==='language')renderLanguage(card,item,v);
    const noteLabel=el('label','备注（可选）');noteLabel.htmlFor='note';const note=el('textarea');note.id='note';note.maxLength=2000;note.value=v.note;note.placeholder=id==='ab'?'哪里自然，哪里不像？':'有不确定的地方，可以记在这里。';note.addEventListener('input',()=>edit(id,x=>x.items[item.id].note=note.value));card.append(noteLabel,note);app.append(card);
    const nav=el('nav',undefined,'row nav');const prev=button('‹ 上一项',()=>move(-1));prev.disabled=position===0;const next=button('下一项 ›',()=>move(1));next.disabled=position===task.items.length-1;nav.append(prev,next);app.append(nav);
    if(id==='source'){const label=el('label','核验人（正式决定使用此署名）');label.htmlFor='reviewer';const input=el('input');input.type='text';input.id='reviewer';input.maxLength=100;input.value=s.values.reviewer;input.autocomplete='name';input.addEventListener('input',()=>edit(id,x=>x.reviewer=input.value));app.append(label,input);}
    app.append(el('p',countText(id,counts(id,s.values)),'muted'),button('提交本次结果',()=>confirmSubmit(id),'primary wide'));
    if(s.receipt)showReceipt(id,s.receipt);app.append(el('footer',id==='ab'?'这些合成语音属于 Tier-3，不是真实录音。这只是声音偏好，不会批准训练，也不会自动切换线上声音。':id==='language'?'语言标注不批准原声或训练，不改变说话人、转写和质量核验。“两种都有”和“不确定”不会自动归入单一训练语域；留出评估仍保留。':'未完成确认的条目仍是待定。留出评估录音不会作为训练候选。'));updateStatus();
  }
  function move(delta){const id=active;edit(id,v=>v.position+=delta);render();window.scrollTo(0,0);}
  function audio(parent,url,label,onPlayed){const box=el('div',undefined,'audio'),a=el('audio');a.controls=true;a.preload='none';
    const resolved=new URL(url,location.origin);if(resolved.origin!==location.origin||!resolved.pathname.startsWith(base+'audio/'))throw new Error('音频地址不属于本批评测');a.src=resolved.href;
    const b=button('▶ '+label,async()=>{try{if(!a.paused)a.pause();else await a.play();}catch(_){b.textContent='播放未开始，请用下方播放器重试';}});
    a.addEventListener('play',()=>{document.querySelectorAll('audio').forEach(other=>{if(other!==a)other.pause();});b.textContent='Ⅱ 暂停 '+label;if(onPlayed)onPlayed();});a.addEventListener('pause',()=>b.textContent='▶ '+label);a.addEventListener('ended',()=>b.textContent='▶ '+label);a.addEventListener('error',()=>{b.textContent='音频未加载，请检查连接或重新登录';});box.append(b,a);parent.append(box);}
  function renderAB(card,item,v){card.append(el('h2','哪一个更自然、更像？'),el('p',item.text,'text'));audio(card,item.audio_a,'播放 A',()=>edit('ab',x=>x.items[item.id].played_a=true));audio(card,item.audio_b,'播放 B',()=>edit('ab',x=>x.items[item.id].played_b=true));const choices=el('div',undefined,'choices');for(const [value,label]of [['A','A 更好'],['B','B 更好'],['same','差不多'],['neither','都不好'],['unheard','暂不判断']]){const b=button(label,()=>{edit('ab',x=>x.items[item.id].preference=value);render();},v.preference===value?'selected':'');b.setAttribute('aria-pressed',String(v.preference===value));choices.append(b);}card.append(choices);}
  function renderSource(card,item,v){card.append(el('h2','听原声，逐项核验'),el('span',item.split==='train'?'训练候选':'留出评估 · 不用于训练','badge'),el('p',item.source_label,'muted'),el('p',`实际 ${(item.actual_duration_ms/1000).toFixed(1)} 秒 · 来源记录 ${(item.expected_duration_ms/1000).toFixed(1)} 秒`,'small'));audio(card,item.audio,'播放原声');
    const label=el('label','转写草稿（请边听边改）');label.htmlFor='transcript-text';const text=el('textarea');text.id='transcript-text';text.maxLength=2000;text.value=v.text;text.addEventListener('input',()=>{edit('source',x=>{const state=x.items[item.id];state.text=text.value;state.transcript=false;state.transcript_confirmed_text=null;});document.getElementById('check-transcript').checked=false;});card.append(label,text);
    for(const [field,labelText]of [['speaker','我确认说话人正确'],['single','我确认是单人真实录音'],['transcript','我已逐字听完并校对上述全文'],['quality','我确认音质可用于后续处理'],...(item.duration_requires_confirmation?[['duration','我已核对时长差异，录音内容完整']]:[])]){
      const l=el('label',undefined,'check'),check=el('input');check.type='checkbox';check.id='check-'+field;check.checked=v[field];check.addEventListener('change',()=>edit('source',x=>{const state=x.items[item.id];state[field]=check.checked;if(field==='transcript')state.transcript_confirmed_text=check.checked?state.text:null;}));l.append(check,el('span',labelText));card.append(l);}
    if(item.duration_requires_confirmation)card.append(el('p','此段有时长差异，需要单独听完核对。','warning small'));
    const choices=el('div',undefined,'choices');for(const [value,labelText]of [['pending','待定'],['exclude','暂不采用'],['review','纳入本次核验']]){const b=button(labelText,()=>{edit('source',x=>{x.items[item.id].disposition=value;x.items[item.id].include=value==='review';});render();},v.disposition===value?'selected':'');b.setAttribute('aria-pressed',String(v.disposition===value));choices.append(b);}card.append(choices,el('p','“纳入”仍须完成上方全部必要确认；否则不能提交为通过。','muted small'));}
  function modal(title){const d=el('dialog');d.append(el('h2',title));app.append(d);d.addEventListener('close',()=>d.remove());d.showModal();return d;}
  function renderLanguage(card,item,v){card.append(el('h2',`录音 ${item.number} · 这段说的是什么语言？`),el('span',item.split==='validation'?'留出评估 · 不用于训练':'原声语言标注','badge'));audio(card,item.audio,'播放原声');
    const choices=el('div',undefined,'choices');for(const [value,label]of [['wu','上海话'],['mandarin','普通话'],['mixed','两种都有'],['unknown','不确定']]){const b=button(label,()=>{edit('language',x=>x.items[item.id].language=value);render();},v.language===value?'selected':'');b.setAttribute('aria-pressed',String(v.language===value));choices.append(b);}card.append(choices,button('清除本条标注',()=>{edit('language',x=>x.items[item.id].language='unlabeled');render();},'wide'),el('p',v.language==='unlabeled'?'本条尚未标注。请听后选择，不会自动判断语言。':'本条已选，自动保存为草稿；点击“提交本次结果”后才形成正式回执。','muted small'));}
  async function resolveConflict(id){try{const fresh=await request('/session');if(fresh.package_revision!==session.package_revision){alert('评测批次已变化。旧草稿保留在本机，请重新登录页面查看新批次。');return;}session.csrf_token=fresh.csrf_token;const s=syncs[id],server=fresh.drafts[id];s.receipt=fresh.latest_receipts[id];const d=modal('两边都有修改');d.append(el('p','请选择保留哪一份。另一份不会自动合并；选择本机将以电脑最新版本为基础保存。'));
    for(const [name,values]of [['本机草稿',s.values],['电脑草稿',server.values]]){const details=el('details');details.append(el('summary',name),el('pre',JSON.stringify(values,null,2)));d.append(details);}
    d.append(button('保留本机草稿并保存',async()=>{await s.resolve(server,true);d.close();render();await s.flush();}),button('采用电脑草稿',async()=>{await s.resolve(server,false);d.close();render();}),button('暂不处理',()=>d.close()));
  }catch(e){alert(e.message);}}
  async function retryAll(){try{const fresh=await request('/session');if(fresh.package_revision!==session.package_revision){alert('评测批次已变化；旧草稿不会应用到新批次，请重新打开页面。');return;}session.csrf_token=fresh.csrf_token;
    const tasksChanged=JSON.stringify(session.tasks.map(t=>t.id))!==JSON.stringify(fresh.tasks.map(t=>t.id));
    for(const task of fresh.tasks){const id=task.id;let s=syncs[id];if(!s){s=syncs[id]=new DraftSync(id,session.package_revision,fresh.drafts[id],request,value=>cache(id,value),updateStatus,readCache(id));}s.receipt=fresh.latest_receipts[id];s.observe(fresh.drafts[id]);if(s.submitIntent){await recoverSubmit(id);continue;}if(!s.pending&&s.dirty&&s.revision!==fresh.drafts[id].revision){s.conflict=fresh.drafts[id];s.notify();}else await s.flush();}session.tasks=fresh.tasks;if(tasksChanged){if(active&&!fresh.tasks.some(t=>t.id===active))active=null;render();}updateStatus();
  }catch(e){for(const s of Object.values(syncs)){s.error=e;s.notify();}}}
  async function confirmSubmit(id){const s=syncs[id];if(s.submitIntent){await recoverSubmit(id);return;}await s.flush();if(s.dirty||s.pending||s.conflict){updateStatus();return;}
    const revision=s.revision,c=counts(id,s.values);if(id==='source'&&!s.values.reviewer.trim()){alert('请填写核验人署名。');return;}
    if(decidedCount(id,c)===0){alert('本次还没有明确决定，可以继续保存草稿。');return;}
    const latest=s.receipt, supersedes=typeof latest==='string'?latest:latest?.receipt_id||null;
    const d=modal('提交本次结果');d.append(el('p',countText(id,c)),el('p',supersedes?'本次会更新此前提交，并留下明确的替代记录。旧回执仍保留。':'只提交你明确作出的决定，剩余条目仍是待定。'),el('p','完成后回到 Codex 说“已提交，请继续”。','muted'));
    d.append(button('确认提交',async()=>{if(s.revision!==revision||s.dirty||s.pending||s.conflict){d.close();alert('草稿刚有变化，请重新核对后提交。');return;}d.close();await recoverSubmit(id,supersedes);},'primary wide'),button('继续核对',()=>d.close(),'wide'));
  }
  async function recoverSubmit(id,supersedes=null){const s=syncs[id];try{const receipt=await s.submit(supersedes);if(receipt){render();if(s.dirty)s.flush();}else updateStatus();}catch(e){s.error=e;s.notify();}}
  function showReceipt(id,receipt){if(typeof receipt==='string'){const b=button('查看上次回执',async()=>{try{syncs[id].receipt=await request('/receipts/'+encodeURIComponent(receipt));render();}catch(e){alert(e.message);}});app.append(b);return;}
    const box=el('section',undefined,'card receipt');box.append(el('h3','电脑已收到正式提交'),el('p',countText(id,receipt.counts)),el('p',receipt.submitted_at||'','small'),el('code',receipt.receipt_id.slice(0,12)));
    box.append(button('复制回执编号',async()=>{try{await navigator.clipboard.writeText(receipt.receipt_id);alert('回执编号已复制');}catch(_){const d=modal('回执编号');d.append(el('p',receipt.receipt_id),button('关闭',()=>d.close()));}}));const link=el('a','下载 JSON 备用副本','link');link.href=base+'api/receipts/'+encodeURIComponent(receipt.receipt_id)+'/export';link.download='review.json';box.append(link,el('p','回到本条 Codex 对话，说“已提交，请继续”。','small'));app.append(box);}
  async function start(){try{session=await request('/session');try{draftCache=new DraftCache(localStorage,session.package_revision,tabId,base);}catch(_){storageWarning='浏览器禁止本机缓存。';}for(const {id} of session.tasks){syncs[id]=new DraftSync(id,session.package_revision,session.drafts[id],request,value=>cache(id,value),updateStatus,readCache(id));syncs[id].receipt=session.latest_receipts[id];}active=session.tasks.some(t=>t.id===location.hash.slice(1))?location.hash.slice(1):null;render();for(const s of Object.values(syncs)){if(s.submitIntent)await recoverSubmit(s.id);else if(!s.conflict)await s.flush();}}
    catch(e){header();app.append(el('p',e.message,'warning'),button('重试连接',start,'primary'),Object.assign(el('a','重新登录','link'),{href:base||'/review/'}));}}
  window.addEventListener('hashchange',()=>{if(session){active=session.tasks.some(t=>t.id===location.hash.slice(1))?location.hash.slice(1):null;render();}});window.addEventListener('online',retryAll);window.addEventListener('beforeunload',event=>{if(Object.values(syncs).some(s=>s.dirty||s.pending||s.submitIntent)){event.preventDefault();event.returnValue='';}});start();
})();
