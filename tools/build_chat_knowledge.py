# -*- coding: utf-8 -*-
"""Build chat knowledge files (memories.json and transcripts.json) for the BYOK archive."""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


PERSON_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _is_under_raw(path: Path, raw_dir: Path) -> bool:
    """Return True if path is inside or equal to the raw directory."""
    try:
        path.resolve().relative_to(raw_dir.resolve())
        return True
    except ValueError:
        return False


def _validate_paths(args, args_p: argparse.Namespace, person_dir: Path, raw_dir: Path,
                    repo_root: Path) -> None:
    """Validate all input/output paths against raw and person-tree guards."""
    for attr in ("candidates", "voice_transcripts", "video_transcripts"):
        p = Path(getattr(args_p, attr)).resolve()
        if _is_under_raw(p, raw_dir):
            print(f"ERROR: path resolves under raw/: {p}", file=sys.stderr)
            sys.exit(2)

    out_dir = Path(args_p.out_dir).resolve()
    if not _is_under_raw(out_dir, raw_dir) and out_dir != raw_dir.resolve():
        # out-dir must be inside person tree (and not raw)
        try:
            out_dir.relative_to(person_dir.resolve())
        except ValueError:
            print("ERROR: out-dir outside person tree", file=sys.stderr)
            sys.exit(2)
    # Final raw check for out-dir too
    if _is_under_raw(out_dir, raw_dir):
        print(f"ERROR: path resolves under raw/: {out_dir}", file=sys.stderr)
        sys.exit(2)


def _resolve_default(repo_root: Path, person: str, suffix: str) -> Path:
    """Build a default path under people/<person>."""
    return repo_root / "people" / person / suffix


def load_candidates(path: Path) -> tuple[list[dict], int]:
    """Load candidate lines, skipping malformed ones, return (candidates, bad_lines)."""
    candidates = []
    bad_lines = 0
    if not path.exists():
        return candidates, bad_lines
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                bad_lines += 1
                continue
            if not isinstance(obj, dict) or "candidate_id" not in obj:
                bad_lines += 1
                continue
            candidates.append(obj)
    return candidates, bad_lines


def load_transcripts(path: Path) -> tuple[list[dict], int]:
    """Load transcript lines, skipping malformed ones, return (transcripts, bad_lines)."""
    transcripts = []
    bad_lines = 0
    if not path.exists():
        return transcripts, bad_lines
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                bad_lines += 1
                continue
            if not isinstance(obj, dict) or "record_id" not in obj:
                bad_lines += 1
                continue
            transcripts.append(obj)
    return transcripts, bad_lines


def build_memories(candidates: list[dict], person: str) -> dict:
    """Build the memories.json top-level object from confirmed candidates."""
    entries = []
    for cand in candidates:
        if cand.get('schema_version') == 2:
            try:
                from .memory_evidence import validate_candidate, decision_is_current
            except ImportError:
                from memory_evidence import validate_candidate, decision_is_current
            validate_candidate(cand)
            if cand.get('person') != person or not decision_is_current(cand):
                continue
        if cand.get("status") != "confirmed":
            continue
        title = cand.get("user_title") or cand.get("title") or ""
        texts = []
        for exc in cand.get("excerpts") or []:
            txt = exc.get("text")
            if isinstance(txt, str) and txt.strip():
                texts.append(txt)
        entry = {
            "id": cand["candidate_id"],
            "date": cand.get("date", ""),
            "title": title,
            "kind_label": cand.get("kind_label", ""),
            "texts": texts,
            "tier": 1,
        }
        note = cand.get("user_note")
        if cand.get('schema_version') == 2:
            entry['schema_version'] = 2
            for key in ('person', 'relationship_id', 'evidence_revision', 'evidence_records', 'provenance', 'decision'):
                entry[key] = cand[key]
        if isinstance(note, str) and note.strip():
            entry["note"] = note
        entries.append(entry)

    entries.sort(key=lambda e: (e["date"] or "", e["id"] or ""))
    return {
        "schema_version": 1,
        "person": person,
        "kind": "memories",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "entries": entries,
    }


def build_transcript_entries(transcripts: list[dict], media: str) -> list[dict]:
    """Build transcript entries from raw transcript records."""
    entries = []
    for rec in transcripts:
        text = rec.get("text")
        if rec.get('schema_version') == 2:
            if 'verification_contract' in rec:
                try:
                    from .transcript_evidence import validate_verified_transcript
                except ImportError:
                    from transcript_evidence import validate_verified_transcript
                validate_verified_transcript(rec)
            if (rec.get('speaker_status') != 'confirmed' or rec.get('single_speaker') is not True
                    or rec.get('transcript_status') != 'corrected'
                    or rec.get('speaker_id') in (None, '', 'unknown')
                    or rec.get('source_kind') != 'real_recording'):
                continue
            if not isinstance(text, str) or not text.strip():
                continue
            entries.append(dict(rec, media=media, tier=2,
                                is_subject=rec['speaker_id'] == rec.get('person')))
            continue
        if not (rec.get("is_subject") is True and isinstance(text, str) and text.strip()):
            continue
        timestamp = rec.get("timestamp", "")
        date_str = ""
        if isinstance(timestamp, str) and len(timestamp) >= 10 and ISO_DATE_RE.match(timestamp[:10]):
            date_str = timestamp[:10]
        try:
            duration_ms = int(rec.get("duration_ms", 0))
        except (TypeError, ValueError):
            duration_ms = 0
        entries.append({
            "record_id": rec["record_id"],
            "timestamp": timestamp,
            "date": date_str,
            "media": media,
            "text": text,
            "quality": rec.get("quality", ""),
            "duration_ms": duration_ms,
            "tier": 2,
        })
    return entries


