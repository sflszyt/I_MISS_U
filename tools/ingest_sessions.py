#!/usr/bin/env python3
"""Ingest sessions from people/<slug>/sessions/**/*.jsonl into archive_out/data.

Usage:
  python tools/ingest_sessions.py --person <slug>
  python tools/ingest_sessions.py --person <slug> [--out-dir <dir>] [--exclude-file <path>]
  python tools/ingest_sessions.py --person <slug> [--patterns <path>] [--dry-run]
"""

import argparse
import contextlib
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

try:  # POSIX advisory locking
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None

try:  # Windows advisory locking
    import msvcrt
except ImportError:  # pragma: no cover - POSIX
    msvcrt = None

# ---------------------------------------------------------------------------
# Constants and global state
# ---------------------------------------------------------------------------

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
VIEWER_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
DEFAULT_VIEWER = "owner"
REDACTED_TEXT = "\u3014\u542b\u654f\u611f\u4fe1\u606f\uff0c\u5df2\u7701\u7565\u3015"
EXCLUDE_EVENT_TEXT = "exclude_session"
OUT_NAME_RE = re.compile(r"^sessions_([a-z][a-z0-9_-]{0,31})\.json$")
AUDIO_BASENAME_RE = re.compile(r"^session_[A-Za-z0-9_-]+_t\d{3}(?:_\d+)?\.wav$")

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


class IngestLockTimeout(RuntimeError):
    """在超时时间内拿不到输出目录的跨进程锁。"""


def _out_lock_path(person_dir, out_dir):
    """把 out_dir 解析后的路径哈希成一个 .lock 文件名。

    锁文件放在 person_dir 下的 .ingest_locks/ 而不是 out_dir 里：out_dir 可能是
    被静态站提供、甚至被打包进可分发档案的目录，锁文件绝不能跟着分发出去。
    """
    # Windows 文件系统不区分大小写，而目录尚不存在时 resolve() 不会把大小写规范化：
    # 同一个目录的两种大小写写法会得到不同的哈希，两个进程就会各自取得不同的锁。
    # 因此先 normcase 再哈希（它在区分大小写的平台上是恒等变换，不影响那些平台）。
    key = os.path.normcase(str(Path(out_dir).resolve()))
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return Path(person_dir) / ".ingest_locks" / (digest + ".lock")


@contextlib.contextmanager
def _acquire_out_lock(person_dir, out_dir, timeout_s=60.0):
    """取得覆盖整轮 ingest 的跨进程排他锁。

    tts_server 内部的 threading.Lock 只能管到同一个进程，管不到手工运行的 CLI，
    因此互斥必须落到文件系统上。锁文件永远不删除：删除会引入竞态（第三个进程
    会新建并锁住一个全新的文件，从而与持锁者并行）。
    """
    lock_path = _out_lock_path(person_dir, out_dir)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o644)
    locked = False
    try:
        deadline = time.monotonic() + float(timeout_s)
        while True:
            try:
                if msvcrt is not None:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise IngestLockTimeout(
                        "timed out waiting for output lock: %s" % lock_path
                    )
                time.sleep(0.1)
        yield lock_path
    finally:
        if locked:
            try:
                if msvcrt is not None:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
        try:
            os.close(fd)
        except OSError:
            pass


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


def _check_out_not_overlapping_sessions(person_dir, out_dir):
    """Validate per-viewer out_dir does not overlap person_dir/sessions.

    Returns None if ok, or an error string (ASCII).
    """
    try:
        guard_out = Path(out_dir).resolve()
        guard_sessions = (Path(person_dir) / "sessions").resolve()
    except (OSError, RuntimeError):
        return "out dir must not overlap sessions/ in per-viewer mode"
    if (guard_out == guard_sessions
            or contain_check(guard_out, guard_sessions)
            or contain_check(guard_sessions, guard_out)):
        return "out dir must not overlap sessions/ in per-viewer mode"
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


