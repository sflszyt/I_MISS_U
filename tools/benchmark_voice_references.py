"""本地单模型参考对照：首抽全部保留，Tier-3 合成，禁止 pending 参考。"""
from __future__ import annotations

import argparse
import contextlib
import html
import importlib
import inspect
import json
import math
import multiprocessing
import os
import random
import re
import struct
import sys
import time
import traceback
import uuid
import wave
from pathlib import Path

try:
    from .viewpoint_manifest import sha256, no_links, read_json, read_jsonl, digest, safe_path
    from .build_relationship_data import new_output, write_json
    from .prepare_voice_upgrade import legacy_references, metrics
except ImportError:
    from viewpoint_manifest import sha256, no_links, read_json, read_jsonl, digest, safe_path
    from build_relationship_data import new_output, write_json
    from prepare_voice_upgrade import legacy_references, metrics


def validate_plan(plan):
    try:
        if plan['schema_version'] != 1 or plan['language'] != 'mandarin':
            raise ValueError('only schema 1 mandarin experiments supported')
        if plan['pad_ms'] != 200 or plan['fade_ms'] != 30:
            raise ValueError('postprocess must match live 200 ms pad / 30 ms fade')
        seeds = plan['seeds']
        if not seeds or len(seeds) > 4 or len(set(seeds)) != len(seeds) or any(type(s) is not int or not 0 <= s < 2**32 for s in seeds):
            raise ValueError('invalid seeds')
        if type(plan['timeout_seconds']) not in (int, float) or not 1 <= plan['timeout_seconds'] <= 600:
            raise ValueError('invalid timeout')
        for key in ('model_dir', 'checkpoint'):
            path = Path(plan[key])
            no_links(path)
            if not path.is_absolute() or not path.exists():
                raise ValueError('local model and checkpoint required')
        if not Path(plan['model_dir']).is_dir() or not Path(plan['checkpoint']).is_file():
            raise ValueError('invalid model directory or checkpoint file')
        refs = plan['references']
        if not 2 <= len(refs) <= 8 or len({r['id'] for r in refs}) != len(refs):
            raise ValueError('invalid reference conditions')
        hashes = set()
        for ref in refs:
            for key, hash_key in [('audio', 'audio_sha256'), ('transcript', 'transcript_sha256')]:
                path = Path(ref[key])
                no_links(path)
                if not path.is_absolute() or sha256(path) != ref[hash_key]:
                    raise ValueError('reference hash mismatch')
            if ref['audio_sha256'] in hashes:
                raise ValueError('same audio cannot be independent conditions')
            hashes.add(ref['audio_sha256'])
            if not Path(ref['transcript']).read_text(encoding='utf-8-sig').strip():
                raise ValueError('empty reference transcript')
            measure = metrics(Path(ref['audio']))
            if not measure['valid'] or measure['channels'] != 1:
                raise ValueError('invalid reference audio')
            basis = ref['basis']
            if basis['kind'] == 'legacy_corrected':
                for field in ('text_mapping', 'wav_mapping'):
                    if sha256(Path(basis[field])) != basis[field+'_sha256']:
                        raise ValueError('legacy mapping changed')
                if Path(basis['text_mapping']).name != 'text' or Path(basis['wav_mapping']) != Path(basis['text_mapping']).with_name('wav.scp'):
                    raise ValueError('invalid legacy mapping pair')
                original = legacy_references(Path(basis['text_mapping']).parent, [basis['utterance_id']])[0]
                if original['audio_sha256'] != ref['audio_sha256'] or original['text'] != Path(ref['transcript']).read_text(encoding='utf-8-sig').strip():
                    raise ValueError('reference differs from corrected legacy mapping')
            elif basis['kind'] != 'existing_reference' or not basis.get('authorization'):
                raise ValueError('unapproved reference basis')
            if ref.get('speaker_status') == 'pending' or ref.get('training_eligible') is False:
                raise ValueError('pending reference forbidden')
        targets = plan['targets']
        if not targets or len(targets)*len(seeds)*len(refs) > 120:
            raise ValueError('experiment must contain 1..120 takes')
        if len({t['id'] for t in targets}) != len(targets):
            raise ValueError('duplicate target ID')
        buckets = set()
        for t in targets:
            n = len(t['text'])
            if not isinstance(t['text'], str) or not 2 <= n <= 100:
                raise ValueError('target length invalid')
            buckets.add(0 if n <= 7 else 1 if n <= 18 else 2 if n <= 30 else 3)
        if buckets != {0, 1, 2, 3}:
            raise ValueError('targets must cover 2..7, 8..18, 19..30 and longer')
    except (KeyError, TypeError, OSError) as exc:
        raise ValueError('invalid experiment plan') from None
    return plan


