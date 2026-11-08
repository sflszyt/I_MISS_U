"""封存现有24首抽/12配对为私有手机AB包；不重训、不读取原声。"""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import math
import re
import shutil
import uuid
import wave
from pathlib import Path

try:
    from . import compare_voice_training as comparison
    from .build_mobile_review import Package, checked_path, separate, inventory, write_json
    from .viewpoint_manifest import digest, sha256
except ImportError:
    import compare_voice_training as comparison
    from build_mobile_review import Package, checked_path, separate, inventory, write_json
    from viewpoint_manifest import digest, sha256


def require(condition):
    if not condition:
        # 固定错误，不输出路径、条件、答案、checkpoint或私人来源。
        raise ValueError('Comparison evidence invalid or changed')


def decode(text):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value)
            value[key] = item
        return value
    return json.loads(text, object_pairs_hook=unique,
                      parse_constant=lambda _: require(False))


def read(path):
    return decode(checked_path(path).read_text(encoding='utf-8-sig'))


def read_rows(path):
    return [decode(line)
            for line in checked_path(path).read_text(encoding='utf-8-sig').splitlines() if line.strip()]


def validate(comparison_dir):
    root = checked_path(comparison_dir)
    require(root.is_dir() and 'raw' not in [part.casefold() for part in root.parts])
    before = inventory(root)
    manifest, summary = read(root/'manifest.json'), read(root/'summary.json')
    require(manifest['tier'] == 3 and manifest['targets'] == comparison.TARGETS
            and manifest['seeds'] == list(comparison.SEEDS)
            and manifest['implementation_sha256'] == sha256(Path(comparison.__file__)))
    require(isinstance(manifest['run_id'], str) and re.fullmatch(r'[0-9a-f]{32}', manifest['run_id']))
    require(manifest['settings'] == dict(pad_ms=200, fade_ms=30, speed=1., fp16=False,
                                       stream=False, retries=0, timeout_seconds=180))
    require(summary == dict(success=True, planned=24, successful=24, run_id=manifest['run_id'],
                            formal_approval=False, live_voice_changed=False))
    require('failure.json' not in before)
    # 原始来源摘要保留在冻结manifest。仅重新读取训练报告/step日志，不重读原声或训练素材。
    frozen = manifest['frozen']
    require(isinstance(frozen, dict) and frozen)
    require(all(isinstance(p, str) and Path(p).is_absolute() and isinstance(h, str)
                and re.fullmatch(r'[0-9a-f]{64}', h) for p,h in frozen.items()))
    reports = [checked_path(p) for p in frozen if Path(p).name == 'report.json']
    require(len(reports) == 1)
    report_path = reports[0]
    require(sha256(report_path) == frozen[str(report_path)])
    report = read(report_path)
    comparison.check_report(report)
    require(report['live_voice_changed'] is False)
    candidate = checked_path(report['checkpoint'])
    require(candidate.parent == report_path.parent and candidate.name == 'candidate_step20.pt'
            and frozen.get(str(candidate)) == report['checkpoint_sha256'])
    steps_path = report_path.with_name('steps.jsonl')
    require(frozen.get(str(steps_path)) == report['step_log_sha256'] == sha256(steps_path))
    steps = read_rows(steps_path)
    require(len(steps) == 20 and all(s['step'] == i+1 and math.isfinite(s['loss'])
            and math.isfinite(s['gradient_norm']) and s['lr'] == 1e-6 and s['epoch'] == i//10
            and s['batch_index'] == i%10 for i,s in enumerate(steps)))
    anchors = {str(report_path):frozen[str(report_path)], str(steps_path):report['step_log_sha256'],
               str(checked_path(comparison.__file__)):manifest['implementation_sha256']}
    rows = read_rows(root/'results.jsonl')
    require(len(rows) == 24)
    expected_schedule = comparison.schedule()
    index = {}
    for i,(row,expected) in enumerate(zip(rows, expected_schedule)):
        require(all(row.get(k) == v for k,v in expected.items()) and row.get('id') == f'take-{i+1:02}'
                and row.get('status') == 'ok' and row.get('reason') is None
                and row.get('wav') == row['id']+'.wav' and row.get('finite') is True)
        key = (row['condition'], row['target_id'], row['seed'])
        require(key not in index)
        path = checked_path(root/row['wav'])
        require(path.parent == root and sha256(path) == row['sha256'])
        with wave.open(str(path), 'rb') as stream:
            frames, rate = stream.getnframes(), stream.getframerate()
            require(frames > 0 and rate == row['sample_rate'] and 8000 <= rate <= 192000
                    and stream.getnchannels() == 1 and stream.getsampwidth() == 2
                    and stream.getcomptype() == 'NONE'
                    and abs(frames/rate-row['duration_seconds']) < 1e-9
                    and len(stream.readframes(frames)) == frames*2)
        index[key] = row
    require({name for name in before if name.lower().endswith('.wav')} == {r['wav'] for r in rows})
    answers = read(root/'answer-key.json')
    require(isinstance(answers,list) and len(answers) == 12)
    page = (root/'listen.html').read_text(encoding='utf-8')
    sections = re.findall(r'<section>(.*?)</section>', page, re.DOTALL)
    require(len(sections) == 12 and 'const runId='+json.dumps(manifest['run_id']) in page)
    jobs = read(root/'asr-jobs.json')
    expected_jobs, pairs = [], []
    for i,(target,seed) in enumerate((t,s) for t in comparison.TARGETS for s in comparison.SEEDS):
        answer, section = answers[i], sections[i]
        require(set(answer) == {'pair','target_id','seed','A','B'} and answer['pair'] == i+1
                and answer['target_id'] == target['id'] and answer['seed'] == seed
                and {answer['A'],answer['B']} == {'baseline','candidate'})
        require(f'<h2>第 {i+1} 组 · {target["language"]}</h2><p>{html.escape(target["text"])}</p>' in section)
        audio = re.findall(r'<h3>([AB])</h3><audio controls preload="none" src="data:audio/wav;base64,([A-Za-z0-9+/=]+)"></audio>', section)
        require([label for label,_ in audio] == ['A','B'])
        takes = {}
        for label, encoded in audio:
            row = index[answer[label], target['id'], seed]
            require(hashlib.sha256(base64.b64decode(encoded, validate=True)).hexdigest() == row['sha256'])
            expected_jobs.append(dict(id=row['id'], wav=str(root/row['wav']), text=target['text'], lang='zh'))
            takes[label] = row
        pairs.append((target, takes))
    require(jobs == expected_jobs)
    evaluations = read(root/'evaluations.json')
    require(set(evaluations) == {'baseline','candidate'})
    for condition, value in evaluations.items():
        require(value == read(root/(condition+'-evaluation.json')) and math.isfinite(value['loss'])
                and value['evaluations'] == 1 and value['eval'] is True and value['no_grad'] is True
                and value['seed'] == 1986 and value['missing_keys'] == [] and value['unexpected_keys'] == [])
    require(inventory(root) == before and all(sha256(checked_path(p)) == h for p,h in anchors.items()))
    return root, before, manifest, pairs, anchors