def _resolve_audio_source(person_dir, file_field, session_id):
    """Validate a simulacrum_audio record's 'file' field.

    Returns the resolved source Path, or None when the record must be dropped.
    The field is relative to people/<slug>/sessions/ and must never escape it.
    """
    if not isinstance(file_field, str) or not file_field:
        return None
    if file_field.startswith("/"):
        return None
    # 日志规定只用 "/" 分隔。出现任何反斜杠或冒号一律拒绝：否则在 Windows 上
    # "2026-09\..\2026-09/audio/x.wav" 会被当成单个路径段而绕过「无 . / .. 段」校验。
    if "\\" in file_field or ":" in file_field:
        return None
    parts = file_field.split("/")
    for part in parts:
        if part == "" or part == "." or part == "..":
            return None
    basename = parts[-1]
    if not AUDIO_BASENAME_RE.match(basename):
        return None
    if not isinstance(session_id, str) or not basename.startswith("session_%s_t" % session_id):
        return None

    sessions_root = Path(person_dir) / "sessions"
    try:
        source = sessions_root.joinpath(*parts).resolve()
        sessions_resolved = sessions_root.resolve()
        raw_resolved = (Path(person_dir) / "raw").resolve()
    except (OSError, RuntimeError):
        return None
    if not contain_check(source, sessions_resolved, allow_same=False):
        return None
    if contain_check(source, raw_resolved, allow_same=True):
        return None
    # 源侧的文件链接可以换名：若只校验解析前的名字，father 会话里一个指向
    # session_ow_t001.wav 的符号链接会把别人的音频发布到本站。因此 resolve 之后
    # 必须用解析后的文件名重新校验，并且拒绝解析前后 basename 不同的引用。
    resolved_basename = source.name
    if resolved_basename != basename:
        return None
    if not AUDIO_BASENAME_RE.match(resolved_basename):
        return None
    if not isinstance(session_id, str) or not resolved_basename.startswith("session_%s_t" % session_id):
        return None
    try:
        if not source.is_file():
            return None
    except OSError:
        return None
    return source


def _sorted_turns(session_turns):
    """Sort turns by (turn asc, role user first)."""
    def sort_key(item):
        role_rank = 0 if item["role"] == "user" else 1
        return (item["turn"], role_rank)
    return sorted(session_turns, key=sort_key)


