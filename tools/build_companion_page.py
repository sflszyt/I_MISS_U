#!/usr/bin/env python3
"""Build companion.html - merged avatar face + chat brain page (8A-2a)."""

import argparse
import json
import os
import re
import sys

if __package__:
    from .father_model_policy import load_policy
else:
    from father_model_policy import load_policy

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
  <span class="subtitle">数字档案 · 模拟对话 · 非本人 · D4</span>
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
var VOICE_GROUPS = __VOICE_GROUPS__;
var AUTO_VOICE_SESSION = __AUTO_VOICE_SESSION__;
var autoVoiceSession = null;
var AUTO_VOICE_CUE = 'data:audio/wav;base64,UklGRuQSAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YcASAAAAAAkAIAA4AEEAMAADAMP/gv9Y/1n/j//y/2sA2QAYAQ8BtwAfAG7/0f55/ob+/v7I/7MAgQH1AegBUwFXADP/Mv6f/an9Vv6C/+AAFgLMAskCBQKrABP/p/3M/MT8m/0h//IAlgKaA7ADyQIaARD/Mv0D/Nv7zvyl/ucAAANdBJoEngOjASn/1PxG+/D68vsQ/sAAUgMTBYUFggREAl7/j/yY+gb6B/ti/X0AigO4BW4GcgX+ArD/ZPz7+R/5Evqd/BwApwNMBlMHbAbNAx4AVfxy+T74E/nD+6D/qAPLBi8IbgexBKkAYvz++Gb3D/jW+gj/jAM0BwIJdQinBU8Bjfyh+Jn2B/fX+VT+UwOEB8gJfgmvBhAC1fxd+Nr1/vXI+Ib9+wK7B38KhgrEB+sCPP00+Cz19/Ss95/8hgLWByULeQvKCMsDzv1k+Pr0dfT59tz71QFTB+UKmgtCCXwEif73+D/1W/SF9i77GgG9BpoKrguxCScFRP+R+Y/1TPQc9oX6XgAfBkQKtwsWCs4FAAAy+ur1SfS89eH5ov97BeQJtAtxCm8GvADZ+k/2UvRm9UP55v7SBHsJpQvBCgkHdwGE+772ZvQb9a34K/4kBAcJiwsGC5wHMgI1/Db3h/Tb9B34cv1yA4oIZQtACycI6gLp/Lf3s/Sn9Jb3vPy8AgUIMwtvC6oInwOg/UH46vR+9Bf3CPwDAngH9gqTCyUJUARa/tL4LfVg9KH2WftJAeMGrgqqC5YJ/QQV/2r5evVO9DX2r/qNAEcGWwq2C/0JpQXR/wn60/VI9NP1CfrR/6UF/Qm2C1sKRwaNAK/6NfZO9Hr1avkV//0ElgmqC64K4wZJAVn7ofZg9C310vha/lAEJQmTC/YKeAcDAgj8F/d+9Or0Qfig/Z8DqghvCzMLBQi8Arz8lven9LP0t/fp/OoCJwhAC2ULighyA3L9Hfjb9If0Nvc1/DICnAcGC4sLBwkkBCv+rfgb9Wb0vvaE+3cBCQfBCqULewnSBOb+Q/lm9VL0T/bZ+rwAbwZxCrQL5Al7BaL/4fm89Un06vUy+gAAzgUWCrcLRAofBl4Ahfoc9kz0j/WR+UT/JwWxCa4Lmgq9BhoBLvuF9lv0P/X3+In+fARCCZoL5QpTB9UB3Pv59nX0+vRk+M79ywPKCHkLJQvjB44Cjvx295v0wPTZ9xb9FwNJCE0LWQtqCEQDRP379830kfRW92H8YAK/BxYLggvpCPgD/f2I+Ar1bfTb9rD7pgEuB9MKoAtfCacEt/4d+VL1VvRq9gP76wCWBoYKsgvLCVEFc/+5+aX1SvQD9lv6LwD3BS0KuAstCvcFLwBb+gP2SvSl9bn5c/9RBcsJsguGCpYG6wAD+2r2VvRS9R35t/6nBF8JoAvTCi4HpgGw+9v2bfQK9Yj4/f34A+kIggsWC78HYAJh/Fb3kfTN9Pv3RP1EA2oIWQtNC0kIFwMW/dn3wPSb9Hb3jvyOAuMHJQt5C8oIywPO/WT4+vR19Pn23PvVAVMH5QqaC0IJfASJ/vf4P/Vb9IX2LvsaAb0GmgquC7EJJwVE/5H5j/VM9Bz2hfpeAB8GRAq3CxYKzgUAADL66vVJ9Lz14fmi/3sF5Am0C3EKbwa8ANn6T/ZS9Gb1Q/nm/tIEewmlC8EKCQd3AYT7vvZm9Bv1rfgr/iQEBwmLCwYLnAcyAjX8NveH9Nv0Hfhy/XIDighlC0ALJwjqAun8t/ez9Kf0lve8/LwCBQgzC28LqgifA6D9Qfjq9H70F/cI/AMCeAf2CpMLJQlQBFr+0vgt9WD0ofZZ+0kB4wauCqoLlgn9BBX/avl69U70Nfav+o0ARwZbCrYL/QmlBdH/CfrT9Uj00/UJ+tH/pQX9CbYLWwpHBo0Ar/o19k70evVq+RX//QSWCaoLrgrjBkkBWfuh9mD0LfXS+Fr+UAQlCZML9gp4BwMCCPwX93706vRB+KD9nwOqCG8LMwsFCLwCvPyW96f0s/S39+n86gInCEALZQuKCHIDcv0d+Nv0h/Q29zX8MgKcBwYLiwsHCSQEK/6t+Bv1ZvS+9oT7dwEJB8EKpQt7CdIE5v5D+Wb1UvRP9tn6vABvBnEKtAvkCXsFov/h+bz1SfTq9TL6AADOBRYKtwtECh8GXgCF+hz2TPSP9ZH5RP8nBbEJrguaCr0GGgEu+4X2W/Q/9ff4if58BEIJmgvlClMH1QHc+/n2dfT69GT4zv3LA8oIeQslC+MHjgKO/Hb3m/TA9Nn3Fv0XA0kITQtZC2oIRANE/fv3zfSR9Fb3YfxgAr8HFguCC+kI+AP9/Yj4CvVt9Nv2sPumAS4H0wqgC18JpwS3/h35UvVW9Gr2A/vrAJYGhgqyC8sJUQVz/7n5pfVK9AP2W/ovAPcFLQq4Cy0K9wUvAFv6A/ZK9KX1uflz/1EFywmyC4YKlgbrAAP7avZW9FL1Hfm3/qcEXwmgC9MKLgemAbD72/Zt9Ar1iPj9/fgD6QiCCxYLvwdgAmH8VveR9M30+/dE/UQDaghZC00LSQgXAxb92ffA9Jv0dveO/I4C4wclC3kLygjLA879ZPj69HX0+fbc+9UBUwflCpoLQgl8BIn+9/g/9Vv0hfYu+xoBvQaaCq4LsQknBUT/kfmP9Uz0HPaF+l4AHwZECrcLFgrOBQAAMvrq9Un0vPXh+aL/ewXkCbQLcQpvBrwA2fpP9lL0ZvVD+eb+0gR7CaULwQoJB3cBhPu+9mb0G/Wt+Cv+JAQHCYsLBgucBzICNfw294f02/Qd+HL9cgOKCGULQAsnCOoC6fy397P0p/SW97z8vAIFCDMLbwuqCJ8DoP1B+Or0fvQX9wj8AwJ4B/YKkwslCVAEWv7S+C31YPSh9ln7SQHjBq4KqguWCf0EFf9q+Xr1TvQ19q/6jQBHBlsKtgv9CaUF0f8J+tP1SPTT9Qn60f+lBf0JtgtbCkcGjQCv+jX2TvR69Wr5Ff/9BJYJqguuCuMGSQFZ+6H2YPQt9dL4Wv5QBCUJkwv2CngHAwII/Bf3fvTq9EH4oP2fA6oIbwszCwUIvAK8/Jb3p/Sz9Lf36fzqAicIQAtlC4oIcgNy/R342/SH9Db3NfwyApwHBguLCwcJJAQr/q34G/Vm9L72hPt3AQkHwQqlC3sJ0gTm/kP5ZvVS9E/22fq8AG8GcQq0C+QJewWi/+H5vPVJ9Or1MvoAAM4FFgq3C0QKHwZeAIX6HPZM9I/1kflE/ycFsQmuC5oKvQYaAS77hfZb9D/19/iJ/nwEQgmaC+UKUwfVAdz7+fZ19Pr0ZPjO/csDygh5CyUL4weOAo78dveb9MD02fcW/RcDSQhNC1kLaghEA0T9+/fN9JH0Vvdh/GACvwcWC4IL6Qj4A/39iPgK9W302/aw+6YBLgfTCqALXwmnBLf+HflS9Vb0avYD++sAlgaGCrILywlRBXP/ufml9Ur0A/Zb+i8A9wUtCrgLLQr3BS8AW/oD9kr0pfW5+XP/UQXLCbILhgqWBusAA/tq9lb0UvUd+bf+pwRfCaAL0wouB6YBsPvb9m30CvWI+P39+APpCIILFgu/B2ACYfxW95H0zfT790T9RANqCFkLTQtJCBcDFv3Z98D0m/R29478jgLjByULeQvKCMsDzv1k+Pr0dfT59tz71QFTB+UKmgtCCXwEif73+D/1W/SF9i77GgG9BpoKrguxCScFRP+R+Y/1TPQc9oX6XgAfBkQKtwsWCs4FAAAy+ur1SfS89eH5ov97BeQJtAtxCm8GvADZ+k/2UvRm9UP55v7SBHsJpQvBCgkHdwGE+772ZvQb9a34K/4kBAcJiwsGC5wHMgI1/Db3h/Tb9B34cv1yA4oIZQtACycI6gLp/Lf3s/Sn9Jb3vPy8AgUIMwtvC6oInwOg/UH46vR+9Bf3CPwDAngH9gqTCyUJUARa/tL4LfVg9KH2WftJAeMGrgqqC5YJ/QQV/2r5evVO9DX2r/qNAEcGWwq2C/0JpQXR/wn60/VI9NP1CfrR/6UF/Qm2C1sKRwaNAK/6NfZO9Hr1avkV//0ElgmqC64K4wZJAVn7ofZg9C310vha/lAEJQmTC/YKeAcDAgj8F/d+9Or0Qfig/Z8DqghvCzMLBQi8Arz8lven9LP0t/fp/OoCJwhAC2ULighyA3L9Hfjb9If0Nvc1/DICnAcGC4sLBwkkBCv+rfgb9Wb0vvaE+3cBCQfBCqULewnSBOb+Q/lm9VL0T/bZ+rwAbwZxCrQL5Al7BaL/4fm89Un06vUy+gAAzgUWCrcLRAofBl4Ahfoc9kz0j/WR+UT/JwWxCa4Lmgq9BhoBLvuF9lv0P/X3+In+fARCCZoL5QpTB9UB3Pv59nX0+vRk+M79ywPKCHkLJQvjB44Cjvx295v0wPTZ9xb9FwNJCE0LWQtqCEQDRP379830kfRW92H8YAK/BxYLggvpCPgD/f2I+Ar1bfTb9rD7pgEuB9MKoAtfCacEt/4d+VL1VvRq9gP76wCWBoYKsgvLCVEFc/+5+aX1SvQD9lv6LwD3BS0KuAstCvcFLwBb+gP2SvSl9bn5c/9RBcsJsguGCpYG6wAD+2r2VvRS9R35t/6nBF8JoAvTCi4HpgGw+9v2bfQK9Yj4/f34A+kIggsWC78HYAJh/Fb3kfTN9Pv3RP1EA2oIWQtNC0kIFwMW/dn3wPSb9Hb3jvyOAuMHJQt5C8oIywPO/WT4+vR19Pn23PvVAVMH5QqaC0IJfASJ/vf4P/Vb9IX2LvsaAb0GmgquC7EJJwVE/5H5j/VM9Bz2hfpeAB8GRAq3CxYKzgUAADL66vVJ9Lz14fmi/3sF5Am0C3EKbwa8ANn6T/ZS9Gb1Q/nm/tIEewmlC8EKCQd3AYT7vvZm9Bv1rfgr/iQEBwmLCwYLnAcyAjX8NveH9Nv0Hfhy/XIDighlC0ALJwjqAun8t/ez9Kf0lve8/LwCBQgzC28LqgifA6D9Qfjq9H70F/cI/AMCeAf2CpMLJQlQBFr+0vgt9WD0ofZZ+0kB4wauCqoLlgn9BBX/avl69U70Nfav+o0ARwZbCrYL/QmlBdH/CfrT9Uj00/UJ+tH/pQX9CbYLWwpHBo0Ar/o19k70evVq+RX//QSWCaoLrgrjBkkBWfuh9mD0LfXS+Fr+UAQlCZML9gp4BwMCCPwX93706vRB+KD9nwOqCG8LMwsFCLwCvPyW96f0s/S39+n86gInCEALZQuKCHIDcv0d+Nv0h/Q29zX8MgKcBwYLiwsHCSQEK/6t+Bv1ZvS+9oT7dwEJB8EKpQt7CdIE5v5D+Wb1UvRP9tn6vABvBnEKtAvkCXsFov/h+bz1SfTq9TL6AADOBRYKtwtECh8GXgCF+hz2TPSP9ZH5RP8nBbEJrguaCr0GGgEu+4X2W/Q/9ff4if58BEIJmgvlClMH1QHc+/n2dfT69GT4zv3LA8oIeQslC+MHjgKO/Hb3m/TA9Nn3Fv0XA0kITQtZC2oIRANE/fv3zfSR9Fb3YfxgAr8HFguCC+kI+AP9/Yj4CvVt9Nv2sPumAS4H0wqgC18JpwS3/h35UvVW9Gr2A/vrAJYGhgqyC8sJUQVz/7n5pfVK9AP2W/ovAPcFLQq4Cy0K9wUvAFv6A/ZK9KX1uflz/1EFywmyC4YKlgbrAAP7avZW9FL1Hfm3/qcEXwmgC9MKLgemAbD72/Zt9Ar1iPj9/fgD6QiCCxYLvwdgAmH8VveR9M30+/dE/UQDaghZC00LSQgXAxb92ffA9Jv0dveO/I4C4wclC3kLygjLA879ZPj69HX0+fbc+9UBUwflCpoLQgl8BIn+9/g/9Vv0hfYu+xoBvQaaCq4LsQknBUT/kfmP9Uz0HPaF+l4AHwZECrcLFgrOBQAAMvrq9Un0vPXh+aL/ewXkCbQLcQpvBrwA2fpP9lL0ZvVD+eb+0gR7CaULwQoJB3cBhPu+9mb0G/Wt+Cv+JAQHCYsLBgucBzICNfw294f02/Qq+Hr9YQNUCAkL1ArMB8QCFf08+Hr1gfVF+AX9egI4BwIKJgqjBysD8P1R+YL2OPZ8+K38rAEpBvkIZwlfB3MDsf5Z+ov3/vbM+HT8+AAqBfEHmggCB54DV/9P+5L40fc1+Vj8YAA9BO0GwgeOBqsD4v8z/JT5rfi0+Vn85P9jA+4F4QYFBpwDUAAC/Y76kvlI+nb8g/+eAvkE+gVoBXEDogC8/X77e/rt+q78QP/wAQ4EEAW6BCwD1wBd/mL8Zvuj+wD9Gf9bATIDJQT9A84C8ADm/jf9UPxm/Gr9Dv/fAGUCPAM0A1kC7QBV//v9N/00/er9IP9+AKoBVwJhAs4BzQCp/63+GP4L/n/+Tf84AAIBegGHAS8BkgDh/0n/8f7o/if/lf8OAHEApwCoAH4APQD9/9D/v//I/+D/9/8=';
var MSG_MAX = 30;                /* 每条消息字符上限（微信式短消息） */
var MSG_MAX_VOICE = 12;          /* 单回合最多为前 N 条消息合成语音，其余纯文字（失控超长回复保护） */
var uiPrefsKey = storageKey + '_ui';
var showVoiceText = true;        /* 语音条下方显示文字（默认开） */
var replayingBar = null;         /* 正在回放的语音条元素 */
var replayAudio = null;          /* 回放降级路径（无 iframe player）用的 Audio 实例，便于停止 */
var TTS_FETCH_TIMEOUT_MS = 30000; /* 单条 /tts 请求超时，超时按 'failed' 转文字继续 */
var nativeEpoch = 0;
var voiceBars = [];              /* 本页全部语音入口；离开页面时统一释放 URL */
var activePlay = null;          /* 当前原生播放器的自动播放回合 */
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
var faceReady = false;
var contextLoaded = false;
var contextLoading = null;
var sendGeneration = 0;
var sendPending = false;
var inputRevision = 0;
var lastInputValue = '';
function trackDraftInput() {
  if (inputText.value !== lastInputValue) {
    lastInputValue = inputText.value;
    inputRevision++;
  }
  autoGrow();
}
var cancelActiveSend = null;
var audioUnlocked = false;
var SILENT_WAV = 'data:audio/wav;base64,UklGRmQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YUAAAACAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA';
var emotionsCfg = null;
var lastEmotion = null;
var emotionTimer = null;
var emotionImg = null;
var VIEWER = '__VIEWER__';
var EXPECTED_SCOPE = __EXPECTED_SCOPE__;
var scopeError = false;
// Consent and archive readiness live only for this document lifetime.
var introAccepted = typeof document === 'undefined' || !document.getElementById('intro-card');
var dataReadyPromise = null, dataReadyPhase = 'idle', dataProgress = Object.create(null), dataProgressListeners = [];
var knowledgePieces = Object.create(null);
function dataProgressSnapshot() {
  var entries = Object.keys(dataProgress).map(function(k) { return dataProgress[k]; });
  return {phase:dataReadyPhase, total:entries.length,
    downloaded:entries.filter(function(e) { return e.downloaded; }).length,
    verified:entries.filter(function(e) { return e.verified; }).length,
    active:entries.filter(function(e) { return e.state === 'downloading' || e.state === 'checking'; }).map(function(e) { return e.resource; }),
    failed:Object.keys(dataFailures)};
}
function reportDataProgress(resource, state) {
  if (resource) {
    var item = dataProgress[resource] || (dataProgress[resource] = {resource:resource,downloaded:false,verified:false});
    item.state = state;
    if (state === 'downloading') { item.downloaded = false; item.verified = false; }
    if (state === 'checking') item.downloaded = true;
    if (state === 'verified') { item.downloaded = true; item.verified = true; }
  }
  var snapshot = dataProgressSnapshot();
  dataProgressListeners.slice().forEach(function(fn) { fn(snapshot); });
}
function subscribeDataProgress(fn) {
  dataProgressListeners.push(fn); fn(dataProgressSnapshot());
  return function() { var i = dataProgressListeners.indexOf(fn); if (i >= 0) dataProgressListeners.splice(i, 1); };
}
function dataProgressText(p) {
  var counts = '已下载 ' + p.downloaded + '/' + p.total + ' 个文件，已校验 ' + p.verified + '/' + p.total + ' 个文件。';
  if (p.phase === 'ready') return '资料已准备好，可以开始聊天。' + counts;
  if (p.phase === 'failed') return (dataBlocked ? '资料传输未结束，请稍后重试；若一直没有结束，请重新打开本页。' : '资料暂时未能完整准备，请重试。') + counts + dataDiagnostic();
  return '正在下载并校验资料。' + counts + ' 可以先进入聊天，发送前仍需等待准备完成。';
}
function boundedWait(promise, milliseconds) {
  return new Promise(function(resolve, reject) {
    var timer = setTimeout(function() { reject(new Error('WAIT_TIMEOUT')); }, milliseconds);
    Promise.resolve(promise).then(function(value) { clearTimeout(timer); resolve(value); },
      function(error) { clearTimeout(timer); reject(error); });
  });
}
// Local-only, bounded diagnostic labels; never include response/error text or URLs.
var dataFailures = Object.create(null);
function dataFailure(resource, code) {
  if (!dataFailures[resource]) dataFailures[resource] = code;
  reportDataProgress(resource, 'failed');
}
function dataError(resource, code) {
  dataFailure(resource, code);
  var error = new Error('data validation failed'); error.dataCode = code; return error;
}
function dataDiagnostic() {
  var names = Object.keys(dataFailures).sort();
  var first = names.length ? names[0] + ':' + dataFailures[names[0]] : 'DATA:INCOMPLETE';
  return ' [D20261026-1 ' + first + '; failed=' + names.length + ']';
}
// A slot covers headers AND body; waiting in this queue consumes no deadline.
var dataQueue = [], dataActive = 0, dataBlocked = 0, dataRequests = Object.create(null);
var dataArchiveEpoch = 0, dataArchiveControllers = new Set();
function invalidateDataArchive() {
  dataArchiveEpoch++;
  dataArchiveControllers.forEach(function(ctrl) { try { ctrl.abort(); } catch (_) {} });
}
function drainDataQueue() {
  while (!dataBlocked && dataActive < 4 && dataQueue.length) { dataActive++; dataQueue.shift()(); }
}
function fetchDataJson(url, resource, rawBytes) {
  if (dataRequests[url]) return dataRequests[url];
  if (dataBlocked) return Promise.reject(dataError(resource, "TRANSPORT_BLOCKED"));
  var job, archiveEpoch = rawBytes ? dataArchiveEpoch : 0;
  var result = new Promise(function(resolve, reject) {
    job = function() {
      delete dataFailures[resource];
      reportDataProgress(resource, 'downloading');
      var ctrl = typeof AbortController !== 'undefined' ? new AbortController() : null;
      if (rawBytes && ctrl) dataArchiveControllers.add(ctrl);
      var phase = 'FETCH', expired = false;
      function failure(code) { var error = new Error('data unavailable'); error.dataCode = code; return error; }
      var timer = setTimeout(function() {
        expired = true;
        dataBlocked++;
        while (dataQueue.length) dataQueue.shift().cancel();
        reject(dataError(resource, phase + '_TIMEOUT'));
        if (ctrl) { try { ctrl.abort(); } catch (_) {} }
      }, 15000);
      Promise.resolve().then(function() {
        if (rawBytes && archiveEpoch !== dataArchiveEpoch) throw new Error('ARCHIVE_INVALIDATED');
        return fetch(url, {cache: rawBytes ? 'no-store' : 'no-cache', credentials: 'same-origin', redirect: rawBytes ? 'error' : 'follow', signal: ctrl ? ctrl.signal : undefined});
      }).then(function(r) {
        phase = 'BODY';
        if (!r.ok) {
          var httpError = failure('HTTP_' + (Number.isInteger(r.status) && r.status >= 100 && r.status <= 599 ? r.status : 'OTHER'));
          // Consume the error body before releasing its transport slot. A hung
          // body uses the same deadline and blocked-transport recovery path.
          return r.text().then(function() { throw httpError; }, function() { throw httpError; });
        }
        if (rawBytes) {
          if (r.redirected) throw failure('REDIRECT');
          return r.arrayBuffer();
        }
        return r.json().catch(function() {
          var type = (r.headers.get('content-type') || '').split(';')[0].trim().toLowerCase();
          var nonJson = type && type !== 'application/json' && !/\+json$/.test(type);
          throw failure(r.redirected ? (nonJson ? 'REDIRECT_NON_JSON' : 'REDIRECT_JSON') : (nonJson ? 'NON_JSON' : 'JSON'));
        });
      }).then(function(data) { if (!expired) {
        if (rawBytes && archiveEpoch !== dataArchiveEpoch) { reject(new Error('ARCHIVE_INVALIDATED')); return; }
        reportDataProgress(resource, 'checking'); resolve(data);
      } }, function(error) {
        if (expired) return;
        if (rawBytes && archiveEpoch !== dataArchiveEpoch) { reject(new Error('ARCHIVE_INVALIDATED')); return; }
        var code = error && error.dataCode || (phase === 'FETCH' ? 'NETWORK' : 'JSON');
        reject(dataError(resource, code));
      }).then(function() {
        clearTimeout(timer);
        if (rawBytes && ctrl) dataArchiveControllers.delete(ctrl);
        if (expired) dataBlocked--;
        delete dataRequests[url];
        dataActive--; drainDataQueue();
      });
      // Without AbortController, retain the slot and dedup entry until transport
      // settles. A timed-out response cannot mutate callers or overlap a retry.
    };
    job.cancel = function() {
      delete dataRequests[url];
      reject(dataError(resource, 'TRANSPORT_BLOCKED'));
    };
  });
  reportDataProgress(resource, 'queued');
  dataRequests[url] = result;
  if (resource === 'MEMORY' || resource === 'TRANSCRIPTS') dataQueue.unshift(job);
  else dataQueue.push(job);
  drainDataQueue();
  return result;
}
function checkScope(data, kind) {
  if (!EXPECTED_SCOPE) return;
  function reject() { scopeError = true; throw new Error('关系资料范围不一致，请联系建档人'); }
  if (!data || data.person !== EXPECTED_SCOPE.person || data.relationship_id !== EXPECTED_SCOPE.relationship_id) reject();
  if (kind === 'context' && (data.viewer !== VIEWER || data.coverage_status !== 'partial' ||
      data.language !== 'mandarin' || !data.system_prompt || !Array.isArray(data.message_shards) ||
      !data.message_shards.length || data.message_shards.some(function(n) { return !/^messages-\d{4}\.json$/.test(n); }))) reject();
  var binding = EXPECTED_SCOPE.memory_release;
  if (binding && (typeof binding.release_revision !== 'string' || !/^[0-9a-f]{64}$/.test(binding.release_revision))) reject();
  if (kind === 'context' && JSON.stringify(data.memory_release || null) !== JSON.stringify(binding || null)) {
    dataFailure('CONTEXT', 'BINDING'); reject();
  }
  if (kind === 'memory' && binding) {
    var a = data.authorization || {}, p = data.provenance || {};
    if (data.tier !== 2 || data.release_id !== binding.release_id ||
        !Object.prototype.hasOwnProperty.call(binding.card_revisions, data.id) || data.evidence_revision !== binding.card_revisions[data.id] ||
        a.mode !== 'batch_adoption' || a.individual_human_confirmed !== false || a.acoustic_listened !== false ||
        p.source_kind !== 'original_text' || p.source_sha256 !== binding.source_sha256 ||
        !Array.isArray(p.sources) || !p.sources.length || p.sources.some(function(r){return !r.record_id || !r.timestamp || !r.text_sha256 || (r.speaker_id !== VIEWER && r.speaker_id !== EXPECTED_SCOPE.person);}) ||
        !Array.isArray(data.texts) || data.texts.length !== 1 || typeof data.texts[0] !== 'string' || !data.texts[0].trim() || Array.from(data.texts[0]).length > 900) reject();
  }
  if (kind === 'message' && (typeof data.record_id !== 'string' || !data.record_id.trim() ||
      !data.provenance || typeof data.provenance.source_record_id !== 'string' ||
      !data.provenance.source_record_id.trim())) reject();
  if (kind === 'message' && (data.viewpoint !== VIEWER || data.conversation_kind !== 'direct' ||
      data.content_type !== 'text' || data.tier !== 2 || !data.provenance ||
      data.provenance.source_record_id !== data.record_id ||
      (data.sender_person_id !== EXPECTED_SCOPE.person && data.sender_person_id !== VIEWER) ||
      data.sender !== (data.sender_person_id === EXPECTED_SCOPE.person ? 'subject' : 'viewpoint_owner') ||
      !Array.isArray(data.participant_ids) || data.participant_ids.length !== 2 ||
      data.participant_ids.indexOf(EXPECTED_SCOPE.person) < 0 || data.participant_ids.indexOf(VIEWER) < 0)) reject();
}
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

