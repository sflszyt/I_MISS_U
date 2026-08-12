#!/usr/bin/env python3
"""Scrub sensitive records from derived layers of a digital archive.

Usage:
  python tools/scrub_sensitive.py scan   --person <slug> [--patterns <path>] [--out-dir <dir>]
  python tools/scrub_sensitive.py apply  --person <slug> --ids-file <path> --reason <text> [--dry-run] [--allow-missing]
  python tools/scrub_sensitive.py verify --person <slug> [--ids-file <path>]
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants and global state
# ---------------------------------------------------------------------------

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
ID_RE = re.compile(r"^[0-9a-f]{64}$")

SCAN_REPORT_JSONL = "sensitive_scan_report.jsonl"
SCAN_REPORT_MD = "sensitive_scan_report.md"
MANIFEST = "scrub_manifest.jsonl"

SCRUB_DATA_FILES = {SCAN_REPORT_JSONL, SCAN_REPORT_MD, MANIFEST}

EXCLUDED_SCAN_KEYS = {
    "record_id", "person", "viewpoint", "source", "tier", "lang",
    "timestamp", "timestamp_precision", "content_type", "record_type",
    "msg_type_native", "conversation_id", "chat_room", "sender",
    "sender_wxid",
}

ROOT = Path(__file__).resolve().parent.parent
PEOPLE_DIR = ROOT / "people"

_severity_rank = {"high": 0, "medium": 1, "low": 2}


def exit_error(msg):
    """Print ASCII-only message to stderr and exit with code 2."""
    print(msg.encode("ascii", "replace").decode("ascii"), file=sys.stderr)
    sys.exit(2)


def validate_slug(slug):
    """Validate slug and return the person directory."""
    if not SLUG_RE.match(slug):
        exit_error(f"error: invalid slug '{slug}'")
    person_dir = PEOPLE_DIR / slug
    people_resolved = PEOPLE_DIR.resolve()
    try:
        inside = person_dir.resolve().is_relative_to(people_resolved)
    except AttributeError:
        # Python < 3.9 fallback (should not happen with 3.10+, kept for safety)
        person_str = str(person_dir.resolve())
        people_str = str(people_resolved)
        inside = person_str.startswith(people_str + os.sep)
    if not inside:
        exit_error(f"error: person dir not inside people dir: {person_dir}")
    return person_dir


class RawGuard:
    """Central raw/ guard. Every file open must go through this."""

    def __init__(self, raw_dir):
        self.raw_dir = raw_dir.resolve()

    def assert_not_raw(self, path):
        p = Path(path).resolve()
        try:
            if p.is_relative_to(self.raw_dir):
                raise ValueError(f"refusing to touch raw/ path: {path}")
        except AttributeError:
            if str(p).startswith(str(self.raw_dir) + os.sep):
                raise ValueError(f"refusing to touch raw/ path: {path}")
        if p == self.raw_dir:
            raise ValueError(f"refusing to touch raw/ path: {path}")


def scrub_data_paths(person_dir):
    """Return set of resolved paths to the three scrub data files in normalized/."""
    normalized_dir = person_dir / "normalized"
    paths = set()
    for fname in SCRUB_DATA_FILES:
        paths.add((normalized_dir / fname).resolve())
    return paths


# ---------------------------------------------------------------------------
# Shared I/O helpers
# ---------------------------------------------------------------------------

def read_jsonl_lines(path, guard):
    """Read a JSONL file and yield (line_no, line_bytes, parsed_obj_or_None)
    for lines that parse as dict with string record_id.
    """
    guard.assert_not_raw(path)
    with open(path, "rb") as f:
        for line_no, line_bytes in enumerate(f, start=1):
            try:
                text = line_bytes.decode("utf-8")
            except UnicodeDecodeError:
                yield line_no, line_bytes, None
                continue
            try:
                obj = json.loads(text)
                if isinstance(obj, dict) and isinstance(obj.get("record_id"), str):
                    yield line_no, line_bytes, obj
                else:
                    yield line_no, line_bytes, None
            except json.JSONDecodeError:
                yield line_no, line_bytes, None


def get_uif_targets(person_dir, guard):
    """Return sorted list of UIF target .jsonl files directly in normalized/,
    excluding the three scrub data files."""
    normalized_dir = person_dir / "normalized"
    if not normalized_dir.is_dir():
        return []
    targets = []
    scrub_data = scrub_data_paths(person_dir)
    for child in sorted(normalized_dir.iterdir()):
        if child.is_file() and child.suffix == ".jsonl":
            if child.name in SCRUB_DATA_FILES:
                continue
            if child.resolve() in scrub_data:
                continue
            targets.append(child)
    return targets


def rel_posix(path):
    """Return path relative to repo root with posix separators."""
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def safe_print_ascii(s):
    """Print ASCII-safe to stdout."""
    sys.stdout.write(s.encode("ascii", "replace").decode("ascii") + "\n")


def compile_patterns(patterns_path, guard):
    """Load and compile pattern config. Returns list of (name, regex, severity, compiled)."""
    try:
        guard.assert_not_raw(patterns_path)
    except ValueError:
        exit_error(f"error: patterns file is under raw/: {patterns_path}")
    try:
        with open(patterns_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        exit_error(f"error: cannot load patterns file: {patterns_path}: {e}")

    if not isinstance(config, dict) or not isinstance(config.get("patterns"), list):
        exit_error(f"error: patterns file schema invalid: {patterns_path}")

    compiled = []
    for i, pat in enumerate(config["patterns"]):
        if not isinstance(pat, dict):
            exit_error(f"error: pattern #{i} not an object")
        name = pat.get("name")
        regex = pat.get("regex")
        severity = pat.get("severity")
        if not isinstance(name, str) or not isinstance(regex, str):
            exit_error(f"error: pattern #{i} missing name/regex")
        if severity not in ("high", "medium", "low"):
            exit_error(f"error: pattern '{name}' has invalid severity")
        try:
            compiled_re = re.compile(regex, re.IGNORECASE)
        except re.error as e:
            exit_error(f"error: cannot compile pattern '{name}': {e}")
        compiled.append((name, regex, severity, compiled_re))
    return compiled


def build_scan_text(obj):
    """Build scan text from top-level string values, excluding certain keys."""
    parts = []
    for key, value in obj.items():
        if key in EXCLUDED_SCAN_KEYS:
            continue
        if key == "provenance":
            continue
        if isinstance(value, str):
            parts.append(value)
    return "\n".join(parts)


def mask_digits(s):
    """Replace runs of ≥4 digits with same-length asterisks."""
    return re.sub(r"\d{4,}", lambda m: "*" * len(m.group(0)), s)


# ---------------------------------------------------------------------------
# scan mode
# ---------------------------------------------------------------------------

def cmd_scan(args):
    person_dir = validate_slug(args.person)
    raw_dir = person_dir / "raw"
    guard = RawGuard(raw_dir)

    patterns_path = Path(args.patterns) if args.patterns else (ROOT / "tools" / "sensitive_patterns.json")
    patterns = compile_patterns(patterns_path, guard)

    if args.out_dir:
        report_dir = Path(args.out_dir)
    else:
        report_dir = person_dir / "normalized"
    guard.assert_not_raw(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    scan_report_jsonl_path = report_dir / SCAN_REPORT_JSONL
    scan_report_md_path = report_dir / SCAN_REPORT_MD

    targets = get_uif_targets(person_dir, guard)

    hits = []  # list of hit dicts
    scanned = 0
    skipped_lines = 0
    pattern_counts = {}  # name -> count
    year_counts = {}     # year -> count
    for pattern_name, _, _, _ in patterns:
        pattern_counts[pattern_name] = 0

    for target in targets:
        for line_no, line_bytes, obj in read_jsonl_lines(target, guard):
            if obj is None:
                skipped_lines += 1
                continue
            scanned += 1
            scan_text = build_scan_text(obj)
            matched = []
            max_sev = None
            for name, _, severity, compiled in patterns:
                if compiled.search(scan_text):
                    matched.append(name)
                    pattern_counts[name] = pattern_counts.get(name, 0) + 1
                    if max_sev is None or _severity_rank[severity] < _severity_rank[max_sev]:
                        max_sev = severity
            if matched:
                year = str(obj.get("timestamp", ""))[:4]
                year_counts[year] = year_counts.get(year, 0) + 1
                excerpt = mask_digits(scan_text[:60]).replace("\n", "\u23ce")
                hit = {
                    "record_id": obj["record_id"],
                    "source_file": rel_posix(target),
                    "timestamp": obj.get("timestamp", ""),
                    "conversation_id": obj.get("conversation_id", ""),
                    "sender": obj.get("sender", ""),
                    "content_type": obj.get("content_type", ""),
                    "text_len": len(scan_text),
                    "patterns": matched,
                    "max_severity": max_sev,
                    "excerpt": excerpt,
                }
                hits.append(hit)

    # Sort hits for report: severity high->low, patterns count desc
    hits_sorted = sorted(
        hits,
        key=lambda h: (
            _severity_rank.get(h["max_severity"], 99),
            -len(h["patterns"]),
        ),
    )

    # Write JSONL report (overwrite)
    guard.assert_not_raw(scan_report_jsonl_path)
    with open(scan_report_jsonl_path, "w", encoding="utf-8") as f:
        for hit in hits_sorted:
            f.write(json.dumps(hit, ensure_ascii=False) + "\n")

    # Write MD report (overwrite)
    guard.assert_not_raw(scan_report_md_path)
    with open(scan_report_md_path, "w", encoding="utf-8") as f:
        f.write("# 敏感信息扫描报告\n\n")
        f.write(f"- 扫描记录数: {scanned}\n")
        f.write(f"- 命中记录数: {len(hits)}\n")
        f.write(f"- 跳过行数: {skipped_lines}\n\n")
        f.write("## 各模式命中数\n\n")
        f.write("| 模式 | 严重级别 | 命中数 |\n")
        f.write("|------|----------|--------|\n")
        for name, _, severity, _ in patterns:
            f.write(f"| {name} | {severity} | {pattern_counts.get(name, 0)} |\n")
        f.write("\n## 按年份分布\n\n")
        f.write("| 年份 | 命中数 |\n")
        f.write("|------|--------|\n")
        for year in sorted(year_counts.keys()):
            f.write(f"| {year} | {year_counts[year]} |\n")
        f.write("\n## 命中记录 Top-10\n\n")
        for hit in hits_sorted[:10]:
            f.write(f"- `{hit['record_id'][:12]}...` | {hit['timestamp']} | {','.join(hit['patterns'])} | {hit['excerpt']}\n")

    safe_print_ascii(
        f"scanned={scanned} hits={len(hits)} report={rel_posix(scan_report_jsonl_path)}"
    )
    return 0


# ---------------------------------------------------------------------------
# apply mode
# ---------------------------------------------------------------------------

def load_ids_file(ids_file_path, guard):
    """Load and validate ids file. Returns set of ids."""
    try:
        guard.assert_not_raw(ids_file_path)
    except ValueError:
        exit_error(f"error: ids file is under raw/: {ids_file_path}")
    try:
        with open(ids_file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        exit_error(f"error: cannot read ids file: {e}")

    ids = set()
    bad_lines = []
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not ID_RE.match(stripped):
            bad_lines.append(i)
        else:
            ids.add(stripped)

    if bad_lines:
        exit_error(f"error: invalid ids on lines: {','.join(map(str, bad_lines))}")
    return ids


def cmd_apply(args):
    person_dir = validate_slug(args.person)
    raw_dir = person_dir / "raw"
    guard = RawGuard(raw_dir)

    if not args.reason or not args.reason.strip():
        exit_error("error: --reason is required and must be non-empty")

    ids = load_ids_file(args.ids_file, guard)
    if not ids:
        exit_error("error: ids file contains no valid ids")

    manifest_path = person_dir / "normalized" / MANIFEST
    guard.assert_not_raw(manifest_path)

    targets = get_uif_targets(person_dir, guard)

    # PASS 1: count occurrences
    id_locations = {}  # id -> list of (file_path, line_no)
    file_hits = {}     # file_path -> set of ids
    for target in targets:
        for line_no, line_bytes, obj in read_jsonl_lines(target, guard):
            if obj is None:
                continue
            rid = obj.get("record_id", "")
            if rid in ids:
                id_locations.setdefault(rid, []).append((target, line_no))
                file_hits.setdefault(target, set()).add(rid)

    # Check for unmatched ids
    found_ids = set(id_locations.keys())
    missing_ids = ids - found_ids
    if missing_ids and not args.allow_missing:
        for rid in sorted(missing_ids):
            safe_print_ascii(f"unmatched: {rid}")
        exit_error("error: unmatched ids (use --allow-missing to proceed)")

    # Dry run
    if args.dry_run:
        total = sum(len(v) for v in id_locations.values())
        file_occurrences = {}
        for rid, locations in id_locations.items():
            for fpath, _ in locations:
                file_occurrences[fpath] = file_occurrences.get(fpath, 0) + 1
        for target in sorted(file_occurrences.keys()):
            safe_print_ascii(
                f"would-remove {file_occurrences[target]} from {rel_posix(target)}"
            )
        safe_print_ascii(f"total={total}")
        return 0

    # PASS 2: rewrite files with hits
    total_removed = 0
    manifest_lines = []

    for target in sorted(file_hits.keys()):
        target_ids = file_hits[target]
        removed_in_file = 0
        kept_lines = []
        removed_records = []

        for line_no, line_bytes, obj in read_jsonl_lines(target, guard):
            if obj is not None and obj.get("record_id", "") in target_ids:
                removed_in_file += 1
                rid = obj["record_id"]
                removed_records.append({
                    "record_id": rid,
                    "source_file": rel_posix(target),
                    "timestamp": obj.get("timestamp", ""),
                    "conversation_id": obj.get("conversation_id", ""),
                    "sender": obj.get("sender", ""),
                    "content_type": obj.get("content_type", ""),
                    "text_len": len(build_scan_text(obj)),
                })
            else:
                kept_lines.append(line_bytes)

        # Write temp file and replace atomically
        tmp_path = target.with_name(target.name + ".scrub_tmp")
        guard.assert_not_raw(tmp_path)
        try:
            with open(tmp_path, "wb") as f:
                f.writelines(kept_lines)
            os.replace(tmp_path, target)
        except Exception:
            try:
                tmp_path.unlink()
            except OSError:
                pass
            raise

        # Append manifest lines
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with open(manifest_path, "a", encoding="utf-8") as f:
            for rec in removed_records:
                line = {
                    **rec,
                    "reason": args.reason,
                    "removed_at": now,
                    "tool": "scrub_sensitive.py",
                }
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
                manifest_lines.append(line)

        total_removed += removed_in_file
        safe_print_ascii(
            f"removed {removed_in_file} from {rel_posix(target)}"
        )

    safe_print_ascii(f"total={total_removed} manifest={rel_posix(manifest_path)}")
    return 0


# ---------------------------------------------------------------------------
# verify mode
# ---------------------------------------------------------------------------

VERIFY_EXTENSIONS = {".json", ".jsonl", ".md", ".html", ".txt", ".csv"}


def collect_verify_files(person_dir, guard):
    """Collect files to verify, excluding scrub data files."""
    files = []
    base_dirs = [
        person_dir / "normalized",
        person_dir / "archive_out",
        person_dir / "memories",
        person_dir / "persona",
    ]
    scrub_data = scrub_data_paths(person_dir)
    for base in base_dirs:
        if not base.is_dir():
            continue
        guard.assert_not_raw(base)
        for root, dirs, filenames in os.walk(base):
            root_path = Path(root)
            # Prune raw/ if somehow encountered
            dirs[:] = [d for d in dirs if not (root_path / d).resolve().is_relative_to(guard.raw_dir)]
            for fname in filenames:
                fpath = root_path / fname
                if fpath.suffix.lower() in VERIFY_EXTENSIONS:
                    # Exclude the three scrub data files wherever they appear
                    if fpath.name in SCRUB_DATA_FILES:
                        continue
                    if fpath.resolve() in scrub_data:
                        continue
                    files.append(fpath)
    return sorted(files)


def cmd_verify(args):
    person_dir = validate_slug(args.person)
    raw_dir = person_dir / "raw"
    guard = RawGuard(raw_dir)

    ids = set()
    manifest_path = person_dir / "normalized" / MANIFEST
    if manifest_path.exists():
        guard.assert_not_raw(manifest_path)
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        obj = json.loads(line)
                        if isinstance(obj, dict) and isinstance(obj.get("record_id"), str):
                            ids.add(obj["record_id"])
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            exit_error(f"error: cannot read manifest: {e}")

    if args.ids_file:
        ids |= load_ids_file(args.ids_file, guard)

    if not ids:
        exit_error("error: no ids to verify (manifest and --ids-file both empty/missing)")

    files = collect_verify_files(person_dir, guard)

    residue = []  # list of (file, id, count)
    for fpath in files:
        guard.assert_not_raw(fpath)
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            exit_error(f"error: cannot read {fpath}: {e}")
        for rid in ids:
            count = content.count(rid)
            if count > 0:
                residue.append((fpath, rid, count))

    safe_print_ascii(f"verify ids={len(ids)} files={len(files)} residue={len(residue)}")
    if residue:
        for fpath, rid, count in sorted(residue):
            safe_print_ascii(
                f"{rel_posix(fpath)} {rid[:12]} x{count}"
            )
        return 2
    return 0


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Scrub sensitive records from derived layers")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # scan
    p_scan = subparsers.add_parser("scan")
    p_scan.add_argument("--person", required=True)
    p_scan.add_argument("--patterns")
    p_scan.add_argument("--out-dir")
    p_scan.set_defaults(func=cmd_scan)

    # apply
    p_apply = subparsers.add_parser("apply")
    p_apply.add_argument("--person", required=True)
    p_apply.add_argument("--ids-file", required=True)
    p_apply.add_argument("--reason", required=True)
    p_apply.add_argument("--dry-run", action="store_true")
    p_apply.add_argument("--allow-missing", action="store_true")
    p_apply.set_defaults(func=cmd_apply)

    # verify
    p_verify = subparsers.add_parser("verify")
    p_verify.add_argument("--person", required=True)
    p_verify.add_argument("--ids-file")
    p_verify.set_defaults(func=cmd_verify)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        # Unexpected exception: let it traceback (exit code 1)
        raise
