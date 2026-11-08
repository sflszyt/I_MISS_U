#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解析 chatlog-keeper 导出的微信全量消息 JSON 为 UIF JSONL。

工具 #13：I_MISS_U 数字档案项目微信解析器。

铁律：
- raw/ 目录只读，本工具绝不向 raw/ 写入任何字节。
- 所有输出必须位于 people/<person>/normalized/ 目录内。
- 群聊中他人发言必须可清晰区分，绝不与档案对象本人的话混淆。
- sender_wxid 只能来自原始 sender_wxid 字段，绝不用 sender 显示名字段顶替。
- 控制台输出只用 ASCII，中文只写入输出文件。
"""

from __future__ import annotations

try:
    from .local_identity import owner_participant
except ImportError:
    from local_identity import owner_participant


import argparse
import hashlib
import json
import math
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

PARSER_VERSION = "1.0.0"
TZ = timezone(timedelta(hours=8))
DURATION_RE = re.compile(r"\[(?:语音|视频)\s*(\d+(?:\.\d+)?)s\]")
KNOWN_MSG_TYPES = {1, 3, 34, 43, 47, 48, 49, 42, 50, 10000}


@dataclass
class RoomStat:
    label: str
    total: int = 0
    subject_count: int = 0
    first_ts: Optional[datetime] = None
    last_ts: Optional[datetime] = None


def _ascii(s: str) -> str:
    """Force a string to ASCII for console output."""
    return s.encode("ascii", "backslashreplace").decode("ascii")


def _load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _to_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isfinite(value) and value.is_integer():
            return int(value)
        return None
    if isinstance(value, str):
        s = value.strip()
        try:
            return int(s)
        except ValueError:
            try:
                f = float(s)
                if math.isfinite(f) and f.is_integer():
                    return int(f)
            except ValueError:
                return None
    return None


def _parse_ts(value: Any) -> Tuple[Optional[float], str, bool]:
    if isinstance(value, bool):
        return None, str(value), False
    if isinstance(value, (int, float)):
        v = float(value)
        if math.isnan(v) or math.isinf(v):
            return None, str(value), False
        return v, str(value), True
    if isinstance(value, str):
        s = value.strip()
        try:
            v = float(s)
        except ValueError:
            return None, s, False
        if math.isnan(v) or math.isinf(v):
            return None, s, False
        return v, s, True
    return None, "" if value is None else str(value), False


def _format_timestamp(ts: float) -> str:
    dt = datetime.fromtimestamp(ts, TZ)
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + "+08:00"


def _content_type(msg_type: int) -> str:
    if msg_type == 1:
        return "text"
    if msg_type == 3:
        return "image"
    if msg_type == 34:
        return "voice"
    if msg_type == 43:
        return "video"
    if msg_type == 47:
        return "sticker"
    if msg_type == 48:
        return "location"
    if msg_type in (49, 42):
        return "link"
    if msg_type in (50, 10000):
        return "system"
    return "system"


def _unique_record_id(base_input: str, seen: Set[str]) -> str:
    candidate = hashlib.sha256(base_input.encode("utf-8")).hexdigest()
    if candidate not in seen:
        seen.add(candidate)
        return candidate
    counter = 1
    while True:
        candidate = hashlib.sha256(
            f"{base_input}:{counter}".encode("utf-8")
        ).hexdigest()
        if candidate not in seen:
            seen.add(candidate)
            return candidate
        counter += 1


def _build_record(
    msg: Any,
    *,
    person: str,
    cfg: Dict[str, Any],
    source_file: str,
    extracted_at: str,
    seen: Set[str],
    known_participants: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], int]:
    """Build a UIF message record. Returns (record, warning_count)."""
    warnings = 0

    if not isinstance(msg, dict):
        return None, 1

    chat_room = msg.get("chat_room")
    if not isinstance(chat_room, str) or chat_room == "":
        return None, 1

    room_info = cfg["rooms"].get(chat_room)
    if room_info is None:
        return None, 0
    room_label = room_info.get("label", "") if isinstance(room_info, dict) else ""

    # 铁律：sender_wxid 只能来自原始 sender_wxid 字段，缺失或非字符串即跳过。
    sender_wxid = msg.get("sender_wxid")
    if not isinstance(sender_wxid, str) or sender_wxid == "":
        return None, 1

    content = msg.get("content", "")
    if content is None:
        content = ""
    if not isinstance(content, str):
        content = str(content)
        warnings += 1

    msg_type = _to_int(msg.get("msg_type"))
    if msg_type is None:
        return None, 1

    is_self = msg.get("is_self")
    if isinstance(is_self, bool):
        pass
    elif isinstance(is_self, (int, float)) and not isinstance(is_self, bool):
        is_self = bool(is_self)
        warnings += 1
    elif isinstance(is_self, str):
        s = is_self.strip().lower()
        if s in ("true", "1"):
            is_self = True
        elif s in ("false", "0"):
            is_self = False
        else:
            is_self = False
            warnings += 1
    else:
        is_self = False
        warnings += 1

    ts, ts_raw, ts_ok = _parse_ts(msg.get("ts"))
    if not ts_ok:
        warnings += 1

    timestamp: Optional[str] = None
    timestamp_precision = "unknown"
    if ts_ok:
        try:
            timestamp = _format_timestamp(ts)
            timestamp_precision = "exact"
        except (OverflowError, OSError, ValueError):
            # 极大/极小/Windows 不支持的时间戳：降级，不中断整体运行。
            warnings += 1
            timestamp = None
            timestamp_precision = "unknown"

    if sender_wxid == cfg["subject_wxid"]:
        sender = "subject"
    elif sender_wxid == cfg["viewpoint_owner_wxid"]:
        sender = "viewpoint_owner"
    else:
        sender = sender_wxid

    ctype = _content_type(msg_type)

    duration_ms = None
    if msg_type in (34, 43):
        m = DURATION_RE.search(content)
        if m:
            seconds = float(m.group(1))
            duration_ms = int(round(seconds * 1000))

    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    base_input = f"wechat:{chat_room}:{ts_raw}:{sender_wxid}:{content_hash}"
    viewpoint = cfg.get("viewpoint", owner_participant())
    if viewpoint != owner_participant() or cfg.get("source_account_id"):
        base_input = f"{cfg.get('source_account_id', viewpoint)}:{base_input}"
    record_id = _unique_record_id(base_input, seen)

    record: Dict[str, Any] = {
        "record_id": record_id,
        "record_type": "message",
        "person": person,
        "viewpoint": viewpoint,
        "source": "wechat",
        "timestamp": timestamp,
        "timestamp_precision": timestamp_precision,
        "tier": 2,
        "lang": "zh",
        "provenance": {
            "source_file": source_file,
            "parser": "parse_wechat",
            "parser_version": PARSER_VERSION,
            "extracted_at": extracted_at,
        },
        "conversation_id": chat_room,
        "sender": sender,
        "content_type": ctype,
    }

    if content:
        record["text"] = content
    if duration_ms is not None:
        record["duration_ms"] = duration_ms

    record["chat_room"] = chat_room
    record["room_label"] = room_label
    record["sender_wxid"] = sender_wxid

    alias = known_participants.get(sender_wxid)
    if alias:
        record["sender_alias"] = str(alias)

    record["msg_type_native"] = msg_type
    record["is_self"] = is_self

    if ctype == "system" and msg_type not in KNOWN_MSG_TYPES:
        record["notes"] = f"unknown msg_type {msg_type}"

    return record, warnings


def _md_escape(value: Any) -> str:
    return str(value).replace("|", "\\|")


def _write_report(
    path: Path,
    *,
    source_file: str,
    extracted_at: str,
    total_msgs: int,
    in_scope_count: int,
    out_of_scope: int,
    failed_in_scope: int,
    parsed_count: int,
    skipped_rooms: Set[str],
    warnings: int,
    room_stats: Dict[str, RoomStat],
    content_type_all: Counter,
    content_type_subject: Counter,
    unknown_msg_types: Counter,
) -> None:
    lines: List[str] = []
    lines.append("# 微信解析报告")
    lines.append("")
    lines.append(f"- 生成时间: {extracted_at}")
    lines.append(f"- parser 版本: {PARSER_VERSION}")
    lines.append(f"- 输入文件: `{source_file}`")
    lines.append(f"- 总消息数: {total_msgs}")
    lines.append(f"- 进入解析范围的消息数: {in_scope_count}")
    lines.append(f"- 范围外消息数: {out_of_scope}")
    lines.append(f"- 解析失败消息数（进入范围但被丢弃）: {failed_in_scope}")
    lines.append(f"- 成功输出消息数: {parsed_count}")
    lines.append(
        f"- 恒等式: total_msgs = out_of_scope + failed_in_scope + parsed_count "
        f"({total_msgs} = {out_of_scope} + {failed_in_scope} + {parsed_count})"
    )
    lines.append(f"- 跳过的会话数: {len(skipped_rooms)}")
    lines.append(f"- 警告数（附加告警，与消息数解耦）: {warnings}")
    lines.append("")

    lines.append("## 按会话统计")
    lines.append("")
    lines.append("| 会话 | label | 总条数 | subject 条数 | 时间范围 |")
    lines.append("|---|---|---|---|---|")
    for chat_room, st in room_stats.items():
        if st.first_ts is not None and st.last_ts is not None:
            time_range = (
                f"{st.first_ts.date().isoformat()} ~ {st.last_ts.date().isoformat()}"
            )
        else:
            time_range = "N/A"
        lines.append(
            f"| `{_md_escape(chat_room)}` | {_md_escape(st.label)} | "
            f"{st.total} | {st.subject_count} | {time_range} |"
        )
    lines.append("")

    lines.append("## 按 content_type 统计")
    lines.append("")
    lines.append("| content_type | 全部 | 仅 subject |")
    lines.append("|---|---|---|")
    sorted_types = sorted(content_type_all.items(), key=lambda kv: (-kv[1], kv[0]))
    for ct, count in sorted_types:
        lines.append(f"| {ct} | {count} | {content_type_subject.get(ct, 0)} |")
    lines.append("")

    lines.append("## subject 全部文字消息总数")
    lines.append("")
    lines.append(str(content_type_subject.get("text", 0)))
    lines.append("")

    lines.append("## 未知 msg_type")
    lines.append("")
    if not unknown_msg_types:
        lines.append("无")
    else:
        for msg_type in sorted(unknown_msg_types):
            lines.append(f"- msg_type {msg_type}: {unknown_msg_types[msg_type]}")
    lines.append("")

    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))


def _run(args: argparse.Namespace) -> int:
    person = args.person
    if re.fullmatch(r"[a-z0-9_-]+", person) is None:
        print(
            "error: invalid person slug (must match ^[a-z0-9_-]+$)",
            file=sys.stderr,
        )
        return 1

    repo_root = (
        Path(args.repo_root).resolve()
        if args.repo_root
        else Path(__file__).resolve().parent.parent
    )
    resolved_repo = repo_root.resolve()
    person_dir_resolved = (repo_root / "people" / person).resolve()
    out_dir = (repo_root / "people" / person / "normalized").resolve()

    # 路径锚定防符号链接绕过：以 repo_root.resolve() 为锚。
    try:
        rel_to_repo = out_dir.relative_to(resolved_repo)
    except ValueError:
        print(
            "error: output directory resolves outside repository root",
            file=sys.stderr,
        )
        return 1

    if len(rel_to_repo.parts) < 3 or rel_to_repo.parts[:3] != (
        "people",
        person,
        "normalized",
    ):
        print(
            "error: output directory must resolve to people/<person>/normalized",
            file=sys.stderr,
        )
        return 1

    if "raw" in rel_to_repo.parts:
        print(
            "error: resolved output path must not contain 'raw'",
            file=sys.stderr,
        )
        return 1

    input_path = (
        Path(args.input).resolve()
        if args.input
        else (
            repo_root
            / "people"
            / person
            / "raw"
            / "wechat"
            / "export_full"
            / "wechat_messages.json"
        ).resolve()
    )
    config_path = (
        Path(args.config).resolve()
        if args.config
        else (repo_root / "people" / person / "wechat_parse_config.json").resolve()
    )

    if not input_path.is_file():
        print(
            f"error: input file not found: {_ascii(str(input_path))}",
            file=sys.stderr,
        )
        return 1
    if not config_path.is_file():
        print(
            f"error: config file not found: {_ascii(str(config_path))}",
            file=sys.stderr,
        )
        return 1

    try:
        messages = _load_json(input_path)
    except Exception as exc:
        print(
            f"error: failed to parse input JSON from {_ascii(str(input_path))}: {_ascii(str(exc))}",
            file=sys.stderr,
        )
        return 1

    if not isinstance(messages, list):
        print("error: input JSON must be an array of messages", file=sys.stderr)
        return 1

    try:
        cfg = _load_json(config_path)
    except Exception as exc:
        print(
            f"error: failed to parse config JSON from {_ascii(str(config_path))}: {_ascii(str(exc))}",
            file=sys.stderr,
        )
        return 1

    if not isinstance(cfg, dict):
        print("error: config JSON must be an object", file=sys.stderr)
        return 1

    missing = [k for k in ("subject_wxid", "viewpoint_owner_wxid", "rooms") if k not in cfg]
    if missing:
        print(
            "error: config missing required field(s): " + ", ".join(missing),
            file=sys.stderr,
        )
        return 1

    subject_wxid = cfg["subject_wxid"]
    viewpoint_owner_wxid = cfg["viewpoint_owner_wxid"]
    rooms = cfg["rooms"]
    known_participants = cfg.get("known_participants", {})

    if not isinstance(cfg.get("viewpoint", owner_participant()), str) or re.fullmatch(r"[a-z0-9_-]+", cfg.get("viewpoint", owner_participant())) is None:
        print("error: invalid viewpoint slug", file=sys.stderr)
        return 1
    if "source_account_id" in cfg and (not isinstance(cfg["source_account_id"], str) or not cfg["source_account_id"]):
        print("error: invalid source account namespace", file=sys.stderr)
        return 1

    if not isinstance(subject_wxid, str) or not subject_wxid:
        print("error: config subject_wxid must be a non-empty string", file=sys.stderr)
        return 1
    if not isinstance(viewpoint_owner_wxid, str) or not viewpoint_owner_wxid:
        print("error: config viewpoint_owner_wxid must be a non-empty string", file=sys.stderr)
        return 1
    if not isinstance(rooms, dict):
        print("error: config rooms must be an object", file=sys.stderr)
        return 1
    if not isinstance(known_participants, dict):
        print("error: config known_participants must be an object", file=sys.stderr)
        return 1

    try:
        source_file = input_path.relative_to(person_dir_resolved).as_posix()
    except ValueError:
        source_file = input_path.as_posix()

    extracted_at = datetime.now(TZ).isoformat(timespec="seconds")

    seen_ids: Set[str] = set()
    room_stats: Dict[str, RoomStat] = {}
    content_type_all: Counter = Counter()
    content_type_subject: Counter = Counter()
    unknown_msg_types: Counter = Counter()

    total_msgs = len(messages)
    in_scope_count = 0
    failed_in_scope = 0
    parsed_count = 0
    skipped_rooms: Set[str] = set()
    warnings = 0

    out_dir.mkdir(parents=True, exist_ok=True)
    out_jsonl = out_dir / "wechat_messages.uif.jsonl"
    out_report = out_dir / "wechat_parse_report.md"

    # 边解析边写 JSONL，内存只保留统计数据与 seen_ids。
    with open(out_jsonl, "w", encoding="utf-8", newline="\n") as out_f:
        for msg in messages:
            if not isinstance(msg, dict):
                warnings += 1
                continue

            chat_room = msg.get("chat_room")
            if not isinstance(chat_room, str) or chat_room not in rooms:
                if isinstance(chat_room, str):
                    skipped_rooms.add(chat_room)
                else:
                    warnings += 1
                continue

            in_scope_count += 1
            record, warn = _build_record(
                msg,
                person=person,
                cfg=cfg,
                source_file=source_file,
                extracted_at=extracted_at,
                seen=seen_ids,
                known_participants=known_participants,
            )
            warnings += warn
            if record is None:
                failed_in_scope += 1
                continue

            parsed_count += 1
            out_f.write(json.dumps(record, ensure_ascii=False))
            out_f.write("\n")

            sender_wxid = record["sender_wxid"]
            ctype = record["content_type"]
            content_type_all[ctype] += 1

            if sender_wxid == subject_wxid:
                content_type_subject[ctype] += 1

            st = room_stats.get(chat_room)
            if st is None:
                label = rooms[chat_room].get("label", "") if isinstance(rooms[chat_room], dict) else ""
                st = RoomStat(label=label)
                room_stats[chat_room] = st
            st.total += 1
            if sender_wxid == subject_wxid:
                st.subject_count += 1

            if record["timestamp"] is not None:
                ts_dt = datetime.fromisoformat(record["timestamp"])
                if st.first_ts is None or ts_dt < st.first_ts:
                    st.first_ts = ts_dt
                if st.last_ts is None or ts_dt > st.last_ts:
                    st.last_ts = ts_dt

            msg_type = record["msg_type_native"]
            if msg_type not in KNOWN_MSG_TYPES:
                unknown_msg_types[msg_type] += 1

    out_of_scope = total_msgs - in_scope_count

    _write_report(
        out_report,
        source_file=source_file,
        extracted_at=extracted_at,
        total_msgs=total_msgs,
        in_scope_count=in_scope_count,
        out_of_scope=out_of_scope,
        failed_in_scope=failed_in_scope,
        parsed_count=parsed_count,
        skipped_rooms=skipped_rooms,
        warnings=warnings,
        room_stats=room_stats,
        content_type_all=content_type_all,
        content_type_subject=content_type_subject,
        unknown_msg_types=unknown_msg_types,
    )

    subject_msgs = sum(st.subject_count for st in room_stats.values())
    print(
        f"[ok] parsed={parsed_count} subject_msgs={subject_msgs} "
        f"rooms={len(room_stats)} warnings={warnings} "
        f"-> {_ascii(str(out_jsonl))}"
    )
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Parse WeChat export JSON into UIF JSONL and report."
    )
    parser.add_argument("--person", required=True, help="Person slug")
    parser.add_argument("--input", help="Override input WeChat JSON path")
    parser.add_argument("--config", help="Override parse config path")
    parser.add_argument("--repo-root", help="Repository root (default: parent of tools/)")
    args = parser.parse_args(argv)

    try:
        return _run(args)
    except Exception as exc:
        print(f"error: {_ascii(str(exc))}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
