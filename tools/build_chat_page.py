#!/usr/bin/env python3
"""
Build a self-contained BYOK chat page for a memorial archive.
Usage:
    python tools/build_chat_page.py --person <slug> [--out <path>]
"""

import argparse
import html as _html
import json
import os
import re
import sys

SLUG_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]*$')
RAW_GUARD = 'raw'
FILE_MARKER = 'tools/build_chat_page.py'
DEFAULT_CONTEXT = 'archive_out/data/chat_context.json'


def esc(s):
    """Escape a string for safe HTML embedding."""
    return _html.escape(str(s), quote=True)


def find_repo_root(start):
    """Find repository root by walking up until FILE_MARKER is found."""
    current = os.path.abspath(start)
    while True:
        if os.path.isfile(os.path.join(current, FILE_MARKER)):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def validate_and_resolve(args):
    """Validate args, return paths; exit 2 with message on any error."""
    if not args.person or not SLUG_RE.match(args.person):
        print('error: invalid --person slug')
        sys.exit(2)
    if '../' in args.person or args.person in ('.', '..'):
        print('error: invalid --person slug')
        sys.exit(2)

    repo = find_repo_root(os.getcwd())
    if not repo:
        print(f'error: repository root not found (missing {FILE_MARKER})')
        sys.exit(2)

    person_dir = os.path.join(repo, 'people', args.person)
    if not os.path.isdir(person_dir):
        print(f'error: person directory not found: {person_dir}')
        sys.exit(2)

    archive_dir = os.path.join(person_dir, 'archive_out')
    if os.path.basename(archive_dir) == RAW_GUARD or args.person == RAW_GUARD:
        print('error: raw guard')
        sys.exit(2)

    context_path = os.path.join(archive_dir, 'data', 'chat_context.json')
    if not os.path.isfile(context_path):
        print(f'error: {context_path} not found; run build_chat_context.py first')
        sys.exit(2)

    # Resolve raw tree for guard checks
    raw_tree = os.path.realpath(os.path.join(person_dir, RAW_GUARD))

    # Check context path is not inside raw tree
    resolved_context = os.path.realpath(context_path)
    if resolved_context.startswith(raw_tree + os.sep) or resolved_context == raw_tree:
        print('error: context path resolves inside raw tree')
        sys.exit(2)

    if args.out:
        out_path = os.path.abspath(args.out)
        out_dir = os.path.dirname(out_path)
        if not os.path.isdir(out_dir):
            print(f'error: output directory does not exist: {out_dir}')
            sys.exit(2)
    else:
        out_path = os.path.join(archive_dir, 'chat.html')

    # Final guard: resolved output must not be inside resolved raw tree
    resolved_out = os.path.realpath(out_path)
    if resolved_out.startswith(raw_tree + os.sep) or resolved_out == raw_tree:
        print('error: output path resolves inside raw tree')
        sys.exit(2)

    return context_path, out_path


