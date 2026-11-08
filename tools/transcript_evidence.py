"""已核验声音转写的本地一致性合同；不提供签名或审核人身份认证。"""
from __future__ import annotations

import copy
from datetime import datetime
from pathlib import Path
import wave

try:
    from .viewpoint_manifest import digest, read_json, safe_path, sha256
except ImportError:
    from viewpoint_manifest import digest, read_json, safe_path, sha256


def normalized_native_id(value):
    """与导入器一致：缺失、空值与零都是无原生 ID，不是字面字符串。"""
    if value in (None, '', 0, '0'):
        return None
    if not isinstance(value, (str, int)):
        raise ValueError('invalid native ID')
    return str(value)


def locate_source_row(parent, root, source_cache=None):
    """用源文件哈希 + 原生 ID/原 source_row 唯一定位，返回1-based数组位置。"""
    prov = parent['provenance']
    source_row = prov.get('source_row')
    if source_row is None or isinstance(source_row, (dict,list,bool)):
        raise ValueError('invalid source row reference')
    source_path = safe_path(Path(root), prov['source_file'])
    cache = source_cache if source_cache is not None else {}
    cache_key = (source_path, prov['source_file_sha256'])
    if cache_key not in cache:
        if sha256(source_path) != prov['source_file_sha256']:
            raise ValueError('source file hash mismatch')
        positions = {}
        for position, original in enumerate(read_json(source_path), 1):
            key = digest([normalized_native_id(original.get('server_id')), original.get('source_row')])
            positions.setdefault(key, []).append(position)
        cache[cache_key] = positions
    key = digest([normalized_native_id(prov.get('native_id')), source_row])
    matches = cache[cache_key].get(key, [])
    if len(matches) != 1:
        raise ValueError('source row missing or ambiguous')
    return matches[0]


def _render(base, review):
    revision = digest(base)
    timestamp = base.get('timestamp')
    return dict(copy.deepcopy(base), schema_version=2, verification_contract=1,
                candidate_evidence=copy.deepcopy(base), review=copy.deepcopy(review),
                revision=revision, evidence_revision=digest([revision, review]),
                exclusion_reasons=[], text=review['text'], speaker_id=review['speaker_id'],
                speaker_status=review['speaker_status'], transcript_status=review['transcript_status'],
                source_kind=review['source_kind'], single_speaker=review['single_speaker'],
                quality_status=review['quality_status'], transcript_verified=True,
                date=timestamp[:10] if isinstance(timestamp, str) else '',
                duration_ms=base['actual_duration_ms'], is_subject=True)


def make_verified_transcript(candidate):
    """从原 pending 候选及明确审核生成消费对象，不从已展平字段反推。"""
    base = {k: copy.deepcopy(v) for k, v in candidate.items()
            if k not in ('revision', 'review', 'exclusion_reasons')}
    if candidate.get('exclusion_reasons') or candidate.get('revision') != digest(base):
        raise ValueError('candidate is not current and eligible')
    result = _render(base, candidate.get('review', {}))
    validate_verified_transcript(result)
    return result


