#!/usr/bin/env python3
"""Build avatar page for a person's digital archive."""

import argparse
import base64
import io
import json
import math
import os
import re
import sys
import time
from pathlib import Path

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
PLAYLIST_ID = "playlist"
FOOTER_NOTE = (
    "真实语音来自微信语音档案（Tier-2 可溯源）。"
    "卡通形象为示意，非真人形象。"
)

BUILD_TAG = time.strftime('%Y%m%d-%H%M%S')

# Default viseme map (Rhubarb phoneme shapes -> mouth patch state names)
DEFAULT_VISEME_MAP = {
    "X": "closed",
    "A": "closed",
    "B": "half",
    "C": "open",
    "D": "wide",
    "E": "round",
    "F": "round",
    "G": "half",
    "H": "half",
}
# Fallback chain for missing state names
STATE_FALLBACK = {"wide": "open", "round": "half", "pucker": "round"}
FINAL_FALLBACK = ["open", "half", "closed"]


def resolve_viseme_map(viseme_map, states):
    """Resolve viseme map values to valid state names or 'closed'.
    
    Returns (resolved_map, warn_count) where resolved_map is a dict of
    shape -> state_name (or "closed"), and warn_count is the number of
    fallback warnings emitted.
    """
    if not isinstance(viseme_map, dict):
        viseme_map = dict(DEFAULT_VISEME_MAP)
    
    resolved = {}
    warn_count = 0
    
    for shape, state in viseme_map.items():
        if not isinstance(state, str):
            resolved[shape] = "closed"
            continue
        if state == "closed" or state in states:
            resolved[shape] = state
            continue
        # Try fallback chain
        fallback_used = None
        for _ in range(3):
            if state in STATE_FALLBACK:
                state = STATE_FALLBACK[state]
                if state == "closed" or state in states:
                    resolved[shape] = state
                    break
            else:
                break
        else:
            state = None
        
        if state is None or (state != "closed" and state not in states):
            # Final fallback
            for candidate in FINAL_FALLBACK:
                if candidate in states:
                    resolved[shape] = candidate
                    break
            else:
                resolved[shape] = "closed"
            warn_count += 1
            if state is None:
                final_state = resolved[shape]
            else:
                final_state = resolved[shape]
            print("[WARN] viseme state '{}' missing, fallback to '{}'".format(
                viseme_map.get(shape, "?"), final_state
            ))
        else:
            resolved[shape] = state
    
    return resolved, warn_count


