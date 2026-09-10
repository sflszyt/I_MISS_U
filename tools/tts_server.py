import argparse
import hmac
import io
import json
import os
import re
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import soundfile as sf
import torch
import lameenc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ingest_sessions
from ingest_sessions import SessionsIngestScheduler


MODELS_DIR_DEFAULT = r'C:\Users\justin\CosyVoice-models\WenetSpeech-Wu-Speech-Generation'
EXP_DIR_DEFAULT = r'C:\Users\justin\wu-sft\v02_full\exp\mama_v02f160_llm'
EPOCH_DEFAULT = 14
PORT_DEFAULT = 8022
HOST_DEFAULT = '0.0.0.0'
REF_DEFAULT = r'C:\Users\justin\Documents\I_MISS_U\people\mama\voice\reference\ref01_clip18_20220731_141056_6038514757115197166_mama.wav'
PROMPT_TEXT_DEFAULT = r'C:\Users\justin\Documents\I_MISS_U\people\mama\voice\reference\ref01_transcript.txt'
DEFAULT_LANG_DEFAULT = 'mandarin'
WU_PREFIX = '<|wuyu|>'
MAX_BODY = 65536

SESSION_ID_RE = re.compile(r'^\d{8}-\d{6}-[A-Za-z0-9]{4,12}$')
PERSON_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]*$')
SESSION_ROLES = ('user', 'simulacrum', 'event')
SESSION_MAX_TEXT = 4000
SESSION_OPTIONAL_FIELDS = {
    'ts': (str, 64), 'provider': (str, 32), 'model': (str, 128), 'emotion': (str, 32),
    'tts': (str, 32), 'page': (str, 32), 'ua': (str, 300), 'detail': (str, 500),
    'qid': (str, 64), 'aborted': (bool, None), 'retrieval_used': (list, 20),
    'messages': (int, None),
    'viewer': (str, 32), 'exclude': (bool, None),
}

BRACKET_RE = re.compile(r'[\[【（(][^\[\]【】（）()]*[\]】）)]')

VIEWER_RE = re.compile(r'^[a-z][a-z0-9_-]{0,31}$')
TOKEN_RE = re.compile(r'^[A-Za-z0-9_-]{8,128}$')


