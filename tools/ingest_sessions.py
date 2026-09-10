#!/usr/bin/env python3
"""Ingest sessions from people/<slug>/sessions/**/*.jsonl into archive_out/data.

Usage:
  python tools/ingest_sessions.py --person <slug>
  python tools/ingest_sessions.py --person <slug> [--out-dir <dir>] [--exclude-file <path>]
  python tools/ingest_sessions.py --person <slug> [--patterns <path>] [--dry-run]
"""

import argparse
import json
import os
import re
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants and global state
# ---------------------------------------------------------------------------

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
VIEWER_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
DEFAULT_VIEWER = "owner"
REDACTED_TEXT = "\u3014\u542b\u654f\u611f\u4fe1\u606f\uff0c\u5df2\u7701\u7565\u3015"
EXCLUDE_EVENT_TEXT = "exclude_session"
OUT_NAME_RE = re.compile(r"^sessions_([a-z][a-z0-9_-]{0,31})\.json$")

ROOT = Path(__file__).resolve().parent.parent
PEOPLE_DIR = ROOT / "people"
SCHEMA_VERSION = 1


def exit_error(msg):
    """Print ASCII-only message to stderr and exit with code 2."""
    print(msg.encode("ascii", "replace").decode("ascii"), file=sys.stderr)
    sys.exit(2)


def validate_slug(slug):
    """Validate slug and return person dir string."""
    if not SLUG_RE.match(slug):
        exit_error(f"error: invalid slug '{slug}'")
    return slug


def contain_check(path, base_dir, allow_same=False):
    """Return True if path is inside base_dir (or equal when allow_same)."""
    try:
        rel = Path(path).resolve().relative_to(Path(base_dir).resolve())
        return True
    except ValueError:
        if allow_same and Path(path).resolve() == Path(base_dir).resolve():
            return True
        return False


# ---------------------------------------------------------------------------
# Public interfaces
# ---------------------------------------------------------------------------

def load_exclude_ids(path):
    """Load exclude IDs from text file. Missing file -> empty set."""
    result = set()
    if not os.path.exists(path):
        return result
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                result.add(stripped)
    except OSError as exc:
        print(("warning: cannot read exclude file: %s" % exc).encode("ascii", "replace").decode("ascii"), file=sys.stderr)
    return result


def load_patterns(path):
    """Load sensitive patterns from JSON. Missing file -> [] and warn stderr once."""
    if not os.path.exists(path):
        print("warning: sensitive patterns file %s not found; skipping sensitivity scan" % path, file=sys.stderr)
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(("warning: cannot read patterns file %s: %s" % (path, exc)).encode("ascii", "replace").decode("ascii"), file=sys.stderr)
        return []
    result = []
    for item in data.get("patterns", []):
        name = item.get("name", "???")
        regex = item.get("regex", "")
        severity = item.get("severity", "low")
        try:
            compiled = re.compile(regex, re.IGNORECASE)
        except re.error as exc:
            print(("warning: invalid regex for pattern '%s': %s" % (name, exc)).encode("ascii", "replace").decode("ascii"), file=sys.stderr)
            continue
        if severity not in ("high", "medium", "low"):
            print("warning: pattern '%s' has invalid severity; treating as high" % name, file=sys.stderr)
            severity = "high"
        result.append((name, compiled, severity))
    return result


def validate_paths(person_dir, out_dir, exclude_file=None, patterns_path=None):
    """Validate path safety. Returns None if ok, or an error string (ASCII)."""
    person_dir = Path(person_dir).resolve()
    out_dir = Path(out_dir).resolve()
    raw_dir = person_dir / "raw"
    raw_dir = raw_dir.resolve()

    try:
        out_dir.relative_to(person_dir)
    except ValueError:
        return "out dir must be inside person dir"

    try:
        out_dir.relative_to(raw_dir)
        return "out dir must not be inside raw/"
    except ValueError:
        pass
    if out_dir == raw_dir:
        return "out dir must not be inside raw/"

    for label, p in (("exclude file", exclude_file), ("patterns file", patterns_path)):
        if p is not None:
            resolved_p = Path(p).resolve()
            try:
                resolved_p.relative_to(raw_dir)
                return "%s must not be inside raw/" % label
            except ValueError:
                pass
    return None


def _normalize_viewer(viewer):
    """Return normalized viewer or DEFAULT_VIEWER."""
    if isinstance(viewer, str) and VIEWER_RE.match(viewer):
        return viewer
    return DEFAULT_VIEWER


