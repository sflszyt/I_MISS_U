# -*- coding: utf-8 -*-
"""Extract memory candidates from UIF messages and media manifests."""

try:
    from .local_identity import owner_participant
except ImportError:
    from local_identity import owner_participant


import argparse
import hashlib
import json
import math
import os
import re
import sys
from collections import defaultdict, Counter
from datetime import datetime
from pathlib import Path

try:
    from .memory_evidence import scope_candidate, dataset_fingerprint, preflight_outputs
except ImportError:
    from memory_evidence import scope_candidate, dataset_fingerprint, preflight_outputs


def _parse_manifest_line(line: str):
    """Parse a manifest line with validation. Returns (record, error_count)."""
    try:
        rec = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return None, 1
    if not isinstance(rec, dict):
        return None, 1
    # Required fields per spec
    record_id = rec.get("record_id")
    timestamp = rec.get("timestamp")
    file_ref = rec.get("file_ref")
    media_type = rec.get("media_type")
    if not isinstance(record_id, str) or not record_id.strip():
        return None, 1
    if not isinstance(timestamp, str) or not extract_date(timestamp):
        return None, 1
    if not isinstance(file_ref, str) or not file_ref.strip():
        return None, 1
    if not isinstance(media_type, str) or not media_type.strip():
        return None, 1
    # duration_ms robust conversion
    raw_duration = rec.get("duration_ms")
    try:
        rec["duration_ms"] = int(raw_duration) if raw_duration is not None else 0
    except (TypeError, ValueError):
        rec["duration_ms"] = 0
    return rec, 0


def _parse_uif_line(line: str):
    """Parse a UIF line with strict validation. Returns (record, error_count)."""
    try:
        rec = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return None, 1
    if not isinstance(rec, dict):
        return None, 1
    # Only accept message/text rows
    if rec.get("record_type") != "message" or rec.get("content_type") != "text":
        return None, 0
    # Required field validations - any failure counts as bad line
    record_id = rec.get("record_id")
    if not isinstance(record_id, str) or not record_id.strip():
        return None, 1
    timestamp = rec.get("timestamp")
    if not isinstance(timestamp, str) or not extract_date(timestamp):
        return None, 1
    chat_room = rec.get("chat_room")
    if not isinstance(chat_room, str) or not chat_room.strip():
        return None, 1
    text = rec.get("text")
    if not isinstance(text, str) or not text.strip():
        return None, 1
    sender = rec.get("sender")
    if not isinstance(sender, str) or not sender.strip():
        return None, 1
    return rec, 0


def _parse_transcript_line(line: str):
    """Parse a transcript line with validation. Returns (record, error_count)."""
    try:
        rec = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return None, 1
    if not isinstance(rec, dict):
        return None, 1
    record_id = rec.get("record_id")
    if not isinstance(record_id, str) or not record_id.strip():
        return None, 1
    timestamp = rec.get("timestamp")
    if not isinstance(timestamp, str) or not extract_date(timestamp):
        return None, 1
    return rec, 0


def extract_date(ts_str: str) -> str:
    """Extract YYYY-MM-DD from ISO timestamp string."""
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return dt.date().isoformat()
    except (ValueError, AttributeError):
        return ""


def is_subject(rec: dict) -> bool:
    """Determine if a message/media record is from the subject."""
    if rec.get("record_type") == "message":
        return rec.get("sender") == "subject"
    return rec.get("is_subject") is True


def make_candidate(kind: str, kind_label: str, date: str, chat_room, group,
                   excerpts, counts, source_records, key_suffix=""):
    """Build a candidate record dict."""
    aux_key = f"{date}|{key_suffix}" if key_suffix else date
    hash_input = f"{kind}|{aux_key}".encode("utf-8")
    candidate_id = hashlib.sha256(hash_input).hexdigest()[:16]

    head = ""
    if excerpts and isinstance(excerpts[0], dict):
        text = excerpts[0].get("text")
        if isinstance(text, str) and text:
            head = text[:20]
        else:
            file_ref = excerpts[0].get("file_ref")
            if isinstance(file_ref, str) and file_ref:
                head = os.path.basename(file_ref)[:20]

    title = f"{date} {kind_label}：{head}"

    return {
        "candidate_id": candidate_id,
        "kind": kind,
        "kind_label": kind_label,
        "date": date,
        "chat_room": chat_room,
        "group": group,
        "title": title,
        "excerpts": excerpts[:5],
        "counts": counts,
        "tier": 2,
        "status": "pending",
        "provenance": {
            "generator": "extract_memory_candidates",
            "version": "1.0.0",
            "source_records": source_records,
        },
    }


