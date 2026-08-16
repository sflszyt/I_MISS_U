#!/usr/bin/env python3
"""Build chat context JSON for a person's BYOK chat page."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
PLACEHOLDER_RE = re.compile(r"\{\{([a-zA-Z0-9_]+)\}\}")

RELATION_MAP = {
    "mother": "母亲",
    "father": "父亲",
    "child": "孩子",
    "son": "儿子",
    "daughter": "女儿",
    "spouse": "伴侣",
    "wife": "妻子",
    "husband": "丈夫",
    "friend": "朋友",
    "grandmother": "祖母",
    "grandfather": "祖父",
    "sibling": "手足",
}


def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build chat context JSON")
    parser.add_argument("--person", required=True, help="Person slug")
    parser.add_argument("--template", help="Template path (default: prompts/chat_system.zh.md)")
    parser.add_argument("--out", help="Output path (default: people/<slug>/archive_out/data/chat_context.json)")
    parser.add_argument("--max-persona-kb", type=int, default=40, help="Max persona size in KB")
    parser.add_argument("--memories-mode", choices=["index", "full"], default="index", help="记忆块模式：index=只嵌日期+标题索引（默认），full=嵌入全文（旧行为）")
    return parser.parse_args()


def load_json(path: Path, required: bool = False) -> dict[str, Any] | None:
    if not path.exists():
        if required:
            fail(f"Required file missing: {path}")
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            if required:
                fail(f"Invalid JSON object in {path}")
            return None
        return data
    except (json.JSONDecodeError, OSError) as e:
        if required:
            fail(f"Cannot read {path}: {e}")
        return None


def load_text(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def get_relation_zh(relation_value: str, override: str | None) -> str:
    if override:
        return override
    if relation_value in RELATION_MAP:
        return RELATION_MAP[relation_value]
    return relation_value


def build_languages_note(lang: dict[str, Any]) -> str:
    primary = str(lang.get("primary", "")).strip()
    secondary = str(lang.get("secondary", "")).strip()
    notes = str(lang.get("notes", "")).strip()

    parts: list[str] = []
    if primary and secondary:
        parts.append(f"主 {primary}，辅 {secondary}")
    elif primary:
        parts.append(f"主 {primary}")
    elif secondary:
        parts.append(f"辅 {secondary}")
    if notes:
        parts.append(notes)
    return "；".join(p for p in parts if p)


def format_catchphrases(entries: Any) -> list[str]:
    """Format catchphrase entries, whether dict {'phrase':…,'count':…} or [phrase, count]."""
    out: list[str] = []
    for entry in entries[:15]:
        try:
            if isinstance(entry, dict):
                phrase = str(entry.get("phrase", "")).strip()
                count = entry.get("count")
            elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
                phrase = str(entry[0]).strip()
                count = entry[1]
            else:
                continue
            if not phrase:
                continue
            if count is not None:
                out.append(f"「{phrase}」({count})")
            else:
                out.append(f"「{phrase}」")
        except Exception:
            continue
    return out


def build_rhythm_block(rhythm: dict[str, Any] | None) -> str:
    if rhythm is None:
        return "（暂无节律统计）"

    lines: list[str] = []

    text_stats = rhythm.get("text_stats")
    if isinstance(text_stats, dict):
        total = text_stats.get("messages_total")
        avg = text_stats.get("avg_length")
        median = text_stats.get("median_length")
        if total is not None:
            lines.append(f"消息总量 {total} 条")
        if avg is not None:
            lines.append(f"平均长度约 {avg} 字")
        if median is not None:
            lines.append(f"中位长度约 {median} 字")

    time_pattern = rhythm.get("time_pattern")
    if isinstance(time_pattern, dict):
        peak_hours = time_pattern.get("peak_hours")
        active_periods = time_pattern.get("active_periods")
        if isinstance(peak_hours, (list, tuple)) and len(peak_hours) > 0:
            top2 = [str(h) for h in peak_hours[:2]]
            lines.append(f"活跃高峰时段：{', '.join(top2)}")
        elif isinstance(active_periods, (list, tuple)) and len(active_periods) > 0:
            top2 = [str(p) for p in active_periods[:2]]
            lines.append(f"活跃时段：{', '.join(top2)}")

    burst = rhythm.get("burst")
    if isinstance(burst, dict):
        note = burst.get("overall") or burst.get("note") or burst.get("summary")
        if note:
            lines.append(f"连发习惯：{note}")
    elif isinstance(burst, str) and burst.strip():
        lines.append(f"连发习惯：{burst.strip()}")

    punct = rhythm.get("punctuation_habits")
    if isinstance(punct, dict):
        notable = punct.get("notable") or punct.get("significant") or punct.get("overall")
        if notable:
            lines.append(f"标点习惯：{notable}")
    elif isinstance(punct, str) and punct.strip():
        lines.append(f"标点习惯：{punct.strip()}")

    catchphrases = rhythm.get("catchphrases")
    if isinstance(catchphrases, list) and len(catchphrases) > 0:
        formatted = format_catchphrases(catchphrases)
        if formatted:
            lines.append("口头禅：" + "，".join(formatted))

    emoji = rhythm.get("emoji_usage")
    if isinstance(emoji, dict):
        note = emoji.get("summary") or emoji.get("overall") or emoji.get("habit")
        top = emoji.get("top")
        if note:
            lines.append(f"Emoji/颜文字习惯：{note}")
        elif isinstance(top, (list, tuple)) and len(top) > 0:
            top_str = ", ".join(str(t) for t in top[:5])
            lines.append(f"常用 Emoji/颜文字：{top_str}")
    elif isinstance(emoji, str) and emoji.strip():
        lines.append(f"Emoji/颜文字习惯：{emoji.strip()}")

    voice = rhythm.get("voice_habit")
    if isinstance(voice, dict):
        note = voice.get("summary") or voice.get("overall") or voice.get("habit")
        if note:
            lines.append(f"语音使用习惯：{note}")
    elif isinstance(voice, str) and voice.strip():
        lines.append(f"语音使用习惯：{voice.strip()}")

    if not lines:
        return "（暂无节律统计）"
    return "\n".join(lines)


def truncate_persona(text: str, max_kb: int) -> tuple[str, bool]:
    """Truncate at last full line under limit. Returns (text, truncated)."""
    limit = max_kb * 1024
    data = text.encode("utf-8")
    if len(data) <= limit:
        return text, False

    # Find last full line whose end position (including its newline) is under limit
    lines = text.splitlines(keepends=True)
    current = ""
    current_bytes = 0
    for line in lines:
        line_bytes = len(line.encode("utf-8"))
        if current_bytes + line_bytes > limit:
            break
        current += line
        current_bytes += line_bytes

    if not current:
        # Cannot fit even one line; truncate at byte boundary safely
        truncated_bytes = data[:limit]
        current = truncated_bytes.decode("utf-8", errors="ignore").rstrip("\n")
    else:
        current = current.rstrip("\n")

    return current + "\n\n（persona 全文超长，此处截断；完整版见档案 persona.md）", True


def build_timeline_block(timeline: dict[str, Any] | None) -> str:
    if timeline is None:
        return "（暂无时间线）"

    months = timeline.get("months")
    if not isinstance(months, list) or len(months) == 0:
        return "（暂无时间线）"

    valid_months = [m for m in months if isinstance(m, dict) and "month" in m]
    if not valid_months:
        return "（暂无时间线）"

    total_messages = 0
    total_subject = 0
    years: dict[str, dict[str, int]] = {}

    for m in valid_months:
        month_str = str(m.get("month", ""))
        total = int(m.get("messages_total", 0) or 0)
        subject = int(m.get("messages_from_subject", 0) or 0)
        total_messages += total
        total_subject += subject
        year = month_str[:4]
        if year:
            y = years.setdefault(year, {"total": 0, "subject": 0})
            y["total"] += total
            y["subject"] += subject

    first = valid_months[0].get("month", "?")
    last = valid_months[-1].get("month", "?")
    n = len(valid_months)

    lines = [f"数据范围 {first} 至 {last}，共 {n} 个月，消息 {total_messages} 条（本人 {total_subject} 条）"]
    for year in sorted(years.keys()):
        y = years[year]
        lines.append(f"{year} 年：消息 {y['total']} · 本人 {y['subject']}")

    return "\n".join(lines)


def build_memories_index(memories_md: str) -> str:
    """Build a compact index of memory titles from the memories markdown."""
    headings: list[str] = []
    for line in memories_md.splitlines():
        if line.startswith("## "):
            title = line[len("## "):].strip()
            if title:
                headings.append(title)

    if not headings:
        return memories_md

    lines: list[str] = [
        f"以下为家人确认的记忆索引（Tier-1，共 {len(headings)} 条）。记忆全文不在本提示词内：对话页会把与当前话题相关的记忆片段作为检索结果附在用户消息里（标注「家人确认记忆 Tier-1」）。索引之外或未检索到的记忆，不得凭空展开细节，只能说记不清了。",
        "",
    ]
    for h in headings:
        lines.append(f"- {h}")
    return "\n".join(lines)


def main() -> None:
    args = parse_args()

    person = args.person
    if not SLUG_RE.match(person):
        fail(f"Invalid person slug: {person}")

    repo_root = Path(__file__).resolve().parent.parent
    person_dir = repo_root / "people" / person
    protected_dir = person_dir / "raw"

    def check_path(p: Path, label: str) -> None:
        try:
            resolved = p.resolve()
            raw_resolved = protected_dir.resolve()
            if raw_resolved in resolved.parents or resolved == raw_resolved:
                fail(f"{label} path resolves under raw/: {p}")
        except OSError:
            fail(f"Cannot resolve {label} path: {p}")

    template_path = Path(args.template) if args.template else repo_root / "prompts" / "chat_system.zh.md"
    if not template_path.is_absolute():
        template_path = repo_root / template_path
    check_path(template_path, "template")

    out_path = Path(args.out) if args.out else person_dir / "archive_out" / "data" / "chat_context.json"
    if not out_path.is_absolute():
        out_path = repo_root / out_path
    check_path(out_path, "output")

    # Guard every input path against resolving under raw/
    relationship_path = person_dir / "persona" / "relationship.json"
    persona_path = person_dir / "persona" / "persona.md"
    rhythm_path = person_dir / "persona" / "rhythm.json"
    memories_path = person_dir / "memories" / "memories.md"
    timeline_path = person_dir / "archive_out" / "data" / "timeline.json"
    check_path(relationship_path, "relationship")
    check_path(persona_path, "persona")
    check_path(rhythm_path, "rhythm")
    check_path(memories_path, "memories")
    check_path(timeline_path, "timeline")

    # Load inputs
    relationship = load_json(relationship_path, required=True)
    if relationship is None:
        fail("relationship.json missing or invalid")

    persona_md = load_text(persona_path)
    rhythm = load_json(rhythm_path)
    memories_md = load_text(memories_path)
    timeline = load_json(timeline_path)

    # Render template
    try:
        template = template_path.read_text(encoding="utf-8")
    except OSError as e:
        fail(f"Cannot read template {template_path}: {e}")

    display_name = str(relationship.get("display_name", "")).strip()
    if not display_name:
        fail("relationship.json missing display_name")

    languages = relationship.get("languages")
    if not isinstance(languages, dict):
        languages = {}
    languages_note = build_languages_note(languages) or "（语言信息缺失）"

    rel = relationship.get("relationship")
    if not isinstance(rel, dict):
        fail("relationship.json missing relationship")
    subject_to_viewpoint = str(rel.get("subject_to_viewpoint", "")).strip() or "未知"
    viewpoint_to_subject = str(rel.get("viewpoint_to_subject", "")).strip() or "未知"

    subject_relation_zh = get_relation_zh(
        subject_to_viewpoint,
        str(relationship.get("subject_relation_zh", "")).strip() or None,
    )
    viewpoint_relation_zh = get_relation_zh(
        viewpoint_to_subject,
        str(relationship.get("viewpoint_relation_zh", "")).strip() or None,
    )

    # Persona
    persona_truncated = False
    if persona_md is None:
        persona_block = "（persona 档案尚未生成——不得陈述任何性格或事实描述为档案内容）"
    else:
        persona_block, persona_truncated = truncate_persona(persona_md, args.max_persona_kb)

    rhythm_block = build_rhythm_block(rhythm)
    if memories_md is None:
        memories_block = "（暂无家人确认的记忆——不得把任何具体事件说成\"家人确认过\"）"
    elif args.memories_mode == "index":
        memories_block = build_memories_index(memories_md)
    else:
        memories_block = memories_md
    timeline_block = build_timeline_block(timeline)

    replacements = {
        "display_name": display_name,
        "subject_relation_zh": subject_relation_zh,
        "viewpoint_relation_zh": viewpoint_relation_zh,
        "languages_note": languages_note,
        "persona_block": persona_block,
        "rhythm_block": rhythm_block,
        "memories_block": memories_block,
        "timeline_block": timeline_block,
    }

    rendered = template
    for key, value in replacements.items():
        rendered = rendered.replace("{{" + key + "}}", value)

    # Check for unknown placeholders
    remaining = PLACEHOLDER_RE.findall(rendered)
    if remaining:
        unknown = sorted(set(remaining))
        fail(f"Unknown template placeholders: {', '.join(unknown)}")

    if "{{" in rendered:
        fail("Render left {{ in output")

    # Sources
    sources = {
        "relationship": True,
        "persona": persona_md is not None,
        "rhythm": rhythm is not None,
        "memories": memories_md is not None,
        "memories_mode": args.memories_mode,
        "timeline": timeline is not None,
    }

    # Message shards
    shards: list[str] = []
    shard_dir = person_dir / "archive_out" / "data"
    if shard_dir.is_dir():
        shards = sorted(
            p.name for p in shard_dir.glob("messages_*.json") if p.is_file()
        )

    output = {
        "schema_version": 1,
        "person": person,
        "display_name": display_name,
        "system_prompt": rendered,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "sources": sources,
        "persona_truncated": persona_truncated,
        "message_shards": shards,
    }

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
            f.write("\n")
    except OSError as e:
        fail(f"Cannot write output {out_path}: {e}")

    source_list = ",".join(k for k, v in sources.items() if v is True)
    print(f"context={out_path.relative_to(repo_root)} prompt_chars={len(rendered)} memories_mode={args.memories_mode} sources={source_list}")


if __name__ == "__main__":
    main()
