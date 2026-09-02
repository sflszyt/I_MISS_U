"""
数字档案项目：把 AI 生成的候选整图按给定区域烘成 RGBA 透明贴片，叠加在卡通头像底图之上。
贴片 RGB = 候选图像素，alpha = 区域羽化掩码；掩码为 0 处 RGB 清零、alpha=0（压体积）。

掩码数学（与 2026-08-29 情绪贴片审核页的预览数学一致）：
  对每个区域 (x0,y0,x1,y1,feather)：新建 L 模式全 0 图 → ImageDraw.Draw(m).rectangle((x0,y0,x1,y1),
  fill=255) → 若 feather>0 则 m = m.filter(ImageFilter.GaussianBlur(feather))；多个区域的掩码用
  ImageChops.lighter 逐个合并（逐像素取最大）。注意：不做 inset（不要把矩形先内缩再模糊）。

自验方法：
  expected = Image.composite(src_rgb, base_rgb, mask)
  actual   = Image.alpha_composite(base_rgb.convert("RGBA"), patch_rgba).convert("RGB")
  max_diff = ImageChops.difference(expected, actual) 三通道 getextrema() 的最大值
  max_diff > 2 视为失败。

与旧 Phase 1 烘焙脚本的差别：
  旧脚本先把矩形内缩 feather 再 GaussianBlur(feather/2)；本工具不内缩、直接 GaussianBlur(feather)，
  对应 2026-08-29 情绪贴片审核页的预览数学。

CLI 示例：
  单任务：
    python tools/bake_face_patch.py --base <base.png> --src <cand.png> --out <patch.png> --region x0,y0,x1,y1:feather [--region ...]
  批任务：
    python tools/bake_face_patch.py --base <base.png> --jobs <jobs.json>
"""
from pathlib import Path
import sys
import json
import argparse
import os
from PIL import Image, ImageDraw, ImageFilter, ImageChops



def parse_region(text: str) -> tuple:
    parts = text.split(":")
    if len(parts) != 2:
        raise ValueError("格式必须为 x0,y0,x1,y1:feather")
    try:
        coords = [int(v) for v in parts[0].split(",")]
        feather = int(parts[1])
    except ValueError:
        raise ValueError("坐标和羽化值必须为整数")
    if len(coords) != 4:
        raise ValueError("需要 4 个坐标值 x0,y0,x1,y1")
    x0, y0, x1, y1 = coords
    if feather < 0:
        raise ValueError("feather 必须 >= 0")
    return (x0, y0, x1, y1, feather)


def validate_region(region: tuple, size: tuple) -> None:
    x0, y0, x1, y1, feather = region
    W, H = size
    if feather < 0:
        raise ValueError("feather 必须 >= 0")
    if not (0 <= x0 < x1 <= W):
        raise ValueError(f"x 范围无效: x0={x0}, x1={x1}, 宽度={W}")
    if not (0 <= y0 < y1 <= H):
        raise ValueError(f"y 范围无效: y0={y0}, y1={y1}, 高度={H}")


def build_mask(size: tuple, regions: list) -> Image.Image:
    W, H = size
    mask = Image.new("L", (W, H), 0)
    for region in regions:
        x0, y0, x1, y1, feather = region
        m = Image.new("L", (W, H), 0)
        d = ImageDraw.Draw(m)
        d.rectangle((x0, y0, x1, y1), fill=255)
        if feather > 0:
            m = m.filter(ImageFilter.GaussianBlur(feather))
        mask = ImageChops.lighter(mask, m)
    return mask


def bake(base_rgb: Image.Image, src_rgb: Image.Image, regions: list) -> tuple:
    size = base_rgb.size
    mask = build_mask(size, regions)
    rgb_masked = Image.composite(
        src_rgb,
        Image.new("RGB", size, (0, 0, 0)),
        mask.point(lambda v: 255 if v > 0 else 0),
    )
    patch_rgba = Image.merge("RGBA", (*rgb_masked.split(), mask))
    return (patch_rgba, mask)


def verify(base_rgb, src_rgb, mask, patch_rgba) -> int:
    size = base_rgb.size
    expected = Image.composite(src_rgb, base_rgb, mask)
    actual = Image.alpha_composite(base_rgb.convert("RGBA"), patch_rgba).convert("RGB")
    diff = ImageChops.difference(expected, actual)
    extrema = diff.getextrema()
    return max(mx for _, mx in extrema)


