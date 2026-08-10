#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import base64
import hashlib
import io
import json
import os
import re
import sys
import tempfile

import numpy as np
import soundfile as sf
import lameenc


BAD_CHAR_RE = re.compile(r'\ufffd')
LATIN_RE = re.compile(r'[A-Za-z]{2,}')


def load_text(text_path):
    entries = []
    with open(text_path, 'r', encoding='utf-8') as f:
        for line_no, line in enumerate(f, 1):
            line = line.rstrip('\n')
            if not line.strip():
                continue
            parts = line.split(None, 1)
            if len(parts) != 2:
                raise ValueError(
                    'Bad text line %d: expected "utt_id<whitespace>text"' % line_no
                )
            utt, text = parts
            entries.append({'utt': utt, 'text': text})
    return entries


def load_wav_scp(wav_scp_path):
    wav_map = {}
    with open(wav_scp_path, 'r', encoding='utf-8') as f:
        for line_no, line in enumerate(f, 1):
            line = line.rstrip('\n')
            if not line.strip():
                continue
            parts = line.split(None, 1)
            if len(parts) != 2:
                raise ValueError(
                    'Bad wav.scp line %d: expected "utt_id<whitespace>path"' % line_no
                )
            utt, path = parts
            wav_map[utt] = path
    return wav_map


def encode_mp3(wav_path, bitrate=64):
    try:
        data, sr = sf.read(wav_path, dtype='float32', always_2d=False)
    except Exception as e:
        raise RuntimeError('Failed to read wav "%s": %s' % (wav_path, e))

    if data.ndim == 2:
        data = data.mean(axis=1)
    data = np.clip(data, -1.0, 1.0)
    pcm = (data * 32767.0).astype(np.int16)

    encoder = lameenc.Encoder()
    encoder.set_bit_rate(bitrate)
    encoder.set_in_sample_rate(sr)
    encoder.set_channels(1)
    encoder.set_quality(2)
    mp3_bytes = encoder.encode(pcm.tobytes())
    mp3_bytes += encoder.flush()

    # Verify by reading back
    try:
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp:
            tmp.write(mp3_bytes)
            tmp_path = tmp.name
        try:
            verify_data, _ = sf.read(tmp_path, dtype='float32')
        finally:
            os.unlink(tmp_path)
        rms = float(np.sqrt(np.mean(np.square(verify_data))))
    except Exception as e:
        raise RuntimeError('MP3 verification failed for "%s": %s' % (wav_path, e))

    if rms <= 0.005:
        raise RuntimeError(
            'MP3 RMS too low (%f) for "%s" - possibly silent or bad audio'
            % (rms, wav_path)
        )

    b64 = base64.b64encode(mp3_bytes).decode('ascii')
    return 'data:audio/mpeg;base64,' + b64


def format_date(utt_id):
    if len(utt_id) >= 8 and utt_id[:8].isdigit():
        d = utt_id[:8]
        return '%s-%s-%s' % (d[:4], d[4:6], d[6:8])
    return ''


def needs_review(text):
    return bool(BAD_CHAR_RE.search(text)) or bool(LATIN_RE.search(text))


def build_html(items, review_items, normal_items, total_count, review_count, only_flagged=False, page_id='', source_dataset='', source_total=0):
    # Compute dataset_id from ordered utt + '\0' + text concatenation
    dataset_str = '\0'.join(it['utt'] + '\0' + it['text'] for it in items)
    dataset_id = hashlib.md5(dataset_str.encode('utf-8')).hexdigest()[:12]

    data_for_js = []
    for it in items:
        data_for_js.append({
            'utt': it['utt'],
            'text': it['text'],
            'date': it.get('date', ''),
            'audio': it.get('audio', ''),
            'needsReview': it.get('needsReview', False),
            'index': it.get('index', 0),
        })

    json_payload = json.dumps(data_for_js, ensure_ascii=False).replace('</', '<\\/')

    # Escape page_id for safe JSON string embedding
    if page_id:
        page_id_escaped = json.dumps(page_id, ensure_ascii=False)[1:-1]
    else:
        page_id_escaped = ''

    source_total_str = str(int(source_total))

    # Determine whether to show normal section
    show_normal = not only_flagged
    normal_count = len(normal_items) if show_normal else 0
    review_count_render = len(review_items)

    html = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<title>上海话转写校对</title>
