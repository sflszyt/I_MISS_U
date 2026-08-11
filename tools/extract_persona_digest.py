# -*- coding: utf-8 -*-
"""Deterministically extract persona drafting digest from UIF JSONL."""

import argparse
import json
import os
import random
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def resolve_repo_root():
    """Return repo root as the parent of the tools/ directory."""
    return Path(__file__).resolve().parent.parent


def parse_year(ts_str):
    """Extract year from ISO timestamp string, or None on failure."""
    try:
        return str(datetime.fromisoformat(ts_str).year)
    except (ValueError, TypeError):
        return None


def load_keywords(path):
    """Load keyword group config from JSON file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except OSError as e:
        print(f"ERROR: cannot read keywords file: {e}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid keywords JSON: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(data, dict):
        print(f"ERROR: keywords file {path} must contain a JSON object at top level", file=sys.stderr)
        sys.exit(1)
    groups = data.get("groups")
    if not isinstance(groups, dict) or not groups:
        print(f"ERROR: keywords file {path} must contain non-empty 'groups' object", file=sys.stderr)
        sys.exit(1)
    for gname, ginfo in groups.items():
        if not isinstance(ginfo, dict):
            print(f"ERROR: keywords file {path} group {gname!r} must be an object", file=sys.stderr)
            sys.exit(1)
        if "keywords" not in ginfo or not isinstance(ginfo["keywords"], list):
            print(f"ERROR: keywords file {path} group {gname!r} must contain a 'keywords' list", file=sys.stderr)
            sys.exit(1)
        for kw in ginfo["keywords"]:
            if not isinstance(kw, str) or not kw:
                print(f"ERROR: keywords file {path} group {gname!r} contains invalid keyword element: {kw!r}", file=sys.stderr)
                sys.exit(1)
        if "label" not in ginfo or not isinstance(ginfo["label"], str):
            print(f"ERROR: keywords file {path} group {gname!r} must contain a string 'label'", file=sys.stderr)
            sys.exit(1)
    return groups


def validate_person(person):
    """Validate person slug, exit 2 on failure."""
    if not re.fullmatch(r"[a-z0-9_-]{1,64}", person):
        print(f"ERROR: invalid --person value: {person!r}", file=sys.stderr)
        sys.exit(2)


def check_path_within(path, root):
    """Assert output path lies within root (strict parent-chain check)."""
    resolved = path.resolve()
    rroot = root.resolve()
    cur = resolved.parent
    while True:
        if cur == rroot:
            return resolved
        if cur == cur.parent:
            break
        cur = cur.parent
    print(f"ERROR: output path {resolved} is outside {rroot}", file=sys.stderr)
    sys.exit(2)


def parse_args():
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Extract persona digest from UIF JSONL")
    parser.add_argument("--person", required=True, help="Person slug")
    parser.add_argument("--uif", type=str, default=None)
    parser.add_argument("--out", type=str, default=None)
    parser.add_argument("--keywords", type=str, default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--samples-per-year", type=int, default=10)
    parser.add_argument("--longest-per-year", type=int, default=5)
    parser.add_argument("--threads-per-year", type=int, default=3)
    parser.add_argument("--thread-window", type=int, default=20)
    parser.add_argument("--kw-samples-per-group", type=int, default=15)
    parser.add_argument("--kw-context", type=int, default=2)
    parser.add_argument("--max-kb", type=int, default=300)
    return parser.parse_args()


def build_pools(uif_path):
    """Read UIF file, build subject/all pools, return stats dict."""
    subject_msgs = []
    all_msgs = []
    bad = 0
    total = 0
    with open(uif_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                bad += 1
                continue
            if rec.get("record_type") != "message":
                continue
            if rec.get("content_type") != "text":
                continue
            record_id = rec.get("record_id")
            ts = rec.get("timestamp")
            chat_room = rec.get("chat_room")
            text = rec.get("text")
            sender = rec.get("sender")
            if not record_id or not ts or not chat_room or not text or not text.strip() or not sender:
                bad += 1
                continue
            year = parse_year(ts)
            if year is None:
                bad += 1
                continue
            room_label = rec.get("room_label") or "unknown"
            msg = {
                "record_id": record_id,
                "ts": ts,
                "text": text,
                "sender": sender,
                "chat_room": chat_room,
                "room_label": room_label,
                "sender_alias": rec.get("sender_alias"),
                "sender_wxid": rec.get("sender_wxid"),
                "year": year,
            }
            all_msgs.append(msg)
            if msg["sender"] == "subject":
                subject_msgs.append(msg)
    sort_key = lambda x: (x["chat_room"], x["ts"], x["record_id"])
    subject_msgs = sorted(subject_msgs, key=sort_key)
    all_msgs = sorted(all_msgs, key=sort_key)
    return subject_msgs, all_msgs, {"total_records": total, "bad": bad}


def build_all_index(all_msgs):
    """Index all messages by chat_room, sorted by timestamp."""
    index = defaultdict(list)
    for m in all_msgs:
        index[m["chat_room"]].append(m)
    for room in index:
        index[room].sort(key=lambda x: (x["ts"], x["record_id"]))
    return index


def truncate(text, limit):
    """Truncate text to limit chars, appending ellipsis if needed."""
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


def sample_random(subject_pool, year, count, rng):
    """Randomly sample year messages."""
    msgs = [m for m in subject_pool if m["year"] == year]
    out = []
    for m in rng.sample(msgs, min(count, len(msgs))):
        out.append({
            "record_id": m["record_id"],
            "ts": m["ts"],
            "room_label": m["room_label"],
            "text": truncate(m["text"], 300),
        })
    return out


def sample_longest(subject_pool, year, count, exclude_ids):
    """Longest messages for year, excluding given ids."""
    msgs = [m for m in subject_pool if m["year"] == year and m["record_id"] not in exclude_ids]
    msgs.sort(key=lambda x: (-len(x["text"]), x["record_id"]))
    out = []
    for m in msgs[:count]:
        out.append({
            "record_id": m["record_id"],
            "ts": m["ts"],
            "room_label": m["room_label"],
            "text": truncate(m["text"], 300),
        })
    return out


def pick_anchors(subject_pool, year, count, rng):
    """Pick anchor messages spaced >=7 days apart, best effort."""
    msgs = [m for m in subject_pool if m["year"] == year]
    if not msgs:
        return []
    msgs.sort(key=lambda x: (x["ts"], x["record_id"]))
    chosen = []
    attempts = 0
    max_attempts = count * 50
    while len(chosen) < count and attempts < max_attempts:
        attempts += 1
        cand = rng.choice(msgs)
        ok = True
        for c in chosen:
            try:
                t1 = datetime.fromisoformat(c["ts"])
                t2 = datetime.fromisoformat(cand["ts"])
            except (ValueError, TypeError):
                continue
            if abs((t2 - t1).days) < 7:
                ok = False
                break
        if ok:
            chosen.append(cand)
            if len(chosen) >= count:
                break
    return chosen


def extract_window(anchor, all_index, window_size):
    """Extract context window around anchor from same chat_room."""
    room_msgs = all_index.get(anchor["chat_room"], [])
    try:
        pos = room_msgs.index(anchor)
    except ValueError:
        pos = -1
        for i, m in enumerate(room_msgs):
            if m["record_id"] == anchor["record_id"] and m["ts"] == anchor["ts"]:
                pos = i
                break
        if pos == -1:
            return []
    half = window_size // 2
    start = max(0, pos - half)
    end = min(len(room_msgs), pos + half + (window_size % 2))
    return room_msgs[start:end]


def format_msg(m):
    """Format a message for thread/window output."""
    if m["sender"] == "subject":
        sender = "subject"
    else:
        alias = m.get("sender_alias")
        sender = alias if alias else (m.get("sender_wxid") or "unknown")[:8]
    return {
        "ts": m["ts"],
        "sender": sender,
        "text": truncate(m["text"], 120),
    }


def build_threads(subject_pool, all_index, year, count, window_size, rng):
    """Build thread windows for a year."""
    anchors = pick_anchors(subject_pool, year, count, rng)
    threads = []
    for a in anchors:
        win = extract_window(a, all_index, window_size)
        msgs = [format_msg(m) for m in win]
        threads.append({
            "chat_room": a["chat_room"],
            "room_label": a.get("room_label"),
            "messages": msgs,
        })
    return threads


def keyword_counts(subject_pool, year, kws):
    """Count messages in year containing any keyword."""
    count = 0
    for m in subject_pool:
        if m["year"] != year:
            continue
        if any(k in m["text"] for k in kws):
            count += 1
    return count


def sample_kw_messages(subject_pool, years, kws, per_group, rng):
    """Sample keyword-hit messages, evenly distributed across years by rotation."""
    hits_by_year = {}
    for y in years:
        hits_by_year[y] = [m for m in subject_pool if m["year"] == y and any(k in m["text"] for k in kws)]
    shuffled = {}
    for y in years:
        pool = hits_by_year.get(y, [])
        rng.shuffle(pool)
        shuffled[y] = pool
    selected = []
    pos = {y: 0 for y in years}
    years_list = sorted(years)
    while len(selected) < per_group:
        added_this_round = False
        for y in years_list:
            pool = shuffled.get(y, [])
            if pos[y] < len(pool):
                selected.append(pool[pos[y]])
                pos[y] += 1
                added_this_round = True
                if len(selected) >= per_group:
                    break
        if not added_this_round:
            break
    return selected


def build_kw_samples(subject_pool, all_index, years, groups, per_group, ctx, rng):
    """Build keyword-hit samples with context windows."""
    result = {}
    for gname, ginfo in groups.items():
        label = ginfo.get("label", gname)
        kws = ginfo.get("keywords", [])
        counts_by_year = {}
        for y in years:
            counts_by_year[y] = keyword_counts(subject_pool, y, kws)
        samples_raw = sample_kw_messages(subject_pool, years, kws, per_group, rng)
        samples = []
        for m in samples_raw:
            win = extract_window(m, all_index, ctx * 2 + 1)
            hit_pos = None
            for i, x in enumerate(win):
                if x["record_id"] == m["record_id"] and x["ts"] == m["ts"]:
                    hit_pos = i
                    break
            if hit_pos is None:
                samples.append({
                    "record_id": m["record_id"],
                    "ts": m["ts"],
                    "text": truncate(m["text"], 120),
                    "context": [],
                })
                continue
            ctx_before = win[max(0, hit_pos - ctx):hit_pos]
            ctx_after = win[hit_pos + 1: hit_pos + 1 + ctx]
            context_msgs = [format_msg(x) for x in ctx_before + ctx_after]
            samples.append({
                "record_id": m["record_id"],
                "ts": m["ts"],
                "text": truncate(m["text"], 120),
                "context": context_msgs,
            })
        result[gname] = {
            "label": label,
            "counts_by_year": counts_by_year,
            "samples": samples,
        }
    return result


def build_digest(params):
    """Build complete digest dict from params."""
    subject_pool, all_msgs, stats = build_pools(params["uif_path"])
    all_index = build_all_index(all_msgs)
    years = sorted({m["year"] for m in subject_pool if m["year"]})
    rng = random.Random(params["seed"])

    meta = {
        "person": params["person"],
        "seed": params["seed"],
        "samples_per_year": params["samples_per_year"],
        "longest_per_year": params["longest_per_year"],
        "threads_per_year": params["threads_per_year"],
        "thread_window": params["thread_window"],
        "kw_samples_per_group": params["kw_samples_per_group"],
        "kw_context": params["kw_context"],
        "max_kb": params["max_kb"],
        "total_records": stats["total_records"],
        "subject_text_msgs": len(subject_pool),
        "counts_by_room": defaultdict(int),
        "counts_by_year": defaultdict(int),
        "date_range": None,
        "bad_lines": stats["bad"],
        "rhythm_ref": f"people/{params['person']}/persona/rhythm.json",
    }

    for m in subject_pool:
        meta["counts_by_room"][m["room_label"]] = meta["counts_by_room"].get(m["room_label"], 0) + 1
        meta["counts_by_year"][m["year"]] = meta["counts_by_year"].get(m["year"], 0) + 1
    if subject_pool:
        ts_list = [m["ts"] for m in subject_pool]
        meta["date_range"] = [min(ts_list), max(ts_list)]

    yearly_samples = {}
    for y in years:
        random_samples = sample_random(subject_pool, y, params["samples_per_year"], rng)
        random_ids = {s["record_id"] for s in random_samples}
        longest_samples = sample_longest(subject_pool, y, params["longest_per_year"], random_ids)
        yearly_samples[y] = {
            "random": random_samples,
            "longest": longest_samples,
        }

    threads = {}
    for y in years:
        threads[y] = build_threads(
            subject_pool, all_index, y,
            params["threads_per_year"], params["thread_window"], rng
        )

    kw_samples = build_kw_samples(
        subject_pool, all_index, years, params["groups"],
        params["kw_samples_per_group"], params["kw_context"], rng
    )

    return {
        "meta": meta,
        "yearly_samples": yearly_samples,
        "threads": threads,
        "keyword_hits": kw_samples,
    }


def main():
    """Main entry point."""
    args = parse_args()
    validate_person(args.person)
    repo_root = resolve_repo_root()

    if args.uif:
        uif_path = Path(args.uif).resolve()
    else:
        uif_path = repo_root / "people" / args.person / "normalized" / "wechat_messages.uif.jsonl"
    if args.out:
        out_path = Path(args.out).resolve()
    else:
        out_path = repo_root / "people" / args.person / "persona" / "persona_digest.json"
    check_path_within(out_path, repo_root / "people" / args.person / "persona")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if args.keywords:
        kw_path = Path(args.keywords).resolve()
    else:
        kw_path = repo_root / "tools" / "persona_keywords.zh.json"
    groups = load_keywords(kw_path)

    if not uif_path.exists():
        print(f"ERROR: UIF file not found: {uif_path}", file=sys.stderr)
        sys.exit(1)

    print(f"UIF path: {uif_path}")
    print(f"Output path: {out_path}")
    print(f"Keywords path: {kw_path}")

    # Volume control
    levels = [
        {
            "seed": args.seed,
            "samples_per_year": args.samples_per_year,
            "longest_per_year": args.longest_per_year,
            "threads_per_year": args.threads_per_year,
            "thread_window": args.thread_window,
            "kw_samples_per_group": args.kw_samples_per_group,
            "kw_context": args.kw_context,
            "max_kb": args.max_kb,
        },
        {
            "seed": args.seed,
            "samples_per_year": args.samples_per_year,
            "longest_per_year": args.longest_per_year,
            "threads_per_year": args.threads_per_year,
            "thread_window": args.thread_window,
            "kw_samples_per_group": 10,
            "kw_context": args.kw_context,
            "max_kb": args.max_kb,
        },
        {
            "seed": args.seed,
            "samples_per_year": args.samples_per_year,
            "longest_per_year": args.longest_per_year,
            "threads_per_year": args.threads_per_year,
            "thread_window": args.thread_window,
            "kw_samples_per_group": 6,
            "kw_context": args.kw_context,
            "max_kb": args.max_kb,
        },
        {
            "seed": args.seed,
            "samples_per_year": args.samples_per_year,
            "longest_per_year": args.longest_per_year,
            "threads_per_year": args.threads_per_year,
            "thread_window": 12,
            "kw_samples_per_group": 6,
            "kw_context": args.kw_context,
            "max_kb": args.max_kb,
        },
        {
            "seed": args.seed,
            "samples_per_year": 6,
            "longest_per_year": args.longest_per_year,
            "threads_per_year": args.threads_per_year,
            "thread_window": 12,
            "kw_samples_per_group": 6,
            "kw_context": args.kw_context,
            "max_kb": args.max_kb,
        },
    ]

    final_digest = None
    final_data_str = None
    final_kb = None

    for i, params in enumerate(levels):
        params["person"] = args.person
        params["uif_path"] = str(uif_path)
        params["groups"] = groups
        digest = build_digest(params)
        data_str = json.dumps(digest, ensure_ascii=False, indent=1)
        kb = len(data_str.encode("utf-8")) / 1024
        if kb <= args.max_kb:
            final_digest = digest
            final_data_str = data_str
            final_kb = kb
            break
        if i < len(levels) - 1:
            print(f"  Reducing output size (stage {i + 1}): kw_samples={params['kw_samples_per_group']}, "
                  f"thread_window={params['thread_window']}, samples_per_year={params['samples_per_year']}")
    else:
        print(f"ERROR: cannot reduce output below max-kb ({args.max_kb} KB)", file=sys.stderr)
        sys.exit(1)

    # Atomic write
    part_path = out_path.with_suffix(".part")
    with open(part_path, "w", encoding="utf-8") as f:
        f.write(final_data_str)
    os.replace(part_path, out_path)

    y_samples = final_digest["yearly_samples"]
    threads = final_digest["threads"]
    kw_hits = final_digest["keyword_hits"]
    print(f"Yields: random={sum(len(v['random']) for v in y_samples.values())}, "
          f"longest={sum(len(v['longest']) for v in y_samples.values())}, "
          f"threads={sum(len(v) for v in threads.values())}, "
          f"kw_groups={len(kw_hits)}")
    print(f"Final size: {final_kb:.1f} KB -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