def _text_truncate(text, max_len):
    """Truncate text to max_len chars + ellipsis if too long."""
    if len(text) > max_len:
        return text[:max_len] + "\u2026"
    return text


def _text_strip_lines(text):
    """Trim leading/trailing whitespace from text."""
    return text.strip() if isinstance(text, str) else ""


def _extract_date_from_str(ts_str, session_id):
    """Extract date (first 10 chars) from timestamp or session_id filename date."""
    if ts_str and isinstance(ts_str, str):
        # take first 10 chars, ensure resembles date
        candidate = ts_str[:10]
        if re.match(r"^\d{4}-\d{2}-\d{2}$", candidate):
            return candidate
    # try session_id date like YYYYMMDD-HHMMSS-xxxxxx
    if session_id and isinstance(session_id, str):
        m = re.match(r"^(\d{4})(\d{2})(\d{2})-", session_id)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return "0000-00-00"


def _session_id_from_filename(filename):
    """Extract session id from filename 'session_<id>.jsonl' or None."""
    if filename:
        m = re.match(r"^session_(.+)\.jsonl$", filename)
        if m:
            return m.group(1)
    return None


def _sorted_turns(session_turns):
    """Sort turns by (turn asc, role user first)."""
    def sort_key(item):
        role_rank = 0 if item["role"] == "user" else 1
        return (item["turn"], role_rank)
    return sorted(session_turns, key=sort_key)


