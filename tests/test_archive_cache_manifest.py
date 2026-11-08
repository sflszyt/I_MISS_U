import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from tools import build_companion_page


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'data').mkdir()
        self.scope = {'person': 'test', 'relationship_id': 'test_father'}
        self.context = dict(self.scope, viewer='father', schema_version=2,
                            language='mandarin', coverage_status='partial',
                            system_prompt='synthetic', message_shards=['messages-2000.json'])
        self.write('chat_context.json', self.context)
        self.write('messages-2000.json', [])
        for name in ('memories.json', 'transcripts.json'):
            self.write(name, dict(self.scope, entries=[]))
        self.write('sessions_father.json', {'secret': 'must not persist'})

    def write(self, name, value):
        (self.root / 'data' / name).write_text(json.dumps(value), encoding='utf-8')

    def build(self):
        from tools.build_archive_cache_manifest import build_manifest
        return build_manifest(self.root, 'data/chat_context.json', self.scope)

    def test_exact_deterministic_allowlist_and_changed_bytes(self):
        self.assertIsNotNone(importlib.util.find_spec('tools.build_archive_cache_manifest'))
        first = self.build()
        self.assertEqual(first, self.build())
        self.assertEqual({f['path'] for f in first['files']}, {
            'data/chat_context.json', 'data/messages-2000.json',
            'data/memories.json', 'data/transcripts.json'})
        p = self.root / 'data/messages-2000.json'
        p.write_bytes(p.read_bytes() + b'\n')
        self.assertNotEqual(first['revision'], self.build()['revision'])
        self.assertNotIn(str(self.root), json.dumps(first))

    def test_reject_scope_duplicate_escape_and_missing(self):
        for changes in ({'viewer': 'owner'}, {'relationship_id': 'other'},
                        {'message_shards': ['../sessions_father.json']},
                        {'message_shards': ['messages-2000.json'] * 2},
                        {'message_shards': ['messages-2001.json']}):
            with self.subTest(changes=changes):
                self.write('chat_context.json', dict(self.context, **changes))
                with self.assertRaises(ValueError):
                    self.build()

    def test_builder_opt_in(self):
        plain = build_companion_page.build('test', '.', 'owner')
        self.assertNotIn('ArchiveDeviceCache', plain)
        enabled = build_companion_page.build('test', '.', 'father', relationship_scope=self.scope,
                   archive_manifest_path='data/archive-cache-manifest.json')
        self.assertIn('ArchiveDeviceCache', enabled)
        self.assertIn('D15', enabled)
        self.assertIn('#intro-card .archive-cache-controls p', enabled)
        self.assertIn('#intro-card #intro-progress{color:#3a3330;}', enabled)
        for path in ('../x.json', 'https://x/a.json', 'data/sessions_father.json'):
            with self.assertRaises(ValueError):
                build_companion_page.build('test', '.', 'father', relationship_scope=self.scope,
                    archive_manifest_path=path)
        with self.assertRaises(ValueError):
            build_companion_page.build('test', '.', 'owner', archive_manifest_path='data/archive-cache-manifest.json')

    def test_dotted_context_and_invalid_payloads(self):
        from tools.build_archive_cache_manifest import build_manifest
        self.write('chat_context.welcome-20261029-d14.json', self.context)
        result = build_manifest(self.root, 'data/chat_context.welcome-20261029-d14.json', self.scope)
        self.assertIn('data/chat_context.welcome-20261029-d14.json', [f['path'] for f in result['files']])
        for name, payload in [('messages-2000.json', {}), ('messages-2000.json', [{'person':'other'}]),
                              ('transcripts.json', dict(self.scope, entries=[{'person':'test'}]))]:
            with self.subTest(name=name, payload=payload):
                old = (self.root/'data'/name).read_bytes()
                self.write(name, payload)
                with self.assertRaises(ValueError):
                    self.build()
                (self.root/'data'/name).write_bytes(old)
        (self.root/'data/messages-2000.json').unlink()
        with self.assertRaises(ValueError):
            self.build()

    def test_nonempty_bound_memory_and_evidence_tamper(self):
        from tests.test_couple_memory_release import fixture
        from tools.couple_memory_release import validate_release, runtime_binding
        from tools.build_archive_cache_manifest import build_manifest
        packet, rows = fixture()
        container = validate_release(packet, rows, '0' * 64)
        scope = dict(person='mama', relationship_id='mama_father', memory_release=runtime_binding(container))
        self.write('chat_context.json', dict(self.context, **scope))
        self.write('messages-2000.json', rows)
        self.write('transcripts.json', dict(person='mama', relationship_id='mama_father', entries=[]))
        name = 'memories-' + container['release_revision'] + '.json'
        self.write(name, container)
        result = build_manifest(self.root, 'data/chat_context.json', scope)
        self.assertIn('data/' + name, [f['path'] for f in result['files']])
        self.assertNotIn('data/memories.json', [f['path'] for f in result['files']])
        container['entries'][0]['texts'][0] = 'corrupted'
        self.write(name, container)
        with self.assertRaises(ValueError):
            build_manifest(self.root, 'data/chat_context.json', scope)