def run_job(base_path: Path, src_path: Path, out_path: Path, regions: list, label: str) -> bool:
    # 检查防覆盖
    if Path(out_path).resolve() == Path(base_path).resolve() or Path(out_path).resolve() == Path(src_path).resolve():
        print(f"[ERROR] {label} out 路径与 base/src 相同")
        return False

    # 读取 base
    try:
        base_img = Image.open(base_path).convert("RGB")
    except Exception:
        print(f"[ERROR] {label} 无法打开 base: {base_path}")
        return False

    # 读取 src
    try:
        src_img = Image.open(src_path).convert("RGB")
    except Exception:
        print(f"[ERROR] {label} 无法打开 src: {src_path}")
        return False

    # 尺寸校验/调整
    if src_img.size != base_img.size:
        bw, bh = base_img.size
        sw, sh = src_img.size
        print(f"[WARN] {src_path.name} size {sw}x{sh} != base {bw}x{bh}, resizing (LANCZOS)")
        src_img = src_img.resize(base_img.size, Image.LANCZOS)

    # 批次标签用于错误信息
    if label.startswith("job"):
        job_label = f"job {label[3:]}"
    else:
        job_label = label

    # 验证 regions
    valid_regions = []
    for idx, region in enumerate(regions):
        try:
            validate_region(region, base_img.size)
            valid_regions.append(region)
        except ValueError as e:
            print(f"[ERROR] {job_label} region {idx}: {e}")
            return False

    # 烘焙
    patch_rgba, mask = bake(base_img, src_img, valid_regions)

    # 自验
    max_diff = verify(base_img, src_img, mask, patch_rgba)
    if max_diff > 2:
        # 清理本次可能遗留的临时文件，不触碰既有成品
        tmp = out_path.with_name(out_path.name + ".tmp")
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        print(f"[FAIL] {out_path.name} overlay math mismatch max_diff={max_diff}")
        return False
    else:
        print(f"[CHECK] {out_path.name} max_diff={max_diff} (<=2 pass)")

    # 输出
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path.with_name(out_path.name + ".tmp")
        patch_rgba.save(tmp, format="PNG", optimize=True)
        os.replace(tmp, out_path)
    except OSError as e:
        tmp = out_path.with_name(out_path.name + ".tmp")
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        print(f"[ERROR] {label} 写输出文件失败: {e}")
        return False

    # 统计 coverage
    hist = mask.histogram()
    total = sum(hist)
    coverage = (total - hist[0]) / total * 100 if total > 0 else 0.0
    size_kb = out_path.stat().st_size / 1024.0
    print(f"[BAKE] {out_path.name} {size_kb:.1f}KB coverage={coverage:.1f}% regions={len(valid_regions)}")
    return True


def load_jobs(jobs_path: Path) -> list:
    try:
        with open(jobs_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except OSError as e:
        raise ValueError(f"无法读取 jobs 文件 {jobs_path}: {e}")
    except json.JSONDecodeError as e:
        raise ValueError(f"jobs 文件 JSON 格式错误 {jobs_path}: {e}")

    if not isinstance(data, dict) or "jobs" not in data:
        raise ValueError("jobs 文件必须包含 'jobs' 键，值为列表")
    jobs_data = data["jobs"]
    if not isinstance(jobs_data, list) or not jobs_data:
        raise ValueError("jobs 必须是非空列表")

    base_dir = jobs_path.parent
    result = []
    for idx, job in enumerate(jobs_data):
        if not isinstance(job, dict):
            raise ValueError(f"job {idx} 必须是对象")
        if "src" not in job or "out" not in job or "regions" not in job:
            raise ValueError(f"job {idx} 必须包含 src, out, regions 字段")
        src_str = job["src"]
        out_str = job["out"]
        if not isinstance(src_str, str) or not src_str or not isinstance(out_str, str) or not out_str:
            raise ValueError(f"job {idx} src/out 必须是非空字符串")
        regions_data = job["regions"]
        if not isinstance(regions_data, list) or not regions_data:
            raise ValueError(f"job {idx} regions 必须是非空列表")
        # 解析 regions
        regions = []
        for ridx, r in enumerate(regions_data):
            if not isinstance(r, list) or len(r) != 5:
                raise ValueError(f"job {idx} region {ridx} 必须是 5 个整数")
            if any(not isinstance(v, int) or isinstance(v, bool) for v in r):
                raise ValueError(f"job {idx} region {ridx} 必须是 5 个整数")
            regions.append(tuple(r))
        src_path = (base_dir / src_str).resolve()
        out_path = (base_dir / out_str).resolve()
        result.append((src_path, out_path, regions, f"job{idx}"))
    return result


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="烘焙面部贴片")
    parser.add_argument("--base", required=True, help="底图路径")
    parser.add_argument("--jobs", help="批任务 JSON 文件")
    parser.add_argument("--src", help="候选图路径")
    parser.add_argument("--out", help="输出贴片路径")
    parser.add_argument("--region", action="append", help="区域 x0,y0,x1,y1:feather")
    args = parser.parse_args(argv)

    has_single = args.src is not None or args.out is not None or args.region is not None
    has_jobs = args.jobs is not None

    if has_jobs and has_single:
        parser.error("--jobs 与 --src/--out/--region 互斥")
    if not has_jobs and not has_single:
        parser.error("必须提供 --jobs 或 --src/--out/--region")

    if has_jobs:
        try:
            jobs_path = Path(args.jobs)
            jobs = load_jobs(jobs_path)
        except ValueError as e:
            print(f"[ERROR] 加载 jobs 失败: {e}")
            return 2

        base_path = Path(args.base)
        ok = 0
        fail = 0
        for src_path, out_path, regions, label in jobs:
            if run_job(base_path, src_path, out_path, regions, label):
                ok += 1
            else:
                fail += 1
        print(f"[SUMMARY] ok={ok} fail={fail}")
        return 0 if fail == 0 else 2
    else:
        # 单任务
        if args.src is None or args.out is None or not args.region:
            parser.error("单任务必须提供 --src, --out 和至少一个 --region")
        base_path = Path(args.base)
        src_path = Path(args.src)
        out_path = Path(args.out)

        # 解析 regions
        regions = []
        for idx, text in enumerate(args.region):
            try:
                region = parse_region(text)
            except ValueError as e:
                print(f"[ERROR] job0 region {idx}: {e}")
                print("[SUMMARY] ok=0 fail=1")
                return 2
            regions.append(region)

        if run_job(base_path, src_path, out_path, regions, "job0"):
            print("[SUMMARY] ok=1 fail=0")
            return 0
        else:
            print("[SUMMARY] ok=0 fail=1")
            return 2


if __name__ == "__main__":
    sys.exit(main())