#!/usr/bin/env python3
"""Build companion.html - merged avatar face + chat brain page (8A-2a)."""

import argparse
import os
import re
import sys

_PERSON_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]*$')

TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>陪伴</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    background: #1a1a2e; color: #e0e0e0; height: 100vh; overflow: hidden;
    display: flex; flex-direction: column;
  }
  header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 8px 16px; background: #16213e; border-bottom: 1px solid #2a2a4a;
    flex-shrink: 0;
  }
  header .title { font-size: 18px; font-weight: 600; color: #f0d9b5; }
  header .subtitle { font-size: 12px; color: #8888aa; }
  #settings-btn {
    background: none; border: 1px solid #444; color: #aaa; border-radius: 6px;
    padding: 4px 10px; cursor: pointer; font-size: 16px;
  }
  #settings-btn:hover { border-color: #888; color: #fff; }
  #face-section {
    flex-shrink: 0; text-align: center; padding: 8px 0 0; background: #1a1a2e;
  }
  #face-frame {
    border: none; width: 100%; height: 300px; display: block; margin: 0 auto;
  }
  .face-note { font-size: 11px; color: #666; padding: 2px 0 8px; }
  #chat {
    flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 8px;
  }
  .bubble {
    max-width: 85%; padding: 8px 12px; border-radius: 12px; line-height: 1.5;
    font-size: 14px; white-space: pre-wrap; word-wrap: break-word;
  }
  .bubble.user { align-self: flex-end; background: #2d4a7a; color: #fff; }
  .bubble.subject {
    align-self: flex-start; background: #222244; color: #ddd;
    display: flex; gap: 8px; align-items: flex-start;
  }
  .bubble.notice {
    align-self: center; background: #333355; color: #aaa; font-size: 12px;
    padding: 6px 12px; max-width: 90%;
  }
  .bubble.center {
    align-self: center; background: none; color: #666; font-size: 13px;
  }
  .bubble-avatar {
    width: 32px; height: 32px; border-radius: 50%; object-fit: cover;
    background: #333; flex-shrink: 0;
  }
  #input-bar {
    flex-shrink: 0; display: flex; gap: 8px; padding: 8px 12px;
    background: #16213e; border-top: 1px solid #2a2a4a;
  }
  #input-text {
    flex: 1; background: #222244; border: 1px solid #333; border-radius: 8px;
    color: #e0e0e0; padding: 8px 10px; font-size: 14px; resize: none; outline: none;
    min-height: 36px; max-height: 120px; line-height: 1.4; font-family: inherit;
  }
  #input-text:focus { border-color: #5566aa; }
  #send-btn {
    background: #2d4a7a; border: none; color: #fff; border-radius: 8px;
    padding: 0 20px; font-size: 14px; cursor: pointer; font-weight: 600;
    min-width: 64px; flex-shrink: 0;
  }
  #send-btn:disabled { background: #333355; color: #666; cursor: default; }
  #send-btn.stop { background: #6a2d2d; }
  #drawer-overlay {
    position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5);
    display: none; z-index: 99;
  }
  #drawer-overlay.open { display: block; }
  #drawer {
    position: fixed; top: 0; right: -320px; width: 300px; height: 100%;
    background: #1a1a2e; border-left: 1px solid #2a2a4a; transition: right 0.25s ease;
    padding: 20px; z-index: 100; display: flex; flex-direction: column; gap: 10px;
    overflow-y: auto;
  }
  #drawer.open { right: 0; }
  #drawer h3 { color: #f0d9b5; margin-bottom: 4px; }
  #drawer label { font-size: 12px; color: #8888aa; display: block; margin-bottom: 2px; }
  #drawer select, #drawer input {
    width: 100%; background: #222244; border: 1px solid #333; color: #e0e0e0;
    padding: 8px; border-radius: 6px; font-size: 13px; outline: none;
  }
  #drawer select:focus, #drawer input:focus { border-color: #5566aa; }
  #save-btn {
    background: #2d4a7a; border: none; color: #fff; border-radius: 8px;
    padding: 10px; font-size: 14px; cursor: pointer; font-weight: 600; margin-top: 8px;
  }
  .drawer-close {
    position: absolute; top: 10px; right: 12px; background: none; border: none;
    color: #8888aa; font-size: 20px; cursor: pointer;
  }
</style>
</head>
<body>

