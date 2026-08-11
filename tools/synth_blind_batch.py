import argparse
import json
import os
import re
import sys
import time
import traceback

sys.path.insert(0, r'C:\Users\justin\CosyVoice')
sys.path.insert(0, r'C:\Users\justin\CosyVoice\third_party\Matcha-TTS')

import torch
import torchaudio
import soundfile as sf
import numpy as np
import lameenc

MODELS = r'C:\Users\justin\CosyVoice-models\WenetSpeech-Wu-Speech-Generation'
REF = r'C:\Users\justin\Documents\I_MISS_U\people\mama\voice\reference\ref01_clip18_20220731_141056_6038514757115197166_mama.wav'
TRANSCRIPT = r'C:\Users\justin\Documents\I_MISS_U\people\mama\voice\reference\ref01_transcript.txt'

def load_prompt_text(prompt_text_path):
    with open(prompt_text_path, 'r', encoding='utf-8') as f:
        return f.read().strip()

def save_mp3_from_wav(wav_path, mp3_path):
    data, sr = sf.read(wav_path)  # float reading
    if data.ndim > 1:
        data = data.mean(axis=1)
    
    full_data = (np.clip(data, -1.0, 1.0) * 32767).astype(np.int16)
    encoder2 = lameenc.Encoder()
    encoder2.set_bit_rate(64)
    encoder2.set_channels(1)
    encoder2.set_quality(2)
    encoder2.set_in_sample_rate(sr)
    mp3_data_full = encoder2.encode(full_data.tobytes())
    mp3_data_full += encoder2.flush()
    
    with open(mp3_path, 'wb') as f:
        f.write(mp3_data_full)

    # verify on middle segment
    check, _ = sf.read(mp3_path)
    if check.ndim > 1:
        check = check.mean(axis=1)
    
    # Take middle 80% of the mp3 for validation
    if len(check) > 0:
        mid_start = int(len(check) * 0.1)
        mid_end = int(len(check) * 0.9)
        check_middle = check[mid_start:mid_end]
        rms = float(np.sqrt(np.mean(check_middle**2))) if len(check_middle) > 0 else 0.0
    else:
        rms = 0.0
    
    if rms <= 0.005:
        raise RuntimeError(f"MP3 validation failed for {mp3_path}: RMS={rms:.6f} <= 0.005")
    return rms

