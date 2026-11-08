"""冻结已有试听和原声候选；公开投影不包含答案或原始标识。"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import uuid
import wave
from pathlib import Path

try:
    from .viewpoint_manifest import digest, no_links, read_json, read_jsonl, safe_path, sha256, load_dataset
    from .prepare_voice_upgrade import metrics
    from .benchmark_voice_references import experiment_schedule, take_identity
    from .build_training_manifest import load_drafts, exclusion_reasons
    from .build_relationship_data import public_record
    from .transcript_evidence import locate_source_row, normalized_native_id
except ImportError:
    from viewpoint_manifest import digest, no_links, read_json, read_jsonl, safe_path, sha256, load_dataset
    from prepare_voice_upgrade import metrics
    from benchmark_voice_references import experiment_schedule, take_identity
    from build_training_manifest import load_drafts, exclusion_reasons
    from build_relationship_data import public_record
    from transcript_evidence import locate_source_row, normalized_native_id


def checked_path(path, writable=False):
    path = Path(path).absolute()
    no_links(path)
    if writable and 'raw' in [p.casefold() for p in path.parts]:
        raise ValueError('raw is read only')
    path = path.resolve()
    no_links(path)
    if writable and 'raw' in [p.casefold() for p in path.parts]:
        raise ValueError('raw is read only')
    return path


def separate(path, roots):
    path = checked_path(path, True)
    for root in roots:
        root = checked_path(root)
        if path == root or path in root.parents or root in path.parents:
            raise ValueError('output overlaps protected input')
    return path


def inventory(root):
    result = {}
    for p in sorted(root.rglob('*')):
        no_links(p)
        if p.is_file():
            result[p.relative_to(root).as_posix()] = sha256(p)
    return result


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def training_anchors(summary, candidates):
    """从真实 dataset/ASR 入口重算候选，不能以自洽 revision 代替源证据。"""
    anchors, datasets, draft_paths, mapping_paths = [], [], [], []
    for entry in summary['inputs']:
        p = checked_path(entry['path'])
        if sha256(p) != entry['sha256']:
            raise ValueError('training source changed')
        anchors.append(p)
        if p.name == 'dataset.json':
            datasets.append(p)
        elif p.suffix == '.json':
            value = read_json(p)
            if isinstance(value,list) and value and all(isinstance(r,dict) and 'asr_text' in r for r in value):
                draft_paths.append(p)
            if isinstance(value,list) and value and all(isinstance(r,dict) and 'wav_sha256' in r and 'source_row_number' in r for r in value):
                mapping_paths.append(p)
    if not datasets or len(set(datasets)) != len(datasets) or len(draft_paths)>1 or len(mapping_paths)>1 or bool(draft_paths)!=bool(mapping_paths):
        raise ValueError('missing or ambiguous training dataset/ASR anchors')
    drafts = load_drafts(draft_paths[0] if draft_paths else None,mapping_paths[0] if mapping_paths else None)
    expected, matched, source_indexes = {}, set(), {}
    for path in datasets:
        manifest, records = load_dataset(path)
        if manifest['person'] != summary['person']:
            raise ValueError('training person mismatch')
        root = path.parents[4]
        for field in ('records_path','media_manifest_path','registry_path'):
            anchors.append(safe_path(root,manifest[field]))
        for parent in records:
            anchors.append(safe_path(root,parent['provenance']['source_file']))
        by_id = {r['record_id']:r for r in records}
        for media in read_jsonl(safe_path(root,manifest['media_manifest_path'])):
            for rep in media['representations']:
                audio = safe_path(root,rep['path'])
                if sha256(audio) != rep['sha256']:
                    raise ValueError('media source changed')
                anchors.append(audio)
            parent = by_id[media['record_id']]
            if parent['sender_person_id'] != summary['person']:
                continue
            wavs = [r for r in media['representations'] if str(r.get('format','')).upper()=='WAV']
            if len(wavs)>1:
                raise ValueError('ambiguous source WAV')
            rep = wavs[0] if wavs else None
            c = public_record(parent)
            c.update(audio_sha256=rep['sha256'] if rep else None,speaker_id='unknown',speaker_status='pending',
                     transcript_status='draft',draft_text='',source_kind='recording_unverified',audio_valid=False,
                     duration_check=rep.get('duration_check') if rep else 'missing',parent_record_id=parent['record_id'],
                     segment_start_ms=0,segment_end_ms=None,language='unknown',audio_file=None,tier=2,
                     actual_duration_ms=None,expected_duration_ms=parent.get('duration_ms'),duration_delta_ms=None)
            if rep:
                try:
                    with wave.open(str(safe_path(root,rep['path'])),'rb') as stream:
                        frames,rate=stream.getnframes(),stream.getframerate()
                        c['audio_valid']=frames>0 and rate>0 and stream.getnchannels()==1 and stream.getsampwidth() in (2,3,4)
                        c['segment_end_ms']=round(frames*1000/rate)
                        c['actual_duration_ms']=c['segment_end_ms']
                        if len(stream.readframes(frames))!=frames*stream.getnchannels()*stream.getsampwidth():
                            c['audio_valid']=False
                except (wave.Error,EOFError):
                    pass
                c['audio_file']='audio/'+rep['sha256']+'.wav'
                source=parent['provenance']['source_file']
                source='records/'+source.split('/records/',1)[1] if '/records/' in source else source
                c['source_row_number']=locate_source_row(parent,root,source_indexes)
                key=(source,c['source_row_number'],normalized_native_id(parent['provenance'].get('native_id')),rep['sha256'])
                if key in drafts:
                    c['draft_text']=drafts[key];matched.add(key)
            duration=c['expected_duration_ms']
            if isinstance(duration,(int,float)) and not isinstance(duration,bool) and duration>=0 and c['actual_duration_ms'] is not None:
                c['duration_delta_ms']=c['actual_duration_ms']-duration
            else:
                c['expected_duration_ms']=None
            c['dedup_group']=c['audio_sha256'] or digest(['missing',c['record_id']])
            c['split']='validation' if int(c['dedup_group'][:8],16)%10==0 else 'train'
            c['segmentation_status']='whole_recording_not_segmented'
            c['revision']=digest(c)
            c['exclusion_reasons']=exclusion_reasons(c,None)
            if c['record_id'] in expected:
                raise ValueError('duplicate source candidate')
            expected[c['record_id']]=c
    if matched != set(drafts) or expected != {c['record_id']:c for c in candidates}:
        raise ValueError('candidate differs from dataset/ASR evidence')
    return list(dict.fromkeys(anchors))


def build(ab_dir, prep_dir, out):
    ab, prep = checked_path(ab_dir), checked_path(prep_dir)
    evidence = read_json(ab / 'build-evidence.json')
    paired = read_json(ab / 'paired-manifest.json')
    experiment = checked_path(paired['experiment_path'])
    analysis = checked_path(paired['analysis_path'])
    if (evidence['groups'] != 14 or evidence['copied_wavs'] != 28
            or inventory(experiment) != evidence['source_hashes']
            or evidence['source_files_unchanged'] != len(evidence['source_hashes'])
            or sha256(analysis) != evidence['analysis_sha256']
            or paired['analysis_sha256'] != evidence['analysis_sha256']
            or {k:v for k,v in inventory(ab).items() if k != 'build-evidence.json'} != evidence['outputs']):
        raise ValueError('AB evidence changed')
    summary = read_json(experiment / 'summary.json')
    report_analysis = read_json(analysis)
    if (summary['total'] != 70 or summary['smoke'] is not False
            or report_analysis['total'] != 70 or report_analysis['run_id'] != summary['run_id']
            or paired['experiment_run_id'] != summary['run_id']):
        raise ValueError('incomplete experiment')
    for name, key in [('plan.json','plan_sha256'), ('results.jsonl','results_sha256'), ('asr-jobs.json','asr_jobs_sha256')]:
        if sha256(experiment / name) != summary[key]:
            raise ValueError('experiment evidence mismatch')
    rows = read_jsonl(experiment / 'results.jsonl')
    plan = read_json(experiment / 'plan.json')
    schedule = experiment_schedule(plan,False)
    if len(schedule) != 70:
        raise ValueError('incomplete schedule')
    for i,(row,(target,seed,reference)) in enumerate(zip(rows,schedule)):
        if any(row.get(k)!=v for k,v in take_identity(i,target,seed,reference,summary['run_id']).items()):
            raise ValueError('experiment identity mismatch')
    takes = {r['id']:r for r in rows}
    if len(rows) != 70 or len(takes) != 70:
        raise ValueError('experiment duplicates or missing takes')
    groups = paired['groups']
    if len(groups) != 14 or [g['group'] for g in groups] != list(range(1,15)) or len({(g['target_id'],g['seed']) for g in groups}) != 14:
        raise ValueError('incomplete pairs')
    if ({(g['target_id'],g['seed']) for g in groups} != {(t['id'],s) for t in plan['targets'] for s in plan['seeds']}
            or paired['candidate_condition'] != plan['references'][2]['id']
            or paired['baseline_condition'] != 'current-long-reference'):
        raise ValueError('fixed comparison changed')
    technical = read_json(prep / 'technical-report.json')
    source = checked_path(technical['source'])
    training = source.parent
    full = read_jsonl(source)
    selected = read_jsonl(prep / 'candidates.jsonl')
    full_by_id = {c['record_id']:c for c in full}
    selected_ids = {c['record_id'] for c in selected}
    recommended = {r['record_id'] for r in technical['records'] if r['recommended_for_review']}
    if (sha256(source) != technical['source_sha256'] or len(full_by_id) != len(full)
            or technical['candidates'] != len(full) or technical['selected'] != 12
            or len(selected) != 12 or len(selected_ids) != 12 or selected_ids != recommended
            or len(technical['records']) != len(full)
            or {r['record_id'] for r in technical['records']} != set(full_by_id)
            or technical['training_started'] is not False):
        raise ValueError('candidate selection mismatch')
    for c in full:
        original = {k:v for k,v in c.items() if k not in ('revision','exclusion_reasons','review')}
        if (c.get('speaker_status') != 'pending' or c.get('transcript_status') != 'draft' or c.get('review')
                or digest(original) != c['revision'] or c['split'] not in ('train','validation')
                or c['split'] != ('validation' if int(c['dedup_group'][:8],16)%10 == 0 else 'train')):
            raise ValueError('candidate revision or pending state mismatch')
        if c.get('audio_file') and sha256(safe_path(training,c['audio_file'])) != c['audio_sha256']:
            raise ValueError('full candidate audio changed')
    for r in technical['records']:
        if any(r[k] != full_by_id[r['record_id']][k] for k in ('audio_sha256','revision','split','provenance')):
            raise ValueError('technical report mismatch')
    if sum(c['split']=='train' for c in selected) != 11:
        raise ValueError('expected original 11/1 split')
    training_summary = read_json(training / 'summary.json')
    if (training_summary.get('training_started') is not False or training_summary.get('candidates') != len(full)
            or training_summary.get('eligible') != 0 or training_summary.get('verified_transcripts') != 0):
        raise ValueError('training summary must remain pending')
    anchors = training_anchors(training_summary,full)
    roots = [ab, prep, experiment, analysis, training, *anchors]
    out = separate(out, roots)
    if out.exists():
        raise ValueError('output must be new')
    media, tasks, private, copies = {}, [], {}, []
    def audio(path, expected):
        path = checked_path(path)
        if sha256(path) != expected or not metrics(path).get('valid'):
            raise ValueError('invalid audio')
        key = uuid.uuid4().hex
        media[key] = {'file':'audio/'+key+'.wav', 'sha256':expected}
        copies.append((path, media[key]['file']))
        return '/review/audio/'+key+'.wav'
    ab_items = []
    used = set()
    for g in groups:
        key = uuid.uuid4().hex
        item = dict(id=key, number=g['group'], text=g['target_text'])
        if item['text'] != next(t['text'] for t in plan['targets'] if t['id']==g['target_id']):
            raise ValueError('target text changed')
        if set(g['takes']) != {'A','B'} or {t['condition'] for t in g['takes'].values()} != {paired['baseline_condition'],paired['candidate_condition']}:
            raise ValueError('incorrect pair conditions')
        for label,t in g['takes'].items():
            row = takes[t['source_take']]
            if (row['id'] in used or row['status'] != 'ok' or row['condition'] != t['condition']
                    or row['target_id'] != g['target_id'] or row['seed'] != g['seed']
                    or row['wav'] != t['source_wav'] or row['sha256'] != t['source_sha256']
                    or t['source_sha256'] != t['output_sha256']
                    or sha256(safe_path(experiment,row['wav'])) != row['sha256']):
                raise ValueError('pair source mismatch')
            used.add(row['id'])
            item['audio_'+label.lower()] = audio(safe_path(ab,t['output_wav']),t['output_sha256'])
        ab_items.append(item)
    source_items = []
    for i,c in enumerate(selected,1):
        if c != full_by_id[c['record_id']]:
            raise ValueError('selected candidate changed')
        key = uuid.uuid4().hex
        private[key] = c
        source_items.append(dict(id=key,number=i,text=c['draft_text'],audio=audio(safe_path(prep,c['audio_file']),c['audio_sha256']),
                                 source_label='原声 '+str(i),split=c['split'],actual_duration_ms=c['actual_duration_ms'],
                                 expected_duration_ms=c['expected_duration_ms'],duration_requires_confirmation=c['duration_check'] != 'within_tolerance'))
    tasks = [dict(id='ab',title='声音对比',items=ab_items),dict(id='source',title='原声核验',items=source_items)]
    snapshots = {str(p):sha256(p) for root in (ab,prep,experiment,training) for p in root.rglob('*') if p.is_file()}
    snapshots.update({str(p):sha256(p) for p in [analysis,*anchors]})
    frozen_sources = [(source,'candidates.jsonl'),(training/'summary.json','training-summary.json'),(ab/'paired-manifest.json','paired-manifest.json'),(prep/'technical-report.json','technical-report.json')]
    manifest = dict(schema_version=1,tasks=tasks,media=media,candidates=private,study_id=paired['study_id'],
                    readonly_roots=[str(p) for p in roots],source_hashes=snapshots,synthetic=False,
                    source_inventories={str(root):inventory(root) for root in (ab,prep,experiment,training)},
                    frozen_hashes={'frozen/'+name:sha256(src) for src,name in frozen_sources})
    manifest['package_revision'] = digest(manifest)
    out.mkdir(parents=True)
    (out/'audio').mkdir()
    for src,rel in copies:
        shutil.copyfile(src,out/rel)
    write_json(out/'manifest.json',manifest)
    (out/'frozen').mkdir()
    for src,name in frozen_sources:
        shutil.copyfile(src,out/'frozen'/name)
    Package(out).verify()
    return out


class Package:
    def __init__(self, path):
        self.path = checked_path(path)
        self.manifest = read_json(self.path/'manifest.json')
        self.revision = self.manifest['package_revision']
        self.verify()

    @property
    def tasks(self):
        return self.manifest['tasks']

    def verify(self):
        current = read_json(self.path/'manifest.json')
        if current != self.manifest or digest({k:v for k,v in current.items() if k != 'package_revision'}) != self.revision:
            raise ValueError('package revision changed')
        for path, expected in current['source_hashes'].items():
            if sha256(checked_path(path)) != expected:
                raise ValueError('source evidence changed')
        for root, expected in current.get('source_inventories',{}).items():
            if inventory(checked_path(root)) != expected:
                raise ValueError('source inventory changed')
        for relative, expected in current.get('frozen_hashes',{}).items():
            if sha256(safe_path(self.path,relative)) != expected:
                raise ValueError('frozen evidence changed')
        for entry in current['media'].values():
            if sha256(safe_path(self.path,entry['file'])) != entry['sha256']:
                raise ValueError('package audio changed')

    def audio(self, key):
        entry = self.manifest['media'][key]
        data = safe_path(self.path,entry['file']).read_bytes()
        if hashlib.sha256(data).hexdigest() != entry['sha256']:
            raise ValueError('audio changed')
        return data


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('ab-dir','prep-dir','out'):
        p.add_argument('--'+name,type=Path,required=True)
    args = p.parse_args()
    build(args.ab_dir,args.prep_dir,args.out)
    print('Private review package verified; no approval or training performed')
