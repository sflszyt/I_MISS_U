#!/usr/bin/env python3
"""Build companion.html - merged avatar face + chat brain page (8A-2a)."""

import argparse
import os
import re
import sys

_PERSON_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]*$')
_VIEWER_RE = re.compile(r'^[a-z][a-z0-9_-]{0,31}$')
_OUT_RE = re.compile(r'^[A-Za-z0-9_.-]+\.html$')
_TTS_TOKEN_RE = re.compile(r'^[A-Za-z0-9_-]{0,128}$')
_CONTEXT_PATH_RE = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_.-]*(?:/[A-Za-z0-9_][A-Za-z0-9_.-]*)*\.json')
_TTS_ORIGIN_RE = re.compile(r'https?://[A-Za-z0-9.\-]+(?::\d{1,5})?')
_INTRO_BUILDER_RE = re.compile(r'^[一-龥]{1,6}$')
_LLM_PROXY_RE = re.compile(r'/[A-Za-z0-9_./-]{1,120}')
_PLACEHOLDER_RE = re.compile(r'__[A-Z_]+__')

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
    /* 2026-09-10 用户反馈：手机上偏大，缩 1/3（300 → 200） */
    border: none; width: 100%; height: 200px; display: block; margin: 0 auto;
  }
  .face-note { font-size: 11px; color: #666; padding: 2px 0 8px; }
  #no-memory-banner {
    text-align: center; color: #8888aa; background: #222244;
    font-size: 12px; padding: 4px 0; flex-shrink: 0;
  }
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
  .bubble-content { min-width: 0; }
  .bubble-content.voice { display: flex; flex-direction: column; gap: 4px; }
  .voice-bar {
    display: flex; align-items: center; gap: 8px; height: 32px;
    padding: 0 10px; border-radius: 16px; background: #2d3f6b; color: #fff;
    cursor: pointer; max-width: 100%; user-select: none; -webkit-user-select: none;
    -webkit-tap-highlight-color: transparent;
  }
  .voice-bar:active { background: #3b5188; }
  .voice-bar.expired { opacity: 0.45; }
  .voice-icon {
    position: relative; width: 16px; height: 16px; flex-shrink: 0;
  }
  .voice-icon i {
    position: absolute; left: 0; top: 50%; transform: translateY(-50%);
    border: 2px solid transparent; border-right-color: #fff; border-radius: 50%;
  }
  .voice-icon i:nth-child(1) { width: 4px; height: 4px; }
  .voice-icon i:nth-child(2) { width: 9px; height: 9px; }
  .voice-icon i:nth-child(3) { width: 14px; height: 14px; }
  .voice-bar.playing .voice-icon i:nth-child(2),
  .voice-bar.playing .voice-icon i:nth-child(3) {
    animation: voice-arc 1.2s infinite;
  }
  .voice-bar.playing .voice-icon i:nth-child(3) { animation-delay: 0.4s; }
  @keyframes voice-arc {
    0%, 100% { opacity: .15; }
    50% { opacity: 1; }
  }
  .voice-dur { font-size: 12px; opacity: .9; white-space: nowrap; }
  .voice-text { font-size: 13px; color: #bbb; line-height: 1.5; white-space: pre-wrap; word-wrap: break-word; }
  #chat.hide-voice-text .voice-text { display: none; }
  #drawer .cfg-check { display: flex; align-items: center; gap: 8px; font-size: 13px; color: #ccc; margin: 4px 0 12px; }
  #drawer .cfg-check input { width: auto; margin: 0; }
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
__INTRO_CARD_CSS__</style>
</head>
<body>
__INTRO_CARD_HTML__
<header>
  <span class="title">陪伴</span>
  <span class="subtitle">数字档案 · 模拟对话 · 非本人</span>
  <button id="settings-btn" title="设置">⚙</button>
</header>

<section id="face-section">
  <iframe id="face-frame" src="avatar.html" title="她" scrolling="no"></iframe>
  <div class="face-note">合成语音 · 非本人原声</div>
</section>

<div id="no-memory-banner" hidden>本次对话不进记忆</div>
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
  <label class="cfg-check"><input type="checkbox" id="cfg-voice-text" checked> 语音条下方显示文字</label>
  <label class="cfg-check"><input type="checkbox" id="cfg-no-memory"> 本次对话不进记忆</label>
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
var cfgVoiceText = document.getElementById('cfg-voice-text');
var cfgNoMemory = document.getElementById('cfg-no-memory');
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
var ttsBase = __TTS_BASE_EXPR__;
__TTS_TOKEN_LINE__var ttsAvailable = false;
var sessionId = buildSessionId(new Date());
__LLM_PROXY_LINE__
__DEFAULT_PROFILE_LINE__var sessionTurn = 0;
var sessionQueueKey = storageKey + '_sessionq';
var sessionFlushing = false;
var sessionStarted = false;
var lastMessageTs = null;
var TIME_DIVIDER_GAP_MS = 5 * 60 * 1000;
var SESSION_QUEUE_MAX = 500;
var voiceTurn = null;            /* 当前回复的呈现引擎状态 */
var playerEndedHooked = false;   /* iframe player 的 ended 监听只挂一次 */
var MSG_MAX = 30;                /* 每条消息字符上限（微信式短消息） */
var MSG_MAX_VOICE = 12;          /* 单回合最多为前 N 条消息合成语音，其余纯文字（失控超长回复保护） */
var uiPrefsKey = storageKey + '_ui';
var showVoiceText = true;        /* 语音条下方显示文字（默认开） */
var replayingBar = null;         /* 正在回放的语音条元素 */
var replayUrl = null;            /* 回放用 blob URL（下次回放前 revoke） */
var replayAudio = null;          /* 回放降级路径（无 iframe player）用的 Audio 实例，便于停止 */
var TTS_FETCH_TIMEOUT_MS = 30000; /* 单条 /tts 请求超时，超时按 'failed' 转文字继续 */
var VOICE_BLOB_KEEP = 60;        /* 最多保留最近 N 条语音条的 Blob 供回放，更早的释放 */
var voiceBars = [];              /* 按创建顺序登记的语音条元素（用于 Blob 释放） */
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
var VIEWER = '__VIEWER__';
var SESSIONS_PATH = '__SESSIONS_PATH__';
var SESSIONS_BASE = SESSIONS_PATH.substring(0, SESSIONS_PATH.lastIndexOf('/') + 1);
var sessionsData = {last_card: null, recent_dates: [], sessions: []};
var noMemoryEnabled = false;
var sessionsCardApplied = false;
var historyReplayed = false;      /* 往次记录是否已经回放进聊天区 */
var sessionsLoaded = false;       /* sessions 数据是否已落地（无论成功失败） */
var sessionsDataPromise = null;   /* loadSessionsData 的记忆化 Promise，绝不重复 fetch */

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
    __TTS_HEADERS_SESSION__,
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
    page: '__PAGE_TAG__',
    viewer: VIEWER
  };
  if (noMemoryEnabled) { record.exclude = true; }
  ['emotion', 'tts', 'messages', 'retrieval_used', 'ua', 'aborted', 'detail'].forEach(function(k) {
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
  applyDefaultProfile();
}
function applyDefaultProfile() {
  /* 构建时内置的 key：页面开箱就能说话，iOS 清掉 localStorage 也不至于连接口一起丢。
     只补空位：用户在抽屉里存过的 key 绝不覆盖，也绝不往 localStorage 回写。
     内置 key 只写进 DEFAULT_PROFILE.provider 自己的档位，别的服务商档位一个字都不碰，
     免得把内置 key 发到不该发的端点上。 */
  if (typeof DEFAULT_PROFILE === 'undefined' || !DEFAULT_PROFILE || typeof DEFAULT_PROFILE !== 'object') return;
  if (typeof DEFAULT_PROFILE.key !== 'string' || DEFAULT_PROFILE.key === '') return;
  var dp = DEFAULT_PROFILE.provider;
  if (!Object.prototype.hasOwnProperty.call(PROVIDERS, dp)) return;   /* 不认识的服务商：什么都不做 */
  if (!settings.profiles || Object.prototype.toString.call(settings.profiles) !== '[object Object]') { settings.profiles = {}; }
  if (!settings.profiles[dp]) { settings.profiles[dp] = normalizeProfile(null); }
  if (settings.profiles[dp].key) { return; }               /* 用户在内置档位存过 key：一个字都不动 */
  var storedHasKey = false;
  for (var p in settings.profiles) {
    if (Object.prototype.hasOwnProperty.call(settings.profiles, p) && settings.profiles[p] && settings.profiles[p].key) { storedHasKey = true; break; }
  }
  settings.profiles[dp].key = DEFAULT_PROFILE.key;         /* 只写内置档位 */
  if (!storedHasKey && !settings.key) {                    /* 存档里没有任何可用 key：切到内置服务商 */
    settings.provider = dp;
  }
  var active = Object.prototype.hasOwnProperty.call(PROVIDERS, settings.provider) ? settings.provider : DEFAULT_PROVIDER;
  settings.provider = active;
  if (active === dp) {                                     /* 内置档位在用：顺手刷新 url/model/key；否则原样不动 */
    var seeded = withDefaults(dp, settings.profiles[dp]);
    settings.url = seeded.url;
    settings.model = seeded.model;
    settings.key = seeded.key;
  }
}
__SETTINGS_COMPLETE_FN__
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
function clearChat() { chat.innerHTML = ''; historyReplayed = false; lastMessageTs = null; }
function addBubble(opts) {
  if (!opts.noDivider && (opts.type === 'user' || opts.type === 'subject')) { maybeAddTimeDivider(Date.now()); }
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
function confNoticeKeepHistory() {
  /* 与 confNotice 同一句提示，但不清空聊天区：往次记录是档案内容，不该因为没配 key 就消失。
     updateChatState 会反复调用，同一句居中提示只留一条。 */
  var CENTER_TEXT = '点右上角 ⚙ 配置接口后开始对话';
  var present = false;
  for (var i = 0; i < chat.children.length; i++) {
    var el = chat.children[i];
    if (el.className === 'bubble center' && el.textContent === CENTER_TEXT) { present = true; break; }
  }
  if (!present) { addBubble({type:'center', text: CENTER_TEXT}); }
  sendBtn.disabled = true;
}
function systemNotice(msg) { addBubble({type:'notice', text: msg}); }
function updateChatState() {
  if (!contextLoaded) { clearChat(); addBubble({type:'center', text:'档案加载中，请稍候…'}); sendBtn.disabled = true; return; }
  maybeReplayHistory();                                    /* 历史先回放：它不依赖接口配置 */
  if (!settingsComplete()) { confNoticeKeepHistory(); return; }
  removeStartPlaceholder();                                /* 配置齐了：清掉可能残留的居中占位提示 */
  if (chat.children.length === 0) { addBubble({type:'center', text:'开始对话吧...'}); }
  sendBtn.disabled = false; sendBtn.textContent = '发送'; streaming = false;
  if (controller) { try { controller.abort(); } catch(e) {} controller = null; }
}

/* ===== 历史回放：刷新后仍能看到（并点播）之前说过的话 ===== */
function removeStartPlaceholder() {
  /* 居中状态提示有三处（文字与下面三处 addBubble 逐字相同）：
     '开始对话吧...'（无历史时）、'点右上角 ⚙ 配置接口后开始对话'（儿子站未配 key）、
     '档案加载中，请稍候…'（档案未就绪）。保存设置后回放发生时它们都会留在历史上方，全部移除。 */
  var CENTER_TEXTS = ['开始对话吧...', '点右上角 ⚙ 配置接口后开始对话', '档案加载中，请稍候…'];
  var removed = false;
  var i = chat.children.length - 1;   /* 倒序遍历：边删边遍历不会跳元素 */
  for (; i >= 0; i--) {
    var el = chat.children[i];
    if (el.className !== 'bubble center') continue;
    for (var j = 0; j < CENTER_TEXTS.length; j++) {
      if (el.textContent === CENTER_TEXTS[j]) {
        chat.removeChild(el);
        removed = true;
        break;
      }
    }
  }
  return removed;
}
function maybeReplayHistory() {
  if (historyReplayed) return;
  if (!contextLoaded || !sessionsLoaded) return;
  if (history.length !== 0) return;   /* 用户已经开口：往次记录绝不插进正在进行的对话 */
  if (voiceTurn) return;
  removeStartPlaceholder();
  var rendered = replayHistory();
  historyReplayed = true;
  if (rendered === 0 && chat.children.length === 0) {
    addBubble({type:'center', text:'开始对话吧...'});
  }
  chat.scrollTop = chat.scrollHeight;
}
function wireHistoryBar(bar) {
  /* 独立作用域接住 bar：循环里注册闭包不能引用循环变量 */
  bar.addEventListener('click', function() {
    /* 回合进行中不做独立回放：在入口先做一次与 replayBar 相同的判断。
       拉取是异步的，若只靠 replayBar 内部的检查，下载期间回合可能结束，
       这次点击就会被延迟到那时执行，老人会听到一段没预期的声音。 */
    if (voiceTurn && !voiceTurn.done && !voiceTurn.canceled) return;
    if (bar._voiceBlob) { replayBar(bar); return; }   /* 已缓存：同步调用本就在手势之内，不再解锁 */
    if (bar._voiceLoading) return;
    bar._voiceLoading = true;
    /* 必须在发起 fetch 之前、手势的同步调用链里解锁 iOS 音频。
       Blob 只解决「媒体从哪里加载」，替代不了「手势授权」；fetch 完成后已脱离手势，
       老人刷新页面后第一个点的往往就是历史语音条，iOS Safari 可能拒绝那次异步播放。 */
    /* 已有独立回放在进行时跳过解锁：unlockAudio() 只在自身 play() 成功后才置位，且成功回调
       无条件 pause()，会把正在播放的回放掐断（下载若失败也不会恢复）；而此时播放器必然
       已被用户手势解锁过，交给下载成功后的 replayBar() 接管即可。 */
    if (!replayingBar) unlockAudio();
    fetch(bar._voiceUrl)
      .then(function(r) { if (!r.ok) throw new Error('audio ' + r.status); return r.blob(); })
      .then(function(blob) {
        bar._voiceLoading = false;
        bar._voiceBlob = blob;
        bar.classList.remove('expired');   /* 失败后重试成功：恢复正常外观 */
        replayBar(bar);          /* 必须走 Blob 路径：iOS 无法从 URL 直接播，且口型只能由 Blob 驱动 */
      })
      .catch(function() {
        /* 重试语义：此处 _voiceLoading 已复位、_voiceBlob 仍为空，下一次点击会重新拉取；
           若拉取成功而播放被拒，Blob 已缓存在 bar 上，下一次点击走同步分支直接 replayBar()，
           在手势之内，可以播放。 */
        bar._voiceLoading = false;
        bar.classList.add('expired');
      });
  });
}
function replayHistory() {
  var sessions = (sessionsData && sessionsData.sessions) ? sessionsData.sessions : [];
  var rendered = 0;
  for (var i = 0; i < sessions.length; i++) {
    var s = sessions[i];
    if (!s || s.session_id === sessionId) continue;   /* 当前会话由本轮实时对话负责 */
    var turns = (s.turns && s.turns.length) ? s.turns : [];
    var groups = [];
    var groupByTurn = {};
    var j;
    for (j = 0; j < turns.length; j++) {
      var t = turns[j];
      if (!t) continue;
      var gkey = 't' + String(t.turn);
      if (!Object.prototype.hasOwnProperty.call(groupByTurn, gkey)) {
        groupByTurn[gkey] = {user: null, sim: null};
        groups.push(groupByTurn[gkey]);
      }
      var grp = groupByTurn[gkey];
      if (t.role === 'user') { if (!grp.user) { grp.user = t; } }
      else if (t.role === 'simulacrum') { if (!grp.sim) { grp.sim = t; } }
    }
    for (j = 0; j < groups.length; j++) {
      var g = groups[j];
      if (!g.sim) continue;              /* 没有数字人回复的孤立发言整轮跳过 */
      var tsRaw = g.user ? g.user.ts : g.sim.ts;
      var tsNum = Date.parse(String(tsRaw || ''));
      if (isFinite(tsNum)) { maybeAddTimeDivider(tsNum); }
      if (g.user) {
        addBubble({type: 'user', text: String(g.user.text || ''), noDivider: true});
        rendered += 1;
      }
      var segs = splitMessages(g.sim.text);
      if (!segs || segs.length === 0) {
        var whole = String(g.sim.text || '').replace(/^\s+|\s+$/g, '');
        segs = [whole || '…'];
      }
      var pool = [];
      var audios = (g.sim.audio && g.sim.audio.length) ? g.sim.audio : [];
      var ai;
      for (ai = 0; ai < audios.length; ai++) {
        var item = audios[ai];
        if (!item || typeof item.text !== 'string' || typeof item.file !== 'string') continue;
        if (item.file.indexOf('audio/session_') !== 0) continue;
        if (item.file.substring(item.file.length - 4) !== '.wav') continue;
        if (item.file.indexOf('..') !== -1) continue;
        if (item.file.indexOf('\\') !== -1) continue;
        if (item.file.indexOf('/', 6) !== -1) continue;   /* 除开头 'audio/' 外不再含 '/' */
        pool.push(item);
      }
      for (ai = 0; ai < segs.length; ai++) {
        var segText = segs[ai];
        var b = addBubble({type: 'subject', text: '', noDivider: true});
        var el = b.querySelector('.bubble-content');
        rendered += 1;
        var hit = -1;
        for (var pi = 0; pi < pool.length; pi++) {
          if (pool[pi].text === segText) { hit = pi; break; }
        }
        if (hit === -1) { el.textContent = segText; continue; }
        var au = pool[hit];
        pool.splice(hit, 1);             /* 每条音频只用一次 */
        var durNum = (typeof au.dur === 'number' && isFinite(au.dur) && au.dur > 0) ? au.dur : null;
        el.className = 'bubble-content voice';
        el.innerHTML = voiceBarHtml(segText, durNum);
        var bar = el.querySelector('.voice-bar');
        bar._voiceUrl = SESSIONS_BASE + au.file;
        bar._voiceBlob = null;
        bar._voiceLoading = false;
        wireHistoryBar(bar);             /* 不进 voiceBars：可重新拉取，不挤占实时语音条的 Blob */
      }
    }
  }
  return rendered;
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
    if (rec.sender !== 'subject') continue;
    if (rec.content_type !== 'text') continue;
    var txt = (rec.text || '').trim(); if (!txt) continue;
    var score = scoreText(tokens, txt); if (score <= 0) continue;
    results.push({ date: String(rec.timestamp || '').substring(0, 10), text: txt.length > 200 ? txt.substring(0, 200) : txt, score: score });
  }
  results.sort(function(a, b) {
    if (b.score !== a.score) return b.score - a.score;
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
function retrieveSessions(tokens, data, opts) {
  opts = opts || {}; var top = opts.sessTop || 3;
  var out = []; var sess = (data && data.sessions) || [];
  for (var i = 0; i < sess.length; i++) {
    var s = sess[i];
    if (!s || s.session_id === sessionId) continue;
    var turns = s.turns || [];
    for (var j = 0; j < turns.length; j++) {
      var t = turns[j];
      var txt = String((t && t.text) || '');
      if (!txt) continue;
      var score = scoreText(tokens, txt);
      if (score <= 0) continue;
      if (txt.length > 200) txt = txt.substring(0, 200);
      var lbl = (t.role === 'user') ? '[对话者自述 · 往次对话 Tier-2]' : '[往次数字对话 Tier-3]';
      out.push({label: lbl, date: String(s.date || ''), text: txt, score: score});
    }
  }
  out.sort(function(a, b) { return b.score - a.score; });
  return out.slice(0, top);
}
function daysBetween(dateStr, today) {
  var parts = String(dateStr || '').split('-');
  var tparts = String(today || '').split('-');
  if (parts.length !== 3 || tparts.length !== 3) { return -1; }
  var d1 = new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
  var d2 = new Date(parseInt(tparts[0], 10), parseInt(tparts[1], 10) - 1, parseInt(tparts[2], 10));
  return Math.round((d2 - d1) / 86400000);
}
function buildSessionsCard(card, recentDates, todayStr) {
  if (!card) return '';
  if (!card.date) return '';
  var n = daysBetween(card.date, todayStr);
  var whenDesc;
  if (n === 0) { whenDesc = '今天早些时候'; }
  else if (n === 1) { whenDesc = '1 天前'; }
  else { whenDesc = n + ' 天前'; }
  var lines = [];
  lines.push('【往次对话 · 第二纪元 · 非她生前记忆】');
  var earlier = [];
  if (recentDates && recentDates.length) {
    for (var ei = 0; ei < recentDates.length; ei++) {
      if (recentDates[ei] && recentDates[ei] !== card.date) { earlier.push(recentDates[ei]); }
    }
  }
  var secondLine = '上次对话：' + card.date + '（' + whenDesc + '）';
  if (earlier.length) {
    var take = earlier.slice(0, 3);
    secondLine += '。更早还有：' + take.join('、');
  }
  lines.push(secondLine);
  var userLines = (card.user_lines && card.user_lines.length) ? card.user_lines : [];
  if (userLines.length) {
    lines.push('对话者当时说过（Tier-2，可当真，引用时说「侬上趟搭我讲过」）：');
    for (var ul = 0; ul < userLines.length; ul++) {
      lines.push('- ' + userLines[ul]);
    }
  }
  var le = card.last_exchange;
  if (le && le.user && le.simulacrum) {
    lines.push('最后一来一回：对话者「' + le.user + '」／你「' + le.simulacrum + '」（你上次的话只用于前后一致，不是事实来源）');
  }
  if (lines.length === 1) return '';
  return lines.join('\n');
}
function applySessionsCard() {
  if (sessionsCardApplied) return;
  if (!systemPrompt) return;
  var card = sessionsData.last_card;
  if (!card || card.session_id === sessionId) return;
  var d = new Date();
  var y = d.getFullYear(), mo = d.getMonth() + 1, da = d.getDate();
  var todayStr = y + '-' + (mo < 10 ? '0' + mo : mo) + '-' + (da < 10 ? '0' + da : da);
  var block = buildSessionsCard(card, sessionsData.recent_dates, todayStr);
  if (!block) return;
  systemPrompt = systemPrompt + '\n\n' + block;
  sessionsCardApplied = true;
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
    return fetch('data/' + safeName, {cache: 'no-cache'})
      .then(function(r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function(data) { shardCache[name] = Array.isArray(data) ? data : [data]; shardStatus[name] = true; loadedCount++; })
      .catch(function() { shardStatus[name] = 'failed'; failedCount++; });
  });
  return Promise.all(fetches).then(function() { shardsLoading = false; });
}
function loadSessionsData() {
  if (sessionsDataPromise) return sessionsDataPromise;
  sessionsDataPromise = fetch(SESSIONS_PATH, {cache: 'no-cache'})
    .then(function(r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(function(data) {
      if (data && data.viewer === VIEWER) {
        sessionsData = {
          last_card: data.last_card || null,
          recent_dates: (data.recent_dates && data.recent_dates.length) ? data.recent_dates : [],
          sessions: (data.sessions && data.sessions.length) ? data.sessions : []
        };
      }
    })
    .catch(function() { /* 文件不存在或坏：功能静默关闭 */ })
    .then(function() {
      sessionsLoaded = true;
      applySessionsCard();
      updateChatState();
    });
  return sessionsDataPromise;
}
function loadKnowledge() {
  if (knowledgeLoading || knowledgeCache !== null) return Promise.resolve(knowledgeCache);
  knowledgeLoading = true; var out = {memories: [], transcripts: []};
  var one = function(name, key) {
    return fetch('data/' + name, {cache: 'no-cache'})
      .then(function(r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function(data) { if (data && Array.isArray(data.entries)) out[key] = data.entries; })
      .catch(function() {});
  };
  return Promise.all([one('memories.json', 'memories'), one('transcripts.json', 'transcripts'), loadSessionsData()])
    .then(function() { knowledgeCache = out; knowledgeLoading = false; applySessionsCard(); return out; });
}
function collectAllRecords() {
  var all = []; for (var name in shardCache) { if (shardCache[name]) all = all.concat(shardCache[name]); } return all;
}

/* ===== streamRequest（唯一改动：openai 分支 reqBody 后加 deepseek thinking:disabled）===== */
function streamRequest(messages, onDelta, onDone, onError) {
  if (!settingsComplete()) { onError('请先在设置中配置接口'); return; }
  controller = new AbortController(); streaming = true; sendBtn.textContent = '停止'; sendBtn.classList.add('stop');
__LLM_PROXY_BRANCH__  var endpoint = settings.url;
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
function probeTts() { __TTS_FETCH_HEALTH__ }
function startTtsProbeLoop() {
  var attempts = 0;
  var maxAttempts = 24;
  var waitingNotified = false;
  var recoveredShown = false;
  var gaveUpShown = false;
  function runProbe() {
    attempts += 1;
    probeTts().then(function(success) {
      if (success) {
        if (waitingNotified && !recoveredShown) {
          systemNotice('她的声音准备好了。');
          recoveredShown = true;
        }
        return;
      }
      if (attempts > 1) {
        if (!waitingNotified) {
          systemNotice('她的声音还在准备，稍等一会儿。现在也可以先打字跟她说。');
          waitingNotified = true;
        }
      }
      if (attempts >= maxAttempts) {
        if (waitingNotified && !gaveUpShown) {
          systemNotice('今天听不到她的声音，但还可以打字跟她说话。');
          gaveUpShown = true;
        }
        return;
      }
      setTimeout(runProbe, 15000);
    });
  }
  runProbe();
}

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
  cancelVoiceTurn();               /* 先收掉上一回合（未念完的消息就地转文字），再挂用户气泡，保证顺序 */
  addBubble({type:'user', text: userText});
  history.push({role:'user', content: userText});
  ensureSessionStarted();
  sessionTurn += 1;
  var thisTurn = sessionTurn;
  logSession({role:'user', turn: thisTurn, text: userText});

  var subjectBubble = addBubble({type:'subject', text: ''});
  var contentEl = subjectBubble.querySelector('.bubble-content');
  setTypingIndicator(contentEl);

  function run() {
    sendPending = false;
    var allRecords = collectAllRecords();
    var tokens = extractTokens(userText);
    var snippets = retrieveSnippets(tokens, allRecords, {top: 6});
    var kld = retrieveKnowledge(tokens, (knowledgeCache||{}).memories, (knowledgeCache||{}).transcripts, {memTop: 3, transTop: 2});
    var sessHits = retrieveSessions(tokens, sessionsData, {sessTop: 3});
    var combined = kld.memories.concat(snippets, kld.transcripts, sessHits);
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

      var pres = startTurnPresentation(contentEl, finalText, thisTurn, emo);
      logSession({role:'simulacrum', turn: thisTurn, text: finalText, emotion: emo, tts: pres.tts, messages: pres.count, retrieval_used: retrievalUsed});
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

function splitMessages(text) {
  var s = String(text || '');
  if (!s) return [];
  var lines = s.split('\n');
  var out = [];
  var i, j;
  for (i = 0; i < lines.length; i++) {
    var line = lines[i].replace(/^\s+|\s+$/g, '');
    if (!line) continue;
    var primary = [];
    var cur = '';
    for (j = 0; j < line.length; j++) {
      var ch1 = line.charAt(j);
      cur += ch1;
      if (ch1 === '。' || ch1 === '！' || ch1 === '？' || ch1 === '!' || ch1 === '?' || ch1 === '；' || ch1 === ';') {
        primary.push(cur);
        cur = '';
      }
    }
    if (cur) primary.push(cur);
    var lineMsgs = [];
    var cur2 = '';
    for (j = 0; j < primary.length; j++) {
      var piece = primary[j];
      if (!cur2) {
        cur2 = piece;
      } else if ((cur2 + piece).length <= MSG_MAX) {
        cur2 += piece;
      } else {
        lineMsgs.push(cur2);
        cur2 = piece;
      }
    }
    if (cur2) lineMsgs.push(cur2);
    for (j = 0; j < lineMsgs.length; j++) {
      var m = lineMsgs[j];
      if (m.length > MSG_MAX) {
        var secondary = [];
        var cur3 = '';
        var k;
        for (k = 0; k < m.length; k++) {
          var ch2 = m.charAt(k);
          cur3 += ch2;
          if (ch2 === '，' || ch2 === '、' || ch2 === ',' || ch2 === '：' || ch2 === ':') {
            secondary.push(cur3);
            cur3 = '';
          }
        }
        if (cur3) secondary.push(cur3);
        var cur4 = '';
        for (k = 0; k < secondary.length; k++) {
          var sp = secondary[k];
          if (sp.length > MSG_MAX) {
            if (cur4) { out.push(cur4); cur4 = ''; }
            var h = 0;
            while (h < sp.length) {
              var take = MSG_MAX;
              if (h + take > sp.length) take = sp.length - h;
              if (take > 0 && h + take <= sp.length) {
                var cutPos = h + take;
                if (cutPos > h && cutPos <= sp.length) {
                  var cp = sp.charCodeAt(cutPos - 1);
                  if (cp >= 0xD800 && cp <= 0xDBFF && cutPos < sp.length) {
                    take -= 1;
                  }
                }
              }
              out.push(sp.substr(h, take));
              h += take;
            }
            continue;
          }
          if (!cur4) {
            cur4 = sp;
          } else if ((cur4 + sp).length <= MSG_MAX) {
            cur4 += sp;
          } else {
            out.push(cur4);
            cur4 = sp;
          }
        }
        if (cur4) out.push(cur4);
      } else {
        out.push(m);
      }
    }
  }
  var result = [];
  for (i = 0; i < out.length; i++) {
    var item = out[i].replace(/^\s+|\s+$/g, '');
    var stripped = item.replace(/[\s。！？!?；;，、,：:…\.~～—\-·"'“”‘’]/g, '');
    if (!item) continue;
    if (!stripped) {
      /* 标点-only 片：能并入前一条且不超 MSG_MAX 才并；否则独立成条（不静默丢弃，TTS 侧按标点-only 跳过） */
      if (result.length > 0 && (result[result.length - 1] + item).length <= MSG_MAX) {
        result[result.length - 1] += item;
      } else {
        result.push(item);
      }
      continue;
    }
    result.push(item);
  }
  if (result.length === 0) { var t = s.replace(/^\s+|\s+$/g, ''); return t ? [t] : []; }
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
    var onEnd = function() {
      var ap = activePlay;
      activePlay = null;
      if (ap && ap === voiceTurn && !ap.canceled) { onSegmentEnded(ap); }
      if (replayingBar) { replayingBar.classList.remove('playing'); replayingBar = null; }
    };
    p.addEventListener('ended', onEnd);
    p.addEventListener('error', onEnd);
    /* #4 诊断（2026-09-10）：语音段中途停住时留证，用于区分「元素提前停」与「音频本身就短」。
       只在真的没播完时记一条，正常播完不产生任何记录。 */
    p.addEventListener('pause', function() {
      try {
        if (p.ended) return;
        var ap = activePlay;
        /* 只记「本该继续播却停了」。以下都是代码主动暂停的正常路径，不记：
           stopReplay() 在回放中暂停时 activePlay 为 null；
           cancelVoiceTurn() 在 p.pause() 之前已置 vt.canceled、之后才清 activePlay；
           unlockAudio() 的 8ms 静音 activePlay 亦为 null。 */
        if (!ap || ap.canceled) return;
        var t = p.currentTime || 0, d = p.duration || 0;
        if (t > 0.05 && d > 0 && t < d - 0.25) {
          logSession({ role: 'event', turn: ap.turn, text: 'seg_cut',
                       detail: 't=' + t.toFixed(2) + ' dur=' + d.toFixed(2) });
        }
      } catch (e) {}
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
function takePending(vt, i) {
  var el;
  if (vt.pendingEl) {
    el = vt.pendingEl;
    vt.pendingEl = null;
  } else {
    var b2 = addBubble({ type: 'subject', text: '', noDivider: true });
    el = b2.querySelector('.bubble-content');
  }
  el.innerHTML = '';
  el.className = 'bubble-content';
  vt.contents[i] = el;
  var nextIdx = i + 1;
  if (nextIdx < vt.msgs.length) {
    var b3 = addBubble({ type: 'subject', text: '', noDivider: true });
    vt.pendingEl = b3.querySelector('.bubble-content');
    setTypingIndicator(vt.pendingEl);
  } else {
    vt.pendingEl = null;
  }
  return el;
}
function showTextMsg(vt, i) {
  var el = takePending(vt, i);
  el.textContent = vt.msgs[i];
  if (!vt.firstShown) {
    vt.firstShown = true;
    showEmotion(vt.emo);
  }
  chat.scrollTop = chat.scrollHeight;
}
function voiceBarHtml(msg, dur) {
  var safeMsg = String(msg || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
  var durNum = (dur && !isNaN(dur) && dur > 0) ? dur : null;
  var W = 72 + Math.min(Math.max((durNum || 1), 1), 30) * 4;
  var D = durNum ? (String(Math.max(1, Math.round(durNum))) + '"') : '';
  return '<div class="voice-bar" role="button" tabindex="0" style="width:' + W + 'px"><span class="voice-icon"><i></i><i></i><i></i></span><span class="voice-dur">' + D + '</span></div><div class="voice-text">' + safeMsg + '</div>';
}
function showVoiceMsg(vt, i, blob, dur) {
  var el = takePending(vt, i);
  el.className = 'bubble-content voice';
  var html = voiceBarHtml(vt.msgs[i], dur);
  el.innerHTML = html;
  var bar = el.querySelector('.voice-bar');
  bar._voiceBlob = blob;
  voiceBars.push(bar);
  while (voiceBars.length > VOICE_BLOB_KEEP) {
    var oldBar = voiceBars.shift();
    oldBar._voiceBlob = null;
    oldBar.classList.add('expired');
  }
  bar.addEventListener('click', function(ev) { replayBar(bar); });
  if (!vt.bars) vt.bars = [];
  vt.bars[i] = bar;
  if (!vt.firstShown) {
    vt.firstShown = true;
    showEmotion(vt.emo);
  }
  chat.scrollTop = chat.scrollHeight;
  return bar;
}
function synthMsg(vt, i) {
  if (vt.canceled || i >= vt.msgs.length) return;
  if (i >= vt.voiceCount) {
    vt.blobs[i] = 'text';
    tryAdvance(vt);
    synthMsg(vt, i + 1);
    return;
  }
  var msg = vt.msgs[i];
  if (msg.replace(/[\s]/g, '') === '') {
    vt.blobs[i] = 'failed';
    tryAdvance(vt);
    synthMsg(vt, i + 1);
    return;
  }
  var spoken = msg.replace(/[\[【（(][^\[\]【】（）()]*[\]】）)]/g, '').replace(/[\s。！？!?；;，、,：:…\.~～—\-·"'“”‘’]+/g, '');   /* H8：标签/标点-only 的条不送 TTS */
  if (spoken === '') {
    vt.blobs[i] = 'text';
    tryAdvance(vt);
    synthMsg(vt, i + 1);
    return;
  }
  var ctrl = (typeof AbortController !== 'undefined') ? new AbortController() : null;
  var timer = setTimeout(function () { if (ctrl) ctrl.abort(); }, TTS_FETCH_TIMEOUT_MS);
  fetch(ttsBase + '/tts', {
    method: 'POST',
    __TTS_HEADERS_TTS__,
    body: JSON.stringify({ text: msg, lang: '__TTS_LANG__', session_id: sessionId, turn: vt.turn }),
    signal: ctrl ? ctrl.signal : undefined
  })
  .then(function(r) {
    if (!r.ok) throw new Error('tts ' + r.status);
    var h = r.headers.get('X-Duration-Seconds');
    var dv = parseFloat(h);
    vt.durs[i] = (isNaN(dv)) ? null : dv;
    return r.blob();                       /* 超时定时器要盖到 body 读完，见下一个 then */
  })
  .then(function(blob) {
    clearTimeout(timer);
    vt.blobs[i] = blob;
    tryAdvance(vt);
    synthMsg(vt, i + 1);
  })
  .catch(function(err) {
    clearTimeout(timer);
    vt.blobs[i] = 'failed';
    if (!vt.failLogged) {
      vt.failLogged = true;
      logSession({ role: 'event', turn: vt.turn, text: 'tts_failed', detail: String((err && (err.name || err.message)) || err || '') });
    }
    tryAdvance(vt);
    synthMsg(vt, i + 1);
  });
}
function tryAdvance(vt) {
  if (vt.canceled || vt.playing || vt.waiting) return;
  var i = vt.playIdx;
  if (i >= vt.msgs.length) {
    vt.done = true;
    vt.pendingEl = null;
    return;
  }
  var b = vt.blobs[i];
  if (b === undefined) {
    return;
  }
  if (b === 'failed' || b === 'text') {
    showTextMsg(vt, i);
    vt.playIdx += 1;
    vt.waiting = true;
    setTimeout(function () { vt.waiting = false; tryAdvance(vt); }, textDelay(vt.msgs[i]));
    return;
  }
  vt.playing = true;
  var bar = showVoiceMsg(vt, i, b, vt.durs[i]);
  bar.classList.add('playing');
  playSegmentBlob(vt, b);
}
function textDelay(msg) {
  return Math.min(600 + String(msg || '').length * 90, 3500);
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
      if (vt.bars && vt.bars[vt.playIdx]) vt.bars[vt.playIdx].classList.remove('playing');
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
      vt.blobs[vt.playIdx] = 'failed';
      var elIdx = vt.playIdx;
      if (vt.bars && vt.bars[elIdx]) {
        vt.bars[elIdx].classList.remove('playing');
      }
      var contentEl2 = vt.contents[elIdx];
      if (contentEl2) {
        contentEl2.className = 'bubble-content';
        contentEl2.innerHTML = '';
        contentEl2.textContent = vt.msgs[elIdx];
      }
      vt.playing = false;
      vt.playIdx += 1;
      vt.waiting = true;
      setTimeout(function() { vt.waiting = false; tryAdvance(vt); }, 400);
      return;
    }
    if (pr2 && pr2.catch) {
      pr2.catch(function() {
        if (vt.bars && vt.bars[vt.playIdx]) vt.bars[vt.playIdx].classList.remove('playing');
        showPlayButton(vt, url, a);
      });
    }
  }
}
function showPlayButton(vt, url, fallbackAudio) {
  if (vt.canceled || vt !== voiceTurn) { return; }
  var curIdx = vt.playIdx;
  var hostEl = vt.contents[curIdx];
  if (!hostEl) return;
  if (vt.playBtnShown === curIdx) return;
  vt.playBtnShown = curIdx;
  var btn = document.createElement('button');
  btn.className = 'play-voice-btn';
  btn.textContent = '▶ 播放她的声音';
  btn.addEventListener('click', function() {
    if (vt.canceled || vt !== voiceTurn) { return; }
    var ok = false;
    try {
      var p = frame.contentWindow.document.getElementById('player');
      if (p) {
        p.muted = false;
        p.src = url;
        activePlay = vt;
        var pr = p.play();
        if (pr && pr.then) {
          pr.then(function() { btn.remove(); if (vt.bars && vt.bars[vt.playIdx]) vt.bars[vt.playIdx].classList.add('playing'); }).catch(function() { activePlay = null; });
          ok = true;
        } else {
          ok = true;
          btn.remove();
          if (vt.bars && vt.bars[vt.playIdx]) vt.bars[vt.playIdx].classList.add('playing');
        }
      }
    } catch (e) {}
    if (!ok && fallbackAudio) {
      try {
        var pr2 = fallbackAudio.play();
        if (pr2 && pr2.then) {
          pr2.then(function() { btn.remove(); if (vt.bars && vt.bars[vt.playIdx]) vt.bars[vt.playIdx].classList.add('playing'); }).catch(function() {});
        } else {
          btn.remove();
          if (vt.bars && vt.bars[vt.playIdx]) vt.bars[vt.playIdx].classList.add('playing');
        }
        ok = true;
      } catch (e2) {}
    }
  });
  hostEl.appendChild(btn);
}
function onSegmentEnded(vt) {
  if (!vt || vt !== voiceTurn || vt.canceled) return;
  if (vt.bars && vt.bars[vt.playIdx]) {
    vt.bars[vt.playIdx].classList.remove('playing');
  }
  vt.playing = false;
  vt.playIdx += 1;
  tryAdvance(vt);
}
function dumpRemaining(vt) {
  var i = 0;
  var idx;
  if (vt.contents[vt.playIdx]) {
    i = vt.playIdx;
  } else {
    i = vt.playIdx;
  }
  for (idx = i; idx < vt.msgs.length; idx++) {
    if (!vt.contents[idx]) {
      var parent;
      if (vt.pendingEl) {
        parent = vt.pendingEl;
        vt.pendingEl = null;
      } else {
        var b5 = addBubble({ type: 'subject', text: '', noDivider: true });
        parent = b5.querySelector('.bubble-content');
      }
      parent.className = 'bubble-content';
      parent.innerHTML = '';
      parent.textContent = vt.msgs[idx];
      vt.contents[idx] = parent;
      if (!vt.firstShown) {
        vt.firstShown = true;
        showEmotion(vt.emo);
      }
    }
  }
  if (vt.pendingEl) {
    var bempty = vt.pendingEl;
    var bdiv = bempty.parentNode;
    if (bdiv) {
      bdiv.parentNode.removeChild(bdiv);
    }
    vt.pendingEl = null;
  }
}
function stopReplay() {
  var wasReplaying = (replayingBar !== null);
  if (replayingBar) { replayingBar.classList.remove('playing'); replayingBar = null; }
  if (replayAudio) { try { replayAudio.pause(); } catch (e) {} replayAudio = null; }
  if (wasReplaying) {
    try { var p = frame.contentWindow.document.getElementById('player'); if (p && p.pause) p.pause(); } catch (e) {}
  }
}
function cancelVoiceTurn() {
  stopReplay();
  if (!voiceTurn) return;
  var vt = voiceTurn;
  vt.canceled = true;
  if (vt.textTimer) clearTimeout(vt.textTimer);
  if (vt.safetyTimer) clearTimeout(vt.safetyTimer);
  if (vt.bars) {
    for (var i = 0; i < vt.bars.length; i++) {
      if (vt.bars[i]) vt.bars[i].classList.remove('playing');
    }
  }
  for (var ci = 0; ci < vt.contents.length; ci++) {
    if (vt.contents[ci]) {
      var btns = vt.contents[ci].querySelectorAll('.play-voice-btn');
      for (var bi = 0; bi < btns.length; bi++) {
        var bEl = btns[bi];
        if (bEl.parentNode) bEl.parentNode.removeChild(bEl);
      }
    }
  }
  dumpRemaining(vt);
  try {
    var p = frame.contentWindow.document.getElementById('player');
    if (p && p.pause) p.pause();
  } catch (e) {}
  if (vt.fallbackAudio) { try { vt.fallbackAudio.pause(); } catch (e2) {} }
  if (activePlay === vt) { activePlay = null; }
  if (replayingBar) { replayingBar.classList.remove('playing'); replayingBar = null; }
  voiceTurn = null;
}
function scheduleTextReveal(vt) {
  var i = 0;
  var step = function() {
    if (vt.canceled) return;
    if (i >= vt.msgs.length) {
      vt.done = true;
      return;
    }
    showTextMsg(vt, i);
    i += 1;
    var delay = (i === 1) ? 400 : textDelay(vt.msgs[i - 1]);
    vt.textTimer = setTimeout(step, delay);
  };
  vt.textTimer = setTimeout(step, 400);
}
function replayBar(bar) {
  if (!bar._voiceBlob) return;
  if (voiceTurn && !voiceTurn.done && !voiceTurn.canceled) {
    /* 回合进行中不做独立回放（回放会把 activePlay 置空，ended 就推进不了回合）；
       唯一例外：当前条因自动播放被拒正等 ▶，点它本身 = 点 ▶（走 activePlay 归属路径继续回合） */
    var cur = voiceTurn;
    if (cur.playBtnShown === cur.playIdx && cur.bars && cur.bars[cur.playIdx] === bar && cur.contents[cur.playIdx]) {
      var btn = cur.contents[cur.playIdx].querySelector('.play-voice-btn');
      if (btn) { btn.click(); }
    }
    return;
  }
  var stopReplayLocal = function() {
    stopReplay();
  };
  if (replayingBar === bar) {
    stopReplayLocal();
    return;
  }
  stopReplayLocal();
  hookPlayerEnded();
  if (replayUrl) {
    try { URL.revokeObjectURL(replayUrl); } catch (e) {}
  }
  replayUrl = URL.createObjectURL(bar._voiceBlob);
  var played = false;
  try {
    var p2 = frame.contentWindow.document.getElementById('player');
    if (p2) {
      p2.muted = false;
      p2.src = replayUrl;
      activePlay = null;
      replayingBar = bar;
      bar.classList.add('playing');
      var pr = p2.play();
      if (pr && pr.catch) {
        pr.catch(function() {
          bar.classList.remove('playing');
          if (replayingBar === bar) replayingBar = null;
        });
      }
      played = true;
    }
  } catch (e) {}
  if (!played) {
    var a = new Audio(replayUrl);
    replayAudio = a;
    a.addEventListener('ended', function() {
      bar.classList.remove('playing');
      if (replayingBar === bar) replayingBar = null;
      if (replayAudio === a) replayAudio = null;
    });
    replayingBar = bar;
    bar.classList.add('playing');
    var pr3;
    try {
      pr3 = a.play();
    } catch (e2) {
      bar.classList.remove('playing');
      if (replayingBar === bar) replayingBar = null;
      if (replayAudio === a) replayAudio = null;
      return;
    }
    if (pr3 && pr3.catch) {
      pr3.catch(function() {
        bar.classList.remove('playing');
        if (replayingBar === bar) replayingBar = null;
        if (replayAudio === a) replayAudio = null;
      });
    }
  }
}
function startTurnPresentation(contentEl, finalText, turnNo, emo) {
  stopReplay();
  cancelVoiceTurn();
  var msgs = splitMessages(finalText);
  if (msgs.length === 0) { msgs = [String(finalText || '').replace(/^\s+|\s+$/g, '') || '…']; }
  var mode = ttsAvailable ? 'voice' : 'text';
  var voiceCount = Math.min(msgs.length, MSG_MAX_VOICE);
  var vt = {
    turn: turnNo,
    msgs: msgs,
    blobs: [],
    durs: [],
    contents: [],
    bars: [],
    pendingEl: contentEl,
    playIdx: 0,
    playing: false,
    waiting: false,
    canceled: false,
    firstShown: false,
    done: false,
    failLogged: false,
    playBtnShown: -1,
    emo: emo,
    textTimer: null,
    safetyTimer: null,
    mode: mode,
    voiceCount: voiceCount,
    fallbackAudio: null
  };
  voiceTurn = vt;
  var resultTts;
  if (mode === 'voice') {
    hookPlayerEnded();
    synthMsg(vt, 0);
    resultTts = (voiceCount < msgs.length) ? 'partial' : 'requested';
    vt.safetyTimer = setTimeout(function() {
      if (!vt.firstShown && !vt.canceled) {
        cancelVoiceTurn();
      }
    }, 20000);
  } else {
    scheduleTextReveal(vt);
    resultTts = 'unavailable';
  }
  return { mode: mode, tts: resultTts, count: msgs.length };
}
function loadUiPrefs() {
  var saved = null;
  try {
    saved = JSON.parse(localStorage.getItem(uiPrefsKey) || 'null');
  } catch (e) { saved = null; }
  if (saved && saved.voiceText !== undefined) {
    showVoiceText = (saved.voiceText !== false);
  }
  applyVoiceTextPref();
}
function applyVoiceTextPref() {
  if (showVoiceText) {
    chat.classList.remove('hide-voice-text');
  } else {
    chat.classList.add('hide-voice-text');
  }
  if (cfgVoiceText) cfgVoiceText.checked = showVoiceText;
}
function onVoiceTextToggle() {
  showVoiceText = !!cfgVoiceText.checked;
  applyVoiceTextPref();
  try {
    localStorage.setItem(uiPrefsKey, JSON.stringify({ voiceText: showVoiceText }));
  } catch (e) {}
}
function onNoMemoryToggle() {
  noMemoryEnabled = !!(cfgNoMemory && cfgNoMemory.checked);
  var banner = document.getElementById('no-memory-banner');
  if (banner) { banner.hidden = !noMemoryEnabled; }
  if (noMemoryEnabled) {
    logSession({role: 'event', text: 'exclude_session'});
  }
}
__LLM_PROXY_HIDE_JS__/* ===== init ===== */
function init() {
  // face-frame 样式注入：隐藏 avatar 页自带的播放器 UI，只留脸。
  // scale(0.67) 与 #face-frame 的 200px 高度是一对：avatar 内容原高约 292px，
  // 缩到 ~196px 才装得下。**只改其中一个会变成裁剪而不是缩小**（2026-09-10 事故）。
  function injectFaceCss() {
    try {
      var doc = frame.contentWindow && frame.contentWindow.document;
      if (!doc || !doc.head) return;
      // 以「样式节点是否还在」为准，不用一次性布尔量：iframe 若重新加载，
      // 注入的 style 会随旧文档一起消失，必须能再注入一次。
      if (doc.getElementById('companion-face-css')) { faceReady = true; return; }
      var st = doc.createElement('style');
      st.id = 'companion-face-css';
      st.textContent = '.now-playing,.controls,.playlist,footer{display:none!important;} main{padding:0!important;justify-content:center;min-height:auto;transform:scale(0.67);transform-origin:top center;} body{background:transparent!important;overflow:hidden;}';
      doc.head.appendChild(st);
      faceReady = true;
    } catch(e) { faceReady = false; /* 跨源等异常：降级仅播声不驱动嘴 */ }
  }
  // 三重保险。2026-09-10 事故：原先只挂 load 一处，iframe 若在注册监听之前就
  // 加载完（缓存命中/快网），load 永不再触发，注入落空 —— 用户看到的不是脸，
  // 而是 avatar 页自带的播放列表 UI，还能误点播放键放出真实录音。本地与真机均已复现。
  frame.addEventListener('load', injectFaceCss);   // 覆盖首次加载与后续任何重载
  injectFaceCss();                                 // 覆盖「load 已经过去了」
  var faceCssTries = 0;                            // 覆盖「文档还没建好」
  var faceCssTimer = setInterval(function() {
    faceCssTries += 1;
    injectFaceCss();
    if (faceReady || faceCssTries >= 40) { clearInterval(faceCssTimer); }
  }, 250);

  // file:// 拦截提示
  if (location.protocol === 'file:') {
    addBubble({type:'notice', text:'本页需通过本地服务器打开：双击档案目录里的 start_server.bat，然后浏览器访问 http://localhost:8020/ 。直接双击 HTML 无法加载档案数据与脸。'});
    sendBtn.disabled = true;
    return;
  }

  loadSettings();
  loadUiPrefs();
  startTtsProbeLoop();
  __SW_REGISTER_JS__

  // 页面一打开就取会话数据（与 chat_context 并行，不等待），刷新后才回放得了往次记录
  loadSessionsData();

  // 从 chat_context.json 载入 systemPrompt + shards
  fetch('__CONTEXT_PATH__', {cache: 'no-cache'})
    .then(function(r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(function(data) {
      systemPrompt = data.system_prompt || '';
      shards = Array.isArray(data.message_shards) ? data.message_shards : [];
      contextLoaded = true;
      applySessionsCard();
      updateChatState();
    })
    .catch(function(err) {
      clearChat();
      addBubble({type:'notice', text:'档案加载失败：' + err.message});
      sendBtn.disabled = true;
    });

  fetch('data/avatar/emotions.json', {cache: 'no-cache'})
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
  if (cfgVoiceText) { cfgVoiceText.addEventListener('change', onVoiceTextToggle); }
  if (cfgNoMemory) { cfgNoMemory.addEventListener('change', onNoMemoryToggle); }
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
window.splitMessages = splitMessages;
window.splitSegments = splitMessages;
__INTRO_CARD_JS__
})();
</script>
</body>
</html>
"""

_INTRO_CARD_CSS = """#intro-card{position:fixed;inset:0;z-index:9999;background:#faf7f2;overflow-y:auto;-webkit-overflow-scrolling:touch;display:flex;align-items:center;justify-content:center;padding:24px;box-sizing:border-box;}
#intro-card .ic-box{max-width:640px;width:100%;}
#intro-card h2{font-size:26px;line-height:1.5;margin:0 0 20px;color:#3a3330;font-weight:600;}
#intro-card ol{font-size:20px;line-height:1.9;color:#3a3330;margin:0 0 20px;padding-left:1.3em;}
#intro-card li{margin-bottom:12px;}
#intro-card .ic-voice{font-size:19px;line-height:1.8;color:#5a504a;background:#f0e9df;border-radius:10px;padding:14px 16px;margin:0 0 24px;}
#intro-card button{display:block;width:100%;min-height:56px;font-size:22px;font-weight:600;color:#fff;background:#8a7a6d;border:none;border-radius:12px;cursor:pointer;-webkit-tap-highlight-color:transparent;}
#intro-card button:active{background:#786a5e;}
"""

_INTRO_CARD_HTML = """<div id="intro-card"><div class="ic-box">
<h2>开始之前，请先看一下</h2>
<ol>
<li>这里跟您说话的不是她本人，是一个模拟。</li>
<li>它说的话，不是她生前说过的话。</li>
<li>它知道的一切，来自__INTRO_BUILDER__手机里的聊天记录，是__INTRO_BUILDER__那一边的视角。</li>
<li>它可能会说出她当年对__INTRO_BUILDER__讲的、关于您的话。</li>
<li>您和它说的话会被记录下来，存在这台电脑上。</li>
<li>随时可以关掉，不想聊就不聊。</li>
<li>这台电脑没开机的时候，这个页面打不开。</li>
</ol>
<p class="ic-voice">它的声音是用她的录音合成的，不是她本人在说话。</p>
<button id="intro-ok" type="button">我知道了</button>
</div></div>
"""

_INTRO_CARD_JS = """(function(){
  var card = document.getElementById('intro-card');
  var ok = document.getElementById('intro-ok');
  if (!card || !ok) return;
  ok.addEventListener('click', function(){ card.parentNode.removeChild(card); });
})();
"""


def build(person: str, archive_dir: str, viewer: str, context_path: str = 'data/chat_context.json',
          sessions_path: str = '',
          out_name: str = 'companion.html', lang: str = 'mandarin',
          tts_origin: str = 'auto', tts_token: str = '',
          intro_card: bool = False, intro_builder: str = '家人',
          llm_proxy: str = '', offline_fallback: bool = False,
          default_key: str = '', default_provider: str = 'deepseek') -> str:
    """Render companion.html content."""
    if not sessions_path:
        sessions_path = f'data/sessions_{viewer}.json'
    storage_key = 'companion_' + person + '_byok'
    if viewer != 'owner':
        storage_key += '_' + viewer

    # TTS origin
    if tts_origin == 'auto':
        tts_base_expr = "location.protocol + '//' + location.hostname + ':8022'"
    elif tts_origin == 'same':
        tts_base_expr = 'location.origin'
    else:
        tts_base_expr = "'" + tts_origin + "'"

    # Page tag
    if viewer == 'owner':
        page_tag = 'companion'
    else:
        page_tag = 'companion_' + viewer

    # TTS token line
    if tts_token:
        tts_token_line = "var TTS_TOKEN = '" + tts_token + "';\n"
        tts_headers_session = "headers: {'Content-Type': 'application/json', 'X-TTS-Token': TTS_TOKEN}"
        tts_headers_tts = "headers: { 'Content-Type': 'application/json', 'X-TTS-Token': TTS_TOKEN }"
        tts_fetch_health = ("return fetch(ttsBase + '/health', {method:'GET', headers: {'X-TTS-Token': TTS_TOKEN}})"
                            ".then(function(r){ ttsAvailable = !!r.ok; if (ttsAvailable) { flushSessionQueue(); } return ttsAvailable; })"
                            ".catch(function(){ ttsAvailable = false; return false; });")
    else:
        tts_token_line = ''
        tts_headers_session = "headers: {'Content-Type': 'application/json'}"
        tts_headers_tts = "headers: { 'Content-Type': 'application/json' }"
        tts_fetch_health = ("return fetch(ttsBase + '/health', {method:'GET'})"
                            ".then(function(r){ ttsAvailable = !!r.ok; if (ttsAvailable) { flushSessionQueue(); } return ttsAvailable; })"
                            ".catch(function(){ ttsAvailable = false; return false; });")

    # LLM proxy line (placed right after sessionId line)
    if llm_proxy:
        llm_proxy_line = "var LLM_PROXY = '" + llm_proxy + "';\n"
    else:
        llm_proxy_line = ''

    # 内置 API Key（构建时烘焙）：走 LLM 代理时页面不需要 key，一律注入 null
    if llm_proxy:
        default_key = ''
    if default_key:
        default_profile_line = ("var DEFAULT_PROFILE = {provider: '" + default_provider
                                + "', key: '" + default_key + "'};\n")
    else:
        default_profile_line = 'var DEFAULT_PROFILE = null;\n'

    # settingsComplete replacement
    if llm_proxy:
        settings_complete_fn = ("function settingsComplete() { if (typeof LLM_PROXY !== 'undefined' && LLM_PROXY) return true; "
                                "return settings && settings.url && settings.model && settings.key; }")
    else:
        settings_complete_fn = "function settingsComplete() { return settings && settings.url && settings.model && settings.key; }"

    # streamRequest proxy branch - placed BEFORE settings.url validation
    if llm_proxy:
        llm_proxy_branch = (
            "  if (typeof LLM_PROXY !== 'undefined' && LLM_PROXY && typeof TTS_TOKEN !== 'undefined' && TTS_TOKEN) {\n"
            "    var pEndpoint = location.origin + LLM_PROXY;\n"
            "    var pHeaders = { 'Content-Type': 'application/json', 'X-TTS-Token': TTS_TOKEN };\n"
            "    var pBody = { model: 'proxy', messages: messages, stream: true };\n"
            "    var pSse = sseCreate('openai');\n"
            "    var pAcc = ''; var pFallbackText = '';\n"
            "    fetch(pEndpoint, { method: 'POST', headers: pHeaders, body: JSON.stringify(pBody), signal: controller.signal })\n"
            "      .then(function(resp) {\n"
            "        if (!resp.ok) { return resp.text().then(function(t) { var snippet = t.substring(0, 200); throw new Error('接口错误 ' + resp.status + '：' + snippet); }); }\n"
            "        var reader = resp.body.getReader(); var decoder = new TextDecoder('utf-8');\n"
            "        function readChunk() {\n"
            "          return reader.read().then(function(result) {\n"
            "            if (result.done) {\n"
            "              var tail = decoder.decode(); if (tail) pFallbackText += tail;\n"
            "              var finalDeltas = sseFeed(pSse, tail);\n"
            "              for (var i = 0; i < finalDeltas.length; i++) { pAcc += finalDeltas[i]; onDelta(finalDeltas[i]); }\n"
            "              finalDeltas = sseFinish(pSse);\n"
            "              for (var j = 0; j < finalDeltas.length; j++) { pAcc += finalDeltas[j]; onDelta(finalDeltas[j]); }\n"
            "              if (!pSse.sawData && pFallbackText && pFallbackText.trim()) {\n"
            "                try {\n"
            "                  var json = JSON.parse(pFallbackText);\n"
            "                  var content = (json.choices && json.choices[0] && json.choices[0].message && json.choices[0].message.content) || '';\n"
            "                  if (!content && Array.isArray(json.content)) {\n"
            "                    var textParts = [];\n"
            "                    for (var p = 0; p < json.content.length; p++) { if (json.content[p] && json.content[p].type === 'text' && json.content[p].text) textParts.push(json.content[p].text); }\n"
            "                    content = textParts.join('');\n"
            "                  }\n"
            "                  if (content) { pAcc += content; onDelta(content); }\n"
            "                } catch(e) {}\n"
            "              }\n"
            "              onDone(pAcc, controller.signal.aborted);\n"
            "              return;\n"
            "            }\n"
            "            var text = decoder.decode(result.value, {stream: true}); if (text) pFallbackText += text;\n"
            "            var deltas = sseFeed(pSse, text);\n"
            "            for (var k = 0; k < deltas.length; k++) { pAcc += deltas[k]; onDelta(deltas[k]); }\n"
            "            return readChunk();\n"
            "          });\n"
            "        }\n"
            "        return readChunk();\n"
            "      })\n"
            "      .catch(function(err) { if (err.name === 'AbortError') { onDone(pAcc, true); } else { onError(err.message || '网络错误'); } });\n"
            "    return;\n"
            "  }\n"
        )
    else:
        llm_proxy_branch = ''

    # JS to hide config UI in proxy mode
    if llm_proxy:
        llm_proxy_hide_js = ("(function(){\n"
                             "  if (typeof LLM_PROXY === 'undefined' || !LLM_PROXY) return;\n"
                             "  var ids = ['cfg-provider', 'cfg-url', 'cfg-key'];\n"
                             "  for (var i = 0; i < ids.length; i++) {\n"
                             "    var el = document.getElementById(ids[i]);\n"
                             "    if (!el) continue;\n"
                             "    var box = el.parentNode;\n"
                             "    while (box && box.tagName !== 'DIV') { box = box.parentNode; }\n"
                             "    if (box && box.parentNode) { box.parentNode.removeChild(box); }\n"
                             "  }\n"
                             "  var hint = document.getElementById('cfg-hint');\n"
                             "  if (hint && hint.parentNode) { hint.parentNode.removeChild(hint); }\n"
                             "})();\n")
    else:
        llm_proxy_hide_js = ''

    # Intro card content
    if intro_card:
        intro_css = _INTRO_CARD_CSS
        intro_html = _INTRO_CARD_HTML.replace('__INTRO_BUILDER__', intro_builder)
        intro_js = _INTRO_CARD_JS
    else:
        intro_css = ''
        intro_html = ''
        intro_js = ''

    # Only register the service worker if the deployment explicitly provides it
    if offline_fallback:
        sw_register_js = (
            "if ('serviceWorker' in navigator && "
            "(location.protocol === 'https:' || location.hostname === 'localhost' || "
            "location.hostname === '127.0.0.1')) {\n"
            "    navigator.serviceWorker.register('/sw.js').catch(function(){});\n"
            "  }"
        )
    else:
        sw_register_js = ''

    mapping = {
        '__STORAGE_KEY__': storage_key,
        '__VIEWER__': viewer,
        '__CONTEXT_PATH__': context_path,
        '__SESSIONS_PATH__': sessions_path,
        '__TTS_LANG__': lang,
        '__TTS_BASE_EXPR__': tts_base_expr,
        '__PAGE_TAG__': page_tag,
        '__TTS_TOKEN_LINE__': tts_token_line,
        '__LLM_PROXY_LINE__': llm_proxy_line,
        '__DEFAULT_PROFILE_LINE__': default_profile_line,
        '__SETTINGS_COMPLETE_FN__': settings_complete_fn,
        '__LLM_PROXY_BRANCH__': llm_proxy_branch,
        '__LLM_PROXY_HIDE_JS__': llm_proxy_hide_js,
        '__TTS_HEADERS_TTS__': tts_headers_tts,
        '__TTS_HEADERS_SESSION__': tts_headers_session,
        '__TTS_FETCH_HEALTH__': tts_fetch_health,
        '__SW_REGISTER_JS__': sw_register_js,
        '__INTRO_CARD_CSS__': intro_css,
        '__INTRO_CARD_HTML__': intro_html,
        '__INTRO_CARD_JS__': intro_js,
    }
    html = _PLACEHOLDER_RE.sub(lambda m: mapping.get(m.group(0), m.group(0)), TEMPLATE)
    return html


def main() -> int:
    parser = argparse.ArgumentParser(description='Build companion.html page (8A-2a)')
    parser.add_argument('--person', required=True, help='Person slug')
    parser.add_argument('--archive-dir', default='archive_out', help='Archive directory (default: archive_out)')
    parser.add_argument('--viewer', default='owner', help='Viewer identity (default: owner)')
    parser.add_argument('--sessions-path', default='',
                        help='sessions 文件路径（默认 data/sessions_<viewer>.json）')
    parser.add_argument('--context-path', default='data/chat_context.json',
                        help='页面加载的 context 路径，相对页面（默认 data/chat_context.json）')
    parser.add_argument('--out-name', default='companion.html', help='输出文件名（默认 companion.html）')
    parser.add_argument('--lang', default='mandarin', choices=['mandarin', 'wu'],
                        help='TTS 语域（默认 mandarin）')
    parser.add_argument('--tts-origin', default='auto',
                        help="TTS 地址：auto=同主机:8022（默认）；same=同源（经隧道时用）；或指定完整 URL")
    parser.add_argument('--tts-token', default='',
                        help='TTS 服务 token，非空则页面请求带 X-TTS-Token 头')
    parser.add_argument('--intro-card', action='store_true',
                        help='每次打开先显示大字说明卡，点「我知道了」才进对话（老人模式）')
    parser.add_argument('--intro-builder', default='家人',
                        help='说明卡文案里对建档者的称呼（默认「家人」，例如「儿子」）')
    parser.add_argument('--llm-proxy', default='',
                        help='LLM 代理路径（同源，如 /llm/v1/chat/completions）；给定后页面固定用它、不再需要 API key')
    parser.add_argument('--default-key', default='',
                        help='构建时内置的 API Key，页面开箱即用（与 --default-key-env 二选一）')
    parser.add_argument('--default-key-env', default='',
                        help='构建时读取内置 API Key 的环境变量名（与 --default-key 二选一）')
    parser.add_argument('--default-provider', default='deepseek',
                        help='内置 API Key 对应的服务商：openai/anthropic/deepseek/kimi/custom（默认 deepseek）')
    parser.add_argument('--offline-fallback', action='store_true',
                        help='注册 Service Worker，以便在机器不可达时显示 offline.html（仅用于随附 sw.js 和 offline.html 的部署）')
    args = parser.parse_args()

    if not _PERSON_RE.fullmatch(args.person):
        print(f'错误：--person 参数 "{args.person}" 不符合正则 ^[a-zA-Z0-9][a-zA-Z0-9_-]*$', file=sys.stderr)
        return 2

    if not _VIEWER_RE.fullmatch(args.viewer):
        print(f'错误：--viewer 参数 "{args.viewer}" 不符合正则 ^[a-z][a-z0-9_-]{{0,31}}$', file=sys.stderr)
        return 2

    # Validate context path (strict whitelist)
    if not _CONTEXT_PATH_RE.fullmatch(args.context_path) or '%' in args.context_path:
        print(f'错误：--context-path 参数 "{args.context_path}" 不符合安全路径规范', file=sys.stderr)
        return 2
    segments = args.context_path.split('/')
    if any(seg in ('.', '..') for seg in segments):
        print(f'错误：--context-path 参数 "{args.context_path}" 不能包含 "." 或 ".." 段', file=sys.stderr)
        return 2

    if not args.sessions_path:
        args.sessions_path = f'data/sessions_{args.viewer}.json'
    if not _CONTEXT_PATH_RE.fullmatch(args.sessions_path) or '%' in args.sessions_path:
        print(f'错误：--sessions-path 参数 "{args.sessions_path}" 不符合安全路径规范', file=sys.stderr)
        return 2
    sessions_segments = args.sessions_path.split('/')
    if any(seg in ('.', '..') for seg in sessions_segments):
        print(f'错误：--sessions-path 参数 "{args.sessions_path}" 不能包含 "." 或 ".." 段', file=sys.stderr)
        return 2

    # Validate out-name
    if not _OUT_RE.fullmatch(args.out_name):
        print(f'错误：--out-name 参数 "{args.out_name}" 不符合正则 ^[A-Za-z0-9_.-]+\\.html$', file=sys.stderr)
        return 2

    # Validate tts-origin (if not auto/same, must be http(s) URL without path, query, fragment)
    if args.tts_origin not in ('auto', 'same'):
        if not _TTS_ORIGIN_RE.fullmatch(args.tts_origin):
            print(f'错误：--tts-origin 参数 "{args.tts_origin}" 必须是 "http(s)://主机名(:端口)" 形式', file=sys.stderr)
            return 2
        if any(ch in args.tts_origin for ch in '<>\\"\'`'):
            print(f'错误：--tts-origin 参数 "{args.tts_origin}" 不能包含特殊字符', file=sys.stderr)
            return 2

    # Validate tts-token
    if not _TTS_TOKEN_RE.fullmatch(args.tts_token):
        print(f'错误：--tts-token 参数不符合正则 ^[A-Za-z0-9_-]{{0,128}}$', file=sys.stderr)
        return 2

    # Validate intro-builder
    if not _INTRO_BUILDER_RE.fullmatch(args.intro_builder):
        print(f'错误：--intro-builder 参数 "{args.intro_builder}" 不符合正则 ^[一-龥]{{1,6}}$', file=sys.stderr)
        return 2

    # Validate llm-proxy
    if args.llm_proxy:
        if not _LLM_PROXY_RE.fullmatch(args.llm_proxy):
            print(f'错误：--llm-proxy 参数 "{args.llm_proxy}" 不符合正则 ^/[A-Za-z0-9_./-]{{1,120}}$', file=sys.stderr)
            return 2
        if not args.tts_token:
            print('错误：--llm-proxy 需要同时提供 --tts-token（代理必须鉴权，否则会成为开放的 LLM 中转）', file=sys.stderr)
            return 2

    # 内置 API Key：--default-key 与 --default-key-env 二选一
    if args.default_key and args.default_key_env:
        print('错误：--default-key 与 --default-key-env 不能同时给出，只能二选一', file=sys.stderr)
        return 2

    default_key = args.default_key
    if args.default_key_env:
        default_key = os.environ.get(args.default_key_env, '')
        if not default_key:
            print(f'错误：环境变量 {args.default_key_env} 未设置或为空，拒绝生成没有内置 Key 的页面', file=sys.stderr)
            return 2

    if args.default_provider not in ('openai', 'anthropic', 'deepseek', 'kimi', 'custom'):
        print(f'错误：--default-provider 参数 "{args.default_provider}" 不在支持列表 openai/anthropic/deepseek/kimi/custom 中', file=sys.stderr)
        return 2

    if default_key and any(ch in default_key for ch in '"\'\\\n\r\u2028\u2029<>'):
        print('错误：--default-key 含有引号、反斜杠、换行、回车、行分隔符或尖括号，无法安全写进页面', file=sys.stderr)
        return 2

    if default_key and os.path.basename(args.out_name.replace('\\', '/')).casefold() in ('avatar.html', 'chat.html', 'index.html'):
        print(f'错误：--out-name "{args.out_name}" 是档案发布用的文件名（tools/build_archive.py 会把它复制或生成到 archive_dist/ 分发出去），'
              '带内置 Key 的页面绝不能写进该文件，请改用别的 --out-name', file=sys.stderr)
        return 2

    if args.llm_proxy and default_key:
        print('警告：已指定 --llm-proxy，页面走代理不需要 API Key，内置 Key 被忽略', file=sys.stderr)

    context_path = os.path.join(args.archive_dir, *args.context_path.split('/'))
    if not os.path.exists(context_path):
        print(f'错误：缺少 {context_path}（{args.context_path} 不存在）', file=sys.stderr)
        return 1

    html = build(args.person, args.archive_dir, args.viewer,
                 context_path=args.context_path, sessions_path=args.sessions_path,
                 out_name=args.out_name,
                 lang=args.lang, tts_origin=args.tts_origin,
                 tts_token=args.tts_token,
                 intro_card=args.intro_card, intro_builder=args.intro_builder,
                 llm_proxy=args.llm_proxy,
                 offline_fallback=args.offline_fallback,
                 default_key=default_key, default_provider=args.default_provider)

    out_path = os.path.join(args.archive_dir, args.out_name)
    tmp_path = out_path + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8', newline='') as f:
        f.write(html)
    os.replace(tmp_path, out_path)

    byte_count = os.path.getsize(out_path)
    print(f'已生成 {out_path}（{byte_count} 字节）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
