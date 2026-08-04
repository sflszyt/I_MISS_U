#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""I_MISS_U 备份健康检查工具（只读审计）。

本脚本只检查 people/<person>/ 下的备份目标是否健康，绝不修改源目录或任何备份目标。
唯一允许写入的是缺失的 backup_targets.json 配置模板，以及 people/<person>/backup_report.md 报告。
原始 raw/ 文件不可再生，必须至少存在 min_targets 个正常备份，且其中至少一个为异地备份。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Set

CONFIG_TEMPLATE = '''{
  "min_targets": 2,
  "scope": "raw",
  "targets": []
}
'''

HASH_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class FileInfo:
    size: int
    mtime: float


@dataclass
class ManifestResult:
    files: dict[str, FileInfo] = field(default_factory=dict)
    errors: int = 0


@dataclass
class TargetResult:
    name: str
    path: str
    offsite: bool
    reachable: bool = True
    missing: list[str] = field(default_factory=list)
    size_mismatch: list[str] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)
    hash_mismatch: list[str] = field(default_factory=list)
    sampled_count: int = 0
    scan_errors: int = 0
    status: str = "FAIL"


def sha256_file(path: Path) -> str:
    """计算文件的 SHA-256，适合大文件流式读取。"""
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(HASH_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def walk_manifest(
    root: Path,
    wanted: Optional[Set[str]] = None,
    skip_paths: Optional[Set[Path]] = None,
) -> ManifestResult:
    """使用 os.scandir 遍历目录，返回 ManifestResult。

    files 为 {相对路径: FileInfo}，errors 为因 OSError 跳过的条目数。
    wanted 不为空时，只保留需要的相对路径，减少目标端内存占用。
    """
    if not root.is_dir():
        return ManifestResult()

    result = ManifestResult()
    stack = [root]

    while stack:
        current = stack.pop()
        try:
            scan_it = os.scandir(current)
        except OSError:
            if current == root:
                raise
            result.errors += 1
            continue

        with scan_it as it:
            for entry in it:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False):
                        p = Path(entry.path)
                        if skip_paths and p in skip_paths:
                            continue
                        rel = p.relative_to(root).as_posix()
                        if wanted is not None and rel not in wanted:
                            continue
                        st = entry.stat(follow_symlinks=False)
                        result.files[rel] = FileInfo(st.st_size, st.st_mtime)
                except OSError:
                    result.errors += 1

    return result


def format_size(size: int) -> str:
    """把字节数格式化为人类可读字符串。"""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.2f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def parse_offsite(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)


def check_target(
    cfg: dict[str, Any],
    source_manifest: dict[str, FileInfo],
    source_root: Path,
    do_hash: bool,
    sample_size: int,
) -> TargetResult:
    name = str(cfg.get("name") or "未命名备份")
    raw_path = str(cfg.get("path") or "")
    if not raw_path:
        raise ValueError(f"备份目标 {name} 缺少 path 字段")

    target_root = Path(raw_path)
    offsite = parse_offsite(cfg.get("offsite", False))
    result = TargetResult(name=name, path=raw_path, offsite=offsite)

    try:
        if not target_root.is_dir():
            result.reachable = False
            result.status = "FAILED"
            return result

        wanted = set(source_manifest.keys())
        target_scan = walk_manifest(target_root, wanted=wanted)
        target_manifest = target_scan.files
        result.scan_errors = target_scan.errors
    except OSError:
        result.reachable = False
        result.status = "FAILED"
        return result

    for rel, src in source_manifest.items():
        dst = target_manifest.get(rel)
        if dst is None:
            result.missing.append(rel)
        else:
            if src.size != dst.size:
                result.size_mismatch.append(rel)
            if src.mtime - dst.mtime > 2.0:
                result.stale.append(rel)

    if do_hash and source_manifest:
        rng = random.Random(0)
        rel_paths = sorted(source_manifest.keys())
        sample_count = max(0, min(sample_size, len(rel_paths)))
        sample = rng.sample(rel_paths, sample_count) if sample_count else []
        result.sampled_count = len(sample)

        for rel in sample:
            src = source_manifest[rel]
            dst = target_manifest.get(rel)
            if dst is None or src.size != dst.size:
                continue
            try:
                src_hash = sha256_file(source_root / rel)
                dst_hash = sha256_file(target_root / rel)
                if src_hash != dst_hash:
                    result.hash_mismatch.append(rel)
            except OSError:
                result.hash_mismatch.append(rel)

    if result.missing or result.size_mismatch or result.hash_mismatch:
        result.status = "FAIL"
    elif result.stale:
        result.status = "WARN"
    else:
        result.status = "OK"

    return result


