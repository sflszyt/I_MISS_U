"""离线 SenseVoice 缓存探测/辅助回读；只接受本比较工具的合成输出。"""
import argparse
import contextlib
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

try:
    from . import compare_voice_training as comparison
except ImportError:
    import compare_voice_training as comparison


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--model', type=Path, default=(Path.home() / '.cache/modelscope/models/iic--SenseVoiceSmall/snapshots/master'))
    parser.add_argument('--probe', action='store_true', help='仅离线加载本地 ASR 模型，不读取音频')
    args = parser.parse_args()
    comparison.require(args.probe or args.experiment is not None, 'experiment required')
    experiment = comparison.checked_path(args.experiment) if args.experiment else None
    model = comparison.checked_path(args.model)
    comparison.require(model.is_dir() and (model/'configuration.json').is_file(), 'local ASR cache missing')
    out = comparison.training.fresh_output(args.out, [p for p in (experiment, model) if p is not None])
    out.mkdir(parents=True)
    jobs = []
    rows = []
    if not args.probe:
        manifest = comparison.read_json(experiment/'manifest.json')
        rows = comparison.training.read_jsonl(experiment/'results.jsonl')
        comparison.require(manifest['tier'] == 3 and manifest['targets'] == comparison.TARGETS
                           and len(rows) == 24, 'not a frozen comparison experiment')
    for row in rows:
        if row['status'] != 'ok':
            continue
        wav = comparison.checked_path(experiment/row['wav'])
        comparison.require(wav.parent == experiment and comparison.sha256(wav) == row['sha256'], 'audio binding changed')
        target = next(t for t in comparison.TARGETS if t['id'] == row['target_id'])
        jobs.append(dict(id=row['id'], wav=str(wav), text=target['text'], lang='zh'))
    comparison.write_json(out/'jobs.json', jobs)
    # 与已执行的 v3 启动一致：仅在封网前缓存 ffmpeg 版本查询。
    original = subprocess.check_output
    try:
        version = original(['ffmpeg', '-version'], stderr=subprocess.STDOUT)
    except FileNotFoundError:
        version = None

    def cached_version(command, *pos, **kw):
        if command == ['ffmpeg', '-version'] and not pos and kw == {'stderr': subprocess.STDOUT}:
            if version is None:
                raise FileNotFoundError('ffmpeg unavailable')
            return version
        return original(command, *pos, **kw)

    subprocess.check_output = cached_version
    policy = comparison.benchmark.OfflinePolicy()
    try:
        with open(os.devnull, 'w') as quiet, contextlib.redirect_stdout(quiet), contextlib.redirect_stderr(quiet):
            policy.install()
            policy.patch_downloaders()
            if args.probe:
                from funasr import AutoModel
                AutoModel(model=str(model), disable_update=True, device='cpu')
            else:
                try:
                    from .gsv_pipeline import cmd_asr
                except ImportError:
                    from gsv_pipeline import cmd_asr
                try:
                    cmd_asr(SimpleNamespace(jobs=str(out/'jobs.json'), out=str(out/'results.json'), model=str(model)))
                except SystemExit as exc:
                    if exc.code not in (None, 0):
                        raise RuntimeError('ASR helper failed') from None
            policy.check()
        results = [] if args.probe else comparison.read_json(out/'results.json')
        comparison.write_json(out/'summary.json', dict(success=True, probe=args.probe, planned=24,
            generated=len(jobs), missing_generated=24-len(jobs), asr_success=sum('cer' in r for r in results),
            asr_failed=sum('cer' not in r for r in results), limitation='ASR is auxiliary; zh recognition on wu is not voice-quality evidence.'))
        return 0
    except Exception as exc:
        comparison.write_json(out/'failure.json', dict(success=False, diagnostic=comparison.benchmark.error_details(exc)))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