def resolve_rms_states(rms_states, states):
    """Resolve rms_states to valid state names or 'closed'.
    
    Returns list of two valid state names (or "closed" placeholders).
    """
    if not isinstance(rms_states, list) or len(rms_states) < 2:
        defaults = ["half", "open"]
        rms_states = [s if s in states else (s if s == "closed" else defaults[i]) 
                      for i, s in enumerate(defaults)]
    
    resolved = []
    for state in rms_states[:2]:
        if not isinstance(state, str):
            resolved.append("closed")
            continue
        if state == "closed" or state in states:
            resolved.append(state)
            continue
        # Try fallback chain
        orig = state
        fallback_used = None
        for _ in range(3):
            if state in STATE_FALLBACK:
                state = STATE_FALLBACK[state]
                if state == "closed" or state in states:
                    break
            else:
                break
        else:
            state = None
        
        if state is None or (state != "closed" and state not in states):
            for candidate in FINAL_FALLBACK:
                if candidate in states:
                    state = candidate
                    break
            else:
                state = "closed"
            print("[WARN] rms state '{}' missing, fallback to '{}'".format(orig, state))
        resolved.append(state)
    
    # Ensure exactly 2 entries
    while len(resolved) < 2:
        resolved.append("closed")
    
    return resolved


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>语音档案</title>
<style>
:root {
    --bg: #faf5ec;
    --card: #fffaf0;
    --text: #4a3523;
    --muted: #8a7159;
    --accent: #d97b3e;
    --accent-light: #f0c8a0;
    --border: #e0cbb0;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; }
body {
    background: var(--bg);
    color: var(--text);
    font-size: 16px;
    font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
    display: flex;
    flex-direction: column;
    min-height: 100vh;
}
main {
    flex: 1;
    width: 100%;
    max-width: 720px;
    margin: 0 auto;
    padding: 24px 16px 40px;
}
.avatar-wrap {
    display: flex;
    justify-content: center;
    margin-bottom: 12px;
}
.avatar {
    width: 280px;
    height: 280px;
    position: relative;
    animation: ambient 7s ease-in-out infinite;
    transform-origin: 50% 85%;
}
@keyframes ambient {
    0%, 100% { transform: rotate(-0.35deg) translateY(0); }
    50% { transform: rotate(0.35deg) translateY(-1.5px); }
}
@keyframes bob {
    0% { transform: translateY(0); }
    50% { transform: translateY(-2px); }
    100% { transform: translateY(0); }
}
.avatar.speaking .avatar-inner {
    animation: bob 1.2s ease-in-out infinite;
}
#eye-l, #eye-r {
    transform-origin: center center;
    transition: transform 0.08s ease;
}
/* Image-avatar styles */
.avatar-image {
    width: 100%;
    height: 100%;
    border-radius: 24px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.12);
    position: relative;
    overflow: hidden;
}
.avatar-image img {
    width: 100%;
    height: 100%;
    display: block;
    border-radius: inherit;
    object-fit: cover;
}
.avatar-image .frame-open {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    display: none;
}
.avatar-image.speaking-scale {
    transition: transform 0.1s ease;
}
/* Patch-avatar styles */
.avatar-image .mouth-patch {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    display: none;
    pointer-events: none;
}
.now-playing {
    text-align: center;
    margin-bottom: 16px;
    min-height: 40px;
}
.now-playing .title {
    font-size: 18px;
    font-weight: 600;
    margin-bottom: 4px;
}
.now-playing .sub {
    color: var(--muted);
    font-size: 14px;
}
.controls {
    display: flex;
    justify-content: center;
    gap: 12px;
    margin-bottom: 24px;
    flex-wrap: wrap;
}
.btn {
    min-width: 48px;
    min-height: 48px;
    padding: 8px 16px;
    font-size: 18px;
    border: 2px solid var(--border);
    border-radius: 24px;
    background: var(--card);
    color: var(--text);
    cursor: pointer;
    transition: background 0.2s, border-color 0.2s, transform 0.1s;
    touch-action: manipulation;
}
.btn:hover {
    background: var(--accent-light);
    border-color: var(--accent);
}
.btn:active {
    transform: scale(0.96);
}
.btn-play {
    min-width: 56px;
    border-radius: 28px;
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
}
.btn-play:hover {
    background: #c96a2c;
    border-color: #c96a2c;
}
.btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
}
.playlist {
    list-style: none;
    border-top: 1px solid var(--border);
}
.playlist li {
    min-height: 48px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 4px 12px;
    border-bottom: 1px solid var(--border);
    cursor: pointer;
    background: var(--card);
    transition: background 0.15s;
    touch-action: manipulation;
}
.playlist li:hover {
    background: var(--accent-light);
}
.playlist li.current {
    background: #fde8d0;
    border-left: 4px solid var(--accent);
    padding-left: 8px;
    font-weight: 600;
}
.playlist .idx {
    color: var(--muted);
    font-size: 14px;
    margin-right: 10px;
    min-width: 32px;
    text-align: right;
}
.playlist .name {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.playlist .dot {
    color: var(--accent);
    font-size: 14px;
    margin-left: 10px;
}
footer {
    padding: 12px 16px 20px;
    text-align: center;
    color: var(--muted);
    font-size: 13px;
    border-top: 1px solid var(--border);
    background: var(--card);
}
</style>
</head>
<body>
<main>
    <div class="avatar-wrap">
        __AVATAR_BLOCK__
    </div>

    <div class="now-playing" id="now-info">
        <div class="title" id="now-title">点击下方播放</div>
        <div class="sub" id="now-sub">共 <span id="total-count">0</span> 条语音</div>
    </div>

    <div class="controls">
        <button class="btn" id="btn-prev" aria-label="上一条" title="上一条">&#9664;</button>
        <button class="btn btn-play" id="btn-toggle" aria-label="播放/暂停" title="播放/暂停">&#9654;</button>
        <button class="btn" id="btn-next" aria-label="下一条" title="下一条">&#9654;&#9654;</button>
    </div>

    <audio id="player" preload="none"></audio>
    <ul class="playlist" id="playlist-ul"></ul>
</main>

<footer>__FOOTER__</footer>

<script type="application/json" id="playlist-data">
__PLAYLIST__
</script>

__VISEME_SCRIPT__

<script>
(function () {
'use strict';

// ---------- global error capture ----------
var jsErrors = [];
var BUILD_TAG = '__BUILD_TAG__';
window.onerror = function (message, source, lineno) {
    var errMsg = String(message) + ' @' + String(source) + ':' + String(lineno);
    jsErrors.push(errMsg);
    if (jsErrors.length > 10) jsErrors.shift();
    return false;
};

// ---------- parsing playlist ----------
var rawEl = document.getElementById('playlist-data');
var items = [];
try {
    var data = JSON.parse(rawEl.textContent);
    if (Array.isArray(data)) items = data;
} catch (e) {
    console.error('Failed to parse playlist', e);
}
var countEl = document.getElementById('total-count');
if (countEl) countEl.textContent = items.length;

// ---------- parse avatar config (patch mode config) ----------
var avatarConfig = null;
var visemeData = null;
var configEl = document.getElementById('avatar-config');
if (configEl) {
    try {
        avatarConfig = JSON.parse(configEl.textContent);
        if (!avatarConfig || typeof avatarConfig !== 'object' ||
            !avatarConfig.states || typeof avatarConfig.states !== 'object' ||
            Object.keys(avatarConfig.states).length === 0) {
            avatarConfig = null;
        }
    } catch (e) {
        avatarConfig = null;
    }
}
var visemeDataEl = document.getElementById('viseme-data');
if (visemeDataEl) {
    try {
        visemeData = JSON.parse(visemeDataEl.textContent);
    } catch (e) {
        visemeData = null;
    }
}

var listEl = document.getElementById('playlist-ul');
var audio = document.getElementById('player');
var avatar = document.getElementById('avatar');
var mouthStatic = document.getElementById('mouth-static');
var mouthSpeak = document.getElementById('mouth-speak');
var eyeL = document.getElementById('eye-l');
var eyeR = document.getElementById('eye-r');
var avatarImage = document.getElementById('avatar-image');
var frameClosed = document.getElementById('avatar-frame-closed');
var frameOpen = document.getElementById('avatar-frame-open');
var mouthHalf = document.getElementById('mouth-half');
var mouthOpen = document.getElementById('mouth-open');
var avatarBase = document.getElementById('avatar-base');
var hasImageMode = document.getElementById('avatar-frame-closed') !== null;
var hasOpenFrame = hasImageMode && document.getElementById('avatar-frame-open') !== null;
var hasPatchMode = avatarConfig !== null;

// patch-mode state images
var stateImgs = {};
var stateNames = [];
if (hasPatchMode) {
    stateNames = Object.keys(avatarConfig.states);
    for (var si = 0; si < stateNames.length; si++) {
        var sname = stateNames[si];
        var simg = document.getElementById('mouth-state-' + sname);
        if (simg) {
            stateImgs[sname] = simg;
        }
    }
}

// patch-mode config
var visemeMap = null;
var rmsStates = ['half', 'open'];
var blinkConfig = null;
if (hasPatchMode) {
    visemeMap = avatarConfig.visemeMap || {};
    if (avatarConfig.rmsStates && avatarConfig.rmsStates.length >= 2) {
        rmsStates = [avatarConfig.rmsStates[0], avatarConfig.rmsStates[1]];
    }
    blinkConfig = avatarConfig.blink || null;
}

// blink image
var blinkImg = null;
if (hasPatchMode && blinkConfig && blinkConfig.file) {
    blinkImg = document.getElementById('eyes-blink');
    if (blinkImg) {
        blinkImg._blinkActive = true;
    }
}

// current viseme timeline key
var currentVisemeKey = null;
var cueIdx = 0;
var hasTimeline = false;

// patch-mode error listeners
if (hasPatchMode) {
    if (avatarBase) {
        avatarBase.addEventListener('error', function () {
            avatarBase._hudError = true;
            var msg = 'avatar.png load error';
            jsErrors.push(msg);
            if (jsErrors.length > 10) jsErrors.shift();
        });
    }
    for (var si2 = 0; si2 < stateNames.length; si2++) {
        var sname2 = stateNames[si2];
        var simg2 = stateImgs[sname2];
        if (simg2) {
            simg2.addEventListener('error', (function (name, img) {
                return function () {
                    img._hudError = true;
                    var msg = name + ' load error';
                    jsErrors.push(msg);
                    if (jsErrors.length > 10) jsErrors.shift();
                };
            })(sname2, simg2));
        }
    }
    if (blinkImg) {
        blinkImg.addEventListener('error', function () {
            blinkImg._hudError = true;
            var msg = 'blink load error';
            jsErrors.push(msg);
            if (jsErrors.length > 10) jsErrors.shift();
        });
    }
} else if (hasImageMode) {
    // Legacy image-mode DOM detection
} else {
    // DOM scan recovery: attempt to recover patch states directly from the DOM
    // (handles both current and legacy markup when avatar-config is missing/invalid)
    var patchImgs = document.querySelectorAll('img.mouth-patch');
    var recovered = 0;
    for (var pi = 0; pi < patchImgs.length; pi++) {
        var pImg = patchImgs[pi];
        var pId = pImg.getAttribute('id') || '';
        var pName = null;
        if (pId.indexOf('mouth-state-') === 0) {
            pName = pId.substring('mouth-state-'.length);
        } else if (pId === 'mouth-half') {
            pName = 'half';
        } else if (pId === 'mouth-open') {
            pName = 'open';
        } else if (pId === 'eyes-blink') {
            continue; // skip blink overlay
        }
        if (pName && !stateImgs[pName]) {
            stateImgs[pName] = pImg;
            stateNames.push(pName);
            recovered++;
        }
    }
    if (recovered > 0) {
        hasPatchMode = true;
        console.info('avatar-config missing/invalid, recovered ' + String(recovered) + ' patch states from DOM');
        // Resolve RMS states: prefer ['half','open'] if both exist
        if (stateImgs['half'] && stateImgs['open']) {
            rmsStates = ['half', 'open'];
        } else if (stateNames.length >= 2) {
            rmsStates = [stateNames[0], stateNames[1]];
        } else if (stateNames.length === 1) {
            rmsStates = [stateNames[0], stateNames[0]];
        }
        // visemeMap stays null -> timeline branch won't activate, RMS fallback only (expected)
    }
    // Blink recovery: take over eyes-blink if present with default params
    if (hasPatchMode && !blinkImg) {
        var candidateBlink = document.getElementById('eyes-blink');
        if (candidateBlink) {
            blinkImg = candidateBlink;
            blinkImg._blinkActive = true;
            blinkConfig = {
                file: null,
                min_gap_ms: 2500,
                max_gap_ms: 5500,
                duration_ms: 130
            };
        }
    }
    // Attach error listeners for recovered states
    if (hasPatchMode) {
        if (avatarBase) {
            avatarBase.addEventListener('error', function () {
                avatarBase._hudError = true;
                var msg = 'avatar.png load error';
                jsErrors.push(msg);
                if (jsErrors.length > 10) jsErrors.shift();
            });
        }
        for (var ri = 0; ri < stateNames.length; ri++) {
            var rname = stateNames[ri];
            var rimg = stateImgs[rname];
            if (rimg) {
                rimg.addEventListener('error', (function (name, img) {
                    return function () {
                        img._hudError = true;
                        var msg = name + ' load error';
                        jsErrors.push(msg);
                        if (jsErrors.length > 10) jsErrors.shift();
                    };
                })(rname, rimg));
            }
        }
        if (blinkImg) {
            blinkImg.addEventListener('error', function () {
                blinkImg._hudError = true;
                var msg = 'blink load error';
                jsErrors.push(msg);
                if (jsErrors.length > 10) jsErrors.shift();
            });
        }
    }
}

var cur = -1;
var srcMode = 'real';
var rms = 0;
var fakePhase = 0;
var rmsWindow = [];
var zeroStart = null;

// ---------- mouth frame pure function ----------
var OPEN_THRESHOLD = 0.04;
var HALF_THRESHOLD = 0.02;
var FRAME_HOLD_MS = 90;
function mouthFrameFor(level, speaking, nowMs, state) {
    if (!speaking) {
        state.current = 'closed';
        state.lastSwitchMs = nowMs;
        return 'closed';
    }
    var frame;
    if (level > OPEN_THRESHOLD) {
        frame = 'open';
    } else if (level > HALF_THRESHOLD) {
        frame = 'half';
    } else {
        frame = 'closed';
    }
    if (state.current === frame) {
        return frame;
    }
    if (state.current === null) {
        state.current = frame;
        state.lastSwitchMs = nowMs;
        return frame;
    }
    if (nowMs - state.lastSwitchMs < FRAME_HOLD_MS) {
        return state.current;
    }
    state.current = frame;
    state.lastSwitchMs = nowMs;
    return frame;
}

// ---------- build list ----------
function el(tag, cls, text) {
    var d = document.createElement(tag);
    if (cls) d.className = cls;
    if (text !== undefined) d.textContent = text;
    return d;
}

items.forEach(function (item, i) {
    var li = el('li');
    var spanIdx = el('span', 'idx', String(i + 1));
    var name = item.display || ('#' + (i + 1));
    var spanName = el('span', 'name', name);
    var dot = el('span', 'dot', '\u25CF');
    li.appendChild(spanIdx);
    li.appendChild(spanName);
    li.appendChild(dot);
    li.addEventListener('click', function () {
        playAt(i);
    });
    listEl.appendChild(li);
});

function setCurrent(i) {
    var lis = listEl.querySelectorAll('li');
    for (var k = 0; k < lis.length; k++) {
        if (k === i) {
            lis[k].classList.add('current');
            if (lis[k].scrollIntoView) {
                lis[k].scrollIntoView({ block: 'nearest', behavior: 'smooth' });
            }
        } else {
            lis[k].classList.remove('current');
        }
    }
    cur = i;
}

function absUrl(u) {
    var a = document.createElement('a');
    a.href = u;
    return a.href;
}

/* 当前音源是否为本页播放列表里的条目。
   外部注入源一律返回 false：companion 页的 TTS（blob:）、iOS 音频解锁用的 8ms 静音（data:）。

   2026-09-10 事故：原判据是「排除 blob:」，属黑名单语义。companion 的 unlockAudio
   往本页 player 塞的是 data: URI 静音，8ms 播完即触发 ended → 漏过守卫 → playAt(0)，
   造成两个可见故障：①一开口先播一段无关的真实录音 ②playAt 顺带把 currentVisemeKey
   设成那条录音的时间轴，此后每段 TTS 都走时间轴分支，cue 用尽后嘴被钉死在 closed。
   改为白名单语义：只有确实来自播放列表的音源才允许续播/套用时间轴。 */
function isPlaylistSrc(src) {
    if (!src) return false;
    for (var pi = 0; pi < items.length; pi++) {
        var it = items[pi];
        if (!it || !it.src) continue;
        // 先做整串相等：预览页的播放列表条目本身就是 data:audio/mpeg;base64,… 内嵌音频，
        // 不能按前缀把 data: 一律当外部源排除（否则预览页失去续播与口型时间轴）。
        if (it.src === src) return true;
        // 只有相对/短路径才值得再解析成绝对 URL；内嵌 data: 已在上一行比过。
        if (it.src.length > 512) continue;
        if (absUrl(it.src) === src) return true;
    }
    return false;
}

function visemeKeyFromSrc(src) {
    if (!src) return null;
    var parts = String(src).split('/');
    var last = parts[parts.length - 1] || '';
    try {
        last = decodeURIComponent(last);
    } catch (e) {
        // keep as-is
    }
    return last;
}

function playAt(i) {
    if (i < 0 || i >= items.length) return;
    var item = items[i];
    if (audioCtx && audioCtx.state === 'suspended') {
        audioCtx.resume().catch(function (err) {
            console.info('AudioContext resume failed:', err);
            setFakeMode();
        });
    }
    // If we're already on this track, just resume playback
    if (cur === i && audio.src && !audio.paused) {
        return;
    }
    if (cur === i && audio.src && audio.paused) {
        audio.play().catch(function (err) {
            console.info('Audio play error, switching to fake:', err);
            setFakeMode();
        });
    } else {
        audio.src = item.src;
        audio.play().catch(function (err) {
            console.info('Audio play error, switching to fake:', err);
            setFakeMode();
        });
        setCurrent(i);
        updateInfo(i);
        // Update viseme timeline key
        currentVisemeKey = visemeKeyFromSrc(item.src);
        var vd = (visemeData && currentVisemeKey) ? visemeData[currentVisemeKey] : null;
        hasTimeline = !!(vd && vd.cues && vd.cues.length > 0);
        cueIdx = 0;
    }
}

function updateInfo(i) {
    var item = items[i];
    var title = document.getElementById('now-title');
    var sub = document.getElementById('now-sub');
    if (title && item) title.textContent = item.display;
    if (sub && item) sub.textContent = (item.date || '') + (item.duration ? ' \u00B7 ' + item.duration : '');
}

// ---------- controls ----------
document.getElementById('btn-prev').addEventListener('click', function () {
    if (items.length === 0) return;
    var to = (cur - 1 + items.length) % items.length;
    playAt(to);
});
document.getElementById('btn-toggle').addEventListener('click', function () {
    if (items.length === 0) return;
    if (audio.paused) {
        if (cur < 0) {
            playAt(0);
        } else {
            // Resume current track without resetting src
            audio.play().catch(function (err) {
                console.info('Audio play error, switching to fake:', err);
                setFakeMode();
            });
        }
    } else {
        audio.pause();
    }
});
document.getElementById('btn-next').addEventListener('click', function () {
    if (items.length === 0) return;
    var to = (cur + 1) % items.length;
    playAt(to);
});
audio.addEventListener('ended', function () {
    // 只有确实来自播放列表的音源才续播下一条。外部注入源（TTS 的 blob:、
    // iOS 解锁用的 data: 静音）一律不触发——否则她念完话会接着播训练用的真实语音。
    if (!isPlaylistSrc(audio.src)) return;
    if (items.length > 0) playAt((cur + 1) % items.length);
});
audio.addEventListener('loadstart', function () {
    // 外部注入源没有对应的 viseme 时间轴：复位 key，让口型回落到 RMS 分支。
    // 否则上一条播放列表条目的时间轴会被套用到 TTS 上，cue 用尽即嘴闭死。
    if (!isPlaylistSrc(audio.src)) {
        currentVisemeKey = null;
        cueIdx = 0;
    }
});
audio.addEventListener('pause', function () {
    document.getElementById('btn-toggle').innerHTML = '\u25B6';
    avatar.classList.remove('speaking');
    if (hasPatchMode) {
        for (var pn = 0; pn < stateNames.length; pn++) {
            var pimg = stateImgs[stateNames[pn]];
            if (pimg) pimg.style.display = 'none';
        }
        if (blinkImg && !blinkImg._blinkVisible) blinkImg.style.display = 'none';
        if (avatarBase) avatarBase.style.transform = '';
        for (var pn2 = 0; pn2 < stateNames.length; pn2++) {
            var pimg2 = stateImgs[stateNames[pn2]];
            if (pimg2) pimg2.style.transform = '';
        }
        if (blinkImg) blinkImg.style.transform = '';
        if (avatarImage) {
            avatarImage.classList.remove('patch-scale');
        }
    } else if (hasImageMode) {
        if (frameClosed) frameClosed.style.display = 'block';
        if (frameOpen) frameOpen.style.display = 'none';
        if (avatarImage) {
            avatarImage.classList.remove('speaking-scale');
        }
        if (frameClosed) frameClosed.style.transform = '';
        if (frameOpen) frameOpen.style.transform = '';
    } else {
        if (mouthStatic) mouthStatic.style.display = 'block';
        if (mouthSpeak) mouthSpeak.style.display = 'none';
    }
});
audio.addEventListener('play', function () {
    document.getElementById('btn-toggle').innerHTML = '\u23F8';
    avatar.classList.add('speaking');
    if (hasPatchMode) {
        if (avatarBase) avatarBase.style.transition = 'transform 0.08s ease';
        for (var pn3 = 0; pn3 < stateNames.length; pn3++) {
            var pimg3 = stateImgs[stateNames[pn3]];
            if (pimg3) pimg3.style.transition = 'transform 0.08s ease';
        }
        if (blinkImg) blinkImg.style.transition = 'transform 0.08s ease';
    } else if (hasImageMode) {
        if (avatarImage) {
            avatarImage.classList.add('speaking-scale');
            avatarImage.style.transition = 'transform 0.08s ease';
        }
    } else {
        if (mouthStatic) mouthStatic.style.display = 'none';
        if (mouthSpeak) mouthSpeak.style.display = 'block';
    }
});

// ---------- try real mode on play ----------
function tryRealMode() {
    if (analyser && srcMode === 'fake') {
        srcMode = 'real';
        zeroStart = null;
        console.info('Retrying real audio level mode');
    }
}
audio.addEventListener('play', tryRealMode);

// ---------- blink animation (SVG mode only) ----------
function blink() {
    if (!eyeL || !eyeR) return;
    var doBlink = function () {
        eyeL.style.transition = eyeR.style.transition = 'none';
        eyeL.style.transform = 'scaleY(0.1)';
        eyeR.style.transform = 'scaleY(0.1)';
        setTimeout(function () {
            eyeL.style.transition = eyeR.style.transition = 'transform 0.12s ease';
            eyeL.style.transform = 'scaleY(1)';
            eyeR.style.transform = 'scaleY(1)';
        }, 80);
    };
    doBlink();
    var next = 4000 + Math.random() * 2000;
    setTimeout(blink, next);
}
setTimeout(blink, 3500);

// ---------- patch-mode blink scheduler ----------
function schedulePatchBlink() {
    if (!blinkConfig || !blinkImg) return;
    var gap = blinkConfig.min_gap_ms + Math.random() * (blinkConfig.max_gap_ms - blinkConfig.min_gap_ms);
    setTimeout(function () {
        if (blinkImg) {
            blinkImg.style.display = 'block';
            blinkImg._blinkVisible = true;
        }
        setTimeout(function () {
            if (blinkImg) {
                blinkImg.style.display = 'none';
                blinkImg._blinkVisible = false;
            }
            schedulePatchBlink();
        }, blinkConfig.duration_ms);
    }, gap);
}
if (hasPatchMode && blinkImg) {
    schedulePatchBlink();
}

// ---------- audio analyser ----------
var AudioCtx = window.AudioContext || window.webkitAudioContext;
var audioCtx = null;
var analyser = null;

function initAudioCtx() {
    if (!AudioCtx) {
        console.info('Web Audio not supported, using fake mode');
        setFakeMode();
        return;
    }
    try {
        audioCtx = new AudioCtx();
        var source = audioCtx.createMediaElementSource(audio);
        analyser = audioCtx.createAnalyser();
        analyser.fftSize = 512;
        source.connect(analyser);
        analyser.connect(audioCtx.destination);
        console.info('Web Audio analyser ready');
    } catch (err) {
        console.info('AudioContext creation failed, using fake mode:', err);
        setFakeMode();
    }
}

function setFakeMode() {
    if (srcMode === 'fake') return;
    srcMode = 'fake';
    console.info('Fallback: fake mouth animation mode (no real audio level)');
    // Do NOT disconnect analyser or disturb WebAudio chain - just switch data source
}

// ---------- mouth state for frame hold ----------
var mouthState = { current: null, lastSwitchMs: 0 };

// ---------- debug HUD ----------
var hudEl = null;
var hudLastUpdate = 0;
var debugMode = false;
try {
    var hudQs = String(window.location.search || '').replace(/^\?/, '');
    if (('&' + hudQs + '&').indexOf('&debug=1&') !== -1) {
        debugMode = true;
    }
} catch (e) {
    debugMode = false;
}
if (debugMode) {
    hudEl = document.createElement('div');
    hudEl.id = 'hud-debug';
    hudEl.style.cssText = 'position:fixed; top:8px; left:8px; z-index:9999; background:rgba(0,0,0,0.75); color:#8f8; font:11px/1.5 monospace; padding:6px 9px; border-radius:6px; pointer-events:none; white-space:pre; text-align:left; max-width:92vw; overflow:hidden;';
    document.body.appendChild(hudEl);
}

function imgStatus(img, prefix) {
    if (!img) return prefix + '=none';
    var w = img.naturalWidth;
    if (w > 0) {
        return prefix + '=' + String(img.naturalWidth) + 'x' + String(img.naturalHeight);
    }
    if (img._hudError) {
        return prefix + '=ERR';
    }
    return prefix + '=pending';
}

function patchBaseStatus() {
    return imgStatus(avatarBase, 'base');
}
function patchStateStatus(name) {
    return imgStatus(stateImgs[name], name);
}
function patchBlinkStatus() {
    return imgStatus(blinkImg, 'blink');
}
function patchHalfStatus() {
    return imgStatus(mouthHalf, 'half');
}
function patchOpenStatus() {
    return imgStatus(mouthOpen, 'open');
}

// ---------- rAF loop ----------
function updateMouth() {
    var targetRy;
    var level = 0;
    var speaking = avatar.classList.contains('speaking');
    var now = Date.now();
    var hudFrame = '-';
    var driveSource = '';

    if (srcMode === 'real') {
        if (!analyser) {
            targetRy = 0;
            level = 0;
        } else {
            var buf = new Uint8Array(analyser.fftSize);
            analyser.getByteTimeDomainData(buf);
            var sum = 0;
            for (var i = 0; i < buf.length; i++) {
                var v = (buf[i] - 128) / 128;
                sum += v * v;
            }
            rms = Math.sqrt(sum / buf.length);
            level = rms;
            targetRy = 2 + Math.min(12, rms * 30);
            var playing = audio && audio.src && !audio.paused && !audio.ended;
            if (rms < 0.0001) {
                if (playing) {
                    if (zeroStart === null) zeroStart = Date.now();
                    else if (Date.now() - zeroStart > 600) setFakeMode();
                } else {
                    zeroStart = null;
                }
            } else {
                zeroStart = null;
            }
        }
    } else {
        fakePhase += 0.1 + Math.random() * 0.02;
        var osc = Math.sin(fakePhase * 2.0) * 0.5 + 0.5;
        var jitter = Math.random() * 0.4;
        targetRy = 4 + osc * 8 + jitter * 4;
        targetRy = Math.min(14, Math.max(2, targetRy));
        // Synthesize level for frame logic: continuous envelope through both thresholds
        level = (Math.sin(fakePhase * 2.0) * 0.5 + 0.5) * 0.08;
    }

    if (hasPatchMode) {
        // Patch mode: apply frames and scale to all imgs via container
        var patchState = 'closed';
        var useTimeline = false;
        if (speaking && hasTimeline && visemeMap && currentVisemeKey && visemeData && visemeData[currentVisemeKey]) {
            var vd = visemeData[currentVisemeKey];
            var cues = vd.cues;
            var t = audio.currentTime || 0;
            if (t < cues[0][0] || (cueIdx > 0 && t < cues[cueIdx][1])) {
                cueIdx = 0;
            }
            while (cueIdx < cues.length && t >= cues[cueIdx][1]) {
                cueIdx++;
            }
            if (cueIdx < cues.length) {
                var shape = cues[cueIdx][2];
                var mapped = visemeMap[shape];
                patchState = mapped || 'closed';
                useTimeline = true;
            } else {
                patchState = 'closed';
                useTimeline = true;
            }
        } else if (speaking) {
            // Volume fallback
            var rmsFrame = mouthFrameFor(level, speaking, now, mouthState);
            if (rmsFrame === 'open') {
                patchState = rmsStates[1] || 'closed';
            } else if (rmsFrame === 'half') {
                patchState = rmsStates[0] || 'closed';
            } else {
                patchState = 'closed';
            }
            useTimeline = false;
        } else {
            patchState = 'closed';
            mouthState.current = 'closed';
            mouthState.lastSwitchMs = now;
        }
        hudFrame = patchState;
        driveSource = useTimeline ? 'TL' : 'RMS';
        
        for (var pn4 = 0; pn4 < stateNames.length; pn4++) {
            var pimg4 = stateImgs[stateNames[pn4]];
            if (pimg4) {
                pimg4.style.display = (stateNames[pn4] === patchState) ? 'block' : 'none';
            }
        }
        // Subtle scale effect while speaking — apply to IMG elements to avoid
        // clobbering the bob animation's transform on the .avatar-inner container
        if (speaking) {
            var patchScale = 1 + Math.min(rms || level, 1) * 0.02;
            var patchScaleStr = 'scale(' + patchScale.toFixed(4) + ')';
            if (avatarBase) avatarBase.style.transform = patchScaleStr;
            for (var pn5 = 0; pn5 < stateNames.length; pn5++) {
                var pimg5 = stateImgs[stateNames[pn5]];
                if (pimg5) pimg5.style.transform = patchScaleStr;
            }
            if (blinkImg && blinkImg._blinkVisible) blinkImg.style.transform = patchScaleStr;
        } else {
            if (avatarBase) avatarBase.style.transform = '';
            for (var pn6 = 0; pn6 < stateNames.length; pn6++) {
                var pimg6 = stateImgs[stateNames[pn6]];
                if (pimg6) pimg6.style.transform = '';
            }
            if (blinkImg) blinkImg.style.transform = '';
        }
    } else if (hasImageMode) {
        // Image mode: frame swapping and scale effect
        var frame = mouthFrameFor(level, speaking, now, mouthState);
        hudFrame = frame;
        driveSource = 'RMS';
        if (hasOpenFrame) {
            if (frame === 'open') {
                if (frameClosed) frameClosed.style.display = 'none';
                if (frameOpen) frameOpen.style.display = 'block';
            } else {
                if (frameClosed) frameClosed.style.display = 'block';
                if (frameOpen) frameOpen.style.display = 'none';
            }
        }
        // Subtle scale effect while speaking — apply to IMG elements to avoid
        // clobbering the bob animation's transform on the .avatar-inner container
        if (speaking) {
            var scale = 1 + Math.min(rms || level, 1) * 0.02;
            var scaleStr = 'scale(' + scale.toFixed(4) + ')';
            if (frameClosed) frameClosed.style.transform = scaleStr;
            if (frameOpen) frameOpen.style.transform = scaleStr;
        } else {
            if (frameClosed) frameClosed.style.transform = '';
            if (frameOpen) frameOpen.style.transform = '';
        }
    }

    // SVG mode mouth
    if (mouthSpeak) {
        var curRy = parseFloat(mouthSpeak.getAttribute('ry')) || 4;
        var newRy = curRy * 0.6 + targetRy * 0.4;
        newRy = Math.min(14, Math.max(2, newRy));
        mouthSpeak.setAttribute('ry', String(newRy));
    }

    // ---------- HUD refresh (~200ms) ----------
    if (debugMode && hudEl && (now - hudLastUpdate >= 200)) {
        hudLastUpdate = now;
        var mode = 'svg';
        if (hasPatchMode) {
            mode = 'patch';
        } else if (hasImageMode) {
            mode = 'image';
        }
        var srcStr = srcMode;
        var ctxState = 'none';
        if (audioCtx) ctxState = audioCtx.state || 'unknown';
        var levelStr = level.toFixed(3);
        var spkStr = speaking ? 'true' : 'false';
        var audioPaused = audio ? audio.paused : true;
        var audioEnded = audio ? audio.ended : true;
        var curTime = audio ? (audio.currentTime || 0) : 0;
        var readyState = audio ? audio.readyState : -1;
        var netState = audio ? audio.networkState : -1;
        var imgLine = 'IMG -';
        if (hasPatchMode) {
            var parts = [];
            for (var psi = 0; psi < stateNames.length; psi++) {
                var ps = stateNames[psi];
                var pst = imgStatus(stateImgs[ps], ps);
                var pv = pst.split('=')[1] || '';
                parts.push(ps + '=' + pv);
            }
            var baseStatus = imgStatus(avatarBase, 'base');
            var baseVal = baseStatus.split('=')[1] || '';
            parts.unshift('base=' + baseVal);
            if (blinkImg) {
                var blinkStatus = patchBlinkStatus();
                var blinkVal = blinkStatus.split('=')[1] || '';
                parts.push('blink=' + blinkVal);
            }
            imgLine = 'IMG ' + parts.join(' ');
        }
        var visemesTotal = visemeData ? Object.keys(visemeData).length : 0;
        var tlFlag = hasTimeline ? '1' : '0';
        var modeLine = 'MODE ' + mode;
        if (hasPatchMode) {
            modeLine += ' TL=' + tlFlag + '/' + String(visemesTotal);
        }
        var frameLine = 'FRM ' + hudFrame;
        if (hasPatchMode) {
            frameLine += ' ' + driveSource;
        }
        var lines = [
            'BUILD ' + BUILD_TAG,
            modeLine,
            'SRC ' + srcStr + '  CTX ' + ctxState,
            'SPK ' + spkStr + '  LV ' + levelStr + '  ' + frameLine,
            'AUD paused=' + String(audioPaused) + ' ended=' + String(audioEnded) +
                ' t=' + curTime.toFixed(1) + ' rs=' + String(readyState) + ' ns=' + String(netState),
            imgLine
        ];
        lines.push('ERR ' + String(jsErrors.length));
        var startIdx = jsErrors.length - 3;
        if (startIdx < 0) startIdx = 0;
        for (var ei = startIdx; ei < jsErrors.length; ei++) {
            var eMsg = jsErrors[ei];
            if (eMsg.length > 80) eMsg = eMsg.substring(0, 80);
            lines.push(eMsg);
        }
        hudEl.textContent = lines.join('\n');
    }

    requestAnimationFrame(updateMouth);
}

// init
initAudioCtx();
requestAnimationFrame(updateMouth);

// delayed init if no user gesture
var firstInteraction = false;
document.addEventListener('click', function onceHandle() {
    firstInteraction = true;
    if (audioCtx && audioCtx.state === 'suspended') {
        audioCtx.resume().catch(function (err) {
            console.info('Resume failed:', err);
            setFakeMode();
        });
    }
    document.removeEventListener('click', onceHandle);
});
})();
</script>
</body>
</html>
"""

SVG_AVATAR_BLOCK = r"""        <div class="avatar" id="avatar">
            <div class="avatar-inner">
                <svg width="280" height="280" viewBox="0 0 280 280" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="卡通语音形象">
                    <ellipse cx="140" cy="150" rx="95" ry="100" fill="#f2d3a8" stroke="#8a5a2e" stroke-width="4"/>
                    <path d="M48 150 C48 85 80 50 140 50 C200 50 232 85 232 150 C232 170 228 185 224 195 C216 175 160 170 140 170 C120 170 64 175 56 195 C52 185 48 170 48 150 Z" fill="#7a4a2b" stroke="#5a3418" stroke-width="3"/>
                    <path d="M60 140 C70 110 95 90 140 88 C185 90 210 110 220 140 C228 118 220 80 195 62 C170 44 110 44 85 62 C60 80 52 118 60 140 Z" fill="#7a4a2b" stroke="none" opacity="0.7"/>
                    <ellipse cx="50" cy="148" rx="12" ry="18" fill="#f4d7ad" stroke="#8a5a2e" stroke-width="3"/>
                    <ellipse cx="230" cy="148" rx="12" ry="18" fill="#f4d7ad" stroke="#8a5a2e" stroke-width="3"/>
                    <circle id="eye-l" cx="112" cy="132" r="9" fill="#3b2a1d"/>
                    <circle id="eye-r" cx="168" cy="132" r="9" fill="#3b2a1d"/>
                    <ellipse cx="90" cy="158" rx="18" ry="12" fill="#e8a27c" opacity="0.6"/>
                    <ellipse cx="190" cy="158" rx="18" ry="12" fill="#e8a27c" opacity="0.6"/>
                    <path id="mouth-static" d="M118 168 Q140 184 162 168" fill="none" stroke="#8a2d1c" stroke-width="5" stroke-linecap="round"/>
                    <ellipse id="mouth-speak" cx="140" cy="174" rx="22" ry="4" fill="#8a2d1c" style="display:none"/>
                    <path d="M112 238 Q140 258 168 238 Q140 250 112 238 Z" fill="#f0c8a0" stroke="#8a5a2e" stroke-width="2"/>
                </svg>
            </div>
        </div>"""


def _file_version_tag(path: str) -> str:
    """Short content hash used as a cache-busting query param (?v=...)."""
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:8]


def image_avatar_block(has_open: bool, closed_v: str = "", open_v: str = "") -> str:
    """Generate the image-avatar HTML block."""
    open_img = ""
    if has_open:
        open_img = (
            '                <img id="avatar-frame-open" class="frame-open" '
            'src="data/avatar/avatar_open.png' + open_v + '" alt="" aria-hidden="true" '
            'style="display:none">\n'
        )
    return (
        '        <div class="avatar" id="avatar">\n'
        '            <div class="avatar-inner avatar-image" id="avatar-image" '
        'role="img" aria-label="卡通语音形象">\n'
        '                <img id="avatar-frame-closed" '
        'src="data/avatar/avatar.png' + closed_v + '" alt="">\n'
        + open_img +
        '            </div>\n'
        '        </div>'
    )


def patch_avatar_block(states, version_tags, blink_file=None, blink_version="", base_version="") -> str:
    """Generate the patch-avatar HTML block.
    
    states: dict of state_name -> filename
    version_tags: dict of state_name -> version query string
    blink_file: optional blink image filename
    blink_version: version query for blink image
    """
    lines = []
    lines.append('        <div class="avatar" id="avatar">')
    lines.append('            <div class="avatar-inner avatar-image" id="avatar-image" ')
    lines.append('role="img" aria-label="卡通语音形象">')
    lines.append('                <img id="avatar-base" src="data/avatar/avatar.png' + base_version + '" alt="">')
    for sname in states:
        version = version_tags.get(sname, "")
        lines.append('                <img id="mouth-state-' + sname + '" class="mouth-patch" '
                     'src="data/avatar/' + states[sname] + version + '" alt="" aria-hidden="true" '
                     'style="display:none">')
    if blink_file:
        lines.append('                <img id="eyes-blink" class="mouth-patch" '
                     'src="data/avatar/' + blink_file + blink_version + '" alt="" aria-hidden="true" '
                     'style="display:none">')
    lines.append('            </div>')
    lines.append('        </div>')
    return '\n'.join(lines)


def html_escape(s: str) -> str:
    """Escape & < > " ' for HTML text."""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def format_duration(seconds) -> str:
    if seconds is None:
        return ""
    total = int(seconds)
    h, r = divmod(total, 3600)
    m, s = divmod(r, 60)
    if h:
        return "{}:{}:{}".format(h, str(m).zfill(2), str(s).zfill(2))
    return "{}:{:02d}".format(m, s)


def build_playlist(media_index: dict) -> list:
    voice = media_index.get("voice") or []
    entries = []
    for i, item in enumerate(sorted(voice, key=lambda x: str(x.get("timestamp") or ""))):
        ap = item.get("archive_path") or item.get("path") or ""
        if ap.startswith("media/"):
            src = "data/" + ap
        elif ap.startswith("data/media/"):
            src = ap
        else:
            print("Error: archive_path must start with 'media/' or 'data/media/', got: {}".format(ap))
            sys.exit(1)
        ts = item.get("timestamp") or ""
        date = str(ts)[:10] if ts else ""
        dur_ms = item.get("duration_ms")
        dur = None
        if dur_ms is not None:
            dur = dur_ms / 1000.0
        else:
            dur = item.get("duration") or item.get("duration_sec") or None
        dur_str = format_duration(dur)
        display = date if date else "语音 {}".format(i + 1)
        if dur_str:
            display = "{} ({})".format(date if date else "语音 {}".format(i + 1), dur_str)
        entry = {
            "src": src,
            "timestamp": ts,
            "display": display,
            "date": date,
            "duration": dur_str,
        }
        entries.append(entry)
    def sort_key(e):
        return str(e.get("timestamp") or "")
    entries.sort(key=sort_key)
    for idx, e in enumerate(entries):
        if not e.get("date"):
            e["display"] = "语音 {}".format(idx + 1)
    return entries


def select_preview_clips(media_index: dict, n: int) -> list:
    """Select N clips for the preview page deterministically.
    
    Returns a list of (entry, archive_path) tuples.
    """
    voice = media_index.get("voice") or []
    
    # Candidate selection: is_subject True and 4000 <= duration_ms <= 15000
    candidates = []
    for item in voice:
        if not item.get("is_subject"):
            continue
        dur_ms = item.get("duration_ms")
        if dur_ms is None or not (4000 <= dur_ms <= 15000):
            continue
        candidates.append(item)
    
    # Sort by timestamp (string comparison for robustness)
    candidates.sort(key=lambda x: str(x.get("timestamp") or ""))
    
    if len(candidates) >= n:
        # Evenly spaced indices across the sorted list
        if n == 1:
            indices = [0]
        else:
            # Pick first, last, and evenly spaced points in between
            indices = [int(round(i * (len(candidates) - 1) / (n - 1))) for i in range(n)]
            # Ensure uniqueness
            indices = sorted(set(indices))
            # If deduplication reduced count, fill in evenly spaced unique ones
            if len(indices) < n:
                remaining = list(range(len(candidates)))
                for idx in indices:
                    remaining.remove(idx)
                step = len(remaining) / (n - len(indices))
                for i in range(n - len(indices)):
                    indices.append(remaining[min(len(remaining) - 1, int(i * step))])
                indices = sorted(set(indices))
        selected = [candidates[i] for i in indices]
    else:
        # Fallback: all is_subject entries sorted by |duration_ms - 8000|, take top N
        all_subject = [item for item in voice if item.get("is_subject")]
        all_subject.sort(key=lambda x: abs((x.get("duration_ms") or 0) - 8000))
        selected = all_subject[:n]
        if len(selected) < n:
            print("Warning: only {} preview clips available, requested {}".format(len(selected), n))
        # Re-sort selected by timestamp string to maintain chronological order
        selected.sort(key=lambda x: str(x.get("timestamp") or ""))
    
    # Ensure we have archive_path for each
    result = []
    for item in selected:
        ap = item.get("archive_path") or item.get("path") or ""
        result.append((item, ap))
    return result


def encode_mp3(wav_path: Path, bitrate: int) -> bytes:
    """Convert WAV to MP3 bytes using soundfile + lameenc + numpy."""
    try:
        import soundfile as sf
        import lameenc
        import numpy as np
    except ImportError as e:
        print("Error: preview mode requires soundfile, lameenc, and numpy.")
        print("Please run with a python that has these libs, e.g.:")
        print("  python tools/build_avatar_page.py --preview N")
        sys.exit(1)
    
    try:
        data, sr = sf.read(str(wav_path), dtype="float32", always_2d=True)
    except Exception as e:
        print("Error: failed to read WAV file {}: {}".format(wav_path, e))
        sys.exit(1)
    
    # Mix to mono
    if data.shape[1] > 1:
        mono = np.mean(data, axis=1)
    else:
        mono = data[:, 0]
    
    # Clip and convert to int16
    mono = np.clip(mono, -1.0, 1.0)
    pcm = (mono * 32767.0).astype(np.int16)
    
    # Encode MP3
    encoder = lameenc.Encoder()
    encoder.set_bit_rate(bitrate)
    encoder.set_in_sample_rate(sr)
    encoder.set_channels(1)
    encoder.set_quality(2)  # high quality
    
    mp3_bytes = encoder.encode(pcm.tobytes())
    mp3_bytes += encoder.flush()
    return mp3_bytes


def verify_mp3_bytes(mp3_bytes: bytes) -> bool:
    """Verify encoded MP3 is valid audio using soundfile read-back.
    
    Returns True if valid, False if decode failure or RMS <= 0.005 (near silence).
    """
    try:
        import soundfile as sf
    except ImportError:
        print("Error: soundfile not available for verification")
        return False
    
    import tempfile
    import numpy as np
    
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp.write(mp3_bytes)
        tmp_path = tmp.name
    
    try:
        data, _ = sf.read(tmp_path, dtype="float32")
        if len(data) == 0:
            return False
        rms = float(np.sqrt(np.mean(np.square(data))))
        ok = rms > 0.005
        if not ok:
            print("Warning: bad audio - RMS {:.6f} <= 0.005".format(rms))
        return ok
    except Exception as e:
        print("Error: failed to verify MP3: {}".format(e))
        return False
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def downsample_image_for_preview(path: Path, max_edge: int = 480) -> str:
    """Downscale image to max_edge px long edge, return base64 JPEG data URI."""
    try:
        from PIL import Image
    except ImportError:
        raise
    img = Image.open(str(path))
    img = img.convert("RGB")
    w, h = img.size
    long_edge = max(w, h)
    if long_edge > max_edge:
        ratio = max_edge / long_edge
        new_w = max(1, int(w * ratio))
        new_h = max(1, int(h * ratio))
        img = img.resize((new_w, new_h), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    data_uri = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    return data_uri


def build_preview_playlist(media_index: dict, archive_dir: Path, n: int, bitrate: int) -> list:
    """Build playlist for preview page with base64 data URIs."""
    import base64
    
    # Get all subject candidate items sorted deterministically by timestamp string
    voice = media_index.get("voice") or []
    subject_items = [item for item in voice if item.get("is_subject")]
    # Sort: first 4000-15000ms (by timestamp string), then rest (by timestamp string)
    good = [item for item in subject_items if (item.get("duration_ms") or 0) >= 4000 and (item.get("duration_ms") or 0) <= 15000]
    good.sort(key=lambda x: str(x.get("timestamp") or ""))
    rest = [item for item in subject_items if not ((item.get("duration_ms") or 0) >= 4000 and (item.get("duration_ms") or 0) <= 15000)]
    rest.sort(key=lambda x: str(x.get("timestamp") or ""))
    all_candidates = good + rest
    
    # Initial selection
    selected_pairs = select_preview_clips(media_index, n)
    used_aps = set()
    for _, ap in selected_pairs:
        if ap:
            used_aps.add(ap)
    
    playlist = []
    # For each selected candidate, attempt encode+verify; on failure, try next unused
    # Build a queue of candidates to try: first the selected ones, then the rest
    remaining_queue = []
    for item in all_candidates:
        ap = item.get("archive_path") or item.get("path") or ""
        if ap not in used_aps:
            remaining_queue.append(item)
    
    while len(playlist) < n and (selected_pairs or remaining_queue):
        # Take next candidate
        if selected_pairs:
            item, ap = selected_pairs.pop(0)
        else:
            item = remaining_queue.pop(0)
            ap = item.get("archive_path") or item.get("path") or ""
        
        if not ap:
            continue
        
        wav_path = archive_dir / "data" / ap
        if not wav_path.exists():
            print("Warning: WAV file not found, skipping: {}".format(wav_path))
            continue
        
        try:
            mp3_bytes = encode_mp3(wav_path, bitrate)
        except SystemExit:
            # Encode failure is hard error (encoding chain broken)
            raise
        
        if not verify_mp3_bytes(mp3_bytes):
            print("Warning: encoded MP3 failed verification for {}, trying next".format(ap))
            continue
        
        data_uri = "data:audio/mpeg;base64," + base64.b64encode(mp3_bytes).decode("ascii")
        
        ts = item.get("timestamp") or ""
        date = str(ts)[:10] if ts else ""
        dur_ms = item.get("duration_ms")
        dur = None
        if dur_ms is not None:
            dur = dur_ms / 1000.0
        dur_str = format_duration(dur)
        display = date if date else "语音 {}".format(len(playlist) + 1)
        if dur_str:
            display = "{} ({})".format(date if date else "语音 {}".format(len(playlist) + 1), dur_str)
        
        entry = {
            "src": data_uri,
            "timestamp": ts,
            "display": display,
            "date": date,
            "duration": dur_str,
        }
        playlist.append(entry)
        print("  preview clip {}: {}".format(len(playlist), ap))
        print("    duration: {:.1f}s".format((dur_ms or 0) / 1000.0))
    
    # Final chronological sort: reorder by timestamp string ascending
    playlist.sort(key=lambda e: str(e.get("timestamp") or ""))
    
    if len(playlist) < n:
        print("Warning: only {} of {} requested preview clips were successfully produced".format(
            len(playlist), n
        ))
    
    return playlist


def write_atomic(target: Path, content: str):
    tmp = target.with_suffix(target.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    os.replace(tmp, target)


def copy_binary(src: Path, dst: Path):
    """Binary-exact copy, create parent dirs, overwrite stale."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(src, "rb") as f_in:
        with open(dst, "wb") as f_out:
            f_out.write(f_in.read())


def load_emotion_assets(persona_dir: Path, avatar_dst_dir: Path) -> list:
    """
    将 persona 侧的情绪资产复制到 archive 侧，并返回需要加入 reconcile 白名单的文件名列表。

    persona 侧 emotions.json 中的 "file" 是裸文件名（如 "emo_happy.png"），
    archive 侧 emotions.json 中的 "file" 是带路径和版本号的 URL（如 "data/avatar/emo_happy.png?v=abc123"）。
    返回值是白名单文件名列表（含 "emotions.json" 和所有复制的图片裸文件名），供 reconcile_avatar_dir 使用。

    校验不通过或任何异常时不写任何文件，返回空列表；拷贝阶段中途失败可能留下部分文件，
    reconcile 会根据返回的空白名单将其清理。
    """
    src_json = persona_dir / "emotions.json"
    if not src_json.is_file():
        return []

    try:
        with open(src_json, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        print("[WARN] emotions.json ignored: 读取/解析失败: {}".format(e), file=sys.stderr)
        return []

    if not isinstance(cfg, dict):
        print("[WARN] emotions.json ignored: 顶层必须是 JSON 对象", file=sys.stderr)
        return []

    # 校验 neutral_delay_ms
    if "neutral_delay_ms" in cfg:
        ndm = cfg["neutral_delay_ms"]
        if not isinstance(ndm, int) or isinstance(ndm, bool) or ndm <= 0:
            print("[WARN] emotions.json ignored: neutral_delay_ms 必须是大于 0 的整数", file=sys.stderr)
            return []

    # 校验 emotions
    emotions = cfg.get("emotions")
    if not isinstance(emotions, dict) or not emotions:
        print("[WARN] emotions.json ignored: emotions 必须是非空对象", file=sys.stderr)
        return []

    key_re = re.compile(r'^[a-z0-9_]+$')
    files_to_copy = set()

    for key, val in emotions.items():
        if not isinstance(key, str) or not key or not key_re.match(key):
            print("[WARN] emotions.json ignored: 情绪键 '{}' 不符合 ^[a-z0-9_]+$ 或为空".format(key), file=sys.stderr)
            return []
        if not isinstance(val, dict):
            print("[WARN] emotions.json ignored: 情绪 '{}' 的值必须是对象".format(key), file=sys.stderr)
            return []

        fname = val.get("file")
        if not isinstance(fname, str) or not fname:
            print("[WARN] emotions.json ignored: 情绪 '{}' 缺少非空 file".format(key), file=sys.stderr)
            return []
        if Path(fname).name != fname or ".." in fname or "/" in fname or "\\" in fname:
            print("[WARN] emotions.json ignored: 情绪 '{}' 的 file '{}' 必须是裸文件名".format(key, fname), file=sys.stderr)
            return []
        if not fname.lower().endswith(".png"):
            print("[WARN] emotions.json ignored: 情绪 '{}' 的 file '{}' 必须以 .png 结尾".format(key, fname), file=sys.stderr)
            return []
        src_file = persona_dir / fname
        if not src_file.is_file():
            print("[WARN] emotions.json ignored: 情绪 '{}' 的 file '{}' 在 persona 侧不存在".format(key, fname), file=sys.stderr)
            return []

        if "keywords" in val:
            kw = val["keywords"]
            if not isinstance(kw, list) or not all(isinstance(x, str) and x for x in kw):
                print("[WARN] emotions.json ignored: 情绪 '{}' 的 keywords 必须是字符串列表".format(key), file=sys.stderr)
                return []

        files_to_copy.add(fname)

    # 所有校验通过，开始复制
    try:
        for fname in files_to_copy:
            copy_binary(persona_dir / fname, avatar_dst_dir / fname)
    except OSError as e:
        print("[WARN] emotions.json ignored: 复制文件失败: {}".format(e), file=sys.stderr)
        return []

    # 深拷贝并改写 file 字段
    try:
        cfg2 = json.loads(json.dumps(cfg))
        for key in cfg2["emotions"]:
            fname = cfg2["emotions"][key]["file"]
            dst_file = avatar_dst_dir / fname
            cfg2["emotions"][key]["file"] = "data/avatar/" + fname + "?v=" + _file_version_tag(str(dst_file))
        write_atomic(avatar_dst_dir / "emotions.json",
                     json.dumps(cfg2, ensure_ascii=False, indent=2) + "\n")
    except (json.JSONDecodeError, OSError, KeyError) as e:
        print("[WARN] emotions.json ignored: 写入 archive 侧失败: {}".format(e), file=sys.stderr)
        return []

    print("[EMOTION] {} emotions -> data/avatar/emotions.json".format(len(emotions)))
    return ["emotions.json"] + sorted(files_to_copy)


def reconcile_avatar_dir(archive_dir: Path, use_image_mode: bool, has_open_frame: bool, has_choice_json: bool, use_patch_mode: bool = False, patch_extra_files=None):
    """Reconcile archive_out/data/avatar against the desired asset set.
    
    image mode active: desired = avatar.png (+ avatar_open.png if has_open_frame)
    (+ avatar_choice.json if has_choice_json). Delete anything else.
    patch mode active: desired = avatar.png + mouth_half.png + mouth_open.png + mouth_patches.json
    + any extra patch files (blink etc).
    + emotion overlay assets (emotions.json + PNGs) when persona/emotions.json is valid (see load_emotion_assets).
    image mode inactive: delete the whole dir if it exists.
    """
    avatar_dir = archive_dir / "data" / "avatar"
    if not use_image_mode and not use_patch_mode:
        if avatar_dir.exists():
            for f in avatar_dir.iterdir():
                if f.is_file():
                    f.unlink()
            # Remove the (now empty) directory
            try:
                avatar_dir.rmdir()
            except OSError:
                pass
        return

    # mode active
    avatar_dir.mkdir(parents=True, exist_ok=True)
    if use_patch_mode:
        desired = {"avatar.png", "mouth_half.png", "mouth_open.png", "mouth_patches.json"}
        if patch_extra_files:
            for f in patch_extra_files:
                desired.add(f)
        # visemes.json is not managed by reconcile - whitelist it
        desired.add("visemes.json")
    else:
        desired = {"avatar.png"}
        if has_open_frame:
            desired.add("avatar_open.png")
        if has_choice_json:
            desired.add("avatar_choice.json")

    for f in avatar_dir.iterdir():
        if f.is_file() and f.name not in desired:
            f.unlink()


def generate_html(playlist: list, footer: str, avatar_block: str, viseme_script: str = "") -> str:
    playlist_json = json.dumps(playlist, ensure_ascii=False)
    playlist_json = playlist_json.replace("</", "<\\/")
    html = HTML_TEMPLATE.replace("__PLAYLIST__", playlist_json)
    html = html.replace("__FOOTER__", html_escape(footer))
    html = html.replace("__AVATAR_BLOCK__", avatar_block)
    html = html.replace("__VISEME_SCRIPT__", viseme_script)
    html = html.replace("__BUILD_TAG__", BUILD_TAG)
    return html


def load_visemes(archive_dir: Path) -> str:
    """Load visemes.json from archive_out/data/avatar and return script block."""
    visemes_path = archive_dir / "data" / "avatar" / "visemes.json"
    if not visemes_path.exists():
        return ""
    try:
        with open(visemes_path, "r", encoding="utf-8") as f:
            visemes = json.load(f)
        if not isinstance(visemes, dict):
            print("[WARN] visemes.json root not object, ignoring")
            return ""
        visemes_json = json.dumps(visemes, ensure_ascii=False, separators=(',', ':'))
        visemes_json = visemes_json.replace("</", "<\\/")
        return (
            '<script type="application/json" id="viseme-data">\n'
            + visemes_json +
            '\n</script>\n'
        )
    except (json.JSONDecodeError, OSError) as e:
        print("[WARN] Failed to load visemes.json: {}".format(e))
        return ""


def main():
    parser = argparse.ArgumentParser(description="Build avatar voice page")
    parser.add_argument("--person", required=True, help="person slug")
    parser.add_argument("--repo-root", default=None, help="repo root (default: parent of script)")
    parser.add_argument("--preview", type=int, default=0, help="generate preview page with N embedded clips (default: 0 = off)")
    parser.add_argument("--preview-bitrate", type=int, default=24, help="MP3 bitrate for preview clips, 16-64 kbps (default: 24)")
    parser.add_argument("--preview-max-mb", type=float, default=1.0, help="max size of preview HTML in MB (default: 1.0)")
    parser.add_argument("--no-avatar-image", action="store_true", help="force SVG mode even when avatar.png exists")
    args = parser.parse_args()

    slug = args.person
    if not SLUG_RE.match(slug):
        print("Error: invalid slug")
        sys.exit(1)

    if args.preview < 0:
        print("Error: --preview must be >= 0")
        sys.exit(1)
    
    if args.preview > 0:
        if args.preview_bitrate < 16 or args.preview_bitrate > 64:
            print("Error: --preview-bitrate must be between 16 and 64")
            sys.exit(1)
        if args.preview_max_mb <= 0:
            print("Error: --preview-max-mb must be positive")
            sys.exit(1)

    script_dir = Path(__file__).resolve().parent
    repo_root = Path(args.repo_root).resolve() if args.repo_root else script_dir.parent
    person_dir = (repo_root / "people" / slug).resolve()
    if person_dir.parent.name != "people" or person_dir.name != slug:
        print("Error: person directory must be under people/<slug>/")
        sys.exit(1)
    archive_dir = (person_dir / "archive_out").resolve()
    if archive_dir.parent != person_dir or archive_dir.name != "archive_out":
        print("Error: archive_out must be under people/<slug>/")
        sys.exit(1)

    media_index_path = archive_dir / "data" / "media_index.json"
    if not media_index_path.exists():
        print("Error: media_index.json not found - run build_data_bundle first")
        sys.exit(1)

    with open(media_index_path, "r", encoding="utf-8") as f:
        media_index = json.load(f)

    playlist = build_playlist(media_index)

    # Determine avatar mode: patch > image > svg
    persona_dir = (person_dir / "persona").resolve()
    avatar_png = persona_dir / "avatar.png"
    avatar_open_png = persona_dir / "avatar_open.png"
    avatar_choice_json = persona_dir / "avatar_choice.json"
    mouth_patches_json = persona_dir / "mouth_patches.json"

    use_patch_mode = False
    patch_config = None
    if not args.no_avatar_image and mouth_patches_json.exists():
        try:
            with open(mouth_patches_json, "r", encoding="utf-8") as f:
                patch_config = json.load(f)
            if not isinstance(patch_config, dict):
                raise ValueError("root not object")
            rect = patch_config.get("rect")
            img_size = patch_config.get("image_size")
            states = patch_config.get("states")
            if not isinstance(states, dict):
                raise ValueError("states not object")
            if len(states) == 0:
                raise ValueError("states empty")
            if (isinstance(rect, list) and len(rect) == 4 and
                isinstance(img_size, list) and len(img_size) == 2):
                # Validate all state files exist
                all_ok = True
                for sname, fname in states.items():
                    if not isinstance(fname, str):
                        all_ok = False
                        break
                    fpath = persona_dir / fname
                    if not fpath.exists():
                        all_ok = False
                        break
                if all_ok and avatar_png.exists():
                    use_patch_mode = True
                else:
                    print("[WARN] mouth_patches states validation failed")
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
    if not use_patch_mode and mouth_patches_json.exists():
        print("[WARN] mouth_patches invalid, fallback to image mode", file=sys.stderr)

    use_image_mode = False
    has_open_frame = False
    if not use_patch_mode and not args.no_avatar_image and avatar_png.exists():
        use_image_mode = True
        has_open_frame = avatar_open_png.exists()

    viseme_script = load_visemes(archive_dir)

    emotion_extra = []
    if use_patch_mode:
        # Resolve viseme map and rms states
        states = patch_config["states"]
        
        # Resolve viseme map
        viseme_map_raw = patch_config.get("viseme_map")
        viseme_map, warn_count = resolve_viseme_map(viseme_map_raw, states)
        if warn_count > 0:
            print("[WARN] {} viseme states required fallback resolution".format(warn_count))
        
        # Resolve rms states
        rms_states_raw = patch_config.get("rms_states")
        rms_states = resolve_rms_states(rms_states_raw, states)
        
        # Resolve blink config
        blink_config = None
        blink_file = None
        blink_raw = patch_config.get("blink")
        if isinstance(blink_raw, dict) and isinstance(blink_raw.get("file"), str):
            blink_path = persona_dir / blink_raw["file"]
            if blink_path.exists():
                blink_config = {
                    "file": blink_raw["file"],
                    "min_gap_ms": int(blink_raw.get("min_gap_ms", 2500)),
                    "max_gap_ms": int(blink_raw.get("max_gap_ms", 5500)),
                    "duration_ms": int(blink_raw.get("duration_ms", 130)),
                }
                blink_file = blink_raw["file"]
            else:
                print("[WARN] blink file '{}' not found in persona dir, ignoring blink".format(blink_raw["file"]))
        
        # Build avatar config JSON
        config_payload = {
            "states": dict(states),
            "visemeMap": viseme_map,
            "rmsStates": rms_states,
            "blink": blink_config,
        }
        config_json = json.dumps(config_payload, ensure_ascii=False, separators=(',', ':'))
        
        # Copy patch-mode assets into bundle
        avatar_dst_dir = archive_dir / "data" / "avatar"
        avatar_dst_dir.mkdir(parents=True, exist_ok=True)
        copy_binary(avatar_png, avatar_dst_dir / "avatar.png")
        
        # Copy state files (use original filenames)
        state_files = {}
        version_tags = {}
        for sname, fname in states.items():
            fpath = persona_dir / fname
            copy_binary(fpath, avatar_dst_dir / fname)
            state_files[sname] = fname
            version_tags[sname] = "?v=" + _file_version_tag(avatar_dst_dir / fname)
        
        # Copy blink file if present
        blink_version = ""
        if blink_file:
            blink_path = persona_dir / blink_file
            copy_binary(blink_path, avatar_dst_dir / blink_file)
            blink_version = "?v=" + _file_version_tag(avatar_dst_dir / blink_file)
        
        copy_binary(mouth_patches_json, avatar_dst_dir / "mouth_patches.json")
        emotion_extra = load_emotion_assets(persona_dir, avatar_dst_dir)
        
        # Build avatar block with all state imgs + blink
        base_v = "?v=" + _file_version_tag(avatar_dst_dir / "avatar.png")
        avatar_block = patch_avatar_block(state_files, version_tags, blink_file, blink_version, base_v)
        
        # Build avatar-config script block
        avatar_config_script = (
            '<script type="application/json" id="avatar-config">\n'
            + config_json +
            '\n</script>\n'
        )
        # Insert avatar-config after playlist-data script
        # Since HTML_TEMPLATE has __VISEME_SCRIPT__ placeholder before main script,
        # we combine avatar-config + viseme-data there
        viseme_script = avatar_config_script + viseme_script
        
        avatar_mode_label = "patch3"
    elif use_image_mode:
        # Copy assets into bundle
        avatar_dst_dir = archive_dir / "data" / "avatar"
        avatar_dst_dir.mkdir(parents=True, exist_ok=True)
        copy_binary(avatar_png, avatar_dst_dir / "avatar.png")
        avatar_mode_label = "image"
        if has_open_frame:
            copy_binary(avatar_open_png, avatar_dst_dir / "avatar_open.png")
            avatar_mode_label = "image+open"
        if avatar_choice_json.exists():
            copy_binary(avatar_choice_json, avatar_dst_dir / "avatar_choice.json")
        closed_v = "?v=" + _file_version_tag(avatar_dst_dir / "avatar.png")
        open_v = ""
        if has_open_frame:
            open_v = "?v=" + _file_version_tag(avatar_dst_dir / "avatar_open.png")
        avatar_block = image_avatar_block(has_open_frame, closed_v, open_v)
    else:
        avatar_block = SVG_AVATAR_BLOCK
        avatar_mode_label = "svg"

    # Reconcile stale assets in archive_out/data/avatar
    patch_extra = []
    if use_patch_mode:
        patch_extra.append("visemes.json")  # whitelist
        patch_extra.extend(emotion_extra)
        if blink_file:
            patch_extra.append(blink_file)
        for sname, fname in state_files.items():
            patch_extra.append(fname)
    
    reconcile_avatar_dir(
        archive_dir,
        use_image_mode,
        has_open_frame,
        avatar_choice_json.exists(),
        use_patch_mode,
        patch_extra,
    )

    html = generate_html(playlist, FOOTER_NOTE, avatar_block, viseme_script)
    html_path = archive_dir / "avatar.html"
    write_atomic(html_path, html)

    bat_content = (
        '@echo off\r\n'
        'cd /d "%~dp0"\r\n'
        'echo Starting server: http://localhost:8020/avatar.html\r\n'
        'python -m http.server 8020\r\n'
    )
    bat_path = archive_dir / "start_server.bat"
    write_atomic(bat_path, bat_content)

    sh_content = (
        '#!/bin/sh\n'
        'cd "$(dirname "$0")"\n'
        'echo "Starting server: http://localhost:8020/avatar.html"\n'
        'python -m http.server 8020\n'
    )
    sh_path = archive_dir / "start_server.sh"
    write_atomic(sh_path, sh_content)
    if os.name != "nt":
        try:
            os.chmod(sh_path, 0o755)
        except OSError:
            pass

    html_kb = len(html.encode("utf-8")) / 1024.0
    print("clips: {}".format(len(playlist)))
    print("HTML KB: {:.1f}".format(html_kb))
    print("wrote: {}".format(html_path))
    print("avatar={}".format(avatar_mode_label))

    # Preview page generation
    if args.preview > 0:
        print("Building preview page with {} clips...".format(args.preview))
        
        preview_playlist = build_preview_playlist(media_index, archive_dir, args.preview, args.preview_bitrate)
        
        actual_count = len(preview_playlist)
        footer_note = FOOTER_NOTE + " 手机预览版：内嵌 {} 条语音；完整版 {} 条请在电脑上打开 avatar.html".format(
            actual_count, len(playlist)
        )
        
        # Determine preview avatar block
        preview_avatar_block = avatar_block
        preview_used_image = use_image_mode or use_patch_mode
        if use_image_mode:
            try:
                closed_uri = downsample_image_for_preview(avatar_png, 480)
            except ImportError:
                print("note: Pillow unavailable, preview uses svg face")
                preview_avatar_block = SVG_AVATAR_BLOCK
                preview_used_image = False
            except Exception as e:
                print("note: failed to process avatar image ({}), preview uses svg face".format(e))
                preview_avatar_block = SVG_AVATAR_BLOCK
                preview_used_image = False
            else:
                open_uri = None
                if has_open_frame:
                    try:
                        open_uri = downsample_image_for_preview(avatar_open_png, 480)
                    except Exception:
                        open_uri = None
                # Build preview image block with embedded data URIs
                if open_uri:
                    preview_avatar_block = (
                        '        <div class="avatar" id="avatar">\n'
                        '            <div class="avatar-inner avatar-image" id="avatar-image" '
                        'role="img" aria-label="卡通语音形象">\n'
                        '                <img id="avatar-frame-closed" src="{}" alt="">\n'
                        '                <img id="avatar-frame-open" class="frame-open" '
                        'src="{}" alt="" aria-hidden="true" style="display:none">\n'
                        '            </div>\n'
                        '        </div>'
                    ).format(closed_uri, open_uri)
                else:
                    # Single-frame image (no open frame, or open failed)
                    preview_avatar_block = (
                        '        <div class="avatar" id="avatar">\n'
                        '            <div class="avatar-inner avatar-image" id="avatar-image" '
                        'role="img" aria-label="卡通语音形象">\n'
                        '                <img id="avatar-frame-closed" src="{}" alt="">\n'
                        '            </div>\n'
                        '        </div>'
                    ).format(closed_uri)
                    if has_open_frame:
                        print("note: open frame unavailable in preview, using single image")
        elif use_patch_mode:
            try:
                closed_uri = downsample_image_for_preview(avatar_png, 480)
            except ImportError:
                print("note: Pillow unavailable, preview uses svg face")
                preview_avatar_block = SVG_AVATAR_BLOCK
                preview_used_image = False
            except Exception as e:
                print("note: failed to process avatar image ({}), preview uses svg face".format(e))
                preview_avatar_block = SVG_AVATAR_BLOCK
                preview_used_image = False
            else:
                # Patch mode preview: use base image only
                preview_avatar_block = (
                    '        <div class="avatar" id="avatar">\n'
                    '            <div class="avatar-inner avatar-image" id="avatar-image" '
                    'role="img" aria-label="卡通语音形象">\n'
                    '                <img id="avatar-frame-closed" src="{}" alt="">\n'
                    '            </div>\n'
                    '        </div>'
                ).format(closed_uri)
        
        preview_html = generate_html(preview_playlist, footer_note, preview_avatar_block)
        preview_path = archive_dir / "avatar_preview.html"
        
        preview_size = len(preview_html.encode("utf-8"))
        max_bytes = int(args.preview_max_mb * 1024 * 1024)
        
        # Size-budget fallback chain: drop open frame, then fall back to SVG
        if preview_size > max_bytes and preview_used_image:
            # Try without open frame
            if has_open_frame and open_uri:
                print("note: preview too large, dropping open frame")
                pre_open_block = (
                    '        <div class="avatar" id="avatar">\n'
                    '            <div class="avatar-inner avatar-image" id="avatar-image" '
                    'role="img" aria-label="卡通语音形象">\n'
                    '                <img id="avatar-frame-closed" src="{}" alt="">\n'
                    '            </div>\n'
                    '        </div>'
                ).format(closed_uri)
                preview_html = generate_html(preview_playlist, footer_note, pre_open_block)
                preview_size = len(preview_html.encode("utf-8"))
            
            if preview_size > max_bytes:
                print("note: preview too large, falling back to svg face")
                preview_avatar_block = SVG_AVATAR_BLOCK
                preview_html = generate_html(preview_playlist, footer_note, preview_avatar_block)
                preview_size = len(preview_html.encode("utf-8"))
        
        if preview_size > max_bytes:
            print("Error: preview HTML size {:.2f} MB exceeds limit {:.2f} MB".format(
                preview_size / (1024 * 1024), args.preview_max_mb
            ))
            print("Try reducing --preview N or --preview-bitrate")
            sys.exit(1)
        
        write_atomic(preview_path, preview_html)
        
        print("preview clips: {}".format(actual_count))
        for i, (item, ap) in enumerate(select_preview_clips(media_index, args.preview)):
            dur_ms = item.get("duration_ms") or 0
            print("  {}: {} ({:.1f}s)".format(i + 1, ap, dur_ms / 1000.0))
        print("preview HTML MB: {:.2f}".format(preview_size / (1024 * 1024)))
        print("wrote: {}".format(preview_path))


if __name__ == "__main__":
    main()