def load_context(context_path):
    """Read chat context JSON; return display_name or '' on error."""
    try:
        with open(context_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('display_name', '') or data.get('person_name', '') or ''
    except Exception:
        return ''


class PageBuilder:
    """Builds the HTML page."""

    def __init__(self, slug, display_name):
        self.slug = slug
        self.display_name = display_name
        self.storage_key = f'chat_byok_{slug}'

    def build(self):
        """Return the full HTML string."""
        html = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>__TITLE__ · 模拟对话</title>
<style>
:root {
  --bg: #f5f5f7;
  --panel: #ffffff;
  --text: #1d1d1f;
  --muted: #86868b;
  --accent: #007aff;
  --accent-dark: #0062cc;
  --user-bubble: #e8f0fe;
  --subject-bubble: #ffffff;
  --border: #e5e5e7;
  --danger: #ff3b30;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body {
  height: 100%;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  background: var(--bg);
  color: var(--text);
}
body {
  display: flex;
  flex-direction: column;
  max-width: 720px;
  margin: 0 auto;
  height: 100dvh;
  overflow: hidden;
}
/* Header */
header {
  display: flex;
  align-items: center;
  padding: 10px 14px 6px;
  background: var(--panel);
  border-bottom: 1px solid var(--border);
  gap: 10px;
  flex-shrink: 0;
}
.avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: #e0e0e0;
  object-fit: cover;
  flex-shrink: 0;
}
.header-info { flex: 1; min-width: 0; }
.header-name {
  font-size: 17px;
  font-weight: 600;
  line-height: 1.3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.header-banner {
  font-size: 11px;
  color: var(--muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.settings-btn {
  width: 40px;
  height: 40px;
  border: none;
  background: transparent;
  font-size: 22px;
  cursor: pointer;
  border-radius: 8px;
  flex-shrink: 0;
  color: var(--muted);
}
.settings-btn:hover { background: var(--bg); }
/* Chat area */
#chat {
  flex: 1;
  overflow-y: auto;
  padding: 16px 12px 8px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  -webkit-overflow-scrolling: touch;
}
.bubble {
  max-width: 85%;
  padding: 10px 14px;
  border-radius: 16px;
  line-height: 1.5;
  font-size: 15px;
  white-space: pre-wrap;
  word-break: break-word;
  position: relative;
}
.bubble.user {
  align-self: flex-end;
  background: var(--user-bubble);
  border-bottom-right-radius: 4px;
}
.bubble.subject {
  align-self: flex-start;
  background: var(--subject-bubble);
  border: 1px solid var(--border);
  border-bottom-left-radius: 4px;
  display: flex;
  gap: 8px;
  align-items: flex-start;
}
.bubble-avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  flex-shrink: 0;
  background: #e0e0e0;
  margin-top: 2px;
}
.bubble-content { flex: 1; min-width: 0; }
.bubble.notice {
  align-self: center;
  background: transparent;
  color: var(--danger);
  font-size: 13px;
  text-align: center;
  padding: 6px 10px;
}
.bubble.center {
  align-self: center;
  text-align: center;
  background: transparent;
  color: var(--muted);
  font-size: 14px;
  padding: 20px;
}
/* Input bar */
#input-bar {
  display: flex;
  gap: 8px;
  padding: 8px 12px calc(12px + env(safe-area-inset-bottom));
  background: var(--panel);
  border-top: 1px solid var(--border);
  flex-shrink: 0;
  align-items: flex-end;
}
#input-text {
  flex: 1;
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 10px 14px;
  font-size: 15px;
  font-family: inherit;
  line-height: 1.4;
  resize: none;
  max-height: 100px;
  outline: none;
  background: var(--bg);
}
#input-text:focus { border-color: var(--accent); background: #fff; }
#send-btn {
  width: 56px;
  height: 44px;
  border: none;
  border-radius: 22px;
  background: var(--accent);
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  flex-shrink: 0;
  min-height: 44px;
}
#send-btn:disabled { background: #c7c7cc; }
#send-btn.stop { background: var(--danger); }
/* Settings drawer */
#drawer-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.4);
  z-index: 20;
  display: none;
}
#drawer {
  position: fixed;
  top: 0;
  right: -300px;
  width: 280px;
  height: 100dvh;
  background: var(--panel);
  z-index: 21;
  padding: 20px 18px;
  transition: right 0.25s ease;
  overflow-y: auto;
  box-shadow: -4px 0 20px rgba(0,0,0,0.15);
}
#drawer.open { right: 0; }
#drawer-overlay.open { display: block; }
.drawer-title {
  font-size: 18px;
  font-weight: 700;
  margin-bottom: 18px;
}
.drawer-label {
  font-size: 13px;
  color: var(--muted);
  margin-bottom: 6px;
  margin-top: 14px;
  display: block;
}
.drawer-input {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 9px 10px;
  font-size: 14px;
  font-family: inherit;
  outline: none;
  background: #fff;
}
.drawer-input:focus { border-color: var(--accent); }
.drawer-note {
  font-size: 11px;
  color: var(--muted);
  margin-top: 24px;
  line-height: 1.4;
}
.save-btn {
  width: 100%;
  height: 44px;
  border: none;
  border-radius: 22px;
  background: var(--accent);
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  margin-top: 20px;
  cursor: pointer;
}
.save-btn:active { background: var(--accent-dark); }
.hidden { display: none !important; }
</style>
</head>
<body>
<header>
  <img class="avatar" id="avatar-img" src="data/avatar/avatar.png" alt="" onerror="this.style.display='none'">
  <div class="header-info">
    <div class="header-name" id="header-name">__DISPLAY_NAME__</div>
    <div class="header-banner">基于档案的检索式模拟对话 · 非本人</div>
  </div>
  <button class="settings-btn" id="settings-btn" title="设置">⚙</button>