def sort_candidates(candidates):
    """Sort candidates by priority and counts."""
    kind_order = {
        "keyword_event": 0,
        "media_burst": 1,
        "burst_day": 2,
        "voice_long": 3,
        "long_message": 4,
    }

    def count_value(cand):
        kind = cand["kind"]
        counts = cand["counts"]
        if kind == "keyword_event":
            return counts.get("hits", 0)
        if kind == "burst_day":
            return counts.get("messages", 0)
        if kind == "media_burst":
            return counts.get("total", 0)
        if kind == "voice_long":
            return counts.get("duration_ms", 0)
        if kind == "long_message":
            return counts.get("length", 0)
        return 0

    # Sort by (kind_priority, -count_value, date)
    return sorted(
        candidates,
        key=lambda c: (
            kind_order.get(c["kind"], 99),
            -count_value(c),
            c["date"],
        ),
    )


def load_transcripts(path: Path, kind: str):
    """Load transcript records from JSONL, returning (map, bad_count).
    
    Map: record_id -> transcript dict (with text, quality, kind, etc.)
    Only entries with non-null non-empty text AND is_subject true are kept.
    The passed `kind` is tagged onto each kept record.
    """
    transcript_map = {}
    bad = 0
    if not path.exists():
        return transcript_map, bad
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec, err = _parse_transcript_line(line)
            if rec is None:
                bad += err
                continue
            text = rec.get("text")
            if not isinstance(text, str) or not text.strip():
                continue  # skip null/empty text
            if not rec.get("is_subject") is True:
                continue  # skip non-subject entries
            record_id = rec.get("record_id")
            rec["media_kind"] = kind  # explicit voice/video kind
            transcript_map[record_id] = rec
    return transcript_map, bad


def _truncate_text(text, max_len=300):
    """Truncate text to max_len characters on a character boundary."""
    if text is None:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len]


def _text_source_quality(rec):
    """Get quality string for a transcript record."""
    quality = rec.get("quality", "corrected")
    return f"transcript_{quality}"


def extract_keyword_events(messages, groups_cfg, enabled_groups, transcript_map=None):
    """Extract keyword_event candidates."""
    candidates = []
    if not enabled_groups:
        return candidates

    # Build scannable items: messages + transcript clips
    scannable = []
    for msg in messages:
        if not is_subject(msg):
            continue
        text = msg.get("text", "")
        date = extract_date(msg.get("timestamp", ""))
        if not date:
            continue
        scannable.append({
            "type": "message",
            "record_id": msg.get("record_id"),
            "text": text,
            "timestamp": msg.get("timestamp", ""),
            "date": date,
            "chat_room": msg.get("chat_room"),
            "source": msg,
        })

    if transcript_map:
        for record_id, rec in transcript_map.items():
            text = rec.get("text", "")
            date = extract_date(rec.get("timestamp", ""))
            if not date:
                continue
            scannable.append({
                "type": "transcript",
                "record_id": record_id,
                "text": text,
                "timestamp": rec.get("timestamp", ""),
                "date": date,
                "chat_room": rec.get("chat_room"),
                "source": rec,
                "media_kind": rec.get("media_kind"),
            })

    # Group by (group, chat_room, date)
    clusters = defaultdict(list)
    for item in scannable:
        text = item["text"]
        for group in enabled_groups:
            keywords = groups_cfg.get("groups", {}).get(group, {}).get("keywords", [])
            if not keywords:
                continue
            for kw in keywords:
                if kw and kw in text:
                    clusters[(group, item["chat_room"], item["date"])].append(item)
                    break

    for (group, chat_room, date), items in clusters.items():
        items_sorted = sorted(
            items,
            key=lambda m: m["timestamp"],
        )
        excerpts = []
        for item in items_sorted[:5]:
            if item["type"] == "message":
                excerpts.append({
                    "record_id": item["record_id"],
                    "text": _truncate_text(item["text"]),
                    "timestamp": item["timestamp"],
                })
            else:
                excerpt = {
                    "record_id": item["record_id"],
                    "text": _truncate_text(item["text"]),
                    "timestamp": item["timestamp"],
                    "text_source": _text_source_quality(item["source"]),
                    "media": item.get("media_kind"),
                }
                excerpts.append(excerpt)
        source_records = [item["record_id"] for item in items_sorted if item["record_id"]]
        counts = {"hits": len(items)}
        group_label = groups_cfg.get("groups", {}).get(group, {}).get("label", group)
        candidates.append(
            make_candidate(
                "keyword_event",
                f"关键词事件-{group_label}",
                date,
                chat_room,
                group,
                excerpts,
                counts,
                source_records,
                key_suffix=f"{group}|{chat_room or ''}",
            )
        )
    return candidates


