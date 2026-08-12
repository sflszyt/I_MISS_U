#!/usr/bin/env python3
"""Build per-original-clip transcripts for a person's voice archive."""

import argparse
import datetime
import json
import os
import re
import sys

HOUSE_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class GuardError(Exception):
    pass


def guard_path(path, raw_dir):
    """Resolve path; forbid anything under the person's raw/ tree. Paths outside the repo are allowed."""
    if not path:
        raise GuardError("empty path")
    ap = os.path.realpath(path)
    rd = os.path.realpath(raw_dir)
    if ap == rd or ap.startswith(rd + os.sep):
        raise GuardError(f"path resolves under raw/: {path}")
    return ap


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--person", required=True)
    p.add_argument("--segments-manifest", required=True)
    p.add_argument("--asr-text", required=True)
    p.add_argument("--corrected-text", default=None)
    p.add_argument("--media-kind", default="voice")
    p.add_argument("--manifest", default=None)
    p.add_argument("--out", default=None)
    return p.parse_args()


def load_jsonl(path):
    records = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def load_kaldi_space(path):
    """<seg_key> <text> -- split first space."""
    d = {}
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            sp = line.split(" ", 1)
            if len(sp) == 2:
                d[sp[0]] = sp[1]
            elif len(sp) == 1:
                d[sp[0]] = ""
    return d


def load_kaldi_tab(path):
    """<key>\t<text>."""
    d = {}
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            sp = line.split("\t", 1)
            if len(sp) == 2:
                d[sp[0]] = sp[1]
            elif len(sp) == 1:
                d[sp[0]] = ""
    return d


def stem_of_file_ref(file_ref):
    base = os.path.basename(file_ref)
    return os.path.splitext(base)[0]


def main():
    args = parse_args()

    if not HOUSE_SLUG_RE.match(args.person):
        print("error: invalid person slug", file=sys.stderr)
        return 2

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    raw_dir = os.path.join(repo_root, "people", args.person, "raw")

    # Resolve every input/output
    try:
        seg_path = guard_path(args.segments_manifest, raw_dir)
        asr_path = guard_path(args.asr_text, raw_dir)
        corr_path = guard_path(args.corrected_text, raw_dir) if args.corrected_text else None

        manifest_path = args.manifest
        if not manifest_path:
            manifest_path = os.path.join(
                repo_root, "people", args.person, "normalized",
                f"wechat_{args.media_kind}_manifest.jsonl",
            )
        manifest_path = guard_path(manifest_path, raw_dir)

        out_path = args.out
        if not out_path:
            out_path = os.path.join(
                repo_root, "people", args.person, "normalized",
                f"{args.media_kind}_transcripts.jsonl",
            )
        out_path = guard_path(out_path, raw_dir)
    except GuardError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    # Load segments manifest
    try:
        segments = load_jsonl(seg_path)
    except Exception as e:
        print(f"error: cannot read segments manifest: {e}", file=sys.stderr)
        return 2

    # Load ASR
    try:
        asr_map = load_kaldi_space(asr_path)
    except Exception as e:
        print(f"error: cannot read ASR text: {e}", file=sys.stderr)
        return 2

    # Load corrected
    corr_map = {}
    if corr_path:
        try:
            corr_map = load_kaldi_tab(corr_path)
        except Exception as e:
            print(f"error: cannot read corrected text: {e}", file=sys.stderr)
            return 2

    # Load manifest
    try:
        manifest_records = load_jsonl(manifest_path)
    except Exception as e:
        print(f"error: cannot read manifest: {e}", file=sys.stderr)
        return 2

    # Build orig_key -> manifest record
    manifest_by_key = {}
    for rec in manifest_records:
        if "file_ref" not in rec or "record_id" not in rec:
            continue
        key = stem_of_file_ref(rec["file_ref"])
        manifest_by_key[key] = rec

    # Build orig_key -> list of segments
    seg_by_orig = {}
    for seg in segments:
        sk = seg.get("seg_key")
        ok = seg.get("orig_key")
        if not sk or not ok:
            continue
        if ok in ("justin_prompt",) or sk in ("justin_prompt",):
            continue
        if ok not in manifest_by_key:
            continue
        seg_by_orig.setdefault(ok, []).append(seg)

    # Sort segments by start_s
    for ok in seg_by_orig:
        seg_by_orig[ok].sort(key=lambda s: s.get("start_s", 0.0))

    # Determine per-segment text / source
    corrected_count = 0
    draft_count = 0
    missing_count = 0
    skipped_keys = 0

    out_lines = []
    # Iterate manifest order
    for rec in manifest_records:
        key = stem_of_file_ref(rec.get("file_ref", ""))

        clip_text = None
        quality = None
        segment_records = []

        if key in seg_by_orig and key not in ("justin_prompt",):
            segs = seg_by_orig[key]
            clip_parts = []
            all_corr = True
            all_draft = True

            for seg in segs:
                sk = seg.get("seg_key", "")
                start = seg.get("start_s", 0.0)
                end = seg.get("end_s", 0.0)

                if sk in corr_map:
                    txt = corr_map[sk]
                    src = "corrected"
                    corrected_count += 1
                elif sk in asr_map:
                    txt = asr_map[sk]
                    src = "asr_draft"
                    draft_count += 1
                else:
                    txt = ""
                    src = "missing"
                    missing_count += 1

                if src != "corrected":
                    all_corr = False
                if src != "asr_draft":
                    all_draft = False

                seg_rec = {
                    "seg_key": sk,
                    "start_s": start,
                    "end_s": end,
                    "text": txt,
                    "source": src,
                }
                segment_records.append(seg_rec)
                clip_parts.append(txt)

            if all_corr:
                quality = "corrected"
            elif all_draft:
                quality = "asr_draft"
            else:
                quality = "mixed"

            has_any_text = any(part for part in clip_parts)
            if has_any_text:
                clip_text = "\n".join(clip_parts)
            else:
                clip_text = None
                quality = "untranscribed"

        else:
            # Untranscribed / no pool presence
            quality = None
            clip_text = None

        if key in ("justin_prompt",) or (key in seg_by_orig and key not in manifest_by_key):
            skipped_keys += 1
            continue

        out_rec = {
            "record_id": rec.get("record_id"),
            "orig_key": key,
            "timestamp": rec.get("timestamp"),
            "chat_room": rec.get("chat_room"),
            "duration_ms": rec.get("duration_ms"),
            "is_subject": rec.get("is_subject"),
            "tier": 2,
            "quality": quality if clip_text is not None else "untranscribed",
            "text": clip_text,
            "segments": segment_records,
            "generated_at": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "derived_from": {
                "asr": asr_path,
                "corrected": corr_path if corr_path else None,
            },
        }
        out_lines.append(out_rec)

    # Write output
    try:
        with open(out_path, "w", encoding="utf-8") as fh:
            for rec in out_lines:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"error: cannot write output: {e}", file=sys.stderr)
        return 2

    # Summary
    total = len(out_lines)
    transcribed = sum(1 for r in out_lines if r["text"] not in (None, ""))
    corrected = sum(1 for r in out_lines if r["quality"] == "corrected")
    draft = sum(1 for r in out_lines if r["quality"] == "asr_draft")
    mixed = sum(1 for r in out_lines if r["quality"] == "mixed")
    untranscribed = sum(1 for r in out_lines if r["text"] in (None, ""))

    print(
        f"clips={total} transcribed={transcribed} corrected={corrected} "
        f"draft={draft} mixed={mixed} untranscribed={untranscribed} out={out_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