class OfflineDependencyError(RuntimeError):
    def __init__(self, kind):
        self.kind = kind
        super().__init__(kind)


class OfflinePolicy:
    """仅实验子进程安装；环境变量不够，ModelScope 必须显式只读缓存。"""
    def __init__(self):
        self.failures = []

    def fail(self, kind):
        self.failures.append(kind)
        raise OfflineDependencyError(kind)

    def install(self):
        # Python 3.10 Windows 的 uname 首次调用通过 cmd /c ver 查询本机版本；
        # 在第三方导入前缓存这项标准库本机信息，之后不允许启动下载子程序。
        import platform
        platform.uname()
        for name in ('HF_HUB_OFFLINE', 'TRANSFORMERS_OFFLINE', 'HF_DATASETS_OFFLINE',
                     'HF_HUB_DISABLE_TELEMETRY', 'MODELSCOPE_OFFLINE'):
            os.environ[name] = '1'

        def audit(event, args):
            if event in ('socket.connect', 'socket.connect_ex', 'socket.getaddrinfo',
                         'socket.gethostbyname', 'socket.gethostbyaddr', 'socket.sendto',
                         'subprocess.Popen', 'os.system', 'os.exec', 'os.posix_spawn'):
                self.fail('offline_network_blocked')
        sys.addaudithook(audit)

    def cached_only(self, function):
        signature = inspect.signature(function)

        def local(*args, **kwargs):
            bound = signature.bind(*args, **kwargs)
            bound.arguments['local_files_only'] = True
            try:
                return function(*bound.args, **bound.kwargs)
            except OfflineDependencyError:
                raise
            except (OSError, ValueError):
                self.fail('offline_cache_missing')
        return local

    def patch_downloaders(self):
        # 在 CosyVoice/wetext 的 from ... import 发生前绑定；拒绝网络回退。
        for package, module_name, names in (
                ('modelscope', 'modelscope.hub.snapshot_download', ('snapshot_download',)),
                ('modelscope', 'modelscope.hub.file_download', ('model_file_download',)),
                ('huggingface_hub', 'huggingface_hub._snapshot_download', ('snapshot_download',)),
                ('huggingface_hub', 'huggingface_hub.file_download', ('hf_hub_download',))):
            module = importlib.import_module(module_name)
            top = importlib.import_module(package)
            for name in names:
                wrapped = self.cached_only(getattr(module, name))
                setattr(module, name, wrapped)
                setattr(top, name, wrapped)

    def preflight_wetext(self):
        # 本机前端无 ttsfrd 时使用这些 FST；先查缓存，避免分配 GPU 后才发现缺依赖。
        from modelscope import snapshot_download
        cache = Path(snapshot_download('pengzhendong/wetext', local_files_only=True))
        for lang in ('en', 'zh'):
            for name in ('tagger.fst', 'verbalizer.fst'):
                path = cache / lang / 'tn' / name
                if not path.is_file() or path.stat().st_size == 0:
                    self.fail('offline_cache_missing')
        self.check()

    def check(self):
        # 前端有裸 except，不能让被吞掉的离线异常变成“成功且无前端”。
        if self.failures:
            raise OfflineDependencyError(self.failures[0])


class LocalModel:
    def __init__(self, plan, offline):
        import torch
        root = Path(plan['cosyvoice_root'])
        if not root.is_dir():
            raise ValueError('local CosyVoice checkout required')
        sys.path[:0] = [str(root), str(root / 'third_party/Matcha-TTS')]
        from cosyvoice.cli.cosyvoice import CosyVoice2
        self.cv = CosyVoice2(plan['model_dir'], load_jit=False, load_trt=False, load_vllm=False, fp16=False)
        offline.check()
        if getattr(self.cv.frontend, 'text_frontend', '') not in ('wetext', 'ttsfrd'):
            offline.fail('offline_frontend_unavailable')
        state = torch.load(plan['checkpoint'], map_location='cpu')
        self.cv.model.llm.load_state_dict({k:v for k,v in state.items() if isinstance(v, torch.Tensor)}, strict=True)

    def synthesize(self, text, reference, seed, language):
        import numpy as np
        import torch
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        prompt = Path(reference['transcript']).read_text(encoding='utf-8-sig').strip()
        with torch.inference_mode():
            chunks = [o['tts_speech'].detach().cpu() for o in self.cv.inference_zero_shot(
                text, prompt, reference['audio'], stream=False, speed=1.0)]
        if not chunks:
            raise ValueError('empty generation')
        return torch.cat(chunks, dim=1).numpy().flatten().tolist(), self.cv.sample_rate


