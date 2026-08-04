#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""I_MISS_U 媒体导入工具（M0）。

扫描 people/<person>/raw/photos 和 people/<person>/raw/videos，
提取媒体元数据，生成 normalized/media_items.jsonl 和 media_report.md。

铁律：绝不写入/修改/重命名/删除 raw/ 下任何内容。所有输出写入 normalized/。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

try:
    from PIL import Image
    _PILLOW_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    Image = None  # type: ignore
    _PILLOW_AVAILABLE = False

IMAGE_EXTS = {
    ".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif",
    ".bmp", ".tiff", ".webp",
}
VIDEO_EXTS = {
    ".mp4", ".mov", ".avi", ".mkv", ".wmv", ".m4v", ".3gp", ".mts",
}
AUDIO_EXTS = {
    ".wav", ".mp3", ".m4a", ".aac", ".flac", ".amr",
}

LOCAL_TZ = datetime.now().astimezone().tzinfo
FFPROBE_PATH = shutil.which("ffprobe")

_PILLOW_WARNED = False
_FFPROBE_WARNED = False


@dataclass
class ScannedFile:
    path: Path
    rel_path: str
    media_type: str
    source: str


def human_size(num: int) -> str:
    """将字节数转换为人类可读的字符串。"""
    num = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(num)} B"
            return f"{num:.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} TB"


def classify_ext(ext: str) -> Optional[str]:
    """根据扩展名返回 media_type；不支持的返回 None。"""
    if ext in IMAGE_EXTS:
        return "photo"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "audio"
    return None


def gather_media_files(person_dir: Path) -> list[ScannedFile]:
    """递归扫描 raw/photos 和 raw/videos，返回媒体文件列表。"""
    scanned: list[ScannedFile] = []
    photos_dir = person_dir / "raw" / "photos"
    videos_dir = person_dir / "raw" / "videos"

    for input_dir in (photos_dir, videos_dir):
        if not input_dir.is_dir():
            continue

        for p in sorted(input_dir.rglob("*")):
            try:
                if p.is_dir():
                    continue
            except OSError:
                continue

            try:
                rel = p.relative_to(person_dir)
            except ValueError:
                continue

            parts = rel.parts
            if any(part.startswith(".") for part in parts):
                continue
            if p.name == "README.md" or p.name == ".gitkeep":
                continue

            ext = p.suffix.lower()
            media_type = classify_ext(ext)
            if media_type is None:
                continue

            source = "photos" if len(parts) > 1 and parts[1] == "photos" else "videos"
            scanned.append(
                ScannedFile(
                    path=p,
                    rel_path=rel.as_posix(),
                    media_type=media_type,
                    source=source,
                )
            )

    return sorted(scanned, key=lambda x: x.rel_path)


