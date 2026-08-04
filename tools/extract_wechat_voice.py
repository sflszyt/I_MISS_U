#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""提取微信已解密 sqlite 中的语音消息(SILK)并解码为 WAV。

铁律：
- raw/ 目录与 db-dir 只读，绝不写入任何字节。
- 所有 sqlite 文件只以只读模式打开，SQL 仅限 SELECT/PRAGMA。
- sender_wxid 保持原始值；仅在文件名中使用 known_participants 别名或原始 wxid。
- 控制台输出仅 ASCII；文件输出统一 UTF-8、newline="\\n"。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import urllib.parse
import wave
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import pysilk
except ImportError:
    print("ERROR: pysilk is not installed. Run: pip install pysilk-mod", file=sys.stderr)
    sys.exit(1)


PARSER_VERSION = "1.0.0"
VIEWPOINT = "justin"
SAMPLE_RATE = 24000
SILK_HEADER = b"\x02#!SILK_V3"


@dataclass
class MsgInfo:
    chat_room: str
    sender_wxid: str
    create_time: Optional[int]


def ascii_safe(s: Any) -> str:
    return str(s).encode("ascii", "backslashreplace").decode("ascii")


def fatal(msg: str) -> None:
    print(f"ERROR: {ascii_safe(msg)}", file=sys.stderr)
    sys.exit(1)