def _worker(connection, plan):
    # 模型库可能回显 prompt；整个实验子进程输出静默，不留下私人文本日志。
    with open(os.devnull, 'w') as quiet, contextlib.redirect_stdout(quiet), contextlib.redirect_stderr(quiet):
        try:
            offline = OfflinePolicy()
            offline.install()
            offline.patch_downloaders()
            offline.preflight_wetext()
            model = LocalModel(plan, offline)
            connection.send(('ready', None))
            while True:
                job = connection.recv()
                if job is None:
                    break
                try:
                    result = model.synthesize(*job)
                    offline.check()
                    connection.send(('ok', result))
                except Exception as exc:
                    kind = error_kind(exc)
                    connection.send((kind, error_details(exc)))
        except Exception as exc:
            connection.send((error_kind(exc), error_details(exc)))
        finally:
            connection.close()


class ModelProcess:
    """只管理本工具创建的子进程；超时不会停止任何现役服务。"""
    def __init__(self, plan, *, worker_target=None):
        ctx = multiprocessing.get_context('spawn')
        self.connection, child = ctx.Pipe()
        self.process = ctx.Process(target=worker_target or _worker, args=(child, plan))
        self.timeout = plan['timeout_seconds']
        self.process.start()
        child.close()
        try:
            self.receive(max(self.timeout, 180))
        except BaseException:
            self.close()
            raise

    def receive(self, timeout):
        if not self.connection.poll(timeout):
            raise TimeoutError('experiment worker timeout')
        status, payload = self.connection.recv()
        if status == 'oom':
            exc = MemoryError('out of memory')
        elif status == 'error':
            exc = RuntimeError('model worker failed')
        elif status.startswith('offline_'):
            exc = OfflineDependencyError(status)
        else:
            return payload
        exc.details = payload
        raise exc

    def synthesize(self, *args):
        self.connection.send(args)
        return self.receive(self.timeout)

    def close(self):
        if self.process.is_alive():
            self.process.terminate()
        self.process.join(timeout=10)
        self.connection.close()


def postprocess_live(data, rate):
    import numpy as np
    try:
        from .tts_server import soften_onsets
    except ImportError:
        from tts_server import soften_onsets
    padded = np.pad(np.asarray(data, dtype=np.float32), (int(rate*.2), int(rate*.2)))
    return soften_onsets(padded, rate, fade_ms=30).tolist()


def error_kind(exc):
    if isinstance(exc, OfflineDependencyError):
        return exc.kind
    if isinstance(exc, MemoryError) or 'out of memory' in str(exc).lower():
        return 'oom'
    return 'timeout' if isinstance(exc, TimeoutError) else 'error'


def error_details(exc):
    """保留排错位置，不记录可能含 prompt/私人文本的异常消息或源码行。"""
    if hasattr(exc, 'details'):
        return exc.details
    return dict(error_type=type(exc).__name__,
                frames=[dict(file=Path(frame.filename).name, line=frame.lineno, function=frame.name)
                        for frame in traceback.extract_tb(exc.__traceback__)[-6:]])


def experiment_schedule(plan, smoke):
    targets = plan['targets'][:1] if smoke else plan['targets']
    seeds = plan['seeds'][:1] if smoke else plan['seeds']
    schedule = [(t, seed, r) for t in targets for seed in seeds for r in plan['references']]
    random.Random(82026).shuffle(schedule)
    return schedule


def take_identity(index, target, seed, reference, run_id):
    return dict(id=f'take-{run_id}-{index+1:03d}', target_id=target['id'], seed=seed,
                condition=reference['id'], reference_sha256=reference['audio_sha256'],
                transcript_sha256=reference['transcript_sha256'], target_sha256=digest(target['text']))


