#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""采集微信视频原始 mp4 到 raw 档案并输出 UIF manifest/报告。

铁律（raw 永不覆盖/修改/删除）：
- raw/wechat/video 下只允许“新增不存在的文件”；
- 目标已存在时绝不打开写句柄，绝不覆盖，比较 sha256 后只区分 already_present / conflict；
- normalized 下允许覆盖 manifest 和报告。
"""
from __future__ import annotations

try:
    from .local_identity import owner_participant
except ImportError:
    from local_identity import owner_participant


import argparse
import hashlib
import json
import os
import stat
import re
import shutil
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

PARSER_NAME = "collect_wechat_video"
PARSER_VERSION = "1.0.0"
VIEWPOINT = owner_participant()
CHUNK_SIZE = 8 * 1024 * 1024
RAW_PREFIX = ("raw", "wechat", "video")
NORMALIZED_PREFIX = ("normalized",)


def ascii_print(message: str) -> None:
    """向 stdout 输出 ASCII 安全文本。"""
    sys.stdout.write(message.encode("ascii", "backslashreplace").decode("ascii") + "\n")
    sys.stdout.flush()


def ascii_eprint(message: str) -> None:
    """向 stderr 输出 ASCII 安全文本。"""
    sys.stderr.write(message.encode("ascii", "backslashreplace").decode("ascii") + "\n")


def fatal(message: str) -> None:
    ascii_eprint(f"error: {message}")
    raise SystemExit(1)


def connect_ro(db_path: Path) -> sqlite3.Connection:
    """以只读方式连接 sqlite。"""
    full = str(db_path.resolve())
    uri = "file:{}?mode=ro".format(quote(full, safe="/:"))
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _force_unlink(path: Path) -> None:
    """删除 staging 临时文件。微信源 mp4 带 ReadOnly 属性且 copy2 会连属性复制，
    Windows 上直接 unlink 只读文件报 PermissionError，需先清除只读位。"""
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except PermissionError:
        os.chmod(path, stat.S_IWRITE)
        path.unlink()


def _exclusive_copy(staging_file: Path, target: Path) -> None:
    """Copy staging file to target with O_EXCL; never overwrite, never leave partial."""
    created = False
    try:
        out = open(target, "xb")
    except FileExistsError:
        raise
    created = True
    try:
        with out:
            with open(staging_file, "rb") as src:
                while True:
                    chunk = src.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    out.write(chunk)
    except BaseException:
        if created:
            try:
                target.unlink()
            except FileNotFoundError:
                pass
        raise


def _stage_and_place(
    src: Path,
    staging_file: Path,
    target: Path,
    source_sha: str,
    file_ref: str,
    fallback_warned: list[bool],
    warnings: list[str],
) -> tuple[str, str, int]:
    """Atomically place a staged copy of src at target.

    Returns (status, sha256, size_bytes). status is one of:
      copied  - target did not exist and was created from staging file
      already - target existed with content identical to source
      conflict - target existed with different content (old file is kept)
    """
    try:
        if staging_file.exists():
            _force_unlink(staging_file)
        shutil.copy2(src, staging_file)
        os.chmod(staging_file, stat.S_IWRITE)
        target_sha = sha256_file(staging_file)
        size = staging_file.stat().st_size

        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(staging_file, target)
            return "copied", target_sha, size
        except FileExistsError:
            existing_sha = sha256_file(target)
            existing_size = target.stat().st_size
            if existing_sha == source_sha:
                return "already", existing_sha, existing_size
            return "conflict", existing_sha, existing_size
        except OSError as e:
            if not fallback_warned[0]:
                warnings.append(
                    f"hard link unavailable for {file_ref}: {e}; using exclusive write fallback"
                )
                fallback_warned[0] = True
            try:
                _exclusive_copy(staging_file, target)
            except FileExistsError:
                existing_sha = sha256_file(target)
                existing_size = target.stat().st_size
                if existing_sha == source_sha:
                    return "already", existing_sha, existing_size
                return "conflict", existing_sha, existing_size
            return "copied", target_sha, size
    finally:
        _force_unlink(staging_file)


def ensure_safe_output(repo_root: Path, target: Path, allowed_prefix: tuple[str, ...]) -> Path:
    """校验输出路径锚定在仓库内且前缀合规，返回 resolve 后的路径。"""
    repo = repo_root.resolve()
    resolved = target.resolve()
    try:
        rel = resolved.relative_to(repo)
    except ValueError:
        fatal(f"refusing to write outside repo: {resolved}")
    if rel.parts[: len(allowed_prefix)] != allowed_prefix:
        fatal(f"refusing unsafe output path: {resolved}")
    return resolved


def load_config(config_path: Path) -> dict[str, Any]:
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        fatal(f"cannot read config {config_path}: {e}")
    if not isinstance(data, dict):
        fatal(f"config {config_path} is not a JSON object")
    return data


def validate_config(cfg: dict[str, Any], config_path: Path) -> None:
    """校验配置中必需字段，缺失/类型错误即致命。"""
    subject_wxid = cfg.get("subject_wxid")
    if not isinstance(subject_wxid, str) or not subject_wxid.strip():
        fatal(f"config {config_path}: subject_wxid must be a non-empty string")

    rooms = cfg.get("rooms")
    if not isinstance(rooms, dict):
        fatal(f"config {config_path}: rooms must be a dict")

    known = cfg.get("known_participants", {})
    if known is None:
        known = {}
    if not isinstance(known, dict):
        fatal(f"config {config_path}: known_participants must be a dict")


def get_room_names(cfg: dict[str, Any]) -> list[str]:
    """会话名直接来自 config rooms 的 key。"""
    rooms_cfg = cfg["rooms"]
    return [r for r in rooms_cfg.keys() if isinstance(r, str) and r.strip()]


def build_alias_map(cfg: dict[str, Any]) -> dict[str, str]:
    """known_participants 是平铺 dict：wxid -> 别名字符串。"""
    aliases: dict[str, str] = {}
    known = cfg.get("known_participants", {}) or {}
    for wxid, val in known.items():
        if isinstance(val, str) and val.strip():
            aliases[str(wxid)] = val.strip()
    return aliases


def load_name2id(conn: sqlite3.Connection) -> dict[int, str]:
    """读取 Name2Id：rowid -> wxid。表结构已实机验证：列就是 user_name。"""
    mapping: dict[int, str] = {}
    try:
        cur = conn.execute('SELECT rowid, user_name FROM "Name2Id"')
        for row in cur:
            mapping[int(row["rowid"])] = row["user_name"]
    except sqlite3.Error:
        return {}
    return mapping


def extract_md5_candidates(blob: Any) -> list[str]:
    if blob is None:
        return []
    if isinstance(blob, memoryview):
        blob = blob.tobytes()
    elif isinstance(blob, str):
        blob = blob.encode("ascii", "ignore")
    found: list[str] = []
    for m in re.finditer(rb"[0-9a-f]{32}", blob):
        s = m.group().decode("ascii")
        if s not in found:
            found.append(s)
    return found


@dataclass
class VideoMessage:
    db_file: Path
    table: str
    server_id: Optional[int]
    sender_wxid: Optional[str]
    create_time: Optional[int]
    candidates: list[str]
    chat_room: str


def scan_video_messages(
    db_paths: list[Path], cfg: dict[str, Any], warnings: list[str]
) -> dict[int, VideoMessage]:
    rooms = get_room_names(cfg)
    master: dict[int, VideoMessage] = {}
    opened_any = False
    unknown_sender_warned: set[tuple[str, str]] = set()

    for db_path in db_paths:
        try:
            conn = connect_ro(db_path)
        except Exception as e:
            warnings.append(f"cannot open message db {db_path.name}: {e}")
            continue
        opened_any = True
        try:
            name2id = load_name2id(conn)

            for room in rooms:
                table = "Msg_" + hashlib.md5(room.encode("utf-8")).hexdigest().lower()
                try:
                    cur = conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
                    )
                    exists = cur.fetchone() is not None
                except Exception as e:
                    warnings.append(f"cannot check table {table} in {db_path.name}: {e}")
                    continue

                if not exists:
                    continue

                qtable = table.replace('"', '""')
                try:
                    rows = conn.execute(
                        "SELECT local_id, server_id, real_sender_id, create_time, packed_info_data "
                        f'FROM "{qtable}" WHERE local_type = 43 ORDER BY local_id'
                    ).fetchall()
                except Exception as e:
                    warnings.append(f"query video rows failed for {db_path.name}/{table}: {e}")
                    continue

                no_cand_warned = False
                for row in rows:
                    try:
                        server_id_raw = row["server_id"]
                        if server_id_raw is None:
                            warnings.append(f"{db_path.name}/{table}: server_id is NULL; skipped")
                            continue
                        server_id = int(server_id_raw)

                        create_time_raw = row["create_time"]
                        try:
                            create_time = int(create_time_raw) if create_time_raw is not None else None
                        except (TypeError, ValueError):
                            create_time = None

                        sender_rowid = row["real_sender_id"]
                        if sender_rowid is None:
                            sender_wxid = "unknown_id_unknown"
                        else:
                            try:
                                rid = int(sender_rowid)
                            except (TypeError, ValueError):
                                rid = None

                            if rid is not None and rid in name2id:
                                sender_wxid = name2id[rid]
                            else:
                                raw_rid = rid if rid is not None else sender_rowid
                                sender_wxid = f"unknown_id_{raw_rid}"
                                key = (db_path.name, str(raw_rid))
                                if key not in unknown_sender_warned:
                                    warnings.append(
                                        f"{db_path.name}/{table}: real_sender_id {raw_rid} not in Name2Id"
                                    )
                                    unknown_sender_warned.add(key)

                        candidates = extract_md5_candidates(row["packed_info_data"])
                        if not candidates and not no_cand_warned:
                            warnings.append(
                                f"{db_path.name}/{table}: message {server_id} has no md5 candidate"
                            )
                            no_cand_warned = True

                        msg = VideoMessage(
                            db_file=db_path,
                            table=table,
                            server_id=server_id,
                            sender_wxid=sender_wxid,
                            create_time=create_time,
                            candidates=candidates,
                            chat_room=room,
                        )
                        if server_id in master:
                            old = master[server_id]
                            if (
                                old.sender_wxid != sender_wxid
                                or old.create_time != create_time
                                or old.candidates != candidates
                                or old.chat_room != room
                            ):
                                warnings.append(
                                    f"server_id {server_id} duplicated with inconsistent metadata "
                                    f"between {old.db_file.name} and {db_path.name}; keeping first"
                                )
                        else:
                            master[server_id] = msg
                    except Exception as e:
                        warnings.append(f"failed to parse video row in {db_path.name}/{table}: {e}")
        except Exception as e:
            warnings.append(f"failed to process message db {db_path.name}: {e}")
        finally:
            conn.close()

    if not opened_any:
        fatal("no message db could be opened")
    return master


def build_disk_index(video_dir: Path, warnings: list[str]) -> tuple[dict[str, Path], int]:
    mp4s = sorted(video_dir.glob("**/msg/video/**/*.mp4"), key=lambda p: p.as_posix().lower())
    if not mp4s:
        mp4s = sorted(video_dir.glob("**/*.mp4"), key=lambda p: p.as_posix().lower())
    if not mp4s:
        fatal(f"no mp4 found under video-dir: {video_dir} (path may be wrong)")

    index: dict[str, Path] = {}
    for p in mp4s:
        md5 = p.stem.lower()
        if md5 in index:
            warnings.append(f"duplicate md5 filename {md5}: {p} ignored")
        else:
            index[md5] = p
    return index, len(mp4s)


def derive_year_month(src: Path, create_time: Optional[int]) -> str:
    parts = src.parts
    for i, part in enumerate(parts):
        if part.lower() == "video" and i + 1 < len(parts) - 1:
            ym = parts[i + 1]
            if ym not in (".", "..") and "/" not in ym and "\\" not in ym:
                return ym
    if create_time is not None:
        try:
            dt = datetime.fromtimestamp(create_time, tz=timezone(timedelta(hours=8)))
            return dt.strftime("%Y-%m")
        except (OverflowError, OSError, ValueError, TypeError):
            pass
    return "unknown"


def create_time_to_iso(epoch: Optional[int]) -> tuple[Optional[str], str]:
    if epoch is None:
        return None, "unknown"
    try:
        dt = datetime.fromtimestamp(epoch, tz=timezone(timedelta(hours=8)))
        return dt.isoformat(timespec="seconds"), "exact"
    except (OverflowError, OSError, ValueError, TypeError):
        return None, "unknown"


def ensure_stats(stats: dict[str, dict[str, int]], chat: str) -> dict[str, int]:
    if chat not in stats:
        stats[chat] = {
            "expected": 0,
            "copied": 0,
            "already": 0,
            "conflict": 0,
            "missing": 0,
            "errors": 0,
            "subj_expected": 0,
            "subj_copied": 0,
            "subj_already": 0,
            "subj_conflict": 0,
            "subj_missing": 0,
            "subj_errors": 0,
        }
    return stats[chat]


def inc_stat(stats: dict[str, dict[str, int]], chat: str, is_subject: bool, key: str) -> None:
    s = ensure_stats(stats, chat)
    s[key] += 1
    if is_subject:
        s["subj_" + key] += 1


def md_escape(v: Any) -> str:
    s = "" if v is None else str(v)
    return s.replace("|", "\\|").replace("\n", " ")


def render_epoch(epoch: Optional[int]) -> str:
    if epoch is None:
        return "-"
    iso, _ = create_time_to_iso(epoch)
    return iso if iso else str(epoch)


def write_report(
    report_path: Path,
    person: str,
    db_paths: list[Path],
    video_dir: Path,
    mp4_count: int,
    total_messages: int,
    subject_message_count: int,
    stats: dict[str, dict[str, int]],
    missing_list: list[tuple[Any, ...]],
    conflict_list: list[tuple[Any, ...]],
    warnings: list[str],
    generated_at: str,
    extracted_at: str,
) -> None:
    total_expected = sum(s["expected"] for s in stats.values())
    total_copied = sum(s["copied"] for s in stats.values())
    total_already = sum(s["already"] for s in stats.values())
    total_conflict = sum(s["conflict"] for s in stats.values())
    total_missing = sum(s["missing"] for s in stats.values())
    total_errors = sum(s["errors"] for s in stats.values())

    lines: list[str] = []
    lines.append("# WeChat 视频采集报告")
    lines.append("")
    lines.append(f"- person: `{person}`")
    lines.append(f"- 生成时间: {generated_at}")
    lines.append(f"- extracted_at: {extracted_at}")
    lines.append(f"- parser: {PARSER_NAME} {PARSER_VERSION}")
    lines.append("- 输入 message db:")
    for p in db_paths:
        lines.append(f"  - `{md_escape(p)}`")
    lines.append(f"- 视频目录: `{md_escape(video_dir)}`")
    lines.append(f"- 磁盘索引 mp4 总数: {mp4_count}")
    lines.append(f"- type43 视频消息总数: {total_messages}")
    lines.append("")

    lines.append("## 汇总")
    lines.append("")
    lines.append("| 指标 | 数量 |")
    lines.append("| --- | ---: |")
    lines.append(f"| 期望 | {total_expected} |")
    lines.append(f"| copied | {total_copied} |")
    lines.append(f"| already_present | {total_already} |")
    lines.append(f"| conflict | {total_conflict} |")
    lines.append(f"| missing_on_disk | {total_missing} |")
    lines.append(f"| errors | {total_errors} |")
    lines.append(f"| subject_videos | {subject_message_count} |")
    lines.append(f"| warnings | {len(warnings)} |")
    lines.append("")

    identity_holds = (
        total_expected == total_copied + total_already + total_conflict + total_missing + total_errors
    )
    lines.append("## 恒等式")
    lines.append("")
    lines.append("`期望 = copied + already_present + conflict + missing_on_disk`")
    if total_errors:
        lines.append(f"（本次存在 {total_errors} 条 errors，恒等式另加 errors 项）")
    lines.append("")
    if identity_holds:
        lines.append("恒等式成立。")
    else:
        lines.append("警告：恒等式不成立！")
    lines.append("")

    lines.append("## 分会话")
    lines.append("")
    if not stats:
        lines.append("无视频消息。")
    for chat in sorted(stats.keys()):
        s = stats[chat]
        lines.append(f"### `{md_escape(chat)}`")
        lines.append("")
        lines.append("| 范围 | 期望 | copied | already_present | conflict | missing_on_disk | errors |")
        lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")

        def stat_row(label: str, expected: int, copied: int, already: int, conflict: int, missing: int, errors: int) -> str:
            return (
                f"| {label} | {expected} | {copied} | {already} | {conflict} | {missing} | {errors} |"
            )

        lines.append(
            stat_row(
                "subject",
                s["subj_expected"],
                s["subj_copied"],
                s["subj_already"],
                s["subj_conflict"],
                s["subj_missing"],
                s["subj_errors"],
            )
        )
        lines.append(
            stat_row(
                "非 subject",
                s["expected"] - s["subj_expected"],
                s["copied"] - s["subj_copied"],
                s["already"] - s["subj_already"],
                s["conflict"] - s["subj_conflict"],
                s["missing"] - s["subj_missing"],
                s["errors"] - s["subj_errors"],
            )
        )
        lines.append(
            stat_row(
                "合计",
                s["expected"],
                s["copied"],
                s["already"],
                s["conflict"],
                s["missing"],
                s["errors"],
            )
        )
        lines.append("")

    lines.append("## 缺失清单（missing_on_disk）")
    lines.append("")
    if not missing_list:
        lines.append("无。")
    else:
        lines.append("| svr_id | 时间 | sender | md5 候选 | 会话 |")
        lines.append("| --- | --- | --- | --- | --- |")
        for svr_id, epoch, sender, cand_text, chat in missing_list:
            lines.append(
                f"| {md_escape(svr_id)} | {render_epoch(epoch)} | {md_escape(sender or '-')} | "
                f"{md_escape(cand_text)} | {md_escape(chat)} |"
            )
    lines.append("")

    lines.append("## 冲突清单（conflict）")
    lines.append("")
    if not conflict_list:
        lines.append("无。")
    else:
        lines.append("| svr_id | 时间 | sender | md5 | file_ref | 目标路径 |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for svr_id, epoch, sender, md5, file_ref, target_path in conflict_list:
            lines.append(
                f"| {md_escape(svr_id)} | {render_epoch(epoch)} | {md_escape(sender or '-')} | "
                f"{md_escape(md5)} | {md_escape(file_ref)} | {md_escape(target_path)} |"
            )
    lines.append("")

    lines.append("## 警告清单")
    lines.append("")
    if not warnings:
        lines.append("无。")
    else:
        for i, w in enumerate(warnings, 1):
            lines.append(f"{i}. {md_escape(w)}")
    lines.append("")

    with open(report_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect WeChat video raw mp4 files.")
    parser.add_argument("--person", required=True)
    parser.add_argument("--db-dir", required=True)
    parser.add_argument("--video-dir", required=True)
    parser.add_argument("--config", default=None)
    parser.add_argument("--repo-root", default=None)
    args = parser.parse_args()

    person = args.person
    if not re.fullmatch(r"[a-z0-9_-]+", person):
        fatal(f"invalid person slug: {person!r}")

    if args.repo_root:
        repo_root = Path(args.repo_root).expanduser().resolve()
    else:
        repo_root = Path(__file__).resolve().parent.parent
    repo_root = repo_root.resolve()

    if not (repo_root / "tools").is_dir():
        fatal(f"repo root sentinel tools/ not found under {repo_root}")
    if not (repo_root / "schema" / "uif.schema.json").is_file():
        fatal(f"repo root sentinel schema/uif.schema.json not found under {repo_root}")

    config_path: Path
    if args.config:
        config_path = Path(args.config).expanduser().resolve()
    else:
        config_path = repo_root / "people" / person / "wechat_parse_config.json"
    cfg = load_config(config_path)
    validate_config(cfg, config_path)

    subject_wxid = cfg["subject_wxid"].strip()

    db_dir = Path(args.db_dir).expanduser().resolve()
    if not db_dir.is_dir():
        fatal(f"db-dir does not exist: {db_dir}")

    db_paths = sorted(db_dir.glob("message_*_plain.db"), key=lambda p: p.as_posix().lower())
    if not db_paths:
        db_paths = sorted(db_dir.rglob("message_*_plain.db"), key=lambda p: p.as_posix().lower())
    if not db_paths:
        fatal(f"no message_*_plain.db found under {db_dir}")

    video_dir = Path(args.video_dir).expanduser().resolve()
    if not video_dir.is_dir():
        fatal(f"video-dir does not exist: {video_dir}")

    warnings: list[str] = []
    disk_index, mp4_count = build_disk_index(video_dir, warnings)
    master = scan_video_messages(db_paths, cfg, warnings)

    alias_map = build_alias_map(cfg)

    people_base = (repo_root / "people" / person).resolve()
    raw_video_root = ensure_safe_output(
        repo_root, people_base / "raw" / "wechat" / "video", ("people", person, *RAW_PREFIX)
    )
    normalized_dir = ensure_safe_output(
        repo_root, people_base / "normalized", ("people", person, *NORMALIZED_PREFIX)
    )
    normalized_dir.mkdir(parents=True, exist_ok=True)

    staging_dir = ensure_safe_output(
        repo_root, normalized_dir / ".staging", ("people", person, *NORMALIZED_PREFIX)
    )
    staging_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = ensure_safe_output(
        repo_root, normalized_dir / "wechat_video_manifest.jsonl", ("people", person, *NORMALIZED_PREFIX)
    )
    report_path = ensure_safe_output(
        repo_root, normalized_dir / "wechat_video_report.md", ("people", person, *NORMALIZED_PREFIX)
    )

    extracted_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    stats: dict[str, dict[str, int]] = {}
    missing_list: list[tuple[Any, ...]] = []
    conflict_list: list[tuple[Any, ...]] = []
    file_cache: dict[str, dict[str, Any]] = {}
    occurrence_count: dict[str, int] = {}
    hardlink_fallback_warned: list[bool] = [False]

    with open(manifest_path, "w", encoding="utf-8", newline="\n") as mf:
        for msg in master.values():
            chat = msg.chat_room
            s = ensure_stats(stats, chat)
            s["expected"] += 1
            is_subject = bool(subject_wxid and msg.sender_wxid == subject_wxid)
            if is_subject:
                s["subj_expected"] += 1

            try:
                hit_md5 = next((c for c in msg.candidates if c in disk_index), None)
                if hit_md5 is None:
                    inc_stat(stats, chat, is_subject, "missing")
                    cand_text = ",".join(msg.candidates) if msg.candidates else "-"
                    missing_list.append(
                        (msg.server_id, msg.create_time, msg.sender_wxid, cand_text, chat)
                    )
                    continue

                src = disk_index[hit_md5]
                year_month = derive_year_month(src, msg.create_time)
                target = raw_video_root / year_month / f"{hit_md5}.mp4"
                target = ensure_safe_output(
                    repo_root, target, ("people", person, *RAW_PREFIX)
                )
                file_ref = target.relative_to(people_base).as_posix()

                cnt = occurrence_count.get(hit_md5, 0)
                if cnt == 0:
                    source_sha = sha256_file(src)
                    if target.exists():
                        target_sha = sha256_file(target)
                        size = target.stat().st_size
                        if target_sha == source_sha:
                            first_status = "already"
                        else:
                            first_status = "conflict"
                        repeat_status = first_status
                    else:
                        staging_file = staging_dir / f"{hit_md5}.mp4.part"
                        first_status, target_sha, size = _stage_and_place(
                            src,
                            staging_file,
                            target,
                            source_sha,
                            file_ref,
                            hardlink_fallback_warned,
                            warnings,
                        )
                        repeat_status = "already" if first_status == "copied" else first_status

                    file_cache[hit_md5] = {
                        "target": target,
                        "sha256": target_sha,
                        "size_bytes": size,
                        "repeat_status": repeat_status,
                    }
                else:
                    cache = file_cache[hit_md5]
                    target = cache["target"]
                    target_sha = cache["sha256"]
                    size = cache["size_bytes"]

                occurrence_count[hit_md5] = cnt + 1
                status = first_status if cnt == 0 else file_cache[hit_md5]["repeat_status"]
                inc_stat(stats, chat, is_subject, status)

                if status == "conflict":
                    conflict_list.append(
                        (msg.server_id, msg.create_time, msg.sender_wxid, hit_md5, file_ref, str(target))
                    )
                    warnings.append(
                        f"conflict: {file_ref} exists with different sha256 than source {src} "
                        f"(message {msg.server_id})"
                    )

                timestamp, timestamp_precision = create_time_to_iso(msg.create_time)
                record_id = hashlib.sha256(f"wechat_video:{msg.server_id}".encode("utf-8")).hexdigest()
                record: dict[str, Any] = {
                    "record_id": record_id,
                    "record_type": "media_item",
                    "person": person,
                    "viewpoint": VIEWPOINT,
                    "source": "wechat",
                    "timestamp": timestamp,
                    "timestamp_precision": timestamp_precision,
                    "tier": 2,
                    "lang": "zh",
                    "provenance": {
                        "source_file": msg.db_file.name,
                        "parser": PARSER_NAME,
                        "parser_version": PARSER_VERSION,
                        "extracted_at": extracted_at,
                        "native_id": str(msg.server_id),
                    },
                    "media_type": "video",
                    "file_ref": file_ref,
                    "sha256": target_sha,
                    "size_bytes": size,
                    "chat_room": chat,
                    "sender_wxid": msg.sender_wxid,
                    "svr_id": msg.server_id,
                    "create_time_epoch": msg.create_time,
                    "video_md5": hit_md5,
                    "is_subject": is_subject,
                }
                if msg.sender_wxid and msg.sender_wxid in alias_map:
                    record["sender_alias"] = alias_map[msg.sender_wxid]

                mf.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
            except Exception as e:
                inc_stat(stats, chat, is_subject, "errors")
                warnings.append(
                    f"failed to process video message {msg.server_id} in {msg.db_file.name}: {e}"
                )

    try:
        staging_dir.rmdir()
    except OSError:
        pass

    subject_video_count = sum(1 for m in master.values() if m.sender_wxid == subject_wxid)
    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")

    write_report(
        report_path,
        person,
        db_paths,
        video_dir,
        mp4_count,
        len(master),
        subject_video_count,
        stats,
        missing_list,
        conflict_list,
        warnings,
        generated_at,
        extracted_at,
    )

    total_copied = sum(s["copied"] for s in stats.values())
    total_already = sum(s["already"] for s in stats.values())
    total_conflict = sum(s["conflict"] for s in stats.values())
    total_missing = sum(s["missing"] for s in stats.values())

    ascii_print(
        f"[ok] copied={total_copied} already={total_already} conflict={total_conflict} "
        f"missing={total_missing} subject_videos={subject_video_count} "
        f"warnings={len(warnings)} -> {manifest_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