def md5_hex(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def sanitize_component(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", value)


def sanitize_room_dir(chat_id: str) -> str:
    out = sanitize_component(chat_id)
    return out or "room"


def format_time_cn(create_time: Any) -> Optional[str]:
    try:
        dt = datetime.fromtimestamp(int(create_time), tz=timezone(timedelta(hours=8)))
        return dt.strftime("%Y%m%d_%H%M%S")
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def format_time_iso(create_time: Any) -> Optional[str]:
    try:
        dt = datetime.fromtimestamp(int(create_time), tz=timezone(timedelta(hours=8)))
        return dt.isoformat(timespec="seconds")
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def open_db_ro(path: Path) -> sqlite3.Connection:
    raw_path = path.resolve().as_posix()
    quoted = urllib.parse.quote(raw_path, safe="/:")
    conn = sqlite3.connect(f"file:{quoted}?mode=ro", uri=True)
    return conn


def ensure_output_path(path: Path, repo_root: Path, person: str) -> Path:
    repo_root = repo_root.resolve()
    resolved = path.resolve()
    try:
        rel = resolved.relative_to(repo_root)
    except ValueError:
        raise ValueError(
            f"output path escapes repo root: {resolved} (root={repo_root})"
        )

    parts = rel.parts
    allowed = {
        ("people", person, "processed"),
        ("people", person, "normalized"),
    }
    if len(parts) < 3 or parts[:3] not in allowed:
        raise ValueError(
            f"output path not under people/{person}/processed or people/{person}/normalized: {resolved}"
        )
    if "raw" in parts:
        raise ValueError(f"output path contains raw component: {resolved}")

    return resolved


def load_name2id(conn: sqlite3.Connection) -> Dict[int, str]:
    rows = conn.execute("SELECT rowid, user_name FROM Name2Id")
    return {int(rid): str(name) for rid, name in rows}


def init_counts(rooms: List[str]) -> Dict[str, Dict[str, int]]:
    return {
        room: {"total": 0, "subject": 0, "nonsubject": 0}
        for room in rooms
    }


def add_count(counts: Dict[str, Dict[str, int]], room: str, is_subject: bool) -> None:
    counts[room]["total"] += 1
    if is_subject:
        counts[room]["subject"] += 1
    else:
        counts[room]["nonsubject"] += 1


def collect_msg_index(
    message_dbs: List[Path],
    rooms: List[str],
    subject_wxid: str,
    warnings: List[str],
) -> Tuple[Dict[int, MsgInfo], Dict[str, Dict[str, int]], int]:
    index: Dict[int, MsgInfo] = {}
    expected = init_counts(rooms)
    opened = 0

    for db_path in message_dbs:
        try:
            conn = open_db_ro(db_path)
        except sqlite3.Error as exc:
            warnings.append(f"cannot open message db {db_path.name}: {exc}")
            continue
        opened += 1
        try:
            name2id: Dict[int, str] = {}
            try:
                name2id = load_name2id(conn)
            except sqlite3.Error as exc:
                warnings.append(f"{db_path.name}: cannot read Name2Id: {exc}; sender resolution disabled")

            for chat in rooms:
                table = f"Msg_{md5_hex(chat)}"
                try:
                    cur = conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                        (table,),
                    )
                    exists = cur.fetchone()
                except sqlite3.Error as exc:
                    warnings.append(f"{db_path.name}: sqlite_master check failed for {table}: {exc}")
                    continue

                if exists is None:
                    continue

                sql = (
                    f'SELECT local_id, server_id, real_sender_id, create_time '
                    f'FROM "{table}" WHERE local_type=34'
                )
                try:
                    rows = conn.execute(sql)
                except sqlite3.Error as exc:
                    warnings.append(f"{db_path.name}: query {table} failed: {exc}")
                    continue

                try:
                    for local_id, server_id, real_sender_id, create_time in rows:
                        if server_id is None:
                            continue

                        try:
                            rid = int(real_sender_id)
                        except (TypeError, ValueError):
                            rid = None

                        if rid is not None and rid in name2id:
                            sender_wxid = name2id[rid]
                        else:
                            sender_wxid = f"unknown_id_{rid}" if rid is not None else "unknown_id_null"
                            warnings.append(
                                f"{db_path.name}: real_sender_id {rid} not found in Name2Id "
                                f"(server_id={server_id}, chat={chat})"
                            )

                        if server_id in index:
                            old = index[server_id]
                            if (
                                old.chat_room != chat
                                or old.sender_wxid != sender_wxid
                                or old.create_time != create_time
                            ):
                                warnings.append(
                                    f"duplicate server_id {server_id} has inconsistent fields "
                                    f"({old.chat_room}/{old.sender_wxid}/{old.create_time} vs "
                                    f"{chat}/{sender_wxid}/{create_time})"
                                )
                            continue

                        index[server_id] = MsgInfo(
                            chat_room=chat,
                            sender_wxid=sender_wxid,
                            create_time=create_time,
                        )
                        add_count(expected, chat, sender_wxid == subject_wxid)
                except sqlite3.Error as exc:
                    warnings.append(f"{db_path.name}: iterate {table} failed: {exc}")
        finally:
            conn.close()

    return index, expected, opened


def write_voice_artifact(
    *,
    out_dir_base: Path,
    repo_root: Path,
    person: str,
    media_db_name: str,
    svr_id: int,
    info: MsgInfo,
    pcm: bytes,
    known_participants: Dict[str, str],
    subject_wxid: str,
    extracted_at: str,
) -> Tuple[Path, Dict[str, Any], Optional[str]]:
    room_dir = sanitize_room_dir(info.chat_room)
    out_dir = out_dir_base / room_dir
    ensure_output_path(out_dir, repo_root, person)
    out_dir.mkdir(parents=True, exist_ok=True)

    time_tag = format_time_cn(info.create_time)
    warning: Optional[str] = None
    if time_tag is None:
        time_tag = "unknown_time"
        warning = f"invalid create_time for svr_id {svr_id} (chat={info.chat_room})"

    alias = known_participants.get(info.sender_wxid)
    sender_tag_raw = alias if alias not in (None, "") else info.sender_wxid
    sender_tag = sanitize_component(str(sender_tag_raw)) or "unknown"

    filename = f"{time_tag}_{svr_id}_{sender_tag}.wav"
    out_path = out_dir / filename
    ensure_output_path(out_path, repo_root, person)

    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm)

    sha256_hex = hashlib.sha256(out_path.read_bytes()).hexdigest()
    size_bytes = out_path.stat().st_size
    frames = len(pcm) // 2
    duration_ms = int(round(frames * 1000 / SAMPLE_RATE))

    timestamp = format_time_iso(info.create_time)

    try:
        create_time_epoch: Optional[int] = int(info.create_time)
    except (TypeError, ValueError):
        create_time_epoch = None

    record = {
        "record_id": hashlib.sha256(f"wechat_voice:{svr_id}".encode("utf-8")).hexdigest(),
        "record_type": "media_item",
        "person": person,
        "viewpoint": VIEWPOINT,
        "source": "wechat",
        "timestamp": timestamp,
        "timestamp_precision": "exact" if timestamp else "unknown",
        "tier": 2,
        "lang": "zh",
        "provenance": {
            "source_file": media_db_name,
            "parser": "extract_wechat_voice",
            "parser_version": PARSER_VERSION,
            "extracted_at": extracted_at,
            "native_id": str(svr_id),
        },
        "media_type": "audio",
        "file_ref": f"processed/wechat_voice/{room_dir}/{filename}",
        "sha256": sha256_hex,
        "size_bytes": size_bytes,
        "duration_ms": duration_ms,
        "chat_room": info.chat_room,
        "sender_wxid": info.sender_wxid,
        "svr_id": svr_id,
        "create_time_epoch": create_time_epoch,
        "is_subject": info.sender_wxid == subject_wxid,
    }
    if alias not in (None, ""):
        record["sender_alias"] = alias

    return out_path, record, warning