def run(plan, out, *, smoke=False, factory=None, postprocess=None):
    validate_plan(plan)
    inputs = [Path(r[k]) for r in plan['references'] for k in ('audio', 'transcript')]
    inputs += [Path(plan['checkpoint']), Path(plan['model_dir'])]
    out = new_output(out, inputs)
    out.mkdir(parents=True)
    write_json(out / 'plan.json', plan)
    targets = plan['targets'][:1] if smoke else plan['targets']
    seeds = plan['seeds'][:1] if smoke else plan['seeds']
    schedule = experiment_schedule(plan, smoke)
    run_id = uuid.uuid4().hex
    rows, jobs, key, model = [], [], [], None
    aborted, initialization_error = None, None
    try:
        try:
            model = (factory or ModelProcess)(plan)
        except Exception as exc:
            aborted = error_kind(exc)
            initialization_error = error_details(exc)
            if aborted == 'error':
                aborted = 'initialization_error'
        for index, (target, seed, ref) in enumerate(schedule):
            row = dict(take_identity(index, target, seed, ref, run_id), status='not_run', tier=3, attempt=1)
            blind = row['id']
            key.append(dict(id=blind, condition=ref['id'], target_id=target['id'], seed=seed))
            if aborted:
                row['reason'] = aborted
            else:
                start = time.monotonic()
                try:
                    data, rate = model.synthesize(target['text'], ref, seed, plan['language'])
                    if time.monotonic()-start > plan['timeout_seconds']:
                        raise TimeoutError()
                    if type(rate) is not int or rate <= 0 or not len(data) or any(not math.isfinite(v) for v in data):
                        raise ValueError('invalid generated PCM')
                    data = (postprocess or postprocess_live)(data, rate)
                    path = out / (blind+'.wav')
                    with wave.open(str(path), 'wb') as w:
                        w.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
                        w.writeframes(b''.join(struct.pack('<h', int(max(-1, min(1, v))*32767)) for v in data))
                    row.update(status='ok', wav=path.name, sha256=sha256(path),
                               duration_seconds=len(data)/rate)
                    jobs.append(dict(id=blind, wav=str(path.resolve()), lang='zh', text=target['text']))
                except Exception as exc:
                    status = error_kind(exc)
                    row.update(status=status, error_type=type(exc).__name__)
                    row['diagnostic'] = error_details(exc)
                    if status in ('oom', 'timeout') or status.startswith('offline_'):
                        aborted = status
                row['elapsed_seconds'] = round(time.monotonic()-start, 3)
            rows.append(row)
            with (out / 'results.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(row, ensure_ascii=False)+'\n')
    finally:
        if model is not None and hasattr(model, 'close'):
            model.close()
    write_json(out / 'answer-key.json', key)
    write_json(out / 'asr-jobs.json', jobs)
    write_json(out / 'summary.json', dict(total=len(rows), success=len(jobs), smoke=smoke,
                                         aborted=aborted, tier=3, retries=0,
                                         initialization_error=initialization_error,
                                         checkpoint_sha256=sha256(Path(plan['checkpoint'])),
                                         run_id=run_id, plan_sha256=sha256(out / 'plan.json'),
                                         results_sha256=sha256(out / 'results.jsonl'),
                                         asr_jobs_sha256=sha256(out / 'asr-jobs.json')))
    page = '<!doctype html><meta charset="utf-8"><title>同题盲听</title><h1>Tier-3 合成参考实验</h1><p>这些是合成声音，不是真人录音。请比较同题自然度、漏字添字及声音相似度；ASR 不能判断音色。</p>'
    for target in targets:
        page += '<h2>'+html.escape(target['text'])+'</h2>'
        for seed in seeds:
            page += '<h3>种子 '+str(seed)+'</h3>'
            for row in rows:
                if row['target_id'] == target['id'] and row['seed'] == seed:
                    page += '<p>'+row['id']+' · '+row['status']+'</p>'
                    if row['status'] == 'ok':
                        page += '<audio controls preload="none" src="'+row['wav']+'"></audio>'
    (out / 'listen.html').write_text(page, encoding='utf-8')
    return rows


def analyze(experiment, asr_path, out):
    """按 target+seed 配对；失败/缺失仍在分母，不用 CER 推断音色。"""
    experiment = Path(experiment)
    plan = validate_plan(read_json(experiment / 'plan.json'))
    summary = read_json(experiment / 'summary.json')
    if (type(summary.get('smoke')) is not bool or type(summary.get('total')) is not int
            or not re.fullmatch(r'[0-9a-f]{32}', summary.get('run_id', ''))
            or summary.get('tier') != 3 or summary.get('retries') != 0
            or summary.get('checkpoint_sha256') != sha256(Path(plan['checkpoint']))):
        raise ValueError('invalid experiment summary')
    for filename, field in [('plan.json', 'plan_sha256'), ('results.jsonl', 'results_sha256'),
                            ('asr-jobs.json', 'asr_jobs_sha256')]:
        if sha256(experiment / filename) != summary.get(field):
            raise ValueError('experiment evidence changed')
    schedule = experiment_schedule(plan, summary['smoke'])
    rows = read_jsonl(experiment / 'results.jsonl')
    if len(rows) != len(schedule) or summary['total'] != len(schedule):
        raise ValueError('results do not cover full planned schedule')
    expected_jobs = []
    allowed = {'ok', 'not_run', 'error', 'oom', 'timeout', 'offline_cache_missing',
               'offline_network_blocked', 'offline_frontend_unavailable'}
    for i, (row, (target, seed, reference)) in enumerate(zip(rows, schedule)):
        expected = take_identity(i, target, seed, reference, summary['run_id'])
        if (any(row.get(k) != value for k, value in expected.items())
                or row.get('status') not in allowed or row.get('tier') != 3 or row.get('attempt') != 1):
            raise ValueError('take identity or condition does not match plan')
        if row['status'] == 'ok':
            if row.get('wav') != row['id']+'.wav':
                raise ValueError('take WAV identity mismatch')
            audio = safe_path(experiment, row['wav'])
            if sha256(audio) != row.get('sha256') or not metrics(audio)['valid']:
                raise ValueError('take WAV changed or invalid')
            expected_jobs.append(dict(id=row['id'], wav=str(audio.resolve()), lang='zh', text=target['text']))
    jobs = read_json(experiment / 'asr-jobs.json')
    if summary.get('success') != len(expected_jobs) or jobs != expected_jobs:
        raise ValueError('ASR jobs do not match successful planned takes')
    asr_rows = read_json(Path(asr_path))
    if not isinstance(asr_rows, list) or any(not isinstance(r, dict) or not isinstance(r.get('id'), str) for r in asr_rows):
        raise ValueError('invalid ASR result records')
    by_id = {r['id']:r for r in asr_rows}
    if len(by_id) != len(asr_rows) or set(by_id)-{r['id'] for r in jobs}:
        raise ValueError('invalid ASR IDs')
    try:
        from .gsv_pipeline import compute_cer
    except ImportError:
        from gsv_pipeline import compute_cer
    job_text = {job['id']:job['text'] for job in jobs}
    pairs = {}
    for row in rows:
        result = by_id.get(row['id'], {})
        valid = row['status'] == 'ok' and 'error' not in result and isinstance(result.get('asr_text'), str)
        cer = compute_cer(job_text[row['id']], result['asr_text']) if valid else None
        pairs.setdefault((row['target_id'], row['seed']), []).append(
            dict(condition=row['condition'], generation_status=row['status'],
                 asr_status='ok' if valid else 'failed_or_missing', cer=cer if valid else None))
    output = dict(notice='CER is only a transcription proxy, not voice similarity. Failures remain in denominator.',
                  asr_binding='Unique per-run take IDs and verified input jobs. ASR output itself has no signed input hash.',
                  run_id=summary['run_id'], total=len(schedule),
                  usable_asr=sum(v['cer'] is not None for group in pairs.values() for v in group),
                  pairs=[dict(target_id=k[0], seed=k[1], conditions=v,
                              complete_pair=all(r['cer'] is not None for r in v)) for k,v in pairs.items()])
    out = new_output(out, [experiment, Path(asr_path)])
    out.mkdir(parents=True)
    write_json(out / 'paired-asr.json', output)
    return output


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan', type=Path)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--smoke', action='store_true')
    p.add_argument('--validate-only', action='store_true')
    p.add_argument('--analyze', type=Path)
    p.add_argument('--asr-results', type=Path)
    args = p.parse_args()
    if args.analyze:
        if not args.asr_results:
            p.error('--analyze requires --asr-results')
        analyze(args.analyze, args.asr_results, args.out)
    else:
        if not args.plan:
            p.error('--plan required')
        plan = read_json(args.plan)
        validate_plan(plan)
        if not args.validate_only:
            rows = run(plan, args.out, smoke=args.smoke)
            if any(row['status'] != 'ok' for row in rows):
                print('experiment retained failures; inspect private summary')
                return 1
    print('experiment operation complete; inspect private summary for failures')
    return 0


if __name__ == '__main__':
    sys.exit(main())
