"""构建真实声音待核验清单；人工审核只读独立哈希绑定 overlay。"""
from __future__ import annotations

import argparse
import html
import json
import shutil
import wave
from pathlib import Path

try:
    from .local_identity import owner_participant
    from .viewpoint_manifest import load_dataset, read_json, read_jsonl, safe_path, sha256, digest, slug
    from .build_relationship_data import new_output, public_record, write_json, write_jsonl
    from .transcript_evidence import make_verified_transcript, validate_verified_transcript, normalized_native_id, locate_source_row
except ImportError:
    from local_identity import owner_participant
    from viewpoint_manifest import load_dataset, read_json, read_jsonl, safe_path, sha256, digest, slug
    from build_relationship_data import new_output, public_record, write_json, write_jsonl
    from transcript_evidence import make_verified_transcript, validate_verified_transcript, normalized_native_id, locate_source_row


def exclusion_reasons(candidate, review):
    reasons = []
    if not candidate.get('audio_valid'):
        reasons.append('audio_missing_or_invalid')
    if candidate.get('duration_check') != 'within_tolerance' and (not review or review.get('duration_approved') is not True):
        reasons.append('duration_unresolved')
    if not review:
        return reasons + ['speaker_pending', 'transcript_pending', 'quality_pending']
    if any(review.get(k) != candidate.get(k) for k in ('audio_sha256', 'revision')):
        reasons.append('stale_review')
    if review.get('speaker_id') != candidate['person'] or review.get('speaker_status') != 'confirmed':
        reasons.append('speaker_not_confirmed_subject')
    if review.get('transcript_status') != 'corrected' or not isinstance(review.get('text'), str) or not review['text'].strip():
        reasons.append('transcript_not_corrected')
    if review.get('source_kind') != 'real_recording' or review.get('single_speaker') is not True:
        reasons.append('not_single_real_speaker')
    if review.get('quality_status') != 'approved' or not review.get('decided_by') or not review.get('decided_at'):
        reasons.append('quality_pending')
    return reasons


def load_drafts(drafts_path, mapping_path):
    if bool(drafts_path) != bool(mapping_path):
        raise ValueError('ASR drafts and mapping must be supplied together')
    if not drafts_path:
        return {}
    drafts, mapping = read_json(Path(drafts_path)), read_json(Path(mapping_path))
    if not isinstance(drafts, list) or not isinstance(mapping, list):
        raise ValueError('ASR inputs must be lists')
    by_id = {r['id']:r for r in drafts}
    if len(by_id) != len(drafts) or len({r['id'] for r in mapping}) != len(mapping):
        raise ValueError('duplicate ASR IDs')
    result = {}
    for row in mapping:
        if row['id'] not in by_id or not isinstance(by_id[row['id']].get('asr_text'), str):
            raise ValueError('ASR mapping mismatch')
        if type(row.get('source_row_number')) is not int or row['source_row_number'] < 1:
            raise ValueError('ASR source row number must be a positive integer')
        key = (row['source_file'], row['source_row_number'], normalized_native_id(row.get('native_id')), row['wav_sha256'])
        if key in result:
            raise ValueError('duplicate ASR source')
        result[key] = by_id[row['id']]['asr_text']
    return result