def sha256_file(path: Path) -> str:
    """流式计算文件的 SHA-256（1MB 分块）。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _as_text(value: Any) -> str:
    """将可能的 bytes 安全转为 str。"""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def _to_float(value: Any) -> Optional[float]:
    """将 EXIF 中的有理数/元组/数值转为浮点数。"""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    if hasattr(value, "numerator") and hasattr(value, "denominator"):
        try:
            return float(value.numerator) / float(value.denominator)
        except Exception:
            return None
    if isinstance(value, tuple):
        if len(value) == 3:
            d = _to_float(value[0])
            m = _to_float(value[1])
            s = _to_float(value[2])
            if d is not None and m is not None and s is not None:
                return d + m / 60.0 + s / 3600.0
            return None
        if len(value) == 2:
            num = _to_float(value[0])
            den = _to_float(value[1])
            if num is not None and den:
                return num / den
            return None
        if len(value) == 1:
            return _to_float(value[0])
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coordinate_to_decimal(value: Any, ref: Any) -> Optional[float]:
    """将 GPS 度分秒/有理数转十进制，并根据 N/S/E/W 取正负。"""
    if value is None:
        return None
    deg = _to_float(value)
    if deg is None:
        return None
    if ref is not None:
        ref_text = _as_text(ref).strip().upper()
        if ref_text in ("S", "W"):
            deg = -deg
    return deg


def _extract_gps(exif: Any) -> Optional[dict[str, float]]:
    """从 EXIF 中提取 GPS 坐标。"""
    try:
        if hasattr(exif, "get_ifd"):
            gps_ifd = exif.get_ifd(34853)
        else:
            gps_ifd = exif.get(34853)
    except Exception:
        return None

    if not gps_ifd:
        return None

    lat = _coordinate_to_decimal(gps_ifd.get(2), gps_ifd.get(1))
    lon = _coordinate_to_decimal(gps_ifd.get(4), gps_ifd.get(3))
    if lat is None or lon is None:
        return None
    return {"lat": lat, "lon": lon}


def read_image_info(path: Path) -> dict[str, Any]:
    """读取图像尺寸与 EXIF 信息；失败时返回空 dict。"""
    global _PILLOW_WARNED

    if not _PILLOW_AVAILABLE:
        if not _PILLOW_WARNED:
            print("警告: 未安装 Pillow，图像尺寸和 EXIF 信息将被跳过。", file=sys.stderr)
            _PILLOW_WARNED = True
        return {}

    try:
        with Image.open(path) as img:  # type: ignore[name-defined]
            width, height = img.size
            exif_obj: dict[str, Any] = {}

            exif = img.getexif()
            if exif is None:
                exif = {}

            raw_dt = exif.get(36867) or exif.get(306)
            if raw_dt:
                raw_dt = _as_text(raw_dt).strip().replace("\x00", "")
                if raw_dt:
                    exif_obj["datetime_original"] = raw_dt

            make = exif.get(271)
            if make:
                make = _as_text(make).strip().replace("\x00", "")
                if make:
                    exif_obj["camera_make"] = make

            model = exif.get(272)
            if model:
                model = _as_text(model).strip().replace("\x00", "")
                if model:
                    exif_obj["camera_model"] = model

            gps = _extract_gps(exif)
            if gps:
                exif_obj["gps"] = gps

            return {"width": width, "height": height, "exif": exif_obj}
    except Exception:
        return {}


def parse_ffprobe_time(value: Any) -> Optional[datetime]:
    """解析 ffprobe 返回的 creation_time。"""
    if isinstance(value, bytes):
        value = value.decode("utf-8", "replace")
    if not value:
        return None

    s = str(value).strip()
    if not s:
        return None

    if s.endswith("Z"):
        s = s[:-1] + "+00:00"

    if " " in s and "T" not in s:
        s = s.replace(" ", "T", 1)

    if "." in s:
        head, frac = s.split(".", 1)
        tz = ""
        for i, ch in enumerate(frac):
            if ch in ("+", "-") and i > 0:
                tz = frac[i:]
                frac = frac[:i]
                break
        frac = (frac + "000000")[:6]
        s = head + "." + frac + tz

    try:
        return datetime.fromisoformat(s)
    except ValueError:
        try:
            return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return None


def probe_media(path: Path) -> dict[str, Any]:
    """使用 ffprobe 获取视频/音频元数据。"""
    global _FFPROBE_WARNED

    if not FFPROBE_PATH:
        if not _FFPROBE_WARNED:
            print("警告: 未找到 ffprobe，视频/音频时长、宽高等元数据将被跳过。", file=sys.stderr)
            _FFPROBE_WARNED = True
        return {}

    try:
        result = subprocess.run(
            [
                FFPROBE_PATH,
                "-v", "error",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                str(path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        if result.returncode != 0:
            return {}
        data = json.loads(result.stdout)
    except Exception:
        return {}

    info: dict[str, Any] = {}
    fmt = data.get("format") or {}
    duration_str = fmt.get("duration")
    creation_time = (fmt.get("tags") or {}).get("creation_time")

    width: Optional[int] = None
    height: Optional[int] = None

    for stream in data.get("streams") or []:
        if stream.get("codec_type") == "video":
            if width is None:
                try:
                    width = int(stream.get("width") or stream.get("coded_width") or 0)
                except (TypeError, ValueError):
                    width = None
            if height is None:
                try:
                    height = int(stream.get("height") or stream.get("coded_height") or 0)
                except (TypeError, ValueError):
                    height = None
            if duration_str is None and stream.get("duration"):
                duration_str = stream.get("duration")
        elif stream.get("codec_type") == "audio":
            if duration_str is None and stream.get("duration"):
                duration_str = stream.get("duration")

        if creation_time is None:
            creation_time = (stream.get("tags") or {}).get("creation_time")

    if duration_str:
        try:
            info["duration_ms"] = int(round(float(duration_str) * 1000))
        except (TypeError, ValueError):
            pass

    if width is not None:
        info["width"] = width
    if height is not None:
        info["height"] = height
    if creation_time:
        info["creation_time"] = creation_time

    return info


def parse_exif_datetime(value: Any) -> Optional[datetime]:
    """解析 EXIF 日期时间字符串，按本地时区解释。"""
    if not value:
        return None
    s = _as_text(value).strip().replace("\x00", "")
    if not s:
        return None

    for fmt in (
        "%Y:%m:%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y:%m:%d %H:%M:%S.%f",
    ):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=LOCAL_TZ)
        except ValueError:
            continue
    return None


def resolve_timestamp(
    exif_datetime: Optional[str],
    ffprobe_creation_time: Optional[str],
    mtime: float,
) -> tuple[str, str]:
    """按顺序解析时间戳：EXIF > ffprobe > mtime。"""
    if exif_datetime:
        dt = parse_exif_datetime(exif_datetime)
        if dt is not None:
            return dt.isoformat(), "exact"

    if ffprobe_creation_time:
        dt = parse_ffprobe_time(ffprobe_creation_time)
        if dt is not None:
            return dt.astimezone().isoformat(), "exact"

    return datetime.fromtimestamp(mtime, tz=LOCAL_TZ).isoformat(), "unknown"


def build_record(
    sf: ScannedFile,
    file_hash: str,
    size: int,
    mtime: float,
    image_meta: dict[str, Any],
    probe: dict[str, Any],
    person: str,
    extracted_at: str,
) -> dict[str, Any]:
    """构造 UIF media_item 记录。"""
    timestamp, precision = resolve_timestamp(
        (image_meta.get("exif") or {}).get("datetime_original"),
        probe.get("creation_time"),
        mtime,
    )

    record: dict[str, Any] = {
        "record_id": hashlib.sha256(
            f"{sf.rel_path}|{file_hash}".encode("utf-8")
        ).hexdigest(),
        "record_type": "media_item",
        "person": person,
        "viewpoint": "justin",
        "source": sf.source,
        "tier": 2,
        "provenance": {
            "source_file": sf.rel_path,
            "parser": "ingest_media",
            "parser_version": "0.1.0",
            "extracted_at": extracted_at,
        },
        "media_type": sf.media_type,
        "file_ref": sf.rel_path,
        "sha256": file_hash,
        "size_bytes": size,
        "timestamp": timestamp,
        "timestamp_precision": precision,
    }

    if image_meta.get("width") is not None:
        record["width"] = image_meta["width"]
    if image_meta.get("height") is not None:
        record["height"] = image_meta["height"]
    if probe.get("width") is not None:
        record["width"] = probe["width"]
    if probe.get("height") is not None:
        record["height"] = probe["height"]
    if probe.get("duration_ms") is not None:
        record["duration_ms"] = probe["duration_ms"]

    if image_meta.get("exif"):
        record["exif"] = image_meta["exif"]

    return record


def validate_records(records: list[dict[str, Any]], repo_root: Path) -> bool:
    """使用 schema/uif.schema.json 校验记录；失败时报告前 5 条并返回 False。"""
    try:
        import jsonschema
    except ImportError:
        print("错误: 未安装 jsonschema 库，无法进行 schema 校验（可用 --no-validate 跳过）。", file=sys.stderr)
        return False

    schema_path = repo_root / "schema" / "uif.schema.json"
    if not schema_path.is_file():
        print(f"错误: 找不到 schema 文件 {schema_path}（可用 --no-validate 跳过）。", file=sys.stderr)
        return False

    try:
        with open(schema_path, encoding="utf-8") as f:
            schema = json.load(f)
        jsonschema.Draft202012Validator.check_schema(schema)
    except Exception as e:
        print(f"错误: schema 无效或无法读取：{e}（可用 --no-validate 跳过）。", file=sys.stderr)
        return False

    format_checker = jsonschema.Draft202012Validator.FORMAT_CHECKER
    validator = jsonschema.Draft202012Validator(
        schema,
        format_checker=format_checker,
    )

    errors: list[str] = []

    def check_datetime(value: Any, rec: dict[str, Any], field_path: str) -> None:
        if not isinstance(value, str):
            return
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            errors.append(
                f"{rec.get('record_id', '<unknown>')}: {field_path} 不是合法的 date-time 格式：{value!r}"
            )
            return
        if dt.tzinfo is None:
            errors.append(
                f"{rec.get('record_id', '<unknown>')}: {field_path} 缺少时区信息（RFC3339 date-time 必须含时区）：{value!r}"
            )

    use_manual_datetime_check = "date-time" not in getattr(format_checker, "checkers", {})

    try:
        for rec in records:
            for err in sorted(
                validator.iter_errors(rec),
                key=lambda e: [str(p) for p in e.path],
            ):
                errors.append(f"{rec.get('record_id', '<unknown>')}: {err.message}")

            if use_manual_datetime_check:
                timestamp = rec.get("timestamp")
                if timestamp is not None:
                    check_datetime(timestamp, rec, "timestamp")

                provenance = rec.get("provenance")
                if isinstance(provenance, dict):
                    extracted_at = provenance.get("extracted_at")
                    if extracted_at is not None:
                        check_datetime(extracted_at, rec, "provenance.extracted_at")
    except Exception as exc:
        print(f"错误: schema 校验过程中发生异常：{exc}", file=sys.stderr)
        return False

    if errors:
        print(f"错误: schema 校验失败，共 {len(errors)} 条。前 5 条：", file=sys.stderr)
        for err in errors[:5]:
            print(err, file=sys.stderr)
        return False

    return True


def build_report(
    person: str,
    records: list[dict[str, Any]],
    duplicates: dict[str, list[str]],
    zero_bytes: list[str],
    unreadable: list[tuple[str, str]],
) -> str:
    """生成中文 media_report.md 内容。"""
    photo_count = sum(1 for r in records if r["media_type"] == "photo")
    video_count = sum(1 for r in records if r["media_type"] == "video")
    audio_count = sum(1 for r in records if r["media_type"] == "audio")
    total_size = sum(r["size_bytes"] for r in records)
    unknown_ts_count = sum(1 for r in records if r["timestamp_precision"] != "exact")

    exact_dts: list[datetime] = []
    for r in records:
        if r["timestamp_precision"] == "exact":
            try:
                exact_dts.append(datetime.fromisoformat(r["timestamp"]))
            except (ValueError, KeyError):
                pass

    if exact_dts:
        date_range = f"{min(exact_dts).isoformat()} ～ {max(exact_dts).isoformat()}"
    else:
        date_range = "无"

    dup_groups = {h: sorted(set(paths)) for h, paths in duplicates.items() if len(paths) > 1}

    lines: list[str] = []
    lines.append(f"# 媒体清单报告 — {person}")
    lines.append("")
    lines.append(f"- 生成时间：{datetime.now().astimezone().isoformat()}")
    lines.append("")

    lines.append("## 总览")
    lines.append("")
    lines.append("| 媒体类型 | 文件数 | 总大小 |")
    lines.append("| --- | ---: | ---: |")
    lines.append(f"| 照片 | {photo_count} | {human_size(sum(r['size_bytes'] for r in records if r['media_type'] == 'photo'))} |")
    lines.append(f"| 视频 | {video_count} | {human_size(sum(r['size_bytes'] for r in records if r['media_type'] == 'video'))} |")
    lines.append(f"| 音频 | {audio_count} | {human_size(sum(r['size_bytes'] for r in records if r['media_type'] == 'audio'))} |")
    lines.append(f"| 总计 | {len(records)} | {human_size(total_size)} |")
    lines.append("")
    lines.append(f"- 精确时间戳日期范围：{date_range}")
    lines.append(f"- 无精确时间戳文件数：{unknown_ts_count}")
    lines.append("")

    lines.append("## 重复文件清单")
    lines.append("")
    if dup_groups:
        for h, paths in sorted(dup_groups.items()):
            lines.append(f"- 哈希 `{h}`")
            for p in paths:
                lines.append(f"  - {p}")
    else:
        lines.append("无重复文件。")
    lines.append("")

    lines.append("## 疑似问题")
    lines.append("")
    lines.append("### 0 字节文件")
    if zero_bytes:
        for p in sorted(set(zero_bytes)):
            lines.append(f"- {p}")
    else:
        lines.append("无。")
    lines.append("")
    lines.append("### 不可读文件")
    if unreadable:
        for p, reason in unreadable:
            lines.append(f"- {p}（{reason}）")
    else:
        lines.append("无。")
    lines.append("")

    lines.append("> 注意：raw/ 目录需要两份离线备份！")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="扫描原始照片/视频，生成 UIF 媒体清单和中文报告。",
        epilog="示例：python tools/ingest_media.py --person mama",
    )
    parser.add_argument("--person", required=True, help="人物目录名，例如 mama")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(), help="仓库根目录（默认当前目录）")
    parser.add_argument("--no-validate", action="store_true", help="跳过 JSON Schema 校验")
    args = parser.parse_args()

    try:
        repo_root: Path = args.repo_root.resolve()

        person: str = args.person
        if not re.fullmatch(r"[a-z0-9_-]+", person):
            print(
                f"错误: --person 参数无效：{person!r}（只允许小写字母、数字、下划线和连字符）",
                file=sys.stderr,
            )
            return 1

        person_dir = repo_root / "people" / person
        if not person_dir.is_dir():
            print(f"错误: 人物目录不存在：{person_dir}", file=sys.stderr)
            return 1

        resolved_person_dir = person_dir.resolve()
        if resolved_person_dir != person_dir:
            print(
                f"错误: 人物目录解析后不在预期位置：{resolved_person_dir}（预期 {person_dir}）",
                file=sys.stderr,
            )
            return 1

        person_dir = resolved_person_dir

        normalized_dir = person_dir / "normalized"
        raw_dir = person_dir / "raw"
        raw_resolved = raw_dir.resolve()
        normalized_resolved = normalized_dir.resolve()

        if (
            normalized_resolved == person_dir
            or not normalized_resolved.is_relative_to(person_dir)
            or normalized_resolved.is_relative_to(raw_resolved)
        ):
            print(
                f"错误: normalized 目录位置非法：{normalized_resolved}",
                file=sys.stderr,
            )
            return 1

        normalized_dir.mkdir(parents=True, exist_ok=True)

        scanned_files = gather_media_files(person_dir)

        extracted_at = datetime.now().astimezone().isoformat()
        records: list[dict[str, Any]] = []
        duplicates: dict[str, list[str]] = defaultdict(list)
        unreadable: list[tuple[str, str]] = []
        zero_byte_files: list[str] = []

        for sf in scanned_files:
            try:
                st = sf.path.stat()
            except Exception as exc:
                unreadable.append((sf.rel_path, str(exc)))
                continue

            size = st.st_size
            mtime = st.st_mtime

            if size == 0:
                zero_byte_files.append(sf.rel_path)

            try:
                file_hash = sha256_file(sf.path)
            except Exception as exc:
                unreadable.append((sf.rel_path, str(exc)))
                continue

            duplicates[file_hash].append(sf.rel_path)

            image_meta: dict[str, Any] = {}
            probe: dict[str, Any] = {}

            if sf.media_type == "photo":
                image_meta = read_image_info(sf.path)
            else:
                probe = probe_media(sf.path)

            record = build_record(
                sf,
                file_hash,
                size,
                mtime,
                image_meta,
                probe,
                person,
                extracted_at,
            )
            records.append(record)

        if not args.no_validate:
            if not validate_records(records, repo_root):
                return 1

        jsonl_path = normalized_dir / "media_items.jsonl"
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")

        report_path = normalized_dir / "media_report.md"
        report = build_report(
            person,
            records,
            dict(duplicates),
            zero_byte_files,
            unreadable,
        )
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)

        dup_groups = {h: paths for h, paths in duplicates.items() if len(paths) > 1}

        print("扫描完成：")
        print(f"  照片: {sum(1 for r in records if r['media_type'] == 'photo')} 个")
        print(f"  视频: {sum(1 for r in records if r['media_type'] == 'video')} 个")
        print(f"  音频: {sum(1 for r in records if r['media_type'] == 'audio')} 个")
        print(f"  无精确时间戳: {sum(1 for r in records if r['timestamp_precision'] != 'exact')} 个")
        print(f"  重复文件: {len(dup_groups)} 组")
        print(f"  不可读文件: {len(unreadable)} 个")
        print(f"报告: {report_path}")

        return 2 if unreadable else 0

    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
