#!/usr/bin/env python3
"""Render a human-readable Chinese markdown timeline from timeline.json."""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
BAR_FULL = "█"
BAR_EMPTY = "░"
BAR_LENGTH = 10


def ascii_safe(s):
    """Convert to ASCII-safe string."""
    return str(s).encode("ascii", "backslashreplace").decode("ascii")


def fail(msg):
    """Print one-line ASCII error and exit 2."""
    print(f"ERROR: {ascii_safe(msg)}", file=sys.stderr)
    sys.exit(2)


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Render timeline markdown.")
    parser.add_argument("--person", required=True, help="Person slug")
    parser.add_argument("--timeline", help="Path to timeline.json")
    parser.add_argument("--out", help="Output markdown path")
    args = parser.parse_args(argv)
    return args


def parse_month(month_str):
    """Return (year, month) ints from 'YYYY-MM'."""
    try:
        year, month = month_str.split("-", 1)
        return int(year), int(month)
    except (ValueError, AttributeError):
        return None


def month_to_str(year, month):
    return f"{year:04d}-{month:02d}"


def is_under(path, base):
    """Check if path is under base directory."""
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def load_timeline(path):
    """Load and validate timeline.json. Returns (meta, months) or exits 2."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        fail(f"timeline file not found: {path}")
    except json.JSONDecodeError as e:
        fail(f"invalid JSON in timeline: {e}")
    except OSError as e:
        fail(f"cannot read timeline: {e}")

    if not isinstance(data, dict):
        fail("timeline top-level is not an object")
    if "months" not in data or not isinstance(data["months"], list):
        fail("timeline missing 'months' array")

    months = data["months"]
    parsed = []
    for item in months:
        if not isinstance(item, dict) or "month" not in item:
            fail("timeline month entry missing 'month'")
        ym = parse_month(item["month"])
        if ym is None:
            fail(f"invalid month string: {item['month']}")
        msgs = item.get("messages_total", 0)
        subj = item.get("messages_from_subject", 0)
        voice = item.get("voice_count", 0)
        video = item.get("video_count", 0)
        try:
            parsed.append({
                "year": ym[0],
                "month": ym[1],
                "month_str": item["month"],
                "messages_total": int(msgs),
                "messages_from_subject": int(subj),
                "voice_count": int(voice),
                "video_count": int(video),
            })
        except (TypeError, ValueError):
            fail(f"invalid numeric value in month {item['month']}")

    if not parsed:
        fail("timeline has no months")
    return data, parsed


def compute_gaps(months):
    """Find gaps of >=2 missing consecutive months. Returns list of (gap_start, gap_len)."""
    months_sorted = sorted(months, key=lambda m: (m["year"], m["month"]))
    if len(months_sorted) < 2:
        return []

    present = set((m["year"], m["month"]) for m in months_sorted)
    first_ym = (months_sorted[0]["year"], months_sorted[0]["month"])
    last_ym = ((months_sorted[-1]["year"], months_sorted[-1]["month"]))

    gaps = []
    # Move through calendar months from first to last
    y, m = first_ym
    while (y, m) < last_ym:
        # Next calendar month
        if m == 12:
            ny, nm = y + 1, 1
        else:
            ny, nm = y, m + 1
        if (ny, nm) not in present:
            # Count how long the gap is
            gap_y, gap_m = ny, nm
            gap_len = 0
            while (gap_y, gap_m) not in present and (gap_y, gap_m) <= last_ym:
                gap_len += 1
                if gap_m == 12:
                    gap_y, gap_m = gap_y + 1, 1
                else:
                    gap_y, gap_m = gap_y, gap_m + 1
            if gap_len >= 2:
                gaps.append((month_to_str(ny, nm), gap_len))
            # Skip ahead past the gap
            y, m = gap_y, gap_m
        else:
            y, m = ny, nm
    return gaps


def build_document(meta, months, slug):
    """Build the markdown string."""

    # Sort months chronologically
    months_sorted = sorted(months, key=lambda m: (m["year"], m["month"]))
    if not months_sorted:
        fail("no months to render")

    n_months = len(months_sorted)

    total_msgs = sum(m["messages_total"] for m in months_sorted)
    total_subj = sum(m["messages_from_subject"] for m in months_sorted)
    total_voice = sum(m["voice_count"] for m in months_sorted)
    total_video = sum(m["video_count"] for m in months_sorted)

    max_msgs = max(m["messages_total"] for m in months_sorted)

    derived_from = str(meta.get("derived_from", "未知来源"))
    generated_at_raw = meta.get("generated_at", "")
    try:
        gen_dt = datetime.fromisoformat(generated_at_raw.replace("Z", "+00:00"))
        gen_local = gen_dt.astimezone().strftime("%Y-%m-%dT%H:%M:%S")
    except (ValueError, AttributeError):
        gen_local = datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S")

    # Group by year
    years = {}
    for m in months_sorted:
        years.setdefault(m["year"], []).append(m)

    # Compute gaps - gap_start = first missing month
    gaps = compute_gaps(months_sorted)
    # Group gap notes by the year in which the gap starts
    gaps_by_year = {}
    for gap_start, n in gaps:
        ym = parse_month(gap_start)
        if ym is None:
            continue
        gaps_by_year.setdefault(ym[0], []).append((gap_start, n))

    # Header
    first_str = months_sorted[0]["month_str"]
    last_str = months_sorted[-1]["month_str"]

    lines = []
    lines.append(f"# 时间线 · {slug}")
    lines.append("")
    lines.append(f"> Tier-2 · 由消息与媒体清单自动统计生成（{derived_from}），未经人工确认。")
    lines.append(f"> 数据范围 {first_str} 至 {last_str} · 共 {n_months} 个月 · 消息 {total_msgs} 条（本人 {total_subj} 条）· 语音 {total_voice} 条 · 视频 {total_video} 条")
    lines.append(f"> 生成时间 {gen_local}")
    lines.append("")

    # Group by year sorted
    sorted_years = sorted(years.keys())
    for year in sorted_years:
        year_months = sorted(years[year], key=lambda m: m["month"])
        y_msgs = sum(m["messages_total"] for m in year_months)
        y_subj = sum(m["messages_from_subject"] for m in year_months)
        y_voice = sum(m["voice_count"] for m in year_months)
        y_video = sum(m["video_count"] for m in year_months)

        heading = f"## {year} 年（消息 {y_msgs} · 本人 {y_subj} · 语音 {y_voice}"
        if y_video > 0:
            heading += f" · 视频 {y_video}"
        heading += "）"
        lines.append(heading)
        lines.append("")
        lines.append("| 月份 | 消息 | 本人 | 语音 | 视频 | 活跃 |")
        lines.append("|---|---|---|---|---|---|")

        for m in year_months:
            bar_len = 0
            if m["messages_total"] > 0:
                if max_msgs > 0:
                    bar_len = max(1, round(10 * m["messages_total"] / max_msgs))
                else:
                    bar_len = 0
                bar_len = min(bar_len, 10)
            bar = BAR_FULL * bar_len + BAR_EMPTY * (BAR_LENGTH - bar_len)
            lines.append(
                f"| {m['month']} 月 | {m['messages_total']} | {m['messages_from_subject']} | {m['voice_count']} | {m['video_count']} | {bar} |"
            )

        # Append gap notes that start in this year
        for gap_start, n in sorted(gaps_by_year.get(year, [])):
            lines.append("")
            lines.append(f">（{gap_start} 起连续 {n} 个月无记录）")

        lines.append("")

    # Attach gap notes for years with no table (fully missing years) after preceding year
    for year in sorted(gaps_by_year.keys()):
        if year not in years:
            # Find preceding year that exists
            prev_year = None
            for py in sorted(years.keys()):
                if py < year:
                    prev_year = py
                else:
                    break
            if prev_year is not None:
                # Find the position after that year's table (last line before next year or footer)
                # Rebuild: easier to insert by finding the heading position
                target = f"## {prev_year} 年"
                for i, line in enumerate(lines):
                    if line.startswith(target):
                        # Find end of that year's block (next heading or footer marker)
                        insert_idx = len(lines)
                        for j in range(i + 1, len(lines)):
                            if lines[j].startswith("## ") or lines[j].startswith("---"):
                                insert_idx = j
                                break
                        # Insert gap notes before the blank line at end of block
                        while insert_idx > 0 and lines[insert_idx - 1] == "":
                            insert_idx -= 1
                        for gap_start, n in sorted(gaps_by_year[year]):
                            lines.insert(insert_idx, f">（{gap_start} 起连续 {n} 个月无记录）")
                            insert_idx += 1
                            lines.insert(insert_idx, "")
                            insert_idx += 1
                        break

    # Footer
    lines.append("---")
    lines.append("*本页由 render_timeline.py 生成，数据源 archive_out/data/timeline.json，重跑即可刷新。*")
    lines.append("")

    return "\n".join(lines)


def main(argv=None):
    args = parse_args(argv)
    slug = args.person

    if not SLUG_RE.match(slug):
        fail(f"invalid slug: {slug}")

    # Resolve default paths
    if args.timeline:
        timeline_path = Path(args.timeline)
    else:
        timeline_path = REPO_ROOT / "people" / slug / "archive_out" / "data" / "timeline.json"

    if args.out:
        out_path = Path(args.out)
    else:
        out_path = REPO_ROOT / "people" / slug / "memories" / "timeline.md"

    # raw/ guard
    raw_dir = REPO_ROOT / "people" / slug / "raw"
    if is_under(timeline_path, raw_dir) or is_under(out_path, raw_dir):
        fail("paths under people/<slug>/raw/ are not allowed")

    # Load data
    meta, months = load_timeline(timeline_path)

    # Build document
    doc = build_document(meta, months, slug)

    # Write out
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(doc)
    except OSError as e:
        fail(f"cannot write output: {e}")

    # ASCII summary on stdout - make path repo-relative if possible
    try:
        rel_out = out_path.resolve().relative_to(REPO_ROOT.resolve())
        out_display = rel_out.as_posix()
    except ValueError:
        out_display = out_path.resolve().as_posix()

    years = sorted(set(m["year"] for m in months))
    print(ascii_safe(f"months={len(months)} years={len(years)} out={out_display}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
