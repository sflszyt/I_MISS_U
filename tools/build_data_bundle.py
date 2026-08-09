#!/usr/bin/env python3
"""Build archive data bundle from normalized UIF JSONL files."""

import argparse
import json
import os
import re
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

PERSON_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

REQUIRED_INPUTS = [
    "normalized/wechat_messages.uif.jsonl",
    "normalized/wechat_voice_manifest.jsonl",
    "normalized/wechat_video_manifest.jsonl",
]

SKIP_MARKERS = ("missing", "absent", "no_file", "not_found", "unavailable")

OUTPUT_DIR_NAME = "archive_out"
DATA_SUBDIR = "data"
MEDIA_SUBDIR = "media"
VOICE_SUBDIR = "voice"
VIDEO_SUBDIR = "video"


def log(msg: str) -> None:
    """Print ASCII-only message to stdout."""
    print(msg, flush=True)


def fail(msg: str) -> None:
    """Print error and exit nonzero."""
    log(f"ERROR: {msg}")
    sys.exit(1)


def read_jsonl(path: Path) -> list:
    """Read JSONL file, fail on bad lines with line number."""
    if not path.is_file():
        fail(f"missing required input file: {path}")
    records = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                fail(f"bad JSONL line {line_no} in {path}: {exc}")
    return records


def safe_copy(src: Path, dst: Path) -> None:
    """Copy src to dst atomically, skipping if exist and same size."""
    if not src.is_file():
        fail(f"source media file missing: {src}")
    if dst.is_file() and dst.stat().st_size == src.stat().st_size:
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".tmp")
    shutil.copy2(src, tmp)
    os.replace(tmp, dst)


def check_within_bound(root: Path, path: Path) -> None:
    """Ensure path is anchored under root after resolution."""
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError:
        fail(f"path escapes repo root: {path}")


