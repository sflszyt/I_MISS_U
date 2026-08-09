#!/usr/bin/env python3
"""Build avatar page for a person's digital archive."""

import argparse
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
        <div class="avatar" id="avatar">
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
        </div>
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

<script>
(function () {
'use strict';

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

var listEl = document.getElementById('playlist-ul');
var audio = document.getElementById('player');
var avatar = document.getElementById('avatar');
var mouthStatic = document.getElementById('mouth-static');
var mouthSpeak = document.getElementById('mouth-speak');
var eyeL = document.getElementById('eye-l');
var eyeR = document.getElementById('eye-r');

var cur = -1;
var srcMode = 'real';
var rms = 0;
var fakePhase = 0;
var rmsWindow = [];
var zeroStart = null;

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
    if (items.length > 0) playAt((cur + 1) % items.length);
});
audio.addEventListener('pause', function () {
    document.getElementById('btn-toggle').innerHTML = '\u25B6';
    avatar.classList.remove('speaking');
    mouthStatic.style.display = '';
    mouthSpeak.style.display = 'none';
});
audio.addEventListener('play', function () {
    document.getElementById('btn-toggle').innerHTML = '\u23F8';
    avatar.classList.add('speaking');
    mouthStatic.style.display = 'none';
    mouthSpeak.style.display = '';
});

// ---------- blink animation ----------
function blink() {
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

// ---------- rAF loop ----------
function updateMouth() {
    var targetRy;
    if (srcMode === 'real') {
        if (!analyser) {
            targetRy = 0;
        } else {
            var buf = new Uint8Array(analyser.fftSize);
            analyser.getByteTimeDomainData(buf);
            var sum = 0;
            for (var i = 0; i < buf.length; i++) {
                var v = (buf[i] - 128) / 128;
                sum += v * v;
            }
            rms = Math.sqrt(sum / buf.length);
            targetRy = 2 + Math.min(12, rms * 30);
            if (rms < 0.0001) {
                if (zeroStart === null) zeroStart = Date.now();
                else if (Date.now() - zeroStart > 600) setFakeMode();
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
    }
    if (mouthSpeak) {
        var curRy = parseFloat(mouthSpeak.getAttribute('ry')) || 4;
        var newRy = curRy * 0.6 + targetRy * 0.4;
        newRy = Math.min(14, Math.max(2, newRy));
        mouthSpeak.setAttribute('ry', String(newRy));
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
    for i, item in enumerate(sorted(voice, key=lambda x: x.get("timestamp") or "")):
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
        t = e.get("timestamp") or ""
        if isinstance(t, (int, float)):
            return t
        return str(t)
    entries.sort(key=sort_key)
    for idx, e in enumerate(entries):
        if not e.get("date"):
            e["display"] = "语音 {}".format(idx + 1)
    return entries


def write_atomic(target: Path, content: str):
    tmp = target.with_suffix(target.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    os.replace(tmp, target)


def generate_html(playlist: list, footer: str) -> str:
    playlist_json = json.dumps(playlist, ensure_ascii=False)
    playlist_json = playlist_json.replace("</", "<\\/")
    html = HTML_TEMPLATE.replace("__PLAYLIST__", playlist_json)
    html = html.replace("__FOOTER__", html_escape(footer))
    return html


def main():
    parser = argparse.ArgumentParser(description="Build avatar voice page")
    parser.add_argument("--person", required=True, help="person slug")
    parser.add_argument("--repo-root", default=None, help="repo root (default: parent of script)")
    args = parser.parse_args()

    slug = args.person
    if not SLUG_RE.match(slug):
        print("Error: invalid slug")
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

    html = generate_html(playlist, FOOTER_NOTE)
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
        'cd "$(dirname "$0)"\n'
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


if __name__ == "__main__":
    main()