def run(args: argparse.Namespace) -> int:
    if not re.fullmatch(r"[a-z0-9_-]+", args.person):
        print(
            f"人物名称不合法：{args.person}，仅允许小写字母、数字、下划线和连字符。",
            file=sys.stderr,
        )
        return 1

    repo_root = Path(args.repo_root).resolve()
    person_dir_expected = repo_root / "people" / args.person
    person_dir = person_dir_expected.resolve()
    if person_dir != person_dir_expected:
        print(
            f"人物目录验证失败：{person_dir} 不是 {person_dir_expected}",
            file=sys.stderr,
        )
        return 1

    config_path = person_dir / "backup_targets.json"
    report_path = person_dir / "backup_report.md"

    if not config_path.exists():
        person_dir.mkdir(parents=True, exist_ok=True)
        config_path.write_text(CONFIG_TEMPLATE, encoding="utf-8")
        print(f"未找到备份配置文件：{config_path}")
        print("已创建配置模板。请编辑该文件，将实际备份目标填入 targets 数组。")
        print("每个目标至少包含 name、path、offsite 字段；min_targets 表示最低正常备份数。")
        return 1

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"备份配置文件不是有效的 JSON：{exc}", file=sys.stderr)
        return 1

    try:
        min_targets = int(config.get("min_targets", 2))
        scope = str(config.get("scope", "raw"))
        if scope not in ("raw", "all"):
            raise ValueError("scope 必须为 'raw' 或 'all'")

        raw_targets = config.get("targets", [])
        if not isinstance(raw_targets, list):
            raise ValueError("targets 必须是数组")
        targets = []
        for item in raw_targets:
            if not isinstance(item, dict):
                raise ValueError("targets 中的每个元素必须是对象")
            targets.append(item)
    except ValueError as exc:
        print(f"备份配置文件内容错误：{exc}", file=sys.stderr)
        return 1

    if scope == "raw":
        scope_dir = person_dir / "raw"
    else:
        scope_dir = person_dir

    skip_paths = {config_path, report_path}
    source_scan = walk_manifest(scope_dir, wanted=None, skip_paths=skip_paths)
    source_manifest = source_scan.files
    source_error_count = source_scan.errors

    results: list[TargetResult] = []
    for target_cfg in targets:
        try:
            results.append(
                check_target(
                    target_cfg,
                    source_manifest,
                    scope_dir,
                    args.hash,
                    args.sample,
                )
            )
        except ValueError as exc:
            print(f"配置错误：{exc}", file=sys.stderr)
            return 1

    count_ok = sum(1 for r in results if r.status == "OK")
    offsite_ok = sum(1 for r in results if r.status == "OK" and r.offsite)

    if not targets:
        verdict = "FAIL"
        summary = "备份目标列表为空，没有可用的备份。"
    elif count_ok >= min_targets and offsite_ok >= 1:
        verdict = "PASS"
        summary = "所有备份目标健康，且满足最低数量与异地备份要求。"
    elif count_ok >= min_targets:
        verdict = "WARN"
        summary = "正常备份数量达标，但没有一个异地备份处于正常状态。"
    else:
        verdict = "FAIL"
        summary = (
            f"正常备份不足：需要至少 {min_targets} 个且至少 1 个异地，"
            f"当前正常 {count_ok} 个，异地正常 {offsite_ok} 个。"
        )

    missing_all = sorted({rel for r in results for rel in r.missing})
    hashed_mismatch_all = sorted({rel for r in results for rel in r.hash_mismatch})
    unreachable_names = [r.name for r in results if not r.reachable]
    total_size = sum(f.size for f in source_manifest.values())
    size_mismatch_count = sum(len(r.size_mismatch) for r in results)
    hash_mismatch_count = len(hashed_mismatch_all)
    stale_count = sum(len(r.stale) for r in results)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines: list[str] = []
    lines.append("# 备份检查报告")
    lines.append("")
    lines.append(f"- 人物：{args.person}")
    lines.append(f"- 源目录：{scope_dir}")
    lines.append(f"- 检查时间：{now}")
    lines.append(f"- 结论：**{verdict}** — {summary}")
    lines.append("")
    lines.append("## 源清单统计")
    lines.append("")
    lines.append(f"- 文件数：{len(source_manifest)}")
    lines.append(f"- 总大小：{total_size} 字节（{format_size(total_size)}）")
    lines.append(f"- 扫描错误数：{source_error_count}（已跳过对应条目）")
    lines.append("")
    lines.append("## 备份目标")
    lines.append("")
    lines.append("| 名称 | 异地 | 状态 | 错误数 | 缺失数 | 不一致数 | 陈旧数 | 抽样哈希结果 |")
    lines.append("|---|---|---|---|---|---|---|---|")

    for r in results:
        name = r.name.replace("|", "\\|")
        offsite = "是" if r.offsite else "否"
        if not r.reachable:
            missing = "—"
            inconsistent = "—"
            stale = "—"
            error_text = "—"
            hash_text = "不可达"
        else:
            missing = str(len(r.missing))
            inconsistent = str(len(r.size_mismatch) + len(r.hash_mismatch))
            stale = str(len(r.stale))
            error_text = str(r.scan_errors)
            if args.hash:
                hash_text = f"{r.sampled_count} 个抽样 / {len(r.hash_mismatch)} 个不一致"
            else:
                hash_text = "未启用"
        lines.append(f"| {name} | {offsite} | {r.status} | {error_text} | {missing} | {inconsistent} | {stale} | {hash_text} |")

    lines.append("")
    lines.append("## 缺失文件")
    lines.append("")
    if missing_all:
        shown = missing_all[:50]
        for rel in shown:
            lines.append(f"- `{rel}`")
        remaining = len(missing_all) - len(shown)
        if remaining > 0:
            lines.append(f"- …还有 {remaining} 个")
    else:
        lines.append("无")
    lines.append("")

    lines.append("## 抽样哈希不一致文件")
    lines.append("")
    if not args.hash:
        lines.append("未启用哈希校验。")
    elif hashed_mismatch_all:
        for r in results:
            for rel in r.hash_mismatch:
                lines.append(f"- {r.name}：`{rel}`")
    else:
        lines.append("无。")
    lines.append("")

    lines.append("## 建议行动")
    lines.append("")
    suggestions: list[str] = []

    if not targets:
        suggestions.append("备份目标列表为空，请先在 backup_targets.json 中配置至少一个备份目标。")
    if count_ok < min_targets:
        suggestions.append(f"当前只有 {count_ok} 个正常备份，低于最低要求 {min_targets} 个，请立即补齐。")
    if count_ok >= min_targets and offsite_ok == 0:
        suggestions.append("请添加或修复一个 offsite=true 的异地备份目标，并确保其处于正常状态。")
    if unreachable_names:
        suggestions.append(f"以下备份目标不可达：{', '.join(unreachable_names)}，请检查磁盘、网络或路径。")
    if missing_all:
        suggestions.append(f"有 {len(missing_all)} 个源文件未出现在备份目标中，请重新复制。")
    if size_mismatch_count:
        suggestions.append(f"有 {size_mismatch_count} 个文件大小不一致，请检查备份是否损坏。")
    if hash_mismatch_count:
        suggestions.append(f"有 {hash_mismatch_count} 个抽样文件哈希不一致，请检查备份数据是否损坏。")
    if stale_count:
        suggestions.append(f"有 {stale_count} 个备份文件版本陈旧，请尽快执行增量备份。")
    if verdict == "PASS":
        suggestions.append("当前备份状态良好，请继续保持定期离线备份。")

    if not suggestions:
        suggestions.append("无需处理。")

    lines.extend(f"- {s}" for s in suggestions)
    lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[{verdict}] {summary}")
    print(f"报告已写入：{report_path}")

    if verdict == "PASS":
        return 0
    if verdict == "WARN":
        return 2
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="backup_check.py",
        description="检查 I_MISS_U 人物的离线备份健康状态（只读审计，不写源/备份目标）。",
    )
    parser.add_argument("--person", required=True, help="人物目录名，例如 mama")
    parser.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parent.parent),
        help="项目根目录，默认是 tools/ 的上一级目录",
    )
    parser.add_argument(
        "--hash",
        action="store_true",
        help="额外对抽样文件计算 SHA-256 校验",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=20,
        help="每个目标抽样哈希的文件数量上限（默认 20，仅在 --hash 时生效）",
    )
    args = parser.parse_args()

    try:
        return run(args)
    except Exception as exc:
        print(f"发生致命错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
