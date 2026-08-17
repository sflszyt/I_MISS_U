import os
import sys
import json
import shutil
import subprocess
import argparse
import time
import wave
import contextlib
import io
import re
import hashlib
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
PEOPLE_DIR = REPO_ROOT / "people"

SLUG_RE = re.compile(r"^[a-z0-9_]+$")


def ts():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def log_write(log_path, text):
    with open(log_path, "a", encoding="utf-8", newline="\n") as f:
        f.write(text)


def run_step(name, cmd_list, cwd, env, log_path):
    log_write(log_path, f"\n===== [{ts()}] STEP {name} =====\n")
    log_write(log_path, f"CMD: {' '.join(str(x) for x in cmd_list)}\n")
    proc = subprocess.run(cmd_list, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    log_write(log_path, proc.stdout)
    if proc.stderr:
        log_write(log_path, "\n--- STDERR ---\n")
        log_write(log_path, proc.stderr)
    if proc.returncode != 0:
        stderr_lines = (proc.stderr or "").strip().splitlines()
        print(f"[FAIL] step {name} rc={proc.returncode}", file=sys.stderr)
        for line in stderr_lines[-10:]:
            print(line, file=sys.stderr)
        sys.exit(1)
    log_write(log_path, f"\n===== [{ts()}] step {name} OK =====\n")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_profile(person_slug, profile_arg=None):
    person_dir = PEOPLE_DIR / person_slug
    profile_path = pathlib.Path(profile_arg) if profile_arg else person_dir / "voice" / "gsv_profile.json"
    if not profile_path.is_file():
        print(f"[ERR] profile not found: {profile_path}", file=sys.stderr)
        sys.exit(2)

    with open(profile_path, "r", encoding="utf-8") as f:
        prof = json.load(f)

    gsv_root = pathlib.Path(prof["gsv_root"])
    if not gsv_root.is_dir():
        print(f"[ERR] gsv_root not a dir: {gsv_root}", file=sys.stderr)
        sys.exit(2)
    if not (gsv_root / "GPT_SoVITS").is_dir():
        print(f"[ERR] gsv_root missing GPT_SoVITS: {gsv_root}", file=sys.stderr)
        sys.exit(2)
    pyexe = gsv_root / "runtime" / "python.exe"
    if not pyexe.is_file():
        print(f"[ERR] runtime python not found: {pyexe}", file=sys.stderr)
        sys.exit(2)

    prof["_person_dir"] = str(person_dir)
    prof["_gsv_root"] = str(gsv_root)
    prof["_work_root"] = str(pathlib.Path(prof["work_root"]))
    prof["_python"] = str(pyexe)
    return prof


def guard_out_path(p):
    prof = getattr(guard_out_path, "_profile", None)
    if prof is None:
        return
    p_res = pathlib.Path(p).resolve()
    work_root = pathlib.Path(prof["_work_root"]).resolve()
    gsv_root = pathlib.Path(prof["_gsv_root"]).resolve()
    raw_root = (pathlib.Path(prof["_person_dir"]) / "raw").resolve()
    inside_work = str(p_res).startswith(str(work_root) + os.sep) or p_res == work_root
    inside_gsv = str(p_res).startswith(str(gsv_root) + os.sep) or p_res == gsv_root
    if not (inside_work or inside_gsv):
        print(f"[ERR] write path outside work/gsv roots: {p}", file=sys.stderr)
        sys.exit(2)
    if str(p_res).startswith(str(raw_root) + os.sep) or p_res == raw_root:
        print(f"[ERR] write path inside raw tree: {p}", file=sys.stderr)
        sys.exit(2)


def exp_name_from_profile(prof, arm):
    return f"{prof['_slug']}_{arm}"


def list_path(prof, arm):
    exp = exp_name_from_profile(prof, arm)
    lpath = pathlib.Path(prof["_work_root"]) / "lists" / f"{exp}.list"
    return lpath


def read_wav_scp(prof):
    wav_scp = pathlib.Path(prof["sources"]["wav_scp"])
    if not wav_scp.is_file():
        print(f"[ERR] wav_scp not found: {wav_scp}", file=sys.stderr)
        sys.exit(2)
    m = {}
    with open(wav_scp, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or "\t" not in line:
                continue
            utt, path = line.split("\t", 1)
            m[utt] = path
    return m


def read_transcript_source(prof, arm):
    arm_cfg = prof["arms"][arm]
    mode = arm_cfg["transcript"]
    if mode == "source":
        with open(prof["sources"]["text"], "r", encoding="utf-8") as f:
            data = {}
            for line in f:
                line = line.strip()
                if not line or "\t" not in line:
                    continue
                utt, text = line.split("\t", 1)
                data[utt] = text
        return data
    else:
        # JSONL mode
        field = arm_cfg["field"]
        jsonl_path = pathlib.Path(mode)
        if not jsonl_path.is_file():
            print(f"[ERR] JSONL transcript not found: {jsonl_path}", file=sys.stderr)
            sys.exit(2)
        data = {}
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                data[rec["utt"]] = rec[field]
        return data


def g2p_apply(text, char_map):
    for k, v in char_map.items():
        text = text.replace(k, v)
    return text


def require_arm(prof, arm):
    if arm not in prof["arms"]:
        avail = ", ".join(sorted(prof["arms"].keys()))
        print(f"[ERR] unknown arm {arm}, available: {avail}", file=sys.stderr)
        sys.exit(2)


def cmd_prepare(args):
    if not SLUG_RE.match(args.person):
        print("[ERR] invalid slug", file=sys.stderr)
        sys.exit(2)
    prof = load_profile(args.person, getattr(args, "profile", None))
    prof["_slug"] = args.person
    require_arm(prof, args.arm)

    guard_out_path._profile = prof

    wav_data = read_wav_scp(prof)
    trans = read_transcript_source(prof, args.arm)

    # check utt equality
    only_wav = set(wav_data.keys()) - set(trans.keys())
    only_trans = set(trans.keys()) - set(wav_data.keys())
    if only_wav or only_trans:
        print("[ERR] transcript/wav_scp utt mismatch:")
        for u in sorted(only_wav)[:10]:
            print(f"  in wav_scp only: {u}")
        for u in sorted(only_trans)[:10]:
            print(f"  in transcript only: {u}")
        sys.exit(1)

    char_map = prof.get("g2p_char_map", {})

    outputs = []
    rejected = {"no_wav": [], "empty_text": [], "pipe_or_tab": [], "dup_basename": []}

    seen_basenames = {}
    for utt in sorted(wav_data.keys()):
        wav_path = wav_data[utt]
        text = trans[utt]
        if not pathlib.Path(wav_path).is_file():
            rejected["no_wav"].append(utt)
            continue
        text = text.strip()
        if not text:
            rejected["empty_text"].append(utt)
            continue
        if "|" in text or "\t" in text:
            rejected["pipe_or_tab"].append(utt)
            continue
        bn = pathlib.Path(wav_path).name
        if bn in seen_basenames:
            rejected["dup_basename"].append(utt)
            continue
        seen_basenames[bn] = utt
        text2 = g2p_apply(text, char_map)
        if any(k in text2 for k in char_map.keys()):
            rejected["pipe_or_tab"].append(utt)
            print(f"[WARN] residual g2p key in {utt}")
            continue
        outputs.append((wav_path, args.person, "ZH", text2))

    total = len(wav_data)
    written = len(outputs)

    for cat, lst in rejected.items():
        if lst:
            print(f"[WARN] rejected {cat}: {len(lst)}")
            for u in lst[:10]:
                print(f"  {u}")

    if written < total:
        if args.strict:
            print("[ERR] strict mode: rejected items present", file=sys.stderr)
            sys.exit(1)

    lpath = list_path(prof, args.arm)
    guard_out_path(lpath)
    lpath.parent.mkdir(parents=True, exist_ok=True)
    guard_out_path(lpath.parent)

    content_lines = []
    with open(lpath, "w", encoding="utf-8", newline="\n") as f:
        for wav_path, pers, lang, text in outputs:
            line = f"{wav_path}|{pers}|{lang}|{text}"
            f.write(line + "\n")
            content_lines.append(line)
    list_sha = sha256_file(lpath)

    _summary = {
        'cmd': 'prepare',
        'exp': exp_name_from_profile(prof, args.arm),
        'total': total,
        'written': written,
        'rejected': {k: len(v) for k, v in rejected.items()},
        'list': str(lpath),
        'sha256': list_sha[:12]
    }
    print("SUMMARY: " + json.dumps(_summary, ensure_ascii=False))


def ensure_users_pth(prof):
    gsv_root = pathlib.Path(prof["_gsv_root"])
    users_pth = gsv_root / "runtime" / "Lib" / "site-packages" / "users.pth"
    guard_out_path(users_pth)
    if not users_pth.is_file():
        content = ""
    else:
        with open(users_pth, "r", encoding="utf-8") as f:
            content = f.read()
    first_line = content.splitlines()[0] if content.strip() else ""
    if first_line != str(gsv_root):
        lines = [
            str(gsv_root),
            str(gsv_root / "GPT_SoVITS" / "BigVGAN"),
            str(gsv_root / "tools"),
            str(gsv_root / "tools" / "asr"),
            str(gsv_root / "GPT_SoVITS"),
            str(gsv_root / "tools" / "uvr5"),
        ]
        users_pth.parent.mkdir(parents=True, exist_ok=True)
        guard_out_path(users_pth.parent)
        with open(users_pth, "w", encoding="utf-8", newline="\n") as f:
            for l in lines:
                f.write(l + "\n")
        print("users.pth rewritten")


def preprocess_check_bert_invalidation(prof, exp, lpath):
    exp_dir = pathlib.Path(prof["_gsv_root"]) / "logs" / exp
    bert_dir = exp_dir / "3-bert"
    rec_file = exp_dir / ".gsv_list_sha256"
    cur_sha = sha256_file(lpath)
    if bert_dir.is_dir():
        last_sha = None
        if rec_file.is_file():
            with open(rec_file, "r", encoding="utf-8") as f:
                last_sha = f.read().strip()
        if last_sha != cur_sha:
            print(f"[INFO] .list sha changed {last_sha} -> {cur_sha}, deleting 3-bert")
            guard_out_path(bert_dir)
            shutil.rmtree(str(bert_dir))
            n2t = exp_dir / "2-name2text.txt"
            if n2t.is_file():
                guard_out_path(n2t)
                n2t.unlink()
    return cur_sha


def cmd_preprocess(args):
    if not SLUG_RE.match(args.person):
        sys.exit(2)
    prof = load_profile(args.person, getattr(args, "profile", None))
    prof["_slug"] = args.person
    arm = args.arm
    exp = exp_name_from_profile(prof, arm)
    require_arm(prof, arm)

    ensure_users_pth(prof)

    lpath = list_path(prof, arm)
    if not lpath.is_file():
        print(f"[ERR] .list not found: {lpath}", file=sys.stderr)
        sys.exit(2)

    gsv_root = pathlib.Path(prof["_gsv_root"])
    exp_dir = gsv_root / "logs" / exp
    s2_dir = exp_dir / "logs_s2_v2Pro"
    s2pow = gsv_root / "SoVITS_weights_v2Pro"
    gpow = gsv_root / "GPT_weights_v2Pro"
    for d in [exp_dir, s2_dir, s2pow, gpow]:
        guard_out_path(d)
        d.mkdir(parents=True, exist_ok=True)
        guard_out_path(d)

    cur_sha = preprocess_check_bert_invalidation(prof, exp, lpath)

    python = prof["_python"]
    env_base = os.environ.copy()
    env_base["PATH"] = str(gsv_root / "runtime") + os.pathsep + env_base.get("PATH", "")
    env_base["version"] = "v2Pro"
    env_base["inp_text"] = str(lpath)
    env_base["inp_wav_dir"] = ""
    env_base["exp_name"] = exp
    env_base["opt_dir"] = f"logs/{exp}"
    env_base["is_half"] = "True"
    env_base["i_part"] = "0"
    env_base["all_parts"] = "1"
    env_base["_CUDA_VISIBLE_DEVICES"] = "0"

    guard_out_path._profile = prof

    log_path = pathlib.Path(prof["_work_root"]) / "logs" / f"preprocess_{exp}.log"
    guard_out_path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    guard_out_path(log_path)

    # 1a
    env1 = env_base.copy()
    env1["bert_pretrained_dir"] = "GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large"
    run_step("1a", [python, "-s", "GPT_SoVITS/prepare_datasets/1-get-text.py"], str(gsv_root), env1, str(log_path))
    # rename 2-name2text-0.txt -> 2-name2text.txt
    n2t0 = exp_dir / "2-name2text-0.txt"
    n2t = exp_dir / "2-name2text.txt"
    if n2t0.is_file():
        guard_out_path(n2t0)
        if n2t.is_file():
            guard_out_path(n2t)
            n2t.unlink()
        guard_out_path(n2t)
        shutil.move(str(n2t0), str(n2t))

    # 1b
    env2 = env_base.copy()
    env2["cnhubert_base_dir"] = "GPT_SoVITS/pretrained_models/chinese-hubert-base"
    run_step("1b", [python, "-s", "GPT_SoVITS/prepare_datasets/2-get-hubert-wav32k.py"], str(gsv_root), env2, str(log_path))

    # 1b-sv
    env3 = env_base.copy()
    env3["sv_path"] = "GPT_SoVITS/pretrained_models/sv/pretrained_eres2netv2w24s4ep4.ckpt"
    run_step("1b-sv", [python, "-s", "GPT_SoVITS/prepare_datasets/2-get-sv.py"], str(gsv_root), env3, str(log_path))

    # 1c
    env4 = env_base.copy()
    env4["pretrained_s2G"] = "GPT_SoVITS/pretrained_models/v2Pro/s2Gv2Pro.pth"
    env4["s2config_path"] = "GPT_SoVITS/configs/s2v2Pro.json"
    run_step("1c", [python, "-s", "GPT_SoVITS/prepare_datasets/3-get-semantic.py"], str(gsv_root), env4, str(log_path))

    # merge 6-name2semantic
    n2s0 = exp_dir / "6-name2semantic-0.tsv"
    n2s = exp_dir / "6-name2semantic.tsv"
    if n2s0.is_file():
        guard_out_path(n2s0)
        lines = []
        with open(n2s0, "r", encoding="utf-8", newline="\n") as f:
            lines = f.read().splitlines()
        guard_out_path(n2s)
        with open(n2s, "w", encoding="utf-8", newline="\n") as f:
            f.write("item_name\tsemantic_audio\n")
            for ln in lines:
                f.write(ln + "\n")
        guard_out_path(n2s0)
        n2s0.unlink()

    # reconciliation
    n2t_lines = []
    with open(n2t, "r", encoding="utf-8") as f:
        n2t_lines = [l for l in f.read().splitlines() if l.strip()]
    bert_files = list((exp_dir / "3-bert").glob("*.pt"))
    hubert_files = list((exp_dir / "4-cnhubert").glob("*.pt"))
    wav32k_files = list((exp_dir / "5-wav32k").glob("*"))
    sv_cn_files = list((exp_dir / "7-sv_cn").glob("*.pt"))
    n2s_lines = []
    with open(n2s, "r", encoding="utf-8") as f:
        n2s_lines = [l for l in f.read().splitlines() if l.strip()]
    total_n2s = len(n2s_lines) - 1 if n2s_lines else 0

    with open(lpath, "r", encoding="utf-8") as f:
        list_cnt = len([l for l in f.read().splitlines() if l.strip()])

    counts = {
        "list": list_cnt,
        "n2t": len(n2t_lines),
        "bert": len(bert_files),
        "hubert": len(hubert_files),
        "wav32k": len(wav32k_files),
        "sv_cn": len(sv_cn_files),
        "n2s": total_n2s,
    }
    ok_all = len(set(counts.values())) == 1
    if not ok_all:
        print(f"[ERR] reconciliation mismatch: {counts}", file=sys.stderr)
        sys.exit(1)

    # write sha record
    rec_file = exp_dir / ".gsv_list_sha256"
    guard_out_path(rec_file)
    with open(rec_file, "w", encoding="utf-8", newline="\n") as f:
        f.write(cur_sha + "\n")

    _summary = {
        'cmd': 'preprocess', 'exp': exp, 'counts': counts,
        'list_sha': cur_sha[:12]
    }
    print("SUMMARY: " + json.dumps(_summary, ensure_ascii=False))


def load_s2_config(prof, exp, arm):
    gsv_root = pathlib.Path(prof["_gsv_root"])
    cfg_path = gsv_root / "GPT_SoVITS" / "configs" / "s2v2Pro.json"
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    cfg["train"]["fp16_run"] = True
    cfg["train"]["batch_size"] = prof["train"]["s2_batch"]
    cfg["train"]["epochs"] = prof["train"]["s2_epochs"]
    cfg["train"]["text_low_lr_rate"] = 0.4
    cfg["train"]["pretrained_s2G"] = "GPT_SoVITS/pretrained_models/v2Pro/s2Gv2Pro.pth"
    cfg["train"]["pretrained_s2D"] = "GPT_SoVITS/pretrained_models/v2Pro/s2Dv2Pro.pth"
    cfg["train"]["if_save_latest"] = True
    cfg["train"]["if_save_every_weights"] = True
    cfg["train"]["save_every_epoch"] = prof["train"]["s2_save_every"]
    cfg["train"]["gpu_numbers"] = "0"
    cfg["model"]["version"] = "v2Pro"
    cfg["data"]["exp_dir"] = f"logs/{exp}"
    cfg["s2_ckpt_dir"] = f"logs/{exp}"
    cfg["save_weight_dir"] = "SoVITS_weights_v2Pro"
    cfg["name"] = exp
    cfg["version"] = "v2Pro"

    out = gsv_root / "TEMP" / f"tmp_s2_{exp}.json"
    guard_out_path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    guard_out_path(out)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return out


def load_s1_config(prof, exp, arm):
    gsv_root = pathlib.Path(prof["_gsv_root"])
    cfg_path = gsv_root / "GPT_SoVITS" / "configs" / "s1longer-v2.yaml"
    try:
        import yaml
    except ImportError:
        print("[ERR] pyyaml required for s1 config", file=sys.stderr)
        sys.exit(2)

    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    cfg["train"]["precision"] = "16-mixed"
    cfg["train"]["batch_size"] = prof["train"]["s1_batch"]
    cfg["train"]["epochs"] = prof["train"]["s1_epochs"]
    cfg["train"]["save_every_n_epoch"] = prof["train"]["s1_save_every"]
    cfg["train"]["if_save_every_weights"] = True
    cfg["train"]["if_save_latest"] = True
    cfg["train"]["if_dpo"] = False
    cfg["train"]["half_weights_save_dir"] = "GPT_weights_v2Pro"
    cfg["train"]["exp_name"] = exp
    cfg["pretrained_s1"] = "GPT_SoVITS/pretrained_models/s1v3.ckpt"
    cfg["train_semantic_path"] = f"logs/{exp}/6-name2semantic.tsv"
    cfg["train_phoneme_path"] = f"logs/{exp}/2-name2text.txt"
    cfg["output_dir"] = f"logs/{exp}/logs_s1_v2Pro"

    out = gsv_root / "TEMP" / f"tmp_s1_{exp}.yaml"
    guard_out_path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    guard_out_path(out)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        yaml.dump(cfg, f, allow_unicode=True, sort_keys=False)
    return out


def read_bert_shapes_runtime(prof, exp, items):
    """Read bert .pt shapes via gsv runtime subprocess. Returns dict name->shape_last."""
    if not items:
        return {}
    gsv_root = pathlib.Path(prof["_gsv_root"])
    exp_dir = gsv_root / "logs" / exp
    bert_dir = exp_dir / "3-bert"
    if not bert_dir.is_dir():
        print(f"[ERR] 3-bert dir missing: {bert_dir}", file=sys.stderr)
        sys.exit(1)

    work_root = pathlib.Path(prof["_work_root"])
    manifest = work_root / "logs" / f"_bert_manifest_{exp}.json"
    guard_out_path(manifest)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    guard_out_path(manifest.parent)

    payload = [{"name": name, "path": str(bert_dir / f"{name}.pt")} for name in items]
    try:
        with open(manifest, "w", encoding="utf-8", newline="\n") as f:
            json.dump(payload, f, ensure_ascii=False)
    except OSError as e:
        print(f"[ERR] bert manifest write failed: {e}")
        sys.exit(1)

    script = (
        "import sys, json\n"
        "manifest = sys.argv[1]\n"
        "with open(manifest, 'r', encoding='utf-8') as f:\n"
        "    items = json.load(f)\n"
        "import torch\n"
        "for it in items:\n"
        "    t = torch.load(it['path'], map_location='cpu')\n"
        "    arr = t[0] if isinstance(t, tuple) else t\n"
        "    print(it['name'] + '\\t' + str(arr.shape[-1]))\n"
    )
    python = prof["_python"]
    try:
        proc = subprocess.run(
            [python, "-s", "-c", script, str(manifest)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(gsv_root)
        )
    except Exception as e:
        print(f"[ERR] bert shape subprocess failed to launch: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        try:
            if manifest.is_file():
                guard_out_path(manifest)
                manifest.unlink()
        except Exception:
            pass

    if proc.returncode != 0:
        stderr_lines = (proc.stderr or "").strip().splitlines()
        print("[ERR] bert shape reading failed (runtime subprocess, rc={})".format(proc.returncode), file=sys.stderr)
        for line in stderr_lines[-5:]:
            print(line, file=sys.stderr)
        print("[HINT] re-run preprocess to regenerate 3-bert", file=sys.stderr)
        sys.exit(1)

    result = {}
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line or "\t" not in line:
            continue
        name, shape = line.split("\t", 1)
        try:
            result[name] = int(shape)
        except ValueError:
            print(f"[ERR] bad shape output for {name}: {shape}", file=sys.stderr)
            sys.exit(1)
    return result


def verify_s1_bert_phones(prof, exp):
    exp_dir = pathlib.Path(prof["_gsv_root"]) / "logs" / exp
    n2t = exp_dir / "2-name2text.txt"
    bert_dir = exp_dir / "3-bert"
    if not n2t.is_file() or not bert_dir.is_dir():
        print(f"[ERR] s1 pre-check missing {n2t} or {bert_dir}")
        sys.exit(1)
    items = []
    phones_map = {}
    with open(n2t, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) != 4:
                print(f"[ERR] 2-name2text.txt malformed line (name={parts[0] if parts else '?'}, cols={len(parts)})", file=sys.stderr)
                sys.exit(1)
            name, phones = parts[0], parts[1]
            pcount = len(phones.split(" "))
            items.append(name)
            phones_map[name] = pcount

    shapes = read_bert_shapes_runtime(prof, exp, items)
    problems = []
    for name in items:
        if name not in shapes:
            problems.append((name, "no bert"))
            continue
        if shapes[name] != phones_map[name]:
            problems.append((name, f"bert {shapes[name]} phones {phones_map[name]}"))

    if problems:
        print(f"[ERR] bert/phones mismatch: {len(problems)}")
        for item, why in problems[:5]:
            print(f"  {item}: {why}")
        print("[HINT] re-run preprocess")
        sys.exit(1)


def train_s2(prof, exp, arm, log_path):
    gsv_root = pathlib.Path(prof["_gsv_root"])
    cfg = load_s2_config(prof, exp, arm)
    python = prof["_python"]
    env = os.environ.copy()
    env["PATH"] = str(gsv_root / "runtime") + os.pathsep + env.get("PATH", "")
    env["_CUDA_VISIBLE_DEVICES"] = "0"
    run_step("s2_train", [python, "-s", "GPT_SoVITS/s2_train.py", "--config", str(cfg)], str(gsv_root), env, str(log_path))

    wdir = gsv_root / "SoVITS_weights_v2Pro"
    pat = f"{exp}_e{prof['train']['s2_epochs']}_s*.pth"
    matches = list(wdir.glob(pat))
    if not matches:
        print(f"[ERR] s2 weight not found for {pat}", file=sys.stderr)
        sys.exit(1)
    # most recent by mtime
    matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0]


def train_s1(prof, exp, arm, log_path):
    gsv_root = pathlib.Path(prof["_gsv_root"])
    verify_s1_bert_phones(prof, exp)
    cfg = load_s1_config(prof, exp, arm)
    python = prof["_python"]
    env = os.environ.copy()
    env["PATH"] = str(gsv_root / "runtime") + os.pathsep + env.get("PATH", "")
    env["_CUDA_VISIBLE_DEVICES"] = "0"
    env["hz"] = "25hz"
    run_step("s1_train", [python, "-s", "GPT_SoVITS/s1_train.py", "--config_file", str(cfg)], str(gsv_root), env, str(log_path))

    wdir = gsv_root / "GPT_weights_v2Pro"
    target = wdir / f"{exp}-e{prof['train']['s1_epochs']}.ckpt"
    if not target.is_file():
        print(f"[ERR] s1 weight not found: {target}", file=sys.stderr)
        sys.exit(1)
    return target


def cmd_train(args):
    if not SLUG_RE.match(args.person):
        sys.exit(2)
    prof = load_profile(args.person, getattr(args, "profile", None))
    prof["_slug"] = args.person
    arm = args.arm
    exp = exp_name_from_profile(prof, arm)
    require_arm(prof, arm)

    guard_out_path._profile = prof

    stages = ["s2", "s1"] if args.stage == "both" else [args.stage]

    log_name = f"train_{exp}_{args.stage}.log"
    log_path = pathlib.Path(prof["_work_root"]) / "logs" / log_name
    guard_out_path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    guard_out_path(log_path)

    result_weights = {}
    for st in stages:
        if st == "s2":
            w = train_s2(prof, exp, arm, str(log_path))
            result_weights["s2"] = str(w)
        else:
            w = train_s1(prof, exp, arm, str(log_path))
            result_weights["s1"] = str(w)

    _summary = {
        'cmd': 'train', 'exp': exp, 'stage': args.stage,
        's2_weights': result_weights.get('s2'),
        's1_weights': result_weights.get('s1')
    }
    print("SUMMARY: " + json.dumps(_summary, ensure_ascii=False))


def select_latest_weight(prof, pattern_hint=None):
    gsv_root = pathlib.Path(prof["_gsv_root"])
    wdir = gsv_root / "SoVITS_weights_v2Pro"
    if pattern_hint:
        matches = list(wdir.glob(pattern_hint))
    else:
        exp = exp_name_from_profile(prof, prof["_cur_arm"])
        matches = list(wdir.glob(f"{exp}_e*_s*.pth"))
    if not matches:
        return None
    matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0]


def cmd_synth(args):
    if not SLUG_RE.match(args.person):
        sys.exit(2)
    prof = load_profile(args.person, getattr(args, "profile", None))
    prof["_slug"] = args.person
    prof["_cur_arm"] = args.arm
    arm = args.arm
    exp = exp_name_from_profile(prof, arm)
    require_arm(prof, arm)

    guard_out_path._profile = prof

    api = args.api.rstrip("/")
    import urllib.request
    import urllib.parse

    # weights
    sovits_w = pathlib.Path(args.sovits_weight) if args.sovits_weight else select_latest_weight(prof)
    if not sovits_w or not sovits_w.is_file():
        print("[ERR] sovits weight not found", file=sys.stderr)
        sys.exit(1)
    gpt_w = pathlib.Path(args.gpt_weight) if args.gpt_weight else None
    if not gpt_w:
        cand = pathlib.Path(prof["_gsv_root"]) / "GPT_weights_v2Pro" / f"{exp}-e{prof['train']['s1_epochs']}.ckpt"
        if cand.is_file():
            gpt_w = cand
    if not gpt_w or not gpt_w.is_file():
        print("[ERR] gpt weight not found", file=sys.stderr)
        sys.exit(1)

    # hot-switch
    for endpoint, wp in [("set_sovits_weights", sovits_w), ("set_gpt_weights", gpt_w)]:
        url = f"{api}/{endpoint}?weights_path={urllib.parse.quote(str(wp))}"
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                if resp.status != 200:
                    print(f"[ERR] {endpoint} returned {resp.status}", file=sys.stderr)
                    sys.exit(1)
        except Exception as e:
            print(f"[ERR] {endpoint} failed: {e}", file=sys.stderr)
            sys.exit(1)

    # reference
    ref_utt = args.ref
    if not ref_utt:
        if "default_ref" in prof and prof["default_ref"]:
            ref_utt = prof["default_ref"]
        else:
            print("[ERR] --ref required or default_ref in profile", file=sys.stderr)
            sys.exit(2)
    wav_data = read_wav_scp(prof)
    if ref_utt not in wav_data:
        print(f"[ERR] ref utt not found: {ref_utt}", file=sys.stderr)
        sys.exit(2)
    trans_api = read_transcript_source(prof, arm)
    ref_text = trans_api.get(ref_utt, "")
    if not ref_text:
        print(f"[ERR] ref utt has no transcript: {ref_utt}", file=sys.stderr)
        sys.exit(2)
    ref_text = g2p_apply(ref_text.strip(), prof.get("g2p_char_map", {}))
    ref_audio = wav_data[ref_utt]

    texts_path = pathlib.Path(args.texts)
    if not texts_path.is_file():
        print(f"[ERR] texts file not found: {texts_path}", file=sys.stderr)
        sys.exit(2)
    entries = []
    with open(texts_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            entries.append(rec)

    out_dir = pathlib.Path(prof["_work_root"]) / "synth" / f"{exp}_{args.out_tag}"
    guard_out_path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    guard_out_path(out_dir)

    report_path = out_dir / "synth_report.jsonl"
    guard_out_path(report_path)

    def do_tts(text, seed):
        payload = {
            "text": text,
            "text_lang": args.lang,
            "ref_audio_path": ref_audio,
            "prompt_text": ref_text,
            "prompt_lang": "zh",
            "seed": seed,
            "text_split_method": "cut5",
            "media_type": "wav",
            "streaming_mode": False
        }
        req = urllib.request.Request(f"{api}/tts", data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                audio_data = resp.read()
                infer_s = time.time() - t0
                return audio_data, infer_s, None
        except Exception as e:
            infer_s = time.time() - t0
            return None, infer_s, str(e)

    results = []
    for rec in entries:
        utt = rec["utt"]
        text = rec["text"]
        chars_cnt = len(re.sub(r"\s", "", text))
        attempt1_status = None
        attempt1_dur = None
        attempt1_ratio = None
        attempt1_infer = None
        attempt1_file = None
        retry_status = None
        retry_dur = None
        retry_ratio = None
        retry_infer = None
        retry_file = None

        # attempt 1
        audio, infer_s, err = do_tts(text, args.seed)
        if err:
            attempt1_status = "FAIL"
            attempt1_dur = 0.0
            attempt1_ratio = 0.0
            attempt1_infer = infer_s
        else:
            attempt1_infer = infer_s
            wpath = out_dir / f"{utt}.wav"
            guard_out_path(wpath)
            with open(wpath, "wb") as wf:
                wf.write(audio)
            # read duration directly from written file
            try:
                with wave.open(str(wpath), "rb") as wf:
                    attempt1_dur = wf.getnframes() / wf.getframerate()
            except Exception:
                attempt1_dur = 0.0
            attempt1_ratio = attempt1_dur / chars_cnt if chars_cnt > 0 else 0
            qc_min = prof["qc"]["sec_per_char_min"]
            qc_max = prof["qc"]["sec_per_char_max"]
            attempt1_status = "PASS" if qc_min <= attempt1_ratio <= qc_max else "SUSPECT"
            attempt1_file = str(wpath)

        retried = False
        if attempt1_status in ("SUSPECT", "FAIL"):
            retried = True
            seed2 = args.seed + 1000
            audio2, infer_s2, err2 = do_tts(text, seed2)
            if err2:
                retry_status = "FAIL"
                retry_dur = 0.0
                retry_ratio = 0.0
                retry_infer = infer_s2
            else:
                retry_infer = infer_s2
                wpath2 = out_dir / f"{utt}_r1.wav"
                guard_out_path(wpath2)
                with open(wpath2, "wb") as wf:
                    wf.write(audio2)
                try:
                    with wave.open(str(wpath2), "rb") as wf:
                        retry_dur = wf.getnframes() / wf.getframerate()
                except Exception:
                    retry_dur = 0.0
                retry_ratio = retry_dur / chars_cnt if chars_cnt > 0 else 0
                qc_min = prof["qc"]["sec_per_char_min"]
                qc_max = prof["qc"]["sec_per_char_max"]
                retry_status = "PASS" if qc_min <= retry_ratio <= qc_max else "SUSPECT"
                retry_file = str(wpath2)

        # pick best
        def rank(s):
            return {"PASS": 2, "SUSPECT": 1, "FAIL": 0}.get(s, 0)

        if retry_status is not None and rank(retry_status) > rank(attempt1_status):
            final_status = retry_status
            final_dur = retry_dur
            final_ratio = retry_ratio
            final_infer = retry_infer
            final_wav = retry_file
        else:
            final_status = attempt1_status
            final_dur = attempt1_dur
            final_ratio = attempt1_ratio
            final_infer = attempt1_infer
            final_wav = attempt1_file

        report = {
            "utt": utt,
            "status": final_status,
            "dur_s": round(final_dur, 3) if final_dur is not None else 0.0,
            "chars": chars_cnt,
            "ratio": round(final_ratio, 3) if final_ratio is not None else 0.0,
            "infer_s": round(final_infer, 3) if final_infer is not None else 0.0,
            "retried": retried,
            "attempt1_status": attempt1_status,
            "retry_status": retry_status if retried else None,
            "wav": final_wav
        }
        results.append(report)
        with open(report_path, "a", encoding="utf-8", newline="\n") as rf:
            rf.write(json.dumps(report, ensure_ascii=False) + "\n")

    total = len(results)
    pass_cnt = sum(1 for r in results if r["status"] == "PASS")
    suspect_cnt = sum(1 for r in results if r["status"] == "SUSPECT")
    fail_cnt = sum(1 for r in results if r["status"] == "FAIL")
    retried_cnt = sum(1 for r in results if r["retried"])

    _summary = {
        'cmd': 'synth', 'exp': exp, 'total': total, 'pass': pass_cnt,
        'suspect': suspect_cnt, 'fail': fail_cnt, 'retried': retried_cnt,
        'out_dir': str(out_dir)
    }
    print("SUMMARY: " + json.dumps(_summary, ensure_ascii=False))


def cmd_verify(args):
    if not SLUG_RE.match(args.person):
        sys.exit(2)
    prof = load_profile(args.person, getattr(args, "profile", None))
    prof["_slug"] = args.person
    arm = args.arm
    exp = exp_name_from_profile(prof, arm)
    require_arm(prof, arm)

    guard_out_path._profile = prof

    problems = []
    gsv_root = pathlib.Path(prof["_gsv_root"])
    exp_dir = gsv_root / "logs" / exp

    # .list sha
    lpath = list_path(prof, arm)
    cur_sha = sha256_file(lpath) if lpath.is_file() else None
    rec_file = exp_dir / ".gsv_list_sha256"
    rec_sha = None
    if rec_file.is_file():
        with open(rec_file, "r", encoding="utf-8") as f:
            rec_sha = f.read().strip()
    if cur_sha is None or cur_sha != rec_sha:
        problems.append(f".list sha mismatch: current={cur_sha[:12] if cur_sha else None} rec={rec_sha[:12] if rec_sha else None}")

    # counts
    n2t = exp_dir / "2-name2text.txt"
    bert_dir = exp_dir / "3-bert"
    hubert_dir = exp_dir / "4-cnhubert"
    wav32k_dir = exp_dir / "5-wav32k"
    sv_cn_dir = exp_dir / "7-sv_cn"
    n2s = exp_dir / "6-name2semantic.tsv"

    def count_lines(p):
        if not p.is_file():
            return 0
        with open(p, "r", encoding="utf-8") as f:
            return len([l for l in f.read().splitlines() if l.strip()])

    cnts = {}
    cnts["list"] = count_lines(lpath)
    cnts["n2t"] = count_lines(n2t)
    cnts["bert"] = len(list(bert_dir.glob("*.pt"))) if bert_dir.is_dir() else 0
    cnts["hubert"] = len(list(hubert_dir.glob("*.pt"))) if hubert_dir.is_dir() else 0
    cnts["wav32k"] = len(list(wav32k_dir.glob("*"))) if wav32k_dir.is_dir() else 0
    cnts["sv_cn"] = len(list(sv_cn_dir.glob("*.pt"))) if sv_cn_dir.is_dir() else 0
    n2s_cnt = count_lines(n2s)
    cnts["n2s"] = n2s_cnt - 1 if n2s_cnt else 0

    if len(set(cnts.values())) != 1:
        problems.append(f"count mismatch: {cnts}")

    # bert == phones
    if n2t.is_file() and bert_dir.is_dir():
        items = []
        phones_map = {}
        with open(n2t, "r", encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if not line.strip():
                    continue
                parts = line.split("\t")
                if len(parts) != 4:
                    print(f"[ERR] 2-name2text.txt malformed line (name={parts[0] if parts else '?'}, cols={len(parts)})", file=sys.stderr)
                    sys.exit(1)
                name, phones = parts[0], parts[1]
                pcount = len(phones.split(" "))
                items.append(name)
                phones_map[name] = pcount
        if items:
            shapes = read_bert_shapes_runtime(prof, exp, items)
            for name in items:
                if name not in shapes:
                    problems.append(f"{name}: no bert")
                    continue
                if shapes[name] != phones_map[name]:
                    problems.append(f"{name}: bert {shapes[name]} phones {phones_map[name]}")

    # weights
    s2w = list((gsv_root / "SoVITS_weights_v2Pro").glob(f"{exp}_e*.pth")) if (gsv_root / "SoVITS_weights_v2Pro").is_dir() else []
    s1w = list((gsv_root / "GPT_weights_v2Pro").glob(f"{exp}-e*.ckpt")) if (gsv_root / "GPT_weights_v2Pro").is_dir() else []
    if not s2w:
        problems.append("no s2 weights found")
    if not s1w:
        problems.append("no s1 weights found")

    if problems:
        print(f"[VERIFY FAIL] {len(problems)} issue(s):")
        for p in problems[:20]:
            print(f"  - {p}")
        sys.exit(1)
    _summary = {
        'cmd': 'verify', 'exp': exp, 'ok': True, 'counts': cnts
    }
    print("SUMMARY: " + json.dumps(_summary, ensure_ascii=False))
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(prog="gsv_pipeline", description="GPT-SoVITS v2Pro pipeline")
    subparsers = parser.add_subparsers(dest="command")

    p_prep = subparsers.add_parser("prepare", help="build .list")
    p_prep.add_argument("--person", required=True)
    p_prep.add_argument("--arm", required=True)
    p_prep.add_argument("--profile", default=None)
    p_prep.add_argument("--strict", dest="strict", action="store_true", default=True)
    p_prep.add_argument("--no-strict", dest="strict", action="store_false")
    p_prep.set_defaults(func=cmd_prepare)

    p_prep2 = subparsers.add_parser("preprocess", help="data prep")
    p_prep2.add_argument("--person", required=True)
    p_prep2.add_argument("--arm", required=True)
    p_prep2.add_argument("--profile", default=None)
    p_prep2.set_defaults(func=cmd_preprocess)

    p_tr = subparsers.add_parser("train", help="train s2/s1")
    p_tr.add_argument("--person", required=True)
    p_tr.add_argument("--arm", required=True)
    p_tr.add_argument("--profile", default=None)
    p_tr.add_argument("--stage", choices=["both", "s2", "s1"], default="both")
    p_tr.set_defaults(func=cmd_train)

    p_sy = subparsers.add_parser("synth", help="synthesize")
    p_sy.add_argument("--person", required=True)
    p_sy.add_argument("--arm", required=True)
    p_sy.add_argument("--texts", required=True)
    p_sy.add_argument("--lang", choices=["all_zh", "all_yue", "zh", "yue", "en"], required=True)
    p_sy.add_argument("--ref", default=None)
    p_sy.add_argument("--api", default="http://127.0.0.1:9880")
    p_sy.add_argument("--seed", type=int, default=42)
    p_sy.add_argument("--out-tag", default="default")
    p_sy.add_argument("--profile", default=None)
    p_sy.add_argument("--sovits-weight", default=None)
    p_sy.add_argument("--gpt-weight", default=None)
    p_sy.set_defaults(func=cmd_synth)

    p_v = subparsers.add_parser("verify", help="verify pipeline")
    p_v.add_argument("--person", required=True)
    p_v.add_argument("--arm", required=True)
    p_v.add_argument("--profile", default=None)
    p_v.set_defaults(func=cmd_verify)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        print("unknown command", file=sys.stderr)
        sys.exit(2)
    args.func(args)


if __name__ == "__main__":
    main()