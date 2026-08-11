# -*- coding: utf-8 -*-
import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants and presets
# ---------------------------------------------------------------------------

STYLES = {
    "warm": "将照片中的人物转换为温暖的手绘卡通头像插画，保留她的脸型、发型、眼镜和神态特征，柔和明亮的色彩，简洁干净的浅色背景，迪士尼动画风格，非写实",
    "watercolor": "将照片中的人物转换为柔和的水彩绘本风格插画头像，保留她的脸型、发型、眼镜和神态特征，温柔的笔触，淡雅的色彩，留白的浅色背景，非写实",
    "flat": "将照片中的人物转换为现代扁平风格插画头像，保留她的脸型、发型、眼镜和神态特征，简洁的色块，柔和的配色，纯色浅背景，非写实",
}
NEGATIVE = "写实照片，真实皮肤纹理，模糊，变形，畸形的手，文字，水印"

DEFAULT_COMFY_ROOT = Path.home() / "ComfyUI_portable" / "ComfyUI_windows_portable"

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}
PERSON_RE = re.compile(r"^[a-z0-9_-]{1,64}$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def http_json(url, payload=None, timeout=30, method=None):
    """Send JSON POST (if payload or method given) or GET, return parsed JSON or None."""
    data = None
    if payload is not None or method == "POST":
        data = json.dumps(payload).encode("utf-8") if payload is not None else b""
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


def http_bytes(url, timeout=300):
    """Download raw bytes from a URL."""
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read()


def parse_args(argv):
    p = argparse.ArgumentParser(description="Generate cartoon avatar candidates from photos via ComfyUI")
    p.add_argument("--person", required=True, help="Person identifier (lowercase letters, digits, underscore, hyphen)")
    p.add_argument("--styles", default=",".join(STYLES.keys()), help="Comma-separated style keys")
    p.add_argument("--seeds", type=int, default=1, help="Variants per photo per style")
    p.add_argument("--base-seed", type=int, default=1000, help="Starting seed")
    p.add_argument("--photos", default="*", help="Glob filter for photo filenames")
    p.add_argument("--comfy", default="http://127.0.0.1:8188", help="ComfyUI API address")
    p.add_argument("--comfy-root", default=str(DEFAULT_COMFY_ROOT), help="ComfyUI portable root directory")
    p.add_argument("--steps", type=int, default=20)
    p.add_argument("--cfg", type=float, default=4.0)
    p.add_argument("--shift", type=float, default=3.0)
    p.add_argument("--timeout", type=int, default=300, help="Seconds per generation")
    p.add_argument("--overwrite", action="store_true", help="Force regeneration even if output exists")
    p.add_argument("--dry-run", action="store_true", help="Print tasks without executing")

    args = p.parse_args(argv)

    # Validate person
    if not PERSON_RE.match(args.person):
        sys.stderr.write(f"ERROR: invalid --person '{args.person}' (must match [a-z0-9_-]{{1,64}})\n")
        sys.exit(2)

    if args.seeds < 1:
        sys.stderr.write("ERROR: --seeds must be >= 1\n")
        sys.exit(2)

    # Parse styles
    style_keys = [s.strip() for s in args.styles.split(",") if s.strip()]
    if not style_keys:
        sys.stderr.write("ERROR: --styles cannot be empty\n")
        sys.exit(2)
    for sk in style_keys:
        if sk not in STYLES:
            sys.stderr.write(f"ERROR: unknown style '{sk}'. Available: {', '.join(STYLES.keys())}\n")
            sys.exit(2)
    args.style_keys = style_keys

    # Validate photos pattern
    if "/" in args.photos or "\\" in args.photos or ".." in args.photos:
        sys.stderr.write("ERROR: --photos must be a simple filename glob (no path separators or '..')\n")
        sys.exit(2)

    return args


def repo_root():
    """The repo root is the parent of the tools/ directory where this script lives."""
    return Path(__file__).resolve().parent.parent


def expected_output_root(repo, person):
    """Build the literal expected output root path (not resolved, just concatenated)."""
    return repo / "people" / person / "processed" / "avatar_candidates"


def safe_output_path(expected_root, filename):
    """Resolve and verify the output path is within the allowed subtree."""
    candidate = (expected_root / filename).resolve()
    if candidate.parent != expected_root or candidate.name != filename:
        sys.stderr.write(f"ERROR: output path escapes allowed directory: {candidate}\n")
        sys.exit(2)
    return candidate


def sha256_of_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def enumerate_photos(repo, person, pattern):
    raw_photos_dir = (repo / "people" / person / "raw" / "photos").resolve()
    if not raw_photos_dir.is_dir():
        sys.stderr.write(f"ERROR: photo directory not found: {raw_photos_dir}\n")
        sys.exit(1)

    files = []
    for path in sorted(raw_photos_dir.iterdir()):
        if path.is_file() and path.suffix.lower() in ALLOWED_EXTENSIONS and fnmatch.fnmatch(path.name, pattern):
            files.append(path)

    if not files:
        sys.stderr.write(f"ERROR: no photos found in {raw_photos_dir} matching '{pattern}'\n")
        sys.exit(1)

    return files


def stage_photo(comfy_root, src, idx):
    """Copy photo into ComfyUI/input with ASCII name. Returns the input filename."""
    input_dir = (comfy_root / "ComfyUI" / "input").resolve()
    try:
        input_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        sys.stderr.write(f"ERROR: cannot create input dir {input_dir}: {e}\n")
        sys.exit(1)

    ext = src.suffix.lower() or ".jpg"
    ascii_name = f"avatar_src_{idx:02d}{ext}"
    dst = input_dir / ascii_name

    if dst.exists() and dst.stat().st_size == src.stat().st_size:
        # Assume same content (size check only, as spec says)
        return ascii_name

    try:
        shutil.copyfile(src, dst)
    except Exception as e:
        sys.stderr.write(f"ERROR: failed to copy {src} -> {dst}: {e}\n")
        sys.exit(1)
    return ascii_name


def build_graph(input_name, prompt, negative, seed, steps, cfg, shift, filename_prefix):
    """Return the API-format graph dict as specified."""
    graph = {
        "37": {"class_type": "UNETLoader", "inputs": {"unet_name": "qwen_image_edit_2509_fp8_e4m3fn.safetensors", "weight_dtype": "default"}},
        "38": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_2.5_vl_7b_fp8_scaled.safetensors", "type": "qwen_image", "device": "default"}},
        "39": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_vae.safetensors"}},
        "78": {"class_type": "LoadImage", "inputs": {"image": input_name}},
        "117": {"class_type": "FluxKontextImageScale", "inputs": {"image": ["78", 0]}},
        "88": {"class_type": "VAEEncode", "inputs": {"pixels": ["117", 0], "vae": ["39", 0]}},
        "111": {"class_type": "TextEncodeQwenImageEditPlus", "inputs": {"clip": ["38", 0], "vae": ["39", 0], "image1": ["117", 0], "prompt": prompt}},
        "110": {"class_type": "TextEncodeQwenImageEditPlus", "inputs": {"clip": ["38", 0], "vae": ["39", 0], "image1": ["117", 0], "prompt": negative}},
        "66": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["37", 0], "shift": shift}},
        "75": {"class_type": "CFGNorm", "inputs": {"model": ["66", 0], "strength": 1}},
        "3": {"class_type": "KSampler", "inputs": {"model": ["75", 0], "seed": seed, "steps": steps, "cfg": cfg, "sampler_name": "euler", "scheduler": "simple", "positive": ["111", 0], "negative": ["110", 0], "latent_image": ["88", 0], "denoise": 1.0}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["39", 0]}},
        "9": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": filename_prefix}},
    }
    return graph


