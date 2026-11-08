"""冻结审批的本地 LLM 小样本试验；不修改现役声音或第三方源码。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
from contextlib import contextmanager
from functools import partial
from pathlib import Path

try:
    from .build_reviewed_language_inputs import ledger, hashes, require
    from .build_mobile_review import checked_path, separate
    from .viewpoint_manifest import digest, read_json, read_jsonl, sha256, no_links
except ImportError:
    from build_reviewed_language_inputs import ledger, hashes, require
    from build_mobile_review import checked_path, separate
    from viewpoint_manifest import digest, read_json, read_jsonl, sha256, no_links


LATEST = dict(ab='9d049dab4653457db7d0ebab04608034',
              source='d97dce02c36a48209e34fe3bc839acb6',
              language='a6302ba985e740e89cabde950347e513')
RECIPE = dict(seed=1986, epochs=2, successful_updates=20, lr=1e-6,
              batch_size=1, accumulation=1, clip_norm=5, optimizer='Adam',
              initialization='weights_only', legacy_samples=0, precision='float32')
UPSTREAM_NAMES = ['report.json', 'excluded.jsonl', 'wu/train.jsonl',
                  'wu/validation.jsonl', 'mandarin/train.jsonl', 'mandarin/validation.jsonl']


def write_json(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def verify_hashes(expected):
    require(bool(expected), 'empty frozen input set')
    for path, wanted in expected.items():
        require(sha256(checked_path(path)).lower() == wanted.lower(), 'frozen input hash changed')


def validate_snapshot(snapshot, expected_digest):
    require(snapshot['latest'] == LATEST, 'formal latest changed; derive new version')
    require(digest(snapshot) == expected_digest, 'formal ledger changed')


def fresh_output(path, protected):
    path = checked_path(path)
    require(not path.exists(), 'output exists; use new directory')
    require('raw' not in [p.lower() for p in path.parts], 'raw is read-only')
    return separate(path, protected)


def validate_rows(rows):
    require(len(rows) == 11, 'expected exactly 11 approved items')
    groups = {'train': [], 'validation': []}
    for row in rows:
        require(row.get('split') in groups, 'unknown split')
        require(row.get('speaker_id') == 'mama' and row.get('training_eligible') is True
                and row.get('exclusion_reasons') == [], 'unapproved speaker/sample')
        require(isinstance(row.get('text'), str) and row['text'].strip()
                and '<|' not in row['text'], 'empty text or injected language token')
        require(row.get('effective_language') in ('wu', 'mandarin'), 'unknown language')
        provenance = row.get('provenance', {})
        require(bool(provenance.get('source_record_id')) and bool(row.get('parent_record_id')),
                'unknown source provenance')
        groups[row['split']].append(row)
    require(len(groups['train']) == 10 and len(groups['validation']) == 1,
            'expected 10 training and 1 held-out item')
    require(sum(r['effective_language'] == 'wu' for r in groups['train']) == 9
            and groups['validation'][0]['effective_language'] == 'wu', 'language count mismatch')
    for key in ('record_id', 'audio_sha256', 'dedup_group', 'parent_record_id'):
        values = [r.get(key) for r in rows]
        require(all(values) and len(set(values)) == 11, 'duplicate or unknown identity/source group')
    sources = [r['provenance']['source_record_id'] for r in rows]
    require(len(set(sources)) == 11, 'source group overlap')
    return groups


def validate_upstream(root, state, pins, pins_sha256):
    require(sha256(checked_path(pins)).lower() == pins_sha256.lower(), 'upstream pins changed')
    entries = read_json(pins)
    pinned = {str(checked_path(e['path'])): e['sha256'].lower() for e in entries}
    require({str(checked_path(root/n)) for n in UPSTREAM_NAMES} <= set(pinned),
            'upstream prepared files not fully pinned')
    verify_hashes(pinned)
    report = read_json(root/'report.json')
    validate_snapshot(ledger(state), report['formal_ledger_sha256'])
    verify_hashes(report['input_sha256'])
    require(report['legacy_samples_added'] == 0, 'unexpected legacy samples')
    rows = []
    for language in ('wu', 'mandarin'):
        for split in ('train', 'validation'):
            for row in read_jsonl(root/language/(split+'.jsonl')):
                require(row['effective_language'] == language and row['split'] == split,
                        'file membership mismatch')
                require(row['language_receipt'] == LATEST['language']
                        and row['source_review_receipt'] == LATEST['source'], 'stale row approval')
                require(sha256(checked_path(row['audio_file'])) == row['audio_sha256'], 'audio changed')
                require(row['review']['text'] == row['text'], 'approved transcript changed')
                rows.append(row)
    validate_rows(rows)
    return rows, report


def offline(vendor):
    # 模型构造前固定离线模式，不修改持久环境或第三方文件。
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    os.environ['HF_DATASETS_OFFLINE'] = '1'
    sys.path.insert(0, str(vendor))
    sys.path.insert(0, str(vendor/'third_party/Matcha-TTS'))
    os.environ.pop('onnx_path', None)
    try:
        from .benchmark_voice_references import OfflinePolicy
    except ImportError:
        from benchmark_voice_references import OfflinePolicy
    policy = OfflinePolicy()
    policy.install()
    return policy


def model_inputs(vendor, model_root, checkpoint):
    paths = [checkpoint, model_root/'speech_tokenizer_v2.onnx']
    paths += [p for p in (model_root/'CosyVoice-BlankEN').rglob('*') if p.is_file()]
    paths += list((vendor/'cosyvoice').rglob('*.py'))
    paths += list(Path(__file__).resolve().parent.glob('*.py'))
    require(len(paths) > 5, 'missing local model/source files')
    return hashes(paths)


def validate_feature(feature):
    import torch
    require(set(feature) == {'text_token', 'text_token_len', 'speech_token', 'speech_token_len'},
            'unexpected model feature fields')
    for key, limit in (('text_token', 200000), ('speech_token', 6561)):
        value, length = feature[key], feature[key+'_len']
        require(isinstance(value, torch.Tensor) and value.ndim == 2 and value.shape[0] == 1
                and value.shape[1] > 0 and value.dtype in (torch.int32, torch.int64), 'empty/invalid tokens')
        require(length.shape == (1,) and length.dtype in (torch.int32, torch.int64)
                and length.item() == value.shape[1], 'invalid token length')
        require(bool((value >= 0).all()) and bool((value < limit).all()), 'token out of vocabulary')


def native_frontend(model_root):
    import torch
    import onnxruntime as ort
    from cosyvoice.cli.frontend import CosyVoiceFrontEnd
    from cosyvoice.tokenizer.tokenizer import get_qwen_tokenizer
    # Qwen2LM forward 不消费 mel/说话人向量。只装配原生提取方法所需属性，
    # 避免默认构造器自动选择 CUDA 或初始化不需要的文本归一化器。
    frontend = CosyVoiceFrontEnd.__new__(CosyVoiceFrontEnd)
    frontend.device = torch.device('cpu')
    frontend.tokenizer = get_qwen_tokenizer(str(model_root/'CosyVoice-BlankEN'), False)
    frontend.allowed_special = 'all'
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    frontend.speech_tokenizer_session = ort.InferenceSession(
        str(model_root/'speech_tokenizer_v2.onnx'), sess_options=options,
        providers=['CPUExecutionProvider'])
    return frontend


def prepare(args):
    upstream, state = checked_path(args.upstream), checked_path(args.state_dir)
    vendor, model_root, checkpoint = map(checked_path, (args.vendor, args.model_root, args.checkpoint))
    rows, report = validate_upstream(upstream, state, args.pins, args.pins_sha256)
    dependencies = model_inputs(vendor, model_root, checkpoint)
    protected = [upstream, state, vendor, model_root, checkpoint, *map(Path, report['input_sha256'])]
    out = fresh_output(args.out, protected)
    policy = offline(vendor)
    import torch
    frontend = native_frontend(model_root)
    out.mkdir(parents=True, exist_ok=False)
    try:
        entries = []
        for row in sorted(rows, key=lambda r: (r['split'], r['record_id'])):
            text, text_len = frontend._extract_text_token(row['text'])
            speech, speech_len = frontend._extract_speech_token(row['audio_file'])
            feature = dict(text_token=text, text_token_len=text_len,
                           speech_token=speech, speech_token_len=speech_len)
            validate_feature(feature)
            relative = row['split']+'/'+row['record_id']+'.pt'
            path = out/relative
            path.parent.mkdir(exist_ok=True)
            with path.open('xb') as stream:
                torch.save(feature, stream)
            entries.append(dict(row, feature_file=relative, feature_sha256=sha256(path),
                                text_tokens=int(text_len.item()), speech_tokens=int(speech_len.item())))
        manifest = dict(items=entries, speaker_id='mama', speaker_embeddings_used=False,
                        inference_references=[], train_count=10, validation_count=1)
        write_json(out/'manifest.json', manifest)
        for split in ('train', 'validation'):
            with (out/(split+'.list')).open('x', encoding='utf-8') as stream:
                stream.writelines(e['feature_file']+'\n' for e in entries if e['split'] == split)
        config = dict(recipe=RECIPE, upstream=str(upstream), state_dir=str(state),
                      pins=str(checked_path(args.pins)), pins_sha256=args.pins_sha256.lower(),
                      vendor=str(vendor), model_root=str(model_root), checkpoint=str(checkpoint),
                      checkpoint_sha256=dependencies[str(checkpoint)], dependency_sha256=dependencies,
                      implementation_sha256=sha256(Path(__file__)), formal_ledger_sha256=report['formal_ledger_sha256'])
        write_json(out/'config.json', config)
        validate_upstream(upstream, state, args.pins, args.pins_sha256)
        verify_hashes(dependencies)
        policy.check()
        output_hashes = hashes([p for p in out.rglob('*') if p.is_file()])
        write_json(out/'prepared.json', dict(success=True, training_started=False,
                   output_sha256=output_hashes, train_count=10, validation_count=1))
    except Exception as exc:
        write_json(out/'failure.json', dict(success=False, error_type=type(exc).__name__))
        raise
    return out


def validate_prepared(root, expected_sha256):
    require(sha256(root/'prepared.json').lower() == expected_sha256.lower(), 'prepared seal changed')
    seal = read_json(root/'prepared.json')
    require(seal.get('success') is True and seal.get('training_started') is False, 'incomplete preparation')
    verify_hashes(seal['output_sha256'])
    config = read_json(root/'config.json')
    require(config['recipe'] == RECIPE and config['implementation_sha256'] == sha256(Path(__file__)),
            'recipe or implementation changed; prepare new version')
    rows, _ = validate_upstream(Path(config['upstream']), Path(config['state_dir']),
                               Path(config['pins']), config['pins_sha256'])
    verify_hashes(config['dependency_sha256'])
    manifest = read_json(root/'manifest.json')
    entries = manifest['items']
    validate_rows(entries)
    require(manifest['speaker_embeddings_used'] is False and manifest['inference_references'] == [],
            'unexpected reference/embedding use')
    original = {r['record_id']: r for r in rows}
    for entry in entries:
        require(all(entry.get(k) == v for k, v in original[entry['record_id']].items()),
                'prepared membership/provenance differs from approved inputs')
        expected = entry['split']+'/'+entry['record_id']+'.pt'
        require(entry['feature_file'] == expected and sha256(checked_path(root/expected)) == entry['feature_sha256'],
                'feature membership/hash changed')
    return config, entries


def tensor_digest(tensor):
    return hashlib.sha256(tensor.detach().cpu().contiguous().numpy().tobytes()).hexdigest()


def optimize(model, batches, device, log, stable, optimizer_factory=None):
    import torch
    require(len(batches) == 10, 'empty/filtered training set; exactly 10 required')
    parameters = [p for p in model.parameters() if p.requires_grad]
    require(bool(parameters), 'no trainable parameters')
    optimizer = (optimizer_factory or torch.optim.Adam)(parameters, lr=RECIPE['lr'])
    require(not optimizer.state, 'optimizer must be fresh')
    before = {name: tensor_digest(p) for name, p in model.named_parameters() if p.requires_grad}
    updates = 0
    model.train()
    for epoch in range(2):
        for index, batch in enumerate(batches):
            stable()
            optimizer.zero_grad(set_to_none=True)
            loss = model(batch, device)['loss']
            require(loss.numel() == 1 and bool(torch.isfinite(loss)), 'nonfinite loss')
            loss.backward()
            require(any(p.grad is not None for p in parameters), 'no gradients')
            norm = torch.nn.utils.clip_grad_norm_(parameters, 5, error_if_nonfinite=True)
            optimizer.step()
            for p in parameters:
                require(bool(torch.isfinite(p).all()), 'nonfinite updated weight')
                if p.grad is not None:
                    require(int(optimizer.state[p].get('step', 0)) == updates + 1, 'skipped optimizer update')
                    require(bool(torch.isfinite(optimizer.state[p]['exp_avg']).all())
                            and bool(torch.isfinite(optimizer.state[p]['exp_avg_sq']).all()), 'nonfinite Adam state')
            updates += 1
            log(dict(step=updates, epoch=epoch, batch_index=index, loss=float(loss.detach()),
                     gradient_norm=float(norm), lr=RECIPE['lr']))
    stable()
    changed = [name for name, p in model.named_parameters()
               if name in before and tensor_digest(p) != before[name]]
    steps = sorted({int(s['step']) for s in optimizer.state.values()})
    require(updates == 20 and steps == [20] and bool(changed), 'incomplete or zero-change optimization')
    return dict(successful_updates=updates, optimizer_steps=steps, weights_changed=True,
                changed_tensor_names=changed, initial_tensor_sha256=before)


@contextmanager
def experiment_lock():
    # 固定仓库锁只约束本工具；不停止或干预任何线上进程。
    path = Path(__file__).resolve().parents[1]/'data/work/voice-training-pilot.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        stream.write(str(os.getpid()))
    try:
        yield
    finally:
        path.unlink()


def native_model(model_root, checkpoint):
    import torch
    from cosyvoice.llm.llm import Qwen2LM, Qwen2Encoder
    from cosyvoice.utils.common import ras_sampling
    model = Qwen2LM(896, 896, 6561, Qwen2Encoder(str(model_root/'CosyVoice-BlankEN')),
                   partial(ras_sampling, top_p=.8, top_k=25, win_size=10, tau_r=.1),
                   length_normalized_loss=True, lsm_weight=0., mix_ratio=[5, 15])
    state = torch.load(checkpoint, map_location='cpu', weights_only=True)
    metadata = {k: v for k, v in state.items() if not isinstance(v, torch.Tensor)}
    require(set(metadata) <= {'epoch', 'step'}, 'unknown checkpoint metadata')
    weights = {k: v for k, v in state.items() if isinstance(v, torch.Tensor)}
    compatibility = model.load_state_dict(weights, strict=True)
    return model, dict(source_metadata=metadata, missing_keys=compatibility.missing_keys,
                       unexpected_keys=compatibility.unexpected_keys, initialized_epoch=0, initialized_step=0)


def train(args):
    root = checked_path(args.prepared)
    config, entries = validate_prepared(root, args.prepared_sha256)
    checkpoint = checked_path(args.checkpoint)
    require(str(checkpoint) == config['checkpoint'] and sha256(checkpoint) == config['checkpoint_sha256'],
            'checkpoint differs from frozen initialization')
    out = fresh_output(args.out, [root, Path(config['upstream']), Path(config['state_dir']),
                                Path(config['vendor']), Path(config['model_root']), checkpoint])
    out.mkdir(parents=True, exist_ok=False)
    peak = 0
    try:
        with experiment_lock():
            policy = offline(Path(config['vendor']))
            import torch
            import numpy as np
            require(torch.cuda.is_available(), 'CUDA required; no external fallback')
            free, total = torch.cuda.mem_get_info()
            require(free >= 12 * 1024**3, 'less than 12 GiB free; do not touch services')
            torch.cuda.set_per_process_memory_fraction((free - 3 * 1024**3) / total)
            torch.cuda.reset_peak_memory_stats()
            random.seed(1986)
            np.random.seed(1986)
            torch.manual_seed(1986)
            torch.cuda.manual_seed_all(1986)
            torch.backends.cudnn.benchmark = False
            batches = []
            for entry in entries:
                feature = torch.load(root/entry['feature_file'], map_location='cpu', weights_only=True)
                validate_feature(feature)
                if entry['split'] == 'train':
                    batches.append(feature)
            model, compatibility = native_model(Path(config['model_root']), checkpoint)
            write_json(out/'load.json', compatibility)
            model = model.to(torch.device('cuda'))
            # 不恢复 epoch14 的计数或 optimizer；两次按冻结顺序遍历十条。
            def stable():
                policy.check()
                validate_prepared(root, args.prepared_sha256)
                require(torch.cuda.mem_get_info()[0] >= 3 * 1024**3, 'CUDA headroom below 3 GiB')
            with (out/'steps.jsonl').open('x', encoding='utf-8') as stream:
                def log(record):
                    stream.write(json.dumps(record)+'\n')
                    stream.flush()
                result = optimize(model, batches, torch.device('cuda'), log, stable)
            stable()
            peak = torch.cuda.max_memory_reserved()
            final = out/'candidate_step20.pt'
            with final.open('xb') as stream:
                torch.save({**{k: v.cpu() for k, v in model.state_dict().items()}, 'epoch': 1, 'step': 20}, stream)
            stable()
            report = dict(success=True, **result, compatibility=compatibility,
                       recipe=RECIPE, prepared=str(root), prepared_dir=str(root), prepared_sha256=args.prepared_sha256,
                       config_sha256=sha256(root/'config.json'), checkpoint=str(final),
                       checkpoint_sha256=sha256(final), step_log_sha256=sha256(out/'steps.jsonl'),
                       peak_reserved_bytes=peak, holdout_used_for_training=False,
                       holdout_loss_computed=False, live_voice_changed=False)
        # 锁释放也可能失败；全部清理成功后才发布成功标记。
        # 先关闭临时文件，再原子重命名，写入/close 失败不会留下有效报告。
        pending = out/'report.pending.json'
        write_json(pending, report)
        pending.rename(out/'report.json')
    except Exception as exc:
        if 'torch' in locals() and torch.cuda.is_available():
            peak = torch.cuda.max_memory_reserved()
        write_json(out/'failure.json', dict(success=False, error_type=type(exc).__name__, peak_reserved_bytes=peak))
        raise
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    stages = parser.add_subparsers(dest='stage', required=True)
    p = stages.add_parser('prepare')
    for name in ('upstream', 'state-dir', 'pins', 'vendor', 'model-root', 'checkpoint', 'out'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--pins-sha256', required=True)
    t = stages.add_parser('train')
    for name in ('prepared', 'checkpoint', 'out'):
        t.add_argument('--'+name, type=Path, required=True)
    t.add_argument('--prepared-sha256', required=True)
    args = parser.parse_args()
    try:
        if args.stage == 'prepare':
            with experiment_lock():
                prepare(args)
        else:
            train(args)
    except Exception as exc:
        # 不在命令行泄漏私有正文、模型输入或音频路径。
        print('FAILED: '+type(exc).__name__, file=sys.stderr)
        return 1
    print(args.stage+' completed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