def write_atomic(path: Path, obj: dict) -> None:
    """Atomically write a JSON object to path (UTF-8 no BOM, indent 2, trailing newline)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(path.suffix + ".part")
    with part.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(part, path)


def main() -> int:
    """Parse args, build output files, print status line."""
    parser = argparse.ArgumentParser(description="Build chat knowledge files for BYOK.")
    parser.add_argument("--person", required=True, help="Person slug")
    parser.add_argument("--candidates", default=None, help="Path to candidates.jsonl")
    parser.add_argument("--voice-transcripts", default=None, help="Path to voice_transcripts.jsonl")
    parser.add_argument("--video-transcripts", default=None, help="Path to video_transcripts.jsonl")
    parser.add_argument("--out-dir", default=None, help="Output directory")
    args = parser.parse_args()

    if not PERSON_SLUG_RE.match(args.person):
        print("ERROR: invalid person slug", file=sys.stderr)
        return 2

    repo_root = Path(__file__).resolve().parent.parent
    person_dir = repo_root / "people" / args.person
    raw_dir = person_dir / "raw"

    candidates_path = Path(args.candidates) if args.candidates else _resolve_default(
        repo_root, args.person, "memories/candidates.jsonl")
    voice_path = Path(args.voice_transcripts) if args.voice_transcripts else _resolve_default(
        repo_root, args.person, "normalized/voice_transcripts.jsonl")
    video_path = Path(args.video_transcripts) if args.video_transcripts else _resolve_default(
        repo_root, args.person, "normalized/video_transcripts.jsonl")
    out_dir = Path(args.out_dir) if args.out_dir else _resolve_default(
        repo_root, args.person, "archive_out/data")

    _validate_paths(args, argparse.Namespace(
        candidates=str(candidates_path),
        voice_transcripts=str(voice_path),
        video_transcripts=str(video_path),
        out_dir=str(out_dir),
    ), person_dir, raw_dir, repo_root)

    cand_exists = candidates_path.exists()
    voice_exists = voice_path.exists()
    video_exists = video_path.exists()
    if not (cand_exists or voice_exists or video_exists):
        print("ERROR: no input available", file=sys.stderr)
        return 2

    total_bad = 0

    memories_count = "skipped"
    if cand_exists:
        cands, bad = load_candidates(candidates_path)
        total_bad += bad
        if cands:
            memories = build_memories(cands, args.person)
            write_atomic(out_dir / "memories.json", memories)
            memories_count = len(memories["entries"])
        else:
            print("WARN: candidates.jsonl empty, memories.json not generated", file=sys.stderr)
    else:
        print("WARN: candidates.jsonl missing, memories.json not generated", file=sys.stderr)

    voice_count = 0
    voice_entries = []
    if voice_exists:
        vt, bad = load_transcripts(voice_path)
        total_bad += bad
        if vt:
            voice_entries = build_transcript_entries(vt, "voice")
            voice_count = len(voice_entries)
        else:
            print("WARN: voice_transcripts.jsonl empty, skipped", file=sys.stderr)
    else:
        print("WARN: voice_transcripts.jsonl missing, skipped", file=sys.stderr)

    video_count = 0
    video_entries = []
    if video_exists:
        vdt, bad = load_transcripts(video_path)
        total_bad += bad
        if vdt:
            video_entries = build_transcript_entries(vdt, "video")
            video_count = len(video_entries)
        else:
            print("WARN: video_transcripts.jsonl empty, skipped", file=sys.stderr)
    else:
        print("WARN: video_transcripts.jsonl missing, skipped", file=sys.stderr)

    combined = voice_entries + video_entries
    if combined:
        combined.sort(key=lambda e: (e["timestamp"] or "", e["record_id"] or ""))
        transcripts_obj = {
            "schema_version": 1,
            "person": args.person,
            "kind": "transcripts",
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "entries": combined,
        }
        write_atomic(out_dir / "transcripts.json", transcripts_obj)
    else:
        print("WARN: no transcript entries, transcripts.json not generated", file=sys.stderr)

    # Relative path for stdout report
    out_resolved = out_dir.resolve()
    try:
        out_rel = out_resolved.relative_to(repo_root)
        out_str = str(out_rel)
    except ValueError:
        out_str = str(out_resolved)

    print(
        f"memories={memories_count} "
        f"transcripts_voice={voice_count} "
        f"transcripts_video={video_count} "
        f"bad_lines={total_bad} "
        f"out={out_str}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