def extract_burst_days(messages, burst_min, p95_daily):
    """Extract burst_day candidates."""
    if burst_min <= 0:
        burst_min = 0

    daily_counts = Counter()
    daily_messages = defaultdict(list)
    for msg in messages:
        if not is_subject(msg):
            continue
        date = extract_date(msg.get("timestamp", ""))
        if not date:
            continue
        daily_counts[date] += 1
        daily_messages[date].append(msg)

    threshold = max(burst_min, p95_daily)

    candidates = []
    for date, count in daily_counts.items():
        if count >= threshold:
            msgs_sorted = sorted(
                daily_messages[date],
                key=lambda m: m.get("timestamp", ""),
            )
            excerpts = []
            seen_ids = set()
            # Earliest 3
            for m in msgs_sorted[:3]:
                rid = m.get("record_id")
                if rid and rid not in seen_ids:
                    seen_ids.add(rid)
                    excerpts.append({
                        "record_id": rid,
                        "text": _truncate_text(m.get("text", "")),
                        "timestamp": m.get("timestamp", ""),
                    })
            # Longest 2 by text length
            longest_2 = sorted(
                msgs_sorted,
                key=lambda m: len(m.get("text", "")),
                reverse=True,
            )[:2]
            for m in longest_2:
                rid = m.get("record_id")
                if rid and rid not in seen_ids:
                    seen_ids.add(rid)
                    excerpts.append({
                        "record_id": rid,
                        "text": _truncate_text(m.get("text", "")),
                        "timestamp": m.get("timestamp", ""),
                    })

            source_records = [m.get("record_id") for m in msgs_sorted if m.get("record_id")]
            candidates.append(
                make_candidate(
                    "burst_day",
                    "消息爆发日",
                    date,
                    None,
                    None,
                    excerpts,
                    {"messages": count},
                    source_records,
                )
            )
    return candidates


def extract_long_messages(messages, min_long):
    """Extract long_message candidates."""
    candidates = []
    for msg in messages:
        if not is_subject(msg):
            continue
        text = msg.get("text", "")
        if len(text) >= min_long:
            date = extract_date(msg.get("timestamp", ""))
            if not date:
                continue
            rid = msg.get("record_id")
            excerpts = [{
                "record_id": rid,
                "text": _truncate_text(text),
                "timestamp": msg.get("timestamp", ""),
            }]
            candidates.append(
                make_candidate(
                    "long_message",
                    "长消息",
                    date,
                    msg.get("chat_room"),
                    None,
                    excerpts,
                    {"length": len(text)},
                    [rid],
                    key_suffix=rid,
                )
            )
    return candidates


