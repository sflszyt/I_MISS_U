#!/usr/bin/env python3
"""Interactive rhythm statistics builder for a person's WeChat messages.

Skipped records documentation:
- skipped_records is counted precisely using per-section counters.
- A record is counted as skipped by a section when it is excluded from that
  section's statistics due to missing fields, invalid types, or timestamp
  parse failures.
- "total" is the sum of all per-section skip counts.
- "by_section" maps each section name to its skip count.
"""

import argparse
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
TIMESTAMP_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})")
FANG_BRACKET_RE = re.compile(r"\[[一-龥A-Za-z]{1,8}\]")
LENGTH_BUCKETS = [(1, 5), (6, 15), (16, 40), (41, 100), (100, None)]
EMOJI_PATTERN = re.compile(
    "[\U0001F300-\U0001FAFF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "\U00002700-\U000027BF"
    "\U00002B00-\U00002BFF"
    "\U0000FE00-\U0000FE0F"
    "\U00002600-\U000026FF"
    "]+"
)
VOICE_KEYWORDS = ("voice", "语音", "audio", "ptt")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build interaction rhythm stats")
    parser.add_argument("--person", required=True, help="person slug")
    parser.add_argument("--repo-root", default=None, help="repository root (default: script parent)")
    args = parser.parse_args()
    if not SLUG_RE.match(args.person):
        sys.exit(f"ERROR: invalid person slug: {args.person}")
    if args.repo_root is None:
        args.repo_root = str(Path(__file__).resolve().parent.parent)
    return args


