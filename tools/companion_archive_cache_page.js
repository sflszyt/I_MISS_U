/* Installed only on the opt-in scoped father page; existing voice/session code is untouched. */
var archiveOptions = __CACHE_OPTIONS__;
var archiveStatusText = '首次准备需联网验证身份并下载；完成校验后可保留设备档案副本。';
var archiveStatusNodes = [], archiveToggleNodes = [], archivePagePending = null, archivePageOperation = 0, archiveSendProof = null;
var archiveOriginalProgressText = dataProgressText;
var archiveProgress = null;
var archiveVerifiedRevision = '';
function updateArchiveRevision(revision) {
  archiveVerifiedRevision = revision || '';
  document.querySelectorAll('.archive-cache-revision').forEach(function(node) {
    node.textContent = archiveVerifiedRevision ? '已核验资料版本 ' + archiveVerifiedRevision : '资料版本待核验';
  });
}
dataProgressText = function(progress) {
  if (progress.phase === 'idle') return introAccepted ? '资料尚未准备，请点击重试准备或重新验证。' : '确认说明后开始验证访问权限并准备资料。';
  if (progress.phase !== 'ready' && progress.phase !== 'failed' && !archiveProgress) return '正在确认访问权限和资料版本。';
  if (progress.phase !== 'ready' && progress.phase !== 'failed' && archiveProgress && archiveProgress.verified === archiveProgress.total) return '资料校验已完成，正在完成访问权限复核。';
  if (archiveProgress) progress = Object.assign({}, progress, archiveProgress);
  if(progress.phase==='failed')return '资料准备发生错误，请重试。'+dataDiagnostic();
  return archiveOriginalProgressText(progress).replace('已下载 ', '已读取 ').replace('正在下载并校验资料', '正在读取并校验资料');
};
var archiveBroadcast = typeof BroadcastChannel === 'function' ? new BroadcastChannel('companion-private-archive-v1') : null;
function archiveStatus(text) {
  archiveStatusText = text;
  archiveStatusNodes.forEach(function(node) { node.textContent = text; });
  archiveToggleNodes.forEach(function(node) { node.checked = !archiveCache.disabled; });
}
// Lifecycle return retires authority, not an already committed reply. Held work
// exists only in this document and is never written to the archive store.
var archiveReplyRevision=null, archiveSendCuePreparation=null;
var archiveLifecycleInvalidation = false, archiveReplyPaused = false, archiveReplyQueue = [];
function archiveReplyStamp() {
  return {generation:sendGeneration, profile:JSON.stringify(settings), scope:JSON.stringify(EXPECTED_SCOPE),
    session:sessionId, revision:archiveReplyRevision, policy:JSON.stringify(archiveCache.readPolicy())};
}
function archiveReplyCurrent(stamp) {
  return stamp.generation === sendGeneration && stamp.profile === JSON.stringify(settings) &&
    stamp.scope === JSON.stringify(EXPECTED_SCOPE) && stamp.session === sessionId &&
    stamp.revision === archiveReplyRevision &&
    stamp.policy === JSON.stringify(archiveCache.readPolicy());
}
function archiveReplyBlocked() { return document.hidden || archiveReplyPaused || dataReadyPhase !== 'ready'; }
function archiveHoldReply(stamp, run, discard) {
  if (!archiveReplyCurrent(stamp)) { if(discard)discard(); return; }
  if (archiveReplyBlocked()) archiveReplyQueue.push({stamp:stamp,run:run,discard:discard});
  else run();
}
function archiveDiscardReplies() {
  var held=archiveReplyQueue;archiveReplyQueue=[];
  held.forEach(function(job){if(job.discard)job.discard();});
}
function archiveReleaseReplies() {
  if(document.hidden || dataReadyPhase !== 'ready')return;
  archiveReplyPaused=false;
  var held=archiveReplyQueue;archiveReplyQueue=[];
  held.forEach(function(job){archiveHoldReply(job.stamp,job.run,job.discard);});
}
// Public cue/unlock playback is owned by the pending Send, including while it
// waits an older preparation. No reply/history audio receives this exception.
function archiveRememberSendCue(operation){
  var session=typeof autoVoiceSession!=='undefined' && autoVoiceSession;
  var job=session && session.job;
  archiveSendCuePreparation=job && job.cue ? {operation:operation,epoch:archiveCache.epoch,stamp:archiveReplyStamp(),job:job} : null;
}
function archiveOwnsSendCue(audio){
  var proof=archiveSendCuePreparation,session=typeof autoVoiceSession!=='undefined' && autoVoiceSession;
  var job=session && session.job;
  return !!(proof && !document.hidden && sendPending && proof.operation===archivePageOperation &&
    proof.epoch===archiveCache.epoch && archiveReplyCurrent(proof.stamp) &&
    (dataReadyPhase==='loading' || dataReadyPhase==='verifying') && job===proof.job && job.cue &&
    session.audio===audio && replayAudio===audio && job.source===audio.src &&
    job.generation===sendGeneration && job.profile===JSON.stringify(settings) && job.scope===JSON.stringify(EXPECTED_SCOPE));
}
function archiveGuardMediaEvent(event){
  if(archiveReplyBlocked() && !archiveOwnsSendCue(event.target) && event.target && typeof event.target.pause==='function')event.target.pause();
}
document.addEventListener('play',archiveGuardMediaEvent,true);
document.addEventListener('playing',archiveGuardMediaEvent,true);
var archiveOriginalPlayHistoryNative=playHistoryNative;
playHistoryNative=function(bar,autoTurn){if(archiveReplyBlocked())return;return archiveOriginalPlayHistoryNative(bar,autoTurn);};
var archiveOriginalStreamRequest=streamRequest;
streamRequest=function(messages,onDelta,onDone,onError,requestSettings){
  var stamp=archiveReplyStamp(), requestController;
  archiveOriginalStreamRequest(messages,onDelta,function(text,aborted){
    if(aborted){onDone(text,true);return;}
    archiveHoldReply(stamp,function(){onDone(text,!!(requestController && requestController.signal.aborted));});
  },function(error){archiveHoldReply(stamp,function(){onError(error);});},requestSettings);
  requestController=controller;
};
// Never regenerate an uncertain POST: it may have saved an audio file already.
// Only the separately protected, same-viewer history may supply an exact binding.
var archiveExcludedSessions=new Set();
var archiveOriginalLogSession=logSession;
logSession=function(rec,requestSettings){
  if((requestSettings ? requestSettings.exclude : noMemoryEnabled) || rec.text === 'exclude_session')archiveExcludedSessions.add(sessionId);
  return archiveOriginalLogSession(rec,requestSettings);
};
var archiveOriginalFetchVoiceBlob=fetchVoiceBlob;
// A retired voice turn deliberately never settles into the inherited handlers:
// their scope check alone cannot distinguish cancellation by the next Send.
function archiveVoiceStep(vt, step) {
  return new Promise(function(resolve,reject){
    archiveHoldReply(vt.archiveStamp,function(){
      if(vt.canceled || !voiceScopeCurrent(vt) || !archiveReplyCurrent(vt.archiveStamp))return;
      try {resolve(step());} catch(error){reject(error);}
    });
  });
}
function archiveVoiceOutcome(vt,promise) {
  return promise.then(function(value){return archiveVoiceStep(vt,function(){return value;});},
    function(error){return archiveVoiceStep(vt,function(){throw error;});});
}
function archiveCheckVoiceLookup(vt) {
  if(archiveExcludedSessions.has(vt.archiveStamp.session))throw new Error('AUDIO_NOT_CONFIRMED');
}
async function archiveFindSavedVoice(vt,i){
  await archiveVoiceStep(vt,function(){archiveCheckVoiceLookup(vt);});
  var ctrl=new AbortController();
  var request=boundedWait(fetch(SESSIONS_PATH,{cache:'no-store',credentials:'same-origin',redirect:'error',signal:ctrl.signal})
    .then(function(r){if(!r.ok)throw new Error('AUDIO_NOT_CONFIRMED');return r.json();}),15000)
    .finally(function(){ctrl.abort();});
  // Network cleanup is bounded independently of a held/retired UI continuation.
  var data=await archiveVoiceOutcome(vt,request);
  archiveCheckVoiceLookup(vt);
  if(!data || data.viewer!==VIEWER || !Array.isArray(data.sessions))throw new Error('AUDIO_NOT_CONFIRMED');
  var sessions=data.sessions.filter(function(s){return s.session_id===vt.archiveStamp.session && !s.exclude;});
  if(sessions.length!==1 || !Array.isArray(sessions[0].turns))throw new Error('AUDIO_NOT_CONFIRMED');
  var turns=sessions[0].turns.filter(function(t){return t.role==='simulacrum' && t.turn===vt.turn && !t.exclude;});
  if(turns.length!==1 || !Array.isArray(turns[0].audio))throw new Error('AUDIO_NOT_CONFIRMED');
  var text=(vt.speechMsgs||vt.msgs)[i].trim();
  if((vt.speechMsgs||vt.msgs).filter(function(t){return t.trim()===text;}).length!==1)throw new Error('AUDIO_NOT_CONFIRMED');
  var prefix='audio/session_'+vt.archiveStamp.session+'_t'+String(vt.turn).padStart(3,'0');
  var matches=turns[0].audio.filter(function(a){return a && a.text===text;});
  if(matches.length!==1 || typeof matches[0].file!=='string' ||
      !/^audio\/session_[A-Za-z0-9_-]+\.wav$/.test(matches[0].file) || matches[0].file.indexOf(prefix)!==0 ||
      !/^(?:_[2-9][0-9]*|_1[0-9]+)?\.wav$/.test(matches[0].file.slice(prefix.length)))throw new Error('AUDIO_NOT_CONFIRMED');
  var result=await archiveVoiceOutcome(vt,archiveOriginalFetchVoiceBlob(SESSIONS_BASE+matches[0].file,{credentials:'same-origin',redirect:'error'},15000));
  archiveCheckVoiceLookup(vt);
  return result;
}
fetchVoiceBlob=function(url,options,timeout){
  var dispatch=options.method==='POST' ? archiveVoiceDispatch : null;
  // Concurrent retries have no reliable ordering. Bind at the synchronous
  // dispatch site, before any request or promise can outlive its stack frame.
  if(options.method==='POST' && !dispatch){
    var error=new Error('Missing voice dispatch owner');error.code='AUDIO_FETCH';return Promise.reject(error);
  }
  var vt=dispatch && dispatch.turn, index=dispatch ? dispatch.index : -1;
  var stamp=vt ? vt.archiveStamp : archiveReplyStamp();
  // A blocked history click is refused, not queued as a future play intent.
  if(!vt && archiveReplyBlocked()){
    var error=new Error('Archive verification required');error.code='AUDIO_REVALIDATE';return Promise.reject(error);
  }
  var request=archiveOriginalFetchVoiceBlob(url,options,timeout);
  if(!vt){
    function settle(value,failed){return new Promise(function(resolve,reject){
      archiveHoldReply(stamp,function(){if(failed)reject(value);else resolve(value);},function(){
        var error=new Error('Retired reply');error.code='AUDIO_FETCH';reject(error);
      });
    });}
    return request.then(function(value){return settle(value,false);},function(error){return settle(error,true);});
  }
  return archiveVoiceOutcome(vt,request).catch(function(original){
    // These server responses reject input before synthesis. A later explicit
    // retry may send once after a fresh gate; delivery failures remain uncertain.
    if(/^AUDIO_HTTP_(400|413|422)$/.test(original.code||'') || index<0)throw original;
    if(!vt.archiveUncertain)vt.archiveUncertain={};vt.archiveUncertain[index]=true;
    return archiveFindSavedVoice(vt,index).then(function(result){
      return archiveVoiceStep(vt,function(){delete vt.archiveUncertain[index];return result;});
    },function(){return archiveVoiceStep(vt,function(){throw original;});});
  });
};
var archiveOriginalShowVoiceMsg=showVoiceMsg;
showVoiceMsg=function(vt,i,blob,dur){
  if(blob && vt.archiveUncertain)delete vt.archiveUncertain[i];
  var bar=archiveOriginalShowVoiceMsg(vt,i,blob,dur);
  if(blob)bar._historyRetry.textContent='\u91cd\u8bd5\u8bed\u97f3';
  return bar;
};
var archiveOriginalVoiceError=voiceError;
voiceError=function(bar,code){
  if(code==='AUDIO_REVALIDATE'){
    bar._historyStatus.textContent='\u8d44\u6599\u5c1a\u672a\u9a8c\u8bc1\uff0c\u5b8c\u6210\u9a8c\u8bc1\u540e\u8bf7\u518d\u70b9\u8bed\u97f3\u6761\u3002';
    bar._historyRetry.hidden=false;
    bar._historyRetry.textContent='\u518d\u6b21\u5c1d\u8bd5';
    return;
  }
  archiveOriginalVoiceError(bar,code);
  if(bar._voiceTurn && bar._voiceTurn.archiveUncertain && bar._voiceTurn.archiveUncertain[bar._voiceIndex]){
    bar._historyStatus.textContent='\u8bed\u97f3\u7ed3\u679c\u5c1a\u672a\u786e\u8ba4\uff0c\u53ef\u67e5\u627e\u5df2\u4fdd\u5b58\u8bed\u97f3\uff1b\u4e0d\u4f1a\u91cd\u590d\u5408\u6210\u3002';
    bar._historyRetry.textContent='\u67e5\u627e\u5df2\u4fdd\u5b58\u8bed\u97f3';
  }
};
var archiveOriginalSynthMsg=synthMsg, archiveVoiceDispatch=null;
function archiveDispatchSynth(vt,i,retry){
  var previous=archiveVoiceDispatch;
  archiveVoiceDispatch={turn:vt,index:i};
  try {return archiveOriginalSynthMsg(vt,i,retry);}
  finally {archiveVoiceDispatch=previous;}
}
synthMsg=function(vt,i,retry){
  if(vt.canceled || !voiceScopeCurrent(vt))return;
  if(!vt.archiveStamp)vt.archiveStamp=archiveReplyStamp();
  if(!archiveReplyCurrent(vt.archiveStamp))return;
  if(archiveReplyBlocked()){
    if(!vt.archiveQueued)vt.archiveQueued={};
    if(vt.archiveQueued[i])return;
    vt.archiveQueued[i]=true;
    archiveHoldReply(vt.archiveStamp,function(){delete vt.archiveQueued[i];synthMsg(vt,i,retry);});return;
  }
  if(retry){
    var bar=vt.bars[i];if(!bar || bar._voiceLoading || vt.requests[i]!=='failed')return;
    bar._voiceLoading=true;
    var dispatched=false;
    ensureDataReady().then(function(ok){
      if(!ok)throw new Error('AUDIO_NOT_CONFIRMED');
      return archiveVoiceStep(vt,function(){
        if(vt.archiveUncertain && vt.archiveUncertain[i])return archiveFindSavedVoice(vt,i);
        dispatched=true;archiveDispatchSynth(vt,i,true);return null;
      });
    }).then(function(result){
      if(!result)return;
      return archiveVoiceStep(vt,function(){
        vt.requests[i]='ready';vt.blobs[i]=result.blob;vt.durs[i]=result.dur;
        showVoiceMsg(vt,i,result.blob,result.dur);
      });
    }).catch(function(){return archiveVoiceStep(vt,function(){voiceError(bar,'AUDIO_FETCH');});})
      .finally(function(){if(!dispatched)bar._voiceLoading=false;});return;
  }
  archiveDispatchSynth(vt,i,retry);
};
var archiveOriginalPresentation=startTurnPresentation;
startTurnPresentation=function(){
  var result=archiveOriginalPresentation.apply(this,arguments);
  // fetchVoiceBlob already has a bounded timeout and a visible retry bar. A
  // second 20s timer must not discard a still-running or held result.
  if(voiceTurn){clearTimeout(voiceTurn.safetyTimer);voiceTurn.safetyTimer=null;
    if(archiveReplyPaused || document.hidden || (autoVoiceSession && autoVoiceSession.suspended))voiceTurn.autoStopped=true;}
  return result;
};
function invalidateArchivePage() {
  updateArchiveRevision('');
  archiveProgress = null;
  archivePageOperation++; archiveSendProof = null; archiveSendCuePreparation=null;
  invalidateDataArchive();
  dataReadyPromise = null; archivePagePending = null; dataReadyPhase = 'idle';
  contextLoaded = false; contextLoading = null; systemPrompt = ''; shards = [];
  shardCache = {}; shardStatus = {}; shardsLoading = false;
  knowledgeCache = null; knowledgePieces = Object.create(null); knowledgeLoading = false;
  memorySourceDigests = new Map(); scopeError = true;
  dataProgress = Object.create(null);
  if(archiveLifecycleInvalidation){reportDataProgress();return;}
  var interruptedReply=archiveReplyPaused && (streaming || !!voiceTurn);
  archiveReplyPaused=false;archiveDiscardReplies();
  sendGeneration++; sendPending = false;
  cancelVoiceTurn();
  if (cancelActiveSend) { cancelActiveSend(); cancelActiveSend = null; }
  if (controller) { controller.abort(); controller = null; }
  streaming = false;
  if(interruptedReply)systemNotice('\u8d44\u6599\u91cd\u65b0\u9a8c\u8bc1\u672a\u901a\u8fc7\u6216\u5df2\u5931\u6548\uff0c\u5f53\u524d\u56de\u590d\u4e0e\u8bed\u97f3\u5df2\u505c\u6b62\u3002\u8bf7\u91cd\u65b0\u9a8c\u8bc1\u8d44\u6599\u540e\u518d\u64cd\u4f5c\uff1b\u4e0d\u4f1a\u81ea\u52a8\u91cd\u53d1\u6216\u91cd\u64ad\u3002');
  sendBtn.classList.remove('stop'); sendBtn.textContent = '发送';
  sendBtn.disabled = !settingsComplete();
  reportDataProgress();
}
function notifyArchiveChange(disabled) {
  if (disabled !== undefined) { try { localStorage.setItem('companion_archive_disabled', JSON.stringify(!!disabled)); } catch (_) {} }
  if (archiveBroadcast) archiveBroadcast.postMessage({invalidated:true});
  try { localStorage.setItem('companion_archive_invalidation', String(Date.now()) + ':' + Math.random()); } catch (_) {}
}
archiveOptions.origin = location.origin;
archiveOptions.crypto = crypto;
archiveOptions.fetch = function(url, options) { return fetch(url, options); };
archiveOptions.invalidate = invalidateArchivePage;
archiveOptions.notify = notifyArchiveChange;
archiveOptions.status = archiveStatus;
archiveOptions.progress = function(progress, epoch, owner) {
  archiveCache.check(epoch, owner);
  archiveProgress = progress;
  reportDataProgress();
};
function publishArchiveFailure(error, proof) {
  if(!proof||proof.epoch!==archiveCache.epoch||proof.owner!==archiveCache.operationOwner)return false;
  updateArchiveRevision('');
  dataReadyPhase='failed';
  // Only fixed diagnostic labels reach the UI; never expose response/error bodies.
  var known = {ARCHIVE_AUTHORITY:'AUTHORITY', ARCHIVE_REFRESH_REQUIRED:'REFRESH_REQUIRED',
    ARCHIVE_HASH:'HASH', ARCHIVE_JSON:'JSON', ARCHIVE_SHARD:'SHARD',
    ARCHIVE_KNOWLEDGE:'KNOWLEDGE', ARCHIVE_UNBOUND_KNOWLEDGE:'UNBOUND_KNOWLEDGE'};
  var resource = error && error.dataResource, code = error && error.dataCode;
  if (typeof resource !== 'string' || /[\r\n]/.test(resource) || !/^(?:archive|IDENTITY|MANIFEST|CONTEXT|MEMORY|TRANSCRIPTS|SHARD_[0-9]{4})$/.test(resource)) resource = 'archive';
  if (typeof code !== 'string' || /[\r\n]/.test(code) || !/^(?:HTTP_[1-5][0-9]{2}|HTTP|HTTP_OTHER|NETWORK|JSON|REDIRECT|TIMEOUT|FETCH_TIMEOUT|BODY_TIMEOUT|TRANSPORT_BLOCKED|AUTHORITY|REFRESH_REQUIRED|HASH|SHARD|KNOWLEDGE|UNBOUND_KNOWLEDGE|SCOPE|SCHEMA|BINDING|RELEASE|DUPLICATE|CRYPTO_UNAVAILABLE|CRYPTO_FAILED|CARD_HASH|VALIDATION)$/.test(code)) {
    code = error && typeof error.message === 'string' && Object.prototype.hasOwnProperty.call(known, error.message) ? known[error.message] : 'VALIDATION';
  }
  dataFailure(resource, code);
  reportDataProgress();return true;
}
archiveOptions.failed = publishArchiveFailure;
archiveOptions.disabledPreference = function() { return localStorage.getItem('companion_archive_disabled') === 'true'; };
archiveOptions.invalidationToken = function() { return localStorage.getItem('companion_archive_invalidation') || ''; };
function archiveResource(path) {
  return path === archiveOptions.contextPath ? 'CONTEXT' : /\/memories/.test(path) ? 'MEMORY' : /\/transcripts/.test(path) ? 'TRANSCRIPTS' : 'SHARD_' + path.match(/(\d{4})\.json$/)[1];
}
archiveOptions.transport = function(path) {
  return fetchDataJson(path + '?archive_epoch=' + archiveCache.epoch, archiveResource(path), true);
};
function checkArchiveScope(data, kind) {
  try { checkScope(data, kind); }
  catch (error) { error.authority = true; throw error; }
}
archiveOptions.validate = (function() {
  // These helpers shadow diagnostics inside this archive transaction only. A late
  // digest rejection cannot modify the page state owned by a newer preparation.
  var scopeError = false, memorySourceDigests = new Map();
  function dataFailure() {}
  function dataError(resource, code) { var error=new Error('ARCHIVE_' + resource + '_' + code);error.dataResource=resource;error.dataCode=code;return error; }
  __CACHE_LOCAL_VALIDATORS__
  function checkArchiveScope(data, kind) {
    try { checkScope(data, kind); } catch(error) {
      error.authority = true; error.dataCode = error.dataCode || 'SCOPE'; throw error;
    }
  }
  return async function(path, data) {
  try {
  if (path === archiveOptions.contextPath) { checkArchiveScope(data, 'context'); return; }
  if (/\/messages-/.test(path)) {
    if (!Array.isArray(data)) throw new Error('ARCHIVE_SHARD');
    data.forEach(function(row) { checkArchiveScope(row, 'message'); }); return;
  }
  checkArchiveScope(data, 'knowledge');
  if (!Array.isArray(data.entries)) throw new Error('ARCHIVE_KNOWLEDGE');
  data.entries.forEach(function(row) { checkArchiveScope(row, 'knowledge'); });
  if (/\/memories/.test(path) && EXPECTED_SCOPE.memory_release) {
    try { return await validateMemoryRelease(data, true); }
    catch (error) { error.authority = true; throw error; }
  }
  else if (data.entries.length) throw new Error('ARCHIVE_UNBOUND_KNOWLEDGE');
  } catch (error) { error.dataResource = error.dataResource || archiveResource(path); throw error; }
  };
})();
var archiveCache = new globalThis.ArchiveDeviceCache.ArchiveDeviceCache(archiveOptions);
try { archiveCache.disabled = localStorage.getItem('companion_archive_disabled') === 'true'; } catch (_) {}
function remoteArchiveChange() {
  archiveCache.forget(false);
  try { archiveCache.disabled = localStorage.getItem('companion_archive_disabled') === 'true'; } catch (_) {}
  archiveStatus(archiveCache.disabled ? '另一页面已停用设备缓存；请重试准备，仍需联网验证和下载。' : '另一页面已清除或改变设备缓存，请重试准备；发送前仍会联网验证。');
}
if (archiveBroadcast) archiveBroadcast.onmessage = remoteArchiveChange;
window.addEventListener('storage', function(e) {
  if (e.key === 'companion_archive_invalidation' || e.key === 'companion_archive_disabled') remoteArchiveChange();
});
// Every observed return invalidates immediately, even if departure was not observed.
// Only automatic preparation is coalesced; no authority result is reused by a timer.
var archiveResumeTimer = null;
function cancelArchiveResume() {
  if (archiveResumeTimer !== null) clearTimeout(archiveResumeTimer);
  archiveResumeTimer = null;
}
function resumeArchivePage() {
  cancelArchiveResume();
  archiveReplyPaused=true;
  archiveLifecycleInvalidation=!sendPending && (streaming || !!voiceTurn || archiveReplyQueue.length>0);
  try { archiveCache.forget(); } finally { archiveLifecycleInvalidation=false; }
  if (document.hidden || !introAccepted) return;
  var epoch = archiveCache.epoch, owner = archiveCache.operationOwner, operation = archivePageOperation;
  archiveResumeTimer = setTimeout(function() {
    archiveResumeTimer = null;
    if (document.hidden || !introAccepted || epoch !== archiveCache.epoch ||
        owner !== archiveCache.operationOwner || operation !== archivePageOperation ||
        archivePagePending || sendPending) return;
    ensureDataReady();
  }, 0);
}
// Departure only cancels a scheduled preparation, preserving background audio policy.
window.addEventListener('pagehide', function(){cancelArchiveResume();archiveReplyPaused=true;});
window.addEventListener('pageshow', function(e) { if (e.persisted) resumeArchivePage(); });
document.addEventListener('visibilitychange', function() {
  if (document.hidden) { cancelArchiveResume(); archiveReplyPaused=true; } else resumeArchivePage();
});
window.addEventListener('online', function() {
  if (!document.hidden && introAccepted && dataReadyPhase === 'failed' && !archivePagePending) ensureDataReady();
});
// No memoized ready shortcut: every explicit preparation/send passes fresh authority.
ensureDataReady = function(forSend) {
  if (!introAccepted) return Promise.resolve(false);
  // Retire even an unloaded history click whose GET is still in flight.
  if(!forSend)suspendNativeVoice(false);
  if(forSend)archiveRememberSendCue(archivePageOperation);
  if (archivePagePending) {
    if (!forSend) return archivePagePending;
    // A welcome/retry terminal gate may have begun before this Send. Never reuse it.
    var waitingEpoch=archiveCache.epoch;
    return archivePagePending.then(function(ok) {
      if (!ok || waitingEpoch!==archiveCache.epoch || !introAccepted) return false;
      return ensureDataReady(true);
    });
  }
  if (!forSend && archiveCache.deferred) archiveCache.forget(false);
  // All fresh preparation, including explicit drawer retry, holds committed work.
  // Explicit verification also stops ongoing playback, without revoking the next
  // user Send's cue/activation or restarting any audio when verification finishes.
  archiveReplyPaused=true;
  var epoch = archiveCache.epoch, pageOperation = ++archivePageOperation, preparationGeneration = null;
  if(forSend)archiveRememberSendCue(pageOperation);else archiveSendCuePreparation=null;
  archiveProgress = null;
  updateArchiveRevision('');
  dataReadyPhase = 'loading'; reportDataProgress();
  var p = (forSend ? archiveCache.finishForSend() : archiveCache.prepare()).then(function(result) {
    preparationGeneration = result.generation;
    if (pageOperation !== archivePageOperation) throw new Error('ARCHIVE_SUPERSEDED');
    archiveCache.check(epoch);
    var context = result.files.get(archiveOptions.contextPath);
    var memoryPath = 'data/memories' + (EXPECTED_SCOPE.memory_release ? '-' + EXPECTED_SCOPE.memory_release.release_revision : '') + '.json';
    var memory = result.files.get(memoryPath), transcripts = result.files.get('data/transcripts.json');
    var digests = EXPECTED_SCOPE.memory_release ? result.validations.get(memoryPath) : new Map();
    if (pageOperation !== archivePageOperation) throw new Error('ARCHIVE_SUPERSEDED');
    archiveCache.check(epoch);
    // Commit the complete, freshly authorized snapshot in one synchronous step.
    systemPrompt = context.system_prompt; shards = context.message_shards.slice();
    shardCache = {}; shardStatus = {};
    shards.forEach(function(name) { shardCache[name] = result.files.get('data/' + name); shardStatus[name] = true; });
    knowledgeCache = {memories:memory.entries, transcripts:transcripts.entries};
    knowledgePieces = {memories:memory.entries, transcripts:transcripts.entries};
    memorySourceDigests = digests; contextLoaded = true; scopeError = false;
    dataFailures = Object.create(null);
    updateArchiveRevision(result.revision);
    result.files.forEach(function(data, path) { reportDataProgress(archiveResource(path), 'verified'); });
    archiveSendProof = forSend ? Object.freeze({epoch:archiveCache.epoch, owner:archiveCache.operationOwner, policy:JSON.stringify(archiveCache.readPolicy())}) : null;
    archiveProgress = {total:result.files.size, downloaded:result.files.size, verified:result.files.size};
    dataReadyPhase = 'ready'; reportDataProgress(); applySessionsCard(); updateChatState();
    if(archiveReplyPaused && archiveReplyRevision && archiveReplyRevision !== result.revision && (streaming || voiceTurn || archiveReplyQueue.length)) {
      invalidateArchivePage();dataReadyPhase='failed';reportDataProgress();return false;
    }
    archiveReplyRevision=result.revision;
    archiveReleaseReplies();
    return true;
  }).catch(function(error) {
    var failure=error&&error.failureProof;
    if(publishArchiveFailure(error,failure))return false;
    if (pageOperation !== archivePageOperation) return false;
    if (error && error.policy && epoch === archiveCache.epoch) {
      return archiveCache.cleanupFailure(preparationGeneration).then(function(cleanup) {
        if(cleanup.epoch===archiveCache.epoch&&cleanup.owner===archiveCache.operationOwner){
          dataReadyPhase='failed';dataFailure('archive','POLICY_CHANGED');
          archiveStatus(cleanup.cleared?'资料设置已改变，已清除本次事务的设备副本；请重新验证。':'资料设置已改变；已停止使用本页资料，未确认清除设备副本。');
          reportDataProgress();
        }
        return false;
      },function(){return false;});
    }
    if (epoch === archiveCache.epoch) { invalidateArchivePage(); dataReadyPhase = 'failed'; reportDataProgress(); }
    else if (!archivePagePending && dataReadyPhase === 'idle') { dataReadyPhase = 'failed'; reportDataProgress(); }
    return false;
  }).finally(function() { if (archivePagePending === p) archivePagePending = null; });
  archivePagePending = p; return p;
};
// This local proof is checked immediately before send effects and again at actual fetch.
// It does not claim an atomic transaction between another tab's storage and HTTP.
function checkArchiveSendProof(proof) {
  if (!proof || proof !== archiveSendProof || proof.policy !== JSON.stringify(archiveCache.readPolicy())) throw new Error('ARCHIVE_SEND_INVALIDATED');
  archiveCache.check(proof.epoch, proof.owner);
}
// init() used to load context unconditionally. The opt-in path must use the same gate.
loadContext = function() { return ensureDataReady(); };
loadShards = function() { return ensureDataReady(); };
loadKnowledge = function() { return ensureDataReady().then(function(ok) { return ok ? knowledgeCache : null; }); };
function stageComposerArchive() {
  if (!introAccepted || document.hidden || document.activeElement !== inputText || !inputText.value.trim() ||
      sendPending || streaming || archivePagePending || !settingsComplete()) return;
  archiveCache.stageForSend();
}
inputText.addEventListener('focus', stageComposerArchive);
inputText.addEventListener('input', stageComposerArchive);
function addArchiveControls(parent) {
  if (!parent) return;
  var section = document.createElement('section'); section.className = 'archive-cache-controls';
  section.innerHTML = '<p><strong>设备档案副本 · 应用 __APP_RELEASE__</strong></p><p class="archive-cache-revision">资料版本待核验</p><p>资料版本以当前已核验清单为准。</p><p class="archive-cache-status" role="status"></p>' +
    '<p>此浏览器会保留已编译的夫妻聊天档案和记忆资料。浏览器清理、无痕模式或空间不足可能移除副本。每次使用仍需联网和当前访问权限。</p>' +
    '<p>本缓存不保存新对话、草稿、历史会话或音频；现有会话记录规则不变。权限失效后会尝试清除副本，无法保证浏览器未打开时远程删除。</p>' +
    '<label><input type="checkbox" class="archive-cache-enabled"> 在这台设备保留档案副本</label>' +
    '<button type="button" class="archive-cache-clear">清除设备档案副本</button>' +
    '<button type="button" class="archive-cache-retry">重新验证并准备档案</button>';
  var status = section.querySelector('.archive-cache-status'), toggle = section.querySelector('.archive-cache-enabled');
  archiveStatusNodes.push(status); archiveToggleNodes.push(toggle);
  toggle.checked = !archiveCache.disabled;
  toggle.addEventListener('change', function() { archiveCache.clear(!toggle.checked).catch(function() {}); });
  section.querySelector('.archive-cache-clear').addEventListener('click', function() { archiveCache.clear().catch(function() {}); });
  section.querySelector('.archive-cache-retry').addEventListener('click', function() { ensureDataReady(); });
  parent.appendChild(section); status.textContent = archiveStatusText;
}
addArchiveControls(document.querySelector('#intro-card .ic-box'));
addArchiveControls(document.getElementById('drawer'));

subscribeDataProgress(function(p) { archiveStatus(dataProgressText(p)); });