def strip_brackets(text):
    """删除成对括号及其内容（微信表情标签/动作描写），供 TTS 念白用；压缩空白后返回。"""
    prev = None
    while prev != text:
        prev = text
        text = BRACKET_RE.sub(' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def soften_onsets(data, sr, fade_ms=30, thresh=0.01, quiet=0.005, min_gap_ms=200, frame_ms=5):
    """在每个"起音"处做 fade_ms 的升余弦淡入，压掉 SFT 模型每次开口带的 ~15 ms 爆音。
    起音定义：5 ms 帧 RMS 首次 > thresh，且此前连续 >= min_gap_ms 的帧 RMS < quiet（或它是整段的第一次发声）。
    fade_ms <= 0 或数据为空时原样返回。返回 float32 副本，不改输入。"""
    if fade_ms <= 0 or data is None or len(data) == 0:
        return np.array(data, dtype=np.float32) if data is not None else data

    x = np.asarray(data, dtype=np.float32)
    if x.size == 0:
        return x.copy()

    total = len(x)
    frame = int(sr * frame_ms / 1000)
    if frame < 1:
        frame = 1

    n_frames = total // frame
    if n_frames == 0:
        return x.copy()

    x2 = x[: n_frames * frame] ** 2
    rms = np.sqrt(x2.reshape(n_frames, frame).mean(axis=1))

    min_gap_frames = max(1, int(min_gap_ms / frame_ms))
    output = x.copy()

    n = int(sr * fade_ms / 1000)
    if n < 1:
        n = 1
    t = np.arange(n, dtype=np.float32) / n
    fade_curve = 0.5 - 0.5 * np.cos(np.pi * t)

    onset_samples = []
    seen_voice = False
    quiet_run = 0
    in_voice = False

    for i in range(n_frames):
        if rms[i] < quiet:
            quiet_run += 1
            in_voice = False
        elif rms[i] <= thresh:
            # quiet <= rms <= thresh: breath/floor noise, resets quiet prefix
            quiet_run = 0
            # in_voice unchanged
        else:  # rms[i] > thresh
            if not in_voice and (not seen_voice or quiet_run >= min_gap_frames):
                onset_samples.append(i * frame)
                in_voice = True
                seen_voice = True
            quiet_run = 0

    # Apply fade at each onset start sample
    for start_sample in onset_samples:
        fade_len = min(n, total - start_sample)
        if fade_len <= 0:
            continue
        output[start_sample:start_sample + fade_len] *= fade_curve[:fade_len]

    return output


def parse_viewer_tokens(raw):
    """解析 --tokens 参数为 {token: viewer} 反查表。空串返回空 dict。非法输入打印错误并 exit(2)。"""
    if not raw:
        return {}
    result = {}
    items = raw.split(',')
    for item in items:
        if not item or ':' not in item:
            sys.stderr.write(f'Invalid --tokens entry: "{item}" (expected viewer:token)\n')
            sys.exit(2)
        viewer, token = item.split(':', 1)
        if not VIEWER_RE.fullmatch(viewer):
            sys.stderr.write(
                f'Invalid viewer in --tokens: "{viewer}" '
                f'(must match ^[a-z][a-z0-9_-]{{0,31}}$)\n'
            )
            sys.exit(2)
        if not TOKEN_RE.fullmatch(token):
            sys.stderr.write(
                f'Invalid token in --tokens for viewer "{viewer}": '
                f'token must be 8-128 chars of [A-Za-z0-9_-]\n'
            )
            sys.exit(2)
        if token in result:
            sys.stderr.write(f'Duplicate token in --tokens for viewers "{result[token]}" and "{viewer}"\n')
            sys.exit(2)
        result[token] = viewer
    return result


def read_tokens_file(path, key):
    """从 tokens 文件读取指定 KEY 的值。错误信息只含文件路径与 key 名，不含文件内容或 token 值。"""
    try:
        with open(path, 'r', encoding='utf-8-sig') as f:
            for line in f:
                stripped = line.strip()
                if not stripped or stripped.startswith('#'):
                    continue
                if '=' not in stripped:
                    continue
                k, v = stripped.split('=', 1)
                k = k.strip()
                v = v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in ('\'', '"'):
                    v = v[1:-1]
                if k == key:
                    return v
    except FileNotFoundError:
        sys.stderr.write(f'Error: tokens file not found: {path} (looking for key "{key}")\n')
        sys.exit(2)
    except IsADirectoryError:
        sys.stderr.write(f'Error: tokens file path is a directory: {path} (looking for key "{key}")\n')
        sys.exit(2)
    except UnicodeDecodeError:
        sys.stderr.write(f'Error: tokens file is not valid UTF-8: {path} (looking for key "{key}")\n')
        sys.exit(2)
    except OSError:
        sys.stderr.write(f'Error: cannot read tokens file: {path} (looking for key "{key}")\n')
        sys.exit(2)
    sys.stderr.write(f'Error: key "{key}" not found in tokens file: {path}\n')
    sys.exit(2)


class SessionLog:
    def __init__(self, sessions_dir):
        self.dir = sessions_dir
        self.lock = threading.Lock()

    @staticmethod
    def month_of(session_id):
        return session_id[0:4] + '-' + session_id[4:6]

    def _session_file(self, session_id):
        month = self.month_of(session_id)
        path = os.path.join(self.dir, month, 'session_' + session_id + '.jsonl')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return path

    def append(self, session_id, record):
        record['server_ts'] = datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')
        path = self._session_file(session_id)
        with self.lock:
            with open(path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(record, ensure_ascii=False) + '\n')
        return os.path.relpath(path, self.dir).replace(os.sep, '/')

    def save_audio(self, session_id, turn, wav_bytes):
        month = self.month_of(session_id)
        audio_dir = os.path.join(self.dir, month, 'audio')
        os.makedirs(audio_dir, exist_ok=True)
        base = f'session_{session_id}_t{turn:03d}'
        candidates = [base + '.wav'] + [f'{base}_{i}.wav' for i in range(2, 101)]
        for name in candidates:
            path = os.path.join(audio_dir, name)
            try:
                with open(path, 'xb') as f:
                    f.write(wav_bytes)
                return os.path.relpath(path, self.dir).replace(os.sep, '/')
            except FileExistsError:
                continue
        raise RuntimeError('too many audio files for ' + base)


class TTSService:
    def __init__(self, args):
        self.args = args
        self.lock = threading.Lock()
        self.session_log = None
        self.sessions_ingest = None
        self._load_model()
        self.prompt_text = self._read_prompt_text(args.prompt_text)

    def _read_prompt_text(self, path):
        with open(path, 'r', encoding='utf-8') as f:
            return f.read().strip()

    def _load_model(self):
        models_dir = self.args.models_dir
        sys.path.insert(0, r'C:\Users\justin\CosyVoice')
        sys.path.insert(0, r'C:\Users\justin\CosyVoice\third_party\Matcha-TTS')
        from cosyvoice.cli.cosyvoice import CosyVoice2
        self.cv = CosyVoice2(
            os.path.join(models_dir, 'CosyVoice2-Wu-SFT'),
            load_jit=False, load_trt=False, load_vllm=False, fp16=False
        )
        ckpt_path = os.path.join(
            self.args.exp_dir, f'epoch_{self.args.epoch}_whole.pt'
        )
        state = torch.load(ckpt_path, map_location='cpu')
        filtered = {k: v for k, v in state.items() if isinstance(v, torch.Tensor)}
        missing, unexpected = self.cv.model.llm.load_state_dict(filtered, strict=False)
        if missing or unexpected:
            sys.stderr.write(
                f'Model load failed: missing={len(missing)} unexpected={len(unexpected)}\n'
            )
            sys.exit(1)

    def synthesize(self, text, lang):
        """Synthesize text to MP3 bytes. Returns (mp3_bytes, duration_seconds, wav_bytes)."""
        with self.lock:
            full_text = (WU_PREFIX + text) if lang == 'wu' else text
            segments = []
            for out in self.cv.inference_zero_shot(
                full_text,
                self.prompt_text,
                self.args.ref,
                stream=False,
                speed=1.0
            ):
                segments.append(out['tts_speech'])
            if not segments:
                raise RuntimeError('No audio segments generated')
            wav = torch.cat(segments, dim=1)
            pad_len = int(self.cv.sample_rate * self.args.pad_ms / 1000.0)
            if pad_len > 0:
                pad = torch.zeros((1, pad_len), dtype=wav.dtype)
                wav = torch.cat([pad, wav, pad], dim=1)
            duration = wav.shape[1] / self.cv.sample_rate
            data = soften_onsets(wav.numpy().flatten(), self.cv.sample_rate, fade_ms=self.args.onset_fade_ms)
            pcm = (np.clip(data, -1.0, 1.0) * 32767).astype(np.int16)
            buf = io.BytesIO()
            sf.write(buf, pcm, self.cv.sample_rate, format='WAV', subtype='PCM_16')
            wav_bytes = buf.getvalue()
            enc = lameenc.Encoder()
            enc.set_bit_rate(64)
            enc.set_channels(1)
            enc.set_quality(2)
            enc.set_in_sample_rate(self.cv.sample_rate)
            mp3 = enc.encode(pcm.tobytes()) + enc.flush()
            self._verify_mp3(mp3)
            return mp3, duration, wav_bytes

    def _verify_mp3(self, mp3_bytes):
        """Decode and check RMS of middle 80% to confirm audio is valid."""
        data, sr = sf.read(io.BytesIO(mp3_bytes))
        if len(data) == 0:
            raise RuntimeError('Decoded audio is empty')
        start = int(len(data) * 0.1)
        end = int(len(data) * 0.9)
        middle = data[start:end]
        rms = float(np.sqrt(np.mean(np.square(middle))))
        if rms <= 0.005:
            raise RuntimeError(f'RMS check failed: rms={rms:.4f}')

    def health_data(self):
        return {
            'status': 'ok',
            'exp': os.path.basename(self.args.exp_dir),
            'epoch': self.args.epoch,
            'default_lang': self.args.default_lang,
            'sample_rate': self.cv.sample_rate,
            'session_log': self.session_log is not None,
            'person': self.args.person,
            'sessions_ingest': self.sessions_ingest is not None,
            'sessions_ingest_last': (self.sessions_ingest.last_success_iso if self.sessions_ingest else None),
        }


def build_handler(service):
    class TTSHandler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, format, *args):
            pass  # disable default access logging

        def _send_cors_headers(self):
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'content-type, x-tts-token')
            self.send_header('Access-Control-Expose-Headers', 'X-Duration-Seconds, X-Lang, X-Session-Audio')

        def _send_json(self, status, obj, extra_headers=None, close=False):
            body = json.dumps(obj).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self._send_cors_headers()
            if extra_headers:
                for k, v in extra_headers.items():
                    self.send_header(k, v)
            if close:
                self.send_header('Connection', 'close')
                self.close_connection = True
            self.end_headers()
            self.wfile.write(body)

        def _send_audio(self, mp3_bytes, duration, lang, session_audio=None):
            self.send_response(200)
            self.send_header('Content-Type', 'audio/mpeg')
            self.send_header('Content-Length', str(len(mp3_bytes)))
            self.send_header('X-Duration-Seconds', f'{duration:.2f}')
            self.send_header('X-Lang', lang)
            if session_audio:
                self.send_header('X-Session-Audio', session_audio)
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(mp3_bytes)

        def _send_204(self):
            self.send_response(204)
            self._send_cors_headers()
            self.send_header('Content-Length', '0')
            self.end_headers()

        def _read_json_body(self):
            """读取并校验 JSON 请求体；返回 dict。返回 None 表示失败且响应已发送（或已尽力发送）。"""
            try:
                try:
                    content_length = int(self.headers.get('Content-Length', '0'))
                except (ValueError, TypeError):
                    self._send_json(400, {'error': 'missing or invalid Content-Length'}, close=True)
                    return None
                if content_length <= 0:
                    self._send_json(400, {'error': 'missing or invalid Content-Length'}, close=True)
                    return None
                if content_length > MAX_BODY:
                    self._send_json(413, {'error': 'body too large'}, close=True)
                    return None
                try:
                    raw_body = self.rfile.read(content_length)
                except Exception:
                    try:
                        self._send_json(400, {'error': 'failed to read body'}, close=True)
                    except Exception:
                        pass
                    return None
                try:
                    body = json.loads(raw_body.decode('utf-8')) if raw_body else None
                except (json.JSONDecodeError, UnicodeDecodeError):
                    self._send_json(400, {'error': 'invalid JSON body'}, close=True)
                    return None

                if not isinstance(body, dict):
                    self._send_json(400, {'error': 'request body must be a JSON object'}, close=True)
                    return None
                return body
            except Exception:
                try:
                    self._send_json(500, {'error': 'bad request'}, close=True)
                except Exception:
                    pass
                return None

        def _check_token(self):
            if service.viewer_tokens:
                token = self.headers.get('X-TTS-Token', '')
                if TOKEN_RE.fullmatch(token):
                    for candidate_token, candidate_viewer in service.viewer_tokens.items():
                        if hmac.compare_digest(token, candidate_token):
                            return True, candidate_viewer
                self._send_json(401, {'error': 'unauthorized'}, close=True)
                return False, None
            if service.args.token:
                token = self.headers.get('X-TTS-Token', '')
                if token != service.args.token:
                    self._send_json(401, {'error': 'unauthorized'}, close=True)
                    return False, None
            return True, None

        def do_OPTIONS(self):
            self._send_204()

        def do_GET(self):
            if self.path == '/health':
                self._send_json(200, service.health_data())
            else:
                self._send_json(404, {'error': 'not found'}, close=True)

        def do_POST(self):
            if self.path == '/tts':
                self._handle_tts()
            elif self.path == '/session':
                self._handle_session()
            else:
                self._send_json(404, {'error': 'not found'}, close=True)

        def _handle_tts(self):
            ok, auth_viewer = self._check_token()
            if not ok:
                return

            start_time = time.time()
            try:
                body = self._read_json_body()
                if body is None:
                    return
                text = body.get('text')
                if not isinstance(text, str):
                    self._send_json(400, {'error': 'text must be a string'}, close=True)
                    return
                text = text.strip()
                if not text:
                    self._send_json(400, {'error': 'text is empty'}, close=True)
                    return
                if len(text) > service.args.max_chars:
                    self._send_json(400, {
                        'error': 'text too long',
                        'max_chars': service.args.max_chars
                    }, close=True)
                    return
                lang = body.get('lang', service.args.default_lang)
                if lang not in ('wu', 'mandarin'):
                    self._send_json(400, {'error': f'invalid lang: {lang}'}, close=True)
                    return
                session_id = body.get('session_id')
                if not isinstance(session_id, str) or not SESSION_ID_RE.match(session_id):
                    session_id = None
                turn = body.get('turn')
                if isinstance(turn, bool) or not isinstance(turn, int) or turn < 0 or turn > 99999:
                    turn = None

                spoken_text = strip_brackets(text)
                if not spoken_text:
                    self._send_json(400, {'error': 'text empty after stripping brackets'}, close=True)
                    return
                # Duration QC: retry once if estimated duration exceeded
                dur_limit = len(spoken_text) * service.args.sec_per_char + service.args.dur_slack
                synth_start = time.time()
                best_mp3, best_duration, best_wav = service.synthesize(spoken_text, lang)
                best_dur_check = best_duration
                if best_duration > dur_limit and service.args.max_retries > 0:
                    try:
                        mp3_retry, dur_retry, wav_retry = service.synthesize(spoken_text, lang)
                        if dur_retry < best_duration:
                            best_mp3, best_duration, best_wav = mp3_retry, dur_retry, wav_retry
                    except Exception:
                        pass  # keep best version on retry failure

                synth_time = time.time() - synth_start
                total_time = time.time() - start_time
                print(
                    f'POST /tts chars={len(text)} lang={lang} '
                    f'dur={best_duration:.2f}s synth={synth_time:.2f}s '
                    f'dur_check={best_dur_check:.2f}s limit={dur_limit:.2f}s '
                    f'status=200 (total={total_time:.2f}s) session={session_id or "-"}',
                    flush=True
                )
                audio_rel = None
                if service.session_log is not None and session_id is not None:
                    try:
                        audio_rel = service.session_log.save_audio(session_id, turn or 0, best_wav)
                        audio_record = {
                            'role': 'simulacrum_audio', 'turn': turn, 'text': text, 'lang': lang,
                            'duration_s': round(best_duration, 2), 'synth_s': round(synth_time, 2),
                            'file': audio_rel
                        }
                        if auth_viewer is not None:
                            audio_record['viewer'] = auth_viewer
                        if spoken_text != text:
                            audio_record['spoken_text'] = spoken_text
                        service.session_log.append(session_id, audio_record)
                    except Exception as e:
                        print(f'[session] audio log failed: {e}', flush=True)
                        audio_rel = None
                self._send_audio(best_mp3, best_duration, lang, audio_rel)
            except Exception as e:
                tb = traceback.format_exc()
                print(tb, flush=True)
                try:
                    self._send_json(500, {'error': str(e)}, close=True)
                except Exception:
                    pass

        def _handle_session(self):
            ok, auth_viewer = self._check_token()
            if not ok:
                return
            if service.session_log is None:
                self._send_json(503, {'error': 'session log disabled'}, close=True)
                return
            body = self._read_json_body()
            if body is None:
                return
            session_id = body.get('session_id')
            if not isinstance(session_id, str) or not SESSION_ID_RE.match(session_id):
                self._send_json(400, {'error': 'invalid session_id'}, close=True)
                return
            role = body.get('role')
            if role not in SESSION_ROLES:
                self._send_json(400, {'error': 'invalid role'}, close=True)
                return
            text = body.get('text')
            if not isinstance(text, str) or len(text) > SESSION_MAX_TEXT:
                self._send_json(400, {'error': 'invalid text'}, close=True)
                return
            turn = body.get('turn')
            if turn is not None:
                if isinstance(turn, bool) or not isinstance(turn, int) or turn < 0 or turn > 99999:
                    self._send_json(400, {'error': 'invalid turn'}, close=True)
                    return
            record = {'role': role, 'turn': turn, 'text': text}
            for field, (ftype, maxlen) in SESSION_OPTIONAL_FIELDS.items():
                if field == 'viewer' and auth_viewer is not None:
                    continue
                if field not in body:
                    continue
                val = body[field]
                if ftype is bool:
                    if not isinstance(val, bool):
                        continue
                elif ftype is list:
                    if not isinstance(val, list) or len(val) > maxlen:
                        continue
                    if not all(isinstance(x, str) and len(x) <= 200 for x in val):
                        continue
                elif ftype is str:
                    if not isinstance(val, str) or (maxlen is not None and len(val) > maxlen):
                        continue
                elif ftype is int:
                    if isinstance(val, bool) or not isinstance(val, int) or val < 0 or val > 99999:
                        continue
                else:
                    if not isinstance(val, ftype):
                        continue
                record[field] = val
            if auth_viewer is not None:
                record['viewer'] = auth_viewer
            try:
                rel = service.session_log.append(session_id, record)
                try:
                    if service.sessions_ingest is not None:
                        service.sessions_ingest.schedule()
                except Exception:
                    tb = traceback.format_exc()
                    print(tb, flush=True)
                self._send_json(200, {'ok': True, 'file': rel})
            except Exception as e:
                tb = traceback.format_exc()
                print(tb, flush=True)
                self._send_json(500, {'error': str(e)}, close=True)

    return TTSHandler