def build_sessions(person_dir, *, exclude_file=None, patterns_path=None,
                   card_max_lines=12, card_line_chars=120, exchange_chars=200,
                   generated_at=None, attach_audio=False, audio_plan=None):
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
                            "file": rec.get("file"),
                            "duration_s": rec.get("duration_s"),
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
            "redacted": redacted,
        })

    # Collect simulacrum_audio records (only used for the per-viewer layout).
    # Records belonging to excluded sessions are never collected at all.
    audio_by_turn = {}   # (viewer, session_id, turn_key) -> [audio entries]
    # viewer -> {basename: [解析后的源 Path, ...]}。同一个 basename 可能来自不同目录，
    # 因此必须把每个解析后的源都保留下来：若只用 setdefault(basename, source) 保留第一个，
    # 冲突检查就永远看不到第二个源，两份同名不同源的音频会被静默合并成一个。
    plan_sources = {}
    audio_rejected = 0
    if attach_audio:
        for rec in raw_records:
            if rec.get("role") != "simulacrum_audio":
                continue
            sid = rec["session_id"]
            if sid is not None and sid in excluded_sessions:
                continue
            text = rec.get("text")
            if not isinstance(text, str) or not text:
                audio_rejected += 1
                continue
            file_field = rec.get("file")
            if not isinstance(file_field, str):
                audio_rejected += 1
                continue
            source = _resolve_audio_source(person_dir, file_field, sid)
            if source is None:
                audio_rejected += 1
                continue
            turn = rec.get("turn")
            turn_key = -1 if turn is None else turn
            viewer = _normalize_viewer(rec.get("viewer"))
            dur = rec.get("duration_s")
            if isinstance(dur, bool) or not isinstance(dur, (int, float)):
                dur = None
            basename = source.name
            audio_by_turn.setdefault((viewer, sid, turn_key), []).append({
                "text": text,
                "file": "audio/" + basename,
                "dur": dur,
                "_basename": basename,
                "_source": source,
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
            turn_dicts = []
            for t in entry["turns"]:
                turn_obj = {
                    "turn": (t["turn"] if t["turn"] is not None else -1),
                    "role": t["role"],
                    "text": t["text"],
                    "ts": t["ts"],
                }
                if attach_audio and t["role"] == "simulacrum" and not t.get("redacted"):
                    matched_audio = audio_by_turn.get((viewer, entry["session_id"], turn_obj["turn"]))
                    if matched_audio:
                        turn_obj["audio"] = [
                            {"text": a["text"], "file": a["file"], "dur": a["dur"]}
                            for a in matched_audio
                        ]
                        for a in matched_audio:
                            _sources = plan_sources.setdefault(viewer, {}).setdefault(a["_basename"], [])
                            _src_key = os.path.normcase(str(a["_source"]))
                            if all(os.path.normcase(str(_s)) != _src_key for _s in _sources):
                                _sources.append(a["_source"])
                turn_dicts.append(turn_obj)
            # Sort
            turn_objects_sorted = _sorted_turns(turn_dicts)
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

    if audio_plan is not None:
        audio_plan["sources"] = plan_sources
        audio_plan["rejected"] = audio_rejected

    return payloads, global_stats


def write_atomic_json(path, obj):
    """Write json atomically via tmp + os.replace."""
    path = Path(path)
    tmp_path = path.with_name(path.name + ".tmp")
    with open(tmp_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    os.replace(str(tmp_path), str(path))


def _viewer_audio_dir(out_dir, viewer):
    """Return <out>/<viewer>/audio when it is a plain directory inside out_dir.

    Returns None when the identity constraints do not hold; callers must then
    copy nothing and attach no audio for that viewer (fail-safe against writing
    through a junction/symlink that points somewhere else).
    """
    viewer_dir = Path(out_dir) / viewer
    audio_dir = viewer_dir / "audio"
    try:
        resolved_out = Path(out_dir).resolve()
        resolved_viewer = viewer_dir.resolve()
        resolved_audio = audio_dir.resolve()
    except (OSError, RuntimeError):
        return None
    if resolved_viewer != resolved_out / viewer:
        return None
    if resolved_audio != resolved_out / viewer / "audio":
        return None
    return audio_dir


def _is_reusable_audio_target(target, source, resolved_audio_dir):
    """True only when `target` 本身就是一个独立、就地、内容匹配的普通文件。

    复用（unchanged）必须用 os.lstat 确认：是普通文件、不是链接（S_ISREG 为真
    且 S_ISLNK 为假）、st_nlink == 1（硬链接不得复用，必须重新独立复制）、且解析
    后的位置就是预期位置；再比较大小与整秒 mtime。任一条不满足都返回 False，
    调用方会重新复制，从而绝不会写穿到源文件。
    """
    try:
        dst_lstat = os.lstat(str(target))
    except OSError:
        return False
    if not stat.S_ISREG(dst_lstat.st_mode) or stat.S_ISLNK(dst_lstat.st_mode):
        return False
    if dst_lstat.st_nlink != 1:
        return False
    try:
        resolved_target = target.resolve()
        src_stat = source.stat()
    except (OSError, RuntimeError):
        return False
    if resolved_target != resolved_audio_dir / target.name:
        return False
    if src_stat.st_size != dst_lstat.st_size:
        return False
    if int(src_stat.st_mtime) != int(dst_lstat.st_mtime):
        return False
    return True


def _copy_viewer_audio(out_dir, viewer, sources, stats):
    """Copy one viewer's clips into <out>/<viewer>/audio/.

    Returns the set of basenames that are in place, or None when the target
    directory identity check fails. Only plain copies are used - never hard
    links or symlinks - so nothing can ever write back into the source tree.
    """
    audio_dir = _viewer_audio_dir(out_dir, viewer)
    if audio_dir is None:
        return None
    try:
        audio_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        stats["rejected"] += len(sources)
        print(("warning: cannot create audio dir %s: %s" % (audio_dir, exc)).encode("ascii", "replace").decode("ascii"), file=sys.stderr)
        return set()
    try:
        resolved_audio_dir = audio_dir.resolve()
    except (OSError, RuntimeError):
        stats["rejected"] += len(sources)
        return set()

    placed = set()
    for basename, source in sources.items():
        target = audio_dir / basename
        try:
            if _is_reusable_audio_target(target, source, resolved_audio_dir):
                stats["unchanged"] += 1
                placed.add(basename)
                continue
        except OSError:
            pass

        # 每次都用一个排他创建的全新随机临时文件：固定名字的 .tmp 在并发下会发布
        # 半截文件，而且若事先存在一个指向源文件的符号链接／硬链接，copy2 会把源
        # 文件写穿。mkstemp 同时消灭这两个问题。
        tmp_path = None
        try:
            fd, tmp_name = tempfile.mkstemp(
                dir=str(audio_dir),
                prefix="." + basename + ".",
                suffix=".tmp",
            )
            tmp_path = Path(tmp_name)
            os.close(fd)
            shutil.copy2(str(source), str(tmp_path))
            os.replace(str(tmp_path), str(target))
            tmp_path = None
            stats["copied"] += 1
            placed.add(basename)
        except OSError as exc:
            # 只清理自己创建的临时文件，然后计 rejected，绝不附进 JSON。
            if tmp_path is not None:
                try:
                    os.unlink(str(tmp_path))
                except OSError:
                    pass
            stats["rejected"] += 1
            print(("warning: cannot copy audio %s: %s" % (source, exc)).encode("ascii", "replace").decode("ascii"), file=sys.stderr)
    return placed


def _filter_payload_audio(payload, keep_files):
    """Drop 'audio' entries that are not in keep_files; remove the key if empty."""
    for session in payload.get("sessions") or []:
        for turn in session.get("turns") or []:
            audios = turn.get("audio")
            if not audios:
                continue
            kept = [item for item in audios if item.get("file") in keep_files]
            if kept:
                turn["audio"] = kept
            else:
                del turn["audio"]


def _referenced_audio_basenames(payload):
    """Basenames of every clip actually referenced by this payload."""
    result = set()
    for session in payload.get("sessions") or []:
        for turn in session.get("turns") or []:
            for item in turn.get("audio") or ():
                file_field = item.get("file")
                if isinstance(file_field, str) and file_field.startswith("audio/"):
                    result.add(file_field[len("audio/"):])
    return result


def _remove_audio_references(payload, bad_keys):
    """移除引用了 bad_keys 中任一 normcase(basename) 的全部 audio 条目。

    列表空了就删掉 "audio" 键。返回被移除的引用条数（每条被移除的引用计一次）。
    """
    removed = 0
    for session in payload.get("sessions") or []:
        for turn in session.get("turns") or []:
            audios = turn.get("audio")
            if not audios:
                continue
            kept = []
            for item in audios:
                file_field = item.get("file")
                if (isinstance(file_field, str) and file_field.startswith("audio/")
                        and os.path.normcase(file_field[len("audio/"):]) in bad_keys):
                    removed += 1
                    continue
                kept.append(item)
            if kept:
                turn["audio"] = kept
            else:
                del turn["audio"]
    return removed


def _reject_text_conflicting_audio(payload, audio_stats, viewer):
    """同一个音频文件被 text 不同的记录引用时，拒绝该 basename 的全部引用。

    页面回放按「段文本完全相等」给气泡配音频。若同一个音频文件（按
    os.path.normcase(basename) 判定）在本 viewer 内被两条及以上 text 不同的有效记录
    引用，那么必有一段文字会配上别的段的声音。tts_server 正常情况下每次保存都是唯一
    文件名、只写一条记录，所以这只可能来自日志被重复或篡改——但宁可不给语音，也不能
    让她的声音配错字。因此整组拒绝：从复制计划与所有回合的 audio 列表中移除（列表空了
    就删掉 "audio" 键），每条被移除的引用计入 rejected，并打印一行 ASCII 告警。
    text 完全相同的重复引用不算冲突，保持原行为。

    Returns the set of rejected normcase(basename) keys (empty when no conflict).
    """
    texts_by_key = {}
    for session in payload.get("sessions") or []:
        for turn in session.get("turns") or []:
            for item in turn.get("audio") or ():
                file_field = item.get("file")
                if not isinstance(file_field, str) or not file_field.startswith("audio/"):
                    continue
                key = os.path.normcase(file_field[len("audio/"):])
                texts_by_key.setdefault(key, set()).add(item.get("text"))

    bad_keys = {k for k, texts in texts_by_key.items() if len(texts) >= 2}
    if not bad_keys:
        return bad_keys

    removed = _remove_audio_references(payload, bad_keys)

    audio_stats["rejected"] += removed
    print(
        ("warning: %s/audio: refusing %d entries whose file is referenced with "
         "different texts: %s" % (viewer, removed, ", ".join(sorted(bad_keys))))
        .encode("ascii", "replace").decode("ascii"),
        file=sys.stderr,
    )
    return bad_keys


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

    per_viewer_subdir = bool(opts.get("per_viewer_subdir", False))

    if per_viewer_subdir:
        # 铁律：会话日志源文件绝不能被改动或删除。若 out_dir 与 person_dir/sessions
        # 相等或互相包含，陈旧清理就可能把源 WAV 当成陈旧产物删掉，因此直接拒绝运行。
        # （validate_paths 本身不改，flat 模式行为保持不变。）
        overlap_err = _check_out_not_overlapping_sessions(person_dir, out_dir)
        if overlap_err:
            raise ValueError(overlap_err)

    # 整轮（读日志、复制、写 JSON、清理）都在跨进程锁内完成。tts_server 内部的
    # threading.Lock 管不到手工运行的 CLI，互斥必须落到文件系统上。
    with _acquire_out_lock(person_dir, out_dir):
        return _ingest_locked(
            person_dir,
            out_dir,
            per_viewer_subdir=per_viewer_subdir,
            exclude_file=exclude_file,
            patterns_path=patterns_path,
            generated_at=generated_at,
            card_max_lines=card_max_lines,
            card_line_chars=card_line_chars,
            exchange_chars=exchange_chars,
        )


def _ingest_locked(person_dir, out_dir, *, per_viewer_subdir, exclude_file,
                   patterns_path, generated_at, card_max_lines,
                   card_line_chars, exchange_chars):
    """实际摄入流程；调用方必须已持有 out_dir 的跨进程锁。"""
    audio_plan = {}
    payloads, global_stats = build_sessions(
        person_dir,
        exclude_file=exclude_file,
        patterns_path=patterns_path,
        card_max_lines=card_max_lines,
        card_line_chars=card_line_chars,
        exchange_chars=exchange_chars,
        generated_at=generated_at,
        attach_audio=per_viewer_subdir,
        audio_plan=audio_plan,
    )

    out_dir.mkdir(parents=True, exist_ok=True)

    audio_stats = None
    audio_sources = {}
    expected_audio = {}
    if per_viewer_subdir:
        audio_stats = {
            "copied": 0,
            "unchanged": 0,
            "rejected": int(audio_plan.get("rejected") or 0),
        }
        audio_sources = audio_plan.get("sources") or {}

    written_files = []
    written_viewers = set()
    for viewer, payload in payloads.items():
        if per_viewer_subdir:
            viewer_dir = out_dir / viewer
            viewer_dir.mkdir(parents=True, exist_ok=True)
            # Audio must be fully in place before the json that references it.
            viewer_sources = audio_sources.get(viewer) or {}
            if viewer_sources:
                # 同一个音频文件被 text 不同的记录引用时，必有一段文字会配上别的段的
                # 声音，因此整组拒绝（见 _reject_text_conflicting_audio）。必须在复制
                # 之前先从复制计划与所有回合的 audio 列表里一起移除。
                _bad_keys = _reject_text_conflicting_audio(payload, audio_stats, viewer)
                # 同一个目标 basename 若对应两个及以上「解析后不同的源」，那么无论先复制
                # 哪一个，目标文件都只有一个，两份引用就会指向同一段声音（一个会话的气泡
                # 播放另一个会话的音频）。因此必须在按 basename 去重之前比较每一个解析后的
                # 源：先按 os.path.normcase(basename) 分组（Windows 上多个会话的 SID 只差
                # 大小写时会落进同一组，区分大小写的平台上基名不同仍是不同组），组内只要有
                # 两个 normcase 后不同的源就整组拒绝——该组所有引用都从各回合的 audio 列表
                # 里移除（列表空了就删掉 "audio" 键），每条被移除的引用计入 rejected 并打印
                # 一行 ASCII 告警。同一个解析后的源被多次引用不算冲突，仍只复制一次（保持
                # 原行为）。已被 text 冲突拒绝的键不再参与分组，避免重复计数或漏判。
                audio_groups = {}
                for _basename, _sources in viewer_sources.items():
                    if os.path.normcase(_basename) in _bad_keys:
                        continue
                    _group = audio_groups.setdefault(os.path.normcase(_basename), [])
                    for _source in _sources:
                        _group.append((_basename, _source))
                conflict_keys = set()
                for _norm_key, _group in audio_groups.items():
                    if len({os.path.normcase(str(_src)) for _b, _src in _group}) >= 2:
                        conflict_keys.add(_norm_key)
                if conflict_keys:
                    for _norm_key in sorted(conflict_keys):
                        _group = audio_groups[_norm_key]
                        _removed = _remove_audio_references(payload, {_norm_key})
                        audio_stats["rejected"] += _removed
                        print(
                            ("warning: %s/audio: refusing %d entries whose target name collides "
                             "under case-insensitive filesystems: %s"
                             % (viewer, _removed, ", ".join(sorted(_b for _b, _s in _group))))
                            .encode("ascii", "replace").decode("ascii"),
                            file=sys.stderr,
                        )
                _viewer_copy_plan = {}
                for _basename, _sources in viewer_sources.items():
                    _norm_key = os.path.normcase(_basename)
                    if _norm_key in _bad_keys or _norm_key in conflict_keys:
                        continue
                    _viewer_copy_plan[_basename] = _sources[0]
                placed = _copy_viewer_audio(out_dir, viewer, _viewer_copy_plan, audio_stats)
                if placed is None:
                    print(
                        ("warning: %s/audio is not a plain directory inside out dir; "
                         "no audio will be attached for viewer '%s'" % (viewer, viewer)).encode("ascii", "replace").decode("ascii"),
                        file=sys.stderr,
                    )
                    placed = set()
                _filter_payload_audio(payload, set("audio/" + b for b in placed))
            expected_audio[viewer] = _referenced_audio_basenames(payload)
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
                # Windows 文件系统不区分大小写：磁盘上可能存在 FATHER 这样的目录，
                # 它其实就是刚刚写入的 father。VIEWER_RE 只接受小写，直接拿原名匹配会
                # 失败，于是这个 viewer 的陈旧产物永远清不掉。因此先 normcase 再匹配，
                # 成员判断也用规范化后的名字；删除时仍使用真实的 existing 路径。
                # （normcase 在区分大小写的平台上是恒等变换，那些平台上 FATHER 本来
                # 就是另一个目录，继续跳过是正确的。）
                vname = os.path.normcase(existing.name)
                if not VIEWER_RE.fullmatch(vname):
                    continue
                if vname in written_viewers:
                    continue
                target = existing / "sessions.json"
                if not target.is_file():
                    continue
                target.unlink()
                deleted_files.append(f"{existing.name}/sessions.json")

        # Stale audio cleanup: only files that live directly inside
        # <out_dir>/<viewer>/audio, whose name matches the clip naming scheme,
        # and that are not referenced by this round's json. Same directory
        # identity constraints as the sessions.json cleanup above; never delete
        # directories, never recurse, never touch non-matching names.
        if out_dir.exists():
            try:
                resolved_audio_out = out_dir.resolve()
            except (OSError, RuntimeError):
                resolved_audio_out = None
            if resolved_audio_out is not None:
                for existing in out_dir.iterdir():
                    try:
                        resolved_existing = existing.resolve()
                    except (OSError, RuntimeError):
                        continue
                    if resolved_existing != resolved_audio_out / existing.name:
                        continue
                    if not existing.is_dir():
                        continue
                    # 同 sessions.json 清理：磁盘上的 FATHER 其实就是 father（Windows
                    # 不区分大小写），而 VIEWER_RE 只接受小写，直接拿原名匹配会跳过该目录，
                    # 导致它的陈旧音频残留。因此先 normcase 再匹配，查该 viewer 的期望音频
                    # 集合也用规范化后的名字；删除仍走真实的 existing 路径。
                    # （normcase 在区分大小写的平台上是恒等变换，那些平台上 FATHER 本来
                    # 就是另一个目录，继续跳过是正确的。）
                    vname = os.path.normcase(existing.name)
                    if not VIEWER_RE.fullmatch(vname):
                        continue
                    audio_dir = existing / "audio"
                    try:
                        resolved_audio_dir = audio_dir.resolve()
                    except (OSError, RuntimeError):
                        continue
                    if resolved_audio_dir != resolved_audio_out / existing.name / "audio":
                        continue
                    if not audio_dir.is_dir():
                        continue
                    # Windows 文件系统不区分大小写：复用（unchanged）判断走的是 Path 比较，
                    # 本身不区分大小写，而这里若用区分大小写的字符串集合判断，就会把刚刚被
                    # 判定为可复用的同名文件当成陈旧产物删掉，JSON 里随即留下悬空引用。
                    # 因此期望集合与待检查名称都先经 os.path.normcase() 规范化后再比较
                    # （它在区分大小写的平台上是恒等变换，不影响那些平台）。
                    expected = {
                        os.path.normcase(_b)
                        for _b in expected_audio.get(vname, set())
                    }
                    try:
                        audio_items = list(audio_dir.iterdir())
                    except OSError:
                        continue
                    for item in audio_items:
                        name = item.name
                        # Windows 文件系统不区分大小写：复用（unchanged）判断走的是 Path
                        # 比较，本身不区分大小写，而 AUDIO_BASENAME_RE 是小写模式。若磁盘上
                        # 已存在的目标名固定部分大小写不同（SESSION_ 前缀、_T001、.WAV），
                        # 正则会因大小写不匹配而跳过它，音频就永远留在输出目录里清不掉。
                        # 因此先算 normcase 再匹配正则、再用同一个 key 判断期望集合
                        # （Windows 上 normcase 会转小写，正好匹配小写模式；非 Windows 平台
                        # normcase 为恒等变换，行为不变），删除仍走真实的 item 路径。
                        key = os.path.normcase(name)
                        if not AUDIO_BASENAME_RE.match(key):
                            continue
                        if key in expected:
                            continue
                        # 删除前用 os.lstat 确认要删的是普通文件（不是目录、不是链接）。
                        try:
                            item_lstat = os.lstat(str(item))
                        except OSError:
                            continue
                        if not stat.S_ISREG(item_lstat.st_mode):
                            continue
                        try:
                            resolved_item = item.resolve()
                        except (OSError, RuntimeError):
                            continue
                        if resolved_item.parent != resolved_audio_dir:
                            continue
                        try:
                            item.unlink()
                        except OSError:
                            continue
                        deleted_files.append(f"{existing.name}/audio/{name}")
    else:
        # Delete stale matching files in out_dir that were not written
        written_set = set(written_files)
        if out_dir.exists():
            for existing in out_dir.iterdir():
                if existing.is_file() and OUT_NAME_RE.match(existing.name):
                    if existing.name not in written_set:
                        existing.unlink()
                        deleted_files.append(existing.name)

    result = {
        "written": written_files,
        "deleted": deleted_files,
        "stats": global_stats,
    }
    if per_viewer_subdir:
        result["audio"] = audio_stats
    return result


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

    if args.per_viewer_subdir:
        overlap_err = _check_out_not_overlapping_sessions(person_dir, out_dir)
        if overlap_err:
            print("error: " + overlap_err, file=sys.stderr)
            return 2

    try:
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
    except IngestLockTimeout:
        print(
            "错误：等待超时，未能取得输出目录的跨进程锁，另一个摄入进程可能正在运行；本次未做任何写入，请稍后重试。",
            file=sys.stderr,
        )
        return 3
    # Print summary to stderr
    print("written: %s" % ",".join(result["written"]), file=sys.stderr)
    if result["deleted"]:
        print("deleted: %s" % ",".join(result["deleted"]), file=sys.stderr)
    if args.per_viewer_subdir:
        audio_summary = result.get("audio") or {"copied": 0, "unchanged": 0, "rejected": 0}
        print(
            "audio: copied=%d unchanged=%d rejected=%d"
            % (audio_summary["copied"], audio_summary["unchanged"], audio_summary["rejected"]),
            file=sys.stderr,
        )
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