def extract_voice_long(voice_manifest_path: Path, min_voice_sec, transcript_map=None):
    """Extract voice_long candidates from voice manifest."""
    candidates = []
    if not voice_manifest_path.exists():
        print(f"[warn] 语音 manifest 不存在，跳过 voice_long 信号: {voice_manifest_path}")
        return candidates, 0

    bad = 0
    with voice_manifest_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec, err = _parse_manifest_line(line)
            if rec is None:
                bad += err
                continue
            if rec.get("record_type") != "media_item":
                continue
            if rec.get("media_type") != "audio":
                continue
            if not is_subject(rec):
                continue
            duration_ms = rec.get("duration_ms", 0)
            if duration_ms >= min_voice_sec * 1000:
                date = extract_date(rec.get("timestamp", ""))
                if not date:
                    continue
                rid = rec.get("record_id")
                file_ref = rec.get("file_ref", "")
                excerpt = {
                    "record_id": rid,
                    "file_ref": file_ref,
                    "duration_ms": duration_ms,
                    "sender_alias": rec.get("sender_alias"),
                    "timestamp": rec.get("timestamp", ""),
                }
                # Enrich with transcript if available
                if transcript_map and rid in transcript_map:
                    trec = transcript_map[rid]
                    text = trec.get("text", "")
                    if isinstance(text, str) and text.strip():
                        excerpt["text"] = _truncate_text(text)
                        excerpt["text_source"] = _text_source_quality(trec)

                title = None
                if transcript_map and rid in transcript_map:
                    text = transcript_map[rid].get("text", "")
                    if isinstance(text, str) and text:
                        title = f"{date} 长语音：{text[:18]}…"

                if title is None:
                    # Use default title from make_candidate
                    candidates.append(
                        make_candidate(
                            "voice_long",
                            "长语音",
                            date,
                            rec.get("chat_room"),
                            None,
                            [excerpt],
                            {"duration_ms": duration_ms},
                            [rid],
                            key_suffix=rid,
                        )
                    )
                else:
                    # Build with custom title
                    aux_key = f"{date}|{rid}"
                    hash_input = f"voice_long|{aux_key}".encode("utf-8")
                    candidate_id = hashlib.sha256(hash_input).hexdigest()[:16]
                    candidates.append({
                        "candidate_id": candidate_id,
                        "kind": "voice_long",
                        "kind_label": "长语音",
                        "date": date,
                        "chat_room": rec.get("chat_room"),
                        "group": None,
                        "title": title,
                        "excerpts": [excerpt],
                        "counts": {"duration_ms": duration_ms},
                        "tier": 2,
                        "status": "pending",
                        "provenance": {
                            "generator": "extract_memory_candidates",
                            "version": "1.0.0",
                            "source_records": [rid],
                        },
                    })
    return candidates, bad


def extract_media_bursts(media_manifest_paths, media_burst, transcript_map=None):
    """Extract media_burst candidates from combined manifests."""
    candidates = []
    if not any(p.exists() for p in media_manifest_paths):
        print("[warn] 媒体 manifests 均不存在，跳过 media_burst 信号")
        return candidates, 0

    all_media = []
    total_bad = 0
    for path in media_manifest_paths:
        if not path.exists():
            print(f"[warn] 媒体 manifest 不存在: {path}")
            continue
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec, err = _parse_manifest_line(line)
                if rec is None:
                    total_bad += err
                    continue
                if rec.get("record_type") != "media_item":
                    continue
                if rec.get("media_type") not in ("audio", "video"):
                    continue
                all_media.append(rec)

    daily_groups = defaultdict(list)
    for rec in all_media:
        date = extract_date(rec.get("timestamp", ""))
        if not date:
            continue
        daily_groups[date].append(rec)

    for date, items in daily_groups.items():
        if len(items) >= media_burst:
            items_sorted = sorted(items, key=lambda m: m.get("timestamp", ""))
            subject_count = sum(1 for i in items if is_subject(i))
            excerpts = []
            for i in items_sorted[:5]:
                excerpt = {
                    "record_id": i.get("record_id"),
                    "media_type": i.get("media_type"),
                    "file_ref": i.get("file_ref"),
                    "sender_alias": i.get("sender_alias"),
                    "is_subject": is_subject(i),
                    "timestamp": i.get("timestamp", ""),
                }
                # Enrich with transcript if available
                rid = i.get("record_id")
                if transcript_map and rid in transcript_map:
                    trec = transcript_map[rid]
                    text = trec.get("text", "")
                    if isinstance(text, str) and text.strip():
                        excerpt["text"] = _truncate_text(text)
                        excerpt["text_source"] = _text_source_quality(trec)
                excerpts.append(excerpt)
            source_records = [i.get("record_id") for i in items if i.get("record_id")]
            candidates.append(
                make_candidate(
                    "media_burst",
                    "媒体爆发",
                    date,
                    None,
                    None,
                    excerpts,
                    {"total": len(items), "subject": subject_count},
                    source_records,
                )
            )
    return candidates, total_bad