def review_page(candidates):
    payload = json.dumps(candidates, ensure_ascii=False).replace('<', '\\u003c')
    return '''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>原声与转写草稿核验</title>
<style>body{max-width:850px;margin:auto;padding:20px;font:16px sans-serif;background:#f4f0e9}article{padding:16px;background:white;margin:16px 0}textarea{width:95%;height:80px}label{display:block;margin:8px 0}small{overflow-wrap:anywhere}button{padding:12px}</style>
<h1>原声与转写草稿核验</h1><p>发送人不等于说话人。每项默认为待核验；播放并确认后才勾选。自动识别的草稿可能有误，请听音后校对。导出决定只生成独立文件，不修改原始音频。</p>
<label>核验人 <input id="reviewer"></label><button id="export">导出已明确审核的决定</button><p id="status"></p><div id="items"></div>
<script>const candidates=__DATA__; const decisions=new Map();
const container=document.getElementById('items');
const reasonLabels={audio_missing_or_invalid:'音频缺失或无法读取',speaker_pending:'说话人待确认',transcript_pending:'转写待校对',quality_pending:'声音质量待确认',stale_review:'审核记录与当前版本不一致',speaker_not_confirmed_subject:'尚未确认是档案本人的声音',transcript_not_corrected:'转写尚未完成校对',not_single_real_speaker:'待确认是真实的单人录音',duration_unresolved:'时长差异待核对',duplicate_audio:'与另一条原声重复'};
let number=0;
for(const c of candidates){const a=document.createElement('article');const title=document.createElement('h2');title.textContent='原声第 '+(++number)+' 条 · '+(c.timestamp ? c.timestamp.replace('T',' ') : '时间未知');a.append(title);
const source=c.viewpoint==='father'?'父亲微信':c.viewpoint===__OWNER_ID__?'本人微信':'来源待确认';
const relation=c.relationship_id===c.person+'_father'?'夫妻私聊':c.relationship_id===c.person+'_'+__OWNER_ID__?'母子私聊':c.conversation_kind==='group'?'群聊':'关系待确认';
const info=document.createElement('small');info.textContent='来源：'+source+' · '+relation+'。'+(c.exclusion_reasons.length?c.exclusion_reasons.map(r=>reasonLabels[r]||'待进一步核验').join('；'):'已完成本轮核验');a.append(info);
const durationLabel={within_tolerance:'正常',mismatch:'有差异',missing:'缺失'}[c.duration_check]||'待核验';
const duration=document.createElement('p');duration.className='duration';duration.textContent='时长检查：'+durationLabel+'；实际 '+(c.actual_duration_ms == null ? '未知' : c.actual_duration_ms+' ms')+'；原期望 '+(c.expected_duration_ms == null ? '未知' : c.expected_duration_ms+' ms')+'；差值 '+(c.duration_delta_ms == null ? '未知' : c.duration_delta_ms+' ms');a.append(duration);
const details=document.createElement('details');const summary=document.createElement('summary');summary.textContent='来源详情';const trace=document.createElement('pre');trace.setAttribute('style','white-space:pre-wrap;overflow-wrap:anywhere');trace.textContent=JSON.stringify({record_id:c.record_id,audio_sha256:c.audio_sha256,revision:c.revision,provenance:c.provenance,source_row_number:c.source_row_number,duration_check:c.duration_check},null,2);details.append(summary,trace);a.append(details);
if(c.audio_file){const audio=document.createElement('audio');audio.controls=true;audio.preload='none';audio.src=c.audio_file;a.append(document.createElement('br'),audio);}
else{const missing=document.createElement('p');missing.textContent='目前没有可播放的音频，请先补齐原声后再核验。';a.append(missing);}
const t=document.createElement('textarea');t.value=c.draft_text||'';t.placeholder='没有可用草稿，请听原声后填写转写。';t.setAttribute('aria-label','校对转写');a.append(t);
if(!t.value.trim()){const empty=document.createElement('p');empty.textContent='这一条没有可用的转写草稿；可在听音后填写，不必把空白当作已校对。';a.append(empty);}
const boxes={};for(const [key,label] of Object.entries({speaker:'我确认实际说话人是建档对象',single:'真实录音且仅一位说话人',transcript:'已逐字校对转写',quality:'质量适合训练',duration:'已核对时长差/截断',include:'将这项明确审核决定加入导出'})){const l=document.createElement('label');const b=document.createElement('input');b.type='checkbox';boxes[key]=b;l.append(b,document.createTextNode(label));a.append(l);}
decisions.set(c.record_id,{c,t,boxes});container.append(a);}
document.getElementById('export').onclick=()=>{const who=document.getElementById('reviewer').value.trim();if(!who){document.getElementById('status').textContent='请填写核验人';return;}
const reviews=[];for(const {c,t,boxes:b} of decisions.values()){if(!b.include.checked)continue;reviews.push({record_id:c.record_id,audio_sha256:c.audio_sha256,revision:c.revision,speaker_id:b.speaker.checked?c.person:'unknown',speaker_status:b.speaker.checked?'confirmed':'pending',single_speaker:b.single.checked,source_kind:b.single.checked?'real_recording':'recording_unverified',text:t.value,transcript_status:b.transcript.checked?'corrected':'draft',quality_status:b.quality.checked?'approved':'pending',duration_approved:b.duration.checked,decided_by:who,decided_at:new Date().toISOString()});}
const url=URL.createObjectURL(new Blob([JSON.stringify({schema_version:1,reviews},null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download='voice-reviews.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);document.getElementById('status').textContent='已导出 '+reviews.length+' 项；请将此文件用于下一版档案，审核结果将在新版本中生效。';};</script>'''.replace('__OWNER_ID__', json.dumps(owner_participant())).replace('__DATA__', payload)


