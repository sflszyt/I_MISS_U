import json
import math
import struct
import subprocess
import re
import tempfile
import unittest
import wave
from pathlib import Path

from tools import prepare_voice_upgrade as m
from tools.viewpoint_manifest import digest, sha256


def wav(path, seconds=3, offset=0):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as w:
        w.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        w.writeframes(b''.join(struct.pack('<h', int(8000*math.sin(i/13))+offset)
                               for i in range(int(16000*seconds))))


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.training = self.root / 'training'
        wav(self.training / 'audio/a.wav')
        self.c = dict(record_id='r1', person='subject', audio_file='audio/a.wav',
                      audio_sha256=sha256(self.training / 'audio/a.wav'),
                      audio_valid=True, draft_text='合成测试文本', speaker_status='pending',
                      duration_check='within_tolerance',
                      transcript_status='draft', source_kind='recording_unverified',
                      split='validation', segmentation_status='whole_recording_not_segmented',
                      exclusion_reasons=['speaker_pending'], revision='original-revision')
        self.save()

    def save(self):
        (self.training / 'candidates.jsonl').write_text(json.dumps(self.c)+'\n', encoding='utf-8')

    def test_preserves_contract_and_whole_audio(self):
        out = m.prepare(self.training, self.root / 'out')
        selected = json.loads((out / 'candidates.jsonl').read_text())
        self.assertEqual(selected, self.c)
        self.assertEqual(sha256(out / self.c['audio_file']), self.c['audio_sha256'])
        report = json.loads((out / 'technical-report.json').read_text())
        self.assertEqual(report['selected'], 1)
        self.assertFalse(report['training_started'])
        self.assertIn('revision:c.revision', (out / 'review.html').read_text(encoding='utf-8'))
        script = re.search(r'<script>(.*?)</script>', (out / 'review.html').read_text(encoding='utf-8'), re.S).group(1)
        result = subprocess.run(['node', '--check'], input=script, text=True, encoding='utf-8', capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_escape_hash_overwrite_and_corruption(self):
        for path in ['../escape.wav', 'C:/escape.wav']:
            self.c['audio_file'] = path
            self.save()
            with self.assertRaises(ValueError):
                m.prepare(self.training, self.root / 'bad')
        self.c['audio_file'] = 'audio/a.wav'
        self.c['audio_sha256'] = '0'*64
        self.save()
        with self.assertRaises(ValueError):
            m.prepare(self.training, self.root / 'bad')
        (self.training / 'audio/a.wav').write_bytes(b'broken')
        self.c['audio_sha256'] = sha256(self.training / 'audio/a.wav')
        self.save()
        out = m.prepare(self.training, self.root / 'out')
        report = json.loads((out / 'technical-report.json').read_text())
        self.assertEqual(report['selected'], 0)
        self.assertEqual(report['status'], 'no_suitable_candidates')
        with self.assertRaises(ValueError):
            m.prepare(self.training, out)

    def test_legacy_exact_mapping(self):
        legacy = self.root / 'legacy'
        wav(legacy / 'a.wav')
        (legacy / 'text').write_text('a 十二个字合成参考文本测试好\n', encoding='utf-8')
        (legacy / 'wav.scp').write_text('a '+str(legacy / 'a.wav')+'\n', encoding='utf-8')
        refs = m.legacy_references(legacy, ['a'])
        self.assertEqual(refs[0]['basis']['kind'], 'legacy_corrected')
        (legacy / 'text').write_text('b 不匹配\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            m.legacy_references(legacy, ['a'])

    def test_mismatch_not_recommended(self):
        self.c['duration_check'] = 'mismatch'
        self.save()
        out = m.prepare(self.training, self.root / 'out')
        self.assertEqual(json.loads((out / 'technical-report.json').read_text())['selected'], 0)

    def test_output_boundaries(self):
        for out in [self.training / 'nested', self.root / 'people/subject/RAW/new',
                    self.root / 'people/subject/x/../RAW/new']:
            with self.subTest(out=out), self.assertRaises(ValueError):
                m.prepare(self.training, out)
        self.assertFalse((self.training / 'nested').exists())

    def test_limit_and_duplicates(self):
        rows = []
        for i in range(14):
            audio = self.training / f'audio/{i}.wav'
            wav(audio, offset=i)
            rows.append(dict(self.c, record_id=str(i), audio_file=f'audio/{i}.wav',
                             audio_sha256=sha256(audio)))
        rows.append(dict(rows[0], record_id='duplicate'))
        (self.training / 'candidates.jsonl').write_text('\n'.join(json.dumps(c) for c in rows))
        out = m.prepare(self.training, self.root / 'out')
        chosen = [json.loads(s) for s in (out / 'candidates.jsonl').read_text().splitlines()]
        self.assertEqual(len(chosen), 12)
        self.assertEqual(len({c['audio_sha256'] for c in chosen}), 12)


class ReviewCompatibilityTests(unittest.TestCase):
    from tests.test_import_wechat_viewpoint import ImportViewpointTests as Fixture
    setUp = Fixture.setUp
    row = Fixture.row
    refresh = Fixture.refresh
    run_import = Fixture.run_import

    def test_subset_decision_applies_to_original_full_training(self):
        from tools import build_training_manifest as training
        from tests.test_import_wechat_viewpoint import dump
        wav(self.source / 'records/conversation-1/a.wav')
        self.refresh()
        dataset = self.run_import()
        drafts, mapping = self.root / 'drafts.json', self.root / 'mapping.json'
        dump(drafts, [dict(id='one', asr_text='合成原声草稿')])
        dump(mapping, [dict(id='one', source_file='records/conversation-1/messages.json',
                            source_row_number=4, native_id='4',
                            wav_sha256=sha256(self.source / 'records/conversation-1/a.wav'))])
        full = self.root / 'full'
        training.build(person='mama', datasets=[dataset], out=full, asr_drafts=drafts, asr_mapping=mapping)
        subset = m.prepare(full, self.root / 'subset')
        c = json.loads((subset / 'candidates.jsonl').read_text())
        review = dict(record_id=c['record_id'], audio_sha256=c['audio_sha256'], revision=c['revision'],
                      speaker_id=c['person'], speaker_status='confirmed', single_speaker=True,
                      source_kind='real_recording', text='合成核验文本', transcript_status='corrected',
                      quality_status='approved', duration_approved=True, decided_by='synthetic-tester',
                      decided_at='2026-10-20')
        overlay = self.root / 'reviews.json'
        dump(overlay, dict(schema_version=1, reviews=[review]))
        checked = self.root / 'checked'
        training.build(person='mama', datasets=[dataset], out=checked, asr_drafts=drafts,
                       asr_mapping=mapping, reviews=overlay)
        eligible = json.loads((checked / 'eligible.jsonl').read_text())
        self.assertEqual(eligible['revision'], c['revision'])
        self.assertEqual(eligible['split'], c['split'])
        self.assertEqual(len((full / 'candidates.jsonl').read_text().splitlines()), 2)
