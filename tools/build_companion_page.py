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
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
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
  .time-divider { align-self: center; color: #666; font-size: 11px; margin: 6px 0 2px; }
  .typing-dots i { display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: #8888aa; margin: 0 2px; animation: typing-blink 1.2s infinite; }
  .typing-dots i:nth-child(2) { animation-delay: 0.2s; }
  .typing-dots i:nth-child(3) { animation-delay: 0.4s; }
  @keyframes typing-blink { 0%, 80%, 100% { opacity: 0.25; } 40% { opacity: 1; } }
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
  #drawer .cfg-hint { font-size: 11px; color: #7788aa; margin: 4px 0 8px; line-height: 1.5; min-height: 1em; }
  #save-btn {
    background: #2d4a7a; border: none; color: #fff; border-radius: 8px;
    padding: 10px; font-size: 14px; cursor: pointer; font-weight: 600; margin-top: 8px;
  }
  .drawer-close {
    position: absolute; top: 10px; right: 12px; background: none; border: none;
    color: #8888aa; font-size: 20px; cursor: pointer;
  }
  * { -webkit-tap-highlight-color: transparent; }
  html, body { height: 100vh; height: 100dvh; }
  #input-text { font-size: 16px; }   /* iOS 聚焦防自动放大 */
  #input-bar { padding-bottom: calc(8px + env(safe-area-inset-bottom)); }
  .play-voice-btn {
    display: inline-flex; align-items: center; gap: 6px; margin-top: 6px;
    background: #2d4a7a; color: #fff; border: none; border-radius: 14px;
    padding: 5px 14px; font-size: 13px; cursor: pointer;
  }
  .play-voice-btn:active { background: #3a5c96; }
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
      <option value="openai">OpenAI</option>
      <option value="anthropic">Anthropic（Claude）</option>
      <option value="deepseek">DeepSeek</option>
      <option value="kimi">Kimi（Moonshot）</option>
      <option value="custom">自定义（OpenAI 兼容端点）</option>
    </select>
    <div class="cfg-hint" id="cfg-hint"></div>
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
var sessionId = buildSessionId(new Date());
var sessionTurn = 0;
var sessionQueueKey = storageKey + '_sessionq';
var sessionFlushing = false;
var sessionStarted = false;
var lastMessageTs = null;
var TIME_DIVIDER_GAP_MS = 5 * 60 * 1000;
var SESSION_QUEUE_MAX = 500;
var voiceTurn = null;            /* 当前回复的呈现引擎状态 */
var playerEndedHooked = false;   /* iframe player 的 ended 监听只挂一次 */
var TTS_TOTAL_MAX = 240;         /* 全文超过此长度不走语音（分句后仍太长的失控回复） */
var SEG_FIRST_MAX = 24;          /* 首段目标上限（越短首声越快） */
var SEG_MAX = 42;                /* 后续段目标上限 */
var SEG_MIN = 6;                 /* 过短句并入相邻段 */
var activePlay = null;          /* 当前占用 iframe player 的回合（用于 ended 归属校验） */
var PROVIDERS = {
  openai: { url: 'https://api.openai.com/v1/chat/completions', model: 'gpt-5.6', keyPlaceholder: 'sk-...', hint: 'OpenAI 官方 Chat Completions 端点' },
  anthropic: { url: 'https://api.anthropic.com/v1/messages', model: 'claude-opus-5', keyPlaceholder: 'sk-ant-...', hint: '需要 console.anthropic.com 的 API 额度（Claude Max 订阅不含 API）' },
  deepseek: { url: 'https://api.deepseek.com/chat/completions', model: 'deepseek-v4-flash', keyPlaceholder: 'sk-...', hint: '追求更强可改模型为 deepseek-v4-pro' },
  kimi: { url: 'https://api.moonshot.cn/v1/chat/completions', model: 'kimi-k3', keyPlaceholder: 'sk-...', hint: '海外账号请把地址改为 https://api.moonshot.ai/v1/chat/completions；更省可改模型为 kimi-k2.6' },
  custom: { url: '', model: '', keyPlaceholder: '', hint: '任意 OpenAI 兼容端点（如本地 Ollama / LM Studio 的 /v1/chat/completions）' }
};
var DEFAULT_PROVIDER = 'deepseek';
var settings = {url:'', model:'', key:'', provider: DEFAULT_PROVIDER, profiles: {}};
var drawerProvider = DEFAULT_PROVIDER;
var draftProfiles = null;
var companionVoiceUrls = [];
var faceReady = false;
var contextLoaded = false;
var sendPending = false;
var audioUnlocked = false;
var SILENT_WAV = 'data:audio/wav;base64,UklGRmQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YUAAAACAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA';
var emotionsCfg = null;
var lastEmotion = null;
var emotionTimer = null;
var emotionImg = null;

/* ===== helpers ===== */
function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

function pad2(n) {
  return (n < 10 ? '0' : '') + n;
}

function buildSessionId(d) {
  var s = pad2(d.getFullYear()) + pad2(d.getMonth() + 1) + pad2(d.getDate()) + '-' + pad2(d.getHours()) + pad2(d.getMinutes()) + pad2(d.getSeconds()) + '-';
  var chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  for (var i = 0; i < 6; i += 1) {
    s += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return s;
}

function isoLocal(d) {
  var off = d.getTimezoneOffset();
  var sign = off <= 0 ? '+' : '-';
  var abs = Math.abs(off);
  var hh = pad2(Math.floor(abs / 60));
  var mm = pad2(abs % 60);
  return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate()) + 'T' + pad2(d.getHours()) + ':' + pad2(d.getMinutes()) + ':' + pad2(d.getSeconds()) + sign + hh + ':' + mm;
}

function formatTimeLabel(ts, nowTs) {
  var d = new Date(ts);
  var n = new Date(nowTs);
  var hm = pad2(d.getHours()) + ':' + pad2(d.getMinutes());
  var dStart = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  var nStart = new Date(n.getFullYear(), n.getMonth(), n.getDate()).getTime();
  if (dStart === nStart) { return hm; }
  if (nStart - dStart === 86400000) { return '昨天 ' + hm; }
  if (nStart - dStart > 0 && nStart - dStart < 7 * 86400000) { return '星期' + ['日','一','二','三','四','五','六'][d.getDay()] + ' ' + hm; }
  if (d.getFullYear() === n.getFullYear()) { return (d.getMonth() + 1) + '月' + d.getDate() + '日 ' + hm; }
  return d.getFullYear() + '年' + (d.getMonth() + 1) + '月' + d.getDate() + '日 ' + hm;
}

function maybeAddTimeDivider(ts) {
  if (lastMessageTs === null || ts - lastMessageTs > TIME_DIVIDER_GAP_MS) {
    var div = document.createElement('div');
    div.className = 'time-divider';
    div.textContent = formatTimeLabel(ts, Date.now());
    chat.appendChild(div);
  }
  lastMessageTs = ts;
}

function readSessionQueue() {
  var raw = null;
  try { raw = localStorage.getItem(sessionQueueKey); } catch (e) { return []; }
  if (!raw) { return []; }
  try {
    var arr = JSON.parse(raw);
    if (Object.prototype.toString.call(arr) === '[object Array]') { return arr; }
    return [];
  } catch (e) { return []; }
}

function writeSessionQueue(arr) {
  try { localStorage.setItem(sessionQueueKey, JSON.stringify(arr)); } catch (e) {}
}

function makeQid() {
  return sessionId + '-' + Date.now() + '-' + Math.floor(Math.random() * 1000000);
}

function enqueueSession(record) {
  if (!record.qid) { record.qid = makeQid(); }
  var q = readSessionQueue();
  q.push(record);
  while (q.length > SESSION_QUEUE_MAX) { q.shift(); }
  writeSessionQueue(q);
}

function postSession(record) {
  return fetch(ttsBase + '/session', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(record)
  }).then(function(r) {
    if (!r.ok) { throw new Error('session ' + r.status); }
    return true;
  });
}

function removeQueued(qid) {
  var q = readSessionQueue();
  var rest = [];
  for (var i = 0; i < q.length; i++) {
    if (q[i].qid !== qid) { rest.push(q[i]); }
  }
  writeSessionQueue(rest);
}

function flushSessionQueue() {
  if (sessionFlushing) { return; }
  var q = readSessionQueue();
  if (!q.length) { return; }
  sessionFlushing = true;
  var next = function() {
    var current = readSessionQueue();
    if (!current.length) {
      sessionFlushing = false;
      return;
    }
    var rec = current[0];
    if (!rec.qid) {                       /* 旧版无 qid 的积压记录：补 id 回存后照常发送，不丢弃 */
      rec.qid = makeQid();
      writeSessionQueue(current);
    }
    postSession(rec).then(function() {
      removeQueued(rec.qid);
      next();
    }).catch(function() {
      sessionFlushing = false;
    });
  };
  next();
}

function logSession(rec) {
  var record = {
    session_id: sessionId,
    turn: (typeof rec.turn === 'number') ? rec.turn : sessionTurn,
    role: rec.role,
    text: String(rec.text || ''),
    ts: isoLocal(new Date()),
    provider: settings.provider || '',
    model: settings.model || '',
    page: 'companion'
  };
  ['emotion', 'tts', 'retrieval_used', 'ua', 'aborted', 'detail'].forEach(function(k) {
    if (rec[k] !== undefined) { record[k] = rec[k]; }
  });
  if (!ttsAvailable) {
    enqueueSession(record);
    return;
  }
  postSession(record).then(function() {
    flushSessionQueue();
  }).catch(function() {
    enqueueSession(record);
  });
}

function ensureSessionStarted() {
  if (sessionStarted) { return; }
  sessionStarted = true;
  logSession({role: 'event', turn: 0, text: 'session_start', ua: navigator.userAgent});
}
function inferProvider(url, provider) {
  if (Object.prototype.hasOwnProperty.call(PROVIDERS, provider)) { return provider; }
  if (typeof url !== 'string') { url = ''; }
  if (url.indexOf('api.anthropic.com') !== -1) { return 'anthropic'; }
  if (url.indexOf('api.deepseek.com') !== -1) { return 'deepseek'; }
  if (url.indexOf('moonshot.cn') !== -1 || url.indexOf('moonshot.ai') !== -1) { return 'kimi'; }
  if (url.indexOf('api.openai.com') !== -1) { return 'openai'; }
  if (url) { return 'custom'; }
  return DEFAULT_PROVIDER;
}
function normalizeProfile(p) {
  var result = {url: '', model: '', key: ''};
  if (p && typeof p === 'object') {
    result.url = (typeof p.url === 'string') ? p.url : '';
    result.model = (typeof p.model === 'string') ? p.model : '';
    result.key = (typeof p.key === 'string') ? p.key : '';
  }
  return result;
}
function cloneProfiles(src) {
  var result = {};
  if (src && Object.prototype.toString.call(src) === '[object Object]') {
    for (var key in src) {
      if (Object.prototype.hasOwnProperty.call(src, key) && Object.prototype.hasOwnProperty.call(PROVIDERS, key)) {
        result[key] = normalizeProfile(src[key]);
      }
    }
  }
  return result;
}
function loadSettings() {
  try {
    var raw = localStorage.getItem(storageKey);
    if (raw) {
      var parsed = JSON.parse(raw);
      /* 旧版存档（无 profiles）里 'openai' 是"任意 OpenAI 兼容"的笼统值：除 anthropic 外按 URL 归类 */
      var hasProfilesMap = Object.prototype.toString.call(parsed.profiles) === '[object Object]';
      var legacy = !hasProfilesMap;
      var provider = (legacy && parsed.provider !== 'anthropic') ? inferProvider(parsed.url, undefined) : inferProvider(parsed.url, parsed.provider);
      var profiles = {};
      if (hasProfilesMap) {
        for (var key in parsed.profiles) {
          if (Object.prototype.hasOwnProperty.call(parsed.profiles, key) && Object.prototype.hasOwnProperty.call(PROVIDERS, key)) {
            profiles[key] = normalizeProfile(parsed.profiles[key]);
          }
        }
      }
      if (!profiles[provider] && ((typeof parsed.url === 'string' && parsed.url) || (typeof parsed.model === 'string' && parsed.model) || (typeof parsed.key === 'string' && parsed.key))) {
        profiles[provider] = normalizeProfile({url: parsed.url, model: parsed.model, key: parsed.key});
      }
      var normalized = normalizeProfile(parsed);
      var base = withDefaults(provider, profiles[provider] || normalized);
      settings = {url: base.url, model: base.model, key: base.key, provider: provider, profiles: profiles};
    } else {
      settings = {url: '', model: '', key: '', provider: DEFAULT_PROVIDER, profiles: {}};
    }
  } catch(e) {
    settings = {url: '', model: '', key: '', provider: DEFAULT_PROVIDER, profiles: {}};
  }
}
function settingsComplete() { return settings && settings.url && settings.model && settings.key; }
function withDefaults(provider, p) {
  if (!Object.prototype.hasOwnProperty.call(PROVIDERS, provider)) { provider = DEFAULT_PROVIDER; }
  var d = PROVIDERS[provider];
  var n = normalizeProfile(p);
  return {url: n.url || d.url, model: n.model || d.model, key: n.key};
}

function profileFor(provider) {
  if (!Object.prototype.hasOwnProperty.call(PROVIDERS, provider)) { provider = DEFAULT_PROVIDER; }
  var src = null;
  if (draftProfiles && Object.prototype.hasOwnProperty.call(draftProfiles, provider)) { src = draftProfiles[provider]; }
  else if (settings.profiles[provider]) { src = settings.profiles[provider]; }
  return withDefaults(provider, src);
}
function fillDrawerFields(provider) {
  var p = profileFor(provider);
  cfgUrl.value = p.url;
  cfgModel.value = p.model;
  cfgKey.value = p.key;
  applyProviderHints(provider);
}
function stashDraft(provider) {
  if (!Object.prototype.hasOwnProperty.call(PROVIDERS, provider)) { return; }
  if (!draftProfiles) { draftProfiles = {}; }
  draftProfiles[provider] = {url: cfgUrl.value.trim(), model: cfgModel.value.trim(), key: cfgKey.value.trim()};
}
function onProviderChange() {
  stashDraft(drawerProvider);
  drawerProvider = cfgProvider.value;
  if (!Object.prototype.hasOwnProperty.call(PROVIDERS, drawerProvider)) {
    drawerProvider = DEFAULT_PROVIDER;
    cfgProvider.value = DEFAULT_PROVIDER;
  }
  fillDrawerFields(drawerProvider);
}
function saveSettings() {
  var p = cfgProvider.value;
  if (!Object.prototype.hasOwnProperty.call(PROVIDERS, p)) { p = DEFAULT_PROVIDER; }
  stashDraft(p);
  settings.profiles = cloneProfiles(draftProfiles);
  settings.provider = p;
  var active = withDefaults(p, settings.profiles[p]);
  settings.url = active.url;
  settings.model = active.model;
  settings.key = active.key;
  try { localStorage.setItem(storageKey, JSON.stringify(settings)); } catch(e) {}
  draftProfiles = null;
  closeDrawer(); updateChatState();
}
function openDrawer() {
  draftProfiles = cloneProfiles(settings.profiles);
  drawerProvider = Object.prototype.hasOwnProperty.call(PROVIDERS, settings.provider) ? settings.provider : DEFAULT_PROVIDER;
  cfgProvider.value = drawerProvider;
  fillDrawerFields(drawerProvider);
  drawer.classList.add('open'); drawerOverlay.classList.add('open');
}
function closeDrawer() { draftProfiles = null; drawer.classList.remove('open'); drawerOverlay.classList.remove('open'); }
function applyProviderHints(provider) {
  var d = PROVIDERS[provider] || PROVIDERS[DEFAULT_PROVIDER];
  cfgUrl.placeholder = d.url || 'https://.../v1/chat/completions';
  cfgModel.placeholder = d.model ? ('例如 ' + d.model) : '模型名';
  cfgKey.placeholder = d.keyPlaceholder || 'API Key';
  var hintEl = document.getElementById('cfg-hint');
  if (hintEl) { hintEl.textContent = d.hint || ''; }
}
function clearChat() { chat.innerHTML = ''; }
function addBubble(opts) {
  if (opts.type === 'user' || opts.type === 'subject') { maybeAddTimeDivider(Date.now()); }
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
function probeTts() { fetch(ttsBase + '/health', {method:'GET'}).then(function(r){ ttsAvailable = !!r.ok; if (ttsAvailable) { flushSessionQueue(); } }).catch(function(){ ttsAvailable = false; }); }

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
  unlockAudio();
  var userText = inputText.value.trim();
  inputText.value = ''; autoGrow();
  addBubble({type:'user', text: userText});
  history.push({role:'user', content: userText});
  ensureSessionStarted();
  sessionTurn += 1;
  var thisTurn = sessionTurn;
  logSession({role:'user', turn: thisTurn, text: userText});

  var subjectBubble = addBubble({type:'subject', text: ''});
  var contentEl = subjectBubble.querySelector('.bubble-content');
  cancelVoiceTurn();
  setTypingIndicator(contentEl);

  function run() {
    sendPending = false;
    var allRecords = collectAllRecords();
    var tokens = extractTokens(userText);
    var snippets = retrieveSnippets(tokens, allRecords, {top: 6});
    var kld = retrieveKnowledge(tokens, (knowledgeCache||{}).memories, (knowledgeCache||{}).transcripts, {memTop: 3, transTop: 2});
    var combined = kld.memories.concat(snippets, kld.transcripts);
    var retrievalBlock = buildRetrievalBlock(combined);
    var retrievalUsed = combined.map(function(x){ return (x.label || '[消息]') + ' ' + (x.date || ''); });
    var messages = buildMessages(systemPrompt, history, retrievalBlock, userText);

    var accText = '';
    streamRequest(messages, function(delta) {
      accText += delta;
    }, function(finalText, aborted) {
      sendBtn.disabled = false;
      sendBtn.classList.remove('stop');
      sendBtn.textContent = '发送';
      streaming = false;
      controller = null;
      if (aborted) {
        contentEl.textContent = accText || '（已停止）';
        history.push({role: 'assistant', content: accText});
        logSession({role:'simulacrum', turn: thisTurn, text: accText, aborted: true, tts: 'skipped', retrieval_used: retrievalUsed});
        return;
      }
      history.push({role: 'assistant', content: finalText});
      var emo = detectEmotion(finalText);
      // TODO 8A-2b: 关窗道别语、空闲「去忙了」、rhythm.json 限速、使用统计自见卡

      var mode = startTurnPresentation(contentEl, finalText, thisTurn, emo);
      logSession({role:'simulacrum', turn: thisTurn, text: finalText, emotion: emo, tts: mode === 'voice' ? 'requested' : (ttsAvailable ? 'skipped_length' : 'unavailable'), retrieval_used: retrievalUsed});
    }, function(err) {
      sendBtn.disabled = false;
      sendBtn.classList.remove('stop');
      sendBtn.textContent = '发送';
      streaming = false;
      controller = null;
      contentEl.textContent = '（出错了：' + (err || '未知错误') + '）';
      logSession({role:'event', turn: thisTurn, text:'llm_error', detail: String(err || '')});
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
/* iOS/Safari 音频解锁：必须在用户手势的同步调用链里执行 */
function unlockAudio() {
  if (audioUnlocked) return;
  try {
    var p = frame.contentWindow.document.getElementById('player');
    if (p) {
      if (!p.src) { p.src = SILENT_WAV; }
      p.muted = true;
      var pr = p.play();
      if (pr && pr.then) {
        pr.then(function(){ p.pause(); p.muted = false; audioUnlocked = true; })
          .catch(function(){ p.muted = false; });
      }
    }
    /* 同源 iframe 共享用户激活：合成 click 触发 avatar 内部的 audioCtx.resume 监听 */
    try {
      var idoc = frame.contentWindow.document;
      idoc.dispatchEvent(new frame.contentWindow.Event('click', {bubbles: true}));
    } catch(e2) {}
  } catch(e) {}
}

function ensureEmotionImg() {
  if (emotionImg) return emotionImg;
  try {
    var idoc = frame.contentWindow.document;
    var container = idoc.getElementById('avatar-image');
    if (!container) return null;
    var img = idoc.createElement('img');
    img.id = 'emotion-overlay';
    img.alt = '';
    /* 全显式 inline style，不挂 mouth-patch 类（display 回落事故铁律） */
    img.style.cssText = 'position:absolute;top:0;left:0;width:100%;height:100%;display:none;';
    var blink = idoc.getElementById('eyes-blink');
    if (blink) { container.insertBefore(img, blink); } else { container.appendChild(img); }
    emotionImg = img;
    return img;
  } catch(e) { return null; }
}

function detectEmotion(text) {
  if (!emotionsCfg || !emotionsCfg.emotions || !text) return null;
  var lower = String(text).toLowerCase();
  for (var name in emotionsCfg.emotions) {
    var ent = emotionsCfg.emotions[name];
    if (!ent) continue;
    var kws = ent.keywords || [];
    for (var i = 0; i < kws.length; i++) {
      if (kws[i] && lower.indexOf(String(kws[i]).toLowerCase()) !== -1) return name;
    }
  }
  return null;
}

function showEmotion(name) {
  if (!name || !emotionsCfg || !emotionsCfg.emotions[name] || !emotionsCfg.emotions[name].file) return;
  var delay0 = (emotionsCfg.neutral_delay_ms || 8000);
  if (name === lastEmotion) {                     /* 同表情防呆滞：不换图但必须刷新回落计时 */
    if (emotionTimer) { clearTimeout(emotionTimer); }
    emotionTimer = setTimeout(clearEmotion, delay0);
    return;
  }
  var img = ensureEmotionImg();
  if (!img) return;
  img.src = emotionsCfg.emotions[name].file;
  img.style.display = 'block';                    /* 显式 block，铁律 */
  lastEmotion = name;
  if (emotionTimer) { clearTimeout(emotionTimer); }
  var delay = (emotionsCfg.neutral_delay_ms || 8000);
  emotionTimer = setTimeout(clearEmotion, delay);
}

function clearEmotion() {
  if (emotionImg) { emotionImg.style.display = 'none'; }
  lastEmotion = null;
}

function splitSegments(text) {
  if (!text) return [];
  var pieces = [];
  var cur = '';
  var i;
  for (i = 0; i < text.length; i++) {
    var ch = text.charAt(i);
    cur += ch;
    if (ch === '。' || ch === '！' || ch === '？' || ch === '!' || ch === '?' || ch === '；' || ch === ';' || ch === '\n') {
      pieces.push(cur);
      cur = '';
    }
  }
  if (cur) pieces.push(cur);
  var result = [];
  var cur2 = '';
  for (i = 0; i < pieces.length; i++) {
    var piece = pieces[i];
    if (!cur2) {
      cur2 = piece;
    } else {
      var limit = (result.length === 0 ? SEG_FIRST_MAX : SEG_MAX);
      if (cur2.replace(/\s/g, '').length < SEG_MIN || (cur2 + piece).length <= limit) {
        cur2 += piece;
      } else {
        result.push(cur2);
        cur2 = piece;
      }
    }
  }
  if (cur2) {
    if (result.length > 0 && cur2.replace(/\s/g, '').length < SEG_MIN) {
      result[result.length - 1] += cur2;
    } else {
      result.push(cur2);
    }
  }
  return result;
}
function setTypingIndicator(el) {
  el.textContent = '';
  var dots = document.createElement('span');
  dots.className = 'typing-dots';
  var i;
  for (i = 0; i < 3; i++) {
    var dot = document.createElement('i');
    dots.appendChild(dot);
  }
  el.appendChild(dots);
}
function hookPlayerEnded() {
  if (playerEndedHooked) return;
  try {
    var p = frame.contentWindow.document.getElementById('player');
    p.addEventListener('ended', function() {
      var ap = activePlay;
      activePlay = null;
      if (ap && ap === voiceTurn && !ap.canceled) { onSegmentEnded(ap); }
    });
    playerEndedHooked = true;
  } catch (e) { /* 跨源降级路径由 fallbackAudio 自带 ended */ }
}
function trackBlobUrl(url) {
  companionVoiceUrls.push(url);
  if (companionVoiceUrls.length > 50) {
    try { URL.revokeObjectURL(companionVoiceUrls.shift()); } catch (e) {}
  }
}
function revealSegment(vt, i) {
  if (vt.canceled) return;
  if (!vt.firstShown) {
    vt.firstShown = true;
    showEmotion(vt.emo);
  }
  vt.revealed = i + 1;
  vt.contentEl.textContent = vt.segments.slice(0, vt.revealed).join('');
  chat.scrollTop = chat.scrollHeight;
}
function revealAll(vt) {
  vt.contentEl.textContent = vt.segments.join('');
  vt.firstShown = true;
  chat.scrollTop = chat.scrollHeight;
  showEmotion(vt.emo);
}
function cancelVoiceTurn() {
  if (!voiceTurn) return;
  var vt = voiceTurn;
  vt.canceled = true;
  if (vt.textTimer) clearTimeout(vt.textTimer);
  if (vt.safetyTimer) clearTimeout(vt.safetyTimer);
  if (!vt.doneRevealing && vt.revealed < vt.segments.length) revealAll(vt);
  try {
    var p = frame.contentWindow.document.getElementById('player');
    if (p && p.pause) p.pause();
  } catch (e) {}
  if (vt.fallbackAudio) { try { vt.fallbackAudio.pause(); } catch (e2) {} }
  if (activePlay === vt) { activePlay = null; }
  voiceTurn = null;
}
function onSegmentEnded(vt) {
  if (!vt || vt !== voiceTurn || vt.canceled) return;
  vt.playing = false;
  vt.playIdx += 1;
  tryAdvance(vt);
}
function tryAdvance(vt) {
  if (vt.canceled || vt.playing) return;
  var i = vt.playIdx;
  if (i >= vt.segments.length) {
    vt.doneRevealing = true;
    return;
  }
  var b = vt.blobs[i];
  if (b === undefined) {
    return;
  }
  if (b === 'failed') {
    revealSegment(vt, i);
    vt.playIdx += 1;
    setTimeout(function() { tryAdvance(vt); }, 400);
    return;
  }
  vt.playing = true;
  revealSegment(vt, i);
  playSegmentBlob(vt, b);
}
function playSegmentBlob(vt, blob) {
  var url = URL.createObjectURL(blob);
  trackBlobUrl(url);
  try {
    var p = frame.contentWindow.document.getElementById('player');
    if (!p) throw new Error('no player');
    p.muted = false;
    p.src = url;
    activePlay = vt;
    var pr = p.play();
    pr.catch(function() {
      activePlay = null;
      showPlayButton(vt, url);
    });
  } catch (e) {
    var a = new Audio(url);
    vt.fallbackAudio = a;
    a.addEventListener('ended', function() {
      if (vt === voiceTurn && !vt.canceled) { onSegmentEnded(vt); }
    });
    var pr2;
    try {
      pr2 = a.play();
    } catch (e2) {
      vt.playing = false;
      vt.playIdx += 1;
      setTimeout(function() { tryAdvance(vt); }, 400);
      return;
    }
    if (pr2 && pr2.catch) {
      pr2.catch(function() {
        showPlayButton(vt, url, a);
      });
    }
  }
}
function showPlayButton(vt, url, fallbackAudio) {
  if (vt.canceled) return;
  if (!vt.playBtnShown) {
    var btn = document.createElement('button');
    btn.className = 'play-voice-btn';
    btn.textContent = '▶ 播放她的声音';
    btn.addEventListener('click', function() {
      var ok = false;
      try {
        var p = frame.contentWindow.document.getElementById('player');
        if (p) {
          p.muted = false;
          p.src = url;
          activePlay = vt;
          var pr = p.play();
          if (pr && pr.then) {
            pr.then(function() { btn.remove(); }).catch(function() { activePlay = null; });
            ok = true;
          } else {
            ok = true;
            btn.remove();
          }
        }
      } catch (e) {}
      if (!ok && fallbackAudio) {
        try {
          var pr2 = fallbackAudio.play();
          if (pr2 && pr2.then) {
            pr2.then(function() { btn.remove(); }).catch(function() {});
          } else {
            btn.remove();
          }
          ok = true;
        } catch (e2) {}
      }
    });
    vt.contentEl.appendChild(btn);
    vt.playBtnShown = true;
  }
}
function synthSegment(vt, i) {
  if (vt.canceled || i >= vt.segments.length) return;
  var seg = vt.segments[i];
  if (seg.replace(/\s/g, '') === '') {
    vt.blobs[i] = 'failed';
    tryAdvance(vt);
    synthSegment(vt, i + 1);
    return;
  }
  fetch(ttsBase + '/tts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: seg, lang: 'mandarin', session_id: sessionId, turn: vt.turn })
  })
  .then(function(r) {
    if (!r.ok) throw new Error('tts ' + r.status);
    return r.blob();
  })
  .then(function(blob) {
    vt.blobs[i] = blob;
    tryAdvance(vt);
    synthSegment(vt, i + 1);
  })
  .catch(function(err) {
    vt.blobs[i] = 'failed';
    if (!vt.failLogged) {
      vt.failLogged = true;
      logSession({ role: 'event', turn: vt.turn, text: 'tts_failed', detail: String((err && err.message) || err || '') });
    }
    tryAdvance(vt);
    synthSegment(vt, i + 1);
  });
}
function scheduleTextReveal(vt) {
  var i = 0;
  var step = function() {
    if (vt.canceled) return;
    if (i >= vt.segments.length) {
      vt.doneRevealing = true;
      return;
    }
    revealSegment(vt, i);
    i += 1;
    var delay = (i === 1) ? 400 : Math.min(600 + vt.segments[i - 1].length * 90, 3500);
    vt.textTimer = setTimeout(step, delay);
  };
  vt.textTimer = setTimeout(step, 400);
}
function startTurnPresentation(contentEl, finalText, turnNo, emo) {
  cancelVoiceTurn();
  var segments = splitSegments(finalText);
  var mode = (ttsAvailable && finalText.length <= TTS_TOTAL_MAX && segments.length > 0) ? 'voice' : 'text';
  var vt = {
    turn: turnNo,
    contentEl: contentEl,
    fullText: finalText,
    segments: segments,
    blobs: [],
    revealed: 0,
    playIdx: 0,
    playing: false,
    canceled: false,
    firstShown: false,
    doneRevealing: false,
    failLogged: false,
    playBtnShown: false,
    emo: emo,
    textTimer: null,
    safetyTimer: null,
    mode: mode
  };
  voiceTurn = vt;
  if (mode === 'voice') {
    hookPlayerEnded();
    synthSegment(vt, 0);
    vt.safetyTimer = setTimeout(function() {
      if (!vt.firstShown && !vt.canceled) {
        vt.canceled = true;
        revealAll(vt);
      }
    }, 20000);
  } else {
    scheduleTextReveal(vt);
  }
  return mode;
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

  fetch('data/avatar/emotions.json')
    .then(function(r) { if (!r.ok) throw new Error('no emotions'); return r.json(); })
    .then(function(cfg) { emotionsCfg = cfg; })
    .catch(function() { emotionsCfg = null; /* 资产未就绪：功能静默关闭 */ });

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
  cfgProvider.addEventListener('change', onProviderChange);
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
window.inferProvider = inferProvider;
window.PROVIDERS = PROVIDERS;
window.formatTimeLabel = formatTimeLabel;
window.buildSessionId = buildSessionId;
window.splitSegments = splitSegments;

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
