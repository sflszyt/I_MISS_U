# -*- coding: utf-8 -*-
"""Make contact sheets of avatar candidates."""

import argparse
import io
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

CELL_PAD = 8
TITLE_H = 40
DIVIDER_H = 12
DIVIDER_COLOR = (200, 200, 200)
ERR_BG = (204, 204, 204)


def parse_args(argv):
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--person", required=True, help="person id")
    parser.add_argument("--in-dir", default=None, help="candidates dir")
    parser.add_argument("--out-dir", default=None, help="output dir")
    parser.add_argument("--cell", type=int, default=320, help="cell size")
    parser.add_argument("--cols", type=int, default=5, help="columns per row")
    parser.add_argument("--quality", type=int, default=82, help="initial JPEG quality")
    parser.add_argument("--max-kb", type=int, default=950, help="max KB per sheet")
    return parser.parse_args(argv)


def get_repo_root():
    """Return repo root (parent of tools/)."""
    tools_dir = Path(__file__).resolve().parent
    return tools_dir.parent


def collect_candidates(in_dir):
    """Return sorted list of (num, seed, path) from in_dir."""
    pattern = re.compile(r"^(\d{2})_([a-z0-9]+)_s(\d+)\.png$")
    files = []
    for path in sorted(in_dir.iterdir()):
        if not path.is_file():
            continue
        name = path.name
        m = pattern.match(name)
        if not m:
            print(f"skip: {name}")
            continue
        num = int(m.group(1))
        seed = int(m.group(3))
        files.append((num, seed, path))
    files.sort(key=lambda x: (x[0], x[1]))
    return files


def collect_sources(raw_photos_dir):
    """Return sorted list of source photo paths."""
    exts = {".jpg", ".jpeg", ".png"}
    files = []
    if raw_photos_dir.is_dir():
        for path in sorted(raw_photos_dir.iterdir()):
            if path.is_file() and path.suffix.lower() in exts:
                files.append(path)
    return files


def render_cell(cell, img_path, label):
    """Render one cell with image and label. Return cell image."""
    cell_img = Image.new("RGB", (cell, cell), "white")
    box = (2, 2, cell - 2, cell - 2)
    try:
        with Image.open(img_path) as im:
            im = im.convert("RGBA")
            im.thumbnail((box[2] - box[0], box[3] - box[1]))
            x = (cell - im.width) // 2
            y = (cell - im.height) // 2
            cell_img.paste(im, (x, y), mask=im)
    except Exception as e:
        print(f"warn: {img_path.name} load failed: {e}")
        draw = ImageDraw.Draw(cell_img)
        draw.rectangle(box, fill=ERR_BG)
        font = ImageFont.load_default()
        draw.text((box[0] + 4, box[1] + 4), "ERR", fill="black", font=font)
        label = "ERR"
    # label
    draw = ImageDraw.Draw(cell_img)
    font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), label, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.rectangle((2, 2, 2 + tw + 2, 2 + th + 2), fill="white")
    draw.text((3, 3), label, fill="black", font=font)
    return cell_img


def render_grid(items, cell, cols):
    """Render a grid from items. items list of (label, path)."""
    n_rows = (len(items) + cols - 1) // cols
    width = cols * (cell + CELL_PAD) + CELL_PAD
    height = n_rows * (cell + CELL_PAD) + CELL_PAD
    img = Image.new("RGB", (width, height), "white")
    for idx, (label, path) in enumerate(items):
        row = idx // cols
        col = idx % cols
        x = CELL_PAD + col * (cell + CELL_PAD)
        y = CELL_PAD + row * (cell + CELL_PAD)
        cell_img = render_cell(cell, path, label)
        img.paste(cell_img, (x, y))
    return img, n_rows


