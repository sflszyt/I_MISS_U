#!/usr/bin/env python3
"""Build visemes JSON for all voice WAV files under a person's archive.

Uses Rhubarb Lip Sync CLI to generate mouth cues per WAV, then aggregates
all results into a single compact JSON file at:
    people/<slug>/archive_out/data/avatar/visemes.json
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PERSON_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
DEFAULT_RHUBARB = Path.home() / "tools/Rhubarb-Lip-Sync-1.14.0-Windows/rhubarb.exe"
RHUBARB_TIMEOUT = 300  # seconds


def parse_args():
    parser = argparse.ArgumentParser(
        description="Batch-generate viseme timelines for voice WAVs with Rhubarb Lip Sync."
    )
    parser.add_argument("--person", required=True, help="Person slug, e.g. 'mama'")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repo root (default: parent of this script's directory)",
    )
    parser.add_argument(
        "--rhubarb",
        type=Path,
        default=DEFAULT_RHUBARB,
        help="Path to rhubarb.exe (default: %(default)s)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=6,
        help="Number of parallel workers (default: 6)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-process all WAVs, ignoring incremental cache",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Validate person slug
    if not PERSON_RE.match(args.person):
        print(
            f"ERROR: invalid person slug '{args.person}' "
            f"(must match {PERSON_RE.pattern})",
            file=sys.stderr,
        )
        sys.exit(2)

    # Validate rhubarb executable
    if not args.rhubarb.is_file():
        print(
            f"ERROR: rhubarb executable not found: {args.rhubarb}",
            file=sys.stderr,
        )
        sys.exit(2)

    # Resolve repo root
    script_dir = Path(__file__).resolve().parent
    repo_root = (args.repo_root or script_dir.parent).resolve()

    # Input / output paths
    voice_dir = repo_root / "people" / args.person / "archive_out" / "data" / "media" / "voice"
    avatar_dir = repo_root / "people" / args.person / "archive_out" / "data" / "avatar"
    visemes_path = avatar_dir / "visemes.json"

    # Gather WAV files
    if not voice_dir.is_dir():
        print(f"ERROR: voice directory not found: {voice_dir}", file=sys.stderr)
        sys.exit(1)

    wav_files = sorted(voice_dir.glob("*.wav"))
    if not wav_files:
        print(f"ERROR: no WAV files found in {voice_dir}", file=sys.stderr)
        sys.exit(1)

    # Load existing visemes data (incremental)
    existing_visemes = {}
    if not args.force and visemes_path.is_file():
        try:
            with open(visemes_path, "r", encoding="utf-8") as f:
                existing_visemes = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(
                f"WARNING: could not read existing {visemes_path}: {e}",
                file=sys.stderr,
            )
            existing_visemes = {}

    json_mtime = visemes_path.stat().st_mtime if visemes_path.is_file() else 0.0

    # Determine work queue: files to process vs. skip
    to_process = []
    skipped = 0
    for wav in wav_files:
        name = wav.name
        if not args.force and name in existing_visemes:
            wav_mtime = wav.stat().st_mtime
            if wav_mtime <= json_mtime:
                skipped += 1
                continue
        to_process.append(wav)

    # Prepare result dict (start with existing entries)
    results = dict(existing_visemes)

    if to_process:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            future_map = {
                executor.submit(process_wav, wav, args.rhubarb): wav
                for wav in to_process
            }
            failures = []
            for future in as_completed(future_map):
                wav = future_map[future]
                try:
                    name, data = future.result()
                    if data is None:
                        failures.append(wav.name)
                        # Drop any stale cached entry so the next incremental
                        # run retries this file instead of skipping it.
                        results.pop(wav.name, None)
                    else:
                        results[name] = data
                except Exception as e:  # noqa: BLE001
                    print(
                        f"ERROR: processing {wav.name}: {e}",
                        file=sys.stderr,
                    )
                    failures.append(wav.name)
                    results.pop(wav.name, None)

        if failures:
            print("FAILED files:")
            for fn in failures:
                print(f"  {fn}", file=sys.stderr)
    else:
        failures = []

    # Ensure output directory
    avatar_dir.mkdir(parents=True, exist_ok=True)

    # Write visemes.json
    with open(visemes_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, separators=(",", ":"))

    # Compute stats
    ok = len(to_process) - len(failures)
    total_cues = sum(len(v["cues"]) for v in results.values())
    out_size = visemes_path.stat().st_size

    # Print summary
    print(
        f"SUMMARY ok={ok} fail={len(failures)} skip={skipped} "
        f"cues={total_cues} bytes={out_size} out={visemes_path}"
    )

    sys.exit(1 if failures else 0)


def process_wav(wav: Path, rhubarb: Path):
    """Run Rhubarb on a single WAV, returning (filename, viseme_data) or
    (filename, None) on failure."""
    tmp_name = None
    try:
        fd, tmp_name = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        tmp_path = Path(tmp_name)

        cmd = [
            str(rhubarb),
            "-r",
            "phonetic",
            "-f",
            "json",
            "--quiet",
            "-o",
            str(tmp_path),
            str(wav),
        ]

        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=RHUBARB_TIMEOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        if proc.returncode != 0:
            stderr_tail = (proc.stderr or "").strip().splitlines()[-3:]
            print(
                f"ERROR: rhubarb failed for {wav.name} (rc={proc.returncode}): "
                f"{'; '.join(stderr_tail)}",
                file=sys.stderr,
            )
            return wav.name, None

        with open(tmp_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        duration = data.get("metadata", {}).get("duration")
        cues = data.get("mouthCues", [])
        cues_compact = [[c["start"], c["end"], c["value"]] for c in cues]

        return wav.name, {"duration": duration, "cues": cues_compact}

    except subprocess.TimeoutExpired:
        print(
            f"ERROR: rhubarb timed out for {wav.name} (> {RHUBARB_TIMEOUT}s)",
            file=sys.stderr,
        )
        return wav.name, None
    except (json.JSONDecodeError, KeyError, OSError) as e:
        print(f"ERROR: failed to parse output for {wav.name}: {e}", file=sys.stderr)
        return wav.name, None
    finally:
        if tmp_name:
            try:
                Path(tmp_name).unlink(missing_ok=True)
            except OSError:
                pass


if __name__ == "__main__":
    main()