def check_file_ref_bound(file_ref: str, person_dir: Path, subdir: str, file_type: str) -> Path:
    """Validate file_ref resolves within people/<slug>/<subdir>/ and return resolved path."""
    candidate = (person_dir / file_ref).resolve()
    allowed_root = (person_dir / subdir).resolve()
    try:
        candidate.relative_to(allowed_root)
    except ValueError:
        fail(f"{file_type} file_ref escapes {subdir}/ tree: {file_ref}")
    return candidate


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build archive data bundle from UIF normalized files"
    )
    parser.add_argument("--person", required=True, help="person slug")
    parser.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parent.parent),
        help="repo root directory",
    )
    args = parser.parse_args()

    if not PERSON_SLUG_RE.match(args.person):
        fail(f"invalid person slug: {args.person}")

    repo_root = Path(args.repo_root).resolve()
    person_dir = repo_root / "people" / args.person
    check_within_bound(repo_root, person_dir)

    normalized_dir = person_dir / "normalized"
    raw_dir = person_dir / "raw"
    processed_dir = person_dir / "processed"
    for d in (normalized_dir, raw_dir, processed_dir):
        check_within_bound(person_dir, d)

    # ---------- read inputs ----------
    messages_path = normalized_dir / "wechat_messages.uif.jsonl"
    voice_manifest_path = normalized_dir / "wechat_voice_manifest.jsonl"
    video_manifest_path = normalized_dir / "wechat_video_manifest.jsonl"

    messages = read_jsonl(messages_path)
    voice_manifest = read_jsonl(voice_manifest_path)
    video_manifest = read_jsonl(video_manifest_path)

    if not messages:
        fail("empty messages file")
    if not voice_manifest:
        fail("empty voice manifest")

    # ---------- output dirs ----------
    out_root = person_dir / OUTPUT_DIR_NAME
    out_data = out_root / DATA_SUBDIR
    media_dir = out_data / MEDIA_SUBDIR
    voice_out = media_dir / VOICE_SUBDIR
    video_out = media_dir / VIDEO_SUBDIR
    for d in (out_data, media_dir, voice_out, video_out):
        d.mkdir(parents=True, exist_ok=True)

    # ---------- messages: sort and validate ----------
    for i, rec in enumerate(messages):
        if "timestamp" not in rec:
            fail(f"message record {i} has no timestamp field")
    messages_sorted = sorted(messages, key=lambda r: r.get("timestamp", ""))

    messages_by_year = defaultdict(list)
    for rec in messages_sorted:
        ts = rec.get("timestamp", "")
        year = str(ts)[:4]
        if len(year) == 4 and year.isdigit():
            messages_by_year[year].append(rec)
        else:
            fail(f"invalid timestamp format: {ts!r}")

    year_files = []
    for year in sorted(messages_by_year.keys()):
        year_records = messages_by_year[year]
        payload = {
            "year": int(year),
            "count": len(year_records),
            "records": year_records,
        }
        fname = f"messages_{year}.json"
        fpath = out_data / fname
        tmp = fpath.with_name(fpath.name + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, fpath)
        year_files.append(fname)

    # ---------- media conflict tracking ----------
    media_dest_basename_map = {}  # basename -> src_path (as string)

    def register_media_name(basename: str, src_path: Path, media_kind: str) -> None:
        """Enforce unique basename across all copied media; fail on collision from different source."""
        src_resolved = str(src_path.resolve())
        existing = media_dest_basename_map.get(basename)
        if existing is None:
            media_dest_basename_map[basename] = src_resolved
            return
        if existing != src_resolved:
            fail(
                f"media basename collision: {basename!r} "
                f"(conflicting sources: {existing!r} vs {src_resolved!r})"
            )
        # Same source repeated -> safe to skip, caller will reuse existing copy

    # ---------- media: voice ----------
    voice_index = []
    voice_src_paths = set()
    for item in voice_manifest:
        media_type = item.get("media_type")
        if media_type != "audio":
            fail(f"voice manifest entry has wrong media_type: {media_type!r}")
        file_ref = item.get("file_ref")
        if not file_ref:
            fail(f"voice manifest entry missing file_ref: {item}")
        src_path = check_file_ref_bound(file_ref, person_dir, "processed", "voice")
        fname = Path(file_ref).name
        register_media_name(fname, src_path, "voice")
        dst_rel = f"media/{VOICE_SUBDIR}/{fname}"
        dst_path = (out_data / dst_rel).resolve()
        check_within_bound(out_data, dst_path)
        if str(src_path) in voice_src_paths:
            # duplicate source, reuse existing entry (idempotent)
            pass
        else:
            safe_copy(src_path, dst_path)
            voice_src_paths.add(str(src_path))
        new_item = dict(item)
        new_item["archive_path"] = dst_rel
        voice_index.append(new_item)

    # ---------- media: video ----------
    video_index = []
    video_copied = 0
    video_skipped_no_file = 0
    video_skipped_not_subject = 0
    video_src_paths = set()
    for item in video_manifest:
        media_type = item.get("media_type")
        if media_type != "video":
            fail(f"video manifest entry has wrong media_type: {media_type!r}")
        file_ref = item.get("file_ref")
        if not file_ref:
            video_skipped_no_file += 1
            continue
        src_path = check_file_ref_bound(file_ref, person_dir, "raw", "video")
        if not src_path.is_file():
            log(f"WARN: video source file not found, skipping: {src_path}")
            video_skipped_no_file += 1
            continue
        if item.get("is_subject") is not True:
            video_skipped_not_subject += 1
            continue
        fname = Path(file_ref).name
        register_media_name(fname, src_path, "video")
        dst_rel = f"media/{VIDEO_SUBDIR}/{fname}"
        dst_path = (out_data / dst_rel).resolve()
        check_within_bound(out_data, dst_path)
        if str(src_path) in video_src_paths:
            # duplicate source, reuse existing copy
            pass
        else:
            safe_copy(src_path, dst_path)
            video_src_paths.add(str(src_path))
        new_item = dict(item)
        new_item["archive_path"] = dst_rel
        video_index.append(new_item)
        video_copied += 1

    media_index = {"voice": voice_index, "video": video_index}
    media_index_path = out_data / "media_index.json"
    tmp = media_index_path.with_name(media_index_path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(media_index, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, media_index_path)

    # ---------- timeline ----------
    month_stats = defaultdict(
        lambda: {
            "messages_total": 0,
            "messages_from_subject": 0,
            "voice_count": 0,
            "video_count": 0,
            "first_ts": None,
            "last_ts": None,
        }
    )
    for rec in messages_sorted:
        ts = str(rec.get("timestamp", ""))
        month = ts[:7]
        if len(month) != 7:
            fail(f"invalid timestamp for month grouping: {ts!r}")
        stats = month_stats[month]
        stats["messages_total"] += 1
        if rec.get("sender") == "subject":
            stats["messages_from_subject"] += 1
        if stats["first_ts"] is None or ts < stats["first_ts"]:
            stats["first_ts"] = ts
        if stats["last_ts"] is None or ts > stats["last_ts"]:
            stats["last_ts"] = ts

    # Count voices per month from message provenance (fallback to media item timestamps)
    voice_by_month = Counter()
    for item in voice_manifest:
        ts = str(item.get("timestamp", ""))
        month = ts[:7]
        if len(month) == 7:
            voice_by_month[month] += 1
    for month, cnt in voice_by_month.items():
        if month in month_stats:
            month_stats[month]["voice_count"] += cnt

    video_by_month = Counter()
    for item in video_index:
        ts = str(item.get("timestamp", ""))
        month = ts[:7]
        if len(month) == 7:
            video_by_month[month] += 1
    for month, cnt in video_by_month.items():
        if month in month_stats:
            month_stats[month]["video_count"] += cnt

    timeline = []
    for month in sorted(month_stats.keys()):
        stats = month_stats[month]
        timeline.append(
            {
                "month": month,
                "messages_total": stats["messages_total"],
                "messages_from_subject": stats["messages_from_subject"],
                "voice_count": stats["voice_count"],
                "video_count": stats["video_count"],
                "first_ts": stats["first_ts"],
                "last_ts": stats["last_ts"],
            }
        )

    generated_at = datetime.now(timezone.utc).isoformat()
    timeline_payload = {
        "tier": 2,
        "derived_from": "wechat_messages.uif.jsonl + manifests",
        "generated_at": generated_at,
        "months": timeline,
    }
    timeline_path = out_data / "timeline.json"
    tmp = timeline_path.with_name(timeline_path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(timeline_payload, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, timeline_path)

    # ---------- meta ----------
    messages_by_year_counts = {y: len(r) for y, r in messages_by_year.items()}
    counts = {
        "messages": len(messages_sorted),
        "messages_by_year": messages_by_year_counts,
        "voice": len(voice_index),
        "video_copied": video_copied,
        "video_skipped_no_file": video_skipped_no_file,
        "video_skipped_not_subject": video_skipped_not_subject,
    }
    meta = {
        "person": args.person,
        "generated_at": generated_at,
        "counts": counts,
        "tier_legend": {
            "1": "家人确认",
            "2": "来源可溯",
            "3": "模型生成，禁作事实",
        },
        "files": year_files + ["media_index.json", "timeline.json", "meta.json"],
    }
    meta_path = out_data / "meta.json"
    tmp = meta_path.with_name(meta_path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, meta_path)

    # ---------- summary ----------
    total_size = 0
    for f in out_data.rglob("*"):
        if f.is_file():
            total_size += f.stat().st_size
    size_mb = total_size / (1024 * 1024)
    log(
        f"summary: messages={len(messages_sorted)} "
        f"years={len(year_files)} voice={len(voice_index)} "
        f"video_copied={video_copied} "
        f"video_skipped_no_file={video_skipped_no_file} "
        f"video_skipped_not_subject={video_skipped_not_subject} "
        f"size={size_mb:.2f}MB"
    )


if __name__ == "__main__":
    main()