def submit_prompt(comfy_base, graph, timeout=30):
    url = f"{comfy_base}/prompt"
    payload = {"prompt": graph}
    resp = http_json(url, payload=payload, timeout=timeout)
    return resp


def poll_history(comfy_base, prompt_id, timeout, poll_interval=3):
    """Poll until completed or error or timeout. Returns (status, detail)"""
    url = f"{comfy_base}/history/{urllib.parse.quote(prompt_id)}"
    start = time.time()
    while True:
        elapsed = time.time() - start
        if elapsed > timeout:
            # interrupt with empty POST body
            try:
                http_json(f"{comfy_base}/interrupt", payload=None, timeout=30, method="POST")
            except Exception:
                pass
            return ("timeout", None)
        try:
            hist = http_json(url, timeout=30)
        except Exception as e:
            # transient network error, keep polling
            time.sleep(poll_interval)
            continue

        if not hist:
            time.sleep(poll_interval)
            continue

        if not isinstance(hist, dict):
            time.sleep(poll_interval)
            continue

        entry = hist.get(prompt_id)
        if not entry or not isinstance(entry, dict):
            time.sleep(poll_interval)
            continue

        status = entry.get("status", {})
        status_str = status.get("status_str")
        completed = status.get("completed")
        if completed or status_str == "completed":
            return ("success", entry)
        if status_str == "error":
            return ("error", entry)
        time.sleep(poll_interval)


