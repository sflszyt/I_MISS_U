# -*- coding: utf-8 -*-
"""Build a self-contained offline archive from archive_out to archive_dist."""

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
EXTERNAL_SRC_RE = re.compile(r"""(?:src|href)\s*=\s*["'](?:https?:)?//""")
EXTERNAL_SRCSET_RE = re.compile(r"""srcset\s*=\s*["'][^"']*(?:https?:)?//""")
EXTERNAL_CSSURL_RE = re.compile(r"""url\(\s*["']?(?:https?:)?//""")
SESSIONS_FILE_RE = re.compile(r"^sessions_[a-z][a-z0-9_-]{0,31}\.json$")
VIEWER_DIR_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")

FILE_ENCODING = "utf-8"
CHUNK_SIZE = 1024 * 1024


def _stderr(msg: str) -> None:
    print(msg, file=sys.stderr)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _atomic_write_text(path: Path, content: str, newline: str = "\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    with open(part, "w", encoding=FILE_ENCODING, newline="") as f:
        f.write(content)
    os.replace(part, path)


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    with open(part, "wb") as f:
        f.write(content)
    os.replace(part, path)


def _same_file_content(src: Path, dst: Path) -> bool:
    try:
        s = src.stat()
        d = dst.stat()
        return s.st_size == d.st_size and int(s.st_mtime) == int(d.st_mtime)
    except OSError:
        return False


def _delete_tree(target: Path) -> None:
    if target.is_dir() and not target.is_symlink():
        for child in target.iterdir():
            _delete_tree(child)
        try:
            target.rmdir()
        except OSError:
            pass
    elif target.exists() or target.is_symlink():
        try:
            target.unlink()
        except OSError:
            pass


def _list_relative(path: Path, base: Path) -> list[str]:
    return [str(p.relative_to(base)).replace(os.sep, "/") for p in sorted(path.rglob("*"))]


class Reporter:
    """Collects copy/skip/delete/generate counts and dry-run actions."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.copied = 0
        self.skipped = 0
        self.deleted = 0
        self.generated = 0
        self._actions: list[str] = []

    def _record(self, action: str, kind: str, dst: Path, src: Path | None = None) -> None:
        try:
            rel_str = str(dst.relative_to(REPO_ROOT)) if dst.is_absolute() else str(dst)
        except ValueError:
            rel_str = str(dst)
        self._actions.append(f"{kind}: {rel_str}")
        if len(self._actions) <= 20:
            if src is not None:
                print(f"{action} {src} -> {dst}")
            else:
                print(f"{action} {dst}")

    def copy(self, src: Path, dst: Path) -> None:
        if _same_file_content(src, dst):
            self.skipped += 1
            return
        self.copied += 1
        self._record("copy", "copy", dst, src)
        if not self.dry_run:
            shutil.copy2(src, dst)

    def delete(self, path: Path) -> None:
        self.deleted += 1
        self._record("delete", "delete", path)
        if not self.dry_run:
            _delete_tree(path)

    def generate(self, path: Path, content: str | bytes, newline: str = "\n") -> None:
        self.generated += 1
        self._record("generate", "generate", path)
        if not self.dry_run:
            if isinstance(content, str):
                _atomic_write_text(path, content, newline)
            else:
                _atomic_write_bytes(path, content)

    def print_detail(self) -> None:
        if self.dry_run and self._actions:
            print(f"  {len(self._actions)} actions (limit 20 shown):")
            for a in self._actions[:20]:
                print(f"    {a}")


def _is_sessions_file(p: Path, data_root: Path) -> bool:
    """会话产物一律不得进入可分发档案。

    按相对 data 根的路径分段判定，同时覆盖两种布局：
      - data/sessions_<viewer>.json        （1 段）
      - data/<viewer>/sessions.json        （2 段）
    data/ 下一级的、目录名合法的任何 sessions.json 一律按会话产物排除（这是有意的保守，因为该路径形式被约定保留给会话产物），
    更深层级的任何 sessions.json 也一律不排除。
    """
    try:
        parts = p.relative_to(data_root).parts
    except ValueError:
        # 不在 data 根之下：不参与会话产物排除判定
        return False
    if len(parts) == 1:
        return SESSIONS_FILE_RE.match(parts[0]) is not None
    if len(parts) == 2:
        return VIEWER_DIR_RE.match(parts[0]) is not None and parts[1] == "sessions.json"
    return False


def copy_tree_whitelist(src: Path, dst: Path, reporter: Reporter) -> bool:
    """Copy whitelisted top-level files and data/ subtree; reconcile dst."""
    required = ["avatar.html", "chat.html"]
    for name in required:
        if not (src / name).is_file():
            _stderr(f"ERROR: required page missing: {name}")
            return False

    # Build expected file set
    expected_files: set[str] = set(["avatar.html", "chat.html"])

    data_src = src / "data"
    if data_src.is_dir():
        for p in data_src.rglob("*"):
            if p.is_file() and not _is_sessions_file(p, data_src):
                expected_files.add(str(p.relative_to(src)).replace(os.sep, "/"))

    generated_and_text = [
        "index.html", "README.txt", "start_server.bat", "start_server.sh",
        "archive_manifest.json", "text/persona.md", "text/memories.md",
        "text/timeline.md", "text/rhythm.json"
    ]
    expected_files.update(generated_and_text)

    # File sweep: delete unexpected files
    if dst.exists():
        for p in sorted(dst.rglob("*")):
            if p.is_file():
                rel = str(p.relative_to(dst)).replace(os.sep, "/")
                if rel not in expected_files:
                    reporter.delete(p)

        # Directory sweep: remove empty dirs (not counted in deleted)
        if not reporter.dry_run:
            dirs = [d for d in dst.rglob("*") if d.is_dir()]
            for d in sorted(dirs, key=lambda x: len(x.parts), reverse=True):
                try:
                    if not any(d.iterdir()):
                        d.rmdir()
                except OSError:
                    pass

    # Copy files
    for name in ["avatar.html", "chat.html"]:
        reporter.copy(src / name, dst / name)
    if data_src.is_dir():
        for src_path in sorted(data_src.rglob("*")):
            if src_path.is_file() and not _is_sessions_file(src_path, data_src):
                rel = src_path.relative_to(src)
                dst_path = dst / rel
                if not reporter.dry_run:
                    dst_path.parent.mkdir(parents=True, exist_ok=True)
                reporter.copy(src_path, dst_path)
    return True


def archive_text_layer(person_dir: Path, dst: Path, reporter: Reporter) -> None:
    """Copy persona/memories text files into dst/text/."""
    text_dir = dst / "text"
    if not reporter.dry_run:
        text_dir.mkdir(parents=True, exist_ok=True)
    candidates = [
        ("persona/persona.md", "text/persona.md"),
        ("memories/memories.md", "text/memories.md"),
        ("memories/timeline.md", "text/timeline.md"),
        ("persona/rhythm.json", "text/rhythm.json"),
    ]
    for rel_src, rel_dst in candidates:
        src_path = person_dir / rel_src
        dst_path = text_dir / Path(rel_dst).name
        if src_path.is_file():
            reporter.copy(src_path, dst_path)
        else:
            _stderr(f"WARN: missing text source {rel_src}")


def _read_meta(path: Path) -> dict:
    try:
        with open(path, "r", encoding=FILE_ENCODING) as f:
            return json.load(f)
    except Exception:
        return {}


def render_index(person_dir: Path, src: Path, dst: Path, slug: str,
                 reporter: Reporter) -> None:
    """Generate index.html."""
    rel_path = person_dir / "persona" / "relationship.json"
    display_name = slug
    try:
        with open(rel_path, "r", encoding=FILE_ENCODING) as f:
            rel = json.load(f)
            display_name = rel.get("display_name", slug)
    except Exception:
        pass
    meta = _read_meta(src / "data" / "meta.json")
    counts = meta.get("counts", {}) if isinstance(meta, dict) else {}
    msg_count = counts.get("messages", 0) if isinstance(counts, dict) else 0
    voice_count = counts.get("voice", 0) if isinstance(counts, dict) else 0
    video_count = counts.get("video", 0) if isinstance(counts, dict) else 0
    from datetime import date
    gen_date = date.today().isoformat()

    html = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__DISPLAY_NAME__ 的数字档案</title>
<style>
  body { background: #faf5ec; color: #3a3226; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif; line-height: 1.6; margin: 0; padding: 2rem 1.5rem; max-width: 860px; margin-left: auto; margin-right: auto; }
  h1 { color: #5b4636; border-bottom: 3px solid #d9c9a3; padding-bottom: 0.4em; }
  .subtitle { color: #8a7a5e; font-size: 0.9rem; margin-bottom: 2rem; }
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 1.2rem; margin: 1.5rem 0; }
  .card { background: #fffaf0; border: 1px solid #eee3cc; border-radius: 10px; padding: 1.3rem; box-shadow: 0 2px 6px rgba(0,0,0,0.05); }
  .card h2 { margin-top: 0; color: #6b5a3e; font-size: 1.15rem; }
  .card p { color: #6b6048; font-size: 0.95rem; margin-bottom: 0.6rem; }
  .card a { display: inline-block; margin-top: 0.4rem; color: #2d5a7b; text-decoration: none; border-bottom: 1px solid #2d5a7b; }
  .card a:hover { color: #1d4a6b; }
  .section { margin-top: 2rem; }
  .section h2 { color: #5b4636; border-bottom: 2px solid #e8dcc0; padding-bottom: 0.3em; }
  .file-list { list-style: none; padding-left: 0; }
  .file-list li { margin-bottom: 1rem; }
  .file-list a { color: #2d5a7b; text-decoration: none; font-weight: 500; }
  .file-list a:hover { text-decoration: underline; }
  .file-note { font-size: 0.8rem; color: #8a7a5e; margin-top: 0.2em; }
  .footnote { background: #f0e8d8; border-radius: 8px; padding: 0.8rem 1.2rem; margin-top: 2rem; font-size: 0.8rem; color: #7a6b50; }
  .footnote p { margin: 0.3em 0; }
</style>
</head>
<body>
<h1>__DISPLAY_NAME__ 的数字档案</h1>
<div class="subtitle">生成日期：__GEN_DATE__ · 本档案完全离线自包含，二十年后仍可打开</div>

<div class="section">
  <h2>档案体验</h2>
  <div class="cards">
    <div class="card">
      <h2>卡通人</h2>
      <p>会说话的头像，基于角色设定生成的交互式卡通形象。</p>
      <a href="avatar.html">打开 avatar.html</a>
    </div>
    <div class="card">
      <h2>模拟对话</h2>
      <p>BYOK · 非本人 · 需自备 OpenAI 兼容 API Key（仅存本地浏览器）。</p>
      <a href="chat.html">打开 chat.html</a>
    </div>
  </div>
</div>

<div class="section">
  <h2>文字档案</h2>
  <ul class="file-list">
    <li><a href="text/persona.md">persona.md</a> <span class="file-note">性格与语言画像</span></li>
    <li><a href="text/memories.md">memories.md</a> <span class="file-note">家人确认的记忆 · Tier-1</span></li>
    <li><a href="text/timeline.md">timeline.md</a> <span class="file-note">时间线</span></li>
    <li><a href="text/rhythm.json">rhythm.json</a> <span class="file-note">语言节律统计</span></li>
  </ul>
  <p class="file-note">md/json 为纯文本开放格式，浏览器或任意文本编辑器可读。</p>
</div>

<div class="section">
  <h2>数据说明</h2>
  <p class="file-note">消息 __MSG_COUNT__ 条 · 原声语音 __VOICE_COUNT__ 条 · 视频 __VIDEO_COUNT__ 条</p>
  <div class="footnote">
    <p><strong>Tier 分级：</strong>1=家人确认 / 2=来源可溯 / 3=模型生成禁作事实</p>
    <p>合成语音非本人原声，原声均标注来源</p>
  </div>
</div>

</body>
</html>"""
    html = (html
            .replace("__DISPLAY_NAME__", display_name)
            .replace("__GEN_DATE__", gen_date)
            .replace("__MSG_COUNT__", str(msg_count))
            .replace("__VOICE_COUNT__", str(voice_count))
            .replace("__VIDEO_COUNT__", str(video_count)))
    reporter.generate(dst / "index.html", html)


def render_scripts(dst: Path, reporter: Reporter) -> None:
    """Generate start_server.bat and start_server.sh."""
    bat_content = "@echo off\r\ncd /d \"%~dp0\"\r\necho Starting: http://localhost:8020/\r\npython -m http.server 8020\r\n"
    reporter.generate(dst / "start_server.bat", bat_content, newline="")
    sh_content = "#!/bin/sh\ncd \"$(dirname \"$0\")\"\necho \"Starting: http://localhost:8020/\"\npython3 -m http.server 8020\n"
    sh_path = dst / "start_server.sh"
    reporter.generate(sh_path, sh_content)
    if not reporter.dry_run:
        try:
            os.chmod(sh_path, 0o755)
        except OSError:
            pass


def render_readme(dst: Path, display_name: str, reporter: Reporter) -> None:
    """Generate README.txt."""
    content = f"""{display_name} 的数字档案
=============

这是什么
--------
这是 {display_name} 的完整数字档案，包含文字档案、数据文件与交互页面。

怎么打开
--------
1. Windows：双击 start_server.bat
2. macOS / Linux：在终端运行 sh start_server.sh（或直接执行 ./start_server.sh）
3. 浏览器打开 http://localhost:8020/
4. 如果没有 Python，请先安装任一系列 3.x（官网 https://www.python.org/）

目录结构
--------
index.html      - 入口页
avatar.html     - 卡通人（会说话的头像）
chat.html       - 模拟对话（BYOK，需自备 API Key）
text/           - 文字档案（persona.md, memories.md, timeline.md, rhythm.json）
data/           - 原始数据与音视频（JSON/WAV/MP4/PNG 等）

格式承诺
--------
所有文件均为 JSON/WAV/MP4/PNG/MD/自包含 HTML 开放格式。
无任何外部网络依赖，无账号要求，完全离线可用。

Tier 分级
---------
1 = 家人确认的事实
2 = 来源可溯的内容
3 = 模型生成内容，禁止当作事实引用

对话页声明
----------
模拟对话页面显示的内容由 AI 模型生成，不是本人真实言论。
使用前需自备任意 OpenAI 兼容 API Key，Key 仅保存在浏览器本地。
"""
    reporter.generate(dst / "README.txt", content)


def _read_json(path: Path) -> object:
    try:
        with open(path, "r", encoding=FILE_ENCODING) as f:
            return json.load(f)
    except Exception:
        return None


def consistency_checks(dst: Path) -> tuple[bool, list[str]]:
    """Run hard checks after build; return (ok, failures)."""
    failures: list[str] = []
    ok = True

    # check 1: chat_context.json shards
    ctx_path = dst / "data" / "chat_context.json"
    if ctx_path.is_file():
        ctx = _read_json(ctx_path)
        if isinstance(ctx, dict):
            shards = ctx.get("message_shards", [])
            if isinstance(shards, list):
                for shard in shards:
                    fname = Path(str(shard)).name
                    if not (dst / "data" / fname).is_file():
                        ok = False
                        failures.append(f"missing chat shard: {fname}")

    # check 2: memories.json and transcripts.json presence
    for name in ["memories.json", "transcripts.json"]:
        if not (dst / "data" / name).is_file():
            _stderr(f"WARN: data/{name} missing (old archive compatibility)")

    # check 3: meta.json counts vs messages shards
    meta = _read_json(dst / "data" / "meta.json")
    if meta is None or not isinstance(meta, dict):
        failures.append("meta.json missing or unparseable")
        ok = False
    messages_total = 0
    if isinstance(meta, dict) and isinstance(meta.get("counts"), dict):
        try:
            expected = int(meta["counts"].get("messages", 0))
        except (TypeError, ValueError):
            ok = False
            failures.append("meta.json counts.messages invalid")
            expected = 0
        else:
            data_dir = dst / "data"
            if data_dir.is_dir():
                for p in data_dir.glob("messages_*.json"):
                    arr = _read_json(p)
                    # 分片两种形态兼容：裸数组 或 {"year","count","records":[...]}
                    if isinstance(arr, dict) and isinstance(arr.get("records"), list):
                        messages_total += len(arr["records"])
                    elif isinstance(arr, list):
                        messages_total += len(arr)
            if messages_total != expected:
                ok = False
                failures.append(f"meta counts.messages {expected} != actual shard sum {messages_total}")

    # check 4: offline scanning
    for p in dst.rglob("*.html"):
        if not p.is_file():
            continue
        try:
            content = p.read_text(encoding=FILE_ENCODING, errors="replace")
        except Exception:
            continue
        for regex in [EXTERNAL_SRC_RE, EXTERNAL_SRCSET_RE, EXTERNAL_CSSURL_RE]:
            for m in regex.finditer(content):
                ok = False
                failures.append(f"external reference in {p.relative_to(dst)}: {m.group(0)}")
                break

    return ok, failures


def build_manifest(dst: Path, slug: str, reporter: Reporter) -> None:
    """Generate archive_manifest.json atomically."""
    files: list[dict] = []
    for p in sorted(dst.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(dst)).replace(os.sep, "/")
        if rel == "archive_manifest.json":
            continue
        files.append({
            "path": rel,
            "bytes": p.stat().st_size,
            "sha256": _sha256_file(p),
        })
    files.sort(key=lambda x: x["path"])
    from datetime import datetime
    manifest = {
        "schema_version": 1,
        "person": slug,
        "generated_at": datetime.now().astimezone().replace(microsecond=0).isoformat(),
        "file_count": len(files),
        "total_bytes": sum(f["bytes"] for f in files),
        "files": files,
    }
    reporter.generate(dst / "archive_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")


def verify_manifest(dst: Path) -> tuple[bool, int, int, int, int]:
    """Verify archive_manifest.json against disk; return (ok, ok_n, changed, missing, extra)."""
    manifest_path = dst / "archive_manifest.json"
    if not manifest_path.is_file():
        _stderr("ERROR: archive_manifest.json not found")
        return False, 0, 0, 0, 0
    try:
        with open(manifest_path, "r", encoding=FILE_ENCODING) as f:
            manifest = json.load(f)
    except Exception as e:
        _stderr(f"ERROR: cannot parse manifest: {e}")
        return False, 0, 0, 0, 0

    files = manifest.get("files", [])
    if not isinstance(files, list):
        _stderr("ERROR: manifest files is not a list")
        return False, 0, 0, 0, 0

    ok_count = 0
    changed = 0
    missing = 0
    ok = True

    disk_paths = set()
    for p in dst.rglob("*"):
        if p.is_file() and p.name != "archive_manifest.json":
            disk_paths.add(str(p.relative_to(dst)).replace(os.sep, "/"))

    manifest_paths = set()
    for f in files:
        path = f.get("path")
        if not isinstance(path, str):
            ok = False
            changed += 1
            _stderr(f"MALFORMED: {str(f)[:120]}")
            continue
        manifest_paths.add(path)
        p = dst / path
        if not p.is_file():
            ok = False
            missing += 1
            _stderr(f"MISSING: {path}")
            continue
        actual_size = p.stat().st_size
        actual_sha = _sha256_file(p)
        if actual_size != f.get("bytes") or actual_sha != f.get("sha256"):
            ok = False
            changed += 1
            _stderr(f"CHANGED: {path}")
        else:
            ok_count += 1

    extra = sorted(disk_paths - manifest_paths)
    for e in extra:
        ok = False
        _stderr(f"EXTRA: {e}")

    return ok, ok_count, changed, missing, len(extra)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build self-contained archive")
    parser.add_argument("--person", required=True, help="person slug")
    parser.add_argument("--src", default=None, help="source archive_out dir")
    parser.add_argument("--out", default=None, help="destination archive_dist dir")
    parser.add_argument("--verify", action="store_true", help="verify existing manifest")
    parser.add_argument("--dry-run", action="store_true", help="print actions without writing")
    parser.add_argument('--relationship-build', help='显式新关系 build.json；无旧目录回退')
    args = parser.parse_args()

    if args.relationship_build:
        if not args.out or args.src or args.verify or args.dry_run:
            parser.error('relationship mode requires --out and excludes --src/--verify/--dry-run')
        try:
            from .build_relationship_data import package_relationship
        except ImportError:
            from build_relationship_data import package_relationship
        package_relationship(Path(args.relationship_build), Path(args.out), args.person)
        print('relationship package written')
        return 0

    slug = args.person
    if not SLUG_RE.match(slug):
        _stderr("ERROR: invalid person slug")
        return 2

    person_dir = REPO_ROOT / "people" / slug
    src = Path(args.src).resolve() if args.src else (person_dir / "archive_out").resolve()
    out = Path(args.out).resolve() if args.out else (person_dir / "archive_dist").resolve()
    person_root = person_dir.resolve()

    # path guards
    try:
        src.relative_to(person_root)
    except ValueError:
        _stderr("ERROR: src must be inside people/<person>")
        return 2
    try:
        out.relative_to(person_root)
    except ValueError:
        _stderr("ERROR: out must be inside people/<person>")
        return 2
    raw_dir = person_root / "raw"
    try:
        src.relative_to(raw_dir)
        _stderr("ERROR: src cannot be inside raw/")
        return 2
    except ValueError:
        pass
    try:
        out.relative_to(raw_dir)
        _stderr("ERROR: out cannot be inside raw/")
        return 2
    except ValueError:
        pass
    if out == src or out in src.parents or src in out.parents:
        _stderr("ERROR: out cannot equal or be parent/child of src")
        return 2

    if args.verify:
        if not out.is_dir():
            _stderr("ERROR: out directory not found")
            return 1
        ok, ok_n, changed, missing, extra = verify_manifest(out)
        print(f"verify={'ok' if ok else 'failed'} ok={ok_n} changed={changed} missing={missing} extra={extra}")
        return 0 if ok else 1

    if not src.is_dir():
        _stderr("ERROR: src invalid")
        return 2
    if not (src / "data").is_dir():
        _stderr("ERROR: src invalid")
        return 2

    reporter = Reporter(dry_run=args.dry_run)

    # 1. whitelist copy
    if not copy_tree_whitelist(src, out, reporter):
        return 2

    # 2. text layer
    archive_text_layer(person_dir, out, reporter)

    # 3. index.html
    render_index(person_dir, src, out, slug, reporter)

    # 4. scripts
    render_scripts(out, reporter)

    # 5. README
    try:
        with open(person_dir / "persona" / "relationship.json", "r", encoding=FILE_ENCODING) as f:
            rel = json.load(f)
            display_name = rel.get("display_name", slug)
    except Exception:
        display_name = slug
    render_readme(out, display_name, reporter)

    # 6. consistency checks
    checks_ok, failures = consistency_checks(out)
    for fail in failures:
        _stderr(f"ERROR: {fail}")

    # 7. manifest
    if checks_ok:
        build_manifest(out, slug, reporter)

    if reporter.dry_run:
        reporter.print_detail()

    from datetime import datetime
    file_count = 0
    total_bytes = 0
    if out.is_dir():
        for p in out.rglob("*"):
            if p.is_file() and p.name != "archive_manifest.json":
                file_count += 1
                total_bytes += p.stat().st_size
    rel_out = out.relative_to(REPO_ROOT)
    status = "ok" if checks_ok else "failed"
    print(f"archive={rel_out} files={file_count} bytes={total_bytes} copied={reporter.copied} "
          f"skipped={reporter.skipped} deleted={reporter.deleted} generated={reporter.generated} checks={status}")
    return 0 if checks_ok else 1


if __name__ == "__main__":
    sys.exit(main())
