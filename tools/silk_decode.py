#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量解码微信 SILK v3 语音文件为 WAV（备用工具）。

用途:
    本工具用于将导出的微信语音（SILK v3，扩展名可能为 .silk/.aud/.amr）
    批量解码为标准 WAV 文件。

备用状态:
    主聊天记录导出链路已经会生成 MP3，本工具仅作为备用方案，
    服务于只拿到原始 silk 文件的导出场景（例如 WeChatMsg）。

铁律:
    绝不写入、修改或删除 people/<person>/raw/ 目录下的任何内容。
    本工具默认只读取 raw/，输出到 processed/voice_decoded/。
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import tempfile
import wave
from pathlib import Path
from typing import Dict, List, Tuple

try:
    import pilk
except ImportError:
    print("缺少依赖 pilk，请先执行: pip install pilk", file=sys.stderr)
    sys.exit(1)

SILK_MAGIC = b"#!SILK_V3"
WECHAT_SILK_PREFIX = b"\x02"
AMR_MAGIC = b"#!AMR"

# 微信 SILK 语音的采样率固定为 24000 Hz
SAMPLE_RATE = 24000

CANDIDATE_EXTENSIONS = {".silk", ".aud", ".amr"}


def _make_temp_path(prefix: str, suffix: str) -> Path:
    """创建一个已关闭、可被其他进程/库安全读取的临时文件路径。"""
    fd, name = tempfile.mkstemp(prefix=prefix, suffix=suffix)
    os.close(fd)
    return Path(name)


def _make_stripped_silk(silk_path: Path) -> Path:
    """复制原始文件并去掉微信加在 SILK 头前面的 0x02 字节。"""
    tmp_path = _make_temp_path(prefix="silk_strip_", suffix=".silk")
    try:
        with silk_path.open("rb") as src, tmp_path.open("wb") as dst:
            src.seek(1)  # 跳过第一个 0x02 字节
            shutil.copyfileobj(src, dst)
        return tmp_path
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def _make_temp_pcm() -> Path:
    return _make_temp_path(prefix="silk_pcm_", suffix=".pcm")


