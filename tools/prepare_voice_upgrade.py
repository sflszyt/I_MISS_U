"""CPU 原声技术筛选；不批准身份、转写或训练，不改变原审核合同。"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import wave
from pathlib import Path

try:
    from .viewpoint_manifest import read_jsonl, safe_path, sha256, no_links
    from .build_relationship_data import new_output, write_json, write_jsonl
    from .build_training_manifest import review_page
except ImportError:
    from viewpoint_manifest import read_jsonl, safe_path, sha256, no_links
    from build_relationship_data import new_output, write_json, write_jsonl
    from build_training_manifest import review_page


def metrics(path):
    """完整 PCM WAV 检查；静音阈值只是技术代理，不代表听感或说话人。"""
    try:
        with wave.open(str(path), 'rb') as w:
            channels, width, rate, frames = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
            raw = w.readframes(frames)
        if not frames or rate < 1 or width not in (1, 2, 3, 4) or len(raw) != frames*channels*width:
            raise ValueError('invalid_pcm')
        scale = 2**(width*8-1)
        values = [(int.from_bytes(raw[i:i+width], 'little', signed=width != 1)
                   - (128 if width == 1 else 0))/scale for i in range(0, len(raw), width)]
        return dict(valid=True, channels=channels, sample_rate=rate, sample_width=width,
                    duration_seconds=frames/rate, peak=max(map(abs, values)),
                    rms=math.sqrt(sum(v*v for v in values)/len(values)),
                    dc=sum(values)/len(values),
                    clipping_ratio=sum(abs(v) >= .999 for v in values)/len(values),
                    silence_ratio=sum(abs(v) < .005 for v in values)/len(values))
    except (wave.Error, EOFError, ValueError, OSError):
        return dict(valid=False, reason='invalid_or_truncated_wav')


def prepare(training_dir, out, limit=12, readonly_inputs=()):
    training_dir = Path(training_dir)
    if type(limit) is not int or not 1 <= limit <= 12:
        raise ValueError('limit must be 1..12')
    source = training_dir / 'candidates.jsonl'
    candidates = read_jsonl(source)
    if len({c['record_id'] for c in candidates}) != len(candidates):
        raise ValueError('duplicate candidate IDs')
    reports, selected, inputs = [], [], [training_dir, source, *readonly_inputs]
    for c in candidates:
        if (c.get('speaker_status') != 'pending' or c.get('review')
                or c.get('transcript_status') != 'draft'
                or c.get('split') not in ('train', 'validation')):
            raise ValueError('expected unreviewed pending candidates')
        report = {k:c.get(k) for k in ('record_id', 'audio_sha256', 'revision', 'split', 'provenance')}
        report['recommended_for_review'] = False
        if c.get('audio_file'):
            if not c['audio_file'].startswith('audio/') or not c['audio_file'].endswith('.wav'):
                raise ValueError('candidate audio must remain under audio/')
            path = safe_path(training_dir, c['audio_file'])
            inputs.append(path)
            if sha256(path) != c['audio_sha256']:
                raise ValueError('candidate audio hash mismatch')
            report.update(metrics(path))
        else:
            report.update(valid=False, reason='missing_audio')
        suitable = (report['valid'] and report['channels'] == 1 and report['sample_rate'] >= 8000
                    and 2 <= report['duration_seconds'] <= 12 and report['clipping_ratio'] <= .001
                    and report['rms'] >= .01 and report['silence_ratio'] <= .8
                    and isinstance(c.get('draft_text'), str) and bool(c['draft_text'].strip())
                    and c.get('audio_valid') is True
                    and c.get('duration_check') == 'within_tolerance'
                    and c.get('segmentation_status') == 'whole_recording_not_segmented')
        report['technically_suitable'] = bool(suitable)
        reports.append(report)
        if suitable:
            selected.append((report['duration_seconds'], c['record_id'], c, report))
    selected.sort(key=lambda row: row[:2])
    chosen, hashes = [], set()
    for _, _, c, report in selected:
        if c['audio_sha256'] not in hashes and len(chosen) < limit:
            chosen.append(c)
            hashes.add(c['audio_sha256'])
            report['recommended_for_review'] = True
    out = new_output(out, inputs)
    out.mkdir(parents=True)
    for c in chosen:
        dest = safe_path(out, c['audio_file'])
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(safe_path(training_dir, c['audio_file']), dest)
        if sha256(dest) != c['audio_sha256']:
            raise ValueError('copied audio hash mismatch')
    write_jsonl(out / 'candidates.jsonl', chosen)
    write_json(out / 'technical-report.json', dict(
        schema_version=1, source=str(source.resolve()), source_sha256=sha256(source),
        status='ready_for_review' if chosen else 'no_suitable_candidates',
        selected=len(chosen), candidates=len(candidates), training_started=False,
        notice='Technical proxies only; no speaker/language/quality approval. Whole recordings; original split retained.',
        thresholds=dict(min_seconds=2, max_seconds=12, max_clipping=.001, min_rms=.01, max_silence=.8),
        records=reports))
    notice = '<p>本页仅为 CPU 技术推荐，不等于批准。原 split 与 revision 保留；validation 原声不能进入训练。<br>'
    notice += '核验子集：' + ', '.join(str(i+1)+' = '+c['split'] for i,c in enumerate(chosen)) + '</p>'
    page = review_page(chosen).replace('<div id="items">', notice+'<div id="items">')
    (out / 'review.html').write_text(page, encoding='utf-8')
    return out


def mapping(path):
    no_links(path)
    result = {}
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or parts[0] in result or not parts[1].strip():
            raise ValueError('invalid or duplicate legacy mapping')
        result[parts[0]] = parts[1].strip()
    return result


def legacy_references(legacy_dir, ids):
    legacy_dir = Path(legacy_dir).resolve()
    text_path, scp_path = legacy_dir / 'text', legacy_dir / 'wav.scp'
    texts, wavs = mapping(text_path), mapping(scp_path)
    if not texts or texts.keys() != wavs.keys() or len(set(ids)) != len(ids):
        raise ValueError('legacy text/wav.scp must map exactly one to one')
    refs = []
    for key in ids:
        if key not in texts:
            raise ValueError('legacy reference ID missing')
        path = Path(wavs[key])
        if not path.is_absolute():
            path = legacy_dir / path
        no_links(path)
        measure = metrics(path)
        if not measure['valid'] or measure['channels'] != 1:
            raise ValueError('invalid legacy WAV')
        refs.append(dict(id=key, audio=str(path.resolve()), audio_sha256=sha256(path),
                         text=texts[key], metrics=measure,
                         basis=dict(kind='legacy_corrected', utterance_id=key,
                                    text_mapping=str(text_path), text_mapping_sha256=sha256(text_path),
                                    wav_mapping=str(scp_path), wav_mapping_sha256=sha256(scp_path),
                                    prior_training_seen=True,
                                    authorization='User-confirmed corrected legacy training corpus; not held-out evaluation')))
    return refs


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--training-dir', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--legacy-data-dir', type=Path)
    p.add_argument('--reference-id', action='append', default=[])
    p.add_argument('--current-reference', type=Path)
    p.add_argument('--current-transcript', type=Path)
    p.add_argument('--model-dir', type=Path)
    p.add_argument('--checkpoint', type=Path)
    p.add_argument('--cosyvoice-root', type=Path)
    args = p.parse_args()
    refs = []
    readonly_inputs = []
    if args.legacy_data_dir:
        if not args.reference_id or not all((args.current_reference, args.current_transcript,
                                             args.model_dir, args.checkpoint, args.cosyvoice_root)):
            p.error('legacy experiment needs reference IDs, current reference/transcript, model, checkpoint and CosyVoice root')
        refs = legacy_references(args.legacy_data_dir, args.reference_id)
        for ref in refs:
            if not 12 <= len(ref['text']) <= 16 or not 2.7 <= ref['metrics']['duration_seconds'] <= 5:
                p.error('requested short reference outside 12..16 characters / 2.7..5 seconds')
        readonly_inputs = [args.legacy_data_dir, args.current_reference, args.current_transcript,
                           args.model_dir, args.checkpoint, args.cosyvoice_root]
        for path in readonly_inputs:
            no_links(path)
            if not path.exists():
                p.error('required local experiment input missing')
        if (not args.model_dir.is_dir() or not args.cosyvoice_root.is_dir()
                or not args.checkpoint.is_file()
                or not metrics(args.current_reference).get('valid')
                or not args.current_transcript.read_text(encoding='utf-8-sig').strip()):
            p.error('invalid local experiment inputs')
    elif any((args.reference_id, args.current_reference, args.current_transcript, args.model_dir,
              args.checkpoint, args.cosyvoice_root)):
        p.error('experiment arguments require --legacy-data-dir')
    out = prepare(args.training_dir, args.out, readonly_inputs=readonly_inputs)
    if refs:
        for i, ref in enumerate(refs):
            transcript = out / f'reference-{i+1}.txt'
            transcript.write_text(ref.pop('text'), encoding='utf-8')
            ref.update(transcript=str(transcript.resolve()), transcript_sha256=sha256(transcript))
        refs.append(dict(id='current-long-reference', audio=str(args.current_reference.resolve()),
                         audio_sha256=sha256(args.current_reference),
                         transcript=str(args.current_transcript.resolve()), transcript_sha256=sha256(args.current_transcript),
                         basis=dict(kind='existing_reference', authorization='Explicit CLI current production reference')))
        plan = dict(schema_version=1, model_dir=str(args.model_dir.resolve()),
                    checkpoint=str(args.checkpoint.resolve()), cosyvoice_root=str(args.cosyvoice_root.resolve()),
                    references=refs, language='mandarin', seeds=[20261020, 20261021], pad_ms=200, fade_ms=30,
                    timeout_seconds=180, targets=[
                        dict(id='short-1', text='吃饭了吗'), dict(id='short-2', text='早点休息'),
                        dict(id='medium-1', text='今天出去走走天气不错'),
                        dict(id='medium-2', text='你到家以后给我打个电话'),
                        dict(id='long-1', text='明天早上我们一起去买点蔬菜回来再慢慢做饭'),
                        dict(id='long-2', text='外面有点冷你出门的时候记得多穿一件衣服'),
                        dict(id='extended-1', text='今天先把家里的事情慢慢做好等到下午天气暖和一点再出去散步走累了就早点回来休息')])
        write_json(out / 'reference-plan.json', plan)
    print('CPU preparation written; no approval or training performed')


if __name__ == '__main__':
    main()