def validate_verified_transcript(row, *, parent=None, media=None, root=None, source_cache=None):
    """先校验审核/展平一致性；给定 dataset 锚点时再核对真实记录和音频。"""
    if (not isinstance(row, dict) or type(row.get('verification_contract')) is not int
            or row['verification_contract'] != 1 or row.get('schema_version') != 2):
        raise ValueError('verified transcript contract required')
    base, review = row.get('candidate_evidence'), row.get('review')
    if not isinstance(base, dict) or not isinstance(review, dict):
        raise ValueError('candidate evidence and review required')
    required = ('record_id','audio_sha256','person','actual_duration_ms','draft_text')
    if any(k not in base for k in required) or not isinstance(base['draft_text'], str):
        raise ValueError('incomplete candidate evidence')
    if (review.get('record_id') != base['record_id'] or review.get('audio_sha256') != base['audio_sha256']
            or review.get('revision') != digest(base) or review.get('speaker_id') != base['person']
            or review.get('speaker_status') != 'confirmed' or review.get('transcript_status') != 'corrected'
            or review.get('source_kind') != 'real_recording' or review.get('single_speaker') is not True
            or review.get('quality_status') != 'approved' or not isinstance(review.get('text'), str)
            or not review['text'].strip() or not isinstance(review.get('decided_by'), str)
            or not review['decided_by'].strip() or not isinstance(review.get('decided_at'), str)):
        raise ValueError('invalid or stale human review')
    try:
        datetime.fromisoformat(review['decided_at'].replace('Z', '+00:00'))
    except ValueError:
        raise ValueError('invalid review timestamp') from None
    if base.get('duration_check') != 'within_tolerance' and review.get('duration_approved') is not True:
        raise ValueError('unresolved duration review')
    pending = {'speaker_id':'unknown', 'speaker_status':'pending', 'transcript_status':'draft',
               'source_kind':'recording_unverified', 'segmentation_status':'whole_recording_not_segmented',
               'segment_start_ms':0, 'audio_valid':True, 'tier':2}
    if any(base.get(k) != v for k, v in pending.items()):
        raise ValueError('invalid original candidate state')
    if digest(row) != digest(_render(base, review)):
        raise ValueError('flattened transcript does not match reviewed evidence')
    if parent is None and media is None and root is None:
        return
    if not isinstance(parent, dict) or not isinstance(media, dict) or root is None:
        raise ValueError('complete dataset anchors required')
    if parent.get('content_type') != 'voice' or parent.get('sender_person_id') != parent.get('person'):
        raise ValueError('dataset record is not a subject voice candidate')
    immutable = ('record_id','record_type','person','viewpoint','source','tier','timestamp','content_type',
                 'sender','sender_person_id','conversation_kind','participant_ids','relationship_id','quality')
    for key in immutable:
        if digest(base.get(key)) != digest(parent.get(key)):
            raise ValueError('transcript does not match dataset record')
    provenance = {k:v for k,v in parent['provenance'].items()
                  if k in ('source_batch_id','source_file_sha256','legacy_source_sha256')}
    provenance['source_record_id'] = parent['record_id']
    scene = 'scene-' + digest(parent.get('conversation_id', parent.get('chat_room')))[:16]
    if (base.get('provenance') != provenance or base.get('conversation_id') != scene
            or base.get('chat_room') != scene or base.get('parent_record_id') != parent['record_id']
            or media.get('record_id') != parent['record_id']):
        raise ValueError('transcript source reference mismatch')
    wavs = [r for r in media.get('representations', []) if str(r.get('format','')).upper() == 'WAV']
    if len(wavs) != 1:
        raise ValueError('one real WAV anchor required')
    rep = wavs[0]
    audio = safe_path(Path(root), rep['path'])
    if base['audio_sha256'] != rep['sha256'] or sha256(audio) != rep['sha256']:
        raise ValueError('transcript audio hash does not match dataset media')
    try:
        with wave.open(str(audio), 'rb') as stream:
            frames, rate = stream.getnframes(), stream.getframerate()
            if frames <= 0 or rate <= 0 or stream.getnchannels() != 1 or stream.getsampwidth() not in (2,3,4):
                raise ValueError('invalid verified WAV')
            if len(stream.readframes(frames)) != frames * stream.getsampwidth():
                raise ValueError('truncated verified WAV')
            duration = round(frames * 1000 / rate)
    except (wave.Error, EOFError):
        raise ValueError('invalid verified WAV') from None
    expected = parent.get('duration_ms')
    if not isinstance(expected, (int,float)) or isinstance(expected, bool) or expected < 0:
        expected = None
    audio_fields = dict(segment_start_ms=0, segment_end_ms=duration, actual_duration_ms=duration,
                        expected_duration_ms=expected, duration_delta_ms=duration-expected if expected is not None else None,
                        duration_check=rep.get('duration_check'), audio_file='audio/'+rep['sha256']+'.wav',
                        dedup_group=rep['sha256'], split='validation' if int(rep['sha256'][:8],16)%10 == 0 else 'train')
    if any(digest(base.get(k)) != digest(v) for k,v in audio_fields.items()):
        raise ValueError('transcript audio/segment metadata mismatch')
    if (type(base.get('source_row_number')) is not int
            or base['source_row_number'] != locate_source_row(parent, root, source_cache)):
        raise ValueError('transcript source row mismatch')
