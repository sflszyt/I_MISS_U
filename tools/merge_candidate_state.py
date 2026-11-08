# -*- coding: utf-8 -*-
"""Merge freshly extracted memory candidates with previously gate-decided state."""

import argparse
import copy
import hashlib
import json
import os
import re
import sys
from pathlib import Path

try:
    from .memory_evidence import (dataset_fingerprint, evidence_revision, decision_is_current,
                                  validate_legacy_freeze, DECISION_FIELDS, preflight_outputs)
except ImportError:
    from memory_evidence import (dataset_fingerprint, evidence_revision, decision_is_current,
                                 validate_legacy_freeze, DECISION_FIELDS, preflight_outputs)

PERSON_RE = re.compile(r"^[a-z0-9_-]{1,64}$")


def repo_root() -> Path:
    """返回本仓库根目录（本文件位于 tools/ 下）。"""
    return Path(__file__).resolve().parent.parent


def path_is_within(child: Path, parent: Path) -> bool:
    """判断 child 是否位于 parent 目录子树内。"""
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def content_sig(rec: dict) -> str:
    """计算卡片用户可见内容（title/excerpts）的 sha256 签名。"""
    if rec.get('schema_version') == 2:
        base = copy.deepcopy(rec)
        base.pop('user_title', None)
        base.pop('user_note', None)
        return evidence_revision(base)
    obj = {k: v for k, v in rec.items() if k not in
           (*DECISION_FIELDS, 'previous_versions', 'carried_forward', 'content_changed')}
    data = json.dumps(obj, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def is_decided(rec: dict) -> bool:
    """判断记录是否为已裁决状态。"""
    return rec.get("status") in ("confirmed", "rejected")


def load_jsonl_strict(path: Path) -> list:
    """严格读取 JSONL 文件，损坏或重复 id 直接报错退出。"""
    records = []
    seen_ids = set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    print(f"[error] {path.name} 第 {line_no} 行非法")
                    sys.exit(2)
                if not isinstance(rec, dict):
                    print(f"[error] {path.name} 第 {line_no} 行非法")
                    sys.exit(2)
                cid = rec.get("candidate_id")
                if not isinstance(cid, str) or not cid.strip():
                    print(f"[error] {path.name} 第 {line_no} 行非法")
                    sys.exit(2)
                if cid in seen_ids:
                    print(f"[error] {path.name} 内 candidate_id 重复: {cid}")
                    sys.exit(2)
                seen_ids.add(cid)
                records.append(rec)
    except OSError as e:
        print(f"[error] 读取失败: {e}")
        sys.exit(2)
    return records


def merge_candidates(old_list: list, new_list: list) -> tuple:
    """合并新旧候选列表，返回 (merged, stats)。纯函数，不做 IO。"""
    versions = {r.get('schema_version', 1) for r in old_list + new_list}
    if len(versions) > 1:
        raise ValueError('cannot merge legacy and v2')
    for records in (old_list, new_list):
        if records:
            dataset_fingerprint(records, legacy=versions == {1})
    if versions == {2} and old_list and new_list:
        if (old_list[0]['person'], old_list[0]['relationship_id']) != (new_list[0]['person'], new_list[0]['relationship_id']):
            raise ValueError('merge scope mismatch')
    old_by_id = {rec["candidate_id"]: rec for rec in old_list}
    new_by_id = {rec["candidate_id"]: rec for rec in new_list}

    merged = []
    stats = {
        "confirmed": 0,
        "rejected": 0,
        "content_changed": 0,
        "new_pending": 0,
        "carried_forward": 0,
        "dropped_pending": 0,
    }

    # 规则 1-3：遍历 new 文件
    for rec in new_list:
        cid = rec["candidate_id"]
        old_rec = old_by_id.get(cid)
        # 已记录的历史版本不能以一次旧提取结果覆盖较新的证据。
        history = list(old_rec.get('previous_versions', [])) if old_rec else []
        seen_historical = False
        while history:
            prior = history.pop()
            if content_sig(prior) == content_sig(rec):
                seen_historical = True
                break
            history.extend(prior.get('previous_versions', []))
        if old_rec is not None and seen_historical and content_sig(old_rec) != content_sig(rec):
            out = copy.deepcopy(old_rec)
            if out.get('status') == 'confirmed' and (versions != {2} or decision_is_current(out)):
                stats['confirmed'] += 1
            elif out.get('status') == 'rejected' and (versions != {2} or decision_is_current(out)):
                stats['rejected'] += 1
            else:
                for field in DECISION_FIELDS:
                    out.pop(field, None)
                out['status'] = 'pending'
                if versions == {2}:
                    out['evidence_revision'] = evidence_revision(out)
                stats['new_pending'] += 1
            merged.append(out)
            continue
        if (old_rec is not None and is_decided(old_rec)
                and (versions != {2} or decision_is_current(old_rec))
                and content_sig(old_rec) == content_sig(rec)):
            out = copy.deepcopy(rec)
            # 剔除可能残留的合并标志字段（幂等性：content_changed 每轮按签名重算）
            out.pop("carried_forward", None)
            out.pop("content_changed", None)
            # 覆盖裁决字段
            for field in DECISION_FIELDS:
                out.pop(field, None)
                if field in old_rec:
                    out[field] = copy.deepcopy(old_rec[field])
            if versions == {2}:
                out['evidence_revision'] = evidence_revision(out)
            if 'previous_versions' in old_rec:
                out['previous_versions'] = copy.deepcopy(old_rec['previous_versions'])
            # 内容变更检测
            if content_sig(old_rec) != content_sig(rec):
                out["content_changed"] = True
                stats["content_changed"] += 1
            if out.get("status") == "confirmed":
                stats["confirmed"] += 1
            else:
                stats["rejected"] += 1
            merged.append(out)
        else:
            out = copy.deepcopy(rec)
            for field in DECISION_FIELDS:
                out.pop(field, None)
            out['status'] = 'pending'
            out.pop('previous_versions', None)
            if old_rec is not None:
                out['previous_versions'] = [copy.deepcopy(old_rec)]
                stats['content_changed'] += 1
            if versions == {2}:
                out['evidence_revision'] = evidence_revision(out)
            out.pop("carried_forward", None)
            out.pop("content_changed", None)
            stats["new_pending"] += 1
            merged.append(out)

    # 规则 4-5：old 中不在 new 里的记录
    carried = []
    for rec in old_list:
        cid = rec["candidate_id"]
        if cid in new_by_id:
            continue
        if is_decided(rec) and (versions != {2} or decision_is_current(rec)):
            out = copy.deepcopy(rec)
            out["carried_forward"] = True
            if out.get("status") == "confirmed":
                stats["confirmed"] += 1
            else:
                stats["rejected"] += 1
            carried.append(out)
            stats["carried_forward"] += 1
        else:
            stats["dropped_pending"] += 1

    # carried_forward 按 (date, candidate_id) 升序排序
    carried.sort(key=lambda r: (r.get("date", "") or "", r["candidate_id"]))
    merged.extend(carried)
    if versions == {2} and any(is_decided(r) and not decision_is_current(r) for r in merged):
        raise ValueError('merged decision does not match evidence revision')

    # 计数自检：总数 = confirmed + rejected + new_pending（carried 计入前两者）
    total = len(merged)
    expected = stats["confirmed"] + stats["rejected"] + stats["new_pending"]
    if total != expected:
        print(f"[error] 计数自检失败")
        return None, stats

    return merged, stats


def write_atomic(path: Path, records: list) -> None:
    """原子写入 JSONL 文件。"""
    part_path = path.with_suffix(path.suffix + ".part")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(part_path, "w", encoding="utf-8", newline="\n") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        os.replace(part_path, path)
    except OSError as e:
        print(f"[error] 写入失败: {e}")
        if part_path.exists():
            try:
                part_path.unlink()
            except OSError:
                pass
        sys.exit(1)


def build_report(stats: dict, old_path: Path, new_path: Path, out_path: Path,
                 old_count: int, new_count: int, old_confirmed: int,
                 old_rejected: int, old_pending: int) -> list:
    """构建报告文本行列表。"""
    lines = [
        f"[info] 旧文件: {old_path}（{old_count} 条，confirmed={old_confirmed} rejected={old_rejected} 未裁决={old_pending}）",
        f"[info] 新文件: {new_path}（{new_count} 条）",
        f"[info] 合并结果: {stats['confirmed'] + stats['rejected'] + stats['new_pending']} 条 → {out_path}",
        f"[info]   裁决保留: confirmed={stats['confirmed']} rejected={stats['rejected']}",
        f"[info]   其中内容已更新(content_changed): {stats['content_changed']}",
        f"[info]   新卡(pending): {stats['new_pending']}",
        f"[info]   仅存旧档结转(carried_forward): {stats['carried_forward']}",
        f"[info]   丢弃未裁决旧卡: {stats['dropped_pending']}",
    ]
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="合并新鲜挖掘候选与旧裁决状态")
    parser.add_argument("--person", required=True, help="person 标识")
    parser.add_argument('--relationship-id', required=True)
    parser.add_argument('--legacy-freeze', type=Path)
    parser.add_argument("--old", type=Path, help="旧候选文件路径")
    parser.add_argument("--new", type=Path, required=True, help="新鲜候选文件路径")
    parser.add_argument("--out", type=Path, help="输出文件路径")
    parser.add_argument("--dry-run", action="store_true", help="仅打印报告不写盘")
    args = parser.parse_args()

    # 校验 person
    if not PERSON_RE.match(args.person):
        print("[error] person 标识不合法")
        return 2

    root = repo_root()
    person_dir = root / "people" / args.person
    memories_dir = person_dir / "memories"
    raw_dir = person_dir / "raw"

    # 默认路径
    default_old = memories_dir / "candidates.jsonl"
    old_path = args.old if args.old is not None else default_old
    out_path = args.out if args.out is not None else default_old

    # 路径安全校验
    if not path_is_within(out_path, memories_dir):
        print(f"[error] 输出路径越界: {out_path}")
        return 2
    for p in (old_path, args.new):
        if path_is_within(p, raw_dir):
            print(f"[error] 输入不能位于 raw 子树: {p}")
            return 2

    # 检查文件存在
    if not old_path.exists():
        print(f"[error] 旧候选文件不存在: {old_path}")
        return 2
    if not args.new.exists():
        print(f"[error] 新候选文件不存在: {args.new}")
        return 2

    # 读取输入（完整读入后才允许写盘）
    old_records = load_jsonl_strict(old_path)
    new_records = load_jsonl_strict(args.new)

    # 统计 old 文件
    old_confirmed = sum(1 for r in old_records if r.get("status") == "confirmed")
    old_rejected = sum(1 for r in old_records if r.get("status") == "rejected")
    old_pending = len(old_records) - old_confirmed - old_rejected

    # 合并
    try:
        preflight_outputs([out_path],
                          [args.new, args.legacy_freeze], inplace_inputs=[old_path])
        # 暂存文件没有原地更新权限，必须保护旧输入和最终输出。
        preflight_outputs([out_path.with_suffix(out_path.suffix + '.part')],
                          [old_path, args.new, args.legacy_freeze, out_path])
        if old_records and old_records[0].get('schema_version') == 2 and out_path.resolve() == default_old.resolve():
            raise ValueError('v2 cannot overwrite legacy candidates')
        if old_records and old_records[0].get('schema_version', 1) == 1:
            validate_legacy_freeze(old_records, old_path.read_bytes(), args.legacy_freeze,
                                   args.person, args.relationship_id)
        elif any(r['person'] != args.person or r['relationship_id'] != args.relationship_id
                 for r in old_records + new_records):
            raise ValueError('CLI scope mismatch')
        merged, stats = merge_candidates(old_records, new_records)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print('[error] invalid merge scope/evidence: ' + str(exc))
        return 2
    if merged is None:
        return 1

    # 打印报告
    report_lines = build_report(stats, old_path, args.new, out_path,
                                len(old_records), len(new_records),
                                old_confirmed, old_rejected, old_pending)
    for line in report_lines:
        print(line)

    # 写盘
    if not args.dry_run:
        write_atomic(out_path, merged)
    else:
        print("[info] dry-run：未写盘")

    return 0


if __name__ == "__main__":
    sys.exit(main())