def render_sheet(style, person, candidates, sources, cell, cols):
    """Render full sheet for a style."""
    title = f"{style} - {person} - {len(candidates)} candidates"
    font = ImageFont.load_default()

    # candidate grid
    cand_items = [(f"{idx:02d} s{seed}", path) for idx, seed, path in candidates]
    cand_grid, _ = render_grid(cand_items, cell, cols)

    if not sources:
        # no source photos: sheet = title + candidate grid
        width = cand_grid.width
        height = TITLE_H + cand_grid.height
        sheet = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(sheet)
        bbox = draw.textbbox((0, 0), title, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text(((width - tw) // 2, (TITLE_H - th) // 2), title, fill="black", font=font)
        sheet.paste(cand_grid, (0, TITLE_H))
        return sheet

    # source grid
    src_items = [(f"{i + 1:02d}", p) for i, p in enumerate(sources)]
    src_grid, _ = render_grid(src_items, cell, cols)

    # assemble
    width = max(src_grid.width, cand_grid.width)
    height = TITLE_H + DIVIDER_H + src_grid.height + cand_grid.height
    sheet = Image.new("RGB", (width, height), "white")

    # title
    draw = ImageDraw.Draw(sheet)
    bbox = draw.textbbox((0, 0), title, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text(((width - tw) // 2, (TITLE_H - th) // 2), title, fill="black", font=font)

    # source grid (left aligned)
    sheet.paste(src_grid, (0, TITLE_H))

    # divider
    draw.rectangle((0, TITLE_H + src_grid.height, width, TITLE_H + src_grid.height + DIVIDER_H),
                   fill=DIVIDER_COLOR)

    # candidate grid
    sheet.paste(cand_grid, (0, TITLE_H + src_grid.height + DIVIDER_H))
    return sheet


def save_under_limit(sheet, out_path, quality, max_kb):
    """Compress and save sheet under limit. Return (ok, message)."""
    scale = 1.0
    while True:
        if scale < 1.0:
            new_w = int(sheet.width * scale)
            new_h = int(sheet.height * scale)
            work = sheet.resize((new_w, new_h), Image.LANCZOS)
        else:
            work = sheet
        q = quality
        while q >= 40:
            buf = io.BytesIO()
            work.save(buf, "JPEG", quality=q)
            size = buf.tell()
            if size <= max_kb * 1024:
                out_path.write_bytes(buf.getvalue())
                print(f"{out_path.name}  {work.width}x{work.height}  q={q}  {size // 1024}KB")
                return True
            q -= 8
        scale *= 0.85
        if scale < 0.4:
            print(f"error: could not fit {out_path.name} under {max_kb}KB", file=sys.stderr)
            return False
    return False


def main():
    """Entry point."""
    args = parse_args(sys.argv[1:])
    if not re.match(r"^[a-z0-9_-]{1,64}$", args.person):
        print(f"error: invalid person {args.person!r}", file=sys.stderr)
        return 2

    repo_root = get_repo_root()
    person_dir = repo_root / "people" / args.person
    raw_dir = person_dir / "raw"
    processed_dir = person_dir / "processed"
    in_dir = Path(args.in_dir) if args.in_dir else processed_dir / "avatar_candidates"
    out_dir = Path(args.out_dir) if args.out_dir else in_dir / "sheets"

    # validate out-dir
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        out_res = out_dir.resolve()
        repo_res = repo_root.resolve()
        expected_parent = repo_res / "people" / args.person / "processed"
        if not (out_res == expected_parent or expected_parent in out_res.parents):
            print(f"error: out-dir outside processed tree: {out_dir}", file=sys.stderr)
            return 2
    except OSError as e:
        print(f"error: cannot create out-dir: {e}", file=sys.stderr)
        return 2

    # source photos
    sources = collect_sources(raw_dir / "photos")
    if not sources:
        print("warn: no source photos found; sheets will contain candidates only")

    # candidates
    if not in_dir.is_dir():
        print(f"error: in-dir not found: {in_dir}", file=sys.stderr)
        return 1
    candidates = collect_candidates(in_dir)
    if not candidates:
        print("error: no candidate files found", file=sys.stderr)
        return 1

    # group by style
    styles = {}
    for num, seed, path in candidates:
        m = re.match(r"^(\d{2})_([a-z0-9]+)_s(\d+)\.png$", path.name)
        style = m.group(2)
        styles.setdefault(style, []).append((num, seed, path))

    ok = True
    for style in sorted(styles):
        style_cands = styles[style]
        missing = sorted({idx for (idx, seed, path) in style_cands if idx > len(sources)})
        for idx in missing:
            print(f"warn: candidate {idx:02d} has no source photo")
        sheet = render_sheet(style, args.person, style_cands, sources,
                             args.cell, args.cols)
        out_path = out_dir / f"sheet_{style}.jpg"
        if not save_under_limit(sheet, out_path, args.quality, args.max_kb):
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