def main():
    parser = argparse.ArgumentParser(description='Local TTS HTTP server')
    parser.add_argument('--exp-dir', default=EXP_DIR_DEFAULT)
    parser.add_argument('--epoch', type=int, default=EPOCH_DEFAULT)
    parser.add_argument('--port', type=int, default=PORT_DEFAULT)
    parser.add_argument('--host', default=HOST_DEFAULT)
    parser.add_argument('--models-dir', default=MODELS_DIR_DEFAULT)
    parser.add_argument('--ref', default=REF_DEFAULT)
    parser.add_argument('--prompt-text', default=PROMPT_TEXT_DEFAULT)
    parser.add_argument('--default-lang', choices=['mandarin', 'wu'], default=DEFAULT_LANG_DEFAULT)
    parser.add_argument('--onset-fade-ms', type=int, default=30, help='每个起音处的淡入毫秒数（压掉模型开口爆音；0=关闭）')
    parser.add_argument('--pad-ms', type=int, default=200)
    parser.add_argument('--max-chars', type=int, default=120)
    parser.add_argument('--max-retries', type=int, default=1)
    parser.add_argument('--sec-per-char', type=float, default=0.32)
    parser.add_argument('--dur-slack', type=float, default=2.0)
    parser.add_argument('--token', default='')
    parser.add_argument('--tokens', default='', help='多观看者 token，格式 viewer:token[,viewer2:token2]；与 --token 互斥')
    parser.add_argument('--tokens-file', default='', help='从文件读取多观看者 token；文件内一行 TTS_TOKENS=viewer:token[,viewer2:token2]')
    parser.add_argument('--person', default='mama')
    parser.add_argument('--repo-root', default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    parser.add_argument('--no-session-log', action='store_true')
    parser.add_argument('--sessions-out-dir', default='')
    parser.add_argument('--no-sessions-ingest', action='store_true')
    parser.add_argument('--sessions-per-viewer-subdir', action='store_true')
    args = parser.parse_args()

    provided_token_args = [
        name for name, value in (
            ('--token', args.token),
            ('--tokens', args.tokens),
            ('--tokens-file', args.tokens_file),
        ) if value != ''
    ]
    if len(provided_token_args) > 1:
        sys.stderr.write('Error: --token, --tokens, and --tokens-file are mutually exclusive\n')
        sys.exit(2)

    if args.tokens_file:
        token_file_value = read_tokens_file(args.tokens_file, 'TTS_TOKENS')
        if not token_file_value.strip():
            sys.stderr.write(f'Error: key "TTS_TOKENS" is empty in tokens file: {args.tokens_file}\n')
            sys.exit(2)
        original_stderr = sys.stderr
        try:
            sys.stderr = io.StringIO()
            try:
                viewer_tokens = parse_viewer_tokens(token_file_value)
            except SystemExit:
                sys.stderr = original_stderr
                sys.stderr.write(f'Error: invalid TTS_TOKENS value in tokens file: {args.tokens_file}\n')
                sys.exit(2)
        finally:
            sys.stderr = original_stderr
    else:
        viewer_tokens = parse_viewer_tokens(args.tokens)

    if not PERSON_RE.match(args.person):
        sys.exit('invalid --person')

    start_load = time.time()
    print('Loading model...', flush=True)
    service = TTSService(args)
    service.viewer_tokens = viewer_tokens
    print(f'Model loaded in {time.time() - start_load:.1f}s', flush=True)

    sessions_dir = None
    if not args.no_session_log:
        sessions_dir = os.path.realpath(os.path.join(args.repo_root, 'people', args.person, 'sessions'))
        people_root = os.path.realpath(os.path.join(args.repo_root, 'people', args.person))
        if sessions_dir != people_root and not sessions_dir.startswith(people_root + os.sep):
            sys.exit('sessions dir escapes person dir')
        os.makedirs(sessions_dir, exist_ok=True)
        service.session_log = SessionLog(sessions_dir)

    if service.session_log is not None and not args.no_sessions_ingest:
        person_dir = os.path.realpath(os.path.join(args.repo_root, 'people', args.person))
        if args.sessions_out_dir:
            out_dir = args.sessions_out_dir
        else:
            out_dir = os.path.join(person_dir, 'archive_out', 'data')
        err = ingest_sessions.validate_paths(person_dir, out_dir)
        if err is not None:
            sys.exit(err)
        service.sessions_ingest = SessionsIngestScheduler(
            person_dir, out_dir, delay_s=5.0,
            per_viewer_subdir=args.sessions_per_viewer_subdir)
        if not service.sessions_ingest.run_now():
            print('Warning: initial sessions ingest failed', flush=True)

    handler = build_handler(service)
    httpd = ThreadingHTTPServer((args.host, args.port), handler)
    if viewer_tokens:
        token_status = f'token=multi({len(viewer_tokens)} viewers)'
    else:
        token_status = 'token=on' if args.token else 'token=off'
    ingest_status = 'on' if service.sessions_ingest is not None else 'off'
    print(
        f'TTS server ready: http://{args.host}:{args.port}  '
        f'model={os.path.basename(args.exp_dir)} e{args.epoch} '
        f'default_lang={args.default_lang} {token_status} '
        f'sessions={sessions_dir or "off"} ingest={ingest_status}',
        flush=True
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\nShutting down...', flush=True)
        httpd.shutdown()
        httpd.server_close()


if __name__ == '__main__':
    main()