def build_sessions(person_dir, *, exclude_file=None, patterns_path=None,
                   card_max_lines=12, card_line_chars=120, exchange_chars=200,
                   generated_at=None):
    """
    Build session payloads per viewer.

    Returns (viewer_payloads: dict[viewer -> payload], global_stats: dict)
    """
    person_dir = Path(person_dir)
    sessions_dir = person_dir / "sessions"

    if exclude_file is None:
        exclude_file = sessions_dir / "exclude.txt"
    exclude_ids = load_exclude_ids(exclude_file)

    if patterns_path is None:
        patterns_path = ROOT / "tools" / "sensitive_patterns.json"
    pattern_list = load_patterns(patterns_path)

    # GLOBAL counters
    stat_files = 0
    stat_records = 0
    stat_bad_lines = 0

    # Collect raw records per file
    raw_records = []  # list of (session_id, turn, role, text, ts, server_ts, viewer, exclude, filepath, lineno)
    if sessions_dir.exists():
        # find all .jsonl recursively, excluding audio dirs
        for dirpath, dirnames, filenames in os.walk(str(sessions_dir)):
            # filter out audio directories
            dirnames[:] = [d for d in dirnames if d.lower() != "audio"]
            dirnames[:] = sorted(dirnames)
            for fname in sorted(filenames):
                if not fname.endswith(".jsonl"):
                    continue
                fpath = os.path.join(dirpath, fname)
                stat_files += 1
                file_session_id = _session_id_from_filename(fname)
                with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                    for lineno, line in enumerate(fh, start=1):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            rec = json.loads(line)
                        except json.JSONDecodeError:
                            stat_bad_lines += 1
                            print("warning: bad JSON line in %s:%d" % (fpath, lineno), file=sys.stderr)
                            continue
                        if not isinstance(rec, dict):
                            stat_bad_lines += 1
                            print("warning: non-object JSON in %s:%d" % (fpath, lineno), file=sys.stderr)
                            continue
                        stat_records += 1
                        session_id = rec.get("session_id")
                        if not isinstance(session_id, str):
                            session_id = file_session_id
                        raw_records.append({
                            "session_id": session_id,
                            "turn": rec.get("turn"),
                            "role": rec.get("role"),
                            "text": rec.get("text"),
                            "ts": rec.get("ts"),
                            "server_ts": rec.get("server_ts"),
                            "viewer": rec.get("viewer"),
                            "exclude": rec.get("exclude", False),
                            "filepath": fpath,
                            "lineno": lineno,
                        })

    # EXCLUDE checks per session_id
    excluded_sessions = set()
    # gather session ids that have excluded marker
    for rec in raw_records:
        sid = rec["session_id"]
        if sid is None:
            continue
        if rec.get("exclude") is True:
            excluded_sessions.add(sid)
        if rec.get("role") == "event" and rec.get("text") == EXCLUDE_EVENT_TEXT:
            excluded_sessions.add(sid)
        if str(sid) in exclude_ids:
            excluded_sessions.add(sid)

    # Filter to keep only user/simulacrum non-empty text; mark redaction
    dedup_seen = set()
    session_items = {}  # session_id -> dict with fields

    for rec in raw_records:
        sid = rec["session_id"]
        if sid is None:
            continue
        if sid in excluded_sessions:
            continue
        role = rec.get("role")
        if role not in ("user", "simulacrum"):
            continue
        text = rec.get("text")
        if not isinstance(text, str) or not text.strip():
            continue

        # dedupe key
        turn = rec.get("turn")
        if turn is None:
            turn_key = -1
        else:
            turn_key = turn
        dedup_key = (sid, turn_key, role)
        if dedup_key in dedup_seen:
            continue
        dedup_seen.add(dedup_key)

        viewer = _normalize_viewer(rec.get("viewer"))

        original_text = text
        redacted = False
        for _name, _regex, severity in pattern_list:
            if severity in ("high", "medium"):
                if _regex.search(original_text):
                    text = REDACTED_TEXT
                    redacted = True
                    break

        if sid not in session_items:
            session_items[sid] = {
                "session_id": sid,
                "date": None,
                "viewer": viewer,
                "turns_in": [],
                "records": [],
                "first_ts": None,
            }
        # NOTE: first record define viewer lineage if conflicting viewer on same session?
        # Spec: per viewer partition from records. But each record has viewer. We group by viewer.
        # For simplicity, a record belongs to the sessions of its viewer. So we should not key session_items
        # by session_id alone but by (viewer, session_id).
        # Rework: use combined key
    # REWORK differently: store per (viewer, session_id)
    session_by_view = {}  # (viewer, sid) -> dict

    dedup_seen = set()
    for rec in raw_records:
        sid = rec["session_id"]
        if sid is None:
            continue
        if sid in excluded_sessions:
            continue
        role = rec.get("role")
        if role not in ("user", "simulacrum"):
            continue
        text = rec.get("text")
        if not isinstance(text, str) or not text.strip():
            continue

        viewer = _normalize_viewer(rec.get("viewer"))

        turn = rec.get("turn")
        if turn is None:
            turn_key = -1
        else:
            turn_key = turn
        dedup_key = (viewer, sid, turn_key, role)
        if dedup_key in dedup_seen:
            continue
        dedup_seen.add(dedup_key)

        redacted = False
        for _name, _regex, severity in pattern_list:
            if severity in ("high", "medium"):
                if _regex.search(text):
                    text = REDACTED_TEXT
                    redacted = True
                    break

        key = (viewer, sid)
        if key not in session_by_view:
            session_by_view[key] = {
                "session_id": sid,
                "viewer": viewer,
                "date": None,
                "turns": [],
                "redacted_turns": 0,
            }
        entry = session_by_view[key]
        if redacted:
            entry["redacted_turns"] += 1

        # compute date
        ts_val = rec.get("ts")
        if not ts_val:
            ts_val = rec.get("server_ts")
        date_str = _extract_date_from_str(ts_val, sid)
        if entry["date"] is None:
            entry["date"] = date_str

        # store turn record for later processing (but keep text full unless redacted)
        entry["turns"].append({
            "turn": turn_key,
            "role": role,
            "text": text,
            "original_text_for_card": None if redacted else text,
            "ts": rec.get("ts") or rec.get("server_ts") or "",
            "date": date_str,
        })

    # Now group by viewer
    viewer_data = {}
    for (viewer, sid), entry in session_by_view.items():
        if viewer not in viewer_data:
            viewer_data[viewer] = []
        viewer_data[viewer].append(entry)

    # excluded count per viewer: count sessions that had records with that viewer but excluded
    # Simple: from raw records with viewer, count unique sid in excluded_sessions
    viewer_excluded_count = {}
    for rec in raw_records:
        sid = rec["session_id"]
        if sid in excluded_sessions:
            v = _normalize_viewer(rec.get("viewer"))
            if v not in viewer_excluded_count:
                viewer_excluded_count[v] = set()
            viewer_excluded_count[v].add(sid)

    # Stats per viewer (all viewers: kept, excluded-only, plus owner)
    viewer_stats = {}
    all_viewers = set(viewer_data) | set(viewer_excluded_count) | {DEFAULT_VIEWER}
    for viewer in all_viewers:
        viewer_data.setdefault(viewer, [])
        redacted_turn_count = sum(e["redacted_turns"] for e in viewer_data[viewer])
        viewer_stats[viewer] = {
            "excluded_sessions": len(viewer_excluded_count.get(viewer, ())),
            "redacted_turns": redacted_turn_count,
            "sessions_kept": len(viewer_data[viewer]),
        }

    # Build payload per viewer
    payloads = {}

    for viewer, entries in sorted(viewer_data.items()):
        if not VIEWER_RE.match(viewer):
            continue  # should not happen because normalize
        # sort entries by date then session_id
        sorted_entries = sorted(entries, key=lambda e: (e["date"] or "", e["session_id"] or ""))

        # Build turns for each session (ensure sorted)
        sessions_list = []
        for entry in sorted_entries:
            # Filter turns? all turns already user/simulacrum non-empty
            turn_objects = [{
                "turn": t["turn"] if t["turn"] != -1 else None,
                "role": t["role"],
                "text": t["text"],
                "ts": t["ts"] if t["ts"] else None,
            } for t in entry["turns"]]
            # Sort
            turn_objects_sorted = _sorted_turns([{
                "turn": (t["turn"] if t["turn"] is not None else -1),
                "role": t["role"],
                "text": t["text"],
                "ts": t["ts"],
            } for t in entry["turns"]])
            # attach ts
            for tt in turn_objects_sorted:
                pass
            session_obj = {
                "session_id": entry["session_id"],
                "date": entry["date"],
                "turns": turn_objects_sorted,
            }
            sessions_list.append(session_obj)

        # Choose last_card: max date, then max session_id, must have at least one user and one simulacrum
        def has_both(entry):
            roles = {t["role"] for t in entry["turns"]}
            return "user" in roles and "simulacrum" in roles

        candidates = [e for e in sorted_entries if has_both(e)]
        last_card_session = None
        if candidates:
            last_card_session = max(candidates, key=lambda e: (e["date"] or "", e["session_id"] or ""))

        # Build recent_dates: all sorted_entries except last_card, dates desc unique, top 5
        recent_dates = []
        if sorted_entries:
            all_entries_sorted_desc = sorted(sorted_entries, key=lambda e: (e["date"] or "", e["session_id"] or ""), reverse=True)
            seen_dates = set()
            for e in all_entries_sorted_desc:
                if last_card_session is not None and e["session_id"] == last_card_session["session_id"] and e["date"] == last_card_session["date"]:
                    continue
                d = e["date"]
                if d and d not in seen_dates:
                    recent_dates.append(d)
                    seen_dates.add(d)
                if len(recent_dates) >= 5:
                    break

        # last_card payload
        last_card_payload = None
        if last_card_session is not None:
            # user lines from original text (excluding redacted ones)
            user_texts = []
            for t in last_card_session["turns"]:
                if t["role"] == "user" and t["text"] != REDACTED_TEXT:
                    user_texts.append(_text_strip_lines(t["original_text_for_card"] if t.get("original_text_for_card") else t["text"]))
            user_texts = [u for u in user_texts if u]
            truncated = False
            if len(user_texts) > card_max_lines:
                truncated = True
                first = user_texts[:4]
                last8 = user_texts[-8:]
                chosen = first + last8
            else:
                chosen = user_texts
            chosen_display = [_text_truncate(u, card_line_chars) for u in chosen]

            # last_exchange: last user text and following simulacrum
            last_exchange = {"user": None, "simulacrum": None}
            # find last user (non-redacted)
            user_turns = [t for t in last_card_session["turns"] if t["role"] == "user" and t["text"] != REDACTED_TEXT]
            sim_turns = [t for t in last_card_session["turns"] if t["role"] == "simulacrum" and t["text"] != REDACTED_TEXT]
            if user_turns:
                last_user_obj = max(user_turns, key=lambda t: (t["turn"], t["ts"] or ""))
                # find last sim after that
                user_idx = last_user_obj["turn"]
                after_sims = [t for t in sim_turns if t["turn"] >= user_idx or (t["turn"] == user_idx)]
                # Actually last sim after user
                after_sims_ordered = [t for t in sim_turns if (t["turn"] > user_idx) or (t["turn"] == user_idx and True)]
                if after_sims_ordered:
                    last_sim = max(after_sims_ordered, key=lambda t: (t["turn"], t["ts"] or ""))
                    last_exchange["user"] = _text_truncate(last_user_obj["original_text_for_card"] if last_user_obj.get("original_text_for_card") else last_user_obj["text"], exchange_chars)
                    last_exchange["simulacrum"] = _text_truncate(last_sim["original_text_for_card"] if last_sim.get("original_text_for_card") else last_sim["text"], exchange_chars)
                else:
                    last_exchange["user"] = _text_truncate(last_user_obj["original_text_for_card"] if last_user_obj.get("original_text_for_card") else last_user_obj["text"], exchange_chars)
            elif sim_turns:
                # no user? shouldn't happen since has_both
                pass

            sorted_session_turns = _sorted_turns([{
                "turn": (t["turn"] if t["turn"] is not None else -1),
                "role": t["role"],
                "text": t["text"],
                "ts": t["ts"],
            } for t in last_card_session["turns"]])

            started_at = None
            ended_at = None
            for t in sorted_session_turns:
                if t["ts"]:
                    started_at = t["ts"]
                    break
            for t in reversed(sorted_session_turns):
                if t["ts"]:
                    ended_at = t["ts"]
                    break

            last_card_payload = {
                "session_id": last_card_session["session_id"],
                "date": last_card_session["date"],
                "started_at": started_at,
                "ended_at": ended_at,
                "turns": len(last_card_session["turns"]),
                "user_lines": chosen_display,
                "user_lines_truncated": truncated,
                "last_exchange": last_exchange,
            }

        # Global stats per viewer
        g_stats = viewer_stats[viewer]

        payload = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": generated_at or datetime.now().astimezone().isoformat(timespec="seconds"),
            "person": Path(person_dir).name,
            "epoch": 2,
            "viewer": viewer,
            "tier_policy": {"user": 2, "simulacrum": 3},
            "source_stats": {
                "files": stat_files,
                "records": stat_records,
                "bad_lines": stat_bad_lines,
                "excluded_sessions": g_stats["excluded_sessions"],
                "redacted_turns": g_stats["redacted_turns"],
                "sessions_kept": g_stats["sessions_kept"],
            },
            "last_card": last_card_payload,
            "recent_dates": recent_dates,
            "sessions": sessions_list,
        }
        payloads[viewer] = payload

    # global stats (for ingest return)
    global_stats = {
        "files": stat_files,
        "records": stat_records,
        "bad_lines": stat_bad_lines,
        "total_excluded_sessions": len(excluded_sessions),
    }

    return payloads, global_stats