def _write_wav(pcm_path: Path, wav_path: Path) -> None:
    """把 24000 Hz、单声道、16-bit PCM 数据封装为 WAV。"""
    with pcm_path.open("rb") as pcm, wave.open(str(wav_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        while True:
            chunk = pcm.read(65536)
            if not chunk:
                break
            wav.writeframes(chunk)


def _call_pilk_decode(silk_path: Path, pcm_path: Path) -> None:
    """调用 pilk 解码为裸 PCM；兼容不支持 to_wav 关键字的旧版本。"""
    try:
        pilk.decode(str(silk_path), str(pcm_path), to_wav=False)
    except TypeError:
        pilk.decode(str(silk_path), str(pcm_path))


def _decode_silk_file(silk_path: Path, output_wav: Path, prefixed: bool) -> None:
    """解码单个 SILK 文件并写出 WAV。"""
    output_wav.parent.mkdir(parents=True, exist_ok=True)

    decode_input: Path = silk_path
    temp_silk: Path | None = None
    temp_pcm: Path | None = None

    try:
        if prefixed:
            temp_silk = _make_stripped_silk(silk_path)
            decode_input = temp_silk

        temp_pcm = _make_temp_pcm()
        _call_pilk_decode(decode_input, temp_pcm)

        if not temp_pcm.exists() or temp_pcm.stat().st_size == 0:
            raise RuntimeError("pilk 未生成 PCM 数据")

        _write_wav(temp_pcm, output_wav)
    except Exception:
        # 避免留下半个 WAV 文件，否则后续没有 --force 时会误判为“已存在”。
        try:
            output_wav.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    finally:
        if temp_silk is not None:
            try:
                temp_silk.unlink(missing_ok=True)
            except OSError:
                pass
        if temp_pcm is not None:
            try:
                temp_pcm.unlink(missing_ok=True)
            except OSError:
                pass


def inspect_silk_header(path: Path) -> Tuple[str, str]:
    """检测文件是否为 SILK，返回 (类型, 说明)。

    类型:
        "silk"     -> 直接以 #!SILK_V3 开头
        "prefixed" -> 微信格式，开头为 0x02 + #!SILK_V3
        "not_silk" -> 不是 SILK（例如真实 AMR）
        "error"    -> 读取失败
    """
    try:
        with path.open("rb") as f:
            head = f.read(16)
    except OSError as exc:
        return "error", f"读取失败: {exc}"

    if head.startswith(SILK_MAGIC):
        return "silk", ""

    if head.startswith(WECHAT_SILK_PREFIX + SILK_MAGIC):
        return "prefixed", ""

    if head.startswith(AMR_MAGIC):
        return "not_silk", "真实 AMR 文件"

    return "not_silk", "非 SILK/未知格式"


def collect_candidates(input_dir: Path, failures: List[Tuple[str, str]]) -> List[Path]:
    candidates: List[Path] = []
    try:
        for p in input_dir.rglob("*"):
            try:
                if p.is_file() and p.suffix.lower() in CANDIDATE_EXTENSIONS:
                    candidates.append(p)
            except OSError as exc:
                failures.append((str(p), f"扫描失败: {type(exc).__name__}: {exc}"))
                continue
    except OSError as exc:
        failures.append((str(input_dir), f"扫描目录失败: {type(exc).__name__}: {exc}"))
    return sorted(candidates)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="批量解码微信 SILK v3 语音文件为 WAV（备用工具）"
    )
    parser.add_argument(
        "--person",
        required=True,
        help="人物标识，用于构造默认输入/输出路径",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="项目根目录（默认当前目录）",
    )
    parser.add_argument(
        "--input",
        help="输入目录（默认 people/<person>/raw/wechat）",
    )
    parser.add_argument(
        "--output",
        help="输出目录（默认 people/<person>/processed/voice_decoded）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制重新解码，即使 WAV 已存在",
    )
    args = parser.parse_args()

    person = args.person.strip()
    if not person:
        parser.error("--person 不能为空")
    if not re.fullmatch(r"[a-z0-9_-]+", person):
        print(
            f"错误: --person 只能包含小写字母、数字、下划线和中划线: {person}",
            file=sys.stderr,
        )
        sys.exit(1)

    repo_root = Path(args.repo_root).expanduser()
    repo_root_resolved = repo_root.resolve()

    person_dir = repo_root / "people" / person
    person_dir_resolved = person_dir.resolve()
    expected_person_dir = repo_root_resolved / "people" / person
    if person_dir_resolved != expected_person_dir:
        print(
            f"错误: people/{person} 目录必须是真实目录，不能是符号链接或 junction: {person_dir}",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.input:
        input_dir = Path(args.input).expanduser()
    else:
        input_dir = person_dir_resolved / "raw" / "wechat"

    if args.output:
        output_dir = Path(args.output).expanduser()
    else:
        output_dir = person_dir_resolved / "processed" / "voice_decoded"

    input_dir = input_dir.resolve()
    output_dir = output_dir.resolve()

    # 铁律保护：不允许把输出写到 raw 输入目录里。
    if output_dir.is_relative_to(input_dir):
        print(
            "错误: 输出目录不能在 raw 输入目录内（铁律：绝不修改 raw/）",
            file=sys.stderr,
        )
        sys.exit(1)

    # 铁律保护：不允许把输出写到 people/<person>/raw/ 目录内或其下。
    raw_dir = (person_dir_resolved / "raw").resolve()
    if output_dir.is_relative_to(raw_dir):
        print(
            f"错误: 输出目录不能在 people/{person}/raw/ 目录内（铁律：绝不修改 raw/）",
            file=sys.stderr,
        )
        sys.exit(1)

    if not input_dir.is_dir():
        print(f"错误: 输入目录不存在: {input_dir}", file=sys.stderr)
        sys.exit(1)

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"错误: 无法创建输出目录 {output_dir}: {exc}", file=sys.stderr)
        sys.exit(1)

    failures: List[Tuple[str, str]] = []
    candidates = collect_candidates(input_dir, failures)

    succeeded = 0
    skipped_existing = 0
    non_silk_reasons: Dict[str, List[str]] = {}

    for file_path in candidates:
        try:
            rel_path = file_path.relative_to(input_dir)
            output_wav = output_dir / rel_path.with_suffix(".wav")

            if output_wav.exists() and not args.force:
                skipped_existing += 1
                print(f"跳过(已存在): {output_wav}")
                continue

            kind, reason = inspect_silk_header(file_path)

            if kind == "error":
                failures.append((str(file_path), reason))
                print(f"失败: {file_path}: {reason}", file=sys.stderr)
                continue

            if kind == "not_silk":
                non_silk_reasons.setdefault(reason, []).append(str(file_path))
                print(f"跳过(非silk): {file_path} ({reason})")
                continue

            prefixed = kind == "prefixed"

            try:
                _decode_silk_file(file_path, output_wav, prefixed)
                succeeded += 1
                print(f"成功: {file_path} -> {output_wav}")
            except Exception as exc:
                failures.append((str(file_path), f"{type(exc).__name__}: {exc}"))
                print(f"失败: {file_path}: {exc}", file=sys.stderr)
        except OSError as exc:
            failures.append((str(file_path), f"处理失败: {type(exc).__name__}: {exc}"))
            print(f"失败: {file_path}: {exc}", file=sys.stderr)
            continue

    non_silk_total = sum(len(paths) for paths in non_silk_reasons.values())

    print()
    print("处理完成。")
    print(f"成功: {succeeded}")
    print(f"跳过已存在: {skipped_existing}")
    print(f"非silk跳过: {non_silk_total}")
    for reason, paths in non_silk_reasons.items():
        print(f"  - {reason}: {len(paths)}")
        for path in paths:
            print(f"      {path}")
    print(f"失败: {len(failures)}")
    for path, err in failures:
        print(f"  - {path}: {err}")
    print(f"输出目录: {output_dir}")

    if failures:
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
