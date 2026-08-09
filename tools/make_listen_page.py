#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_listen_page.py - manifest-driven listening page generator."""

import argparse
import base64
import json
import math
import os
import re
import sys
from html import escape

try:
    import numpy as np
    import soundfile as sf
    import lameenc
except ImportError as exc:
    print(f"ERROR: missing dependency: {exc.name}")
    sys.exit(1)


SUPPORTED_EXTS = {".mp3", ".wav"}
TONE_COLORS = {
    "gray": "#6c757d",
    "blue": "#0d6efd",
    "green": "#198754",
    "red": "#dc3545",
    "amber": "#fd7e14",
}


def fail(message):
    """Print ASCII-only error and exit nonzero."""
    print(f"ERROR: {message}")
    sys.exit(1)


def validate_manifest(data):
    """Validate manifest structure and return normalized data."""
    if not isinstance(data, dict):
        fail("manifest root must be a JSON object")

    required_top = ("title", "groups")
    for key in required_top:
        if key not in data:
            fail(f"missing required field: '{key}'")

    if not isinstance(data["title"], str) or not data["title"].strip():
        fail("field 'title' must be a non-empty string")

    if "groups" not in data or not isinstance(data["groups"], list) or not data["groups"]:
        fail("field 'groups' must be a non-empty array")

    if "intro" in data and not isinstance(data["intro"], str):
        fail("field 'intro' must be a string")
    if "footer_note" in data and not isinstance(data["footer_note"], str):
        fail("field 'footer_note' must be a string")

    normalized_groups = []
    total_clips = 0

    for idx, group in enumerate(data["groups"]):
        if not isinstance(group, dict):
            fail(f"group[{idx}] must be an object")

        if "name" not in group or not isinstance(group["name"], str) or not group["name"].strip():
            fail(f"group[{idx}]: missing/invalid 'name' (non-empty string required)")

        if "clips" not in group or not isinstance(group["clips"], list) or not group["clips"]:
            fail(f"group[{idx}]: missing/invalid 'clips' (non-empty array required)")

        if "text" in group and not isinstance(group["text"], str):
            fail(f"group[{idx}]: 'text' must be a string")

        normalized_clips = []
        for cidx, clip in enumerate(group["clips"]):
            if not isinstance(clip, dict):
                fail(f"group[{idx}].clips[{cidx}] must be an object")

            if "label" not in clip or not isinstance(clip["label"], str) or not clip["label"].strip():
                fail(f"group[{idx}].clips[{cidx}]: missing/invalid 'label'")

            if "path" not in clip or not isinstance(clip["path"], str) or not clip["path"].strip():
                fail(f"group[{idx}].clips[{cidx}]: missing/invalid 'path'")

            path = clip["path"]
            ext = os.path.splitext(path)[1].lower()
            if ext not in SUPPORTED_EXTS:
                fail(f"group[{idx}].clips[{cidx}]: unsupported extension '{ext}' (supported: {', '.join(sorted(SUPPORTED_EXTS))})")

            if not os.path.isfile(path):
                fail(f"group[{idx}].clips[{cidx}]: file not found: {path}")

            tone = clip.get("tone", "gray")
            if tone not in TONE_COLORS:
                fail(f"group[{idx}].clips[{cidx}]: invalid tone '{tone}' (allowed: {', '.join(sorted(TONE_COLORS))})")

            normalized_clips.append({"label": clip["label"], "path": path, "tone": tone})
            total_clips += 1

        normalized_groups.append({
            "name": group["name"],
            "text": group.get("text", ""),
            "clips": normalized_clips,
        })

    return {
        "title": data["title"],
        "intro": data.get("intro", ""),
        "footer_note": data.get("footer_note", ""),
        "groups": normalized_groups,
        "_stats": {"group_count": len(normalized_groups), "clip_count": total_clips},
    }


def wav_to_mp3_bytes(wav_path, bitrate=64):
    """Convert WAV file to MP3 bytes using soundfile + lameenc."""
    try:
        data, samplerate = sf.read(wav_path)
    except Exception as exc:
        fail(f"cannot read WAV file {wav_path}: {exc}")

    # Convert float data to int16 with proper scaling
    if data.ndim == 1:
        mono = data
    else:
        # Average channels
        mono = np.mean(data, axis=1)

    mono = (np.clip(mono, -1.0, 1.0) * 32767).astype(np.int16)

    if mono.size == 0:
        fail(f"WAV file {wav_path} is empty")

    encoder = lameenc.Encoder()
    encoder.set_bit_rate(bitrate)
    encoder.set_channels(1)
    encoder.set_quality(2)
    encoder.set_in_sample_rate(samplerate)

    # Encode in chunks
    chunk_size = 65536
    mp3_chunks = bytearray()
    for i in range(0, mono.size, chunk_size):
        chunk = mono[i:i + chunk_size].tobytes()
        mp3_chunks.extend(encoder.encode(chunk))
    mp3_chunks.extend(encoder.flush())
    mp3_bytes = bytes(mp3_chunks)

    # Validate: decode back and check RMS
    try:
        decoded, _ = sf.read(__import__("io").BytesIO(mp3_bytes), dtype="float32")
        if decoded.size == 0:
            fail(f"MP3 encoding produced empty output for {wav_path}")
        rms = float(np.sqrt(np.mean(np.square(decoded))))
        if rms <= 0.005:
            fail(f"silence-guard: MP3 encoding RMS too low ({rms:.5f}) for {wav_path} - possible silent output")
    except SystemExit:
        raise
    except Exception as exc:
        fail(f"MP3 validation failed for {wav_path}: {exc}")

    return mp3_bytes