function logSession(rec, requestSettings) {
  var logSettings = requestSettings || settings;
  var record = {
    session_id: sessionId,
    turn: (typeof rec.turn === 'number') ? rec.turn : sessionTurn,
    role: rec.role,
    text: String(rec.text || ''),
    ts: isoLocal(new Date()),
    provider: logSettings.provider || '',
    model: logSettings.model || '',
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
  sendGeneration++;
  cancelVoiceTurn();
  sendPending = false;
  if (cancelActiveSend) { cancelActiveSend(); cancelActiveSend = null; }
  if (controller) { controller.abort(); controller = null; }
  streaming = false;
  sendBtn.classList.remove('stop');
  sendBtn.textContent = '发送';
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
  if (streaming) return;
  if (!contextLoaded) { sendBtn.disabled = !settingsComplete(); return; }
  maybeReplayHistory();                                    /* 历史先回放：它不依赖接口配置 */
  if (!settingsComplete()) { confNoticeKeepHistory(); return; }
  removeStartPlaceholder();                                /* 配置齐了：清掉可能残留的居中占位提示 */
  if (chat.children.length === 0) { addBubble({type:'center', text:'开始对话吧...'}); }
  sendBtn.disabled = false; sendBtn.textContent = '发送'; streaming = false;
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
function voiceScopeCurrent(vt) {
  return vt.generation === sendGeneration && vt.profile === JSON.stringify(settings) && vt.scope === JSON.stringify(EXPECTED_SCOPE);
}
function voiceError(bar, code) {
  var safe = /^(AUDIO_HTTP(?:_[1-5][0-9]{2})?|AUDIO_MIME|AUDIO_SIGNATURE|AUDIO_FETCH|AUDIO_BODY|AUDIO_PLAY_(?:NotAllowedError|NotSupportedError|AbortError|OTHER|PENDING)|AUDIO_MEDIA_[1-4])$/.test(code) ? code : 'AUDIO_FETCH';
  bar._historyStatus.textContent = '语音暂未能播放，请点重试或下方播放控件。 [D4 ' + safe + ']';
  bar._historyRetry.hidden = false;
}
function fetchVoiceBlob(url, options, timeout) {
  var ctrl = typeof AbortController !== 'undefined' ? new AbortController() : null;
  options.signal = ctrl ? ctrl.signal : undefined;
  var phase = 'AUDIO_FETCH';
  return boundedWait(Promise.resolve().then(function() { return fetch(url, options); }).then(function(r) {
    if (!r.ok) { var e = new Error(); e.code = 'AUDIO_HTTP' + (/^[1-5][0-9]{2}$/.test(String(r.status)) ? '_' + r.status : ''); throw e; }
    var mime = String(r.headers.get('Content-Type') || '').split(';')[0].trim().toLowerCase();
    if (!/^(audio\/mpeg|audio\/mp3|audio\/wav|audio\/x-wav|audio\/wave)$/.test(mime)) {
      var e = new Error(); e.code = 'AUDIO_MIME'; throw e;
    }
    phase = 'AUDIO_BODY';
    var dur = parseFloat(r.headers.get('X-Duration-Seconds'));
    return r.blob().then(function(blob) {
      var head = blob.slice(0, 12);
      var bytes = head.arrayBuffer ? head.arrayBuffer() : new Promise(function(resolve, reject) {
        var reader = new FileReader(); reader.onload = function() { resolve(reader.result); }; reader.onerror = reject; reader.readAsArrayBuffer(head);
      });
      return bytes.then(function(buffer) {
        var b = new Uint8Array(buffer);
        var wav = b.length >= 12 && b[0] === 82 && b[1] === 73 && b[2] === 70 && b[3] === 70 && b[8] === 87 && b[9] === 65 && b[10] === 86 && b[11] === 69;
        var mp3 = b.length >= 3 && ((b[0] === 73 && b[1] === 68 && b[2] === 51) || (b[0] === 255 && (b[1] & 224) === 224 && (b[1] & 6) !== 0 && (b[2] & 240) !== 0 && (b[2] & 240) !== 240));
        if (!(mime === 'audio/mpeg' || mime === 'audio/mp3' ? mp3 : wav)) { var e = new Error(); e.code = 'AUDIO_SIGNATURE'; throw e; }
        return {blob:blob, dur:isFinite(dur) && dur > 0 ? dur : null};
      });
    });
  }), timeout).catch(function(error) {
    if (ctrl) ctrl.abort();
    var safe = new Error(); safe.code = error.code || phase; throw safe;
  });
}
function armNativeDeadline(bar) {
  if (bar._historyTimer) clearTimeout(bar._historyTimer);
  var attempt = (bar._historyAttempt || 0) + 1;
  bar._historyAttempt = attempt;
  bar._historyTimer = setTimeout(function() {
    if (bar._historyAttempt !== attempt || replayAudio !== bar._historyAudio) return;
    stopReplay(); voiceError(bar, 'AUDIO_PLAY_PENDING');
  }, 10000);
  return attempt;
}
function initAutoVoiceSession() {
  if (typeof AUTO_VOICE_SESSION === 'undefined' || !AUTO_VOICE_SESSION) return null;
  if (typeof autoVoiceSession !== 'undefined' && autoVoiceSession) return autoVoiceSession;
  var audio = document.createElement('audio'); audio.id = 'auto-voice-player'; audio.preload = 'auto';
  var button = document.createElement('button'); button.id = 'auto-voice-activate'; button.type = 'button';
  var status = document.createElement('span'); status.id = 'auto-voice-status'; status.setAttribute('role', 'status');
  var checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.id = 'cfg-auto-voice';
  var label = document.createElement('label'); label.className = 'cfg-check'; label.appendChild(checkbox);
  label.appendChild(document.createTextNode(' 自动朗读新回复'));
  var box = document.createElement('div'); box.id = 'auto-voice-settings';
  box.appendChild(label); box.appendChild(button); box.appendChild(status);
  box.style.cssText = 'margin:12px 0;font-size:12px';
  status.style.cssText = 'display:block;margin-top:6px;color:#aab7d0;line-height:1.5';
  var drawerHost = document.getElementById('drawer');
  drawerHost.insertBefore(box, drawerHost.firstChild);
  document.body.appendChild(audio);
  var saved = readUiPrefs();
  var session = autoVoiceSession = {audio:audio, button:button, checkbox:checkbox, box:box, status:status, job:null,
    enabled:typeof saved.autoVoiceEnabled === 'boolean' ? saved.autoVoiceEnabled : true, ready:false, suspended:false};
  checkbox.checked = session.enabled;
  status.textContent = session.enabled ? '已选择自动朗读，尚未启用播放；发送时会尝试提示音，受限时可逐条手动播放。' : '已关闭自动朗读，可逐条手动播放。';
  checkbox.addEventListener('change', function() {
    session.enabled = !!checkbox.checked;
    saveUiPrefs();
    if (!session.enabled) {
      session.turnDisabled = true;
      if (voiceTurn) voiceTurn.autoStopped = true;
      if (session.job) stopReplay();
      session.ready = false;
    }
    status.textContent = session.enabled ? '已开启，从下次发送的新回复生效；也可逐条手动播放。' : '已关闭自动朗读，可逐条手动播放。';
  });
  // Queued events have no source token: they may only stop an unowned player.
  // Never use an old event/promise to pause the same element's valid new job.
  session.guard = function() {
    var job = session.job;
    if (job && replayAudio === audio && !document.hidden && job.profile === JSON.stringify(settings) && job.scope === JSON.stringify(EXPECTED_SCOPE) && job.generation === sendGeneration &&
        (!job.bar || !job.bar._voiceTurn || voiceScopeCurrent(job.bar._voiceTurn))) return;
    if (replayAudio === audio) stopReplay();
    else audio.pause();
  };
  audio.addEventListener('play', session.guard);
  audio.addEventListener('playing', session.guard);
  button.textContent = '测试提示音 / 重试朗读';
  button.addEventListener('click', maybeActivateAutoVoice);
  return session;
}
function maybeActivateAutoVoice(event) {
  if (!event || event.isTrusted !== true) return;
  var s = initAutoVoiceSession();
  if (!s || !s.enabled || s.ready || s.job || document.hidden || replayAudio) return;
  s.suspended = false; s.lastError = null;
  startAutoVoiceJob(null, null, true);
}
function showAutoVoiceFailure(bar) {
  var s = typeof autoVoiceSession !== 'undefined' ? autoVoiceSession : null;
  var e = s && s.lastError, vt = bar && bar._voiceTurn;
  if (!e || !s.enabled || s.ready || !vt || vt !== voiceTurn || vt.canceled || vt.autoStopped || !bar._voiceBlob ||
      e.generation !== sendGeneration || e.profile !== JSON.stringify(settings) || e.scope !== JSON.stringify(EXPECTED_SCOPE) || !voiceScopeCurrent(vt)) return;
  bar._historyStatus.textContent = '自动播放受限，请用下方播放控件。 [' + e.code + ']';
}
function readUiPrefs() {
  try {
    var saved = JSON.parse(localStorage.getItem(uiPrefsKey) || 'null');
    return saved && typeof saved === 'object' && !Array.isArray(saved) ? saved : {};
  } catch (_) { return {}; }
}
function saveUiPrefs() {
  var saved = typeof AUTO_VOICE_SESSION !== 'undefined' && AUTO_VOICE_SESSION ? readUiPrefs() : {};
  saved.voiceText = showVoiceText;
  if (typeof AUTO_VOICE_SESSION !== 'undefined' && AUTO_VOICE_SESSION && autoVoiceSession) saved.autoVoiceEnabled = autoVoiceSession.enabled;
  try { localStorage.setItem(uiPrefsKey, JSON.stringify(saved)); } catch (_) {}
}
function stopAutoVoiceJob() {
  if (typeof autoVoiceSession === 'undefined' || !autoVoiceSession || !autoVoiceSession.job) return;
  var s = autoVoiceSession, j = s.job; s.job = null;
  clearTimeout(j.timer); s.audio.pause();
  if (j.cue) { s.ready = false; s.status.textContent = '提示音已取消，请重新开启自动朗读'; }
}
function startAutoVoiceJob(bar, turn, cue) {
  var s = initAutoVoiceSession();
  if (!s || !s.enabled || document.hidden || (!cue && (!s.ready || s.suspended || (s.job && s.job.cue)))) return;
  stopReplay();
  var a = s.audio;
  var source = cue ? AUTO_VOICE_CUE : bar._voiceObjectUrl;
  var j = {bar:bar, turn:turn, cue:cue, source:source, profile:JSON.stringify(settings), scope:JSON.stringify(EXPECTED_SCOPE), generation:sendGeneration, started:false, last:0, deadline:Date.now()+10000, began:Date.now(), hardDeadline:Date.now()+(cue ? 10000 : 600000), durationBound:false, timer:null};
  s.job = j; a.src = source; a.load();
  replayAudio = a; replayingBar = bar; activePlay = turn;
  if (turn) turn.playing = true;
  if (cue) { s.ready = false; s.status.textContent = '正在尝试播放提示音…'; }
  function current() {
    return s.job === j && replayAudio === a && !document.hidden && j.profile === JSON.stringify(settings) && j.scope === JSON.stringify(EXPECTED_SCOPE) && j.generation === sendGeneration && (!bar || !bar._voiceTurn || voiceScopeCurrent(bar._voiceTurn));
  }
  function fail(code) {
    if (!current()) return;
    stopReplay(false); s.ready = false;
    s.status.textContent = '自动播放暂不可用，下次发送会重试；请用每条语音的播放控件 ['+code+']';
    if (cue) {
      s.lastError = {code:code, generation:j.generation, profile:j.profile, scope:j.scope};
      if (voiceTurn) voiceTurn.bars.forEach(showAutoVoiceFailure);
    }
    if (bar) voiceError(bar, code);
  }
  // Media events carry no source identity. Observe current-source progress instead
  // of allowing queued play/pause/ended events from an old source to own a new job.
  function observe() {
    if (!current()) { if (s.job === j) stopReplay(); return; }
    if (a.currentSrc === source && a.currentTime > j.last && a.readyState >= 2) {
      j.started = true; s.ready = true; j.deadline = Date.now()+10000;
      s.status.textContent = '自动朗读已开启';
      if (bar) { bar.classList.add('playing'); bar._historyStatus.textContent = ''; bar._historyRetry.hidden = true; }
    }
    if (a.currentSrc === source) {
      j.last = a.currentTime;
      if (!j.durationBound && isFinite(a.duration) && a.duration > 0) {
        j.durationBound = true;
        j.hardDeadline = Math.min(j.hardDeadline, j.began + Math.max(30000, a.duration*2000+10000));
      }
    }
    if (a.currentSrc === source && a.error) { fail('AUDIO_MEDIA_'+a.error.code); return; }
    if (j.started && a.currentSrc === source && a.ended && isFinite(a.duration) && a.duration > 0 && a.currentTime >= a.duration-0.1) {
      s.job = null; replayAudio = null; replayingBar = null; activePlay = null;
      if (bar) bar.classList.remove('playing');
      if (turn && turn === voiceTurn && !turn.canceled && !turn.autoStopped && turn.bars[turn.playIdx] === bar) onSegmentEnded(turn);
      if (cue && voiceTurn) tryAdvance(voiceTurn);
      return;
    }
    if (Date.now() >= j.deadline || Date.now() >= j.hardDeadline) { fail('AUDIO_PLAY_PENDING'); return; }
    if (j.started && a.paused && !a.ended) { stopReplay(); return; }
    j.timer = setTimeout(observe, 50);
  }
  try { Promise.resolve(a.play()).then(function() { s.guard(); }).catch(function(e) { fail('AUDIO_PLAY_'+(/^(NotAllowedError|NotSupportedError|AbortError)$/.test(e && e.name) ? e.name : 'OTHER')); }); }
  catch(e) { fail('AUDIO_PLAY_OTHER'); }
  if (s.job === j) j.timer = setTimeout(observe, 50);
}

function ensureNativeAudio(bar) {
  if (bar._historyAudio || !bar._voiceBlob) return bar._historyAudio;
  var audio = document.createElement('audio');
  audio.controls = true; audio.preload = 'metadata';
  audio.style.cssText = 'display:block;width:100%;max-width:260px;margin-top:6px';
  bar._voiceObjectUrl = bar._voiceObjectUrl || URL.createObjectURL(bar._voiceBlob); audio.src = bar._voiceObjectUrl;
  var nativeSource = audio.src;
  var nativeProfile = JSON.stringify(settings), nativeScope = JSON.stringify(EXPECTED_SCOPE);
  function validNative() {
    return bar._historyAudio === audio && audio.src === nativeSource && !document.hidden &&
      nativeProfile === JSON.stringify(settings) && nativeScope === JSON.stringify(EXPECTED_SCOPE) &&
      (!bar._voiceTurn || voiceScopeCurrent(bar._voiceTurn));
  }
  bar._historyAudio = audio;
  audio.addEventListener('click', function(event) { event.stopPropagation(); });
  function gesture() { bar._controlGesture = Date.now(); bar._controlEpoch = nativeEpoch; }
  audio.addEventListener('pointerdown', gesture);
  audio.addEventListener('touchstart', gesture);
  audio.addEventListener('keydown', gesture);
  audio.addEventListener('play', function() {
    if (audio.paused) return; /* A queued play can arrive after pause/switch. */
    if (!validNative()) { audio.pause(); return; }
    if (replayAudio === audio) {
      /* Native pause/replay may precede its queued pause event. Re-arm for
         the new gesture even while the prior owner still names this audio. */
      if (!bar._historyTimer || (bar._controlGesture && bar._controlEpoch === nativeEpoch && Date.now() - bar._controlGesture <= 1500)) {
        if (voiceTurn) voiceTurn.autoStopped = true;
        activePlay = null; armNativeDeadline(bar);
      }
      bar._controlGesture = 0; return;
    }
    // UA controls may emit no DOM gesture. A fresh native instance has no
    // outstanding script play; retired managed instances fail validNative.
    if (audio._managedNative || (bar._controlGesture && (bar._controlEpoch !== nativeEpoch || Date.now() - bar._controlGesture > 1500))) { audio.pause(); return; }
    bar._controlGesture = 0;
    stopReplay();
    if (voiceTurn) voiceTurn.autoStopped = true;
    replayAudio = audio; replayingBar = bar;
    bar._historyStatus.textContent = ''; bar._historyRetry.hidden = true;
    armNativeDeadline(bar);
  });
  audio.addEventListener('playing', function() {
    if (!validNative() || replayAudio !== audio || audio.paused) { audio.pause(); return; }
    if (bar._historyTimer) { clearTimeout(bar._historyTimer); bar._historyTimer = null; }
    bar._historyAttempt = (bar._historyAttempt || 0) + 1;
    bar.classList.add('playing'); bar._historyStatus.textContent = ''; bar._historyRetry.hidden = true;
  });
  audio.addEventListener('pause', function() {
    if (bar._historyAudio !== audio || !audio.paused || audio.ended) return; /* Ignore retired/old events. */
    bar._historyAttempt = (bar._historyAttempt || 0) + 1;
    if (replayAudio === audio) stopReplay();
    bar.classList.remove('playing');
  });
  audio.addEventListener('ended', function() {
    if (!validNative() || replayAudio !== audio || !audio.ended || !isFinite(audio.duration) || audio.duration <= 0 || audio.currentTime < audio.duration - 0.1) return;
    audio._managedNative = false;
    var vt = activePlay;
    activePlay = null; replayAudio = null; replayingBar = null;
    if (bar._historyTimer) { clearTimeout(bar._historyTimer); bar._historyTimer = null; }
    bar._historyAttempt = (bar._historyAttempt || 0) + 1; bar.classList.remove('playing');
    if (vt && vt === voiceTurn && !vt.canceled && !vt.autoStopped && vt.bars[vt.playIdx] === bar) onSegmentEnded(vt);
  });
  audio.addEventListener('error', function() {
    if (!validNative()) return;
    var code = audio.error && audio.error.code;
    if (!/^[1-4]$/.test(String(code))) return;
    if (replayAudio === audio) stopReplay();
    voiceError(bar, 'AUDIO_MEDIA_' + code);
  });
  bar._historyPanel.appendChild(audio);
  return audio;
}
function playHistoryNative(bar, autoTurn) {
  if (!bar._voiceBlob || document.hidden) return;
  if (bar._voiceTurn && !voiceScopeCurrent(bar._voiceTurn)) return;
  var audio = ensureNativeAudio(bar);
  if (autoTurn && typeof AUTO_VOICE_SESSION !== 'undefined' && AUTO_VOICE_SESSION) { startAutoVoiceJob(bar, autoTurn, false); return; }
  if (replayAudio === audio && !audio.paused) { stopReplay(); return; }
  stopReplay();
  audio = ensureNativeAudio(bar);
  replayAudio = audio; replayingBar = bar; activePlay = autoTurn || null;
  if (autoTurn) { autoTurn.playing = true; }
  var attempt = armNativeDeadline(bar);
  bar._historyStatus.textContent = ''; bar._historyRetry.hidden = true;
  function failed(error) {
    if (bar._historyAttempt !== attempt || replayAudio !== audio) return;
    stopReplay(); voiceError(bar, error && error.code ? error.code : 'AUDIO_PLAY_PENDING');
  }
  function classified(error) {
    var name = error && error.name;
    var safe = new Error();
    safe.code = 'AUDIO_PLAY_' + (/^(NotAllowedError|NotSupportedError|AbortError)$/.test(name) ? name : 'OTHER');
    return safe;
  }
  audio._managedNative = true;
  try { Promise.resolve(audio.play()).catch(function(error) { failed(classified(error)); }); }
  catch (error) { failed(classified(error)); }
}
function suspendNativeVoice(release) {
  if (typeof autoVoiceSession !== 'undefined' && autoVoiceSession) { autoVoiceSession.suspended = true; autoVoiceSession.ready = false; autoVoiceSession.status.textContent = '页面已暂停；自动朗读开启时，下次发送会重试，也可逐条手动播放'; }
  if (voiceTurn) voiceTurn.autoStopped = true;
  stopReplay();
  for (var i = 0; i < voiceBars.length; i++) {
    var bar = voiceBars[i]; bar._controlGesture = 0;
    if (bar._historyAudio) bar._historyAudio.pause();
    if (release && bar._voiceObjectUrl) { URL.revokeObjectURL(bar._voiceObjectUrl); bar._voiceObjectUrl = null; }
  }
}
function wireHistoryBar(bar) {
  if (bar._historyPanel) return;
  var panel = document.createElement('div');
  panel.style.cssText = 'max-width:260px;width:100%';
  bar.parentNode.insertBefore(panel, bar.nextSibling);
  bar._historyPanel = panel;
  var status = document.createElement('span');
  status.style.cssText = 'display:block;font-size:12px;width:100%';
  panel.appendChild(status); bar._historyStatus = status;
  var retry = document.createElement('button');
  retry.className = 'voice-retry'; retry.type = 'button'; retry.textContent = '重试语音'; retry.hidden = true;
  panel.appendChild(retry); bar._historyRetry = retry;
  voiceBars.push(bar);
  function click() {
    if (bar._voiceLoading) return;
    if (voiceTurn) voiceTurn.autoStopped = true;
    if (bar._voiceBlob) { playHistoryNative(bar); return; }
    if (bar._voiceTurn) {
      synthMsg(bar._voiceTurn, bar._voiceIndex, true); return;
    }
    if (!bar._voiceUrl) return;
    stopReplay();
    var epoch = nativeEpoch, generation = sendGeneration;
    bar._voiceLoading = true; retry.hidden = true; status.textContent = '正在加载语音… · D4';
    fetchVoiceBlob(bar._voiceUrl, {}, 15000).then(function(result) {
      if (generation !== sendGeneration) return;
      bar._voiceBlob = result.blob; bar.classList.remove('expired'); status.textContent = '';
      ensureNativeAudio(bar);
      if (epoch === nativeEpoch && !document.hidden) playHistoryNative(bar);
    }).catch(function(error) {
      if (generation === sendGeneration) voiceError(bar, error.code || 'AUDIO_FETCH');
    }).then(function() { bar._voiceLoading = false; });
  }
  bar.addEventListener('click', click);
  bar.addEventListener('keydown', function(event) {
    if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); click(); }
  });
  retry.addEventListener('click', function(event) { event.stopPropagation(); click(); });
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
      if (typeof VOICE_GROUPS !== 'undefined' && VOICE_GROUPS) {
        rendered += renderGroupedHistory(g.sim.text, pool);
        continue;
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
        if (hit === -1) {
          if (typeof VOICE_GROUPS !== 'undefined' && VOICE_GROUPS) el.innerHTML = displayGroupHtml(segText);
          else el.textContent = segText;
          continue;
        }
        var au = pool[hit];
        pool.splice(hit, 1);             /* 每条音频只用一次 */
        var durNum = (typeof au.dur === 'number' && isFinite(au.dur) && au.dur > 0) ? au.dur : null;
        el.className = 'bubble-content voice';
        el.innerHTML = voiceBarHtml(segText, durNum);
        var bar = el.querySelector('.voice-bar');
        bar._voiceUrl = SESSIONS_BASE + au.file;
        bar._voiceBlob = null;
        bar._voiceLoading = false;
        wireHistoryBar(bar);             /* 与实时语音共用原生控件与播放归属 */
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
    results.push({ date: String(rec.timestamp || '').substring(0, 10), text: txt.length > 200 ? txt.substring(0, 200) : txt, score: score, record_id:rec.record_id, person:rec.person, speaker_id:rec.sender_person_id, viewpoint:rec.viewpoint, relationship_id:rec.relationship_id, tier:rec.tier, provenance:rec.provenance, evidence_revision:rec.evidence_revision });
  }
  results.sort(function(a, b) {
    if (b.score !== a.score) return b.score - a.score;
    return a.text.length - b.text.length;
  });
  return results.slice(0, top);
}
function retrieveKnowledge(tokens, memories, transcripts, opts) {
  opts = opts || {}; var memTop = opts.memTop || 3; var transTop = opts.transTop || 2;
  var mem = []; var i, e, score, txt; memories = memories || []; transcripts = transcripts || [];
  for (i = 0; i < memories.length; i++) {
    e = memories[i];
    if ((e.tier === 2 || e.release_id || e.authorization || (e.provenance && e.provenance.source_kind === 'original_text')) && !(typeof EXPECTED_SCOPE !== 'undefined' && EXPECTED_SCOPE && EXPECTED_SCOPE.memory_release)) continue;
    if (e.tier === 2 && !memorySourceDigests.has(e.id + ':' + e.evidence_revision)) continue;
    var title = String(e.title || '').trim();
    var texts = Array.isArray(e.texts) ? e.texts : [];
    var hay = title + '\n' + texts.join('\n');
    if (!hay.trim()) continue;
    score = scoreText(tokens, hay); if (score <= 0) continue;
    var body = String(texts[0] || '').trim();
    txt = title + (body ? ' — ' + body : '');
    if (e.tier !== 2 && txt.length > 240) txt = txt.substring(0, 240);
    mem.push({label: (e.tier === 2 ? '[来源派生记忆 Tier-2；批量采用，非逐条人审]' : '[家人确认记忆 Tier-1]') + (e.relationship_id ? ' [' + e.relationship_id + ']' : ''), date: String(e.date || ''), text: txt, score: score, record_id:e.id, person:e.person, tier:e.tier === 2 ? 2 : 1, relationship_id:e.relationship_id, evidence_revision:e.evidence_revision, provenance:e.provenance, evidence_records:e.evidence_records, release_id:e.release_id, full_sources_digest:e.tier === 2 ? memorySourceDigests.get(e.id + ':' + e.evidence_revision) : null});
  }
  mem.sort(function(a, b) { return b.score - a.score; }); mem = mem.slice(0, memTop);
  var trans = [];
  for (i = 0; i < transcripts.length; i++) {
    e = transcripts[i];
    if (e.schema_version === 2 && (e.speaker_status !== 'confirmed' || e.transcript_status !== 'corrected' || e.single_speaker !== true || !e.speaker_id || e.speaker_id === 'unknown' || e.source_kind !== 'real_recording')) continue;
    txt = String(e.text || '').trim(); if (!txt) continue;
    score = scoreText(tokens, txt); if (score <= 0) continue;
    if (txt.length > 200) txt = txt.substring(0, 200);
    var lbl = e.media === 'video' ? '[视频转写 Tier-2]' : '[语音转写 Tier-2]';
    if (e.schema_version === 2) lbl += ' [' + e.speaker_id + ' / ' + e.viewpoint + ' / ' + (e.relationship_id || '未标注关系') + ']';
    trans.push({label: lbl, date: String(e.date || ''), text: txt, score: score, record_id:e.record_id, person:e.person, tier:e.tier, speaker_id:e.speaker_id, speaker_status:e.speaker_status, relationship_id:e.relationship_id, viewpoint:e.viewpoint, provenance:e.provenance, evidence_revision:e.evidence_revision, segment_start_ms:e.segment_start_ms, segment_end_ms:e.segment_end_ms});
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
    var s = snippets[i], p = s.provenance || {}, refs = [];
    if (s.record_id) refs.push('record=' + s.record_id);
    if (s.person) refs.push('person=' + s.person);
    if (s.speaker_id) refs.push('speaker=' + s.speaker_id);
    if (s.viewpoint) refs.push('viewpoint=' + s.viewpoint);
    if (s.relationship_id) refs.push('relationship=' + s.relationship_id);
    if (s.tier) refs.push('Tier-' + s.tier);
    if (p.source_file_sha256 || p.legacy_source_sha256) refs.push('source_sha256=' + (p.source_file_sha256 || p.legacy_source_sha256));
    if (p.source_sha256) refs.push('source_snapshot_sha256=' + p.source_sha256);
    if (s.release_id) refs.push('release_id=' + s.release_id);
    if (p.sources) refs.push('source_count=' + p.sources.length + '; full_sources_digest=' + s.full_sources_digest + '; sources_EXCERPT=' + p.sources.slice(0, 3).map(function(r){return r.record_id;}).join(','));
    if (s.evidence_revision) refs.push('revision=' + s.evidence_revision);
    if (s.segment_start_ms != null) refs.push('segment_ms=' + s.segment_start_ms + '..' + s.segment_end_ms);
    if (p.source_records) refs.push('evidence=' + p.source_records.slice(0, 3).join(',') + ' (total=' + p.source_records.length + ')');
    lines.push((s.label || '[档案检索 Tier-2]') + ' ' + s.date + ' · ' + s.text + (refs.length ? ' [' + refs.join('; ') + ']' : ''));
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
function ensureDataReady() {
  if (typeof introAccepted !== 'undefined' && !introAccepted) return Promise.resolve(false);
  if (dataReadyPromise) return dataReadyPromise;
  dataReadyPhase = 'loading'; reportDataProgress();
  dataReadyPromise = loadContext().then(function(ok) {
    if (!ok) return false;
    if (contextLoaded) reportDataProgress('CONTEXT', 'verified');
    ['MEMORY','TRANSCRIPTS'].forEach(function(resource) { if (!dataProgress[resource]) reportDataProgress(resource, 'queued'); });
    shards.forEach(function(name, i) { if (!dataProgress['SHARD_' + (i + 1)]) reportDataProgress('SHARD_' + (i + 1), 'queued'); });
    return Promise.all([loadKnowledge(), loadShards()]).then(function() {
      if (knowledgeCache === null || shards.some(function(n) { return shardStatus[n] !== true; })) return false;
      scopeError = false;
      return true;
    });
  }).catch(function() { return false; }).then(function(ready) {
    dataReadyPhase = ready ? 'ready' : 'failed';
    if (!ready) dataReadyPromise = null;
    reportDataProgress();
    return ready;
  });
  return dataReadyPromise;
}
function loadContext() {
  if (contextLoading) return contextLoading;
  if (contextLoaded) return Promise.resolve(true);
  contextLoading = fetchDataJson('__CONTEXT_PATH__', 'CONTEXT')
    .then(function(data) {
      checkScope(data, 'context');
      systemPrompt = data.system_prompt || '';
      shards = Array.isArray(data.message_shards) ? data.message_shards : [];
      contextLoaded = true;
      reportDataProgress('CONTEXT', 'verified');
      applySessionsCard();
      return true;
    }).catch(function() { dataFailure('CONTEXT', 'SCOPE'); return false; })
    .then(function(ok) { contextLoading = null; return ok; });
  return contextLoading;
}
function loadShards() {
  if (shardsLoading) return shardsLoading;
  var names = shards || [];
  var fetches = names.map(function(name, index) {
    if (shardStatus[name] === true) return;
    var safeName = String(name).replace(/[^a-zA-Z0-9_/.-]/g, '_');
    var resource = 'SHARD_' + (index + 1);
    return fetchDataJson('data/' + safeName, resource)
      .then(function(data) {
        if (EXPECTED_SCOPE && !Array.isArray(data)) { scopeError = true; throw new Error('invalid shard'); }
        var rows = Array.isArray(data) ? data : [data];
        rows.forEach(function(row) { checkScope(row, 'message'); });
        shardCache[name] = rows; shardStatus[name] = true;
        reportDataProgress(resource, 'verified');
      })
      .catch(function() { dataFailure(resource, 'SCOPE'); if (EXPECTED_SCOPE) scopeError = true; shardStatus[name] = 'failed'; });
  });
  shardsLoading = Promise.all(fetches).then(function() { shardsLoading = false; });
  return shardsLoading;
}
function loadSessionsData() {
  if (sessionsDataPromise) return sessionsDataPromise;
  sessionsDataPromise = boundedWait(fetch(SESSIONS_PATH, {cache: 'no-cache'})
    .then(function(r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); }), 15000)
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
var memorySourceDigests = new Map();
async function validateMemoryRelease(data, isolated) {
  if (!isolated) memorySourceDigests = new Map();
  var validationDeadline = Date.now() + 15000;
  var b = EXPECTED_SCOPE && EXPECTED_SCOPE.memory_release;
  if (!b) { if (EXPECTED_SCOPE && data.entries.length) throw dataError('MEMORY', 'RELEASE'); return; }
  function stable(v) {
    if (Array.isArray(v)) return '[' + v.map(stable).join(',') + ']';
    if (v && typeof v === 'object') return '{' + Object.keys(v).sort().map(function(k){return JSON.stringify(k)+':'+stable(v[k]);}).join(',') + '}';
    return JSON.stringify(v);
  }
  if (data.schema_version !== 3 || data.release_id !== b.release_id || data.release_revision !== b.release_revision || data.source_sha256 !== b.source_sha256 ||
      data.entries.length !== Object.keys(b.card_revisions).length) throw dataError('MEMORY', 'RELEASE');
  var seen = new Set(), verifiedDigests = new Map();
  for (var c of data.entries) {
    checkScope(c, 'memory');
    if (seen.has(c.id)) throw dataError('MEMORY', 'DUPLICATE'); seen.add(c.id);
    var clean = Object.assign({}, c); delete clean.evidence_revision;
    if (typeof crypto === 'undefined' || !crypto.subtle || typeof crypto.subtle.digest !== 'function' || typeof TextEncoder === 'undefined') throw dataError('MEMORY', 'CRYPTO_UNAVAILABLE');
    var bytes;
    try { bytes = await boundedWait(crypto.subtle.digest('SHA-256', new TextEncoder().encode(stable(clean))), Math.max(0, validationDeadline - Date.now())); }
    catch (_) { throw dataError('MEMORY', 'CRYPTO_FAILED'); }
    var hash = Array.from(new Uint8Array(bytes)).map(function(n){return n.toString(16).padStart(2,'0');}).join('');
    if (hash !== c.evidence_revision) throw dataError('MEMORY', 'CARD_HASH');
    var sourceBytes;
    try { sourceBytes = await boundedWait(crypto.subtle.digest('SHA-256', new TextEncoder().encode(stable(c.provenance.sources))), Math.max(0, validationDeadline - Date.now())); }
    catch (_) { throw dataError('MEMORY', 'CRYPTO_FAILED'); }
    var sourceDigest = Array.from(new Uint8Array(sourceBytes)).map(function(n){return n.toString(16).padStart(2,'0');}).join('');
    verifiedDigests.set(c.id + ':' + c.evidence_revision, sourceDigest);
  }
  if (!isolated) memorySourceDigests = verifiedDigests;
  return verifiedDigests;
}
function loadKnowledge() {
  if (knowledgeLoading) return knowledgeLoading;
  if (knowledgeCache !== null) return Promise.resolve(knowledgeCache);
  var failed = false; var out = {memories: [], transcripts: []};
  var one = function(name, key) {
    var resource = key === 'memories' ? 'MEMORY' : 'TRANSCRIPTS';
    if (Object.prototype.hasOwnProperty.call(knowledgePieces, key)) { out[key] = knowledgePieces[key]; return Promise.resolve(); }
    return fetchDataJson('data/' + name, resource)
      .then(function(data) {
        checkScope(data, 'knowledge');
        if (EXPECTED_SCOPE && !Array.isArray(data.entries)) { scopeError = true; throw new Error('invalid knowledge'); }
        if (data && Array.isArray(data.entries)) {
          data.entries.forEach(function(row) { checkScope(row, 'knowledge'); });
          if (key === 'memories' && EXPECTED_SCOPE && (EXPECTED_SCOPE.memory_release || data.entries.length)) return validateMemoryRelease(data).then(function(){out[key] = data.entries;});
          if (EXPECTED_SCOPE && data.entries.length) throw new Error('unsupported transcripts');
          out[key] = key === 'memories' && !EXPECTED_SCOPE ? data.entries.filter(function(e){return !(e.tier === 2 || e.release_id || e.authorization || (e.provenance && e.provenance.source_kind === 'original_text'));}) : data.entries;
        }
      })
      .then(function() { knowledgePieces[key] = out[key]; reportDataProgress(resource, 'verified'); })
      .catch(function() { dataFailure(resource, 'SCOPE'); failed = true; if (EXPECTED_SCOPE) scopeError = true; });
  };
  var memoryName = 'memories.json';
  if (EXPECTED_SCOPE && EXPECTED_SCOPE.memory_release) {
    var releaseRevision = EXPECTED_SCOPE.memory_release.release_revision;
    if (typeof releaseRevision !== 'string' || !/^[0-9a-f]{64}$/.test(releaseRevision)) { dataFailure('MEMORY', 'RELEASE'); scopeError = true; return Promise.resolve(null); }
    memoryName = 'memories-' + releaseRevision + '.json';
  }
  knowledgeLoading = Promise.all([one(memoryName, 'memories'), one('transcripts.json', 'transcripts'), loadSessionsData()])
    .then(function() { knowledgeCache = failed ? null : out; knowledgeLoading = false; applySessionsCard(); return knowledgeCache; });
  return knowledgeLoading;
}
function collectAllRecords() {
  var all = []; for (var name in shardCache) { if (shardCache[name]) all = all.concat(shardCache[name]); } return all;
}

/* ===== streamRequest（唯一改动：openai 分支 reqBody 后加 deepseek thinking:disabled）===== */
// Companion-only transport: semantic completion owns settlement, not socket EOF.
function newRequestDiagnostic() {
  try {
    var bytes = new Uint8Array(16); crypto.getRandomValues(bytes);
    return {request_id: Array.from(bytes, function(x) { return ('0' + x.toString(16)).slice(-2); }).join('')};
  } catch (_) { return null; }
}
function requestDiagnosticText(diag, phase) {
  if (!diag || !/^[a-f0-9]{32}$/.test(diag.request_id || '')) return '';
  var safe = {request_id: diag.request_id};
  if (/^(FETCH|READ|PROTOCOL|CANCELLED|EMPTY|MIME|BODY|EOF|JSON|COMPLETE|UPSTREAM_FORBIDDEN|HTTP_[1-5][0-9]{2}|HTTP_ERROR)$/.test(phase)) safe.stage = phase;
  if (/^[1-5][0-9]{2}$/.test(String(diag.status))) safe.status = Number(diag.status);
  if (/^[a-fA-F0-9]{16}-[A-Z]{3}$/.test(diag.cf_ray || '')) safe.cf_ray = diag.cf_ray;
  if (/^[a-f0-9]{32}$/.test(diag.proxy_id || '')) safe.proxy_id = diag.proxy_id;
  try { console.info('request_diag', safe); } catch (_) {}
  return ' [request_id=' + safe.request_id + (safe.proxy_id ? ' proxy_id=' + safe.proxy_id : '') + (safe.status ? ' status=' + safe.status : '') + (safe.cf_ray ? ' cf_ray=' + safe.cf_ray : '') + ']';
}
function companionStream(endpoint, headers, body, mode, requestController, onDelta, onDone, onError, diagnostic) {
  var settled = false, reader = null, responseBody = null, acc = '', raw = '', buffer = '', frame = [];
  var completed = false, released = false, stage = 'FETCH';
  var decoder = new TextDecoder('utf-8', {fatal: true});
  function cleanup() {
    requestController.signal.removeEventListener('abort', abort);
    if (!reader) {
      if (responseBody) { try { Promise.resolve(responseBody.cancel()).catch(function() {}); } catch (_) {} }
      return;
    }
    try { Promise.resolve(reader.cancel()).catch(function() {}); } catch (_) {}
    try { if (!released) { reader.releaseLock(); released = true; } } catch (_) {}
  }
  function settle(code) {
    if (settled) return;
    if (!code && !acc.trim()) code = 'EMPTY';
    settled = true;
    cleanup();
    var diagnosticText = requestDiagnosticText(diagnostic, code || 'COMPLETE');
    if (code === 'CANCELLED') onDone(acc, true);
    else if (code) onError('LLM_' + code + diagnosticText);
    else onDone(acc, false);
  }
  function abort() { settle('CANCELLED'); }
  function emit(text) {
    if (typeof text !== 'string') throw new Error('protocol');
    if (text && !settled) { acc += text; onDelta(text); }
  }
  function dispatch() {
    if (!frame.length || completed) { frame = []; return; }
    var data = frame.join('\n'); frame = [];
    if (data === '[DONE]' && mode === 'openai') { completed = true; return; }
    var obj = JSON.parse(data);
    if (!obj || obj.error || obj.type === 'error') throw new Error('protocol');
    if (mode === 'anthropic') {
      if (obj.type === 'content_block_delta' && obj.delta && obj.delta.type === 'text_delta') emit(obj.delta.text);
      if (obj.type === 'message_stop') completed = true;
    } else {
      var choice = obj.choices && obj.choices[0];
      if (choice && choice.delta && choice.delta.content != null) emit(choice.delta.content);
      // A finish_reason can precede usage and DONE. DONE remains the protocol terminator.
    }
  }
  function line(text) {
    if (!text) { dispatch(); return; }
    if (text.indexOf('data:') === 0) frame.push(text.slice(5).replace(/^ /, ''));
    else if (text === 'data') frame.push('');
  }
  function feed(text, final) {
    buffer += text;
    while (!completed) {
      var m = /[\r\n]/.exec(buffer);
      if (!m) break;
      var i = m.index;
      if (buffer[i] === '\r' && i === buffer.length - 1 && !final) break;
      var n = buffer[i] === '\r' && buffer[i + 1] === '\n' ? 2 : 1;
      var value = buffer.slice(0, i); buffer = buffer.slice(i + n); line(value);
    }
    if (final && !completed) { if (buffer) line(buffer); buffer = ''; dispatch(); }
  }
  requestController.signal.addEventListener('abort', abort);
  if (requestController.signal.aborted) { abort(); return; }
  Promise.resolve().then(function() {
    if (settled) return;
    return fetch(endpoint, {method:'POST', headers:headers, body:JSON.stringify(body), signal:requestController.signal});
  }).then(async function(resp) {
    if (settled) { if (resp && resp.body) { try { Promise.resolve(resp.body.cancel()).catch(function(){}); } catch (_) {} } return; }
    responseBody = resp.body;
    if (diagnostic) {
      diagnostic.status = resp.status;
      diagnostic.cf_ray = resp.headers.get('CF-Ray') || '';
      diagnostic.proxy_id = resp.headers.get('X-Request-ID') || '';
    }
    if (!resp.ok) {
      var upstreamForbidden = resp.status === 403 && diagnostic &&
        /^[a-f0-9]{32}$/.test(diagnostic.request_id || '') && diagnostic.proxy_id === diagnostic.request_id &&
        resp.headers.get('X-LLM-Error') === 'upstream_forbidden';
      settle(upstreamForbidden ? 'UPSTREAM_FORBIDDEN' : 'HTTP_' + (/^[1-5][0-9]{2}$/.test(String(resp.status)) ? resp.status : 'ERROR')); return;
    }
    var mime = (resp.headers.get('Content-Type') || '').split(';')[0].trim().toLowerCase();
    var jsonMode = mime === 'application/json';
    if (!jsonMode && mime !== 'text/event-stream') { settle('MIME'); return; }
    if (!resp.body || !resp.body.getReader) { settle('BODY'); return; }
    reader = resp.body.getReader();
    while (!settled) {
      stage = 'READ';
      var result = await reader.read();
      if (settled) break;
      stage = 'PROTOCOL';
      var text = result.done ? decoder.decode() : decoder.decode(result.value, {stream:true});
      if (jsonMode) raw += text;
      else feed(text, result.done);
      if (completed) { settle(); return; }
      if (result.done) {
        if (!jsonMode) { settle('EOF'); return; }
        var obj = JSON.parse(raw);
        if (!obj || obj.error) { settle('JSON'); return; }
        var content = obj.choices && obj.choices[0] && obj.choices[0].message && obj.choices[0].message.content;
        if (mode === 'anthropic' && Array.isArray(obj.content)) {
          content = obj.content.filter(function(x) { return x && x.type === 'text'; }).map(function(x) { if (typeof x.text !== 'string') throw new Error('json'); return x.text; }).join('');
        }
        if (typeof content !== 'string') { settle('JSON'); return; }
        emit(content); settle(); return;
      }
    }
  }).catch(function() { settle(stage); }).finally(function() {
    if (reader) { try { if (!released) { reader.releaseLock(); released = true; } } catch (_) {} }
  });
}

function streamRequest(messages, onDelta, onDone, onError) {
  if (EXPECTED_SCOPE && (scopeError || !contextLoaded || knowledgeCache === null ||
      shards.some(function(n) { return shardStatus[n] !== true; }))) {
    onError('关系资料未完整加载或范围不一致，已停止发送'); return;
  }
  if (!settingsComplete()) { onError('请先在设置中配置接口'); return; }
  var requestController = new AbortController();
  controller = requestController; streaming = true; sendBtn.textContent = '停止'; sendBtn.classList.add('stop');
__LLM_PROXY_BRANCH__  var endpoint = settings.url;
  if (!/^https?:\/\//i.test(endpoint)) { onError('接口地址格式不正确'); return; }
  var isAnthropic = settings.provider === 'anthropic';
  var reqHeaders; var reqBody;
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
  companionStream(endpoint, reqHeaders, reqBody, isAnthropic ? 'anthropic' : 'openai', requestController, onDelta, onDone, onError);
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
function sendMessage(event) {
  if (typeof introAccepted !== 'undefined' && !introAccepted) return;
  if (streaming) {
    if (controller) { controller.abort(); }
    return;
  }
  if (sendPending) return;
  if (!settingsComplete()) { return; }
  if (!inputText.value.trim()) return;
  cancelVoiceTurn(true);
  if (typeof AUTO_VOICE_SESSION !== 'undefined' && AUTO_VOICE_SESSION) {
    var autoSession = initAutoVoiceSession();
    autoSession.turnDisabled = !autoSession.enabled; autoSession.lastError = null;
  }
  maybeActivateAutoVoice(event);
  var userText = inputText.value.trim();
  var generation = sendGeneration;
  var scope = JSON.stringify(EXPECTED_SCOPE);
  var turnSettled = false;
  var revision = inputRevision;
  var profile = JSON.stringify(settings);
  var requestSettings = {provider: settings.provider, model: settings.model};
  function isCurrent() { return !turnSettled && generation === sendGeneration && profile === JSON.stringify(settings) && scope === JSON.stringify(EXPECTED_SCOPE); }
  function run() {
    if (!isCurrent()) return;
    sendPending = false;
    if (revision !== inputRevision || inputText.value.trim() !== userText) return;
    maybeReplayHistory();
  inputText.value = ''; lastInputValue = ''; autoGrow();
  cancelVoiceTurn(true);               /* 先收掉上一回合（未念完的消息就地转文字），再挂用户气泡，保证顺序 */
  addBubble({type:'user', text: userText});
  ensureSessionStarted();
  sessionTurn += 1;
  var thisTurn = sessionTurn;
  logSession({role:'user', turn: thisTurn, text: userText}, requestSettings);

  var subjectBubble = addBubble({type:'subject', text: ''});
  var contentEl = subjectBubble.querySelector('.bubble-content');
  setTypingIndicator(contentEl);
  function incomplete(code) {
    contentEl.textContent = (accText ? accText + '\n' : '') + '（回复未完成，未加入对话上下文） [' + code + ']';
    if (/^LLM_UPSTREAM_FORBIDDEN(?: |$)/.test(code)) {
      contentEl.textContent += '\n模型服务拒绝了这次请求（403），具体原因尚未确认，请联系维护者核查。';
    }
    if (revision === inputRevision && !inputText.value) {
      inputText.value = userText; lastInputValue = userText; autoGrow();
    }
    // Manual recovery never sends automatically or overwrites a newer draft.
    var retry = document.createElement('button');
    retry.textContent = '恢复原问题';
    retry.addEventListener('click', function() {
      if (!inputText.value && !streaming && !sendPending) { inputText.value = userText; lastInputValue = userText; autoGrow(); }
    });
    contentEl.appendChild(retry);
  }
  cancelActiveSend = function() { turnSettled = true; incomplete('LLM_CANCELLED'); };

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
      if (!isCurrent()) return;
      accText += delta;
    }, function(finalText, aborted) {
      if (!isCurrent()) return;
      turnSettled = true;
      cancelActiveSend = null;
      sendBtn.disabled = !settingsComplete();
      sendBtn.classList.remove('stop');
      sendBtn.textContent = '发送';
      streaming = false;
      controller = null;
      if (aborted) {
        incomplete('LLM_CANCELLED');
        return;
      }
      if (typeof finalText !== 'string' || !finalText.trim()) {
        incomplete('LLM_EMPTY');
        logSession({role:'event', turn: thisTurn, text:'llm_error', detail:'LLM_EMPTY'}, requestSettings);
        return;
      }
      history.push({role: 'user', content: userText}, {role: 'assistant', content: finalText});
      var emo = detectEmotion(finalText);
      // TODO 8A-2b: 关窗道别语、空闲「去忙了」、rhythm.json 限速、使用统计自见卡

      var pres = startTurnPresentation(contentEl, finalText, thisTurn, emo);
      logSession({role:'simulacrum', turn: thisTurn, text: finalText, emotion: emo, tts: pres.tts, messages: pres.count, retrieval_used: retrievalUsed}, requestSettings);
    }, function(err) {
      if (!isCurrent()) return;
      turnSettled = true;
      cancelActiveSend = null;
      sendBtn.disabled = !settingsComplete();
      sendBtn.classList.remove('stop');
      sendBtn.textContent = '发送';
      streaming = false;
      controller = null;
      var code = /^LLM_(?:EMPTY|FETCH|READ|PROTOCOL|EOF|MIME|BODY|JSON|UPSTREAM_FORBIDDEN|HTTP_(?:[1-5][0-9]{2}|ERROR))(?: \[request_id=[a-f0-9]{32}(?: proxy_id=[a-f0-9]{32})?(?: status=[1-5][0-9]{2})?(?: cf_ray=[a-fA-F0-9]{16}-[A-Z]{3})?\])?$/.test(err) ? err : 'LLM_REQUEST';
      incomplete(code);
      logSession({role:'event', turn: thisTurn, text:'llm_error', detail: code}, requestSettings);
    });
  }

  sendPending = true;
  var pendingNotice = addBubble({type:'notice', text:'正在加载并校验资料，请稍候… · D4'});
  var sendingStarted = false;
  var stopProgress = subscribeDataProgress(function(p) { pendingNotice.textContent = dataProgressText(p); });
  function pendingResult(text) { pendingNotice.textContent = text; }
  ensureDataReady().then(function(ready) {
    stopProgress();
    if (!isCurrent()) { if (generation === sendGeneration) sendPending = false; pendingResult('设置已更改，本次未发送。请重新点击发送。 · D4'); return; }
    if (revision !== inputRevision || inputText.value.trim() !== userText) {
      sendPending = false;
      pendingResult('输入已修改，本次未发送。请确认后重新点击发送。 · D4');
      return;
    }
    if (!ready) {
      sendPending = false;
      if (dataBlocked > 0) pendingResult('资料传输未结束；请先复制保留输入，再重新打开本页。' + dataDiagnostic());
      else pendingResult('关系资料暂时未能完整加载或校验，请稍后再点发送重试。输入已保留。' + dataDiagnostic());
      return;
    }
    if (pendingNotice.parentNode) pendingNotice.parentNode.removeChild(pendingNotice);
    sendingStarted = true;
    run();
  }).catch(function() {
    stopProgress();
    if (!isCurrent()) return;
    sendPending = false;
    if (sendingStarted) { systemNotice('发送过程中发生错误，请检查聊天记录后再决定是否重发。 [D4 SEND_FAILED]'); return; }
    pendingResult('本次未能发送，输入已保留。请重新点击发送。 [D4 SEND_FAILED]');
  });
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

function historyVoiceEntries(text, pool) {
  text = String(text || '');
  var seen = {}, candidates = [], spoken = paragraphSpeech(text), d12 = paragraphSpeech(text, true);
  pool.forEach(function(audio) {
    if (seen[audio.file]) return;
    seen[audio.file] = true;
    // The service strips boundary whitespace before recording its text key.
    var key = String(audio.text || '').trim(), matches = [];
    function locate(haystack, offsets) {
      if (!key) return;
      var at = haystack.indexOf(key);
      while (at >= 0) {
        var start = offsets ? offsets[at] : at;
        var end = offsets ? offsets[at + key.length] : at + key.length;
        if (!matches.some(function(m) { return m.start === start && m.end === end; })) matches.push({start:start,end:end});
        at = haystack.indexOf(key, at + 1);
      }
    }
    locate(text, null);
    locate(spoken.text, spoken.offsets);
    locate(d12.text, d12.offsets);
    var match = matches[0] || {start:-1,end:-1};
    candidates.push({text: key, audio: audio, start: match.start, end: match.end, unique: matches.length === 1});
  });
  candidates.forEach(function(c) {
    c.placed = c.unique && !candidates.some(function(other) {
      return other !== c && other.unique && c.start < other.end && other.start < c.end;
    });
  });
  var positioned = [], cursor = 0;
  candidates.filter(function(c) { return c.placed; }).sort(function(a,b) { return a.start-b.start; }).forEach(function(c) {
    if (c.start > cursor) positioned.push({text:text.slice(cursor,c.start)});
    positioned.push({text:text.slice(c.start,c.end),audio:c.audio});
    cursor=c.end;
  });
  if (cursor < text.length) positioned.push({text:text.slice(cursor)});
  return {positioned:positioned, unresolved:candidates.filter(function(c) { return !c.placed; })};
}
function renderGroupedHistory(text, pool) {
  var plan = historyVoiceEntries(text, pool), rendered = 0;
  function entry(item) {
    var b=addBubble({type:'subject',text:'',noDivider:true}), el=b.querySelector('.bubble-content');
    rendered++;
    if (!item.audio) { el.innerHTML=displayGroupHtml(item.text); return; }
    var au=item.audio;
    var dur=(typeof au.dur==='number' && isFinite(au.dur) && au.dur>0) ? au.dur : null;
    el.className='bubble-content voice'; el.innerHTML=voiceBarHtml(item.text,dur);
    var bar=el.querySelector('.voice-bar');
    bar._voiceUrl=SESSIONS_BASE+au.file; bar._voiceBlob=null; bar._voiceLoading=false;
    wireHistoryBar(bar);
  }
  plan.positioned.forEach(entry);
  if (plan.unresolved.length) {
    addBubble({type:'notice',text:'本轮另存录音：无法确定对应的原文位置，以下不表示讲话顺序。',noDivider:true});
    plan.unresolved.forEach(entry);
  }
  return rendered;
}
function displayGroupHtml(text) {
  // Let CSS wrap to the available width. Block nodes every 30 characters
  // created visual breaks inside words, unrelated to source or speech pauses.
  var part = String(text || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
  return '<div class="display-chunk" style="white-space:pre-wrap">' + part + '</div>';
}
// Deliberately bounded fallback, not a sentence parser. Other missing punctuation
// is the prompt's responsibility. Never infer stops from display/SSE/group cuts.
function overtSpeechQuestion(text) {
  return /[?？]|(?:吗|么|伐|呢)|是不是|是否|怎么|怎样|为何|为什么|难道|谁|哪|几|多少/.test(text);
}
function continuedSpeechQuotes(text) {
  var pairs = {'“':'”','‘':'’','「':'」','『':'』','"':'"',"'":"'"}, stack = [], spans = [];
  for (var i = 0; i < text.length; i++) {
    var ch = text[i], top = stack[stack.length - 1];
    if (top && ch === top.close) {
      stack.pop();
      if (/[\r\n]/.test(text.slice(top.start, i))) spans.push({start:top.start,end:i + 1});
    } else if (pairs[ch]) stack.push({start:i,close:pairs[ch]});
  }
  stack.forEach(function(open) { spans.push({start:open.start,end:text.length + 1}); });
  return spans;
}
function completedSpeechLine(line) {
  var value = line.trim();
  // Only a whole, single-line quotation is eligible; embedded/open quotes are not.
  if (/^[“「『"']/.test(value)) {
    var pairs = {'“':'”','「':'」','『':'』','"':'"',"'":"'"};
    if (value.slice(-1) !== pairs[value[0]]) return false;
    value = value.slice(1, -1).trim();
  }
  if (/[“”‘’「」『』"'\r\n]/.test(value)) return false;
  // Reject overt questions, conditions and reported/unfinished constructions.
  // Unknown questions and meanings remain outside this small lexical rule.
  if (overtSpeechQuestion(value) || /如果|要是|假如|只要|除非|即使|虽然|因为|等到|等你|等侬|比如|例如|的话|不晓得/.test(value)) return false;
  if (/^(?:等|待|一旦|倘若|既然|尽管|虽说|倘使)/.test(value)) return false;
  return /(?:就好|晓得了)$/.test(value);
}
// Offsets are UTF-16 boundaries, matching slice/indexOf; inserted punctuation
// consumes no source. d12Only retains the old recorded-audio lookup form.
function paragraphSpeech(text, d12Only) {
  text = String(text || '');
  var originalText = text;
  var sourceOffsets = Array.from({length:text.length + 1}, function(_, i) { return i; }), annotation;
  // Remove annotations before grouping, just as the backend does. Otherwise
  // a 120-codepoint cut can expose half an annotation as spoken text.
  while ((annotation = /[\[【（(][^\[\]【】（）()]*[\]】）)]/.exec(text))) {
    var start = annotation.index, end = start + annotation[0].length;
    text = text.slice(0, start) + ' ' + text.slice(end);
    sourceOffsets = sourceOffsets.slice(0, start + 1).concat([sourceOffsets[end]], sourceOffsets.slice(end + 1));
  }
  var quotes = d12Only ? [] : continuedSpeechQuotes(text);
  function quoted(at) { return quotes.some(function(span) { return at > span.start && at < span.end; }); }
  var insertions = {}, boundary = /\r?\n[^\S\r\n]*\r?\n(?:[^\S\r\n]*\r?\n)*/g, match, paragraphStart = 0;
  while ((match = boundary.exec(originalText))) {
    // Annotation removal must not turn ordinary line breaks into a paragraph.
    var boundaryStart = sourceOffsets.indexOf(match.index);
    var boundaryEnd = sourceOffsets.indexOf(boundary.lastIndex);
    if (boundaryStart < 0 || boundaryEnd < 0 || text.slice(boundaryStart, boundaryEnd) !== match[0]) continue;
    var prefix = text.slice(paragraphStart, boundaryStart);
    var content = prefix.replace(/[\s”’"'」』）)\]】》〉]+$/u, '');
    var nextContent = text.slice(boundaryEnd).trim();
    if (content && !/[。！？!?….,，;；:：]$/u.test(content) && nextContent && (d12Only || (!overtSpeechQuestion(content) && !quoted(paragraphStart + content.length) && !/^[。！？!?….]/u.test(nextContent)))) insertions[paragraphStart + content.length] = true;
    paragraphStart = boundaryEnd;
  }
  if (!d12Only) {
    var lines = /[^\r\n]+|\r?\n/g, line, previousClear = true;
    while ((line = lines.exec(text))) {
      if (/^\r?\n$/.test(line[0]) || !line[0].trim()) continue;
      var value = line[0], content = value.replace(/[\s”’"'」』）)\]】》〉]+$/u, '');
      var at = line.index + content.length;
      var next = text.slice(lines.lastIndex).replace(/^\s+/, '');
      var continuation = /^(?:的话|还是|或者|或是|以及|而且|但是|不过|就|才|再|那就|那么|所以|因为|了|着|过|的|地|得|吗|么|伐|呢|[，,、:：;；。！？!?….])/u.test(next);
      if (previousClear && !continuation && !quoted(at) && completedSpeechLine(value)) insertions[at] = true;
      previousClear = !!insertions[at] || /[。！？!?…]$|\.{3}$/u.test(content);
    }
  }
  var speech = '', offsets = [sourceOffsets[0]];
  for (var i = 0; i <= text.length; i++) {
    if (insertions[i]) { speech += '。'; offsets.push(sourceOffsets[i]); }
    if (i < text.length) { speech += text.charAt(i); offsets.push(sourceOffsets[i + 1]); }
  }
  return {text:speech, offsets:offsets};
}
function paragraphVoicePlan(text) {
  text = String(text || '');
  var spoken = paragraphSpeech(text), speech = splitVoiceGroups(spoken.text), cursor = 0;
  // Repair only a stranded inserted stop, identified by zero-width source
  // provenance. Ordinary legacy punctuation/whitespace grouping stays intact.
  for (var i = 0, offset = 0; i < speech.length; offset += speech[i++].length) {
    var inserted = false;
    for (var j = 0; j < speech[i].length; j++) {
      if (speech[i][j] === '。' && spoken.offsets[offset + j] === spoken.offsets[offset + j + 1]) inserted = true;
    }
    // The inserted stop can just fit the previous group while its closing
    // quote/newline spills into this group. Keep that same ending together.
    var tail = offset - 1;
    while (tail >= 0 && /[\s”’"'」』]/u.test(spoken.text[tail])) tail--;
    if (tail >= 0 && spoken.text[tail] === '。' && spoken.offsets[tail] === spoken.offsets[tail + 1]) inserted = true;
    if (i && inserted && !/[\p{L}\p{N}]/u.test(speech[i]) && /[\p{L}\p{N}]/u.test(speech[i - 1])) {
      var joined = Array.from(speech[i - 1] + speech[i]), cut = Math.ceil(joined.length / 2);
      var before = joined.slice(0, cut).join(''), after = joined.slice(cut).join('');
      if (/[\p{L}\p{N}]/u.test(before) && /[\p{L}\p{N}]/u.test(after)) {
        offset -= speech[i - 1].length - before.length;
        speech[i - 1] = before; speech[i] = after;
      }
    }
  }
  var source = speech.map(function(group) {
    var start = spoken.offsets[cursor];
    cursor += group.length;
    return text.slice(start, spoken.offsets[cursor]);
  });
  return {source:source, speech:speech};
}
function splitVoiceGroups(text) {
  var units = String(text || '').match(/[^。！？!?\n]+[。！？!?]*[”’"'」』]*|[。！？!?]+[”’"'」』]*|\n+/gu) || [];
  var groups = [], current = '';
  units.forEach(function(unit, unitIndex) {
    var chars = Array.from(unit);
    while (chars.length > 120) {
      if (current) { groups.push(current); current = ''; }
      var cut = 120;
      for (var j = 119; j >= 60; j--) {
        if (/[,，;；:：\s]/u.test(chars[j])) { cut = j + 1; break; }
      }
      // A cut leaving only terminal punctuation loses the pause at TTS and
      // can map an inserted stop to an empty source bubble. Balance only this
      // final oversized unit, avoiding a one-character spoken tail.
      if (chars.length <= 240 && /^[\s”’"'」』]*$/u.test(units.slice(unitIndex + 1).join('')) && /[^。！？!?”’"'」』]/u.test(chars.slice(0, cut).join('')) && /^[。！？!?”’"'」』]+$/u.test(chars.slice(cut).join(''))) cut = Math.ceil(chars.length / 2);
      groups.push(chars.splice(0, cut).join(''));
    }
    var rest = chars.join('');
    if (Array.from(current + rest).length > 120) { groups.push(current); current = ''; }
    current += rest;
  });
  if (current) groups.push(current);
  return groups;
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
function takePending(vt, i) {
  if (vt.contents[i]) return vt.contents[i];
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
  if (typeof VOICE_GROUPS !== 'undefined' && VOICE_GROUPS) el.innerHTML = displayGroupHtml(vt.msgs[i]);
  else el.textContent = vt.msgs[i];
  if (!vt.firstShown) {
    vt.firstShown = true;
    showEmotion(vt.emo);
  }
  chat.scrollTop = chat.scrollHeight;
}
function voiceBarHtml(msg, dur) {
  var safeMsg = String(msg || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
  if (typeof VOICE_GROUPS !== 'undefined' && VOICE_GROUPS) safeMsg = displayGroupHtml(msg);
  var durNum = (dur && !isNaN(dur) && dur > 0) ? dur : null;
  var W = 72 + Math.min(Math.max((durNum || 1), 1), 30) * 4;
  var D = durNum ? (String(Math.max(1, Math.round(durNum))) + '"') : '';
  return '<div class="voice-bar" role="button" tabindex="0" style="width:' + W + 'px"><span class="voice-icon"><i></i><i></i><i></i></span><span class="voice-dur">' + D + '</span></div><div class="voice-text">' + safeMsg + '</div>';
}
function showVoiceMsg(vt, i, blob, dur) {
  var bar = vt.bars[i];
  if (!bar) {
    var el = takePending(vt, i);
    el.className = 'bubble-content voice';
    el.innerHTML = voiceBarHtml(vt.msgs[i], dur);
    bar = el.querySelector('.voice-bar');
    bar._voiceTurn = vt; bar._voiceIndex = i;
    vt.bars[i] = bar;
    wireHistoryBar(bar);
  }
  if (blob) {
    bar._voiceBlob = blob;
    bar._historyStatus.textContent = ''; bar._historyRetry.hidden = true;
    ensureNativeAudio(bar);
    showAutoVoiceFailure(bar);
  }
  if (!vt.firstShown) { vt.firstShown = true; showEmotion(vt.emo); }
  chat.scrollTop = chat.scrollHeight;
  return bar;
}
function synthMsg(vt, i, retry) {
  if (i >= vt.msgs.length || !voiceScopeCurrent(vt)) return;
  if (!vt.requests) vt.requests = [];
  if (retry) {
    if (vt.requests[i] !== 'failed') return;
  } else if (vt.canceled || vt.requests[i]) return;
  if (i >= vt.voiceCount || (vt.speechMsgs || vt.msgs)[i].replace(/[\[【（(][^\[\]【】（）()]*[\]】）)]/g, '').replace(/[\s。！？!?；;，、,：:…\.~～—\-·"'“”‘’]+/g, '') === '') {
    vt.blobs[i] = 'text'; showTextMsg(vt, i); tryAdvance(vt); synthMsg(vt, i + 1); return;
  }
  vt.requests[i] = 'loading';
  var bar = vt.bars[i];
  if (bar) { bar._voiceLoading = true; bar._historyRetry.hidden = true; bar._historyStatus.textContent = '正在生成语音… · D4'; }
  fetchVoiceBlob(ttsBase + '/tts', {
    method: 'POST',
    __TTS_HEADERS_TTS__,
    body: JSON.stringify({text: (vt.speechMsgs || vt.msgs)[i], lang: '__TTS_LANG__', session_id: sessionId, turn: vt.turn})
  }, TTS_FETCH_TIMEOUT_MS).then(function(result) {
    if (!voiceScopeCurrent(vt)) return;
    vt.requests[i] = 'ready'; vt.blobs[i] = result.blob; vt.durs[i] = result.dur;
    showVoiceMsg(vt, i, result.blob, result.dur);
    if (!retry) { tryAdvance(vt); synthMsg(vt, i + 1); }
  }).catch(function(error) {
    if (!voiceScopeCurrent(vt)) return;
    vt.requests[i] = 'failed'; vt.blobs[i] = 'failed';
    var failedBar = showVoiceMsg(vt, i, null, null);
    voiceError(failedBar, error.code || 'AUDIO_FETCH');
    if (!vt.failLogged) {
      vt.failLogged = true;
      logSession({role:'event', turn:vt.turn, text:'tts_failed', detail:error.code || 'AUDIO_FETCH'});
    }
    if (!retry) { tryAdvance(vt); synthMsg(vt, i + 1); }
  }).then(function() { if (vt.bars[i]) vt.bars[i]._voiceLoading = false; });
}
function tryAdvance(vt) {
  if (vt !== voiceTurn || vt.canceled || vt.autoStopped || vt.playing || vt.waiting || !voiceScopeCurrent(vt) || document.hidden) return;
  var i = vt.playIdx;
  if (i >= vt.msgs.length) { vt.done = true; vt.pendingEl = null; return; }
  var b = vt.blobs[i];
  if (b === undefined) return;
  if (b === 'failed' || b === 'text') {
    vt.playIdx += 1; tryAdvance(vt); return;
  }
  if (typeof AUTO_VOICE_SESSION !== 'undefined' && AUTO_VOICE_SESSION) {
    var session = initAutoVoiceSession();
    if (!session.ready || session.suspended || (session.job && session.job.cue)) return;
  }
  playSegmentBlob(vt, b);
}
function textDelay(msg) {
  return Math.min(600 + String(msg || '').length * 90, 3500);
}
function playSegmentBlob(vt, blob) {
  var bar = vt.bars[vt.playIdx];
  if (bar && bar._voiceBlob === blob) playHistoryNative(bar, vt);
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
      if (typeof VOICE_GROUPS !== 'undefined' && VOICE_GROUPS) parent.innerHTML = displayGroupHtml(vt.msgs[idx]);
      else parent.textContent = vt.msgs[idx];
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
function stopReplay(markManualStop) {
  stopAutoVoiceJob();
  nativeEpoch++;
  var audio = replayAudio, bar = replayingBar;
  replayAudio = null; replayingBar = null;
  if (activePlay) { activePlay.playing = false; if (markManualStop !== false) activePlay.autoStopped = true; }
  activePlay = null;
  if (bar) {
    bar._historyAttempt = (bar._historyAttempt || 0) + 1;
    if (bar._historyTimer) { clearTimeout(bar._historyTimer); bar._historyTimer = null; }
    bar._controlGesture = 0; bar.classList.remove('playing');
  }
  // Retire managed native instances before pausing: a delayed play on the old
  // object can never impersonate a UA-control start on the replacement.
  if (audio && audio._managedNative && bar && bar._historyAudio === audio) {
    bar._historyAudio = null;
    if (audio.parentNode) audio.parentNode.removeChild(audio);
    ensureNativeAudio(bar);
  }
  if (audio) { try { audio.pause(); } catch (_) {} }
}
function cancelVoiceTurn(preserveCue) {
  var session = typeof autoVoiceSession !== 'undefined' ? autoVoiceSession : null;
  var cue = session && session.job;
  if (!(preserveCue && cue && cue.cue && !document.hidden && cue.profile === JSON.stringify(settings) && cue.scope === JSON.stringify(EXPECTED_SCOPE) && cue.generation === sendGeneration)) stopReplay();
  if (!voiceTurn) return;
  var vt = voiceTurn;
  vt.canceled = true; vt.autoStopped = true;
  if (vt.textTimer) clearTimeout(vt.textTimer);
  if (vt.safetyTimer) clearTimeout(vt.safetyTimer);
  dumpRemaining(vt);
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
  if (voiceTurn) voiceTurn.autoStopped = true;
  playHistoryNative(bar);
}
function startTurnPresentation(contentEl, finalText, turnNo, emo) {
  cancelVoiceTurn(true);
  var plan = typeof VOICE_GROUPS !== 'undefined' && VOICE_GROUPS ? paragraphVoicePlan(finalText) : null;
  var msgs = plan ? plan.source : splitMessages(finalText);
  if (msgs.length === 0) { msgs = [String(finalText || '').replace(/^\s+|\s+$/g, '') || '…']; }
  var speechMsgs = plan && plan.speech.length ? plan.speech : msgs;
  var mode = ttsAvailable ? 'voice' : 'text';
  var voiceCount = Math.min(msgs.length, MSG_MAX_VOICE);
  if (typeof VOICE_GROUPS !== 'undefined' && VOICE_GROUPS) {
    voiceCount = 0;
    var used = 0;
    while (voiceCount < msgs.length && used + Array.from(speechMsgs[voiceCount]).length <= 360) {
      used += Array.from(speechMsgs[voiceCount++]).length;
    }
  }
  var vt = {
    turn: turnNo,
    generation: sendGeneration,
    profile: JSON.stringify(settings),
    scope: JSON.stringify(EXPECTED_SCOPE),
    requests: [],
    autoStopped: typeof AUTO_VOICE_SESSION !== 'undefined' && AUTO_VOICE_SESSION && (!initAutoVoiceSession().enabled || !!initAutoVoiceSession().turnDisabled),
    msgs: msgs,
    speechMsgs: speechMsgs,
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
  var saved = readUiPrefs();
  if (typeof AUTO_VOICE_SESSION !== 'undefined' && AUTO_VOICE_SESSION) {
    var s = initAutoVoiceSession();
    s.enabled = typeof saved.autoVoiceEnabled === 'boolean' ? saved.autoVoiceEnabled : true;
    s.checkbox.checked = s.enabled;
  }
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
  saveUiPrefs();
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

  document.addEventListener('visibilitychange', function() { if (document.hidden) suspendNativeVoice(false); });
  window.addEventListener('pagehide', function(event) { suspendNativeVoice(!event.persisted); });
  window.addEventListener('pageshow', function(event) { if (event.persisted) suspendNativeVoice(false); });
  initAutoVoiceSession();
  loadSettings();
  loadUiPrefs();
  startTtsProbeLoop();
  __SW_REGISTER_JS__

  // 页面一打开就取会话数据（与 chat_context 并行，不等待），刷新后才回放得了往次记录
  loadSessionsData();

  // 从 chat_context.json 载入 systemPrompt + shards
  loadContext().then(function(ok) {
    if (ok) updateChatState();
    else {
      systemNotice('关系资料暂时未能完整加载或校验，可稍后输入并点发送重试。' + dataDiagnostic());
      sendBtn.disabled = !settingsComplete();
    }
  });

  fetch('data/avatar/emotions.json', {cache: 'no-cache'})
    .then(function(r) { if (!r.ok) throw new Error('no emotions'); return r.json(); })
    .then(function(cfg) { emotionsCfg = cfg; })
    .catch(function() { emotionsCfg = null; /* 资产未就绪：功能静默关闭 */ });

  // 输入框 auto-grow
  inputText.addEventListener('input', trackDraftInput);

  // 发送按钮 / Enter 发送
  sendBtn.addEventListener('click', sendMessage);
  inputText.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(e);
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
#intro-card [hidden]{display:none;}
#intro-progress{font-size:20px;line-height:1.8;}
#intro-enter{margin-top:16px;}
#preparation-banner{padding:10px 14px;background:#f0e9df;color:#3a3330;font-size:15px;line-height:1.5;}
#preparation-banner[hidden]{display:none;}
#preparation-banner button{margin-left:10px;min-height:36px;}
"""

_INTRO_CARD_HTML = """<div id="intro-card"><div class="ic-box">
<div id="intro-notice"><h2>开始之前，请先看一下</h2>
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
<button id="intro-ok" type="button">我知道了</button></div>
<div id="intro-preparing" hidden><h2>正在准备资料</h2>
<p id="intro-progress" role="status" aria-live="polite"></p>
<button id="intro-retry" type="button" hidden>重试准备</button>
<button id="intro-enter" type="button">先进入聊天</button></div>
</div></div>
"""

_INTRO_CARD_JS = """(function(){
  var card = document.getElementById('intro-card');
  var ok = document.getElementById('intro-ok');
  if (!card || !ok) return;
  var preparing = document.getElementById('intro-preparing');
  var status = document.getElementById('intro-progress');
  var retry = document.getElementById('intro-retry');
  var enter = document.getElementById('intro-enter');
  var banner = document.createElement('div');
  banner.id = 'preparation-banner'; banner.hidden = true;
  var bannerStatus = document.createElement('span'); bannerStatus.setAttribute('role', 'status');
  var bannerRetry = document.createElement('button'); bannerRetry.type = 'button'; bannerRetry.textContent = '重试准备';
  banner.appendChild(bannerStatus); banner.appendChild(bannerRetry);
  var chatElement = document.getElementById('chat'); chatElement.parentNode.insertBefore(banner, chatElement);
  subscribeDataProgress(function(p) {
    status.textContent = dataProgressText(p);
    bannerStatus.textContent = status.textContent;
    bannerRetry.hidden = p.phase !== 'failed';
    retry.hidden = p.phase !== 'failed';
    enter.textContent = p.phase === 'ready' ? '进入聊天' : '先进入聊天';
    preparing.querySelector('h2').textContent = p.phase === 'ready' ? '资料已准备好' : p.phase === 'failed' ? '资料准备未完成' : '正在准备资料';
  });
  ok.addEventListener('click', function(){
    introAccepted = true;
    document.getElementById('intro-notice').hidden = true;
    preparing.hidden = false;
    ensureDataReady();
  });
  retry.addEventListener('click', function(){ ensureDataReady(); });
  bannerRetry.addEventListener('click', function(){ ensureDataReady(); });
  enter.addEventListener('click', function(){ if (!introAccepted) return; banner.hidden = false; card.parentNode.removeChild(card); });
})();
"""


def diagnostic_template(auto_voice_session, voice_groups):
    template = TEMPLATE.replace('D4', 'D6' if auto_voice_session else 'D5') if (auto_voice_session or voice_groups) else TEMPLATE
    if auto_voice_session:
        template = re.sub(r"data:audio/wav;base64,[^']*|D6", lambda m: m.group(0) if m.group(0).startswith('data:') else 'D14', template)
    return template


def guard_archive_transport(html: str) -> str:
    """Keep stale raw-download effects local, only on the opted-in father page."""
    start = html.index('var dataQueue = ')
    end = html.index('function checkScope(', start)
    transport = html[start:end]
    replacements = (
        ("    job = function() {\n",
         "    job = function() {\n"
         "      if (rawBytes && archiveEpoch !== dataArchiveEpoch) {\n"
         "        delete dataRequests[url]; reject(new Error('ARCHIVE_INVALIDATED'));\n"
         "        dataActive--; drainDataQueue(); return;\n"
         "      }\n"),
        ("var phase = 'FETCH', expired = false;", "var phase = 'FETCH', expired = false, countedBlocked = false;"),
        ("        expired = true;\n        dataBlocked++;",
         "        expired = true;\n"
         "        if (rawBytes && archiveEpoch !== dataArchiveEpoch) {\n"
         "          reject(new Error('ARCHIVE_INVALIDATED'));\n"
         "          if (ctrl) { try { ctrl.abort(); } catch (_) {} }\n"
         "          return; // Keep the real transport slot until its body settles.\n"
         "        }\n"
         "        countedBlocked = true; dataBlocked++;"),
        ("        if (expired) dataBlocked--;", "        if (countedBlocked) dataBlocked--;"),
        ("      reject(dataError(resource, 'TRANSPORT_BLOCKED'));",
         "      reject(rawBytes && archiveEpoch !== dataArchiveEpoch ? new Error('ARCHIVE_INVALIDATED') : dataError(resource, 'TRANSPORT_BLOCKED'));"),
    )
    for old, new in replacements:
        if transport.count(old) != 1:
            raise ValueError('archive transport guard anchor changed')
        transport = transport.replace(old, new, 1)
    return html[:start] + transport + html[end:]


def quiet_archive_preparation(html: str) -> str:
    """Change only the opt-in father's preparation presentation, retaining all gates."""
    html = re.sub(r"(var AUTO_VOICE_CUE = ')data:audio/wav;base64,[^']*", lambda m: m.group(1) + 'data:audio/wav;base64,UklGRuQSAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YcASAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=', html, count=1)
    html = html.replace('发送时会尝试提示音', '发送时会静默启用播放').replace('测试提示音 / 重试朗读', '启用播放 / 重试朗读').replace('提示音已取消', '播放启用已取消').replace('正在尝试播放提示音…', '正在静默启用播放…')
    # A consent-gated false is not a load error. This page already has the shared
    # preparation banner (including real failures/retry); do not create a stale
    # independent init notice that can never follow preparation back to ready.
    init_notice = "      systemNotice('关系资料暂时未能完整加载或校验，可稍后输入并点发送重试。' + dataDiagnostic());"
    if html.count(init_notice) != 1:
        raise ValueError('archive init notice template mismatch')
    html = html.replace(init_notice, "      reportDataProgress();", 1)
    replacements = (
        ("    status.textContent = dataProgressText(p);",
         "    banner.hidden = card.isConnected || p.phase !== 'failed';\n"
         "    status.textContent = dataProgressText(p);"),
        ("banner.hidden = false; card.parentNode.removeChild(card);",
         "banner.hidden = dataReadyPhase !== 'failed'; card.parentNode.removeChild(card);"),
        ("  dataReadyPhase = 'loading'; reportDataProgress();\n  var p = (forSend ?",
         "  dataReadyPhase = dataReadyPhase === 'ready' ? 'verifying' : 'loading'; reportDataProgress();\n  var p = (forSend ?"),
        ("archiveOptions.transport = function(path) {\n",
         "archiveOptions.transport = function(path) {\n  dataReadyPhase = 'loading'; reportDataProgress();\n"),
        ("  var stopProgress = subscribeDataProgress(function(p) { pendingNotice.textContent = dataProgressText(p); });",
         "  var stopProgress = subscribeDataProgress(function(p) {\n"
         "    if (p.phase === 'failed') pendingResult(dataProgressText(p));\n"
         "  });"),
        ("  function pendingResult(text) { pendingNotice.textContent = text; }",
         "  function pendingResult(text) {\n"
         "    pendingLabel.textContent = text;\n"
         "    if (!pendingNotice.isConnected) chat.appendChild(pendingNotice);\n"
         "    if (!sendPending || turnSettled) pendingCancel.disabled = true;\n"
         "    chat.scrollTop = chat.scrollHeight;\n"
         "  }"),
        ("    if (pendingNotice.parentNode) pendingNotice.parentNode.removeChild(pendingNotice);",
         "    if (pendingNotice && pendingNotice.parentNode) pendingNotice.parentNode.removeChild(pendingNotice);"),
    )
    for old, new in replacements:
        if html.count(old) != 1:
            raise ValueError('quiet archive preparation template mismatch')
        html = html.replace(old, new, 1)
    html, count = re.subn(
        r"  var pendingNotice = addBubble\(\{type:'notice', text:'正在加载并校验资料，请稍候… · [A-Za-z0-9][A-Za-z0-9._-]{0,63}'\}\);",
        "  var pendingNotice = document.createElement('div'); pendingNotice.className = 'bubble notice';\n"
        "  pendingNotice.setAttribute('role', 'status');\n"
        "  var pendingLabel = document.createElement('span');\n"
        "  pendingLabel.textContent = '正在核验资料，尚未发送；输入已保留。';\n"
        "  var pendingCancel = document.createElement('button');\n"
        "  pendingCancel.type = 'button'; pendingCancel.className = 'archive-send-cancel';\n"
        "  pendingCancel.textContent = '取消'; pendingCancel.setAttribute('aria-label', '取消本次发送');\n"
        "  pendingNotice.appendChild(pendingLabel); inputText.parentNode.insertBefore(pendingCancel, inputText);\n"
        "  chat.scrollTop = chat.scrollHeight;\n"
        "  pendingCancel.addEventListener('click', function() {\n"
        "    if (turnSettled || !sendPending || generation !== sendGeneration) return;\n"
        "    turnSettled = true; stopProgress(); archiveCache.forget();\n"
        "    pendingResult('已取消本次发送，输入已保留。');\n"
        "  });", html)
    if count != 1:
        raise ValueError('quiet archive preparation notice mismatch')
    # Snapshot the per-send choice; a pending draft must not silently change policy.
    html = html.replace("var requestSettings = {provider: settings.provider, model: settings.model};",
                        "var requestSettings = {provider: settings.provider, model: settings.model, exclude: noMemoryEnabled};", 1)
    html = html.replace("if (noMemoryEnabled) { record.exclude = true; }",
                        "if (requestSettings ? requestSettings.exclude : noMemoryEnabled) { record.exclude = true; }", 1)
    html = html.replace("    if (revision !== inputRevision || inputText.value.trim() !== userText) {",
                        "    if (revision !== inputRevision || inputText.value.trim() !== userText || requestSettings.exclude !== noMemoryEnabled) {", 1)
    # An old cancelled preparation must not unlock a newer explicit send.
    html = html.replace("if (generation === sendGeneration) sendPending = false; pendingResult(",
                        "if (!turnSettled && generation === sendGeneration) sendPending = false; pendingResult(", 1)
    html = html.replace("  ensureDataReady(true).then(function(ready) {\n    stopProgress();",
                        "  ensureDataReady(true).then(function(ready) {\n    stopProgress();\n    if (turnSettled) return;", 1)
    html = html.replace("bannerRetry.hidden = p.phase !== 'failed';", "bannerRetry.hidden = p.phase !== 'failed' && !(introAccepted && p.phase === 'idle');", 1)
    html = html.replace("retry.hidden = p.phase !== 'failed';", "retry.hidden = p.phase !== 'failed' && !(introAccepted && p.phase === 'idle');", 1)
    return optimistic_archive_send(html)


def optimistic_archive_send(html: str) -> str:
    """Attach presentation synchronously; keep authority and successful effects gated."""
    start = html.index('function sendMessage(event) {')
    end = html.index('\n/* ===== ', start)
    send = html[start:end]
    send = send.replace('function sendMessage(event)', 'function sendMessage(event, retryBubble, retryText)', 1)
    send = send.replace("if (!inputText.value.trim()) return;", "if (!(retryBubble ? retryText : inputText.value.trim())) return;\n  var attempt = ++archiveSendAttempt;", 1)
    send = send.replace('var userText = inputText.value.trim();', 'var userText = retryBubble ? retryText : inputText.value.trim();', 1)
    send = send.replace('  if (streaming) {', "  if (streaming && event && (event.type === 'keydown' || event.detail > 1)) return;\n  if (streaming) {", 1)
    send = send.replace('return !turnSettled && generation === sendGeneration',
                        'return !turnSettled && attempt === archiveSendAttempt && generation === sendGeneration', 1)
    # Replace only the presentation/commit prelude; retrieval, streaming and voice
    # completion continue through the existing scoped code and archive wrapper.
    a = send.index('  function run() {')
    b = send.index('    var allRecords = collectAllRecords();', a)
    send = send[:a] + r"""  sendPending = true;
  removeStartPlaceholder();
  var pendingUser = retryBubble || addBubble({type:'user', text:userText});
  pendingUser.className = 'bubble user';
  pendingUser.textContent = userText;
  if (!retryBubble || (pendingUser._restoredDraftRevision === inputRevision && inputText.value.trim() === userText)) {
    var acceptedInputHeight = inputText.style.height;
    inputText.value = ''; lastInputValue = ''; autoGrow();
    inputText.style.height = acceptedInputHeight; // Keep the double-click target stable.
  }
  delete pendingUser._restoredDraftRevision;
  var subjectBubble = addBubble({type:'subject', text:''});
  var contentEl = subjectBubble.querySelector('.bubble-content');
  setTypingIndicator(contentEl);
  contentEl.setAttribute('aria-label', '等待回复');
  var pendingCancel = document.createElement('button');
  pendingCancel.type = 'button'; pendingCancel.className = 'archive-send-cancel';
  pendingCancel.textContent = '取消'; pendingCancel.setAttribute('aria-label', '取消本次发送');
  inputText.parentNode.insertBefore(pendingCancel, inputText);
  chat.scrollTop = chat.scrollHeight;
  var failed = false;
  function incomplete(code) {
    if (failed) return;
    failed = true; turnSettled = true;
    pendingCancel.remove(); subjectBubble.remove();
    pendingUser.classList.add('send-failed');
    var status = document.createElement('span');
    status.className = 'send-failure'; status.textContent = '未发送成功 [' + code + ']';
    if (/^LLM_UPSTREAM_FORBIDDEN(?: |$)/.test(code)) {
      status.textContent += '\n模型服务拒绝了这次请求（403），具体原因尚未确认，请联系维护者核查。';
    }
    pendingUser.appendChild(status);
    var retry = document.createElement('button');
    retry.type = 'button'; retry.textContent = '重试';
    retry.addEventListener('click', function(event) {
      if (streaming || sendPending || !pendingUser.isConnected) return;
      sendMessage(event, pendingUser, userText);
    });
    pendingUser.appendChild(retry);
    if (attempt === archiveSendAttempt && generation === sendGeneration) {
      sendPending = false; cancelActiveSend = null;
    }
    if (pendingUser.isConnected && revision === inputRevision && !inputText.value) {
      inputText.value = userText; lastInputValue = userText; autoGrow();
      pendingUser._restoredDraftRevision = inputRevision;
    }
  }
  cancelActiveSend = function() { incomplete('LLM_CANCELLED'); };
  pendingCancel.addEventListener('click', function() {
    if (!isCurrent()) return;
    incomplete('LLM_CANCELLED'); archiveCache.forget();
  });
  function run() {
    if (!isCurrent()) return;
    sendPending = false;
    pendingCancel.remove();
    autoGrow();
    if (!historyReplayed) {
      var displayed = document.createDocumentFragment();
      while (chat.firstChild) displayed.appendChild(chat.firstChild);
      maybeReplayHistory();
      chat.appendChild(displayed);
      removeStartPlaceholder();
    }
    ensureSessionStarted();
    sessionTurn += 1;
    var thisTurn = sessionTurn;

""" + send[b:]
    # A failed or cancelled request is never a successful user turn in logs.
    send = send.replace("      history.push({role: 'user'", "      logSession({role:'user', turn:thisTurn, text:userText}, requestSettings);\n      history.push({role: 'user'", 1)
    a = send.index('\n  sendPending = true;', send.index('    streamRequest(messages'))
    send = send[:a] + r"""
  ensureDataReady(true).then(function(ready) {
    if (turnSettled) return;
    if (!isCurrent() || requestSettings.exclude !== noMemoryEnabled) {
      incomplete('SEND_CHANGED'); return;
    }
    if (!ready) { incomplete('ARCHIVE_NOT_READY'); return; }
    checkArchiveSendProof(archiveSendProof);
    run();
  }).catch(function() {
    if (!turnSettled) incomplete('SEND_FAILED');
  });
}
"""
    html = html[:start] + 'var archiveSendAttempt = 0;\n' + send + html[end:]
    html = html.replace('function maybeReplayHistory() {', 'function maybeReplayHistory() {\n  if (sendPending) return;', 1)
    return html.replace('</style>', '\n.send-failure{display:block;font-size:12px;margin-top:6px;}\n#input-bar .archive-send-cancel{flex-shrink:0;width:48px;min-height:36px;background:#222244;color:#e0e0e0;border:1px solid #5566aa;border-radius:8px;font:inherit;font-size:14px;cursor:pointer;}\n#input-text{min-width:0;}\n</style>', 1)



def build(person: str, archive_dir: str, viewer: str, context_path: str = 'data/chat_context.json',
          sessions_path: str = '',
          out_name: str = 'companion.html', lang: str = 'mandarin',
          tts_origin: str = 'auto', tts_token: str = '',
          intro_card: bool = False, intro_builder: str = '家人',
          llm_proxy: str = '', offline_fallback: bool = False,
          default_key: str = '', default_provider: str = 'deepseek',
          relationship_scope: dict | None = None, voice_groups: bool = False, auto_voice_session: bool = False,
          archive_manifest_path: str = '', reset_ui_prefs: bool = False, hide_ready_banner: bool = False, app_release: str = '', openai_policy_path: str = '') -> str:
    """Render companion.html content."""
    if app_release and (viewer != 'father' or not archive_manifest_path or '__' in app_release or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}', app_release)):
        raise ValueError('app_release requires a scoped father archive page and a safe release label')
    if hide_ready_banner and (viewer != 'father' or not intro_card or not archive_manifest_path):
        raise ValueError('hide_ready_banner requires a father archive-cache page with intro card')
    if reset_ui_prefs and viewer != 'father':
        raise ValueError('page UI defaults are only supported for father')
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
            "    var diagnostic = newRequestDiagnostic();\n"
            "    if (diagnostic) pHeaders['X-Request-ID'] = diagnostic.request_id;\n"
            "    var pBody = { model: 'proxy', messages: messages, stream: true };\n"
            "    companionStream(pEndpoint, pHeaders, pBody, 'openai', requestController, onDelta, onDone, onError, diagnostic);\n"
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

    # The shared non-secret policy controls UI; proxy independently enforces it and credentials.
    if llm_proxy and viewer == 'father':
        enabled_models = load_policy(openai_policy_path)
        father_default_model = 'deepseek-v4-pro'
        llm_proxy_branch = llm_proxy_branch.replace("model: 'proxy'", "model: requestSettings.model, provider: requestSettings.provider")
        llm_proxy_hide_js += """(function(){
  var enabled = __FATHER_ENABLED_MODELS__;
  var defaultModel = __FATHER_DEFAULT_MODEL__;
  var select = document.createElement('select');
  select.id = 'father-model-choice';
  select.setAttribute('aria-label', '聊天模型');
  [['deepseek-v4-pro', 'DeepSeek Pro'], ['gpt-6-luna', 'gpt-6-luna'], ['gpt-6.1-terra', 'gpt-6.1-terra'], ['gpt-6.1-sol', 'gpt-6.1-sol']].forEach(function(item, index){
    var option = document.createElement('option'); option.value = item[0];
    var configured = enabled.indexOf(item[0]) !== -1;
    option.textContent = item[1] + (item[0] === defaultModel ? '（默认）' : '') + (index ? (configured ? '（已配置，账号未验证）' : '（未启用）') : '');
    option.disabled = index > 0 && !configured; select.appendChild(option);
  });
  select.value = defaultModel;
  var field = document.getElementById('cfg-model');
  if (field && field.parentNode) { field.parentNode.insertBefore(select, field); field.hidden = true; }
})();
"""

        llm_proxy_hide_js = llm_proxy_hide_js.replace('__FATHER_ENABLED_MODELS__', json.dumps(enabled_models))
        llm_proxy_hide_js = llm_proxy_hide_js.replace('__FATHER_DEFAULT_MODEL__', json.dumps(father_default_model))

    # Intro card content
    if intro_card:
        intro_css = _INTRO_CARD_CSS
        intro_html = _INTRO_CARD_HTML.replace('__INTRO_BUILDER__', intro_builder)
        if relationship_scope:
            intro_html = intro_html.replace(
                f'它知道的一切，来自{intro_builder}手机里的聊天记录，是{intro_builder}那一边的视角。',
                '当前资料来自您与她的夫妻私聊，只有已导出的部分（partial），不是完整一生。')
            intro_html = intro_html.replace(
                f'它可能会说出她当年对{intro_builder}讲的、关于您的话。',
                '没有来源的事它不能编造；人格摘要仍是待确认草案，争吵和矛盾也会保留。')
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
        '__VOICE_GROUPS__': 'true' if voice_groups else 'false',
        '__AUTO_VOICE_SESSION__': 'true' if auto_voice_session else 'false',
        '__EXPECTED_SCOPE__': 'JSON.parse(' + json.dumps(json.dumps(relationship_scope, ensure_ascii=False), ensure_ascii=False).replace('</', '<\\/') + ')',
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
    template = diagnostic_template(auto_voice_session, voice_groups)
    if archive_manifest_path:
        # Substitute application labels before interpolating any caller data.
        template = re.sub(r"data:audio/wav;base64,[^']*|D(?:14|6|5|4)\b",
                          lambda m: m.group(0) if m.group(0).startswith('data:') else (app_release or 'unlabeled'), template)
        template = template.replace('非本人 · ', '非本人 · 应用 ', 1)
    html = _PLACEHOLDER_RE.sub(lambda m: mapping.get(m.group(0), m.group(0)), template)
    if archive_manifest_path:
        if __package__:
            from .build_archive_cache_manifest import cache_scope
        else:
            from build_archive_cache_manifest import cache_scope
        scope = cache_scope(relationship_scope)
        if (viewer != 'father' or person != scope['person'] or
                archive_manifest_path != 'data/archive-cache-manifest.json' or
                not re.fullmatch(r'data/chat_context[A-Za-z0-9_.-]*\.json', context_path)):
            raise ValueError('archive cache requires a scoped father page and protected data paths')
        from pathlib import Path
        module_root = Path(__file__).resolve().parent
        cache_js = (module_root / 'companion_archive_cache.js').read_text(encoding='utf-8')
        integration = (module_root / 'companion_archive_cache_page.js').read_text(encoding='utf-8')
        integration = integration.replace('__APP_RELEASE__', app_release or 'unlabeled')
        local_validators = '\n'.join(re.search(r'^(?:async )?function ' + name + r'\([^\n]*\) \{.*?^\}', html, re.M | re.S).group()
                                     for name in ('checkScope', 'validateMemoryRelease'))
        integration = integration.replace('__CACHE_LOCAL_VALIDATORS__', local_validators)
        integration = integration.replace('__CACHE_OPTIONS__', json.dumps(dict(scope=scope,
            contextPath=context_path, manifestPath=archive_manifest_path), ensure_ascii=False).replace('</', '<\\/'))
        html = html.replace('/* ===== init ===== */', cache_js + '\n' + integration + '\n/* ===== init ===== */', 1)
        html = html.replace('  ensureDataReady().then(function(ready) {', '  ensureDataReady(true).then(function(ready) {', 1)
        html = guard_archive_transport(html)
        # Only the opted-in father page uses the live local authorization proof.
        html = html.replace('    if (pendingNotice.parentNode) pendingNotice.parentNode.removeChild(pendingNotice);',
                            '    checkArchiveSendProof(archiveSendProof);\n    if (pendingNotice.parentNode) pendingNotice.parentNode.removeChild(pendingNotice);', 1)
        html = html.replace("  var settled = false, reader = null, responseBody = null, acc = '', raw = '', buffer = '', frame = [];",
                            "  var dispatchProof = archiveSendProof;\n  var settled = false, reader = null, responseBody = null, acc = '', raw = '', buffer = '', frame = [];", 1)
        html = html.replace("    return fetch(endpoint, {method:'POST', headers:headers, body:JSON.stringify(body), signal:requestController.signal});",
                            "    checkArchiveSendProof(dispatchProof);\n    return fetch(endpoint, {method:'POST', headers:headers, body:JSON.stringify(body), signal:requestController.signal});", 1)
        html = html.replace('</style>', '\n#intro-card{align-items:flex-start;}#intro-card .ic-box{margin:auto;}\n.archive-cache-controls{font-size:16px;line-height:1.6;overflow-wrap:anywhere;margin:12px 0;}\n.archive-cache-controls button{margin:6px 0;min-height:44px;}\n#intro-card .archive-cache-controls,#intro-card .archive-cache-controls p,#intro-card .archive-cache-controls label,#intro-card #intro-progress{color:#3a3330;}\n</style>', 1)
    if hide_ready_banner:
        html = quiet_archive_preparation(html)
    if reset_ui_prefs:
        # Only this opt-in page keeps ordinary UI preferences in document memory.
        # Connection settings, archive revocation and session queues remain untouched.
        html = html.replace("var uiPrefsKey =", "var pageUiPrefs = {voiceText:true, autoVoiceEnabled:true};\nvar uiPrefsKey =", 1)
        html = re.sub(r"^function readUiPrefs\(\) \{.*?^\}",
                      "function readUiPrefs() {\n  return pageUiPrefs;\n}", html, count=1, flags=re.M | re.S)
        html = re.sub(r"^function saveUiPrefs\(\) \{.*?^\}",
                      "function saveUiPrefs() {\n  pageUiPrefs.voiceText = showVoiceText;\n  if (autoVoiceSession) pageUiPrefs.autoVoiceEnabled = autoVoiceSession.enabled;\n}",
                      html, count=1, flags=re.M | re.S)
        # Synchronize restored form controls once, before any asynchronous work.
        # BFCache/pageshow and later loads must preserve choices made in this document.
        html = html.replace("function init() {", "function init() {\n  if (cfgNoMemory) { cfgNoMemory.autocomplete = 'off'; cfgNoMemory.checked = noMemoryEnabled; }\n  window.addEventListener('pageshow', function() {\n    if (cfgNoMemory) cfgNoMemory.checked = noMemoryEnabled;\n    var banner = document.getElementById('no-memory-banner');\n    if (banner) banner.hidden = !noMemoryEnabled;\n    if (autoVoiceSession) autoVoiceSession.checkbox.checked = autoVoiceSession.enabled;\n    applyVoiceTextPref();\n  });", 1)
        html = html.replace('id="cfg-no-memory"', 'id="cfg-no-memory" autocomplete="off"', 1)
    if llm_proxy and viewer == 'father':
        html = html.replace('function ensureSessionStarted()', 'function ensureSessionStarted(requestSettings)', 1)
        html = html.replace('ensureSessionStarted();', 'ensureSessionStarted(requestSettings);')
        html = html.replace("text: 'session_start', ua: navigator.userAgent});", "text: 'session_start', ua: navigator.userAgent}, requestSettings);", 1)
        html = html.replace('startTurnPresentation(contentEl, finalText, thisTurn, emo)', 'startTurnPresentation(contentEl, finalText, thisTurn, emo, requestSettings)', 1)
        html = html.replace('function startTurnPresentation(contentEl, finalText, turnNo, emo)', 'function startTurnPresentation(contentEl, finalText, turnNo, emo, requestSettings)', 1)
        html = html.replace('  voiceTurn = vt;', '  vt.requestSettings = requestSettings;\n  voiceTurn = vt;', 1)
        html = html.replace("text:'tts_failed', detail:error.code || 'AUDIO_FETCH'});", "text:'tts_failed', detail:error.code || 'AUDIO_FETCH'}, vt.requestSettings);", 1)
        # Snapshot at click, before archive loading. Never reread the select during dispatch.
        html = html.replace("var requestSettings = {provider: settings.provider, model: settings.model",
                            "var clickedModel = (document.getElementById('father-model-choice') || {}).value || " + json.dumps(father_default_model) + ";\n  var requestSettings = {provider: clickedModel === 'deepseek-v4-pro' ? 'deepseek' : 'openai', model: clickedModel", 1)
        html = html.replace('function streamRequest(messages, onDelta, onDone, onError)',
                            'function streamRequest(messages, onDelta, onDone, onError, requestSettings)', 1)
        html = html.replace("    });\n  }\n\n  sendPending = true;", "    }, requestSettings);\n  }\n\n  sendPending = true;", 1)
        # Optimistic archive wrapper changes the prelude, not the stream callback end.
        html = html.replace("logSession({role:'event', turn: thisTurn, text:'llm_error', detail: code}, requestSettings);\n    });",
                            "logSession({role:'event', turn: thisTurn, text:'llm_error', detail: code}, requestSettings);\n    }, requestSettings);", 1)

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
    parser.add_argument('--openai-policy', default='', help='Same non-secret policy used by llm_proxy')
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
    parser.add_argument('--voice-groups', action='store_true', help='Group natural sentences for TTS')
    parser.add_argument('--auto-voice-session', action='store_true', help='Reuse foreground automatic voice player')
    parser.add_argument('--reset-ui-prefs', action='store_true', help='Father only: start ordinary UI preferences at defaults for each document')
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
                 llm_proxy=args.llm_proxy, openai_policy_path=args.openai_policy,
                 offline_fallback=args.offline_fallback, voice_groups=args.voice_groups, auto_voice_session=args.auto_voice_session, reset_ui_prefs=args.reset_ui_prefs,
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