def median(values: list) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    n = len(values)
    if n % 2 == 1:
        return float(values[n // 2])
    return (values[n // 2 - 1] + values[n // 2]) / 2.0


def percentile(values: list, p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    if p <= 0.0:
        return float(values[0])
    if p >= 100.0:
        return float(values[-1])
    k = (len(values) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(values[k])
    lower = values[f]
    upper = values[c]
    return float(lower + (upper - lower) * (k - f))


def parse_timestamp(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    m = TIMESTAMP_RE.match(value)
    if not m:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        try:
            dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S%z")
        except ValueError:
            try:
                dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S%z")
            except ValueError:
                try:
                    # Try without tz offset, assume +08:00
                    dt = datetime.strptime(m.group(1) + " " + m.group(2), "%Y-%m-%d %H:%M:%S")
                    dt = dt.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=8)))
                except ValueError:
                    return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=8)))
    return dt


def compute_totals(subject_records, skipped_counter) -> dict:
    content_counter = Counter()
    room_counter = Counter()
    skipped_content = 0
    skipped_room = 0
    for r in subject_records:
        ct = r.get("content_type")
        if ct:
            content_counter[ct] += 1
        else:
            skipped_content += 1
        rl = r.get("room_label")
        if rl:
            room_counter[rl] += 1
        else:
            skipped_room += 1
    skipped_counter["totals_content_type"] += skipped_content
    skipped_counter["totals_room_label"] += skipped_room
    return {
        "message_count": len(subject_records),
        "by_content_type": dict(sorted(content_counter.items())),
        "by_room_label": dict(sorted(room_counter.items())),
    }


def compute_text_stats(subject_records, skipped_counter) -> dict:
    lengths = []
    buckets = [0] * 5
    skipped_missing = 0
    skipped_type = 0
    for r in subject_records:
        if r.get("content_type") != "text":
            continue
        text = r.get("text")
        if text is None:
            skipped_missing += 1
            continue
        if not isinstance(text, str):
            skipped_type += 1
            continue
        L = len(text)
        lengths.append(L)
        if L <= 5:
            buckets[0] += 1
        elif L <= 15:
            buckets[1] += 1
        elif L <= 40:
            buckets[2] += 1
        elif L <= 100:
            buckets[3] += 1
        else:
            buckets[4] += 1
    skipped_counter["text_stats_missing"] += skipped_missing
    skipped_counter["text_stats_type"] += skipped_type
    if not lengths:
        return {"mean": 0.0, "median": 0.0, "p90": 0.0, "buckets": {"1-5": 0, "6-15": 0, "16-40": 0, "41-100": 0, "100+": 0}, "sample_count": 0}
    return {
        "mean": float(sum(lengths) / len(lengths)),
        "median": median(lengths),
        "p90": percentile(lengths, 90),
        "buckets": {"1-5": buckets[0], "6-15": buckets[1], "16-40": buckets[2], "41-100": buckets[3], "100+": buckets[4]},
        "sample_count": len(lengths),
    }


def compute_time_pattern(subject_records, skipped_counter) -> dict:
    hour_counts = [0] * 24
    weekday_counts = [0] * 7
    skipped_timestamp = 0
    for r in subject_records:
        dt = parse_timestamp(r.get("timestamp"))
        if dt:
            hour_counts[dt.hour] += 1
            weekday_counts[dt.weekday()] += 1
        else:
            skipped_timestamp += 1
    skipped_counter["time_pattern_timestamp"] += skipped_timestamp
    top3 = sorted(range(24), key=lambda h: hour_counts[h], reverse=True)[:3]
    top3 = [{"hour": h, "count": hour_counts[h]} for h in top3]
    return {
        "hour_histogram": [{"hour": i, "count": c} for i, c in enumerate(hour_counts)],
        "weekday_histogram": [{"day": i, "count": c} for i, c in enumerate(weekday_counts)],
        "top_hours": top3,
    }


def compute_burst(subject_records, skipped_counter) -> dict:
    """Group consecutive subject messages by session (chat_room) with <=60s gap."""
    # Sort by chat_room then timestamp
    by_room = defaultdict(list)
    skipped_timestamp = 0
    for r in subject_records:
        room = r.get("chat_room") or r.get("room_label") or "unknown"
        dt = parse_timestamp(r.get("timestamp"))
        if dt:
            by_room[room].append((dt, r))
        else:
            skipped_timestamp += 1
    skipped_counter["burst_timestamp"] += skipped_timestamp
    burst_lengths = []
    max_burst = 0
    for room, items in by_room.items():
        items.sort(key=lambda x: x[0])
        streak = 1
        for i in range(1, len(items)):
            delta = (items[i][0] - items[i - 1][0]).total_seconds()
            if 0 < delta and delta <= 60:
                streak += 1
            else:
                burst_lengths.append(streak)
                max_burst = max(max_burst, streak)
                streak = 1
        if items:
            burst_lengths.append(streak)
            max_burst = max(max_burst, streak)
    if not burst_lengths:
        return {"distribution": {"1": 0, "2": 0, "3": 0, "4": 0, "5+": 0}, "longest_burst": 0, "burst_count": 0}
    dist = {"1": 0, "2": 0, "3": 0, "4": 0, "5+": 0}
    for bl in burst_lengths:
        if bl == 1:
            dist["1"] += 1
        elif bl == 2:
            dist["2"] += 1
        elif bl == 3:
            dist["3"] += 1
        elif bl == 4:
            dist["4"] += 1
        else:
            dist["5+"] += 1
    return {"distribution": dist, "longest_burst": max_burst, "burst_count": len(burst_lengths)}


def compute_reply_latency(records, subject_set, skipped_counter) -> dict:
    # Private chat room laurawang001
    # Look for subject messages immediately following a non-subject message within 1h
    # We need chronological order in that room
    room_msgs = []
    skipped_room = 0
    skipped_timestamp = 0
    for r in records:
        room = r.get("chat_room") or r.get("room_label")
        if not isinstance(room, str):
            skipped_room += 1
            continue
        if "laurawang001" not in room:
            continue
        dt = parse_timestamp(r.get("timestamp"))
        if dt:
            room_msgs.append((dt, r))
        else:
            skipped_timestamp += 1
    skipped_counter["reply_latency_room"] += skipped_room
    skipped_counter["reply_latency_timestamp"] += skipped_timestamp
    room_msgs.sort(key=lambda x: x[0])
    latencies = []
    for i in range(1, len(room_msgs)):
        prev, cur = room_msgs[i - 1][1], room_msgs[i][1]
        if cur.get("sender") == "subject" and prev.get("sender") != "subject":
            delta = (room_msgs[i][0] - room_msgs[i - 1][0]).total_seconds()
            if 0 <= delta <= 3600:
                latencies.append(delta)
    if not latencies:
        return {"median_sec": 0.0, "p90_sec": 0.0, "sample_count": 0}
    return {
        "median_sec": median(latencies),
        "p90_sec": percentile(latencies, 90),
        "sample_count": len(latencies),
    }


def compute_punctuation(subject_records, skipped_counter) -> dict:
    exclaim = quest = ellipsis = tilde = period = 0
    no_end_punct = 0
    text_count = 0
    skipped_missing = 0
    skipped_type = 0
    for r in subject_records:
        if r.get("content_type") != "text":
            continue
        text = r.get("text")
        if text is None:
            skipped_missing += 1
            continue
        if not isinstance(text, str):
            skipped_type += 1
            continue
        text_count += 1
        if "！" in text or "!" in text:
            exclaim += 1
        if "？" in text or "?" in text:
            quest += 1
        if "…" in text:
            ellipsis += 1
        if "～" in text or "~" in text:
            tilde += 1
        if "。" in text:
            period += 1
        if text and text[-1] not in "！？。…～!?~.":
            no_end_punct += 1
    skipped_counter["punctuation_missing"] += skipped_missing
    skipped_counter["punctuation_type"] += skipped_type
    if text_count == 0:
        return {"per_100": {"!": 0, "?": 0, "...": 0, "~": 0, ".": 0}, "no_end_punct_ratio": 0.0, "sample_count": 0}
    return {
        "per_100": {
            "!": float(exclaim * 100 / text_count),
            "?": float(quest * 100 / text_count),
            "...": float(ellipsis * 100 / text_count),
            "~": float(tilde * 100 / text_count),
            ".": float(period * 100 / text_count),
        },
        "no_end_punct_ratio": float(no_end_punct / text_count),
        "sample_count": text_count,
    }


def compute_catchphrases(subject_records, skipped_counter) -> dict:
    counter = Counter()
    skipped_missing = 0
    skipped_type = 0
    for r in subject_records:
        if r.get("content_type") != "text":
            continue
        text = r.get("text")
        if text is None:
            skipped_missing += 1
            continue
        if not isinstance(text, str):
            skipped_type += 1
            continue
        if 2 <= len(text) <= 6:
            counter[text] += 1
    skipped_counter["catchphrases_missing"] += skipped_missing
    skipped_counter["catchphrases_type"] += skipped_type
    top30 = [(phrase, cnt) for phrase, cnt in counter.items() if cnt >= 3]
    top30.sort(key=lambda x: (-x[1], x[0]))
    return [{"phrase": phrase, "count": cnt} for phrase, cnt in top30[:30]]


def compute_emoji(subject_records, skipped_counter) -> dict:
    bracket_counter = Counter()
    total_emoji = 0
    skipped_missing = 0
    skipped_type = 0
    for r in subject_records:
        text = r.get("text")
        if text is None:
            skipped_missing += 1
            continue
        if not isinstance(text, str):
            skipped_type += 1
            continue
        brackets = FANG_BRACKET_RE.findall(text)
        bracket_counter.update(brackets)
        total_emoji += len(EMOJI_PATTERN.findall(text))
    skipped_counter["emoji_missing"] += skipped_missing
    skipped_counter["emoji_type"] += skipped_type
    top20 = bracket_counter.most_common(20)
    return {
        "top20_bracket": [{"tag": tag, "count": c} for tag, c in top20],
        "unicode_emoji_count": total_emoji,
    }


def compute_voice(subject_records, skipped_counter) -> dict:
    voice_records = []
    duration_values_ms = []
    duration_values_sec = []
    skipped_ct = 0
    skipped_duration = 0
    for r in subject_records:
        ct = r.get("content_type")
        if not isinstance(ct, str):
            skipped_ct += 1
            continue
        if ct in VOICE_KEYWORDS or "voice" in ct.lower() or "语音" in ct:
            voice_records.append(r)
            dur = r.get("duration_ms") or r.get("duration") or r.get("duration_sec") or r.get("voice_duration")
            if isinstance(dur, (int, float)):
                duration_values_ms.append(float(dur))
            else:
                dur_sec = r.get("duration_sec")
                if isinstance(dur_sec, (int, float)):
                    duration_values_sec.append(float(dur_sec))
                else:
                    skipped_duration += 1
    skipped_counter["voice_content_type"] += skipped_ct
    skipped_counter["voice_duration"] += skipped_duration
    ratio = len(voice_records) / len(subject_records) if subject_records else 0.0
    result = {"ratio": ratio, "voice_message_count": len(voice_records), "duration": None}
    
    # Combine ms and sec values: convert ms to seconds
    all_sec = [v / 1000.0 for v in duration_values_ms] + duration_values_sec
    if all_sec:
        result["duration"] = {
            "mean_sec": float(sum(all_sec) / len(all_sec)),
            "median_sec": median(all_sec),
            "sample_count": len(all_sec),
        }
    else:
        result["duration"] = "not available (no duration field)"
    return result


def atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def main() -> None:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    person_slug = args.person
    person_dir = (repo_root / "people" / person_slug).resolve()
    
    # Validate paths anchor
    expected_prefix = (repo_root / "people" / person_slug).resolve()
    if not person_dir.is_relative_to(expected_prefix):
        sys.exit(f"ERROR: person_dir {person_dir} is outside allowed path {expected_prefix}")
    
    input_path = person_dir / "normalized" / "wechat_messages.uif.jsonl"
    if not input_path.is_file():
        sys.exit(f"ERROR: input file not found: {input_path}")

    records = []
    skipped_parse = 0
    skipped_non_dict = 0
    try:
        with open(input_path, "r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as e:
                    sys.exit(f"ERROR: line {lineno}: invalid JSON: {e}")
                records.append(record)
                if not isinstance(record, dict):
                    skipped_non_dict += 1
                    sys.exit(f"ERROR: line {lineno}: record is not an object")
    except OSError as e:
        sys.exit(f"ERROR: cannot read {input_path}: {e}")

    subject_records = []
    for r in records:
        if r.get("sender") == "subject":
            subject_records.append(r)

    skipped_counter = Counter()
    skipped_counter["parse"] += skipped_parse
    skipped_counter["non_dict"] += skipped_non_dict
    
    totals = compute_totals(subject_records, skipped_counter)
    text_stats = compute_text_stats(subject_records, skipped_counter)
    time_pattern = compute_time_pattern(subject_records, skipped_counter)
    burst = compute_burst(subject_records, skipped_counter)
    reply = compute_reply_latency(records, set(), skipped_counter)
    punct = compute_punctuation(subject_records, skipped_counter)
    catch = compute_catchphrases(subject_records, skipped_counter)
    emoji = compute_emoji(subject_records, skipped_counter)
    voice = compute_voice(subject_records, skipped_counter)
    
    # Build skipped_records dictionary with exact counts
    skipped_total = sum(skipped_counter.values())
    skipped_dict = {
        "total": skipped_total,
        "by_section": dict(sorted(skipped_counter.items())),
    }

    output = {
        "person": person_slug,
        "tier": 2,
        "derived_from": "wechat_messages.uif.jsonl",
        "message_count_subject": len(subject_records),
        "generated_at": datetime.now().astimezone().isoformat(),
        "totals": totals,
        "text_stats": text_stats,
        "time_pattern": time_pattern,
        "burst": burst,
        "reply_latency": reply,
        "punctuation_habits": punct,
        "catchphrases": catch,
        "emoji_usage": emoji,
        "voice_habit": voice,
        "skipped_records": skipped_dict,
    }

    out1 = (person_dir / "persona" / "rhythm.json").resolve()
    out2 = (person_dir / "archive_out" / "data" / "rhythm.json").resolve()
    
    # Validate output paths anchor
    if not out1.is_relative_to(expected_prefix):
        sys.exit(f"ERROR: output path {out1} is outside allowed directory {expected_prefix}")
    if not out2.is_relative_to(expected_prefix):
        sys.exit(f"ERROR: output path {out2} is outside allowed directory {expected_prefix}")
    
    atomic_write_json(out1, output)
    atomic_write_json(out2, output)

    # Verify both files match
    with open(out1, "r", encoding="utf-8") as f1, open(out2, "r", encoding="utf-8") as f2:
        d1 = json.load(f1)
        d2 = json.load(f2)
    if d1 != d2:
        sys.exit("ERROR: produced rhythm.json files differ")

    print(f"Subject messages: {len(subject_records)}")
    print(f"Totals section: {len(subject_records)} samples")
    print(f"Text stats: {text_stats['sample_count']} samples")
    print(f"Time pattern: {len(subject_records)} samples")
    print(f"Burst: {burst['burst_count']} bursts ({len(subject_records)} messages)")
    print(f"Reply latency: {reply['sample_count']} samples")
    print(f"Punctuation: {punct['sample_count']} samples")
    print(f"Catchphrases: {len(catch)} entries")
    print(f"Emoji: {emoji['unicode_emoji_count']} unicode emoji, top20 brackets found")
    print(f"Voice: {voice['voice_message_count']} voice messages")
    print(f"Skipped: {skipped_dict['total']} total, {skipped_dict['by_section']}")
    print("Output written to persona/rhythm.json and archive_out/data/rhythm.json")


if __name__ == "__main__":
    main()
