"""只读 CPU 训练准备审计；输出元数据与可疑线索，永不授权训练。"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import math
from pathlib import Path

try:
    from .viewpoint_manifest import read_json, read_jsonl, safe_path, no_links, sha256, digest, load_dataset
    from .build_relationship_data import new_output, write_json, write_jsonl
    from .build_mobile_review import training_anchors, checked_path
    from .build_training_manifest import exclusion_reasons
    from .transcript_evidence import make_verified_transcript
    from .prepare_voice_upgrade import mapping
except ImportError:
    from viewpoint_manifest import read_json, read_jsonl, safe_path, no_links, sha256, digest, load_dataset
    from build_relationship_data import new_output, write_json, write_jsonl
    from build_mobile_review import training_anchors, checked_path
    from build_training_manifest import exclusion_reasons
    from transcript_evidence import make_verified_transcript
    from prepare_voice_upgrade import mapping


PLAN_FIELDS = ('record_id', 'audio_sha256', 'revision', 'dedup_group', 'split', 'audio_file')
RATE = 8000
MIN_SECONDS = .5
MIN_RMS = .001
THRESHOLD = .94


def dependencies_available():
    return all(importlib.util.find_spec(x) for x in ('numpy', 'scipy', 'soundfile'))


def planned_audio_path(root, reference):
    """冻结计划可用绝对引用，但必须仍在本次 reviewed build 内且不经过链接。"""
    if not isinstance(reference, str) or not reference:
        raise ValueError('invalid planned audio reference')
    path = Path(reference)
    if not path.is_absolute():
        return safe_path(root, reference).resolve()
    if '..' in path.parts:
        raise ValueError('unsafe planned audio path')
    path = checked_path(path)
    try:
        path.relative_to(root)
    except ValueError:
        raise ValueError('planned audio escapes reviewed build') from None
    return path


def approved_inputs(training_dir, split_plan):
    """重算 dataset/ASR 原候选及审核投影；不把自洽摘要当作来源证明。"""
    root, plan_path = checked_path(training_dir), checked_path(split_plan)
    summary = read_json(root / 'summary.json')
    candidates = read_jsonl(root / 'candidates.jsonl')
    eligible = read_jsonl(root / 'eligible.jsonl')
    plan = read_json(plan_path)
    if (summary.get('schema_version') != 1 or summary.get('training_started') is not False
            or plan.get('schema_version') != 1 or plan.get('ready_for_training') is not False
            or checked_path(plan.get('source_build', '')) != root
            or plan.get('source_eligible_sha256') != sha256(root / 'eligible.jsonl')):
        raise ValueError('summary or split plan binding mismatch')
    if not candidates or len({c['record_id'] for c in candidates}) != len(candidates):
        raise ValueError('missing or duplicate candidates')
    pending = []
    for c in candidates:
        base = {k:copy.deepcopy(v) for k, v in c.items() if k not in ('review', 'exclusion_reasons')}
        base['exclusion_reasons'] = exclusion_reasons(base, None)
        pending.append(base)
    inputs = training_anchors(summary, pending)
    overlays = []
    for entry in summary['inputs']:
        path = checked_path(entry['path'])
        if path.suffix.lower() == '.json':
            value = read_json(path)
            if isinstance(value, dict) and 'reviews' in value:
                if value.get('schema_version') != 1 or not isinstance(value['reviews'], list):
                    raise ValueError('invalid anchored reviews')
                overlays.append(value['reviews'])
    if len(overlays) != 1:
        raise ValueError('exactly one anchored human review overlay required')
    reviews = {r['record_id']:r for r in overlays[0]}
    if len(reviews) != len(overlays[0]) or set(reviews) - {c['record_id'] for c in candidates}:
        raise ValueError('duplicate or unknown review identity')
    expected, verified, reconstructed, seen = [], [], [], set()
    for base in pending:
        c = copy.deepcopy(base)
        review = reviews.get(c['record_id'])
        c['exclusion_reasons'] = exclusion_reasons(c, review)
        if review:
            if any(review.get(k) != c.get(k) for k in ('record_id', 'revision', 'audio_sha256')):
                raise ValueError('stale approval')
            c['review'] = review
        if not c['exclusion_reasons']:
            verified.append(make_verified_transcript(c))
            if c['dedup_group'] in seen:
                c['exclusion_reasons'].append('duplicate_audio')
            else:
                seen.add(c['dedup_group'])
                expected.append(dict(c, text=review['text'], speaker_id=c['person'],
                                     speaker_status='confirmed', transcript_status='corrected',
                                     source_kind='real_recording', single_speaker=True,
                                     quality_status='approved', training_eligible=True))
        reconstructed.append(c)
        if c.get('audio_file'):
            audio = safe_path(root, c['audio_file'])
            if sha256(audio) != c['audio_sha256']:
                raise ValueError('build WAV changed')
            inputs.append(audio)
    excluded = [c for c in reconstructed if c['exclusion_reasons']]
    if (reconstructed != candidates or expected != eligible or not eligible
            or verified != read_jsonl(root / 'verified_transcripts.jsonl')
            or excluded != read_jsonl(root / 'excluded.jsonl')
            or any(summary.get(k) != n for k, n in (
                ('candidates', len(candidates)), ('eligible', len(eligible)),
                ('excluded', len(excluded)), ('verified_transcripts', len(verified))))):
        raise ValueError('reviewed build differs from source and approval evidence')
    planned = {}
    for split in ('train', 'validation'):
        if not isinstance(plan.get(split), list):
            raise ValueError('missing split list')
        for entry in plan[split]:
            if entry.get('split') != split or entry.get('record_id') in planned:
                raise ValueError('unknown split or duplicate planned identity')
            planned_audio_path(root, entry.get('audio_file'))
            planned[entry['record_id']] = entry
    if set(planned) != {c['record_id'] for c in eligible}:
        raise ValueError('plan must cover all approved identities exactly once')
    for c in eligible:
        entry = planned[c['record_id']]
        if (any(entry.get(k) != c.get(k) for k in PLAN_FIELDS if k != 'audio_file')
                or planned_audio_path(root, entry.get('audio_file')) != safe_path(root, c['audio_file']).resolve()):
            raise ValueError('planned candidate identity mismatch')
    for field in ('record_id', 'audio_sha256', 'dedup_group'):
        groups = [{c[field] for c in eligible if c['split'] == split} for split in ('train', 'validation')]
        if groups[0] & groups[1]:
            raise ValueError('cross split identity leak')
    inputs.extend(root / name for name in ('summary.json', 'candidates.jsonl', 'eligible.jsonl',
                                         'excluded.jsonl', 'verified_transcripts.jsonl'))
    inputs.append(plan_path)
    return eligible, list(dict.fromkeys(inputs))


def legacy_inputs(legacy_dir, source_manifest=None, native_manifest=None, person_root=None):
    root = checked_path(legacy_dir)
    files = [root / name for name in ('text', 'wav.scp', 'utt2spk')]
    texts, wavs, speakers = [mapping(p) for p in files]
    if not texts or texts.keys() != wavs.keys() or texts.keys() != speakers.keys():
        raise ValueError('legacy text/wav.scp/utt2spk must map one to one')
    sources = {}
    if source_manifest:
        source_manifest = checked_path(source_manifest)
        for row in read_jsonl(source_manifest):
            key = row.get('seg_key')
            if (key not in wavs or key in sources or not isinstance(row.get('orig_key'), str)
                    or not row['orig_key'] or any(type(row.get(k)) not in (int, float)
                                                or not math.isfinite(row[k]) for k in ('start_s', 'end_s'))
                    or not 0 <= row['start_s'] < row['end_s']):
                raise ValueError('invalid or duplicate legacy source mapping')
            sources[key] = row
        if sources.keys() != wavs.keys():
            raise ValueError('legacy source mapping must cover all utterances')
        files.append(source_manifest)
    native_sources = {}
    if bool(native_manifest) != bool(person_root) or (native_manifest and not source_manifest):
        raise ValueError('native source metadata requires person root and segment source manifest')
    if native_manifest:
        native_manifest, person_root = checked_path(native_manifest), checked_path(person_root)
        # 明确只接受现行 normalized 入口；scrub 前备份不成为本工具的准入依据。
        if native_manifest != safe_path(person_root, 'normalized/wechat_voice_manifest.jsonl'):
            raise ValueError('native manifest must be the current person normalized manifest')
        wanted = {r['orig_key'] for r in sources.values()}
        for row in read_jsonl(native_manifest):
            reference = row.get('file_ref')
            if not isinstance(reference, str):
                raise ValueError('invalid legacy native source reference')
            key = Path(reference).stem
            if key not in wanted:
                continue
            native_id = row.get('provenance', {}).get('native_id')
            if (key in native_sources or not native_id or str(row.get('svr_id')) != str(native_id)
                    or not row.get('sender_wxid')):
                raise ValueError('ambiguous legacy native source metadata')
            audio = safe_path(person_root, reference)
            status = 'missing_original_audio'
            if audio.is_file():
                if sha256(audio) != row.get('sha256'):
                    raise ValueError('legacy original source hash mismatch')
                files.append(audio)
                status = 'original_audio_hash_verified'
            native_sources[key] = dict(native_key=digest(['wechat', str(native_id), row['sender_wxid']]),
                native_bridge_basis='manifest_native_id_via_orig_key_filename',
                original_audio_status=status, cross_corpus_bridge_verified=False)
        files.append(native_manifest)
    rows = []
    for key, value in wavs.items():
        if any(token in value for token in ('|', '\n', '\r', '<', '>')):
            raise ValueError('legacy wav.scp commands are forbidden')
        path = Path(value)
        path = checked_path(path if path.is_absolute() else root / path)
        if not path.is_file():
            raise ValueError('missing legacy audio')
        source = sources.get(key)
        group = dict(basis='filename_heuristic', key=path.stem, verified_native_source=False)
        if source:
            linked = Path(source['wav'])
            linked = checked_path(linked if linked.is_absolute() else source_manifest.parent / linked)
            if linked != path:
                raise ValueError('legacy source WAV mismatch')
            group = dict(basis='legacy_manifest_orig_key', key=source['orig_key'],
                         scope=str(source_manifest), start_s=source['start_s'], end_s=source['end_s'],
                         verified_native_source=False)
            group.update(native_sources.get(source['orig_key'], dict(
                native_bridge_basis='unresolved', original_audio_status='not_verified',
                cross_corpus_bridge_verified=False)))
        rows.append(dict(id=key, audio=str(path), audio_sha256=sha256(path), source_group=group))
        files.append(path)
    return rows, files


def load_audio(path):
    """真实重采样；错误仅输出类别，避免异常中泄露转写或私有路径。"""
    import numpy as np
    import soundfile as sf
    from scipy.signal import resample_poly
    try:
        values, rate = sf.read(str(path), dtype='float64', always_2d=True)
        if rate <= 0 or values.shape[1] != 1 or not len(values) or not np.isfinite(values).all():
            raise ValueError('invalid mono audio')
        values = values[:, 0]
        if rate != RATE:
            factor = math.gcd(rate, RATE)
            values = resample_poly(values, RATE // factor, rate // factor)
        values -= values.mean()
        rms = float(np.sqrt(np.mean(values * values)))
        active = float(np.mean(np.abs(values) >= MIN_RMS))
        status = 'ok' if len(values) >= MIN_SECONDS * RATE and rms >= MIN_RMS and active >= .1 else 'indeterminate'
        return dict(status=status, samples=values, duration_seconds=len(values)/RATE,
                    rms=rms, active_fraction=active,
                    reason=None if status == 'ok' else 'insufficient_duration_or_energy')
    except (OSError, ValueError, RuntimeError):
        return dict(status='error', reason='unreadable_or_invalid_audio')


def compare_audio(a, b):
    """各偏移的重叠区独立去均值/归一化；仅筛查至少80%短音频的重叠。"""
    import numpy as np
    from scipy.signal import correlate, correlation_lags
    if a['status'] != 'ok' or b['status'] != 'ok':
        return dict(status='indeterminate', suspected_duplicate=False, score=None,
                    reason='audio_unreadable_or_insufficient_energy')
    x, y = a['samples'], b['samples']
    lags = correlation_lags(len(x), len(y), mode='full')
    starts_x, starts_y = np.maximum(lags, 0), np.maximum(-lags, 0)
    lengths = np.minimum(len(x)-starts_x, len(y)-starts_y)
    mask = lengths >= max(int(MIN_SECONDS*RATE), math.ceil(.8*min(len(x), len(y))))
    sx, sy, n = starts_x[mask], starts_y[mask], lengths[mask]
    if not len(n):
        return dict(status='indeterminate', suspected_duplicate=False, score=None, reason='no_valid_overlap')
    def moments(values, starts):
        sums = np.r_[0., np.cumsum(values)]
        squares = np.r_[0., np.cumsum(values*values)]
        total = sums[starts+n]-sums[starts]
        energy = np.maximum(0., squares[starts+n]-squares[starts]-total*total/n)
        return total, energy
    sum_x, energy_x = moments(x, sx)
    sum_y, energy_y = moments(y, sy)
    valid = (energy_x/n >= MIN_RMS**2) & (energy_y/n >= MIN_RMS**2)
    if not valid.any():
        return dict(status='indeterminate', suspected_duplicate=False, score=None, reason='no_energetic_overlap')
    numerator = correlate(x, y, mode='full', method='fft')[mask] - sum_x*sum_y/n
    scores = np.zeros(len(n))
    scores[valid] = np.abs(numerator[valid]) / np.sqrt(energy_x[valid]*energy_y[valid])
    best = int(np.argmax(scores))
    score = min(1., float(scores[best]))
    return dict(status='compared', suspected_duplicate=score >= THRESHOLD, score=score,
                lag_seconds=float(lags[mask][best]/RATE), overlap_seconds=float(n[best]/RATE))


def audit(training_dir, split_plan, legacy_data_dir, out, legacy_source_manifest=None,
          legacy_native_manifest=None, legacy_person_root=None):
    # 提前保护输出；后面将所有递归来源及音频也加入保护集合。
    out = new_output(out, [Path(training_dir), Path(split_plan), Path(legacy_data_dir)] +
                     [Path(p) for p in (legacy_source_manifest, legacy_native_manifest, legacy_person_root) if p])
    eligible, inputs = approved_inputs(training_dir, split_plan)
    legacy, old_inputs = legacy_inputs(legacy_data_dir, legacy_source_manifest,
                                      legacy_native_manifest, legacy_person_root)
    inputs.extend(old_inputs)
    out = new_output(out, inputs + [Path(training_dir), Path(legacy_data_dir)] +
                     ([Path(legacy_person_root)] if legacy_person_root else []))
    if not dependencies_available():
        raise ValueError('CPU audit requires existing numpy/scipy/soundfile environment')
    frozen = [{'path':str(p.resolve()), 'sha256':sha256(p)} for p in dict.fromkeys(inputs)]
    root = checked_path(training_dir)
    native = {}
    for entry in read_json(root / 'summary.json')['inputs']:
        path = Path(entry['path'])
        if path.name == 'dataset.json':
            _, records = load_dataset(path)
            for r in records:
                prov = r['provenance']
                native[r['record_id']] = dict(basis='dataset_native_id',
                    key=prov.get('native_id'), scope=r.get('source'),
                    native_key=digest([r.get('source'), str(prov.get('native_id')), r.get('sender_wxid')]),
                    account=prov.get('source_account_id'), verified_native_source=bool(prov.get('native_id')))
    new = [dict(id=c['record_id'], audio=str(safe_path(root, c['audio_file'])),
                audio_sha256=c['audio_sha256'], source_group=native[c['record_id']], split=c['split'])
           for c in eligible]
    audios = {r['audio']:load_audio(r['audio']) for r in new+legacy}
    comparisons = []
    def compare(left, right, kind):
        result = compare_audio(audios[left['audio']], audios[right['audio']])
        exact = left['audio_sha256'] == right['audio_sha256']
        # 即使字节完全一致，静音/不可读也只能报告文件相等，不能认定有效声音重复。
        result.update(kind=kind, left_id=left['id'], right_id=right['id'], file_sha_equal=exact)
        if result['status'] == 'compared' and exact:
            result['suspected_duplicate'] = True
        lg, rg = left['source_group'], right['source_group']
        result['native_source_match'] = bool(kind == 'new_new' and lg['verified_native_source']
            and rg['verified_native_source'] and lg['native_key'] == rg['native_key'])
        result['legacy_native_metadata_match'] = bool(kind == 'new_legacy' and rg.get('native_key')
                                                     and lg['native_key'] == rg['native_key'])
        result['filename_heuristic_match'] = Path(left['audio']).stem == Path(right['audio']).stem
        result['requires_resolution'] = (result['suspected_duplicate'] or result['native_source_match']
                                         or result['legacy_native_metadata_match']
                                         or result['status'] != 'compared')
        comparisons.append(result)
    for i, row in enumerate(new):
        for other in new[i+1:]:
            compare(row, other, 'new_new')
        for other in legacy:
            compare(row, other, 'new_legacy')
    # 防止长时间相关运算期间输入被替换；不留下看似有效的半份报告。
    if any(sha256(Path(e['path'])) != e['sha256'] for e in frozen):
        raise ValueError('input changed during audit')
    metadata = []
    for c, row in zip(eligible, new):
        metadata.append(dict(**{k:c[k] for k in PLAN_FIELDS}, audio=row['audio'],
            language=c.get('language', 'unknown'), ready_for_training=False,
            review_evidence=dict(review_sha256=digest(c['review']),
                                 candidate_revision=c['revision'], summary_sha256=sha256(root/'summary.json')),
            source_group=row['source_group'], pending_gates=['language_human_confirmation',
                'cross_corpus_source_verification', 'duplicate_conflict_resolution', 'independent_training_lists']))
    plan = read_json(split_plan)
    report = dict(schema_version=1, ready_for_training=False, training_started=False,
        notice='Screening clues only; no match does not prove absence of leakage. No speaker or language inference.',
        receipt_chain=dict(reverified=False, basis='anchored review overlay; receipt database chain not reverified',
                           receipt_reference=plan.get('source_review_receipt'), package_revision=plan.get('package_revision')),
        algorithm=dict(name='DC-removed resample_poly normalized FFT cross correlation', sample_rate=RATE,
                       threshold=THRESHOLD, minimum_seconds=MIN_SECONDS, minimum_rms=MIN_RMS,
                       minimum_active_fraction=.1, minimum_shorter_overlap=.8, polarity_invariant=True),
        counts=dict(train=sum(c['split']=='train' for c in new), validation=sum(c['split']=='validation' for c in new),
                    legacy=len(legacy), legacy_source_groups=len({r['source_group']['key'] for r in legacy})),
        legacy_boundary='Previously seen corpus only; this report does not authorize reuse of any legacy sample.',
        source_coverage=dict(legacy_utterances_with_native_metadata=sum(bool(r['source_group'].get('native_key')) for r in legacy),
                             legacy_utterances_without_native_metadata=sum(not r['source_group'].get('native_key') for r in legacy)),
        coverage=dict(new_new_expected=len(new)*(len(new)-1)//2, new_legacy_expected=len(new)*len(legacy),
                      attempted=len(comparisons), compared=sum(r['status']=='compared' for r in comparisons),
                      indeterminate=sum(r['status']!='compared' for r in comparisons)),
        maximum_similarity=max((r['score'] for r in comparisons if r['score'] is not None), default=None),
        conflicts=sum(r['requires_resolution'] for r in comparisons),
        source_gate='unresolved: orig_key-to-native manifest bridge uses filenames; metadata matches are clues, not proof of disjoint sources',
        pending_gates=['language_human_confirmation', 'cross_corpus_source_verification',
                       'duplicate_conflict_resolution', 'independent_training_lists'], inputs=frozen,
        audio_status=[dict(id=r['id'], corpus='new' if i<len(new) else 'legacy',
                           **{k:v for k,v in audios[r['audio']].items() if k!='samples'})
                      for i,r in enumerate(new+legacy)])
    out.mkdir(parents=True)
    for split in ('train', 'validation'):
        write_jsonl(out / (split+'-approved.jsonl'), [r for r in metadata if r['split']==split])
    write_jsonl(out / 'legacy-source-groups.jsonl', legacy)
    write_jsonl(out / 'comparisons.jsonl', comparisons)
    write_jsonl(out / 'conflicts.jsonl', [r for r in comparisons if r['requires_resolution']])
    write_json(out / 'audit-report.json', report)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('training-dir', 'split-plan', 'legacy-data-dir', 'out'):
        parser.add_argument('--'+flag, type=Path, required=True)
    parser.add_argument('--legacy-source-manifest', type=Path)
    parser.add_argument('--legacy-native-manifest', type=Path)
    parser.add_argument('--legacy-person-root', type=Path)
    audit(**vars(parser.parse_args()))
    print('CPU audit written; metadata only; ready_for_training=false')


if __name__ == '__main__':
    main()