def compute_p95_daily(messages):
    """Compute P95 of daily subject message counts."""
    daily_counts = Counter()
    for msg in messages:
        if not is_subject(msg):
            continue
        date = extract_date(msg.get("timestamp", ""))
        if not date:
            continue
        daily_counts[date] += 1

    if not daily_counts:
        return 0

    counts_sorted = sorted(daily_counts.values())
    n = len(counts_sorted)
    idx = max(0, math.ceil(0.95 * n) - 1)
    return counts_sorted[idx]


def load_keywords_config(path: Path):
    """Load keywords config, return data or None on error."""
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"[error] 关键词配置加载失败: {e}")
        return None


def load_uif_messages(uif_path: Path):
    """Load validated subject messages from UIF file."""
    messages = []
    bad = 0
    with uif_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec, err = _parse_uif_line(line)
            if rec is None:
                bad += err
                continue
            messages.append(rec)
    return messages, bad


def guard_transcript_path(transcript_path: Path, person: str) -> bool:
    """Guard against raw-subtree input for transcript files.

    Returns True if the path is allowed, False if it must be rejected.
    """
    resolved = transcript_path.resolve()
    raw_root = (Path(__file__).resolve().parent.parent / "people" / person / "raw").resolve()
    if resolved == raw_root or raw_root in resolved.parents:
        print(f"[error] 转录文件不能位于 raw 子树下: {resolved}")
        return False
    return True