<header>
  <span class="title">陪伴</span>
  <span class="subtitle">数字档案 · 模拟对话 · 非本人</span>
  <button id="settings-btn" title="设置">⚙</button>
</header>

<section id="face-section">
  <iframe id="face-frame" src="avatar.html" title="她" scrolling="no"></iframe>
  <div class="face-note">合成语音 · 非本人原声</div>
</section>

<div id="chat"></div>

<div id="input-bar">
  <textarea id="input-text" rows="1" placeholder="想对她说些什么…"></textarea>
  <button id="send-btn" disabled>发送</button>
</div>

<div id="drawer-overlay"></div>
<div id="drawer">
  <button class="drawer-close" id="drawer-close-btn">×</button>
  <h3>配置接口</h3>
  <div>
    <label>服务商</label>
    <select id="cfg-provider">
      <option value="openai">OpenAI 兼容（DeepSeek 等）</option>
      <option value="anthropic">Claude 官方（Anthropic）</option>
    </select>
  </div>
  <div>
    <label>接口地址</label>
    <input id="cfg-url" type="text" placeholder="https://api.deepseek.com/chat/completions（任意 OpenAI 兼容端点）">
  </div>
  <div>
    <label>模型</label>
    <input id="cfg-model" type="text" placeholder="例如 deepseek-v4-flash">
  </div>
  <div>
    <label>API Key</label>
    <input id="cfg-key" type="password" placeholder="sk-...">
  </div>
  <button id="save-btn">保存并开始</button>
</div>