def compute_rms_windows(wav_tensor, sample_rate, window_ms=50):
    """Compute RMS in fixed windows over the tensor."""
    audio_np = wav_tensor.numpy().flatten()
    window_size = int(sample_rate * window_ms / 1000)
    n_windows = max(1, len(audio_np) // window_size)
    rms_values = []
    for i in range(n_windows):
        chunk = audio_np[i*window_size:(i+1)*window_size]
        if len(chunk) > 0:
            rms_values.append(float(np.sqrt(np.mean(chunk**2))))
    return np.array(rms_values) if rms_values else np.array([0.0])

def append_report(report_path, record):
    try:
        with open(report_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
        return True
    except Exception as e:
        utt = record.get('utt', 'unknown')
        print(f'warn: report write failed for {utt}: {e}')
        return False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--texts', required=True, help='JSONL file with utt and text per line')
    parser.add_argument('--exp-dir', required=True)
    parser.add_argument('--epoch', required=True, type=int)
    parser.add_argument('--out-dir', required=True)
    parser.add_argument('--pad-ms', type=int, default=300)
    parser.add_argument('--exp-tag', default='')
    parser.add_argument('--models-dir', default=MODELS)
    parser.add_argument('--ref', default=REF)
    parser.add_argument('--prompt-text', default=TRANSCRIPT)
    parser.add_argument('--max-retries', type=int, default=3)
    parser.add_argument('--sec-per-char', type=float, default=0.32)
    parser.add_argument('--dur-slack', type=float, default=2.0)
    parser.add_argument('--onset-window', type=float, default=1.0)
    parser.add_argument('--onset-ratio', type=float, default=0.25)
    parser.add_argument('--overwrite', action='store_true', help='Overwrite existing outputs')
    args = parser.parse_args()

    if args.pad_ms < 0:
        print(f'ERROR: --pad-ms must be >= 0, got {args.pad_ms}')
        sys.exit(1)

    # Validate texts file first
    utt_pattern = re.compile(r'^[A-Za-z0-9_-]{1,64}$')
    texts_data = []
    try:
        with open(args.texts, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    print(f'ERROR: Line {line_num}: Invalid JSON: {line}')
                    sys.exit(2)
                utt = item.get('utt', '')
                text = item.get('text', '')
                if not utt_pattern.match(utt):
                    print(f'ERROR: Line {line_num}: Invalid utt "{utt}" (must match ^[A-Za-z0-9_-]{{1,64}}$)')
                    sys.exit(2)
                if not text or not text.strip():
                    print(f'ERROR: Line {line_num}: Empty text for utt "{utt}"')
                    sys.exit(2)
                texts_data.append((utt, text.strip()))
    except FileNotFoundError:
        print(f'ERROR: Texts file not found: {args.texts}')
        sys.exit(2)

    if not texts_data:
        print('ERROR: No valid entries in texts file')
        sys.exit(2)

    epoch = args.epoch
    exp_dir = args.exp_dir
    out_dir = args.out_dir
    pad_ms = args.pad_ms
    exp_tag = args.exp_tag
    models_dir = args.models_dir
    ref_path = args.ref
    prompt_text_path = args.prompt_text
    max_retries = args.max_retries
    sec_per_char = args.sec_per_char
    dur_slack = args.dur_slack
    onset_window = args.onset_window
    onset_ratio = args.onset_ratio
    overwrite = args.overwrite

    wav_dir = os.path.join(out_dir, 'wav')
    mp3_dir = os.path.join(out_dir, 'mp3')
    os.makedirs(wav_dir, exist_ok=True)
    os.makedirs(mp3_dir, exist_ok=True)

    # Load prompt text
    prompt_text = load_prompt_text(prompt_text_path)

    # Load model
    try:
        from cosyvoice.cli.cosyvoice import CosyVoice2
        cv = CosyVoice2(
            os.path.join(models_dir, 'CosyVoice2-Wu-SFT'),
            load_jit=False,
            load_trt=False,
            load_vllm=False,
            fp16=False
        )
    except Exception as e:
        print(f'ERROR: Model initialization failed: {e}')
        traceback.print_exc()
        sys.exit(1)

    # Load checkpoint
    ckpt_path = os.path.join(exp_dir, f'epoch_{epoch}_whole.pt')
    if not os.path.isfile(ckpt_path):
        print(f'ERROR: Checkpoint not found: {ckpt_path}')
        sys.exit(1)
    print(f'Loading checkpoint epoch={epoch}: {ckpt_path}')
    t0 = time.time()
    try:
        state = torch.load(ckpt_path, map_location='cpu')
        filtered = {k: v for k, v in state.items() if isinstance(v, torch.Tensor)}
        missing, unexpected = cv.model.llm.load_state_dict(filtered, strict=False)
        print(f'  loaded epoch={epoch}, missing={len(missing)}, unexpected={len(unexpected)}')
        if missing or unexpected:
            raise RuntimeError(
                f"State dict mismatch for epoch {epoch}: missing={len(missing)}, unexpected={len(unexpected)}"
            )
        print(f'  checkpoint load time: {time.time()-t0:.2f}s')
    except Exception as e:
        print(f'ERROR: Checkpoint load failed: {e}')
        traceback.print_exc()
        sys.exit(1)

    # Prepare QC report
    qc_report_path = os.path.join(out_dir, 'qc_report.jsonl')
    if os.path.exists(qc_report_path):
        os.remove(qc_report_path)

    # Stats
    stats = {'success': 0, 'qc_fail': 0, 'error': 0}

    total = len(texts_data)
    for idx, (utt, text) in enumerate(texts_data, 1):
        # Generate base name
        if exp_tag:
            base_name = f'{utt}_{exp_tag}_e{epoch}'
        else:
            base_name = f'{utt}_e{epoch}'
        mp3_path = os.path.join(mp3_dir, f'{base_name}.mp3')

        total_start = time.time()
        try:
            # Check if exists and skip if not overwrite
            if os.path.exists(mp3_path) and not overwrite:
                print(f'[{idx}/{total}] {utt} SKIP (exists)')
                stats['success'] += 1
                # Still write report entry
                report_entry = {
                    'utt': utt,
                    'text': text,
                    'chars': len(text),
                    'epoch': epoch,
                    'skipped': True,
                    'takes': [],
                    'chosen_index': None,
                    'qc_pass': None,
                    'onset_flag': None,
                    'retries': 0,
                    'elapsed_s': 0.0
                }
                append_report(qc_report_path, report_entry)
                continue

            # Synthesis with retries
            takes = []
            chosen_wav = None
            chosen_index = -1
            qc_pass = True
            onset_flag = False
            retries_used = 0

            full_text = '<|wuyu|>' + text
            limit = len(text) * sec_per_char + dur_slack

            # First take
            take_num = 1
            for attempt in range(max_retries + 1):
                segments = []
                for out in cv.inference_zero_shot(
                    full_text,
                    prompt_text,
                    ref_path,
                    stream=False,
                    speed=1.0
                ):
                    segments.append(out['tts_speech'])
                if not segments:
                    raise RuntimeError(f"No audio generated for {utt} take {take_num}")
                wav_unpadded = torch.cat(segments, dim=1)

                duration = wav_unpadded.shape[1] / cv.sample_rate

                # QC-A: duration
                take_qc_pass = duration <= limit
                # QC-B: onset energy
                onset_rms = compute_rms_windows(wav_unpadded, cv.sample_rate, 50)
                window_count = max(1, int(onset_window * 1000 / 50))
                onset_mean = float(np.mean(onset_rms[:window_count])) if len(onset_rms) > 0 else 0.0
                full_median = float(np.median(onset_rms)) if len(onset_rms) > 0 else 0.0
                take_onset_flag = onset_mean < onset_ratio * full_median

                takes.append({
                    'duration': duration,
                    'qc_pass': take_qc_pass,
                    'onset_flag': take_onset_flag
                })

                status = 'OK' if take_qc_pass else 'OVER'
                print(f'[{idx}/{total}] {utt} take{take_num} dur={duration:.1f}s limit={limit:.1f}s {status} -> {mp3_path}')

                if take_qc_pass:
                    chosen_wav = wav_unpadded
                    chosen_index = take_num - 1
                    qc_pass = True
                    onset_flag = take_onset_flag
                    retries_used = attempt
                    break
                else:
                    # Keep track of shortest
                    if chosen_wav is None or duration < takes[chosen_index]['duration']:
                        chosen_wav = wav_unpadded
                        chosen_index = take_num - 1
                    take_num += 1
                    retries_used = len(takes) - 1

            # If all failed QC-A, use shortest
            if chosen_index >= 0 and not takes[chosen_index]['qc_pass']:
                qc_pass = False
                onset_flag = takes[chosen_index]['onset_flag']

            if chosen_wav is None:
                raise RuntimeError(f"No audio generated for {utt}")

            # Add padding
            if pad_ms > 0:
                pad_samples = int(cv.sample_rate * pad_ms / 1000)
                pad = torch.zeros((chosen_wav.shape[0], pad_samples), dtype=chosen_wav.dtype)
                wav_padded = torch.cat([pad, chosen_wav, pad], dim=1)
            else:
                wav_padded = chosen_wav

            # Save files
            wav_path = os.path.join(wav_dir, f'{base_name}.wav')
            torchaudio.save(wav_path, wav_padded, cv.sample_rate)
            save_mp3_from_wav(wav_path, mp3_path)

            elapsed = time.time() - total_start
            stats['success' if qc_pass else 'qc_fail'] += 1

            # Report
            report_entry = {
                'utt': utt,
                'text': text,
                'chars': len(text),
                'epoch': epoch,
                'takes': [{
                    'duration': round(t['duration'], 2),
                    'qc_pass': t['qc_pass'],
                    'onset_flag': t['onset_flag']
                } for t in takes],
                'chosen_index': chosen_index,
                'qc_pass': qc_pass,
                'onset_flag': onset_flag if chosen_index >= 0 else False,
                'retries': retries_used,
                'elapsed_s': round(elapsed, 1)
            }
            append_report(qc_report_path, report_entry)

            if not qc_pass:
                print(f'  -> QC fail (duration), used shortest take, onset_flag={onset_flag}')

        except Exception as e:
            elapsed = time.time() - total_start
            stats['error'] += 1
            print(f'[{idx}/{total}] {utt} ERROR: {e}')
            traceback.print_exc()
            report_entry = {
                'utt': utt,
                'text': text,
                'chars': len(text),
                'epoch': epoch,
                'takes': [{
                    'duration': round(t['duration'], 2),
                    'qc_pass': t['qc_pass'],
                    'onset_flag': t['onset_flag']
                } for t in takes],
                'chosen_index': chosen_index if chosen_index >= 0 else None,
                'qc_pass': qc_pass if chosen_wav is not None else False,
                'onset_flag': onset_flag if chosen_index >= 0 else False,
                'retries': retries_used,
                'elapsed_s': round(elapsed, 1),
                'error': str(e)
            }
            append_report(qc_report_path, report_entry)

    # Summary
    print(f'\n=== Summary ===')
    print(f'Succeeded: {stats["success"]}')
    print(f'QC failed (duration): {stats["qc_fail"]}')
    print(f'Errors: {stats["error"]}')

    if stats['error'] > 0:
        sys.exit(1)
    # QC fails are OK, exit 0

if __name__ == '__main__':
    main()
