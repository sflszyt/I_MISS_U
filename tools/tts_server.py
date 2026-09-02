import argparse
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
}

BRACKET_RE = re.compile(r'[\[【（(][^\[\]【】（）()]*[\]】）)]')


def strip_brackets(text):
    """删除成对括号及其内容（微信表情标签/动作描写），供 TTS 念白用；压缩空白后返回。"""
    prev = None
    while prev != text:
        prev = text
        text = BRACKET_RE.sub(' ', text)
    return re.sub(r'\s+', ' ', text).strip()


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
            data = wav.numpy().flatten()
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
            if service.args.token:
                token = self.headers.get('X-TTS-Token', '')
                if token != service.args.token:
                    self._send_json(401, {'error': 'unauthorized'}, close=True)
                    return False
            return True

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
            if not self._check_token():
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
            if not self._check_token():
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
                else:
                    if not isinstance(val, ftype):
                        continue
                record[field] = val
            try:
                rel = service.session_log.append(session_id, record)
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
    parser.add_argument('--pad-ms', type=int, default=200)
    parser.add_argument('--max-chars', type=int, default=120)
    parser.add_argument('--max-retries', type=int, default=1)
    parser.add_argument('--sec-per-char', type=float, default=0.32)
    parser.add_argument('--dur-slack', type=float, default=2.0)
    parser.add_argument('--token', default='')
    parser.add_argument('--person', default='mama')
    parser.add_argument('--repo-root', default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    parser.add_argument('--no-session-log', action='store_true')
    args = parser.parse_args()

    if not PERSON_RE.match(args.person):
        sys.exit('invalid --person')

    start_load = time.time()
    print('Loading model...', flush=True)
    service = TTSService(args)
    print(f'Model loaded in {time.time() - start_load:.1f}s', flush=True)

    sessions_dir = None
    if not args.no_session_log:
        sessions_dir = os.path.realpath(os.path.join(args.repo_root, 'people', args.person, 'sessions'))
        people_root = os.path.realpath(os.path.join(args.repo_root, 'people', args.person))
        if sessions_dir != people_root and not sessions_dir.startswith(people_root + os.sep):
            sys.exit('sessions dir escapes person dir')
        os.makedirs(sessions_dir, exist_ok=True)
        service.session_log = SessionLog(sessions_dir)

    handler = build_handler(service)
    httpd = ThreadingHTTPServer((args.host, args.port), handler)
    token_status = 'token=on' if args.token else 'token=off'
    print(
        f'TTS server ready: http://{args.host}:{args.port}  '
        f'model={os.path.basename(args.exp_dir)} e{args.epoch} '
        f'default_lang={args.default_lang} {token_status} '
        f'sessions={sessions_dir or "off"}',
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