<style>
* { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; margin: 0; padding: 0 12px 120px; background: #f5f6fa; color: #222; }
#toolbar { position: sticky; top: 0; background: #2c3e50; color: #fff; padding: 10px 12px; display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; z-index: 99; box-shadow: 0 2px 8px rgba(0,0,0,0.2); margin: 0 -12px 16px; border-radius: 0 0 8px 8px; }
#toolbar h1 { font-size: 16px; margin: 0 12px 0 0; white-space: nowrap; }
#stats { font-size: 14px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.stat { background: rgba(255,255,255,0.15); padding: 4px 8px; border-radius: 4px; white-space: nowrap; }
.stat b { color: #ffeaa7; }
.btn { padding: 8px 16px; border: none; border-radius: 6px; font-size: 15px; font-weight: 600; cursor: pointer; background: #27ae60; color: #fff; margin: 2px; min-height: 44px; }
.btn.danger { background: #e74c3c; }
.btn.outline { background: transparent; border: 1px solid rgba(255,255,255,0.6); color: #fff; }
.btn:active { transform: scale(0.96); }
#bottom-bar { position: fixed; bottom: 0; left: 0; right: 0; background: #fff; padding: 10px 16px calc(10px + env(safe-area-inset-bottom)); box-shadow: 0 -2px 10px rgba(0,0,0,0.15); z-index: 98; }
#bottom-bar .btn { width: 100%; font-size: 17px; padding: 14px; }
.card { background: #fff; border-radius: 10px; padding: 14px; margin: 0 0 14px; box-shadow: 0 2px 6px rgba(0,0,0,0.08); border-left: 4px solid #bdc3c7; }
.card.review { border-left-color: #e74c3c; }
.card.dropped { opacity: 0.55; background: #fdf2f2; }
.card-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.card-index { font-size: 15px; font-weight: 700; color: #7f8c8d; margin-right: 8px; }
.card-date { font-size: 15px; font-weight: 600; color: #2c3e50; }
.utt-id { font-size: 11px; color: #95a5a6; word-break: break-all; flex: 1 1 100%; }
.tag { font-size: 11px; padding: 2px 8px; border-radius: 10px; color: #fff; font-weight: 700; }
.tag.review { background: #e74c3c; }
.tag.edited { background: #3498db; }
.tag.drop { background: #95a5a6; }
audio { width: 100%; margin: 8px 0 4px; min-height: 44px; }
.speed-control { display: flex; gap: 6px; margin: 4px 0; align-items: center; font-size: 13px; color: #666; }
.speed-btn { padding: 5px 10px; background: #ecf0f1; border: 1px solid #bdc3c7; border-radius: 4px; font-size: 13px; cursor: pointer; min-height: 44px; min-width: 44px; }
.speed-btn.active { background: #3498db; color: #fff; border-color: #3498db; }
textarea { width: 100%; font-size: 18px; line-height: 1.5; padding: 10px; border: 1px solid #dcdde1; border-radius: 6px; font-family: inherit; resize: none; min-height: 60px; overflow: hidden; }
textarea:focus { outline: 2px solid #3498db; border-color: #3498db; }
.drop-btn { display: flex; align-items: center; justify-content: center; width: 100%; min-height: 44px; margin-top: 8px; border: 2px solid #e74c3c; border-radius: 8px; background: transparent; color: #e74c3c; font-size: 15px; font-weight: 600; cursor: pointer; transition: all 0.15s; }
.drop-btn.dropped { background: #e74c3c; color: #fff; border-color: #e74c3c; }
.drop-btn:active { transform: scale(0.97); }
details summary { padding: 12px; background: #ecf0f1; border-radius: 8px; font-size: 15px; font-weight: 600; color: #2c3e50; cursor: pointer; margin: 8px 0 12px; min-height: 44px; display: flex; align-items: center; }
#overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.55); display: none; z-index: 100; justify-content: center; align-items: center; padding: 16px; }
#modal { background: #fff; border-radius: 10px; padding: 16px; width: 100%; max-width: 700px; max-height: 90vh; overflow-y: auto; }
#modal h2 { margin: 0 0 10px; font-size: 18px; }
#modal-note { font-size: 13px; color: #666; margin: 0 0 10px; padding: 8px; background: #f0f9ff; border-radius: 6px; border-left: 3px solid #3498db; }
#export-out { width: 100%; height: 260px; font-family: Consolas, monospace; font-size: 13px; border: 1px solid #dcdde1; border-radius: 6px; padding: 8px; white-space: pre; overflow: auto; }
.modal-buttons { display: flex; gap: 8px; margin-top: 12px; flex-wrap: wrap; }
.section-title { font-size: 16px; font-weight: 700; margin: 0 0 8px; padding: 6px 0; border-bottom: 2px solid #2c3e50; color: #2c3e50; }
</style>
</head>
<body>
<div id="toolbar">
  <h1>上海话转写校对</h1>
  <div id="stats">
    <span class="stat">总数: <b id="st-total">0</b></span>
    <span class="stat">需校对: <b id="st-review">0</b></span>
    <span class="stat">已改: <b id="st-edited">0</b></span>
    <span class="stat">已剔除: <b id="st-dropped">0</b></span>
    <button class="btn outline" onclick="clearAllDrafts()">清空草稿</button>
  </div>
</div>

<div id="review-section"><div class="section-title">需校对 (<span id="review-count"></span>)</div></div>
''' + ('''
<details id="normal-section">
  <summary>正常（可选校对，<span id="normal-count"></span> 条）</summary>
  <div id="normal-container"></div>
</details>
''' if show_normal else '') + '''

<div id="bottom-bar">
  <button class="btn" onclick="showExport()">✅ 完成校对 · 生成回贴码</button>
</div>

<div id="overlay">
  <div id="modal">
    <h2>回贴码（复制后粘贴回聊天即可）</h2>
    <div id="modal-note">没改过的条目会自动按"原转写正确"处理，不用逐条确认。</div>
    <textarea id="export-out" readonly></textarea>
    <div class="modal-buttons">
      <button class="btn" onclick="copyExport()">复制回贴码</button>
      <button class="btn" onclick="downloadExport()">下载 corrections.jsonl</button>
      <button class="btn danger" onclick="hideModal()">关闭</button>
    </div>
  </div>
</div>

<script type="application/json" id="init-data">__DATA__</script>
<script>
var ITEMS = JSON.parse(document.getElementById('init-data').textContent);
var storagePrefix = 'shanghai_tts_corr_''' + '__DATASET_ID__' + '''_';
var items = {};
var totals = { total: 0, review: 0, edited: 0, dropped: 0 };

function init() {
  ITEMS.forEach(function(it) {
    var obj = {
      utt: it.utt,
      text: it.text,
      original: it.text,
      date: it.date || '',
      audio: it.audio || '',
      needsReview: !!it.needsReview,
      index: it.index || 0,
      edited: false,
      dropped: false,
      el: null
    };
    items[obj.utt] = obj;
    restoreDraft(obj);
  });
  renderAll();
}

function restoreDraft(obj) {
  try {
    var keyText = storagePrefix + 'text_' + obj.utt;
    var saved = localStorage.getItem(keyText);
    if (saved !== null) {
      obj.text = saved;
      obj.edited = (saved !== obj.original);
    }
    var keyDrop = storagePrefix + 'drop_' + obj.utt;
    saved = localStorage.getItem(keyDrop);
    if (saved === '1') obj.dropped = true;
    else if (saved === '0') obj.dropped = false;
  } catch(e) {}
}

function saveText(obj) {
  try {
    localStorage.setItem(storagePrefix + 'text_' + obj.utt, obj.text);
  } catch(e) {}
}
function saveDrop(obj) {
  try {
    localStorage.setItem(storagePrefix + 'drop_' + obj.utt, obj.dropped ? '1' : '0');
  } catch(e) {}
}

function autoResize(textarea) {
  textarea.style.height = 'auto';
  textarea.style.height = (textarea.scrollHeight + 2) + 'px';
}

function onTextChange(obj, ta) {
  obj.text = ta.value;
  obj.edited = (ta.value !== obj.original);
  saveText(obj);
  var badge = obj.el.querySelector('.tag.edited');
  if (obj.edited && !badge) {
    var tb = document.createElement('span');
    tb.className = 'tag edited';
    tb.textContent = '已改';
    obj.el.querySelector('.card-header').appendChild(tb);
  } else if (!obj.edited && badge) {
    badge.remove();
  }
  updateTotals();
}

function onDropChange(obj, btn) {
  obj.dropped = !obj.dropped;
  saveDrop(obj);
  if (obj.dropped) obj.el.classList.add('dropped');
  else obj.el.classList.remove('dropped');
  var badge = obj.el.querySelector('.tag.drop');
  if (obj.dropped && !badge) {
    var tb = document.createElement('span');
    tb.className = 'tag drop';
    tb.textContent = '已剔除';
    obj.el.querySelector('.card-header').appendChild(tb);
  } else if (!obj.dropped && badge) {
    badge.remove();
  }
  btn.classList.toggle('dropped', obj.dropped);
  btn.textContent = obj.dropped ? '↩ 已剔除，点击恢复' : '🗑 剔除这条（不进训练集）';
  updateTotals();
}

function createCard(obj) {
  var card = document.createElement('div');
  card.className = 'card' + (obj.needsReview ? ' review' : '') + (obj.dropped ? ' dropped' : '');
  obj.el = card;

  var header = document.createElement('div');
  header.className = 'card-header';
  header.innerHTML = '<span class="card-index">#' + obj.index + '</span><span class="card-date">' + (obj.date || '') + '</span>';
  if (obj.needsReview) {
    var tagR = document.createElement('span');
    tagR.className = 'tag review';
    tagR.textContent = '需校对';
    header.appendChild(tagR);
  }
  if (obj.edited) {
    var tagE = document.createElement('span');
    tagE.className = 'tag edited';
    tagE.textContent = '已改';
    header.appendChild(tagE);
  }
  if (obj.dropped) {
    var tagD = document.createElement('span');
    tagD.className = 'tag drop';
    tagD.textContent = '已剔除';
    header.appendChild(tagD);
  }
  var uttId = document.createElement('div');
  uttId.className = 'utt-id';
  uttId.textContent = obj.utt;
  header.appendChild(uttId);
  card.appendChild(header);

  var audio = document.createElement('audio');
  audio.controls = true;
  audio.preload = 'none';
  audio.src = obj.audio;
  card.appendChild(audio);

  var speedDiv = document.createElement('div');
  speedDiv.className = 'speed-control';
  var lbl = document.createElement('span');
  lbl.textContent = '倍速:';
  speedDiv.appendChild(lbl);
  var btn07 = document.createElement('button');
  btn07.className = 'speed-btn';
  btn07.textContent = '0.7x';
  btn07.type = 'button';
  btn07.addEventListener('click', function() { audio.playbackRate = 0.7; setActive(btn07); });
  var btn1 = document.createElement('button');
  btn1.className = 'speed-btn active';
  btn1.textContent = '1.0x';
  btn1.type = 'button';
  btn1.addEventListener('click', function() { audio.playbackRate = 1.0; setActive(btn1); });
  speedDiv.appendChild(btn07);
  speedDiv.appendChild(btn1);
  card.appendChild(speedDiv);

  var ta = document.createElement('textarea');
  ta.value = obj.text;
  ta.spellcheck = false;
  card.appendChild(ta);
  autoResize(ta);
  ta.addEventListener('input', function() { onTextChange(obj, ta); autoResize(ta); });

  var dropBtn = document.createElement('button');
  dropBtn.type = 'button';
  dropBtn.className = 'drop-btn' + (obj.dropped ? ' dropped' : '');
  dropBtn.textContent = obj.dropped ? '↩ 已剔除，点击恢复' : '🗑 剔除这条（不进训练集）';
  dropBtn.addEventListener('click', function() { onDropChange(obj, dropBtn); });
  card.appendChild(dropBtn);

  return card;
}

function setActive(btn) {
  var container = btn.parentNode;
  var btns = container.querySelectorAll('.speed-btn');
  btns.forEach(function(b) { b.classList.remove('active'); });
  btn.classList.add('active');
}

function renderAll() {
  var reviewSection = document.getElementById('review-section');
  var normalContainer = document.getElementById('normal-container');
  reviewSection.innerHTML = '<div class="section-title">需校对 (<span id="review-count"></span>)</div>';
  if (normalContainer) normalContainer.innerHTML = '';

  var reviewArr = [];
  var normalArr = [];
  Object.keys(items).forEach(function(k) {
    var it = items[k];
    if (it.needsReview) reviewArr.push(it);
    else normalArr.push(it);
  });
  reviewArr.sort(function(a,b) { return a.index - b.index; });
  normalArr.sort(function(a,b) { return a.index - b.index; });

  reviewArr.forEach(function(it) {
    var c = createCard(it);
    reviewSection.appendChild(c);
  });
  if (normalContainer) {
    normalArr.forEach(function(it) {
      var c = createCard(it);
      normalContainer.appendChild(c);
    });
  }

  document.getElementById('review-count').textContent = reviewArr.length;
  if (document.getElementById('normal-count')) {
    document.getElementById('normal-count').textContent = normalArr.length;
  }
  if (document.getElementById('normal-section')) {
    document.getElementById('normal-section').open = false;
  }
  updateTotals();
}

function updateTotals() {
  var total = 0, review = 0, edited = 0, dropped = 0;
  Object.keys(items).forEach(function(k) {
    var it = items[k];
    total++;
    if (it.needsReview) review++;
    if (it.edited) edited++;
    if (it.dropped) dropped++;
  });
  totals = { total: total, review: review, edited: edited, dropped: dropped };
  document.getElementById('st-total').textContent = total;
  document.getElementById('st-review').textContent = review;
  document.getElementById('st-edited').textContent = edited;
  document.getElementById('st-dropped').textContent = dropped;
}

function clearAllDrafts() {
  if (!confirm('确定清空所有已保存的草稿吗？此操作无法撤销。')) return;
  Object.keys(items).forEach(function(k) {
    var it = items[k];
    try {
      localStorage.removeItem(storagePrefix + 'text_' + it.utt);
      localStorage.removeItem(storagePrefix + 'drop_' + it.utt);
    } catch(e) {}
    it.text = it.original;
    it.edited = false;
    it.dropped = false;
    if (it.el) {
      var ta = it.el.querySelector('textarea');
      if (ta) { ta.value = it.text; autoResize(ta); }
      var btn = it.el.querySelector('.drop-btn');
      if (btn) { btn.classList.remove('dropped'); btn.textContent = '🗑 剔除这条（不进训练集）'; }
      it.el.classList.remove('dropped');
    }
  });
  renderAll();
}

function buildExport() {
  var changed = [];
  var editedCount = 0;
  var droppedCount = 0;
  Object.keys(items).forEach(function(k) {
    var it = items[k];
    if (it.dropped) {
      droppedCount++;
      changed.push({ utt: it.utt, drop: true });
    } else if (it.edited) {
      editedCount++;
      changed.push({ utt: it.utt, text: it.text });
    }
  });
  var meta = {
    meta: 1,
    dataset: "''' + '__DATASET_ID__' + '''",
    page: "''' + '__PAGE_ID__' + '''",
    source_dataset: "''' + '__SOURCE_DATASET_ID__' + '''",
    source_total: ''' + '__SOURCE_TOTAL__' + ''',
    total: Object.keys(items).length,
    edited: editedCount,
    dropped: droppedCount
  };
  var lines = [JSON.stringify(meta)];
  if (changed.length === 0) {
    lines.push(JSON.stringify({ all_ok: true }));
  } else {
    changed.forEach(function(c) { lines.push(JSON.stringify(c)); });
  }
  return lines.join('\\n');
}

function showExport() {
  document.getElementById('export-out').value = buildExport();
  document.getElementById('overlay').style.display = 'flex';
}
function hideModal() {
  document.getElementById('overlay').style.display = 'none';
}

function copyExport() {
  var out = document.getElementById('export-out');
  var text = out.value;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(function() {
      alert('已复制！回到聊天窗口粘贴给 Claude 即可');
    }, function() {
      fallbackCopy(out);
    });
  } else {
    fallbackCopy(out);
  }
}
function fallbackCopy(ta) {
  ta.focus();
  ta.select();
  ta.setSelectionRange(0, ta.value.length);
  try {
    document.execCommand('copy');
    alert('已复制！回到聊天窗口粘贴给 Claude 即可');
  } catch(e) {
    alert('复制失败 - 请手动选择并复制。');
  }
}

function downloadExport() {
  var text = buildExport();
  var blob = new Blob([text], { type: 'application/jsonl;charset=utf-8' });
  var url = URL.createObjectURL(blob);
  var a = document.createElement('a');
  a.href = url;
  a.download = 'corrections.jsonl';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

init();
</script>
</body>
</html>
'''
    html = html.replace('__DATA__', json_payload)
    html = html.replace('__DATASET_ID__', dataset_id)
    html = html.replace('__PAGE_ID__', page_id_escaped)
    html = html.replace('__SOURCE_DATASET_ID__', source_dataset)
    html = html.replace('__SOURCE_TOTAL__', source_total_str)
    return html


def main():
    parser = argparse.ArgumentParser(description='Generate transcription correction HTML page')
    parser.add_argument('--text', required=True, help='Path to text file (Kaldi format)')
    parser.add_argument('--wav-scp', required=True, help='Path to wav.scp file')
    parser.add_argument('--out', required=True, help='Output HTML file path')
    parser.add_argument('--bitrate', type=int, default=64, help='MP3 bitrate (16-128, default 64)')
    parser.add_argument('--only-flagged', action='store_true', help='Only include items that need review')
    parser.add_argument('--limit', type=int, default=0, help='Only process first N review items (0=unlimited)')
    parser.add_argument('--page-id', default='', help='Page identifier, e.g. "1/2"')
    parser.add_argument('--source-text', default='', help='Path to full source text file (Kaldi format)')
    args = parser.parse_args()

    if args.bitrate < 16 or args.bitrate > 128:
        print('ERROR: --bitrate must be between 16 and 128')
        sys.exit(1)
    if args.limit < 0:
        print('ERROR: --limit must be >= 0')
        sys.exit(1)

    text_entries = load_text(args.text)
    wav_map = load_wav_scp(args.wav_scp)

    if not text_entries:
        print('ERROR: no entries in text file')
        sys.exit(1)

    # Compute source dataset hash and total if --source-text provided
    source_dataset = ''
    source_total = 0
    if args.source_text:
        source_entries = load_text(args.source_text)
        source_str = '\0'.join(e['utt'] + '\0' + e['text'] for e in source_entries)
        source_dataset = hashlib.md5(source_str.encode('utf-8')).hexdigest()[:12]
        source_total = len(source_entries)

    # Filter to review-only if requested
    if args.only_flagged:
        text_entries = [e for e in text_entries if needs_review(e['text'])]
        if not text_entries:
            print('ERROR: no flagged entries found')
            sys.exit(1)
        if args.limit > 0:
            text_entries = text_entries[:args.limit]
    elif args.limit > 0:
        # If limit is set without --only-flagged, apply to review items only
        review_entries = [e for e in text_entries if needs_review(e['text'])]
        normal_entries = [e for e in text_entries if not needs_review(e['text'])]
        text_entries = review_entries[:args.limit] + normal_entries

    items = []
    review_count = 0
    total = len(text_entries)

    for idx, entry in enumerate(text_entries, 1):
        utt = entry['utt']
        if utt not in wav_map:
            raise RuntimeError('WAV missing for utt "%s" (found in text but not in wav.scp)' % utt)
        wav_path = wav_map[utt]
        if not os.path.isfile(wav_path):
            raise RuntimeError('WAV file does not exist: %s (utt %s)' % (wav_path, utt))

        text = entry['text']
        is_review = needs_review(text)
        if is_review:
            review_count += 1

        print('Encoding [%d/%d] %s...' % (idx, total, utt))
        audio_b64 = encode_mp3(wav_path, args.bitrate)

        items.append({
            'utt': utt,
            'text': text,
            'date': format_date(utt),
            'audio': audio_b64,
            'needsReview': is_review,
            'index': idx,
        })

    review_items = [it for it in items if it['needsReview']]
    normal_items = [it for it in items if not it['needsReview']]

    html = build_html(items, review_items, normal_items, total, review_count, args.only_flagged, args.page_id, source_dataset, source_total)

    with open(args.out, 'w', encoding='utf-8') as f:
        f.write(html)

    size_mb = os.path.getsize(args.out) / (1024 * 1024)
    print('SUMMARY: total=%d review_required=%d html_size_mb=%.2f bitrate=%d only_flagged=%s' % (
        total, review_count, size_mb, args.bitrate, args.only_flagged))


if __name__ == '__main__':
    main()