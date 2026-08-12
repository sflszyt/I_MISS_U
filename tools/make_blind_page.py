#!/usr/bin/env python3
"""Build a self-contained mobile blind-listening test page."""

import argparse
import base64
import hashlib
import io
import json
import os
import random
import sys


def parse_args(argv):
    p = argparse.ArgumentParser(description="Build blind listening test page")
    p.add_argument("--synth-dir", required=True, help="dir with synthesized wavs")
    p.add_argument("--real", nargs="+", required=True, help="real wavs")
    p.add_argument("--out", required=True, help="output html path")
    p.add_argument("--key-out", default=None, help="output key json path")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--bitrate", type=int, default=32, help="mp3 bitrate kbps")
    p.add_argument("--max-mb", type=float, default=1.0, help="max html size MB")
    p.add_argument("--title", default="盲听测试")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])

    try:
        import soundfile as sf
        import lameenc
    except ImportError:
        print("ERROR: missing dependency: soundfile and lameenc are required", file=sys.stderr)
        return 2

    if not os.path.isdir(args.synth_dir):
        print("ERROR: --synth-dir not a dir: %s" % args.synth_dir, file=sys.stderr)
        return 2
    synth_wavs = sorted(
        f for f in os.listdir(args.synth_dir)
        if f.lower().endswith(".wav")
    )
    if not synth_wavs:
        print("ERROR: no wav files in --synth-dir", file=sys.stderr)
        return 2
    for r in args.real:
        if not os.path.isfile(r):
            print("ERROR: real wav not found: %s" % r, file=sys.stderr)
            return 2

    clips = []
    for f in synth_wavs:
        full = os.path.join(args.synth_dir, f)
        clips.append({
            "source": "synth",
            "orig": os.path.splitext(f)[0],
            "file": os.path.abspath(full),
        })
    for r in args.real:
        clips.append({
            "source": "real",
            "orig": os.path.splitext(os.path.basename(r))[0],
            "file": os.path.abspath(r),
        })

    rng = random.Random(args.seed)
    rng.shuffle(clips)

    for i, c in enumerate(clips, 1):
        c["id"] = "c%02d" % i

    # encode
    try:
        import numpy as np
    except ImportError:
        print("ERROR: numpy required", file=sys.stderr)
        return 2

    decode_verify_note = False
    for c in clips:
        try:
            data, rate = sf.read(c["file"], dtype="float32", always_2d=True)
            mono = np.mean(data, axis=1) if data.shape[1] > 1 else data[:, 0]
            mono = np.clip(mono, -1.0, 1.0)
            
            # Record source duration and RMS for verification
            source_duration = len(mono) / rate
            source_rms = float(np.sqrt(np.mean(mono ** 2)))
            
            # Encode with int16 PCM (the proven pattern)
            pcm16 = (mono * 32767.0).astype(np.int16)
            try:
                enc = lameenc.Encoder()
                enc.set_bit_rate(args.bitrate)
                enc.set_in_sample_rate(int(rate))
                enc.set_channels(1)
                enc.set_quality(2)
                mp3 = bytes(enc.encode(pcm16.tobytes())) + bytes(enc.flush())
            except Exception:
                # resample to 16000 via linear interpolation (float mono, before int16)
                new_rate = 16000
                n = int(len(mono) * new_rate / rate)
                x_old = np.linspace(0, 1, len(mono), endpoint=False)
                x_new = np.linspace(0, 1, n, endpoint=False)
                mono_resampled = np.interp(x_new, x_old, mono).astype("float32")
                data, rate = mono_resampled, new_rate
                source_duration = len(data) / rate
                source_rms = float(np.sqrt(np.mean(data ** 2)))
                pcm16 = (data * 32767.0).astype(np.int16)
                enc = lameenc.Encoder()
                enc.set_bit_rate(args.bitrate)
                enc.set_in_sample_rate(int(rate))
                enc.set_channels(1)
                enc.set_quality(2)
                mp3 = bytes(enc.encode(pcm16.tobytes())) + bytes(enc.flush())

            # Verify encoded MP3
            expected_bytes = args.bitrate * 1000 / 8 * source_duration
            if len(mp3) < 0.5 * expected_bytes or len(mp3) > 2.0 * expected_bytes:
                print("ERROR: clip %s failed size verification (expected ~%.0f bytes, got %d)" % (
                    c["id"], expected_bytes, len(mp3)), file=sys.stderr)
                return 2
            
            # Try decoding MP3 back for deeper verification
            try:
                dec_data, dec_rate = sf.read(io.BytesIO(mp3))
                dec_duration = len(dec_data) / dec_rate if dec_rate > 0 else 0
                dec_rms = float(np.sqrt(np.mean(np.asarray(dec_data, dtype=np.float64) ** 2)))
                if abs(dec_duration - source_duration) / source_duration > 0.10:
                    print("ERROR: clip %s duration mismatch: source=%.2fs decoded=%.2fs" % (
                        c["id"], source_duration, dec_duration), file=sys.stderr)
                    return 2
                if dec_rms < 0.25 * source_rms:
                    print("ERROR: clip %s RMS too low: source=%.4f decoded=%.4f (silent/empty encode)" % (
                        c["id"], source_rms, dec_rms), file=sys.stderr)
                    return 2
            except Exception:
                if not decode_verify_note:
                    print("note: mp3 decode-verify unavailable", file=sys.stderr)
                    decode_verify_note = True

            c["b64"] = base64.b64encode(mp3).decode("ascii")
        except Exception as e:
            print("ERROR: processing clip %s failed: %s" % (c["id"], str(e)[:200]), file=sys.stderr)
            return 2

    # html size check
    html_size = sum(len(c["b64"]) for c in clips) * 1.34 + 20000  # approx base64 + page overhead
    html_mb = html_size / (1024 * 1024)
    if html_mb > args.max_mb:
        print("ERROR: page %.2f MB exceeds --max-mb %.2f" % (html_mb, args.max_mb), file=sys.stderr)
        return 2

    # key json
    pair_blob = "".join("%s:%s;" % (c["id"], c["orig"]) for c in clips)
    dataset = hashlib.md5(pair_blob.encode("utf-8")).hexdigest()[:12]
    key_data = {
        "seed": args.seed,
        "dataset": dataset,
        "clips": [
            {"id": c["id"], "source": c["source"], "orig": c["orig"], "file": c["file"]}
            for c in clips
        ],
    }
    key_out = args.key_out or (os.path.splitext(args.out)[0] + ".key.json")
    try:
        with open(key_out, "w", encoding="utf-8") as f:
            json.dump(key_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("ERROR: failed to write key file %s: %s" % (key_out, str(e)[:200]), file=sys.stderr)
        return 2

    # build html
    total = len(clips)
    cards_html = []
    for c in clips:
        card = r"""
<div class="card" data-id="__ID__">
  <div class="play-row">
    <button class="play-btn">▶ 播放</button>
    <audio src="data:audio/mpeg;base64,__B64__"></audio>
  </div>
  <div class="q"><div class="q-label">A. 这段是真人录音还是合成？</div>
    <div class="toggle-group" data-q="guess">
      <button data-val="real">真人</button><button data-val="synth">合成</button>
    </div>
  </div>
  <div class="q"><div class="q-label">B. 听起来像她本人吗？</div>
    <div class="score-group" data-q="score">
      <button data-val="1">1</button><button data-val="2">2</button><button data-val="3">3</button><button data-val="4">4</button><button data-val="5">5</button>
    </div>
    <div class="score-hint">1=完全不像, 5=就是她</div>
  </div>
</div>
"""
        card = card.replace("__ID__", c["id"]).replace("__B64__", c["b64"])
        cards_html.append(card)

    html = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; background: #f5f6fa; color: #2c3e50; padding-bottom: 80px; }
.header { background: #34495e; color: #fff; padding: 20px 16px; }
.header h1 { font-size: 22px; margin-bottom: 8px; }
.header p { font-size: 14px; opacity: .9; line-height: 1.5; }
.progress { position: sticky; top: 0; background: #2c3e50; color: #fff; text-align: center; padding: 8px; font-size: 14px; z-index: 10; box-shadow: 0 2px 4px rgba(0,0,0,.2); }
.cards { padding: 16px; max-width: 700px; margin: 0 auto; }
.card { background: #fff; border-radius: 12px; padding: 16px; margin-bottom: 16px; box-shadow: 0 2px 8px rgba(0,0,0,.08); }
.play-row { display: flex; align-items: center; margin-bottom: 12px; }
.play-btn { min-width: 48px; min-height: 48px; font-size: 18px; background: #3498db; color: #fff; border: none; border-radius: 8px; cursor: pointer; padding: 8px 16px; }
.play-btn.playing { background: #e74c3c; }
.q { margin-bottom: 12px; }
.q-label { font-size: 14px; font-weight: 600; margin-bottom: 8px; }
.toggle-group, .score-group { display: flex; gap: 8px; flex-wrap: wrap; }
.toggle-group button, .score-group button { min-width: 48px; min-height: 48px; font-size: 16px; padding: 8px 16px; border: 2px solid #bdc3c7; background: #fff; border-radius: 8px; cursor: pointer; }
.toggle-group button.selected, .score-group button.selected { background: #3498db; color: #fff; border-color: #3498db; }
.score-hint { font-size: 12px; color: #7f8c8d; margin-top: 4px; }
.bottom-bar { position: fixed; bottom: 0; left: 0; right: 0; background: #fff; padding: 12px 16px; box-shadow: 0 -2px 8px rgba(0,0,0,.1); text-align: center; }
#paste-btn { min-width: 180px; min-height: 44px; font-size: 16px; background: #27ae60; color: #fff; border: none; border-radius: 8px; cursor: pointer; }
#paste-btn:disabled { background: #95a5a6; cursor: not-allowed; }
.modal-mask { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,.5); z-index: 100; }
.modal-mask.show { display: flex; align-items: center; justify-content: center; }
.modal { background: #fff; border-radius: 12px; padding: 24px; max-width: 90%; width: 500px; max-height: 80vh; overflow-y: auto; }
.modal textarea { width: 100%; height: 100px; border: 1px solid #ccc; border-radius: 6px; font-family: monospace; font-size: 12px; padding: 8px; resize: none; }
.modal-buttons { display: flex; gap: 8px; margin-top: 12px; justify-content: center; }
.modal-buttons button { min-height: 40px; padding: 8px 24px; font-size: 14px; border: none; border-radius: 6px; cursor: pointer; }
#copy-btn { background: #3498db; color: #fff; }
#close-btn { background: #95a5a6; color: #fff; }
</style>
</head>
<body>
<div class="header">
  <h1>__TITLE__</h1>
  <p>逐条播放，凭直觉回答两个问题；全部答完点底部生成回贴码。</p>
  <p>共 __TOTAL__ 段，请戴耳机或安静环境</p>
</div>
<div class="progress">已完成 0 / __TOTAL__</div>
<div class="cards">__CARDS__</div>
<div class="bottom-bar"><button id="paste-btn">生成回贴码 (0/__TOTAL__)</button></div>

<div class="modal-mask" id="modal">
  <div class="modal">
    <textarea id="paste-area" readonly></textarea>
    <div class="modal-buttons">
      <button id="copy-btn">复制</button>
      <button id="close-btn">关闭</button>
    </div>
  </div>
</div>

<script>
(function() {
  var dataset = __DATASET_JSON__;
  var answers = {};
  var total = __TOTAL__;
  var storage = null;
  try { storage = window.localStorage; } catch(e) {}

  function save() {
    try { storage.setItem("blind_" + dataset, JSON.stringify(answers)); } catch(e) {}
  }
  function load() {
    try {
      var s = storage.getItem("blind_" + dataset);
      if (s) answers = JSON.parse(s);
    } catch(e) {}
    for (var k in answers) {
      var a = answers[k];
      var el = document.querySelector('.card[data-id="' + k + '"]');
      if (el) {
        if (a.guess) selectBtn(el.querySelector('.toggle-group'), a.guess);
        if (a.score) selectBtn(el.querySelector('.score-group'), a.score);
      }
    }
    updateProgress();
  }

  function selectBtn(container, val) {
    var btns = container.querySelectorAll('button');
    for (var i = 0; i < btns.length; i++) {
      if (btns[i].getAttribute('data-val') === String(val)) {
        btns[i].classList.add('selected');
      } else {
        btns[i].classList.remove('selected');
      }
    }
  }

  function updateProgress() {
    var done = 0;
    for (var id in answers) {
      if (answers[id].guess && answers[id].score) done++;
    }
    document.querySelector('.progress').textContent = "已完成 " + done + " / " + total;
    var btn = document.getElementById('paste-btn');
    btn.textContent = "生成回贴码 (" + done + "/" + total + ")";
    btn.disabled = (done < total);
  }

  // play handling
  var players = document.querySelectorAll('audio');
  document.addEventListener('click', function(e) {
    var btn = e.target.closest('.play-btn');
    if (!btn) return;
    var audio = btn.parentElement.querySelector('audio');
    if (btn.classList.contains('playing')) {
      audio.pause();
      btn.classList.remove('playing');
      btn.textContent = "▶ 播放";
    } else {
      for (var i = 0; i < players.length; i++) {
        players[i].pause();
        players[i].parentElement.querySelector('.play-btn').classList.remove('playing');
        players[i].parentElement.querySelector('.play-btn').textContent = "▶ 播放";
      }
      audio.play();
      btn.classList.add('playing');
      btn.textContent = "⏸ 暂停";
    }
  });

  players.forEach(function(a) {
    a.addEventListener('ended', function() {
      var btn = a.parentElement.querySelector('.play-btn');
      btn.classList.remove('playing');
      btn.textContent = "▶ 播放";
    });
  });

  // question selection
  document.addEventListener('click', function(e) {
    var btn = e.target.closest('[data-q] button');
    if (!btn) return;
    var card = btn.closest('.card');
    var id = card.getAttribute('data-id');
    var q = btn.parentElement.getAttribute('data-q');
    selectBtn(btn.parentElement, btn.getAttribute('data-val'));
    answers[id] = answers[id] || {};
    if (q === 'guess') answers[id].guess = btn.getAttribute('data-val');
    else answers[id].score = parseInt(btn.getAttribute('data-val'), 10);
    save();
    updateProgress();
  });

  // paste modal
  var modal = document.getElementById('modal');
  var pasteArea = document.getElementById('paste-area');
  document.getElementById('paste-btn').addEventListener('click', function() {
    var out = [];
    var ids = Object.keys(answers);
    for (var i = 0; i < ids.length; i++) {
      var id = ids[i];
      var a = answers[id];
      if (a.guess && a.score) {
        out.push({"id": id, "guess": a.guess, "score": a.score});
      }
    }
    if (out.length === 0) {
      alert("请至少完整回答一段");
      return;
    }
    var obj = {"v": 1, "dataset": dataset, "answers": out};
    pasteArea.value = JSON.stringify(obj);
    modal.classList.add('show');
  });

  function copyFallback() {
    pasteArea.select();
    try {
      if (document.execCommand('copy')) {
        alert("已复制");
      } else {
        alert("请长按手动复制");
      }
    } catch(e) {
      alert("请长按手动复制");
    }
  }

  function copyText() {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(pasteArea.value).then(function() {
        alert("已复制");
      }).catch(function() {
        copyFallback();
      });
    } else {
      copyFallback();
    }
  }
  document.getElementById('copy-btn').addEventListener('click', copyText);
  document.getElementById('close-btn').addEventListener('click', function() {
    modal.classList.remove('show');
  });
  modal.addEventListener('click', function(e) {
    if (e.target === modal) modal.classList.remove('show');
  });

  load();
})();
</script>
</body>
</html>
"""
    html = html.replace("__TITLE__", args.title)
    html = html.replace("__TOTAL__", str(total))
    html = html.replace("__CARDS__", "\n".join(cards_html))
    html = html.replace("__DATASET_JSON__", json.dumps(dataset))

    try:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(html)
    except Exception as e:
        print("ERROR: failed to write html file %s: %s" % (args.out, str(e)[:200]), file=sys.stderr)
        return 2

    print("clips=%d synth=%d real=%d size_mb=%.2f out=%s key=%s" % (
        total,
        len(synth_wavs),
        len(args.real),
        html_mb,
        args.out,
        key_out,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