def build(comparison_dir, out, url_base):
    require(isinstance(url_base,str) and re.fullmatch(r'/review/batches/[a-z0-9][a-z0-9-]{0,63}/', url_base)
            and url_base != '/review/batches/default/')
    # 拒绝重叠/旧目录后才读取及复制；不清理失败产物供诊断。
    out = separate(out, [comparison_dir])
    require(not out.exists())
    root, before, source, pairs, anchors = validate(comparison_dir)
    protected = [root, *anchors, *source['frozen']]
    out = separate(out, protected)
    media, items, copies, mappings = {}, [], [], []
    for number,(target,takes) in enumerate(pairs,1):
        item = dict(id=uuid.uuid4().hex, number=number, text=target['text'])
        private = dict(item_id=item['id'], number=number, takes={})
        for label,row in takes.items():
            key = uuid.uuid4().hex
            media[key] = dict(file='audio/'+key+'.wav', sha256=row['sha256'])
            item['audio_'+label.lower()] = url_base+'audio/'+key+'.wav'
            copies.append((root/row['wav'],media[key]['file']))
            private['takes'][label] = dict(media_id=key, **row)
        items.append(item)
        mappings.append(private)
    frozen_files = {name: value for name,value in before.items() if not name.lower().endswith('.wav')}
    manifest = dict(schema_version=1, tasks=[dict(id='ab',title='新声音试听 · Tier-3 合成',items=items)],
                    media=media, candidates={}, study_id=uuid.uuid4().hex, synthetic=False,
                    readonly_roots=[str(p) for p in protected], source_hashes=anchors,
                    source_inventories={str(root):before},
                    frozen_hashes={'frozen/'+name:value for name,value in frozen_files.items()})
    require(inventory(root) == before and all(sha256(checked_path(p)) == h for p,h in anchors.items()))
    out.mkdir(parents=True)
    (out/'audio').mkdir()
    (out/'frozen').mkdir()
    for src,rel in copies:
        shutil.copyfile(src,out/rel)
    for name in frozen_files:
        destination = out/'frozen'/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(root/name,destination)
    write_json(out/'frozen'/'mobile-mapping.json', mappings)
    manifest['frozen_hashes']['frozen/mobile-mapping.json'] = sha256(out/'frozen'/'mobile-mapping.json')
    for i,(path,expected) in enumerate(anchors.items()):
        name = f'frozen/anchor-{i}{Path(path).suffix}'
        shutil.copyfile(path,out/name)
        manifest['frozen_hashes'][name] = expected
    manifest['package_revision'] = digest(manifest)
    write_json(out/'manifest.json', manifest)
    Package(out).verify()
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--comparison-dir', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--url-base', required=True)
    args = parser.parse_args()
    try:
        build(args.comparison_dir, args.out, args.url_base)
    except (ValueError, KeyError, TypeError, OSError, wave.Error, EOFError):
        parser.exit(1, 'Comparison evidence invalid or unavailable; no batch published\n')
    print('Private AB package verified; no training or deployment performed')


if __name__ == '__main__':
    main()