<script>
(function(){
'use strict';

var storageKey = '__STORAGE_KEY__';
var THE_STOP_SET = new Set(["的了","了 的","我们","你们","他们","这个","那个","什么","怎么","不是","就是","还是","但是","所以","因为","如果","可以","没有","知道","现在","时候","一个","有点","这样","那样"].map(function(t){return t.replace(/ /g,'');}));

/* ===== DOM refs ===== */
var chat = document.getElementById('chat');
var inputText = document.getElementById('input-text');
var sendBtn = document.getElementById('send-btn');
var settingsBtn = document.getElementById('settings-btn');
var drawer = document.getElementById('drawer');
var drawerOverlay = document.getElementById('drawer-overlay');
var saveBtn = document.getElementById('save-btn');
var cfgProvider = document.getElementById('cfg-provider');
var cfgUrl = document.getElementById('cfg-url');
var cfgModel = document.getElementById('cfg-model');
var cfgKey = document.getElementById('cfg-key');
var drawerCloseBtn = document.getElementById('drawer-close-btn');
var frame = document.getElementById('face-frame');

/* ===== state ===== */
var systemPrompt = '';
var shards = [];
var shardCache = {};
var shardStatus = {};
var history = [];
var controller = null;
var streaming = false;
var shardsLoading = false;
var knowledgeCache = null;
var knowledgeLoading = false;
var ttsBase = location.protocol + '//' + location.hostname + ':8022';
var ttsAvailable = false;
var settings = {url:'', model:'', key:'', provider:'openai'};
var companionVoiceUrls = [];
var faceReady = false;
var contextLoaded = false;
var sendPending = false;

/* ===== helpers ===== */
function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
function loadSettings() {
  try {
    var raw = localStorage.getItem(storageKey);
    if (raw) {
      var parsed = JSON.parse(raw);
      settings = { url: parsed.url || '', model: parsed.model || '', key: parsed.key || '', provider: parsed.provider || 'openai' };
    } else { settings = {url:'', model:'', key:'', provider:'openai'}; }
  } catch(e) { settings = {url:'', model:'', key:'', provider:'openai'}; }
}
function settingsComplete() { return settings && settings.url && settings.model && settings.key; }
function saveSettings() {
  settings = {url: cfgUrl.value.trim(), model: cfgModel.value.trim(), key: cfgKey.value.trim(), provider: cfgProvider.value};
  try { localStorage.setItem(storageKey, JSON.stringify(settings)); } catch(e) {}
  closeDrawer(); updateChatState();
}
function openDrawer() {
  cfgProvider.value = settings.provider; cfgUrl.value = settings.url; cfgModel.value = settings.model; cfgKey.value = settings.key;
  updatePlaceholders(); drawer.classList.add('open'); drawerOverlay.classList.add('open');
}
function closeDrawer() { drawer.classList.remove('open'); drawerOverlay.classList.remove('open'); }
function updatePlaceholders() {
  if (cfgProvider.value === 'anthropic') {
    cfgUrl.placeholder = 'https://api.anthropic.com/v1/messages'; cfgModel.placeholder = '例如 claude-opus-5'; cfgKey.placeholder = 'sk-ant-...';
  } else {
    cfgUrl.placeholder = 'https://api.deepseek.com/chat/completions（任意 OpenAI 兼容端点）'; cfgModel.placeholder = '例如 deepseek-v4-flash'; cfgKey.placeholder = 'sk-...';
  }
}
function clearChat() { chat.innerHTML = ''; }
function addBubble(opts) {
  var div = document.createElement('div');
  if (opts.type === 'user') { div.className = 'bubble user'; div.textContent = opts.text; }
  else if (opts.type === 'subject') {
    div.className = 'bubble subject';
    var av = document.createElement('img'); av.className = 'bubble-avatar'; av.alt = ''; av.src = 'data/avatar/avatar.png'; av.onerror = function(){ this.remove(); };
    var contentWrap = document.createElement('div'); contentWrap.className = 'bubble-content'; contentWrap.textContent = opts.text;
    div.appendChild(av); div.appendChild(contentWrap);
  } else if (opts.type === 'notice') { div.className = 'bubble notice'; div.textContent = opts.text; }
  else { div.className = 'bubble center'; div.textContent = opts.text; }
  chat.appendChild(div); chat.scrollTop = chat.scrollHeight; return div;
}
function confNotice() { clearChat(); addBubble({type:'center', text:'点右上角 ⚙ 配置接口后开始对话'}); sendBtn.disabled = true; }
function systemNotice(msg) { addBubble({type:'notice', text: msg}); }
function updateChatState() {
  if (!settingsComplete()) { confNotice(); return; }
  if (!contextLoaded) { clearChat(); addBubble({type:'center', text:'档案加载中，请稍候…'}); sendBtn.disabled = true; return; }
  if (chat.children.length === 0) { addBubble({type:'center', text:'开始对话吧...'}); }
  sendBtn.disabled = false; sendBtn.textContent = '发送'; streaming = false;
  if (controller) { try { controller.abort(); } catch(e) {} controller = null; }
}

/* ===== pure functions ===== */
function extractTokens(text) {
  var tokens = []; var seen = {}; var cjkRe = /[\u4e00-\u9fff]+/g; var m;
  while ((m = cjkRe.exec(text)) !== null) {
    var run = m[0];
    for (var i = 0; i < run.length - 1; i++) {
      var tok = run.substr(i, 2);
      if (tok[0] === tok[1]) continue;
      if (THE_STOP_SET.has(tok)) continue;
      var key = 'c' + tok;
      if (!seen[key]) { seen[key] = true; tokens.push(tok); }
    }
  }
  var wordRe = /[a-z0-9]{2,}/g;
  while ((m = wordRe.exec(text.toLowerCase())) !== null) {
    var w = m[0];
    if (w[0] === w[1]) continue;
    var key2 = 'w' + w;
    if (!seen[key2]) { seen[key2] = true; tokens.push(w); }
  }
  return tokens;
}
function scoreText(tokens, text) {
  var score = 0; var lower = text.toLowerCase();
  for (var i = 0; i < tokens.length; i++) {
    var tok = tokens[i]; var idx = 0;
    while (true) { idx = lower.indexOf(tok, idx); if (idx === -1) break; score++; idx += tok.length; }
  }
  return score;
}
function retrieveSnippets(tokens, records, opts) {
  opts = opts || {}; var top = opts.top || 6; var results = [];
  for (var i = 0; i < records.length; i++) {
    var rec = records[i];
    if (rec.content_type !== 'text') continue;
    var txt = (rec.text || '').trim(); if (!txt) continue;
    var score = scoreText(tokens, txt); if (score <= 0) continue;
    results.push({ date: String(rec.timestamp || '').substring(0, 10), text: txt.length > 200 ? txt.substring(0, 200) : txt, score: score, isSubject: rec.sender === 'subject' });
  }
  results.sort(function(a, b) {
    if (b.score !== a.score) return b.score - a.score;
    if (a.isSubject !== b.isSubject) return a.isSubject ? -1 : 1;
    return a.text.length - b.text.length;
  });
  return results.slice(0, top).map(function(r) { return {date: r.date, text: r.text, score: r.score}; });
}
function retrieveKnowledge(tokens, memories, transcripts, opts) {
  opts = opts || {}; var memTop = opts.memTop || 3; var transTop = opts.transTop || 2;
  var mem = []; var i, e, score, txt; memories = memories || []; transcripts = transcripts || [];
  for (i = 0; i < memories.length; i++) {
    e = memories[i];
    var title = String(e.title || '').trim();
    var texts = Array.isArray(e.texts) ? e.texts : [];
    var hay = title + '\n' + texts.join('\n');
    if (!hay.trim()) continue;
    score = scoreText(tokens, hay); if (score <= 0) continue;
    var body = String(texts[0] || '').trim();
    txt = title + (body ? ' — ' + body : '');
    if (txt.length > 240) txt = txt.substring(0, 240);
    mem.push({label: '[家人确认记忆 Tier-1]', date: String(e.date || ''), text: txt, score: score});
  }
  mem.sort(function(a, b) { return b.score - a.score; }); mem = mem.slice(0, memTop);
  var trans = [];
  for (i = 0; i < transcripts.length; i++) {
    e = transcripts[i];
    txt = String(e.text || '').trim(); if (!txt) continue;
    score = scoreText(tokens, txt); if (score <= 0) continue;
    if (txt.length > 200) txt = txt.substring(0, 200);
    var lbl = e.media === 'video' ? '[视频转写 Tier-2]' : '[语音转写 Tier-2]';
    trans.push({label: lbl, date: String(e.date || ''), text: txt, score: score});
  }
  trans.sort(function(a, b) { return b.score - a.score; }); trans = trans.slice(0, transTop);
  return {memories: mem, transcripts: trans};
}
function buildRetrievalBlock(snippets) {
  if (!snippets || snippets.length === 0) return '';
  var lines = [];
  for (var i = 0; i < snippets.length; i++) {
    lines.push((snippets[i].label || '[档案检索 Tier-2]') + ' ' + snippets[i].date + ' · ' + snippets[i].text);
  }
  var block = lines.join('\n'); var budget = 2200;
  if (block.length <= budget) return block;
  var out = '';
  for (var j = 0; j < lines.length; j++) {
    if (out.length + (out ? 1 : 0) + lines[j].length > budget) break;
    out += (out ? '\n' : '') + lines[j];
  }
  return out;
}
function buildMessages(systemPrompt, history, retrievalBlock, userText) {
  var messages = [{role:'system', content: systemPrompt}];
  var recent = history.slice(-12);
  for (var i = 0; i < recent.length; i++) { messages.push({role: recent[i].role, content: recent[i].content}); }
  var content = retrievalBlock ? retrievalBlock + '\n\n' + userText : userText;
  messages.push({role:'user', content: content});
  return messages;
}
function splitSystem(messages) {
  var msgs = messages || [];
  if (msgs.length && msgs[0] && msgs[0].role === 'system') { return { system: String(msgs[0].content || ''), messages: msgs.slice(1) }; }
  return { system: '', messages: msgs.slice() };
}

/* ===== SSE ===== */
function sseCreate(mode) { return { buffer: '', sawData: false, done: false, mode: mode === 'anthropic' ? 'anthropic' : 'openai' }; }
function sseFeed(state, chunkText) {
  var deltas = []; if (state.done) return deltas;
  state.buffer += chunkText || ''; var lines = state.buffer.split('\n'); state.buffer = lines.pop() || '';
  for (var i = 0; i < lines.length; i++) {
    var line = lines[i];
    if (line.charAt(line.length - 1) === '\r') line = line.substring(0, line.length - 1);
    var extra = sseProcessLine(state, line); deltas = deltas.concat(extra); if (state.done) break;
  }
  return deltas;
}
function sseFinish(state) {
  var deltas = []; if (state.done) { state.buffer = ''; return deltas; }
  var line = state.buffer; state.buffer = '';
  if (line) { if (line.charAt(line.length - 1) === '\r') line = line.substring(0, line.length - 1); deltas = sseProcessLine(state, line); }
  return deltas;
}
function sseProcessLine(state, line) {
  var deltas = []; if (state.done) return deltas;
  if (line.indexOf('data:') !== 0) return deltas;
  state.sawData = true; var data = line.substring(5).trim();
  if (data === '[DONE]') { state.done = true; return deltas; }
  try {
    var obj = JSON.parse(data);
    if (state.mode === 'anthropic') {
      if (obj.type === 'content_block_delta' && obj.delta && obj.delta.type === 'text_delta' && obj.delta.text) deltas.push(obj.delta.text);
      if (obj.type === 'message_stop') state.done = true;
    } else {
      var delta = obj.choices && obj.choices[0] && obj.choices[0].delta && obj.choices[0].delta.content;
      if (delta) deltas.push(delta);
    }
  } catch(e) {}
  return deltas;
}

/* ===== data loading ===== */
function loadShards() {
  if (shardsLoading) return Promise.resolve(); shardsLoading = true;
  var names = shards || []; var loadedCount = 0; var failedCount = 0;
  var fetches = names.map(function(name) {
    if (shardStatus[name] === 'failed') return;
    var safeName = String(name).replace(/[^a-zA-Z0-9_/.-]/g, '_');
    return fetch('data/' + safeName)
      .then(function(r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function(data) { shardCache[name] = Array.isArray(data) ? data : [data]; shardStatus[name] = true; loadedCount++; })
      .catch(function() { shardStatus[name] = 'failed'; failedCount++; });
  });
  return Promise.all(fetches).then(function() { shardsLoading = false; });
}
function loadKnowledge() {
  if (knowledgeLoading || knowledgeCache !== null) return Promise.resolve(knowledgeCache);
  knowledgeLoading = true; var out = {memories: [], transcripts: []};
  var one = function(name, key) {
    return fetch('data/' + name)
      .then(function(r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function(data) { if (data && Array.isArray(data.entries)) out[key] = data.entries; })
      .catch(function() {});
  };
  return Promise.all([one('memories.json', 'memories'), one('transcripts.json', 'transcripts')])
    .then(function() { knowledgeCache = out; knowledgeLoading = false; return out; });
}
function collectAllRecords() {
  var all = []; for (var name in shardCache) { if (shardCache[name]) all = all.concat(shardCache[name]); } return all;
}

/* ===== streamRequest（唯一改动：openai 分支 reqBody 后加 deepseek thinking:disabled）===== */
function streamRequest(messages, onDelta, onDone, onError) {
  if (!settingsComplete()) { onError('请先在设置中配置接口'); return; }
  controller = new AbortController(); streaming = true; sendBtn.textContent = '停止'; sendBtn.classList.add('stop');
  var endpoint = settings.url;
  if (!/^https?:\/\//i.test(endpoint)) { onError('接口地址格式不正确'); return; }
  var acc = ''; var fallbackText = ''; var isAnthropic = settings.provider === 'anthropic';
  var sseState = sseCreate(isAnthropic ? 'anthropic' : 'openai'); var reqHeaders; var reqBody;
  if (isAnthropic) {
    var sp = splitSystem(messages);
    reqHeaders = { 'Content-Type': 'application/json', 'x-api-key': settings.key, 'anthropic-version': '2023-06-01', 'anthropic-dangerous-direct-browser-access': 'true' };
    reqBody = {model: settings.model, max_tokens: 2048, stream: true, messages: sp.messages};
    if (sp.system) reqBody.system = sp.system;
  } else {
    reqHeaders = { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + settings.key };
    reqBody = {model: settings.model, messages: messages, stream: true};
    if (/deepseek/i.test(endpoint)) { reqBody.thinking = {type: 'disabled'}; }
  }
  fetch(endpoint, { method: 'POST', headers: reqHeaders, body: JSON.stringify(reqBody), signal: controller.signal })
  .then(function(resp) {
    if (!resp.ok) { return resp.text().then(function(t) { var snippet = t.substring(0, 200); throw new Error('接口错误 ' + resp.status + '：' + snippet); }); }
    var reader = resp.body.getReader(); var decoder = new TextDecoder('utf-8');
    function readChunk() {
      return reader.read().then(function(result) {
        if (result.done) {
          var tail = decoder.decode(); if (tail) fallbackText += tail;
          var finalDeltas = sseFeed(sseState, tail);
          for (var i = 0; i < finalDeltas.length; i++) { acc += finalDeltas[i]; onDelta(finalDeltas[i]); }
          finalDeltas = sseFinish(sseState);
          for (var j = 0; j < finalDeltas.length; j++) { acc += finalDeltas[j]; onDelta(finalDeltas[j]); }
          if (!sseState.sawData && fallbackText && fallbackText.trim()) {
            try {
              var json = JSON.parse(fallbackText);
              var content = (json.choices && json.choices[0] && json.choices[0].message && json.choices[0].message.content) || '';
              if (!content && Array.isArray(json.content)) {
                var textParts = [];
                for (var p = 0; p < json.content.length; p++) { if (json.content[p] && json.content[p].type === 'text' && json.content[p].text) textParts.push(json.content[p].text); }
                content = textParts.join('');
              }
              if (content) { acc += content; onDelta(content); }
            } catch(e) {}
          }
          onDone(acc, controller.signal.aborted);
          return;
        }
        var text = decoder.decode(result.value, {stream: true}); if (text) fallbackText += text;
        var deltas = sseFeed(sseState, text);
        for (var k = 0; k < deltas.length; k++) { acc += deltas[k]; onDelta(deltas[k]); }
        return readChunk();
      });
    }
    return readChunk();
  })
  .catch(function(err) { if (err.name === 'AbortError') { onDone(acc, true); } else { onError(err.message || '网络错误'); } });
}

/* ===== probeTts ===== */
function probeTts() { fetch(ttsBase + '/health', {method:'GET'}).then(function(r){ ttsAvailable = !!r.ok; }).catch(function(){ ttsAvailable = false; }); }

/* ===== sendMessage ===== */
function sendMessage() {
  if (streaming) {
    if (controller) { controller.abort(); }
    return;
  }
  if (sendPending) return;
  if (!settingsComplete()) { return; }
  if (!contextLoaded) { return; }
  if (!inputText.value.trim()) return;
  var userText = inputText.value.trim();
  inputText.value = ''; autoGrow();
  addBubble({type:'user', text: userText});
  history.push({role:'user', content: userText});

  var subjectBubble = addBubble({type:'subject', text: '…'});
  var contentEl = subjectBubble.querySelector('.bubble-content');

  function run() {
    sendPending = false;
    var allRecords = collectAllRecords();
    var tokens = extractTokens(userText);
    var snippets = retrieveSnippets(tokens, allRecords, {top: 6});
    var kld = retrieveKnowledge(tokens, (knowledgeCache||{}).memories, (knowledgeCache||{}).transcripts, {memTop: 3, transTop: 2});
    var combined = kld.memories.concat(snippets, kld.transcripts);
    var retrievalBlock = buildRetrievalBlock(combined);
    var messages = buildMessages(systemPrompt, history, retrievalBlock, userText);

    var accText = '';
    streamRequest(messages, function(delta) {
      accText += delta;
      contentEl.textContent = accText;
      chat.scrollTop = chat.scrollHeight;
    }, function(finalText, aborted) {
      sendBtn.disabled = false;
      sendBtn.classList.remove('stop');
      sendBtn.textContent = '发送';
      streaming = false;
      controller = null;
      if (aborted) {
        history.push({role: 'assistant', content: accText});
        return;
      }
      contentEl.textContent = finalText;
      history.push({role: 'assistant', content: finalText});
      chat.scrollTop = chat.scrollHeight;
      // TODO 8A-2b: 关窗道别语、空闲「去忙了」、rhythm.json 限速、使用统计自见卡

      // TTS: 合成她的声音，路由进 iframe 的 audio#player
      if (ttsAvailable && finalText && finalText.length > 0 && finalText.length <= 120) {
        fetch(ttsBase + '/tts', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({text: finalText, lang: 'mandarin'})
        })
        .then(function(r) { if (!r.ok) throw new Error('tts ' + r.status); return r.blob(); })
        .then(function(b) { speakBlob(b); })
        .catch(function() { /* 合成失败：保持文字气泡，不打断 */ });
      }
    }, function(err) {
      sendBtn.disabled = false;
      sendBtn.classList.remove('stop');
      sendBtn.textContent = '发送';
      streaming = false;
      controller = null;
      contentEl.textContent = '（出错了：' + (err || '未知错误') + '）';
    });
  }

  sendPending = true;
  var needShards = !shardsLoading && Object.keys(shardCache).length === 0;
  var needKnowledge = !knowledgeLoading && knowledgeCache === null;
  if (needShards || needKnowledge) {
    Promise.all([
      needShards ? loadShards() : Promise.resolve(),
      needKnowledge ? loadKnowledge() : Promise.resolve()
    ]).then(run);
  } else {
    run();
  }
}

/* ===== 输入框自动增长 ===== */
function autoGrow() {
  inputText.style.height = 'auto';
  inputText.style.height = (inputText.scrollHeight > 120 ? 120 : inputText.scrollHeight) + 'px';
}

/* ===== iframe 集成 ===== */
function speakBlob(blob) {
  var url = URL.createObjectURL(blob);
  companionVoiceUrls.push(url);
  if (companionVoiceUrls.length > 50) {
    try { URL.revokeObjectURL(companionVoiceUrls.shift()); } catch(e) {}
  }
  var played = false;
  try {
    var p = frame.contentWindow.document.getElementById('player');
    if (p) {
      p.src = url;
      var pr = p.play();
      if (pr && pr.catch) pr.catch(function(){});
      played = true;
    }
  } catch(e) { played = false; }
  if (!played) {
    // 跨源/缺元素降级：仅播声，不驱动嘴
    try { var a = new Audio(url); a.play(); } catch(e2) {}
  }
}

/* ===== init ===== */
function init() {
  // face-frame load 接线
  frame.addEventListener('load', function() {
    try {
      var doc = frame.contentWindow.document;
      var st = doc.createElement('style');
      st.textContent = '.now-playing,.controls,.playlist,footer{display:none!important;} main{padding:0!important;justify-content:center;min-height:auto;} body{background:transparent!important;overflow:hidden;}';
      doc.head.appendChild(st);
      faceReady = true;
    } catch(e) { faceReady = false; /* 跨源等异常：降级仅播声不驱动嘴 */ }
  });

  // file:// 拦截提示
  if (location.protocol === 'file:') {
    addBubble({type:'notice', text:'本页需通过本地服务器打开：双击档案目录里的 start_server.bat，然后浏览器访问 http://localhost:8020/ 。直接双击 HTML 无法加载档案数据与脸。'});
    sendBtn.disabled = true;
    return;
  }

  loadSettings();
  probeTts();

  // 从 chat_context.json 载入 systemPrompt + shards
  fetch('data/chat_context.json')
    .then(function(r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(function(data) {
      systemPrompt = data.system_prompt || '';
      shards = Array.isArray(data.message_shards) ? data.message_shards : [];
      contextLoaded = true;
      updateChatState();
    })
    .catch(function(err) {
      clearChat();
      addBubble({type:'notice', text:'档案加载失败：' + err.message});
      sendBtn.disabled = true;
    });

  // 输入框 auto-grow
  inputText.addEventListener('input', autoGrow);

  // 发送按钮 / Enter 发送
  sendBtn.addEventListener('click', sendMessage);
  inputText.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  // 抽屉接线
  settingsBtn.addEventListener('click', openDrawer);
  drawerOverlay.addEventListener('click', closeDrawer);
  drawerCloseBtn.addEventListener('click', closeDrawer);
  saveBtn.addEventListener('click', saveSettings);
  cfgProvider.addEventListener('change', updatePlaceholders);
}

init();

// window 导出（供 harness）
window.extractTokens = extractTokens;
window.scoreText = scoreText;
window.retrieveSnippets = retrieveSnippets;
window.retrieveKnowledge = retrieveKnowledge;
window.loadKnowledge = loadKnowledge;
window.buildRetrievalBlock = buildRetrievalBlock;
window.buildMessages = buildMessages;

})();
</script>
</body>
</html>
"""


def build(person: str, archive_dir: str) -> str:
    """Render companion.html content."""
    storage_key = 'companion_' + person + '_byok'
    html = TEMPLATE.replace('__STORAGE_KEY__', storage_key)
    return html


def main() -> int:
    parser = argparse.ArgumentParser(description='Build companion.html page (8A-2a)')
    parser.add_argument('--person', required=True, help='Person slug')
    parser.add_argument('--archive-dir', default='archive_out', help='Archive directory (default: archive_out)')
    args = parser.parse_args()

    if not _PERSON_RE.match(args.person):
        print(f'错误：--person 参数 "{args.person}" 不符合正则 ^[a-zA-Z0-9][a-zA-Z0-9_-]*$', file=sys.stderr)
        return 2

    context_path = os.path.join(args.archive_dir, 'data', 'chat_context.json')
    if not os.path.exists(context_path):
        print(f'错误：缺少 {context_path}（data/chat_context.json 不存在）', file=sys.stderr)
        return 1

    html = build(args.person, args.archive_dir)

    out_path = os.path.join(args.archive_dir, 'companion.html')
    tmp_path = out_path + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8', newline='') as f:
        f.write(html)
    os.replace(tmp_path, out_path)

    byte_count = os.path.getsize(out_path)
    print(f'已生成 {out_path}（{byte_count} 字节）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
