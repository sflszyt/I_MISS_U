#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import shutil
import sys


def read_utt_map(path):
    """Read Kaldi text or wav.scp into list of (utt, content) preserving order."""
    entries = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(None, 1)
            utt = parts[0]
            content = parts[1] if len(parts) > 1 else ''
            entries.append((utt, content))
    return entries


def compute_fingerprint(entries):
    """Compute dataset fingerprint from ordered (utt, text) pairs."""
    payload = '\0'.join(utt + '\0' + text for utt, text in entries)
    return hashlib.md5(payload.encode('utf-8')).hexdigest()[:12]


def validate_meta(meta_line, fp_expected, total_expected):
    """Validate a meta line for source_dataset and source_total. Returns dataset name."""
    meta = json.loads(meta_line)
    if not isinstance(meta, dict) or not meta.get('meta'):
        raise ValueError(f"Invalid meta line: {meta_line}")

    source_ds = meta.get('source_dataset') or ''
    if source_ds and source_ds != fp_expected:
        print(f"ERROR: source_dataset mismatch for {meta.get('dataset')}: "
              f"got {source_ds}, expected {fp_expected}")
        sys.exit(1)

    source_total = meta.get('source_total') or 0
    if source_total and source_total != total_expected:
        print(f"ERROR: source_total mismatch for {meta.get('dataset')}: "
              f"got {source_total}, expected {total_expected}")
        sys.exit(1)

    return meta.get('dataset')


def validate_counts(meta, file_edits, file_drops):
    """Validate edited/dropped counts for a completed file."""
    edited = meta.get('edited') or 0
    dropped = meta.get('dropped') or 0
    actual_edits = len(file_edits)
    actual_drops = len(file_drops)
    if edited != actual_edits or dropped != actual_drops:
        print(f"WARNING: meta counts for {meta.get('dataset')}: "
              f"edited={edited} (actual {actual_edits}), dropped={dropped} (actual {actual_drops})")


def check_conflicts(applied, utt, correction_type, text):
    """
    Check for conflicting duplicate corrections.
    applied: dict utt -> (kind, text) kind = 'replace'|'drop'
    """
    if utt not in applied:
        return
    prev_kind, prev_text = applied[utt]
    if correction_type == 'replace':
        if prev_kind == 'drop':
            print(f"ERROR: conflict for utt {utt}: drop followed by text replacement")
            sys.exit(1)
        if prev_text != text:
            print(f"ERROR: conflict for utt {utt}: conflicting text replacements")
            sys.exit(1)
    else:  # drop
        if prev_kind == 'replace':
            print(f"ERROR: conflict for utt {utt}: text replacement followed by drop")
            sys.exit(1)
        # two drops are same -> tolerant


def apply_corrections(corrections_paths, original, fp):
    """
    Apply all corrections. Returns:
    - out_onts: ordered list of (utt, text) for non-dropped
    - stats: dict with replaced_count, dropped_utts
    """
    dropped = set()
    applied = {}  # utt -> (kind, text)
    unknown = set()
    replacement_count = 0
    first_meta_ds = None

    for path in corrections_paths:
        file_meta = None
        file_edits = []
        file_drops = []
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        for lineno, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"ERROR: invalid JSON in {path}:{lineno}: {e}")
                sys.exit(1)
            if not isinstance(obj, dict):
                continue
            if obj.get('meta'):
                file_meta = obj
                ds = validate_meta(line, fp, len(original))
                if first_meta_ds is None and ds:
                    first_meta_ds = ds
                continue
            if 'all_ok' in obj and obj.get('all_ok'):
                continue
            utt = obj.get('utt')
            if utt is None:
                continue
            if utt not in original_map:
                unknown.add(utt)
                continue
            if 'drop' in obj and obj.get('drop'):
                check_conflicts(applied, utt, 'drop', None)
                if utt not in applied or applied[utt] != ('drop', None):
                    applied[utt] = ('drop', None)
                    file_drops.append(utt)
                    dropped.add(utt)
            elif 'text' in obj:
                text = obj['text']
                if not isinstance(text, str) or not text.strip():
                    print(f"ERROR: empty replacement text for utt {utt} in {path}:{lineno}")
                    sys.exit(1)
                if '\ufffd' in text:
                    print(f"ERROR: replacement text for utt {utt} contains U+FFFD character")
                    sys.exit(1)
                check_conflicts(applied, utt, 'replace', text)
                if utt not in applied or applied[utt] != ('replace', text):
                    applied[utt] = ('replace', text)
                    file_edits.append(utt)
                    replacement_count += 1
            else:
                print(f"WARNING: unrecognized line in {path}:{lineno}")
        # final validation for this file
        if file_meta:
            validate_counts(file_meta, file_edits, file_drops)

    if unknown:
        print(f"ERROR: unknown utt(s): {' '.join(sorted(unknown))}")
        sys.exit(1)

    # Build final ordered list
    final_entries = []
    for utt, text in original:
        if utt in dropped:
            continue
        if utt in applied and applied[utt][0] == 'replace':
            final_entries.append((utt, applied[utt][1]))
        else:
            final_entries.append((utt, text))

    stats = {
        'replaced': replacement_count,
        'dropped': len(dropped),
        'dropped_utts': sorted(dropped),
        'kept_original': len(original) - replacement_count - len(dropped),
    }
    return final_entries, stats


