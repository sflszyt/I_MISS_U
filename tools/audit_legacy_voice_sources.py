"""旧语料来源内容桥：只读重建历史 PCM，证据不构成训练许可。"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import math
from pathlib import Path
import re

try:
    from .viewpoint_manifest import read_json, read_jsonl, safe_path, sha256, digest
    from .build_relationship_data import new_output, write_json, write_jsonl
    from .build_mobile_review import checked_path
    from .prepare_voice_upgrade import mapping
except ImportError:
    from viewpoint_manifest import read_json, read_jsonl, safe_path, sha256, digest
    from build_relationship_data import new_output, write_json, write_jsonl
    from build_mobile_review import checked_path
    from prepare_voice_upgrade import mapping


ALGORITHM = 'soundfile_float32_mean_round_clip32767_int16_exact_v1'


def file_path(value, root):
    if (not isinstance(value, str) or not value.strip()
            or any(c in value for c in ('|', '\n', '\r', '<', '>'))):
        raise ValueError('invalid file reference')
    path = Path(value)
    if '..' in path.parts or (path.drive and not path.is_absolute()):
        raise ValueError('parent traversal is forbidden')
    path = checked_path(path if path.is_absolute() else root/path)
    if not path.is_file():
        raise ValueError('input file is missing')
    return path


def pcm_hash(values):
    return hashlib.sha256(values.astype('<i2', copy=False).tobytes(order='C')).hexdigest()


def compare_segment(source, target, row, native):
    """仅按已记录边界重建，不搜索偏移、不放宽容差、不执行旧脚本。"""
    import numpy as np
    import soundfile as sf
    result = dict(status='mismatch', reason=None, requested_frames=None, effective_frames=None,
                  source_pcm_sha256=None, expected_pcm_sha256=None, target_pcm_sha256=None,
                  source_channels=None, source_sample_rate=None, source_frames=None,
                  target_channels=None, target_sample_rate=None, target_frames=None,
                  tail_truncated=False)
    try:
        source_info, target_info = sf.info(str(source)), sf.info(str(target))
        original, sr = sf.read(str(source), dtype='float32', always_2d=False)
        actual, target_sr = sf.read(str(target), dtype='int16', always_2d=False)
        source_pcm, _ = sf.read(str(source), dtype='int16', always_2d=False)
        result.update(source_pcm_sha256=pcm_hash(source_pcm), target_pcm_sha256=pcm_hash(actual),
                      source_channels=source_info.channels, source_sample_rate=sr,
                      source_frames=len(original), target_channels=target_info.channels,
                      target_sample_rate=target_sr, target_frames=len(actual))
        if (source_info.format not in ('WAV', 'WAVEX') or target_info.format not in ('WAV', 'WAVEX')
                or target_info.subtype != 'PCM_16' or not len(original) or not np.isfinite(original).all()):
            result['reason'] = 'unsupported_or_invalid_audio'
            return result
        if target_sr != sr:
            result['reason'] = 'sample_rate_mismatch'
            return result
        if target_info.channels != 1:
            result['reason'] = 'target_not_mono'
            return result
        if not row['segmented']:
            result.update(requested_frames=[0, len(original)], effective_frames=[0, len(original)],
                          expected_pcm_sha256=pcm_hash(source_pcm))
            if source != target or sha256(source) != sha256(target):
                result['reason'] = 'direct_reference_mismatch'
            elif row['start_s'] != 0 or row['end_s'] != native['duration_ms']/1000:
                result['reason'] = 'direct_boundary_mismatch'
            else:
                result.update(status='verified_direct', reason=None)
            return result
        if original.ndim > 1:
            original = np.mean(original, axis=1)
        original = original.astype(np.float32)
        start, end = int(round(row['start_s']*sr)), int(round(row['end_s']*sr))
        result.update(requested_frames=[start, end], effective_frames=[min(start,len(original)), min(end,len(original))],
                      tail_truncated=end > len(original))
        # 旧脚本仅当时长差>0.5秒时改用真实时长；manifest边界保留4位小数。
        duration = native['duration_ms']/1000
        if abs(duration-len(original)/sr) > .5:
            duration = len(original)/sr
        if not 0 <= start < min(end, len(original)) or row['end_s'] > round(duration, 4):
            result['reason'] = 'invalid_frame_boundary'
            return result
        expected = (np.clip(original[start:end], -1.0, 1.0)*32767.0).astype(np.int16)
        result['expected_pcm_sha256'] = pcm_hash(expected)
        if len(actual) != len(expected):
            result['reason'] = 'frame_count_mismatch'
        elif not np.array_equal(actual, expected):
            result['reason'] = 'pcm_mismatch'
        else:
            result.update(status='verified_segment', reason=None)
    except (OSError, ValueError, RuntimeError, OverflowError):
        result['reason'] = 'unreadable_or_invalid_audio'
    return result


def audit(legacy_data_dir, segment_manifest, native_manifest, person_root, recipe_path, out):
    root, person = checked_path(legacy_data_dir), checked_path(person_root)
    segment_path, native_path, recipe = [checked_path(p) for p in (segment_manifest, native_manifest, recipe_path)]
    if native_path != safe_path(person, 'normalized/wechat_voice_manifest.jsonl'):
        raise ValueError('native manifest must be the current person normalized manifest')
    protected = [root, person, segment_path, native_path, recipe]
    out = new_output(checked_path(out, writable=True), protected)
    if not all(importlib.util.find_spec(x) for x in ('numpy', 'soundfile')):
        raise ValueError('existing numpy/soundfile environment required')
    frozen = {}

    def freeze(path):
        path = checked_path(path)
        if not path.is_file():
            raise ValueError('input file is missing')
        value = sha256(path)
        if path in frozen and frozen[path] != value:
            raise ValueError('input changed during audit')
        frozen[path] = value
        return path

    for path in (segment_path, native_path, recipe, *(root/n for n in ('text', 'wav.scp', 'utt2spk'))):
        freeze(path)
    texts, wavs, speakers = [mapping(root/n) for n in ('text', 'wav.scp', 'utt2spk')]
    if not texts or texts.keys() != wavs.keys() or texts.keys() != speakers.keys():
        raise ValueError('legacy text/wav.scp/utt2spk must map one to one')
    segments = {}
    targets = {}
    for row in read_jsonl(segment_path):
        key = row.get('seg_key')
        if (not isinstance(key, str) or key not in wavs or key in segments
                or not isinstance(row.get('orig_key'), str) or not row['orig_key'].strip()
                or row['orig_key'] in ('.', '..') or any(c in row['orig_key'] for c in '/\\:\n\r')
                or type(row.get('segmented')) is not bool
                or any(type(row.get(k)) not in (int, float) or not math.isfinite(row[k])
                       for k in ('start_s', 'end_s', 'duration_s'))
                or not 0 <= row['start_s'] < row['end_s'] or row['duration_s'] <= 0
                # 三个字段各自四舍五入至4位；这不是PCM内容比较的容差。
                or abs(row['duration_s']-(row['end_s']-row['start_s'])) > .0001000001):
            raise ValueError('invalid or duplicate segment metadata')
        audio = file_path(wavs[key], root)
        if file_path(row.get('wav'), segment_path.parent) != audio:
            raise ValueError('segment and wav.scp path mismatch')
        targets[key] = freeze(audio)
        segments[key] = row
    if segments.keys() != wavs.keys():
        raise ValueError('segment manifest must cover all utterances')
    native_sources, identities, references = {}, set(), set()
    for row in read_jsonl(native_path):
        reference = row.get('file_ref')
        audio = safe_path(person, reference).resolve()
        key = audio.stem
        provenance = row.get('provenance')
        native_id = provenance.get('native_id') if isinstance(provenance, dict) else None
        svr_id = row.get('svr_id')
        if (not isinstance(native_id, str) or not native_id.isdecimal()
                or type(svr_id) is not int or str(svr_id) != native_id
                or row.get('record_id') != hashlib.sha256(('wechat_voice:'+native_id).encode()).hexdigest()
                or row.get('source') != 'wechat' or row.get('record_type') != 'media_item'
                or row.get('person') != person.name or row.get('media_type') != 'audio'
                or type(row.get('tier')) is not int or row['tier'] != 2
                or not isinstance(row.get('sender_wxid'), str) or not row['sender_wxid'].strip()
                or type(row.get('duration_ms')) is not int or row['duration_ms'] <= 0
                or type(row.get('size_bytes')) is not int or row['size_bytes'] <= 0
                or not isinstance(row.get('sha256'), str) or not re.fullmatch('[0-9a-f]{64}', row['sha256'])
                or key in native_sources or native_id in identities or audio in references):
            raise ValueError('invalid or ambiguous native identity metadata')
        identities.add(native_id)
        references.add(audio)
        native_sources[key] = (row, audio)
    wanted = {r['orig_key'] for r in segments.values()}
    for key in wanted & native_sources.keys():
        row, audio = native_sources[key]
        freeze(audio)
        if frozen[audio] != row['sha256'] or audio.stat().st_size != row['size_bytes']:
            raise ValueError('original source hash or size mismatch')
    # 全部路径发现后再次保护输出，任何报告都不覆盖输入或其祖先。
    out = new_output(out, protected + list(frozen))
    bindings = dict(segment_manifest_sha256=frozen[segment_path], native_manifest_sha256=frozen[native_path],
                    recipe_sha256=frozen[recipe], algorithm=ALGORITHM)
    items = []
    for key, row in segments.items():
        item = dict(seg_key=key, orig_key=row['orig_key'], audio=str(targets[key]),
                    audio_sha256=frozen[targets[key]], segment_metadata_sha256=digest(row),
                    start_s=row['start_s'], end_s=row['end_s'], segmented=row['segmented'],
                    source_file=None, source_file_sha256=None, native_identity_sha256=None,
                    native_metadata_sha256=None, ready_for_training=False, **bindings)
        native = native_sources.get(row['orig_key'])
        if native is None:
            item.update(status='excluded_missing_current_metadata', reason='missing_current_metadata',
                        source_pcm_sha256=None, target_pcm_sha256=None, expected_pcm_sha256=None,
                        requested_frames=None, effective_frames=None)
        else:
            meta, source = native
            item.update(source_file=str(source), source_file_sha256=frozen[source],
                        native_identity_sha256=digest(['wechat', meta['provenance']['native_id'], meta['sender_wxid']]),
                        native_metadata_sha256=digest(meta))
            item.update(compare_segment(source, targets[key], row, meta))
        items.append(item)
    def verify_inputs():
        # 比较及每次输出后核验，避免写入期间来源变化留下成功报告。
        for path, value in frozen.items():
            if checked_path(path) != path or not path.is_file() or sha256(path) != value:
                raise ValueError('input changed during audit')

    verify_inputs()
    counts = {name:sum(i['status']==name for i in items) for name in ('verified_direct', 'verified_segment', 'mismatch')}
    counts['excluded_missing'] = sum(i['status']=='excluded_missing_current_metadata' for i in items)
    report = dict(schema_version=1, ready_for_training=False, input_stable=True,
                  status='failed' if counts['mismatch'] else 'completed', counts=counts, total=len(items),
                  current_sources_verified=len(wanted & native_sources.keys()),
                  unresolved=[dict(seg_key=i['seg_key'], reason=i['reason']) for i in items
                              if i['status'] in ('mismatch', 'excluded_missing_current_metadata')],
                  limitations=['Content binding only; no training authorization or held-out independence.',
                               'Missing current metadata is not proof of removal; no historical metadata used.',
                               'Reconstruction uses recorded four-decimal boundaries; no offset search or tolerance.',
                               'Missing-metadata audio is file-hashed only; PCM and native source are unverified.',
                               'Historical model exposure is unchanged.'],
                  inputs=[dict(path=str(p), sha256=h) for p,h in frozen.items()], **bindings)
    new_output(out, protected + list(frozen))
    out.mkdir(parents=True, exist_ok=False)
    try:
        write_jsonl(out/'items.jsonl', items)
        verify_inputs()
        write_json(out/'report.json', report)
        verify_inputs()
    except (OSError, ValueError, RuntimeError):
        # 仅撤销本次新建的完成标志；保留readyfalse条目供排查，不能作为完整证据。
        (out/'report.json').unlink(missing_ok=True)
        raise
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('legacy-data-dir', 'segment-manifest', 'native-manifest', 'person-root', 'recipe-path', 'out'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        out = audit(**vars(args))
        report = read_json(out/'report.json')
    except (OSError, ValueError, RuntimeError):
        print('legacy_source_audit=failed invalid_or_changed_input; ready_for_training=false')
        return 2
    print('legacy_source_audit='+report['status']+' ready_for_training=false')
    return 1 if report['counts']['mismatch'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