def audio_to_base64(path, bitrate=64):
    """Read audio file and return base64 MP3 data URI string."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".mp3":
        try:
            with open(path, "rb") as f:
                raw = f.read()
        except Exception as exc:
            fail(f"cannot read MP3 file {path}: {exc}")
        if not raw:
            fail(f"MP3 file {path} is empty")
    elif ext == ".wav":
        raw = wav_to_mp3_bytes(path, bitrate)  # wav_to_mp3_bytes handles errors
    else:
        fail(f"unsupported extension for {path}")

    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:audio/mpeg;base64,{b64}"


def escape_html(text):
    """Escape text for safe HTML embedding."""
    return escape(str(text), quote=True)


def build_html(manifest, bitrate=64):
    """Build the complete self-contained HTML page."""
    title = escape_html(manifest["title"])
    intro_text = escape_html(manifest["intro"]).replace("\n", "<br>")
    footer_note = escape_html(manifest["footer_note"]).replace("\n", "<br>")

    # Group cards
    groups_html = []
    for gidx, group in enumerate(manifest["groups"]):
        group_name = escape_html(group["name"])
        group_text = escape_html(group["text"]).replace("\n", "<br>")

        clips_html = []
        for clip in group["clips"]:
            label = escape_html(clip["label"])
            tone = clip["tone"]
            color = TONE_COLORS.get(tone, TONE_COLORS["gray"])
            try:
                data_uri = audio_to_base64(clip["path"], bitrate)
            except SystemExit:
                raise
            except Exception as exc:
                fail(f"failed to process {clip['path']}: {exc}")

            clips_html.append(f"""
            <div class="clip">
              <span class="badge" style="background-color:{color};">{label}</span>
              <audio controls preload="none" src="{data_uri}"></audio>
            </div>""")

        clips_block = "\n".join(clips_html)
        groups_html.append(f"""
      <div class="card">
        <h2>{group_name}</h2>
        {f'<p class="text">{group_text}</p>' if group_text else ''}
        <div class="clips">
{clips_block}
        </div>
      </div>""")

    groups_block = "\n".join(groups_html)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    background: #f8f9fa;
    color: #212529;
    font-size: 16px;
    line-height: 1.6;
    padding: 16px;
  }}
  .container {{ max-width: 900px; margin: 0 auto; }}
  h1 {{ font-size: 1.8rem; margin-bottom: 8px; }}
  .intro {{ margin-bottom: 24px; color: #495057; }}
  .card {{
    background: #fff;
    border: 1px solid #dee2e6;
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 16px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  }}
  .card h2 {{ font-size: 1.2rem; margin-bottom: 8px; }}
  .text {{ color: #495057; margin-bottom: 12px; }}
  .clip {{
    margin-bottom: 12px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }}
  .clip:last-child {{ margin-bottom: 0; }}
  .badge {{
    display: inline-block;
    padding: 3px 10px;
    border-radius: 4px;
    color: #fff;
    font-size: 0.9rem;
    font-weight: 500;
    align-self: flex-start;
  }}
  audio {{
    width: 100%;
    height: 44px;
    display: block;
  }}
  .footer {{
    margin-top: 24px;
    padding-top: 12px;
    border-top: 1px solid #dee2e6;
    color: #6c757d;
    font-size: 0.9rem;
  }}
</style>
</head>
<body>
<div class="container">
  <h1>{title}</h1>
  {f'<div class="intro">{intro_text}</div>' if intro_text else ''}
{groups_block}
  {f'<div class="footer">{footer_note}</div>' if footer_note else ''}
</div>
</body>
</html>"""

    return html


def main():
    parser = argparse.ArgumentParser(description="Generate self-contained listening page from manifest")
    parser.add_argument("--manifest", required=True, help="Path to manifest JSON file")
    parser.add_argument("--out", required=True, help="Output HTML file path")
    parser.add_argument("--bitrate", type=int, default=64, help="MP3 bitrate for WAV transcoding (16-128, default: 64)")
    parser.add_argument("--max-mb", type=float, default=0, help="Maximum output HTML size in MB (0=unlimited)")
    args = parser.parse_args()

    # Validate bitrate
    if args.bitrate < 16 or args.bitrate > 128:
        fail(f"bitrate must be between 16 and 128 (got {args.bitrate})")

    # Validate max-mb
    if args.max_mb < 0:
        fail(f"max-mb must be non-negative (got {args.max_mb})")

    # Read manifest
    try:
        with open(args.manifest, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
    except FileNotFoundError:
        fail(f"manifest file not found: {args.manifest}")
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON in manifest: {exc}")
    except Exception as exc:
        fail(f"cannot read manifest: {exc}")

    manifest = validate_manifest(raw_data)

    # Generate HTML
    html = build_html(manifest, args.bitrate)

    # Check size limit before writing
    html_bytes = len(html.encode('utf-8'))
    size_mb = html_bytes / (1024 * 1024)
    if args.max_mb > 0 and size_mb > args.max_mb:
        fail(f"output size {size_mb:.2f} MB exceeds max-mb limit {args.max_mb:.2f} MB - please split the manifest and regenerate")

    # Write output
    try:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(html)
    except Exception as exc:
        fail(f"cannot write output file {args.out}: {exc}")

    # Summary (ASCII only)
    stats = manifest["_stats"]
    print(f"OK: {stats['group_count']} groups, {stats['clip_count']} clips, HTML {size_mb:.2f} MB")


if __name__ == "__main__":
    main()