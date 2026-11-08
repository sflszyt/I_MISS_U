"""冻结 e14/step20 本地首抽对照；只写新实验目录，不接触正式审核状态。"""
from __future__ import annotations

import argparse
import base64
import contextlib
import html
import importlib.util
import json
import math
import os
import random
import struct
import sys
import time
import unicodedata
import uuid
import wave
from pathlib import Path

try:
    from .reference_bindings import load_reference_bindings
    from . import train_reviewed_voice as training
    from . import benchmark_voice_references as benchmark
except ImportError:
    from reference_bindings import load_reference_bindings
    import train_reviewed_voice as training
    import benchmark_voice_references as benchmark

require = training.require
sha256 = training.sha256
read_json = training.read_json
write_json = training.write_json
checked_path = training.checked_path
SEEDS = (1986, 20261023)
TARGETS = [dict(id=f'{lang}-{i+1}', language=lang, text=text)
           for lang, texts in (
               ('wu', ('慢慢来，勿要急。', '外头有点凉，侬出门记得多着件衣裳。',
                       '今朝买点青菜回来，夜饭烧汤，吃好再出去走走。')),
               ('mandarin', ('先喝口水吧。', '桌上还有几个橘子，想吃就拿一个。',
                             '今天晚一点再去买菜，回来把东西放好，坐下来歇一会儿。')))
           for i, text in enumerate(texts)]
LIMITATIONS = ('Tier-3 合成声音，不是真人录音。实验试听，不是正式批准，也不表示候选更像本人。'
               '训练仅 21.98 秒（9 条上海话、1 条普通话）；留出仅 1 条 2.26 秒上海话，'
               '无普通话留出。两个条件共用长参考，短句可能出现幻觉。'
               'e14 历史上见过旧的五条排除素材；本次训练不消除该历史。')


def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFKC', text).casefold() if c.isalnum())


def inference_text(target):
    return ('<|wuyu|>' if target['language'] == 'wu' else '') + target['text']


def schedule():
    return [dict(condition=condition, target_id=t['id'], seed=seed)
            for condition in ('baseline', 'candidate') for t in TARGETS for seed in SEEDS]


def check_novelty(entries):
    private = {normalize(e['text']) for e in entries}
    require(all(normalize(t['text']) not in private for t in TARGETS), 'target overlaps approved transcript')


def check_report(report):
    require(report.get('success') is True and report.get('successful_updates') == 20
            and report.get('optimizer_steps') == [20] and report.get('weights_changed') is True,
            'successful exact20 training required')
    require(report.get('holdout_used_for_training') is False
            and report.get('holdout_loss_computed') is False, 'holdout already used/evaluated')