def main():
    parser = argparse.ArgumentParser(
        description='Merge user corrections into Kaldi text/wav.scp for clean training list'
    )
    parser.add_argument('--text', required=True)
    parser.add_argument('--wav-scp', required=True)
    parser.add_argument('--corrections', nargs='+', required=True)
    parser.add_argument('--out-dir', required=True)
    parser.add_argument('--expect-source-dataset', default=None)
    args = parser.parse_args()

    original = read_utt_map(args.text)
    wav_entries = read_utt_map(args.wav_scp)

    if len(original) == 0:
        print("ERROR: empty text file")
        sys.exit(1)

    # Basic consistency between text and wav.scp
    text_utts = [u for u, _ in original]
    wav_utts = [u for u, _ in wav_entries]
    if text_utts != wav_utts:
        print("ERROR: text and wav.scp utt order/lists differ")
        sys.exit(1)

    fp = compute_fingerprint(original)
    print(f"Full dataset fingerprint: {fp}")

    # Handle expected source dataset
    if args.expect_source_dataset and args.expect_source_dataset != fp:
        print(f"ERROR: --expect-source-dataset {args.expect_source_dataset} != computed {fp}")
        sys.exit(1)

    # Build lookup for original text
    global original_map
    original_map = {u: t for u, t in original}

    final_entries, stats = apply_corrections(args.corrections, original, fp)

    # Write outputs
    os.makedirs(args.out_dir, exist_ok=True)
    out_text = os.path.join(args.out_dir, 'text')
    out_wav = os.path.join(args.out_dir, 'wav.scp')

    # Backup existing files
    if os.path.exists(out_text):
        shutil.copy2(out_text, out_text + '.bak')
    if os.path.exists(out_wav):
        shutil.copy2(out_wav, out_wav + '.bak')

    # Collect wav.scp matching final utts (preserve original order)
    wav_map = dict(wav_entries)
    final_wav_entries = []
    for utt, _ in final_entries:
        if utt not in wav_map:
            print(f"ERROR: missing wav.scp entry for utt {utt}")
            sys.exit(1)
        final_wav_entries.append((utt, wav_map[utt]))

    with open(out_text, 'w', encoding='utf-8') as f:
        for utt, text in final_entries:
            f.write(f"{utt}\t{text}\n")

    with open(out_wav, 'w', encoding='utf-8') as f:
        for utt, wav_path in final_wav_entries:
            f.write(f"{utt}\t{wav_path}\n")

    # Report
    new_fp = compute_fingerprint(final_entries)
    print(f"\nCorrection report:")
    print(f"  Total original: {len(original)}")
    print(f"  Replaced: {stats['replaced']}")
    print(f"  Dropped: {stats['dropped']}")
    if stats['dropped_utts']:
        print(f"  Dropped utts: {' '.join(stats['dropped_utts'])}")
    print(f"  Kept original: {stats['kept_original']}")
    print(f"  Final count: {len(final_entries)}")
    print(f"  New full dataset fingerprint: {new_fp}")


if __name__ == '__main__':
    main()