def write_report(
    report_path: Path,
    rooms_config: Dict[str, Any],
    expected: Dict[str, Dict[str, int]],
    success: Dict[str, Dict[str, int]],
    missing: Dict[str, Dict[str, int]],
    failed: Dict[str, Dict[str, int]],
    unchecked: Dict[str, Dict[str, int]],
    missing_items: List[Tuple[str, int, MsgInfo, str]],
    failed_items: List[Tuple[str, int, MsgInfo, str]],
    unchecked_items: List[Tuple[str, int, MsgInfo, str]],
    media_scan_incomplete: bool,
    warnings: List[str],
    message_dbs: List[Path],
    media_dbs: List[Path],
    extracted_at: str,
) -> None:
    lines: List[str] = []
    lines.append("# wechat_voice 提取报告")
    lines.append("")
    lines.append(f"- 生成时间: {extracted_at}")
    lines.append(f"- parser: extract_wechat_voice v{PARSER_VERSION}")
    lines.append(f"- 警告数: {len(warnings)}")
    lines.append(f"- media 扫描: {'不完整' if media_scan_incomplete else '完整'}")
    lines.append(f"- 输入 message db: {', '.join(p.name for p in message_dbs)}")
    lines.append(f"- 输入 media db: {', '.join(p.name for p in media_dbs)}")
    lines.append("")

    for chat in expected:
        meta = rooms_config.get(chat, {})
        label = meta.get("label") if isinstance(meta, dict) else None
        heading = f"{label} (`{chat}`)" if label else f"`{chat}`"
        lines.append(f"## {heading}")
        lines.append("")

        exp = expected[chat]
        suc = success[chat]
        mis = missing[chat]
        fail = failed[chat]
        unch = unchecked[chat]

        lines.append(f"- 期望: total={exp['total']}, subject={exp['subject']}, non-subject={exp['nonsubject']}")
        lines.append(f"- 成功: total={suc['total']}, subject={suc['subject']}, non-subject={suc['nonsubject']}")
        lines.append(f"- 缺 blob: total={mis['total']}, subject={mis['subject']}, non-subject={mis['nonsubject']}")
        lines.append(f"- 解码失败: total={fail['total']}, subject={fail['subject']}, non-subject={fail['nonsubject']}")
        lines.append(f"- 未核查: total={unch['total']}, subject={unch['subject']}, non-subject={unch['nonsubject']}")
        lines.append(f"- 恒等式: {exp['total']} = {suc['total']} + {mis['total']} + {fail['total']} + {unch['total']}")
        lines.append(f"- 恒等式(subject): {exp['subject']} = {suc['subject']} + {mis['subject']} + {fail['subject']} + {unch['subject']}")
        lines.append(f"- 恒等式(non-subject): {exp['nonsubject']} = {suc['nonsubject']} + {mis['nonsubject']} + {fail['nonsubject']} + {unch['nonsubject']}")
        lines.append("")

        chat_missing = [item for item in missing_items if item[0] == chat]
        chat_failed = [item for item in failed_items if item[0] == chat]
        chat_unchecked = [item for item in unchecked_items if item[0] == chat]

        if chat_missing:
            lines.append("### 缺失清单")
            for _, svr_id, info, reason in chat_missing:
                lines.append(
                    f"- svr_id={svr_id}, time={format_time_iso(info.create_time) or 'unknown'}, "
                    f"sender={info.sender_wxid}, reason={reason}"
                )
            lines.append("")

        if chat_failed:
            lines.append("### 解码失败清单")
            for _, svr_id, info, reason in chat_failed:
                lines.append(
                    f"- svr_id={svr_id}, time={format_time_iso(info.create_time) or 'unknown'}, "
                    f"sender={info.sender_wxid}, reason={reason}"
                )
            lines.append("")

        if chat_unchecked:
            lines.append("### 未核查清单（media 扫描不完整）")
            for _, svr_id, info, reason in chat_unchecked:
                lines.append(
                    f"- svr_id={svr_id}, time={format_time_iso(info.create_time) or 'unknown'}, "
                    f"sender={info.sender_wxid}, reason={reason}"
                )
            lines.append("")

    lines.append("## 生成信息")
    lines.append("")
    lines.append(f"- 生成时间: {extracted_at}")
    lines.append(f"- parser_version: {PARSER_VERSION}")
    lines.append(f"- message dbs: {', '.join(p.name for p in message_dbs)}")
    lines.append(f"- media dbs: {', '.join(p.name for p in media_dbs)}")
    lines.append("")

    lines.append("## 警告清单")
    lines.append("")
    if warnings:
        for i, w in enumerate(warnings, 1):
            lines.append(f"{i}. {w}")
    else:
        lines.append("- 无")
    lines.append("")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def parse_args(argv: Optional[List[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract WeChat voice SILK blobs from decrypted plain sqlite and decode to WAV."
    )
    parser.add_argument("--person", required=True, help="person slug, e.g. mama")
    parser.add_argument("--db-dir", required=True, help="directory containing decrypted message_*_plain.db and media_*_plain.db")
    parser.add_argument("--config", default=None, help="path to wechat_parse_config.json")
    parser.add_argument("--repo-root", default=None, help="repo root, default is project root")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    person = args.person

    if not re.fullmatch(r"[a-z0-9_-]+", person):
        fatal(f"invalid person slug: {person}")

    repo_root = Path(args.repo_root).resolve() if args.repo_root else Path(__file__).resolve().parent.parent
    repo_root = repo_root.resolve()

    if not (repo_root / "CLAUDE.md").is_file() or not (repo_root / "schema" / "uif.schema.json").is_file():
        fatal("--repo-root must point to the I_MISS_U repository root (missing CLAUDE.md or schema/uif.schema.json)")

    db_dir = Path(args.db_dir).resolve()
    if not db_dir.is_dir():
        fatal(f"db-dir does not exist or is not a directory: {db_dir}")

    message_dbs = sorted(db_dir.glob("message_*_plain.db"), key=lambda p: p.name)
    media_dbs = sorted(db_dir.glob("media_*_plain.db"), key=lambda p: p.name)

    if not message_dbs:
        fatal(f"no message_*_plain.db found in {db_dir}")
    if not media_dbs:
        fatal(f"no media_*_plain.db found in {db_dir}")

    config_path = Path(args.config).resolve() if args.config else repo_root / "people" / person / "wechat_parse_config.json"
    if not config_path.is_file():
        fatal(f"config file not found: {config_path}")

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        fatal(f"failed to read config {config_path}: {exc}")

    subject_wxid = config.get("subject_wxid")
    rooms_config = config.get("rooms")
    known_cfg = config.get("known_participants", {})

    if not isinstance(subject_wxid, str) or not subject_wxid:
        fatal(f"config {config_path} missing string subject_wxid")
    if not isinstance(rooms_config, dict):
        fatal(f"config {config_path} missing dict rooms")
    if not isinstance(known_cfg, dict):
        known_cfg = {}

    rooms = list(rooms_config.keys())
    known_participants: Dict[str, str] = {
        str(k): str(v) for k, v in known_cfg.items()
    }

    warnings: List[str] = []

    msg_index, expected, opened_message_dbs = collect_msg_index(
        message_dbs, rooms, subject_wxid, warnings
    )
    if opened_message_dbs == 0:
        fatal("all message_*_plain.db files failed to open")

    extracted_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    processed_voice_dir = repo_root / "people" / person / "processed" / "wechat_voice"
    normalized_dir = repo_root / "people" / person / "normalized"

    try:
        ensure_output_path(processed_voice_dir, repo_root, person)
        ensure_output_path(normalized_dir, repo_root, person)
    except ValueError as exc:
        fatal(str(exc))

    processed_voice_dir.mkdir(parents=True, exist_ok=True)
    normalized_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = normalized_dir / "wechat_voice_manifest.jsonl"
    report_path = normalized_dir / "wechat_voice_report.md"

    try:
        ensure_output_path(manifest_path, repo_root, person)
        ensure_output_path(report_path, repo_root, person)
    except ValueError as exc:
        fatal(str(exc))

    success_counts = init_counts(rooms)
    missing_counts = init_counts(rooms)
    failed_counts = init_counts(rooms)
    unchecked_counts = init_counts(rooms)
    missing_items: List[Tuple[str, int, MsgInfo, str]] = []
    failed_items: List[Tuple[str, int, MsgInfo, str]] = []
    unchecked_items: List[Tuple[str, int, MsgInfo, str]] = []
    found_svr: set = set()
    media_scan_incomplete = False

    with open(manifest_path, "w", encoding="utf-8", newline="\n") as manifest_fh:
        for media_db in media_dbs:
            try:
                conn = open_db_ro(media_db)
            except sqlite3.Error as exc:
                media_scan_incomplete = True
                warnings.append(f"cannot open media db {media_db.name}: {exc}")
                continue

            try:
                try:
                    cursor = conn.execute(
                        "SELECT svr_id, voice_data, create_time, chat_name_id FROM VoiceInfo"
                    )
                except sqlite3.Error as exc:
                    media_scan_incomplete = True
                    warnings.append(f"{media_db.name}: VoiceInfo query failed: {exc}")
                    continue

                try:
                    for svr_id, voice_data, _voice_create_time, _chat_name_id in cursor:
                        if svr_id is None or svr_id not in msg_index or svr_id in found_svr:
                            continue

                        info = msg_index[svr_id]
                        found_svr.add(svr_id)

                        if voice_data is None or len(voice_data) == 0:
                            add_count(missing_counts, info.chat_room, info.sender_wxid == subject_wxid)
                            missing_items.append(
                                (info.chat_room, svr_id, info, "voice_data is NULL/empty")
                            )
                            continue

                        try:
                            pcm = pysilk.decode(bytes(voice_data), SAMPLE_RATE)
                        except Exception as exc:
                            add_count(failed_counts, info.chat_room, info.sender_wxid == subject_wxid)
                            failed_items.append(
                                (info.chat_room, svr_id, info, f"decode error: {exc}")
                            )
                            continue

                        try:
                            _, record, time_warning = write_voice_artifact(
                                out_dir_base=processed_voice_dir,
                                repo_root=repo_root,
                                person=person,
                                media_db_name=media_db.name,
                                svr_id=svr_id,
                                info=info,
                                pcm=pcm,
                                known_participants=known_participants,
                                subject_wxid=subject_wxid,
                                extracted_at=extracted_at,
                            )
                        except Exception as exc:
                            conn.close()
                            fatal(f"failed to write voice artifact (svr_id={svr_id}): {exc}")

                        if time_warning:
                            warnings.append(time_warning)

                        add_count(success_counts, info.chat_room, info.sender_wxid == subject_wxid)
                        manifest_fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                except sqlite3.Error as exc:
                    media_scan_incomplete = True
                    warnings.append(f"{media_db.name}: VoiceInfo iteration failed: {exc}")
            finally:
                conn.close()

    for svr_id, info in msg_index.items():
        if svr_id in found_svr:
            continue

        is_subject = info.sender_wxid == subject_wxid
        if media_scan_incomplete:
            add_count(unchecked_counts, info.chat_room, is_subject)
            unchecked_items.append(
                (info.chat_room, svr_id, info, "no VoiceInfo row (media scan incomplete)")
            )
        else:
            add_count(missing_counts, info.chat_room, is_subject)
            missing_items.append((info.chat_room, svr_id, info, "no VoiceInfo row"))

    write_report(
        report_path=report_path,
        rooms_config=rooms_config,
        expected=expected,
        success=success_counts,
        missing=missing_counts,
        failed=failed_counts,
        unchecked=unchecked_counts,
        missing_items=missing_items,
        failed_items=failed_items,
        unchecked_items=unchecked_items,
        media_scan_incomplete=media_scan_incomplete,
        warnings=warnings,
        message_dbs=message_dbs,
        media_dbs=media_dbs,
        extracted_at=extracted_at,
    )

    extracted_total = sum(success_counts[r]["total"] for r in rooms)
    subject_total = sum(success_counts[r]["subject"] for r in rooms)
    missing_total = sum(missing_counts[r]["total"] for r in rooms)
    unchecked_total = sum(unchecked_counts[r]["total"] for r in rooms)
    failed_total = sum(failed_counts[r]["total"] for r in rooms)
    warning_total = len(warnings)

    print(
        f"[ok] extracted={extracted_total} subject={subject_total} "
        f"missing_blob={missing_total} unchecked={unchecked_total} "
        f"decode_failed={failed_total} warnings={warning_total} -> {ascii_safe(manifest_path)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
