#!/usr/bin/env python3
"""Apply human gate decisions to Tier-2 candidate cards and regenerate Tier-1 memories.md."""

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")

def eprint(msg: str) -> None:
    """ASCII-only stderr."""
    sys.stderr.write(msg + "\n")

def err_exit(msg: str, code: int = 2) -> None:
    """Print ASCII error and exit with code."""
    eprint(msg)
    sys.exit(code)

def compute_source_dataset(candidates: List[Dict[str, Any]]) -> str:
    """Compute 12-char dataset fingerprint from sorted candidate ids."""
    joined = "\n".join(sorted(c["candidate_id"] for c in candidates))
    return hashlib.md5(joined.encode("utf-8")).hexdigest()[:12]

def strip_fences(text: str) -> str:
    """Remove markdown fences that may wrap a paste code."""
    t = text.strip()
    if t.startswith("```"):
        # optional language tag on the first line
        first_nl = t.find("\n")
        if first_nl != -1:
            first_line = t[:first_nl].strip()
            # first_line like "```" or "```json"
            if re.fullmatch(r"```[A-Za-z0-9_+-]*", first_line):
                t = t[first_nl:].strip()
                if t.endswith("```"):
                    t = t[:-3].strip()
        elif t == "```":
            return ""
    return t

def load_decision_file(path: Path) -> Dict[str, Any]:
    """Parse a decision file; return dict or raise ValueError/JSONDecodeError."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}")
    cleaned = strip_fences(raw)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}")
    if not isinstance(data, dict):
        raise ValueError(f"{path}: top-level JSON must be an object")
    return data

def parse_timestamp_to_hhmm(ts: str) -> str:
    """Extract HH:MM (local) from an ISO-8601-like timestamp."""
    # expected e.g. 2022-07-18T17:46:22+08:00
    m = re.search(r"T(\d{2}):(\d{2})", ts)
    if m:
        return f"{m.group(1)}:{m.group(2)}"
    # fallback: split on T or space, take time part HH:MM
    parts = ts.replace("T", " ").split()
    if len(parts) >= 2 and ":" in parts[1]:
        time_part = parts[1][:5]
        if re.fullmatch(r"\d{2}:\d{2}", time_part):
            return time_part
    return "00:00"

def load_sensitive_patterns(root: Path) -> List[Dict[str, Any]]:
    """Load sensitive pattern file; return list of {name, regex, severity} or [] if missing."""
    p = root / "tools" / "sensitive_patterns.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except OSError:
        err_exit(f"error: cannot read sensitive patterns file {p}")
        return []
    except json.JSONDecodeError as exc:
        err_exit(f"error: malformed sensitive patterns file {p}: {exc}")
        return []
    if not isinstance(data, dict) or not isinstance(data.get("patterns"), list):
        err_exit(f"error: malformed sensitive patterns file {p}: expected object with 'patterns' list")
        return []
    patterns = []
    for item in data["patterns"]:
        if not isinstance(item, dict) or "name" not in item or "regex" not in item or "severity" not in item:
            err_exit(f"error: malformed sensitive pattern entry in {p}")
            return []
        patterns.append({
            "name": item["name"],
            "regex": item["regex"],
            "severity": item["severity"],
        })
    return patterns

def render_excerpt_line(exc: Dict[str, Any]) -> str:
    """Render one excerpt as a line (with HH:MM prefix), handling no-text variants."""
    hhmm = parse_timestamp_to_hhmm(exc.get("timestamp", ""))
    text = exc.get("text")
    if text and isinstance(text, str):
        return f"- {hhmm} {text}"
    dur_ms = exc.get("duration_ms")
    if isinstance(dur_ms, (int, float)):
        secs = int(round(dur_ms / 1000.0))
        return f"- {hhmm} [语音 {secs}秒]"
    return f"- {hhmm} [媒体]"

def render_entry(entry: Dict[str, Any], patterns: List[Dict[str, Any]]) -> Tuple[str, bool]:
    """Render one confirmed entry's markdown block. Returns (block, flagged_bool)."""
    title = entry.get("user_title") or entry.get("title") or "未命名记忆"
    kind_label = entry.get("kind_label", "")
    date = entry.get("date", "")
    note = entry.get("user_note", "")
    lines = [f"## {date} · {title}"]
    if kind_label:
        lines.append(f"- 类型：{kind_label}")
    if note:
        lines.append(f"- 备注：{note}")
    excerpts = entry.get("excerpts", [])
    for exc in excerpts:
        if isinstance(exc, dict):
            lines.append(render_excerpt_line(exc))
    record_ids = [e.get("record_id", "") for e in excerpts if isinstance(e, dict) and e.get("record_id")]
    if record_ids:
        joined = ",".join(record_ids)
        lines.append(f"- <details>来源 record_id：`{joined}`</details>")
    else:
        # no excerpts with record_id — still provide an empty details for consistency
        lines.append("- <details>来源 record_id：</details>")

    # sensitive re-check
    rendered_text = " ".join([title, note] + [
        e.get("text", "") for e in excerpts
        if isinstance(e, dict) and isinstance(e.get("text"), str)
    ])
    flagged = False
    for pat in patterns:
        try:
            if re.search(pat["regex"], rendered_text, re.IGNORECASE):
                severity = pat.get("severity", "medium")
                if severity == "high":
                    flagged = True
                    break
        except re.error:
            continue
    if flagged:
        lines.append("⚠️ 含疑似敏感内容，导出档案前请再确认")
    return "\n".join(lines), flagged