</header>

<div id="chat"></div>

<div id="input-bar">
  <textarea id="input-text" rows="1" placeholder="输入消息…"></textarea>
  <button id="send-btn" disabled>发送</button>
</div>

<div id="drawer-overlay"></div>
<div id="drawer">
  <div class="drawer-title">对话设置</div>
  <label class="drawer-label" for="cfg-url">接口地址</label>
  <input class="drawer-input" id="cfg-url" type="text" placeholder="https://api.deepseek.com/chat/completions（任意 OpenAI 兼容端点）">
  <label class="drawer-label" for="cfg-model">模型名</label>
  <input class="drawer-input" id="cfg-model" type="text" placeholder="例如 deepseek-chat">
  <label class="drawer-label" for="cfg-key">API Key</label>
  <input class="drawer-input" id="cfg-key" type="password" placeholder="sk-…">
  <button class="save-btn" id="save-btn">保存</button>
  <div class="drawer-note">设置仅保存在本浏览器（localStorage）。对话内容仅存在于当前页面内存中，刷新后清空。</div>
</div>

<script>
(function() {
'use strict';

/* ========= storage key ========= */
var storageKey = '__STORAGE_KEY__';
var THE_STOP_SET = new Set(["的了","了 的","我们","你们","他们","这个","那个","什么","怎么","不是","就是","还是","但是","所以","因为","如果","可以","没有","知道","现在","时候","一个","有点","这样","那样"].map(function(t){return t.replace(/ /g,'');}));

/* ========= DOM refs ========= */
var chat = document.getElementById('chat');
var inputText = document.getElementById('input-text');
var sendBtn = document.getElementById('send-btn');
var settingsBtn = document.getElementById('settings-btn');
var drawer = document.getElementById('drawer');
var drawerOverlay = document.getElementById('drawer-overlay');
var saveBtn = document.getElementById('save-btn');
var cfgUrl = document.getElementById('cfg-url');
var cfgModel = document.getElementById('cfg-model');
var cfgKey = document.getElementById('cfg-key');

/* ========= state ========= */
var settings = null;
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

/* ========= helpers ========= */
function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

function loadSettings() {
  try {
    var raw = localStorage.getItem(storageKey);
    if (raw) {
      var parsed = JSON.parse(raw);
      settings = {
        url: parsed.url || '',
        model: parsed.model || '',
        key: parsed.key || ''
      };
    } else {
      settings = {url:'', model:'', key:''};
    }
  } catch(e) {
    settings = {url:'', model:'', key:''};
  }
}

function settingsComplete() {
  return settings && settings.url && settings.model && settings.key;
}

function saveSettings() {
  settings = {url: cfgUrl.value.trim(), model: cfgModel.value.trim(), key: cfgKey.value.trim()};
  try {
    localStorage.setItem(storageKey, JSON.stringify(settings));
  } catch(e) {}
  closeDrawer();
  updateChatState();
}

function openDrawer() {
  cfgUrl.value = settings.url;
  cfgModel.value = settings.model;
  cfgKey.value = settings.key;
  drawer.classList.add('open');
  drawerOverlay.classList.add('open');
}

function closeDrawer() {
  drawer.classList.remove('open');
  drawerOverlay.classList.remove('open');
}

function clearChat() {
  chat.innerHTML = '';
}

function addBubble(opts) {
  var div = document.createElement('div');
  if (opts.type === 'user') {
    div.className = 'bubble user';
  } else if (opts.type === 'subject') {
    div.className = 'bubble subject';
    var av = document.createElement('img');
    av.className = 'bubble-avatar';
    av.alt = '';
    av.src = 'data/avatar/avatar.png';
    av.onerror = function(){ this.remove(); };
    var contentWrap = document.createElement('div');
    contentWrap.className = 'bubble-content';
    contentWrap.textContent = opts.text;
    div.appendChild(av);
    div.appendChild(contentWrap);
  } else if (opts.type === 'notice') {
    div.className = 'bubble notice';
    div.textContent = opts.text;
  } else {
    div.className = 'bubble center';
    div.textContent = opts.text;
  }
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
  return div;
}

function confNotice() {
  clearChat();
  addBubble({type:'center', text:'点右上角 ⚙ 配置接口后开始对话'});
  sendBtn.disabled = true;
}

function systemNotice(msg) {
  addBubble({type:'notice', text: msg});
}

function updateChatState() {
  if (!settingsComplete()) {
    confNotice();
    return;
  }
  if (chat.children.length === 0) {
    addBubble({type:'center', text:'开始对话吧…'});
  }
  sendBtn.disabled = false;
  sendBtn.textContent = '发送';
  streaming = false;
  if (controller) {
    try { controller.abort(); } catch(e) {}
    controller = null;
  }
}

/* ========= PURE FUNCTIONS (top-level in script) ========= */

function extractTokens(text) {
  var tokens = [];
  var seen = {};
  var cjkRe = /[\u4e00-\u9fff]+/g;
  var m;
  while ((m = cjkRe.exec(text)) !== null) {
    var run = m[0];
    for (var i = 0; i < run.length - 1; i++) {
      var tok = run.substr(i, 2);
      if (tok[0] === tok[1]) continue;
      if (THE_STOP_SET.has(tok)) continue;
      var key = 'c' + tok;
      if (!seen[key]) {
        seen[key] = true;
        tokens.push(tok);
      }
    }
  }
  var wordRe = /[a-z0-9]{2,}/g;
  while ((m = wordRe.exec(text.toLowerCase())) !== null) {
    var w = m[0];
    if (w[0] === w[1]) continue;
    var key2 = 'w' + w;
    if (!seen[key2]) {
      seen[key2] = true;
      tokens.push(w);
    }
  }
  return tokens;
}

function scoreText(tokens, text) {
  var score = 0;
  var lower = text.toLowerCase();
  for (var i = 0; i < tokens.length; i++) {
    var tok = tokens[i];
    var idx = 0;
    while (true) {
      idx = lower.indexOf(tok, idx);
      if (idx === -1) break;
      score++;
      idx += tok.length;
    }
  }
  return score;
}

function retrieveSnippets(tokens, records, opts) {
  opts = opts || {};
  var top = opts.top || 6;
  var results = [];
  for (var i = 0; i < records.length; i++) {
    var rec = records[i];
    if (rec.content_type !== 'text') continue;
    var txt = (rec.text || '').trim();
    if (!txt) continue;
    var score = scoreText(tokens, txt);
    if (score <= 0) continue;
    results.push({
      date: String(rec.timestamp || '').substring(0, 10),
      text: txt.length > 200 ? txt.substring(0, 200) : txt,
      score: score,
      isSubject: rec.sender === 'subject'
    });
  }
  results.sort(function(a, b) {
    if (b.score !== a.score) return b.score - a.score;
    if (a.isSubject !== b.isSubject) return a.isSubject ? -1 : 1;
    return a.text.length - b.text.length;
  });
  return results.slice(0, top).map(function(r) {
    return {date: r.date, text: r.text, score: r.score};
  });
}

function retrieveKnowledge(tokens, memories, transcripts, opts) {
  opts = opts || {};
  var memTop = opts.memTop || 3;
  var transTop = opts.transTop || 2;
  var mem = [];
  var i, e, score, txt;
  memories = memories || [];
  transcripts = transcripts || [];
  for (i = 0; i < memories.length; i++) {
    e = memories[i];
    var title = String(e.title || '').trim();
    var texts = Array.isArray(e.texts) ? e.texts : [];
    var hay = title + '\n' + texts.join('\n');
    if (!hay.trim()) continue;
    score = scoreText(tokens, hay);
    if (score <= 0) continue;
    var body = String(texts[0] || '').trim();
    txt = title + (body ? ' — ' + body : '');
    if (txt.length > 240) txt = txt.substring(0, 240);
    mem.push({label: '[家人确认记忆 Tier-1]', date: String(e.date || ''), text: txt, score: score});
  }
  mem.sort(function(a, b) { return b.score - a.score; });
  mem = mem.slice(0, memTop);
  var trans = [];
  for (i = 0; i < transcripts.length; i++) {
    e = transcripts[i];
    txt = String(e.text || '').trim();
    if (!txt) continue;
    score = scoreText(tokens, txt);
    if (score <= 0) continue;
    if (txt.length > 200) txt = txt.substring(0, 200);
    var lbl = e.media === 'video' ? '[视频转写 Tier-2]' : '[语音转写 Tier-2]';
    trans.push({label: lbl, date: String(e.date || ''), text: txt, score: score});
  }
  trans.sort(function(a, b) { return b.score - a.score; });
  trans = trans.slice(0, transTop);
  return {memories: mem, transcripts: trans};
}

function buildRetrievalBlock(snippets) {
  if (!snippets || snippets.length === 0) return '';
  var lines = [];
  for (var i = 0; i < snippets.length; i++) {
    lines.push((snippets[i].label || '[档案检索 Tier-2]') + ' ' + snippets[i].date + ' · ' + snippets[i].text);
  }
  var block = lines.join('\n');
  var budget = 2200;
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
  for (var i = 0; i < recent.length; i++) {
    messages.push({role: recent[i].role, content: recent[i].content});
  }
  var content = retrievalBlock ? retrievalBlock + '\n\n' + userText : userText;
  messages.push({role:'user', content: content});
  return messages;
}

/* ========= SSE state machine (pure, testable) ========= */
function sseCreate() {
  return { buffer: '', sawData: false, done: false };
}

function sseFeed(state, chunkText) {
  var deltas = [];
  if (state.done) return deltas;
  state.buffer += chunkText || '';
  var lines = state.buffer.split('\n');
  // Keep last (incomplete) segment in buffer
  state.buffer = lines.pop() || '';
  for (var i = 0; i < lines.length; i++) {
    var line = lines[i];
    if (line.charAt(line.length - 1) === '\r') {
      line = line.substring(0, line.length - 1);
    }
    var extra = sseProcessLine(state, line);
    deltas = deltas.concat(extra);
    if (state.done) break;
  }
  return deltas;
}

function sseFinish(state) {
  var deltas = [];
  if (state.done) {
    state.buffer = '';
    return deltas;
  }
  var line = state.buffer;
  state.buffer = '';
  if (line) {
    if (line.charAt(line.length - 1) === '\r') {
      line = line.substring(0, line.length - 1);
    }
    deltas = sseProcessLine(state, line);
  }
  return deltas;
}

function sseProcessLine(state, line) {
  var deltas = [];
  if (state.done) return deltas;
  if (line.indexOf('data:') !== 0) return deltas;
  state.sawData = true;
  var data = line.substring(5).trim();
  if (data === '[DONE]') {
    state.done = true;
    return deltas;
  }
  try {
    var obj = JSON.parse(data);
    var delta = obj.choices && obj.choices[0] && obj.choices[0].delta && obj.choices[0].delta.content;
    if (delta) deltas.push(delta);
  } catch(e) {
    // skip malformed / non-JSON lines silently
  }
  return deltas;
}

/* ========= shard loading ========= */
function loadShards() {
  if (shardsLoading) return Promise.resolve();
  shardsLoading = true;
  var names = shards || [];
  var loadedCount = 0;
  var failedCount = 0;
  var fetches = names.map(function(name) {
    if (shardStatus[name] === 'failed') return;
    var safeName = String(name).replace(/[^a-zA-Z0-9_/.-]/g, '_');
    return fetch('data/' + safeName)
      .then(function(r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function(data) {
        shardCache[name] = Array.isArray(data) ? data : [data];
        shardStatus[name] = true;
        loadedCount++;
      })
      .catch(function() {
        shardStatus[name] = 'failed';
        failedCount++;
      });
  });
  return Promise.all(fetches).then(function() {
    shardsLoading = false;
    console.info('shards loaded=' + loadedCount + ' failed=' + failedCount + ' total=' + names.length);
  });
}

function loadKnowledge() {
  if (knowledgeLoading || knowledgeCache !== null) return Promise.resolve(knowledgeCache);
  knowledgeLoading = true;
  var out = {memories: [], transcripts: []};
  var one = function(name, key) {
    return fetch('data/' + name)
      .then(function(r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function(data) {
        if (data && Array.isArray(data.entries)) out[key] = data.entries;
      })
      .catch(function() {});
  };
  return Promise.all([one('memories.json', 'memories'), one('transcripts.json', 'transcripts')])
    .then(function() {
      knowledgeCache = out;
      knowledgeLoading = false;
      console.info('knowledge memories=' + out.memories.length + ' transcripts=' + out.transcripts.length);
      return out;
    });
}

function collectAllRecords() {
  var all = [];
  for (var name in shardCache) {
    if (shardCache[name]) all = all.concat(shardCache[name]);
  }
  return all;
}

/* ========= streaming request ========= */
function streamRequest(messages, onDelta, onDone, onError) {
  if (!settingsComplete()) {
    onError('请先在设置中配置接口');
    return;
  }
  controller = new AbortController();
  streaming = true;
  sendBtn.textContent = '停止';
  sendBtn.classList.add('stop');

  var endpoint = settings.url;
  if (!/^https?:\/\//i.test(endpoint)) {
    onError('接口地址格式不正确');
    return;
  }

  var acc = '';
  var fallbackText = ''; // raw text for non-stream fallback detection
  var sseState = sseCreate();

  fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer ' + settings.key
    },
    body: JSON.stringify({model: settings.model, messages: messages, stream: true}),
    signal: controller.signal
  })
  .then(function(resp) {
    if (!resp.ok) {
      return resp.text().then(function(t) {
        var snippet = t.substring(0, 200);
        throw new Error('接口错误 ' + resp.status + '：' + snippet);
      });
    }
    var reader = resp.body.getReader();
    var decoder = new TextDecoder('utf-8');

    function readChunk() {
      return reader.read().then(function(result) {
        if (result.done) {
          var tail = decoder.decode();
          if (tail) fallbackText += tail;
          var finalDeltas = sseFeed(sseState, tail);
          for (var i = 0; i < finalDeltas.length; i++) {
            acc += finalDeltas[i];
            onDelta(finalDeltas[i]);
          }
          finalDeltas = sseFinish(sseState);
          for (var j = 0; j < finalDeltas.length; j++) {
            acc += finalDeltas[j];
            onDelta(finalDeltas[j]);
          }
          if (!sseState.sawData && fallbackText && fallbackText.trim()) {
            try {
              var json = JSON.parse(fallbackText);
              var content = (json.choices && json.choices[0] && json.choices[0].message && json.choices[0].message.content) || '';
              if (content) {
                acc += content;
                onDelta(content);
              }
            } catch(e) {
              // Not JSON, ignore
            }
          }
          if (controller.signal.aborted) {
            onDone(acc, true);
          } else {
            onDone(acc, false);
          }
          return;
        }
        var text = decoder.decode(result.value, {stream: true});
        if (text) fallbackText += text;
        var deltas = sseFeed(sseState, text);
        for (var k = 0; k < deltas.length; k++) {
          acc += deltas[k];
          onDelta(deltas[k]);
        }
        return readChunk();
      });
    }
    return readChunk();
  })
  .catch(function(err) {
    if (err.name === 'AbortError') {
      onDone(acc, true);
    } else {
      onError(err.message || '网络错误');
    }
  });
}

/* ========= send flow ========= */
function sendMessage() {
  if (!settingsComplete()) return;
  if (streaming) {
    // stop
    if (controller) controller.abort();
    return;
  }
  var text = inputText.value.trim();
  if (!text) return;
  inputText.value = '';
  inputText.style.height = 'auto';
  addBubble({type:'user', text:text});
  history.push({role:'user', content:text});

  // build a temporary assistant bubble
  var assistantBubble = addBubble({type:'subject', text:''});
  var contentEl = assistantBubble.querySelector('.bubble-content');
  var acc = '';

  var run = function() {
    var allRecords = collectAllRecords();
    var tokens = extractTokens(text);
    var snippets = retrieveSnippets(tokens, allRecords, {top:6});
    var kn = knowledgeCache || {memories: [], transcripts: []};
    var kres = retrieveKnowledge(tokens, kn.memories, kn.transcripts, {memTop: 3, transTop: 2});
    var combined = kres.memories.concat(snippets, kres.transcripts);
    var block = buildRetrievalBlock(combined);
    var messages = buildMessages(systemPrompt, history, block, text);

    streamRequest(messages,
      function(delta) {
        acc += delta;
        contentEl.textContent = acc;
        chat.scrollTop = chat.scrollHeight;
      },
      function(full, aborted) {
        if (aborted) {
          contentEl.textContent = (acc || '') + ' ⏹';
        } else {
          contentEl.textContent = full || acc;
        }
        history.push({role:'assistant', content: contentEl.textContent});
        streaming = false;
        sendBtn.textContent = '发送';
        sendBtn.classList.remove('stop');
        controller = null;
        updateChatState();
      },
      function(msg) {
        contentEl.parentNode.remove();
        systemNotice(msg);
        history.pop();
        if (history.length && history[history.length-1].role === 'user') history.pop();
        streaming = false;
        sendBtn.textContent = '发送';
        sendBtn.classList.remove('stop');
        controller = null;
        updateChatState();
      }
    );
  };

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

/* ========= init ========= */
function init() {
  loadSettings();

  // load context
  fetch('data/chat_context.json')
    .then(function(r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(function(data) {
      systemPrompt = data.system_prompt || '';
      shards = data.message_shards || [];
      updateChatState();
    })
    .catch(function(err) {
      clearChat();
      addBubble({type:'notice', text:'档案加载失败：' + err.message});
      sendBtn.disabled = true;
    });

  // auto-grow
  inputText.addEventListener('input', function() {
    this.style.height = 'auto';
    var h = Math.min(this.scrollHeight, 100);
    this.style.height = h + 'px';
  });

  // send on click / enter
  sendBtn.addEventListener('click', function() {
    sendMessage();
  });
  inputText.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  // drawer
  settingsBtn.addEventListener('click', openDrawer);
  drawerOverlay.addEventListener('click', closeDrawer);
  saveBtn.addEventListener('click', saveSettings);

  renderFields();
}

function renderFields() {
  if (settings) {
    cfgUrl.value = settings.url;
    cfgModel.value = settings.model;
    cfgKey.value = settings.key;
  }
}

init();

// expose pure functions for external contract testing (no runtime effect)
window.extractTokens = extractTokens;
window.scoreText = scoreText;
window.retrieveSnippets = retrieveSnippets;
window.retrieveKnowledge = retrieveKnowledge;
window.loadKnowledge = loadKnowledge;
window.buildRetrievalBlock = buildRetrievalBlock;
window.buildMessages = buildMessages;
window.sseCreate = sseCreate;
window.sseFeed = sseFeed;
window.sseFinish = sseFinish;

})();
</script>
</body>
</html>"""
        display_name = esc(self.display_name or self.slug)
        html = html.replace('__TITLE__', display_name)
        html = html.replace('__DISPLAY_NAME__', display_name)
        html = html.replace('__STORAGE_KEY__', esc(self.storage_key))
        return html


def main():
    parser = argparse.ArgumentParser(description='Build BYOK chat page')
    parser.add_argument('--person', required=True, help='person slug')
    parser.add_argument('--out', help='output path (default people/<slug>/archive_out/chat.html)')
    args = parser.parse_args()

    context_path, out_path = validate_and_resolve(args)
    display_name = load_context(context_path)

    builder = PageBuilder(args.person, display_name)
    html = builder.build()

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)

    size_kb = os.path.getsize(out_path) / 1024.0
    rel = os.path.relpath(out_path)
    print(f'chat={rel.replace(os.sep, "/")} size_kb={size_kb:.0f}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