def main():
    parser = argparse.ArgumentParser(
        description="从 UIF 消息 + 媒体 manifest 提取记忆卡片候选"
    )
    parser.add_argument("--person", required=True, help="人物标识")
    parser.add_argument('--relationship-id', help='显式范围，启用 v2 证据合同')
    parser.add_argument("--uif", type=Path, help="UIF 消息 JSONL 路径")
    parser.add_argument("--voice-manifest", type=Path, help="语音 manifest 路径")
    parser.add_argument("--video-manifest", type=Path, help="视频 manifest 路径")
    parser.add_argument("--voice-transcripts", type=Path, help="语音转录 JSONL 路径")
    parser.add_argument("--video-transcripts", type=Path, help="视频转录 JSONL 路径")
    parser.add_argument("--keywords", type=Path, help="关键词配置路径")
    parser.add_argument("--kw-groups", default="family_events,health", help="参与挖掘的组")
    parser.add_argument("--min-long", type=int, default=100, help="长消息字符阈值")
    parser.add_argument("--burst-min", type=int, default=20, help="爆发日最小条数")
    parser.add_argument("--min-voice-sec", type=int, default=30, help="长语音阈值")
    parser.add_argument("--media-burst", type=int, default=3, help="同日媒体条数阈值")
    parser.add_argument("--max-candidates", type=int, default=150, help="总量上限")
    parser.add_argument("--quota", default="keyword_event=0.40,media_burst=0.15,burst_day=0.15,voice_long=0.15,long_message=0.15", help="按 kind 配额比例")
    parser.add_argument("--out", type=Path, help="输出路径")
    args = parser.parse_args()
    if args.relationship_id and (not args.uif or not args.out):
        parser.error('v2 requires explicit --uif and --out')

    # Validate person
    if not re.match(r"^[a-z0-9_-]{1,64}$", args.person):
        print("[error] person 标识不合法")
        return 2

    # Parse and validate quota
    valid_kinds = {"keyword_event", "media_burst", "burst_day", "voice_long", "long_message"}
    quota_map = {}
    try:
        for item in args.quota.split(","):
            item = item.strip()
            if not item:
                continue
            kind, ratio_str = item.split("=", 1)
            kind = kind.strip()
            ratio = float(ratio_str.strip())
            if kind not in valid_kinds:
                print(f"[error] 未知 kind: {kind}")
                return 2
            if not math.isfinite(ratio) or ratio <= 0:
                print(f"[error] kind {kind} 比例必须为正的有限数")
                return 2
            if kind in quota_map:
                print(f"[error] --quota 重复指定 kind: {kind}")
                return 2
            quota_map[kind] = ratio
        total_ratio = sum(quota_map.values())
        if total_ratio > 1.0 + 1e-6:
            print(f"[error] 配额比例总和超过 1.0: {total_ratio:.4f}")
            return 2
    except (ValueError, KeyError) as e:
        print(f"[error] 配额参数格式错误: {e}")
        return 2

    # Repo root
    repo_root = Path(__file__).resolve().parent.parent

    # Default paths
    default_uif = repo_root / "people" / args.person / "normalized" / "wechat_messages.uif.jsonl"
    default_voice = repo_root / "people" / args.person / "normalized" / "wechat_voice_manifest.jsonl"
    default_video = repo_root / "people" / args.person / "normalized" / "wechat_video_manifest.jsonl"
    default_kw = repo_root / "tools" / "persona_keywords.zh.json"
    default_out = repo_root / "people" / args.person / "memories" / "candidates.jsonl"
    default_voice_transcripts = repo_root / "people" / args.person / "normalized" / "voice_transcripts.jsonl"
    default_video_transcripts = repo_root / "people" / args.person / "normalized" / "video_transcripts.jsonl"

    uif_path = args.uif if args.uif else default_uif
    voice_path = args.voice_manifest if args.voice_manifest else default_voice
    video_path = args.video_manifest if args.video_manifest else default_video
    kw_path = args.keywords if args.keywords else default_kw
    out_path = args.out if args.out else default_out
    voice_transcripts_path = args.voice_transcripts if args.voice_transcripts else default_voice_transcripts
    video_transcripts_path = args.video_transcripts if args.video_transcripts else default_video_transcripts

    # v2 不扫描现役默认媒体或转录；只消费本次明确选择的输入。
    if args.relationship_id:
        absent = args.uif.parent / '__unused_v2_media__'
        voice_path = args.voice_manifest or absent
        video_path = args.video_manifest or absent
        voice_transcripts_path = args.voice_transcripts or absent
        video_transcripts_path = args.video_transcripts or absent
        if absent.exists():
            print('[error] reserved absent input exists')
            return 2

    # Resolve paths
    uif_path = uif_path.resolve()
    voice_path = voice_path.resolve()
    video_path = video_path.resolve()
    kw_path = kw_path.resolve()
    out_path = out_path.resolve()
    voice_transcripts_path = voice_transcripts_path.resolve()
    video_transcripts_path = video_transcripts_path.resolve()

    # Guard transcript inputs against raw subtree
    if not guard_transcript_path(voice_transcripts_path, args.person):
        return 2
    if not guard_transcript_path(video_transcripts_path, args.person):
        return 2

    # Check UIF exists
    if not uif_path.exists():
        print(f"[error] UIF 文件不存在: {uif_path}")
        return 1

    # Load keywords config
    kw_config = load_keywords_config(kw_path)
    if kw_config is None:
        return 2

    # Validate groups
    enabled_groups = [g.strip() for g in args.kw_groups.split(",") if g.strip()]
    available_groups = list(kw_config.get("groups", {}).keys())
    for g in enabled_groups:
        if g not in available_groups:
            print(f"[error] 关键词组不存在: {g}")
            print(f"[info] 可用组: {', '.join(available_groups)}")
            return 2

    # Load messages
    messages, bad_lines = load_uif_messages(uif_path)
    source_index = defaultdict(list)
    try:
        for input_path in dict.fromkeys((uif_path, voice_path, video_path,
                                         voice_transcripts_path, video_transcripts_path)):
            if not input_path.exists():
                continue
            for line in input_path.read_text(encoding='utf-8').splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError('input must contain objects')
                if args.relationship_id:
                    if (record.get('person') != args.person or
                            args.relationship_id != args.person + '_' + str(record.get('viewpoint'))):
                        raise ValueError('source relationship mismatch')
                elif record.get('viewpoint', owner_participant()) != owner_participant():
                    raise ValueError('non-legacy source requires --relationship-id')
                if record.get('record_id'):
                    source_index[record['record_id']].append(record)
        if args.relationship_id and bad_lines:
            raise ValueError('invalid v2 source rows')
    except (ValueError, OSError) as exc:
        print('[error] invalid scoped source: ' + str(exc))
        return 2
    if bad_lines > 0:
        print(f"[warn] UIF 坏行数: {bad_lines}")

    # Load transcripts with explicit kind tags
    voice_transcript_map = {}
    video_transcript_map = {}
    voice_transcript_bad = 0
    video_transcript_bad = 0
    if voice_transcripts_path.exists():
        voice_transcript_map, voice_transcript_bad = load_transcripts(voice_transcripts_path, "voice")
        print(f"[info] voice_transcripts=loaded ({len(voice_transcript_map)} clips, {voice_transcript_bad} bad lines)")
    else:
        print(f"[info] voice_transcripts=absent")
    if video_transcripts_path.exists():
        video_transcript_map, video_transcript_bad = load_transcripts(video_transcripts_path, "video")
        print(f"[info] video_transcripts=loaded ({len(video_transcript_map)} clips, {video_transcript_bad} bad lines)")
    else:
        print(f"[info] video_transcripts=absent")
    
    # Merge transcript maps
    combined_transcript_map = dict(voice_transcript_map)
    combined_transcript_map.update(video_transcript_map)

    # P95 computation
    p95_daily = compute_p95_daily(messages)

    # Extract candidates
    all_candidates = []

    # keyword_event (now with transcripts)
    kw_candidates = extract_keyword_events(messages, kw_config, enabled_groups, combined_transcript_map)
    print(f"[info] keyword_event 候选: {len(kw_candidates)}")
    all_candidates.extend(kw_candidates)

    # burst_day
    burst_candidates = extract_burst_days(messages, args.burst_min, p95_daily)
    print(f"[info] burst_day 候选: {len(burst_candidates)}")
    all_candidates.extend(burst_candidates)

    # long_message
    long_candidates = extract_long_messages(messages, args.min_long)
    print(f"[info] long_message 候选: {len(long_candidates)}")
    all_candidates.extend(long_candidates)

    # voice_long
    voice_candidates, voice_bad = extract_voice_long(voice_path, args.min_voice_sec, combined_transcript_map)
    print(f"[info] voice_long 候選: {len(voice_candidates)}")
    if voice_bad > 0:
        print(f"[warn] 语音 manifest 坏行数: {voice_bad}")
    all_candidates.extend(voice_candidates)

    # media_burst
    media_candidates, media_bad = extract_media_bursts([voice_path, video_path], args.media_burst, combined_transcript_map)
    print(f"[info] media_burst 候选: {len(media_candidates)}")
    if media_bad > 0:
        print(f"[warn] 媒体 manifest 坏行数: {media_bad}")
    all_candidates.extend(media_candidates)

    # Sort
    sorted_candidates = sort_candidates(all_candidates)

    # Add has_asr_draft flag to candidates containing asr_draft transcripts
    for cand in sorted_candidates:
        has_asr = False
        for ex in cand.get("excerpts", []):
            ts = ex.get("text_source", "")
            if "asr_draft" in ts:
                has_asr = True
                break
        if has_asr:
            cand["has_asr_draft"] = True

    # Group by kind preserving kind priority order
    kind_order = {
        "keyword_event": 0,
        "media_burst": 1,
        "burst_day": 2,
        "voice_long": 3,
        "long_message": 4,
    }
    by_kind = defaultdict(list)
    for cand in sorted_candidates:
        by_kind[cand["kind"]].append(cand)

    # Initial quota allocation
    final_candidates = []
    quotas = {}
    for kind, ratio in quota_map.items():
        quotas[kind] = math.floor(args.max_candidates * ratio)
        final_candidates.extend(by_kind.get(kind, [])[:quotas[kind]])

    # Round-robin fill remaining seats
    remaining = args.max_candidates - len(final_candidates)
    if remaining > 0:
        for kind in sorted(by_kind.keys(), key=lambda k: kind_order.get(k, 99)):
            if remaining <= 0:
                break
            existing = sum(1 for c in final_candidates if c["kind"] == kind)
            total_available = len(by_kind.get(kind, []))
            if existing < total_available:
                final_candidates.append(by_kind[kind][existing])
                remaining -= 1

        # Continue round-robin for any additional remaining seats
        while remaining > 0:
            progressed = False
            for kind in sorted(by_kind.keys(), key=lambda k: kind_order.get(k, 99)):
                if remaining <= 0:
                    break
                existing = sum(1 for c in final_candidates if c["kind"] == kind)
                total_available = len(by_kind.get(kind, []))
                if existing < total_available:
                    final_candidates.append(by_kind[kind][existing])
                    remaining -= 1
                    progressed = True
            if not progressed:
                break

    # Final sort by kind priority and internal order
    final_candidates = sort_candidates(final_candidates)
    if args.relationship_id:
        try:
            scoped = []
            for cand in final_candidates:
                evidence = []
                for rid in cand['provenance']['source_records']:
                    observations = source_index[rid]
                    if not observations:
                        raise ValueError('missing full evidence')
                    evidence.append({'record_id': rid, 'person': args.person,
                                     'viewpoint': observations[0]['viewpoint'],
                                     'observations': observations})
                scoped.append(scope_candidate(cand, args.person, args.relationship_id, evidence))
            final_candidates = scoped
            if scoped:
                dataset_fingerprint(scoped)
        except ValueError as exc:
            print('[error] invalid candidate evidence: ' + str(exc))
            return 2

    # Re-apply has_asr_draft after sort (already on candidates)
    # Report per-kind truncation
    print("[info] 截断报告:")
    for kind in ("keyword_event", "media_burst", "burst_day", "voice_long", "long_message"):
        total = sum(1 for c in all_candidates if c["kind"] == kind)
        quota = quotas.get(kind, 0)
        kept = sum(1 for c in final_candidates if c["kind"] == kind)
        discarded = total - kept
        print(f"  {kind}: 生成={total} 配额={quota} 保留={kept} 丢弃={discarded}")
    print(f"[info] 最终候选数: {len(final_candidates)}")

    # Output directory
    out_parent = out_path.parent
    try:
        original_out = args.out or out_path
        preflight_outputs([original_out, original_out.with_suffix(original_out.suffix + '.part')],
                          [uif_path, voice_path, video_path, kw_path,
                           voice_transcripts_path, video_transcripts_path])
    except ValueError as exc:
        print('[error] unsafe output: ' + str(exc))
        return 2
    memories_root = (repo_root / "people" / args.person / "memories").resolve()

    # Safety check: ensure output is within memories subtree
    def path_is_within(child: Path, parent: Path) -> bool:
        child = child.resolve()
        parent = parent.resolve()
        for p in child.parents:
            if p == parent:
                return True
        return False

    if not path_is_within(out_path, memories_root):
        print(f"[error] 输出路径越界: {out_path}")
        return 2

    if args.relationship_id and (out_path.exists() or out_path == default_out.resolve()):
        print('[error] v2 requires a new output file; existing legacy cards are frozen')
        return 2

    out_parent.mkdir(parents=True, exist_ok=True)

    # Write atomically
    part_path = out_path.with_suffix(out_path.suffix + ".part")
    try:
        with part_path.open("w", encoding="utf-8") as f:
            for cand in final_candidates:
                f.write(json.dumps(cand, ensure_ascii=False) + "\n")
        os.replace(part_path, out_path)
    except (OSError, IOError) as e:
        print(f"[error] 写入失败: {e}")
        if part_path.exists():
            part_path.unlink()
        return 1

    # Summary
    kind_counts = Counter(c["kind"] for c in final_candidates)
    print("[info] 各 kind 生成数:")
    for kind in ("keyword_event", "media_burst", "burst_day", "voice_long", "long_message"):
        total = sum(1 for c in all_candidates if c["kind"] == kind)
        kept = kind_counts.get(kind, 0)
        print(f"  {kind}: 生成={total} 保留={kept}")

    print(f"[info] 最终写入 {len(final_candidates)} 条候选到: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