def extract_output_image(entry):
    """Extract first image from outputs. Returns (filename, subfolder, type) or None"""
    outputs = entry.get("outputs", {})
    for node_id, out in outputs.items():
        imgs = out.get("images", [])
        if imgs:
            img = imgs[0]
            return img.get("filename"), img.get("subfolder", ""), img.get("type", "output")
    return None


def download_image(comfy_base, filename, subfolder, img_type, timeout=300):
    params = {"filename": filename, "subfolder": subfolder, "type": img_type}
    url = f"{comfy_base}/view?" + urllib.parse.urlencode(params)
    return http_bytes(url, timeout=timeout)


def append_manifest(manifest_path, repo_rel_out, repo_rel_src, src_sha, style, prompt, negative, seed, steps, cfg, shift, prompt_id, elapsed, ts):
    record = {
        "out_file": repo_rel_out,
        "source_photo": repo_rel_src,
        "source_sha256": src_sha,
        "style": style,
        "prompt": prompt,
        "negative": negative,
        "seed": seed,
        "steps": steps,
        "cfg": cfg,
        "shift": shift,
        "model": "qwen_image_edit_2509_fp8_e4m3fn",
        "prompt_id": prompt_id,
        "elapsed_s": round(elapsed, 1),
        "ts": ts,
    }
    with open(manifest_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args(sys.argv[1:])

    repo = repo_root()

    # Build expected output root (literal path)
    expected_root = expected_output_root(repo, args.person)

    # --- Setup output directory with safety checks (skip in dry-run)
    if not args.dry_run:
        try:
            expected_root.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            sys.stderr.write(f"ERROR: cannot create output directory {expected_root}: {e}\n")
            sys.exit(1)

        if expected_root.is_symlink():
            sys.stderr.write(f"ERROR: output directory is a symlink: {expected_root}\n")
            sys.exit(1)

        if expected_root.resolve() != expected_root:
            sys.stderr.write(f"ERROR: output directory path resolves elsewhere: {expected_root} -> {expected_root.resolve()}\n")
            sys.exit(1)

    comfy_root = Path(args.comfy_root).resolve()

    # --- Check ComfyUI is alive unless dry-run
    if not args.dry_run:
        try:
            stats = http_json(f"{args.comfy}/system_stats", timeout=10)
            if stats is None:
                raise RuntimeError("empty response")
        except Exception as e:
            sys.stderr.write(f"ERROR: cannot reach ComfyUI at {args.comfy}: {e}\n")
            sys.stderr.write("Please start ComfyUI first, then retry.\n")
            sys.exit(1)

    # --- Enumerate photos
    photos = enumerate_photos(repo, args.person, args.photos)

    # --- Build task list
    tasks = []
    for idx, photo in enumerate(photos, start=1):
        # Stage photo now (unless dry-run? spec says staging is part of flow; in dry-run we don't write anything)
        if not args.dry_run:
            ascii_name = stage_photo(comfy_root, photo, idx)
        else:
            # compute what the name would be
            ext = photo.suffix.lower() or ".jpg"
            ascii_name = f"avatar_src_{idx:02d}{ext}"

        for style in args.style_keys:
            for var_idx in range(args.seeds):
                seed = args.base_seed + var_idx
                out_filename = f"{idx:02d}_{style}_s{seed}.png"
                tasks.append({
                    "idx": idx,
                    "photo": photo,
                    "ascii_name": ascii_name,
                    "style": style,
                    "seed": seed,
                    "out_filename": out_filename,
                })

    # Print summary
    total = len(tasks)
    print(f"Total tasks: {total} ({len(photos)} photos x {len(args.style_keys)} styles x {args.seeds} seeds)")

    if args.dry_run:
        for i, t in enumerate(tasks, 1):
            print(f"[{i}/{total}] {t['out_filename']} (from {t['photo'].name}, style={t['style']}, seed={t['seed']})")
        return 0

    # --- Execute
    successes = 0
    skips = 0
    failures = []

    manifest_path = safe_output_path(expected_root, "manifest.jsonl")

    for i, t in enumerate(tasks, 1):
        out_path = safe_output_path(expected_root, t["out_filename"])

        if out_path.exists() and not args.overwrite:
            print(f"[{i}/{total}] {t['out_filename']} ... SKIP (exists)")
            skips += 1
            continue

        prompt = STYLES[t["style"]]
        prefix = f"avatar_{t['idx']:02d}_{t['style']}_s{t['seed']}"
        graph = build_graph(t["ascii_name"], prompt, NEGATIVE, t["seed"], args.steps, args.cfg, args.shift, prefix)

        start = time.time()
        try:
            sub = submit_prompt(args.comfy, graph, timeout=30)
        except Exception as e:
            print(f"[{i}/{total}] {t['out_filename']} ... FAIL (submit: {e})")
            failures.append((t["out_filename"], f"submit: {e}"))
            continue

        if not sub or "prompt_id" not in sub:
            detail = str(sub)[:500] if sub else "empty response"
            print(f"[{i}/{total}] {t['out_filename']} ... FAIL (no prompt_id: {detail})")
            failures.append((t["out_filename"], "no prompt_id"))
            continue

        pid = sub["prompt_id"]

        try:
            status, entry = poll_history(args.comfy, pid, timeout=args.timeout)
        except Exception as e:
            print(f"[{i}/{total}] {t['out_filename']} ... FAIL (poll: {e})")
            failures.append((t["out_filename"], f"poll: {e}"))
            continue

        elapsed = time.time() - start
        file_written = False

        # Wrap the entire task in try/except so failures don't escape the main loop
        try:
            if status == "success":
                img_info = extract_output_image(entry)
                if not img_info:
                    print(f"[{i}/{total}] {t['out_filename']} ... FAIL (no output image)")
                    failures.append((t["out_filename"], "no output image"))
                    continue
                filename, subfolder, img_type = img_info
                try:
                    data = download_image(args.comfy, filename, subfolder, img_type, timeout=args.timeout)
                except Exception as e:
                    print(f"[{i}/{total}] {t['out_filename']} ... FAIL (download: {e})")
                    failures.append((t["out_filename"], f"download: {e}"))
                    continue

                # Write atomically
                tmp_path = safe_output_path(expected_root, t["out_filename"] + ".part")
                with open(tmp_path, "wb") as f:
                    f.write(data)
                os.replace(tmp_path, out_path)
                file_written = True

                # Manifest
                src_sha = sha256_of_file(t["photo"])
                rel_out = str(out_path.relative_to(repo))
                rel_src = str(t["photo"].relative_to(repo))
                ts = time.strftime("%Y-%m-%dT%H:%M:%S")
                manifest_path = safe_output_path(expected_root, "manifest.jsonl")
                append_manifest(manifest_path, rel_out, rel_src, src_sha, t["style"], prompt, NEGATIVE,
                                t["seed"], args.steps, args.cfg, args.shift, pid, elapsed, ts)

                print(f"[{i}/{total}] {t['out_filename']} ... DONE {elapsed:.1f}s")
                successes += 1

            elif status == "error":
                # extract error message
                err_msg = ""
                messages = entry.get("status", {}).get("messages", [])
                for m in messages:
                    if m and m[0] == "execution_error":
                        err_msg = str(m[1])[:200]
                        break
                if not err_msg:
                    err_msg = "unknown execution error"
                print(f"[{i}/{total}] {t['out_filename']} ... FAIL (execution error: {err_msg})")
                failures.append((t["out_filename"], err_msg))

            elif status == "timeout":
                print(f"[{i}/{total}] {t['out_filename']} ... FAIL (timeout)")
                failures.append((t["out_filename"], "timeout"))

            else:
                print(f"[{i}/{total}] {t['out_filename']} ... FAIL (unknown status)")
                failures.append((t["out_filename"], "unknown"))

        except Exception as e:
            # Remove any file that was written but not recorded in manifest
            if file_written:
                try:
                    os.remove(out_path)
                except Exception as rm_err:
                    print(f"WARNING: could not remove orphaned output {out_path}: {rm_err}")
            print(f"[{i}/{total}] {t['out_filename']} ... FAIL (task error: {e})")
            failures.append((t["out_filename"], f"task error: {e}"))

    # Summary
    print("\n=== Summary ===")
    print(f"Success: {successes}")
    print(f"Skipped: {skips}")
    print(f"Failed: {len(failures)}")
    for f in failures:
        print(f"  - {f[0]}: {f[1]}")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