def common_dependencies(model_root, cache_root, frontend_package):
    """与本地 CosyVoice2(fp32/no jit/trt/vllm) 构造器实际读取合同一致。"""
    model_root, cache_root, frontend_package = map(checked_path, (model_root, cache_root, frontend_package))
    files = [model_root/name for name in ('cosyvoice2.yaml', 'llm.pt', 'flow.pt', 'hift.pt',
                                         'campplus.onnx', 'speech_tokenizer_v2.onnx')]
    for root in (model_root/'CosyVoice-BlankEN', frontend_package):
        require(root.is_dir(), 'common dependency directory missing')
        # 冻结目录成员也可发现新 tokenizer/config 文件；排除 Python 自生成缓存。
        members = [checked_path(p) for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
        require(bool(members), 'common dependency directory empty')
        files.extend(members)
    files.extend(cache_root/lang/'tn'/name for lang in ('en', 'zh') for name in ('tagger.fst', 'verbalizer.fst'))
    assets = {}
    for path in files:
        require(path.is_file(), 'required common inference asset missing')
        assets[str(checked_path(path))] = sha256(path)
    optional = checked_path(model_root/'spk2info.pt')
    require(not optional.exists() or optional.is_file(), 'invalid optional speaker asset')
    assets[str(optional)] = sha256(optional) if optional.exists() else None
    return dict(model_root=str(model_root), cache_root=str(cache_root), frontend_package=str(frontend_package),
                text_frontend='wetext', ttsfrd_available=False, assets=assets)


def verify_common_dependencies(frozen):
    require(importlib.util.find_spec('ttsfrd') is None, 'text frontend selection changed')
    require(common_dependencies(frozen['model_root'], frozen['cache_root'], frozen['frontend_package']) == frozen,
            'common inference dependencies changed')


def dependency_worker(connection, plan):
    """只解析既有离线缓存；不构造 CosyVoice、不加载 CUDA。"""
    with open(os.devnull, 'w') as quiet, contextlib.redirect_stdout(quiet), contextlib.redirect_stderr(quiet):
        try:
            policy = benchmark.OfflinePolicy()
            policy.install()
            policy.patch_downloaders()
            require(importlib.util.find_spec('ttsfrd') is None,
                    'this frozen local recipe requires wetext; ttsfrd needs a separately reviewed recipe')
            from modelscope import snapshot_download
            cache = checked_path(snapshot_download('pengzhendong/wetext', local_files_only=True))
            spec = importlib.util.find_spec('wetext')
            require(spec is not None and spec.origin, 'wetext package missing')
            frozen = common_dependencies(plan['model_dir'], cache, Path(spec.origin).parent)
            policy.check()
            connection.send(('ready', frozen))
        except Exception as exc:
            connection.send((benchmark.error_kind(exc), benchmark.error_details(exc)))
        finally:
            connection.close()


def reference_provenance(ref, holdout):
    bindings = load_reference_bindings()
    person = checked_path(ref['audio']).parents[2]
    manifest_path = person/'voice/reference/reference_manifest.json'
    native_path = person/'normalized/wechat_voice_manifest.jsonl'
    bridge_path = Path(__file__).resolve().parents[1]/'data/work/language-results-20261023/source-bridge/real-v1/items.jsonl'
    manifest = read_json(checked_path(manifest_path))
    clips = [r for r in manifest['items'] if r['sha256'] == bindings['REFERENCE_AUDIO']]
    require(len(clips) == 1, 'reference source clip missing')
    clip = clips[0]
    require(clip['file'] == manifest['primary_reference'] and clip.get('approved_by_user')
            and 'PRIMARY' in clip.get('user_choice', '')
            and checked_path(person/clip['file']) == checked_path(ref['audio'])
            and (clip['window_start_sample'], clip['window_samples'], clip['sample_rate']) == (573600, 432000, 24000),
            'reference source approval/window changed')
    natives = [r for r in training.read_jsonl(checked_path(native_path))
               if r['file_ref'] == clip['source_file_ref']]
    require(len(natives) == 1, 'reference native source missing')
    native = natives[0]
    source = checked_path(person/clip['source_file_ref'])
    source_hash = sha256(source)
    require(source_hash == native['sha256'] == bindings['REFERENCE_SOURCE']
            and str(clip['source_svr_id']) == native['provenance']['native_id'], 'reference native binding mismatch')
    bridges = [r for r in training.read_jsonl(checked_path(bridge_path))
               if r['orig_key'] == source.stem]
    require(len(bridges) == 3 and all(r['status'] == 'verified_segment'
            and r['source_file_sha256'] == source_hash and checked_path(r['source_file']) == source
            for r in bridges), 'reference source bridge missing')
    require(source_hash != holdout['provenance']['source_file_sha256']
            and native['record_id'] not in (holdout['record_id'], holdout['parent_record_id'],
                                           holdout['provenance']['source_record_id']), 'reference source overlaps holdout')
    return dict(source_record_id=native['record_id'], native_id=native['provenance']['native_id'],
                source_file_sha256=source_hash, window_start_sample=573600, window_samples=432000,
                evidence_sha256={str(p): sha256(p) for p in (manifest_path, native_path, bridge_path, source)})


def validate_inputs(report_path, report_hash, reference_path):
    report_path, reference_path = map(checked_path, (report_path, reference_path))
    require(sha256(report_path) == report_hash, 'training report changed')
    report = read_json(report_path)
    check_report(report)
    root = checked_path(report['prepared_dir'])
    config, entries = training.validate_prepared(root, report['prepared_sha256'])
    require(sha256(root/'config.json') == report['config_sha256'], 'training config mismatch')
    candidate = checked_path(report['checkpoint'])
    require(candidate.parent == report_path.parent and candidate.name == 'candidate_step20.pt',
            'candidate path not bound to training run')
    require(sha256(candidate) == report['checkpoint_sha256'], 'candidate checkpoint changed')
    steps_path = report_path.with_name('steps.jsonl')
    require(sha256(steps_path) == report['step_log_sha256'], 'step log changed')
    steps = training.read_jsonl(steps_path)
    require(len(steps) == 20 and [s['step'] for s in steps] == list(range(1, 21)), 'invalid step sequence')
    require(all(math.isfinite(s['loss']) and math.isfinite(s['gradient_norm'])
                and s['lr'] == 1e-6 and s['epoch'] == i//10 and s['batch_index'] == i % 10
                for i, s in enumerate(steps)), 'invalid training step evidence')
    check_novelty(entries)
    plan = read_json(reference_path)
    refs = [r for r in plan['references'] if r['id'] == 'current-long-reference']
    require(len(refs) == 1, 'fixed reference missing')
    ref = refs[0]
    bindings = load_reference_bindings()
    for field, expected in [('audio', bindings['REFERENCE_AUDIO']), ('transcript', bindings['REFERENCE_TEXT'])]:
        require(ref[field+'_sha256'] == expected and sha256(checked_path(ref[field])) == expected,
                'fixed reference changed')
    require(ref['basis'] == dict(kind='existing_reference', authorization='Explicit CLI current production reference'),
            'reference authorization changed')
    holdout = [e for e in entries if e['split'] == 'validation'][0]
    require(ref['audio_sha256'] not in (holdout['audio_sha256'], holdout['provenance']['source_file_sha256'])
            and checked_path(ref['audio']) != checked_path(holdout['audio_file'])
            and normalize(Path(ref['transcript']).read_text(encoding='utf-8-sig')) != normalize(holdout['text']),
            'reference overlaps holdout')
    require(checked_path(plan['checkpoint']) == checked_path(config['checkpoint'])
            and checked_path(plan['model_dir']) == checked_path(config['model_root'])
            and checked_path(plan['cosyvoice_root']) == checked_path(config['vendor']), 'reference model mismatch')
    frozen = {str(p): sha256(p) for p in (report_path, reference_path, candidate, steps_path,
                                          checked_path(config['checkpoint']))}
    provenance = reference_provenance(ref, holdout)
    frozen.update(provenance['evidence_sha256'])
    return dict(report=report, config=config, reference=ref, holdout=holdout,
                prepared_dir=str(root), frozen=frozen, reference_provenance=provenance)


def worker(connection, plan):
    # 第三方日志可能含私人 prompt；只回传无文本的结构化诊断。
    with open(os.devnull, 'w') as quiet, contextlib.redirect_stdout(quiet), contextlib.redirect_stderr(quiet):
        try:
            os.environ.pop('onnx_path', None)
            root = Path(plan['cosyvoice_root'])
            sys.path[:0] = [str(root), str(root/'third_party/Matcha-TTS')]
            policy = benchmark.OfflinePolicy()
            policy.install()
            policy.patch_downloaders()
            policy.preflight_wetext()
            verify_common_dependencies(plan['common_dependencies'])
            from modelscope import snapshot_download
            require(str(checked_path(snapshot_download('pengzhendong/wetext', local_files_only=True)))
                    == plan['common_dependencies']['cache_root'], 'frontend cache selection changed')
            import torch
            import numpy as np
            require(torch.cuda.is_available(), 'CUDA unavailable')
            free, total = torch.cuda.mem_get_info()
            require(free >= 12 * 1024**3, 'less than 12 GiB free')
            torch.cuda.set_per_process_memory_fraction((free-3*1024**3)/total)
            torch.cuda.reset_peak_memory_stats()
            random.seed(1986)
            np.random.seed(1986)
            torch.manual_seed(1986)
            torch.cuda.manual_seed_all(1986)
            model = benchmark.LocalModel(plan, policy)
            require(model.cv.frontend.text_frontend == plan['common_dependencies']['text_frontend'],
                    'actual text frontend differs from frozen recipe')
            verify_common_dependencies(plan['common_dependencies'])
            state = torch.load(plan['checkpoint'], map_location='cpu', weights_only=True)
            metadata = {k: v for k, v in state.items() if not isinstance(v, torch.Tensor)}
            require(set(metadata) <= {'epoch', 'step'}, 'unknown checkpoint metadata')
            if plan['condition'] == 'candidate':
                require(metadata == {'epoch': 1, 'step': 20}, 'candidate metadata mismatch')
            compatibility = model.cv.model.llm.load_state_dict(
                {k: v for k, v in state.items() if isinstance(v, torch.Tensor)}, strict=True)
            del state
            model.cv.model.llm.eval()
            feature = torch.load(plan['holdout_feature'], map_location='cpu', weights_only=True)
            training.validate_feature(feature)
            random.seed(1986)
            np.random.seed(1986)
            torch.manual_seed(1986)
            torch.cuda.manual_seed_all(1986)
            with torch.no_grad():
                loss = model.cv.model.llm(feature, torch.device('cuda'))['loss']
            require(loss.numel() == 1 and bool(torch.isfinite(loss)), 'nonfinite heldout loss')
            evaluation = dict(loss=float(loss), evaluations=1, eval=True, no_grad=True, seed=1986,
                              missing_keys=compatibility.missing_keys, unexpected_keys=compatibility.unexpected_keys,
                              checkpoint_metadata=metadata, free_before_bytes=free)
            del feature, loss
            policy.check()
            connection.send(('ready', evaluation))
            while True:
                job = connection.recv()
                if job is None:
                    break
                try:
                    require(torch.cuda.mem_get_info()[0] >= 3*1024**3, 'CUDA headroom below 3 GiB')
                    result = model.synthesize(*job)
                    policy.check()
                    connection.send(('ok', result))
                except Exception as exc:
                    connection.send((benchmark.error_kind(exc), benchmark.error_details(exc)))
        except Exception as exc:
            connection.send((benchmark.error_kind(exc), benchmark.error_details(exc)))
        finally:
            connection.close()


class ComparisonProcess(benchmark.ModelProcess):
    def __init__(self, plan, *, worker_target=worker):
        self.evaluation = None
        super().__init__(plan, worker_target=worker_target)

    def receive(self, timeout):
        value = super().receive(timeout)
        if self.evaluation is None:
            self.evaluation = value
        return value


def save_wav(path, data, rate):
    require(type(rate) is int and 8000 <= rate <= 192000 and len(data) > 0
            and all(math.isfinite(v) for v in data), 'invalid generated PCM')
    with path.open('xb') as stream, wave.open(stream, 'wb') as wav:
        wav.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
        wav.writeframes(b''.join(struct.pack('<h', int(max(-1, min(1, v))*32767)) for v in data))
    return dict(wav=path.name, sha256=sha256(path), duration_seconds=len(data)/rate,
                sample_rate=rate, finite=True)


def material(out, rows, run_id):
    require(len(rows) == 24, 'all planned takes required')
    index = {(r['condition'], r['target_id'], r['seed']): r for r in rows}
    require(set(index) == {(r['condition'], r['target_id'], r['seed']) for r in schedule()},
            'result membership mismatch')
    key, cards, jobs = [], [], []
    rng = random.SystemRandom()
    for target in TARGETS:
        for seed in SEEDS:
            number = len(key)+1
            order = ['baseline', 'candidate']
            rng.shuffle(order)
            key.append(dict(pair=number, target_id=target['id'], seed=seed, A=order[0], B=order[1]))
            card = f'<section><h2>第 {number} 组 · {target["language"]}</h2><p>{html.escape(target["text"])}</p>'
            for label, condition in zip(('A', 'B'), order):
                row = index[condition, target['id'], seed]
                card += f'<h3>{label}</h3>'
                if row['status'] == 'ok':
                    path = checked_path(out/row['wav'])
                    require(path.parent == out.resolve() and path.suffix == '.wav'
                            and sha256(path) == row['sha256'], 'output audio binding mismatch')
                    encoded = base64.b64encode(path.read_bytes()).decode('ascii')
                    card += '<audio controls preload="none" src="data:audio/wav;base64,'+encoded+'"></audio>'
                    jobs.append(dict(id=row['id'], wav=str(path), text=target['text'], lang='zh'))
                else:
                    card += '<p class="failed">失败 / 未生成：'+html.escape(row['status'])+'</p>'
            card += f'<label>本组选择 <select data-pair="{number}"><option value="">尚未选择</option>'
            card += ''.join(f'<option value="{v}">{label}</option>' for v, label in
                            [('A', 'A'), ('B', 'B'), ('similar', '差不多'), ('cannot-judge', '无法判断')])
            cards.append(card+'</select></label></section>')
    script = '''const runId=RUN_ID, storageKey='voice-experiment-'+runId;
const selectors=[...document.querySelectorAll('select')];
function payload(){return {schema_version:1,status:'experimental-not-formal',formal_approval:false,
run_id:runId,tier:3,decisions:selectors.map(s=>({pair:Number(s.dataset.pair),choice:s.value}))};}
try{const old=JSON.parse(localStorage.getItem(storageKey)||'null');if(old&&old.run_id===runId)
for(const d of old.decisions||[]){const s=selectors.find(s=>Number(s.dataset.pair)===d.pair);
if(s&&['','A','B','similar','cannot-judge'].includes(d.choice))s.value=d.choice;}}catch(e){}
for(const s of selectors)s.addEventListener('change',()=>{try{localStorage.setItem(storageKey,JSON.stringify(payload()));
document.getElementById('saved').textContent='已保存本机草稿';}catch(e){document.getElementById('saved').textContent='浏览器不能保存，请下载草稿';}});
document.getElementById('download').onclick=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(payload(),null,2)],{type:'application/json'}));
const a=document.createElement('a');a.href=url;a.download='experimental-decisions-'+runId+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};'''.replace('RUN_ID', json.dumps(run_id))
    page = ('<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>本地实验试听</title><style>body{font:18px system-ui;max-width:760px;margin:auto;padding:18px;background:#faf8f4;color:#262626}'
            'section{background:white;border:1px solid #ccc;border-radius:12px;padding:16px;margin:20px 0}audio{width:100%}'
            'button,select{font:inherit;min-height:48px;padding:8px}button{position:sticky;bottom:12px}.failed{color:#a21b1b}</style>'
            '<h1>本地盲听 · 12 组</h1><p>'+LIMITATIONS+'</p><p>请比较声音相似度、自然度和漏字添字。所有首抽与失败均保留。选择仅存本机浏览器或下载 JSON。</p>'
            +''.join(cards)+'<p id="saved" role="status"></p><button id="download">下载实验选择 JSON</button><script>'+script+'</script></html>')
    (out/'listen.html').write_text(page, encoding='utf-8')
    write_json(out/'answer-key.json', key)
    write_json(out/'asr-jobs.json', jobs)


def fixture(out):
    out = training.fresh_output(out, [])
    out.mkdir(parents=True)
    rows = []
    for i, item in enumerate(schedule()):
        row = dict(item, id=f'take-{i+1:02}', status='fixture_failure' if i == 0 else 'ok')
        if i:
            row.update(save_wav(out/(row['id']+'.wav'),
                                [0.08*math.sin(n*2*math.pi*440/24000) for n in range(6000)], 24000))
        rows.append(row)
    write_json(out/'results.json', rows)
    material(out, rows, 'synthetic-'+uuid.uuid4().hex)
    return out


def run(args):
    inputs = validate_inputs(args.report, args.report_sha256, args.reference_plan)
    config, report = inputs['config'], inputs['report']
    protected = [Path(p) for p in inputs['frozen']] + [Path(inputs['prepared_dir']),
                 Path(config['model_root']), Path(config['vendor']), Path(config['state_dir']),
                 Path(config['upstream']), Path(inputs['reference']['audio']).parent]
    out = training.fresh_output(args.out, protected)
    out.mkdir(parents=True)
    rows, evaluations = [], {}
    run_id = uuid.uuid4().hex
    manifest = dict(run_id=run_id, tier=3, targets=TARGETS, seeds=SEEDS,
                    settings=dict(pad_ms=200, fade_ms=30, speed=1., fp16=False, stream=False,
                                  retries=0, timeout_seconds=180), frozen=inputs['frozen'],
                    reference=inputs['reference'], reference_provenance=inputs['reference_provenance'],
                    holdout={k: inputs['holdout'][k] for k in
                    ('record_id', 'audio_sha256', 'feature_file', 'feature_sha256', 'provenance')},
                    limitations=LIMITATIONS, implementation_sha256=sha256(Path(__file__)))
    write_json(out/'manifest.json', manifest)
    try:
        with training.experiment_lock():
            probe = ComparisonProcess(dict(model_dir=config['model_root'], timeout_seconds=180),
                                      worker_target=dependency_worker)
            try:
                common = probe.evaluation
            finally:
                probe.close()
            write_json(out/'common-dependencies.json', common)
            for condition in ('baseline', 'candidate'):
                validate_inputs(args.report, args.report_sha256, args.reference_plan)
                # 在构造任何条件前复核同一个清单；失败直接退出，不发布试听材料。
                verify_common_dependencies(common)
                model, aborted = None, None
                plan = dict(condition=condition, timeout_seconds=180, cosyvoice_root=config['vendor'], common_dependencies=common,
                            model_dir=config['model_root'], checkpoint=config['checkpoint'] if condition == 'baseline' else report['checkpoint'],
                            holdout_feature=str(Path(inputs['prepared_dir'])/inputs['holdout']['feature_file']))
                try:
                    try:
                        model = ComparisonProcess(plan)
                        evaluations[condition] = model.evaluation
                        write_json(out/(condition+'-evaluation.json'), model.evaluation)
                    except Exception as exc:
                        aborted = benchmark.error_kind(exc)
                        evaluations[condition] = dict(status=aborted, diagnostic=benchmark.error_details(exc))
                    for item in [r for r in schedule() if r['condition'] == condition]:
                        row = dict(item, id=f'take-{len(rows)+1:02}', status='not_run', reason=aborted)
                        if not aborted:
                            target = next(t for t in TARGETS if t['id'] == item['target_id'])
                            start = time.monotonic()
                            try:
                                training.verify_hashes(inputs['frozen'])
                                data, rate = model.synthesize(inference_text(target), inputs['reference'], item['seed'], target['language'])
                                row.update(save_wav(out/(row['id']+'.wav'), benchmark.postprocess_live(data, rate), rate))
                                row['status'] = 'ok'
                            except Exception as exc:
                                row.update(status=benchmark.error_kind(exc), diagnostic=benchmark.error_details(exc))
                                # 一次失败即终止该条件；不重启、不重抽，其余计划行仍保留。
                                aborted = row['status']
                            row['elapsed_seconds'] = time.monotonic()-start
                        rows.append(row)
                        with (out/'results.jsonl').open('a', encoding='utf-8') as stream:
                            stream.write(json.dumps(row, ensure_ascii=False)+'\n')
                finally:
                    if model is not None:
                        model.close()
            validate_inputs(args.report, args.report_sha256, args.reference_plan)
            training.verify_hashes(inputs['frozen'])
            verify_common_dependencies(common)
        verify_common_dependencies(common)
        write_json(out/'evaluations.json', evaluations)
        material(out, rows, run_id)
        success = len(rows) == 24 and all(r['status'] == 'ok' for r in rows)
        write_json(out/'summary.json', dict(success=success, planned=24, successful=sum(r['status'] == 'ok' for r in rows),
                                          run_id=run_id, formal_approval=False, live_voice_changed=False))
        return 0 if success else 1
    except Exception as exc:
        write_json(out/'failure.json', dict(success=False, diagnostic=benchmark.error_details(exc)))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='stage', required=True)
    p = sub.add_parser('fixture')
    p.add_argument('--out', type=Path, required=True)
    p = sub.add_parser('run')
    for field in ('report', 'reference-plan', 'out'):
        p.add_argument('--'+field, type=Path, required=True)
    p.add_argument('--report-sha256', required=True)
    args = parser.parse_args()
    try:
        if args.stage == 'fixture':
            fixture(args.out)
            return 0
        return run(args)
    except Exception as exc:
        print(json.dumps(dict(success=False, diagnostic=benchmark.error_details(exc))))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