def build(*, person, datasets, out, asr_drafts=None, asr_mapping=None, reviews=None):
    slug(person)
    drafts = load_drafts(asr_drafts, asr_mapping)
    review_map = {}
    if reviews:
        overlay = read_json(Path(reviews))
        if overlay.get('schema_version') != 1 or not isinstance(overlay.get('reviews'), list):
            raise ValueError('invalid review overlay')
        review_map = {r['record_id']:r for r in overlay['reviews']}
        if len(review_map) != len(overlay['reviews']):
            raise ValueError('duplicate review IDs')
    inputs = [Path(p) for p in (asr_drafts, asr_mapping, reviews) if p]
    candidates, copies, matched_drafts, source_indexes = [], {}, set(), {}
    source_anchors = {}
    for path in map(Path, datasets):
        manifest, records = load_dataset(path)
        if manifest['person'] != person:
            raise ValueError('dataset person mismatch')
        root = path.parents[4]
        media_path = safe_path(root, manifest['media_manifest_path'])
        inputs.extend([path, media_path, root / manifest['records_path'], root / manifest['registry_path']])
        by_id = {r['record_id']:r for r in records}
        for media in read_jsonl(media_path):
            parent = by_id[media['record_id']]
            if parent['sender_person_id'] != person:
                continue
            source_anchors[parent['record_id']] = (parent, media, root)
            wavs = [r for r in media['representations'] if str(r.get('format','')).upper() == 'WAV']
            if len(wavs) > 1:
                raise ValueError('multiple WAV representations require explicit selection')
            rep = wavs[0] if wavs else None
            c = public_record(parent)
            c.update(audio_sha256=rep['sha256'] if rep else None, speaker_id='unknown', speaker_status='pending',
                     transcript_status='draft', draft_text='', source_kind='recording_unverified',
                     audio_valid=False, duration_check=rep.get('duration_check') if rep else 'missing',
                     parent_record_id=parent['record_id'], segment_start_ms=0, segment_end_ms=None,
                     language='unknown', audio_file=None, tier=2,
                     actual_duration_ms=None, expected_duration_ms=parent.get('duration_ms'), duration_delta_ms=None)
            if rep:
                audio = safe_path(root, rep['path'])
                inputs.append(audio)
                try:
                    with wave.open(str(audio), 'rb') as w:
                        frames, rate = w.getnframes(), w.getframerate()
                        c['audio_valid'] = frames > 0 and rate > 0 and w.getnchannels() == 1 and w.getsampwidth() in (2,3,4)
                        c['segment_end_ms'] = round(frames * 1000 / rate)
                        c['actual_duration_ms'] = c['segment_end_ms']
                        if len(w.readframes(frames)) != frames * w.getnchannels() * w.getsampwidth():
                            c['audio_valid'] = False
                except (wave.Error, EOFError):
                    pass
                c['audio_file'] = 'audio/' + rep['sha256'] + '.wav'
                copies[c['audio_file']] = audio
                prov = parent['provenance']
                # mapping 使用验收包内路径；导入 provenance 带 raw 批次前缀。
                source = prov['source_file']
                marker = '/records/'
                source = 'records/' + source.split(marker, 1)[1] if marker in source else source
                source_row_number = locate_source_row(parent, root, source_indexes)
                c['source_row_number'] = source_row_number
                key = (source, source_row_number, normalized_native_id(prov.get('native_id')), rep['sha256'])
                if key in drafts:
                    c['draft_text'] = drafts[key]
                    matched_drafts.add(key)
            if (isinstance(c['expected_duration_ms'], (int, float))
                    and not isinstance(c['expected_duration_ms'], bool) and c['expected_duration_ms'] >= 0
                    and c['actual_duration_ms'] is not None):
                c['duration_delta_ms'] = c['actual_duration_ms'] - c['expected_duration_ms']
            else:
                c['expected_duration_ms'] = None
            c['dedup_group'] = c['audio_sha256'] or digest(['missing', c['record_id']])
            c['split'] = 'validation' if int(c['dedup_group'][:8], 16) % 10 == 0 else 'train'
            c['segmentation_status'] = 'whole_recording_not_segmented'
            c['revision'] = digest(c)
            review = review_map.get(c['record_id'])
            if review and (review.get('revision') != c['revision'] or review.get('audio_sha256') != c['audio_sha256']):
                raise ValueError('review does not match exact source and draft revision')
            c['exclusion_reasons'] = exclusion_reasons(c, review)
            if review:
                c['review'] = review
            candidates.append(c)
    if not candidates or len({c['record_id'] for c in candidates}) != len(candidates):
        raise ValueError('empty candidates or duplicate IDs')
    if set(review_map) - {c['record_id'] for c in candidates}:
        raise ValueError('review references unselected record')
    if set(drafts) != matched_drafts:
        raise ValueError('ASR source mapping did not match selected audio')
    eligible, seen = [], set()
    verified = []
    verified_source_cache = {}
    for c in candidates:
        if not c['exclusion_reasons']:
            # 每个来源必须独立审核；检索保留来源观察，训练才按音频去重。
            entry = make_verified_transcript(c)
            parent, media, root = source_anchors[c['record_id']]
            validate_verified_transcript(entry, parent=parent, media=media, root=root, source_cache=verified_source_cache)
            verified.append(entry)
            if c['dedup_group'] in seen:
                c['exclusion_reasons'].append('duplicate_audio')
            else:
                seen.add(c['dedup_group'])
                eligible.append(dict(c, text=c['review']['text'], speaker_id=person,
                                     speaker_status='confirmed', transcript_status='corrected',
                                     source_kind='real_recording', single_speaker=True,
                                     quality_status='approved', training_eligible=True))
    out = new_output(out, inputs)
    out.mkdir(parents=True)
    for relative, source in copies.items():
        dest = out / relative
        dest.parent.mkdir(exist_ok=True)
        shutil.copyfile(source, dest)
        if sha256(dest) != relative.split('/')[-1][:-4]:
            raise ValueError('copied audio hash mismatch')
    write_jsonl(out / 'candidates.jsonl', candidates)
    write_jsonl(out / 'eligible.jsonl', eligible)
    write_jsonl(out / 'verified_transcripts.jsonl', verified)
    write_jsonl(out / 'excluded.jsonl', [c for c in candidates if c['exclusion_reasons']])
    write_json(out / 'summary.json', {'schema_version':1, 'person':person, 'candidates':len(candidates),
               'eligible':len(eligible), 'excluded':len(candidates)-len(eligible), 'drafts':len(matched_drafts),
               'verified_transcripts':len(verified),
               'inputs':[{'path':str(p.resolve()),'sha256':sha256(p)} for p in inputs],
               'segmentation':'whole recordings only', 'training_started':False})
    (out / 'review.html').write_text(review_page(candidates), encoding='utf-8')
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--person', required=True)
    parser.add_argument('--dataset', action='append', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--asr-drafts', type=Path)
    parser.add_argument('--asr-mapping', type=Path)
    parser.add_argument('--reviews', type=Path)
    args = vars(parser.parse_args())
    args['datasets'] = args.pop('dataset')
    build(**args)
    print('training candidates written; no training started')


if __name__ == '__main__':
    main()
