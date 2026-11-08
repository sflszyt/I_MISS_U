import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import subprocess
import unittest

from tools import parse_wechat


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


class ImportViewpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'accepted'
        self.legacy = self.root / 'legacy.jsonl'
        self.legacy.write_text('\n'.join(json.dumps(r) for r in [
            {'record_id': 'legacy01', 'person': 'mama', 'viewpoint': 'owner',
             'sender': 'subject', 'sender_wxid': 'wx_m'},
            {'record_id': 'legacy02', 'person': 'mama', 'viewpoint': 'owner',
             'sender': 'viewpoint_owner', 'sender_wxid': 'wx_j'}]), encoding='utf-8')
        self.rows = [self.row(1, 'wx_f', True), self.row(2, 'wx_m'),
                     self.row(3, 'wx_m', group=True), self.row(4, 'wx_m', voice=True),
                     self.row(5, 'wx_m', voice=True), self.row(6, 'wx_x', group=True)]
        self.rows[3]['media'] = [dict(kind='voice', path='a.wav', format='WAV',
                                     duration_check='within_tolerance'),
                                 dict(kind='voice_raw', path='a.silk', format='SILK')]
        self.rows[4]['media_status'] = ['voice_source_missing']
        self.rows[5]['record_status'] = 'transport_content_withheld'
        dump(self.source / 'acceptance-summary.json', {'coverage_status': 'partial'})
        for name in ['a.wav', 'a.silk']:
            f = self.source / 'records/conversation-1' / name
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(name.encode())
        self.refresh()

    def row(self, n, sender, own=False, group=False, voice=False):
        return dict(sender_wxid=sender, is_self=own, server_id=str(n), source_row=n,
                    conversation_id='group' if group else 'direct', chat_room='group' if group else 'wx_m',
                    conversation_type='group' if group else 'direct', is_group_chat=group,
                    content='synthetic text', msg_type=34 if voice else 1, ts=1700000000,
                    voice_requested=voice, record_status='existing_normalized', media=[], media_status=[])

    def refresh(self):
        dump(self.source / 'records/conversation-1/messages.json', self.rows)
        files = [dict(path=f.relative_to(self.source).as_posix(), bytes=f.stat().st_size,
                      sha256=hashlib.sha256(f.read_bytes()).hexdigest())
                 for f in self.source.rglob('*') if f.is_file() and f.name != 'package-manifest.json']
        dump(self.source / 'package-manifest.json', files)

    def run_import(self, **kwargs):
        self.assertIsNotNone(importlib.util.find_spec('tools.import_wechat_viewpoint'),
                             'safe importer is not implemented')
        from tools.import_wechat_viewpoint import import_package
        return import_package(person='mama', viewpoint='father', source=self.source,
                              legacy_uif=self.legacy, batch='batch1', repo_root=self.root, **kwargs)

    def test_identity_group_quarantine_and_logical_media(self):
        path = self.run_import()
        from tools.viewpoint_manifest import load_dataset
        manifest, records = load_dataset(path)
        self.assertEqual(len(records), 6)
        self.assertEqual(records[0]['sender_person_id'], 'father')
        self.assertEqual(records[1]['sender_person_id'], 'mama')
        self.assertEqual(records[2]['conversation_kind'], 'group')
        self.assertNotIn('addressee_ids', records[2])
        self.assertNotIn('relationship_id', records[2])
        self.assertNotIn('text', records[5])
        media = [json.loads(x) for x in (path.parent / 'media_manifest.jsonl').read_text().splitlines()]
        self.assertEqual(len(media), 2)
        self.assertEqual(len(media[0]['representations']), 2)
        self.assertTrue(media[1]['missing'])
        self.assertEqual(media[0]['speaker_status'], 'pending')
        self.assertEqual(manifest['counts']['records'], 6)
        before = {f: f.read_bytes() for f in path.parent.rglob('*') if f.is_file()}
        self.assertEqual(path, self.run_import())
        self.assertTrue(all(f.read_bytes() == data for f, data in before.items()))

    def test_changed_existing_batch_refuses(self):
        path = self.run_import()
        before = path.read_bytes()
        self.rows[1]['content'] = 'changed'
        self.refresh()
        with self.assertRaises(ValueError):
            self.run_import()
        self.assertEqual(path.read_bytes(), before)

    def test_bad_package_refuses_before_writes(self):
        for mode in ['hash', 'unlisted', 'traversal', 'absolute']:
            with self.subTest(mode=mode):
                self.refresh()
                p = self.source / 'package-manifest.json'
                data = json.loads(p.read_text())
                if mode == 'hash': data[0]['sha256'] = '0' * 64
                if mode == 'unlisted': data.pop()
                if mode == 'traversal': data[0]['path'] = '../legacy.jsonl'
                if mode == 'absolute': data[0]['path'] = 'C:/outside/file'
                dump(p, data)
                with self.assertRaises(ValueError): self.run_import()
                self.assertFalse((self.root / 'people').exists())

    def test_ambiguous_identity_and_duplicate_native_refuse(self):
        self.rows.append(self.row(7, 'wx_x', True))
        self.refresh()
        with self.assertRaises(ValueError): self.run_import()
        self.rows.pop()
        self.rows.append(dict(self.rows[1], content='conflict'))
        self.refresh()
        with self.assertRaises(ValueError): self.run_import()
        self.assertFalse((self.root / 'people').exists())

    def test_preexisting_raw_refuses_without_changes(self):
        raw = self.root / 'people/mama/raw/wechat/father/batch1'
        raw.mkdir(parents=True)
        (raw / 'keep').write_bytes(b'keep')
        with self.assertRaises(ValueError): self.run_import()
        self.assertEqual((raw / 'keep').read_bytes(), b'keep')

    def test_source_equal_output_refuses(self):
        import shutil
        raw = self.root / 'people/mama/raw/wechat/father/batch1'
        shutil.copytree(self.source, raw)
        self.source = raw
        before = {p: p.read_bytes() for p in raw.rglob('*') if p.is_file()}
        with self.assertRaises(ValueError): self.run_import()
        self.assertTrue(all(p.read_bytes() == b for p, b in before.items()))

    def test_package_media_path_escape_refuses(self):
        self.rows[3]['media'][0]['path'] = '../../legacy.jsonl'
        self.refresh()
        with self.assertRaises(ValueError): self.run_import()
        self.assertFalse((self.root / 'people').exists())

    def test_manifest_tampering_refuses(self):
        path = self.run_import()
        from tools.viewpoint_manifest import load_dataset
        (path.parent / 'messages.uif.jsonl').write_text('{}\n')
        with self.assertRaises(ValueError): load_dataset(path)

    def test_junction_escape_refuses(self):
        destination = self.root / 'people/mama'
        destination.mkdir(parents=True)
        outside = self.root / 'outside'
        outside.mkdir()
        link = destination / 'raw'
        if os.name == 'nt':
            result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(outside)], capture_output=True)
            self.assertEqual(result.returncode, 0)
        else:
            link.symlink_to(outside, target_is_directory=True)
        try:
            with self.assertRaises(ValueError): self.run_import()
            self.assertEqual(list(outside.iterdir()), [])
        finally:
            link.rmdir() if os.name == 'nt' else link.unlink()

    def test_all_quarantine_statuses_never_emit_text(self):
        for status in ['transport_content_withheld', 'empty_or_unparsed', 'unsupported_type']:
            self.rows.append(dict(self.row(len(self.rows) + 1, 'wx_m'), record_status=status))
        self.refresh()
        path = self.run_import()
        from tools.viewpoint_manifest import load_dataset
        _, rows = load_dataset(path)
        self.assertEqual(len(rows), len(self.rows))
        self.assertTrue(all('text' not in r and not r['quality']['usable_text'] for r in rows[-3:]))

    def test_cross_view_links_require_native_conversation_and_content(self):
        old = json.loads(self.legacy.read_text().splitlines()[0])
        old.update(provenance={'native_id': '3'}, conversation_id='group', content_type='text', text='synthetic text')
        with self.legacy.open('a', encoding='utf-8') as f:
            f.write('\n' + json.dumps(dict(old, record_id='legacy03')))
            f.write('\n' + json.dumps(dict(old, record_id='legacy04', text='different')))
        path = self.run_import()
        events = [json.loads(x) for x in (path.parent / 'canonical_events.jsonl').read_text().splitlines()]
        self.assertEqual(len(events), 1)
        self.assertIn('legacy03', events[0]['record_ids'])
        self.assertNotIn('legacy04', events[0]['record_ids'])
        self.assertEqual(len(events[0]['record_ids']), 2)

    def test_fallback_id_stable_and_existing_output_tamper_refuses(self):
        self.rows[1]['server_id'] = None
        self.refresh()
        path = self.run_import()
        self.assertEqual(path, self.run_import())
        (path.parent / 'quarantine.jsonl').write_text('changed')
        with self.assertRaises(ValueError): self.run_import()

    def test_loader_rejects_semantically_invalid_rehashed_records(self):
        path = self.run_import()
        from tools.viewpoint_manifest import load_dataset
        f = path.parent / 'messages.uif.jsonl'
        rows = [json.loads(x) for x in f.read_text().splitlines()]
        rows[0]['sender_person_id'] = 'mama'
        f.write_text('\n'.join(json.dumps(x) for x in rows), encoding='utf-8')
        manifest = json.loads(path.read_text())
        manifest['records_sha256'] = hashlib.sha256(f.read_bytes()).hexdigest()
        dump(path, manifest)
        with self.assertRaises(ValueError): load_dataset(path)

    def test_legacy_default_id_preserved_nondefault_namespaced(self):
        cfg = dict(subject_wxid='wx_m', viewpoint_owner_wxid='wx_f', rooms={'direct': {}})
        msg = dict(chat_room='direct', sender_wxid='wx_m', content='hi', msg_type=1,
                   is_self=False, ts=1700000000)
        def build(config):
            return parse_wechat._build_record(msg, person='mama', cfg=config,
                source_file='a.json', extracted_at='2026-01-01T00:00:00+00:00', seen=set(),
                known_participants={})[0]
        old = build(cfg)
        self.assertEqual(old, build(dict(cfg, viewpoint='owner')))
        new = build(dict(cfg, viewpoint='father', source_account_id='wechat_father'))
        self.assertEqual(new['viewpoint'], 'father')
        self.assertNotEqual(old['record_id'], new['record_id'])

    def test_review_rehashed_invalid_datasets_rejected(self):
        from tools.viewpoint_manifest import load_dataset
        path = self.run_import()
        manifest = json.loads(path.read_text())
        record_path = path.parent / 'messages.uif.jsonl'
        media_path = path.parent / 'media_manifest.jsonl'
        original_records = record_path.read_text()
        original_media = media_path.read_text()
        cases = ['missing_source_hash', 'invalid_source_hash', 'missing_source',
                 'cross_relationship', 'sender_outside_scene', 'outside_addressee',
                 'self_addressee', 'missing_addressee', 'withheld_usable_text',
                 'voice_usable_text', 'voice_text', 'unknown_export_status',
                 'omitted_media', 'duplicate_media', 'nonvoice_media',
                 'media_person', 'media_viewpoint', 'media_provenance',
                 'confirmed_speaker', 'confirmed_transcript', 'eligible_media',
                 'known_speaker', 'incorrect_missing']
        for case in cases:
            with self.subTest(case=case):
                rows = [json.loads(x) for x in original_records.splitlines()]
                media = [json.loads(x) for x in original_media.splitlines()]
                if case == 'missing_source_hash':
                    rows[0]['provenance']['source_file'] = 'raw/nonexistent.json'
                    rows[0]['provenance'].pop('source_file_sha256')
                if case == 'invalid_source_hash': rows[0]['provenance']['source_file_sha256'] = 'bad'
                if case == 'missing_source': rows[0]['provenance']['source_file'] = 'raw/nonexistent.json'
                if case == 'cross_relationship': rows[0]['relationship_id'] = 'mama_owner'
                if case == 'sender_outside_scene':
                    rows[0].update(sender_person_id='owner', sender='owner', sender_wxid='wx_j')
                if case == 'outside_addressee': rows[0]['addressee_ids'] = ['owner']
                if case == 'self_addressee': rows[0]['addressee_ids'] = ['father']
                if case == 'missing_addressee': rows[0].pop('addressee_ids')
                if case == 'withheld_usable_text': rows[0]['quality']['export_status'] = 'transport_content_withheld'
                if case == 'voice_usable_text':
                    rows[3]['quality']['usable_text'] = True
                    rows[3]['text'] = 'unverified transcript'
                if case == 'voice_text': rows[3]['text'] = 'unverified transcript'
                if case == 'unknown_export_status': rows[0]['quality']['export_status'] = 'unknown'
                if case == 'omitted_media': media.pop()
                if case == 'duplicate_media': media.append(dict(media[0]))
                if case == 'nonvoice_media': media[0]['record_id'] = rows[0]['record_id']
                if case == 'media_person': media[0]['person'] = 'other'
                if case == 'media_viewpoint': media[0]['viewpoint'] = 'owner'
                if case == 'media_provenance': media[0]['provenance']['source_row'] = 'other'
                if case == 'confirmed_speaker': media[0]['speaker_status'] = 'confirmed'
                if case == 'confirmed_transcript': media[0]['transcript_status'] = 'confirmed'
                if case == 'eligible_media': media[0]['training_eligible'] = True
                if case == 'known_speaker': media[0]['speaker_id'] = 'mama'
                if case == 'incorrect_missing': media[0]['missing'] = True
                record_path.write_text('\n'.join(json.dumps(r) for r in rows), encoding='utf-8')
                media_path.write_text('\n'.join(json.dumps(r) for r in media), encoding='utf-8')
                manifest['records_sha256'] = hashlib.sha256(record_path.read_bytes()).hexdigest()
                manifest['media_manifest_sha256'] = hashlib.sha256(media_path.read_bytes()).hexdigest()
                manifest['counts']['media'] = len(media)
                dump(path, manifest)
                with self.assertRaises(ValueError): load_dataset(path)

    def test_father_only_unrelated_direct_is_not_spouse_evidence(self):
        self.rows.append(dict(self.row(7, 'wx_f', own=True),
                              conversation_id='unrelated', chat_room='unverified_peer'))
        self.refresh()
        with self.assertRaises(ValueError): self.run_import()
        self.assertFalse((self.root / 'people').exists())

    def test_direct_verified_by_both_senders_allows_two_chat_room_values(self):
        self.rows[1]['chat_room'] = 'wx_f'
        self.refresh()
        self.assertTrue(self.run_import().is_file())


if __name__ == '__main__':
    unittest.main()