def posix_repo_relative(path: Path, root: Path) -> str:
    """Return repo-relative posix path if under root, else absolute posix."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()

def main() -> int:
    parser = argparse.ArgumentParser(description="Apply gate decisions to candidates and regenerate memories.md.")
    parser.add_argument("--person", required=True)
    parser.add_argument("--decisions", required=True, nargs="+", type=Path)
    parser.add_argument("--candidates", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--allow-dataset-mismatch", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    slug = args.person
    if not SLUG_RE.match(slug):
        err_exit(f"error: invalid slug '{slug}'")
        return 2

    # repo root = parent of tools/
    tools_dir = Path(__file__).resolve().parent
    root = tools_dir.parent

    # Resolve candidate/out/ decision paths, canonicalize to detect raw/ violations
    base = root / "people" / slug
    candidates_path = args.candidates or base / "memories" / "candidates.jsonl"
    out_path = args.out or base / "memories" / "memories.md"

    raw_dir = (base / "raw").resolve()
    for p in [candidates_path, out_path] + list(args.decisions):
        try:
            resolved = (root / p).resolve() if not p.is_absolute() else p.resolve()
        except OSError:
            err_exit(f"error: cannot resolve path {p}")
            return 2
        try:
            resolved.relative_to(raw_dir)
            err_exit(f"error: path {p} is under raw/ and untouchable")
            return 2
        except ValueError:
            pass

    # 1. Load candidates
    try:
        raw_bytes = candidates_path.read_bytes()
    except OSError as exc:
        err_exit(f"error: cannot read candidates {candidates_path}: {exc}")
        return 2
    lines = raw_bytes.split(b"\n")
    # drop trailing empty line artifact if present
    if lines and lines[-1] == b"":
        lines.pop()
    candidates: List[Dict[str, Any]] = []
    line_bytes: List[bytes] = []
    for ln in lines:
        if not ln.strip():
            continue
        try:
            obj = json.loads(ln.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            err_exit(f"error: bad JSON line in candidates: {exc}")
            return 2
        candidates.append(obj)
        line_bytes.append(ln)

    # 2. Load decisions files, validate en masse before any write
    decisions_list: List[List[Dict[str, Any]]] = []
    dataset_hashes: List[str] = []
    for df in args.decisions:
        try:
            data = load_decision_file(df)
        except ValueError as exc:
            err_exit(f"error: {exc}")
            return 2
        if data.get("v") != 1:
            err_exit(f"error: {df}: unknown v (expected 1, got {data.get('v')})")
            return 2
        ds = data.get("source_dataset")
        if not isinstance(ds, str) or len(ds) != 12:
            err_exit(f"error: {df}: invalid source_dataset")
            return 2
        dataset_hashes.append(ds)
        decs = data.get("decisions", [])
        if not isinstance(decs, list):
            err_exit(f"error: {df}: decisions must be a list")
            return 2
        parsed = []
        for d in decs:
            if not isinstance(d, dict) or "id" not in d or "action" not in d:
                err_exit(f"error: {df}: invalid decision entry")
                return 2
            act = d["action"]
            if act not in ("confirm", "reject", "pending"):
                err_exit(f"error: {df}: unknown action '{act}'")
                return 2
            parsed.append(d)
        decisions_list.append(parsed)

    # dataset hash check against current file
    current_ds = compute_source_dataset(candidates)
    for i, df in enumerate(args.decisions):
        if dataset_hashes[i] != current_ds:
            if args.allow_dataset_mismatch:
                continue
            err_exit(
                f"error: dataset mismatch in {df}: expected {dataset_hashes[i]}, "
                f"current {current_ds} (use --allow-dataset-mismatch to override)"
            )
            return 2

    # unknown IDs check
    known_ids = {c["candidate_id"] for c in candidates}
    unknown_ids = []
    for decs in decisions_list:
        for d in decs:
            cid = d["id"]
            if cid not in known_ids:
                if cid not in unknown_ids:
                    unknown_ids.append(cid)
    if unknown_ids:
        err_exit(f"error: unknown candidate_id(s): {', '.join(unknown_ids)}")
        return 2

    # 3. Merge decisions (later files, then later entries within file)
    merged: Dict[str, Dict[str, Any]] = {}
    for decs in decisions_list:
        for d in decs:
            merged[d["id"]] = d

    # 4. Compute post-merge state in memory (no writes)
    now_iso = datetime.now().astimezone().isoformat(timespec="seconds")
    new_lines: List[bytes] = []
    for orig_bytes, cand in zip(line_bytes, candidates):
        dec = merged.get(cand["candidate_id"])
        if dec is None:
            new_lines.append(orig_bytes)
            continue
        new_obj = dict(cand)
        act = dec["action"]
        if act == "pending":
            # revert: status pending, remove user_title/user_note/decided_at
            new_obj["status"] = "pending"
            new_obj.pop("user_title", None)
            new_obj.pop("user_note", None)
            new_obj.pop("decided_at", None)
        else:
            new_obj["status"] = "confirmed" if act == "confirm" else "rejected"
            if "title" in dec and dec.get("title"):
                new_obj["user_title"] = dec["title"]
            if "note" in dec and dec.get("note"):
                new_obj["user_note"] = dec["note"]
            new_obj["decided_at"] = now_iso
        serialized = json.dumps(new_obj, ensure_ascii=False, separators=(",", ":"))
        new_lines.append(serialized.encode("utf-8"))

    # Post-merge candidates
    final_cands: List[Dict[str, Any]] = []
    for ln in new_lines:
        if not ln.strip():
            continue
        final_cands.append(json.loads(ln.decode("utf-8")))

    if args.dry_run:
        n_confirmed = sum(1 for c in final_cands if c.get("status") == "confirmed")
        n_rejected = sum(1 for c in final_cands if c.get("status") == "rejected")
        n_pending = len(final_cands) - n_confirmed - n_rejected
        confirmed_entries = [c for c in final_cands if c.get("status") == "confirmed"]
        confirmed_entries.sort(key=lambda c: (c.get("date", ""), c.get("candidate_id", "")))
        patterns = load_sensitive_patterns(root)
        flagged_count = 0
        for ent in confirmed_entries:
            _, flagged = render_entry(ent, patterns)
            if flagged:
                flagged_count += 1
        print(f"applied={len(merged)} confirmed={n_confirmed} rejected={n_rejected} "
              f"pending={n_pending} confirmed_flagged={flagged_count} "
              f"memories={posix_repo_relative(out_path, root)}")
        return 0

    # 5. Rewrite candidates atomically
    try:
        fd, tmp_path = tempfile.mkstemp(dir=str(candidates_path.parent), suffix=".tmp")
        with os.fdopen(fd, "wb") as f:
            for ln in new_lines:
                f.write(ln + b"\n")
        os.replace(tmp_path, candidates_path)
    except OSError as exc:
        err_exit(f"error: failed writing candidates: {exc}")
        return 2

    # 6. Regenerate memories.md
    confirmed_entries = [c for c in final_cands if c.get("status") == "confirmed"]
    n_confirmed = len(confirmed_entries)
    n_rejected = sum(1 for c in final_cands if c.get("status") == "rejected")
    n_pending = len(final_cands) - n_confirmed - n_rejected
    confirmed_entries.sort(key=lambda c: (c.get("date", ""), c.get("candidate_id", "")))

    patterns = load_sensitive_patterns(root)
    flagged_count = 0
    entry_blocks: List[str] = []
    for ent in confirmed_entries:
        block, flagged = render_entry(ent, patterns)
        entry_blocks.append(block)
        if flagged:
            flagged_count += 1

    source_ds = current_ds
    now_str = datetime.now().astimezone().isoformat(timespec="seconds")
    header = [
        f"# 记忆册（Tier-1 · 家人已确认）· {slug}",
        "",
        "> 本册由人工闸门确认生成。每条记忆的原始出处见条目末尾的 record_id 列表。",
        f"> 数据集 {source_ds} · 候选 {len(final_cands)} 条 · 已确认 {n_confirmed} · "
        f"已剔除 {n_rejected} · 待定 {n_pending}",
        f"> 生成时间 {now_str}",
        "",
    ]
    md = "\n".join(header)
    if entry_blocks:
        md += "\n\n" + "\n\n".join(entry_blocks)
    md += "\n"

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fd2, tmp2 = tempfile.mkstemp(dir=str(out_path.parent), suffix=".tmp")
        with os.fdopen(fd2, "w", encoding="utf-8") as f:
            f.write(md)
        os.replace(tmp2, out_path)
    except OSError as exc:
        err_exit(f"error: failed writing memories.md: {exc}")
        return 2

    # 7. stdout summary
    print(f"applied={len(merged)} confirmed={n_confirmed} rejected={n_rejected} "
          f"pending={n_pending} confirmed_flagged={flagged_count} "
          f"memories={posix_repo_relative(out_path, root)}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