def write_atomic_json(path, obj):
    """Write json atomically via tmp + os.replace."""
    path = Path(path)
    tmp_path = path.with_name(path.name + ".tmp")
    with open(tmp_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    os.replace(str(tmp_path), str(path))


def ingest(person_dir, out_dir, **opts):
    """Write viewer files, delete stale files. Return dict with written/deleted/stats."""
    person_dir = Path(person_dir)
    out_dir = Path(out_dir)

    exclude_file = opts.get("exclude_file")
    patterns_path = opts.get("patterns_path")
    generated_at = opts.get("generated_at")

    card_max_lines = int(opts.get("card_max_lines", 12))
    card_line_chars = int(opts.get("card_line_chars", 120))
    exchange_chars = int(opts.get("exchange_chars", 200))

    err = validate_paths(person_dir, out_dir, exclude_file=exclude_file, patterns_path=patterns_path)
    if err:
        raise ValueError(err)

    payloads, global_stats = build_sessions(
        person_dir,
        exclude_file=exclude_file,
        patterns_path=patterns_path,
        card_max_lines=card_max_lines,
        card_line_chars=card_line_chars,
        exchange_chars=exchange_chars,
        generated_at=generated_at,
    )

    out_dir.mkdir(parents=True, exist_ok=True)

    per_viewer_subdir = bool(opts.get("per_viewer_subdir", False))

    written_files = []
    written_viewers = set()
    for viewer, payload in payloads.items():
        if per_viewer_subdir:
            viewer_dir = out_dir / viewer
            viewer_dir.mkdir(parents=True, exist_ok=True)
            write_atomic_json(viewer_dir / "sessions.json", payload)
            written_files.append(f"{viewer}/sessions.json")
        else:
            fname = f"sessions_{viewer}.json"
            write_atomic_json(out_dir / fname, payload)
            written_files.append(fname)
        written_viewers.add(viewer)

    deleted_files = []
    if per_viewer_subdir:
        # Per-viewer layout: the only managed artifact is
        # <out_dir>/<viewer>/sessions.json. Never remove the viewer directory
        # itself (it may also hold e.g. <viewer>/audio/), never touch files
        # directly inside <out_dir>, and never recurse.
        if out_dir.exists():
            try:
                resolved_out_dir = out_dir.resolve()
            except (OSError, RuntimeError):
                # 解析不了 out_dir 就整体不清理（fail-safe：宁可不删，绝不误删）
                resolved_out_dir = None
            for existing in out_dir.iterdir():
                # is_dir() / is_file() 都会跟随符号链接和 Windows 目录联接（Junction）。
                # 必须先确认该目录解析后真实位于 out_dir 内，否则 target.unlink()
                # 删掉的会是联接目标目录里的文件。
                # 注意：Junction 的 is_symlink() 为 False，且 Python 3.10 没有
                # Path.is_junction()，因此只能用 resolve() 后的父目录约束来判断。
                if resolved_out_dir is None:
                    continue
                try:
                    resolved_existing = existing.resolve()
                except (OSError, RuntimeError):
                    # 路径异常 / 权限不足：跳过该目录，不删不报错
                    continue
                # 注意：这里不能用「解析后的父目录 == 解析后的 out_dir」这种父目录约束。
                # 同一 out_dir 内的 junction 别名（例如 out/ghost 指向 out/owner）解析后
                # 父目录依然是 out，能够通过父目录检查；而它不在本次的 written_viewers 中，
                # 于是会被当作 stale 执行 unlink，实际删掉的是刚刚生成的 owner/sessions.json。
                # 因此必须改成目录身份约束：解析后的路径必须等于「out_dir 解析后 + 该目录自己的名字」，
                # 即该目录必须是「它自己」，而不是指向别处（哪怕别处也在 out_dir 内）的别名。
                if resolved_existing != resolved_out_dir / existing.name:
                    continue
                if not existing.is_dir():
                    continue
                if not VIEWER_RE.fullmatch(existing.name):
                    continue
                if existing.name in written_viewers:
                    continue
                target = existing / "sessions.json"
                if not target.is_file():
                    continue
                target.unlink()
                deleted_files.append(f"{existing.name}/sessions.json")
    else:
        # Delete stale matching files in out_dir that were not written
        written_set = set(written_files)
        if out_dir.exists():
            for existing in out_dir.iterdir():
                if existing.is_file() and OUT_NAME_RE.match(existing.name):
                    if existing.name not in written_set:
                        existing.unlink()
                        deleted_files.append(existing.name)

    return {
        "written": written_files,
        "deleted": deleted_files,
        "stats": global_stats,
    }


def main(argv=None):
    """CLI entry. Returns 0 or 2."""
    parser = argparse.ArgumentParser(prog="ingest_sessions")
    parser.add_argument("--person", required=True, help="person slug")
    parser.add_argument("--out-dir", default=None, help="output directory (default people/<slug>/archive_out/data)")
    parser.add_argument("--exclude-file", default=None, help="exclude file path")
    parser.add_argument("--patterns", default=None, help="sensitive patterns JSON path")
    parser.add_argument("--card-max-lines", type=int, default=12)
    parser.add_argument("--card-line-chars", type=int, default=120)
    parser.add_argument("--exchange-chars", type=int, default=200)
    parser.add_argument("--dry-run", action="store_true", help="only print stats")
    parser.add_argument(
        "--per-viewer-subdir",
        action="store_true",
        default=False,
        help=(
            "Write each viewer's artifacts to <out-dir>/<viewer>/sessions.json "
            "instead of <out-dir>/sessions_<viewer>.json."
        ),
    )
    args = parser.parse_args(argv)

    try:
        slug = validate_slug(args.person)
    except SystemExit:
        return 2

    person_dir = PEOPLE_DIR / slug

    # verify person dir is inside PEOPLE_DIR (should be by construction)
    if not contain_check(person_dir, PEOPLE_DIR):
        print("error: person dir not inside people dir".encode("ascii", "replace").decode("ascii"), file=sys.stderr)
        return 2

    # Determine out_dir default and verify constraints
    if args.out_dir:
        out_dir = Path(args.out_dir)
    else:
        out_dir = person_dir / "archive_out" / "data"

    err = validate_paths(person_dir, out_dir, exclude_file=args.exclude_file, patterns_path=args.patterns)
    if err:
        print("error: " + err, file=sys.stderr)
        return 2

    if args.dry_run:
        payloads, global_stats = build_sessions(
            person_dir,
            exclude_file=args.exclude_file,
            patterns_path=args.patterns,
            card_max_lines=args.card_max_lines,
            card_line_chars=args.card_line_chars,
            exchange_chars=args.exchange_chars,
        )
        source_stats_aggregated = {
            "files": global_stats.get("files", 0),
            "records": global_stats.get("records", 0),
            "bad_lines": global_stats.get("bad_lines", 0),
        }
        viewer_summary = {}
        for viewer, payload in payloads.items():
            viewer_summary[viewer] = payload["source_stats"]
        print(json.dumps({"global": source_stats_aggregated, "viewers": viewer_summary}, ensure_ascii=False))
        return 0

    result = ingest(
        person_dir,
        out_dir,
        exclude_file=args.exclude_file,
        patterns_path=args.patterns,
        card_max_lines=args.card_max_lines,
        card_line_chars=args.card_line_chars,
        exchange_chars=args.exchange_chars,
        per_viewer_subdir=args.per_viewer_subdir,
    )
    # Print summary to stderr
    print("written: %s" % ",".join(result["written"]), file=sys.stderr)
    if result["deleted"]:
        print("deleted: %s" % ",".join(result["deleted"]), file=sys.stderr)
    return 0


class SessionsIngestScheduler:
    """去抖调度器：会话日志频繁写入时，把多次请求合并成一次摄入。"""

    def __init__(self, person_dir, out_dir, delay_s=5.0, runner=None, log=print, per_viewer_subdir=False):
        self._person_dir = person_dir
        self._out_dir = out_dir
        self._per_viewer_subdir = per_viewer_subdir
        self._delay_s = max(0.0, float(delay_s))
        self._log = log if log is not None else print
        self._lock = threading.Lock()
        self._timer = None
        self._pending = False
        self._run_lock = threading.Lock()
        self.last_success_iso = None
        if runner is not None:
            self._runner = runner
        else:
            self._runner = lambda: ingest(person_dir, out_dir, per_viewer_subdir=per_viewer_subdir)

    def _timed_callback(self):
        """Called by the timer thread when delay elapses."""
        self._dispatch()

    def _dispatch(self):
        """只在仍然 pending 时执行；timer 回调自己不制造新的 pending。"""
        with self._lock:
            if not self._pending:
                return
        if not self._run_lock.acquire(blocking=False):
            return
        try:
            self._run_loop()
        finally:
            self._run_lock.release()

    def _run_loop(self):
        """Execute runner, then keep executing while _pending set.

        Returns the result of the last execution (True if success, False if error).
        """
        last_result = False
        # We have the run lock. Before entering the loop, this run is for
        # the requests that were pending; clear the flag so it does not
        # cause an extra spurious pass right after the first execution.
        with self._lock:
            self._pending = False
        while True:
            last_result = self._execute_once()
            with self._lock:
                if self._pending:
                    self._pending = False
                else:
                    break
        return last_result

    def _execute_once(self):
        """Run runner once, catch all errors. Returns True if success, False if error."""
        try:
            self._runner()
        except Exception:
            tb = traceback.format_exc()
            self._log("SessionsIngestScheduler error:\n" + tb)
            return False
        with self._lock:
            self.last_success_iso = datetime.now().astimezone().isoformat(timespec="seconds")
        return True

    def schedule(self):
        """去抖调度。若已有未触发的定时器，取消并重新计时 delay_s 秒。

        到点后在后台线程调用 run_now() 的实际执行逻辑。
        """
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._pending = True
            timer = threading.Timer(self._delay_s, self._timed_callback)
            timer.daemon = True
            self._timer = timer
            timer.start()

    def run_now(self):
        """同步执行一次。成功返回 True；失败返回 False（不抛出异常）。"""
        # Fast path: if we can get the lock immediately, run directly.
        if self._run_lock.acquire(blocking=False):
            try:
                return self._run_loop()
            finally:
                self._run_lock.release()
        # Lock busy: wait for the current pass, then run this explicit synchronous pass.
        self._run_lock.acquire()
        try:
            return self._run_loop()
        finally:
            self._run_lock.release()

    def cancel(self):
        """取消未触发的定时器（服务关闭时用）。"""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._pending = False

if __name__ == "__main__":
    sys.exit(main())
