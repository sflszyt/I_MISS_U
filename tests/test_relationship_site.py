import importlib
import base64
import json
import unittest
import re
import subprocess
import threading
import os
import shutil
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from tests import test_import_wechat_viewpoint as fixtures
from tools import build_companion_page, build_relationship_data
from tools.viewpoint_manifest import sha256


class RelationshipSiteTests(unittest.TestCase):
    row = fixtures.ImportViewpointTests.row
    refresh = fixtures.ImportViewpointTests.refresh
    run_import = fixtures.ImportViewpointTests.run_import

    def setUp(self):
        fixtures.ImportViewpointTests.setUp(self)
        self.rows[1]['content'] = 'synthetic 桂花糕是我们夫妻散步后买的'
        self.rows[2]['content'] = 'FORBIDDEN_GROUP_ONLY'
        self.refresh()
        dataset = self.run_import()
        self.material = self.root / 'material'
        build_relationship_data.build(person='mama', datasets=[dataset], viewer='father', out=self.material)
        self.current = self.root / 'current'
        self.current.mkdir()
        self.config = self.root / 'relationship.json'
        fixtures.dump(self.config, dict(person='mama', viewer='father', relationship={
            'subject_to_viewpoint': 'wife', 'viewpoint_to_subject': 'husband', 'viewpoint_user': 'father'}))
        (self.current / 'companion.html').write_text(build_companion_page.build(
            'mama', str(self.current), 'father', tts_origin='same', tts_token='synthetic-token',
            llm_proxy='/v1/chat/completions', sessions_path='data_father/sessions/sessions.json',
            intro_card=True, intro_builder='儿子', offline_fallback=True), encoding='utf-8')
        fixtures.dump(self.current / 'data_father/sessions/sessions.json',
                      dict(person='mama', viewer='father', sessions=[dict(
                          session_id='synthetic-old', date='2026-10-19', turns=[
                              dict(role='user', text='合成历史问候', turn=1),
                              dict(role='simulacrum', text='合成历史回复', turn=1)])], recent_dates=[]))
        fixtures.dump(self.current / 'data/memories.json', dict(entries=[{'text': 'FORBIDDEN_OLD_CARD'}]))
        fixtures.dump(self.current / 'data/messages-2020.json', [{'text': 'FORBIDDEN_OWNER_ONLY'}])
        (self.current / 'offline.html').write_text('<meta charset="utf-8">offline', encoding='utf-8')
        (self.current / 'sw.js').write_text('// synthetic offline only', encoding='utf-8')
        avatar = self.current / 'data/avatar'
        fixtures.dump(avatar / 'mouth_patches.json', dict(
            states={name: 'mouth.png' for name in ['closed', 'half', 'open', 'wide', 'round']},
            rect=[0, 0, 1, 1], image_size=[1, 1],
            blink=dict(file='eyes.png', min_gap_ms=2500, max_gap_ms=5500, duration_ms=130)))
        for name in ['avatar.png', 'mouth.png', 'eyes.png']:
            (avatar / name).write_bytes(base64.b64decode(
                'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='))
        fixtures.dump(avatar / 'emotions.json', dict(emotions={
            'happy': dict(file='data/avatar/mouth.png?v=fixture', keywords=['开心'])}))
        fixtures.dump(avatar / 'visemes.json', {'old-private-voice': 'forbidden'})
        self.out = self.root / 'staging'

    def build(self, **kwargs):
        module = importlib.import_module('tools.build_relationship_site')
        args = dict(person='mama', viewer='father', relationship_build=self.material / 'build.json',
                    relationship_config=self.config, current_site=self.current, out=self.out)
        args.update(kwargs)
        return module.build(**args)

    def test_reject_scope_hash_missing_and_paths_before_output(self):
        manifest_path = self.material / 'build.json'
        original = json.loads(manifest_path.read_text())
        for mode in ['scope', 'hash', 'missing', 'path', 'viewer']:
            with self.subTest(mode=mode):
                manifest = json.loads(json.dumps(original))
                if mode == 'scope':
                    manifest['relationship_id'] = 'mama_owner'
                elif mode == 'hash':
                    manifest['relationship_files']['messages.jsonl'] = '0' * 64
                elif mode == 'missing':
                    del manifest['relationship_files']['memories.json']
                elif mode == 'path':
                    manifest['relationship_files']['../escape'] = '0' * 64
                else:
                    manifest['viewer'] = 'owner'
                fixtures.dump(manifest_path, manifest)
                with self.assertRaises(ValueError):
                    self.build()
                self.assertFalse(self.out.exists())
        fixtures.dump(manifest_path, original)

    def test_reject_row_scope_even_when_hash_updated(self):
        path = self.material / 'relationship/messages.jsonl'
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[0]['viewpoint'] = 'owner'
        path.write_text('\n'.join(json.dumps(row) for row in rows), encoding='utf-8')
        manifest = json.loads((self.material / 'build.json').read_text())
        manifest['relationship_files']['messages.jsonl'] = sha256(path)
        fixtures.dump(self.material / 'build.json', manifest)
        with self.assertRaises(ValueError):
            self.build()
        self.assertFalse(self.out.exists())

    def test_reject_missing_file_nonempty_knowledge_and_output_overlap(self):
        path = self.material / 'relationship/memories.json'
        original = path.read_bytes()
        path.unlink()
        with self.assertRaises(ValueError):
            self.build()
        self.assertFalse(self.out.exists())
        path.write_bytes(original)
        for output in [self.current / 'new', self.material / 'new', self.root / 'people/mama/raw/new']:
            with self.assertRaises(ValueError):
                self.build(out=output)
            self.assertFalse(output.exists())
        with self.assertRaises(ValueError):
            self.build(report=self.out / 'report.json')
        value = json.loads(original)
        value['entries'] = [{'person': 'mama', 'relationship_id': 'mama_father', 'tier': 1}]
        fixtures.dump(path, value)
        manifest = json.loads((self.material / 'build.json').read_text())
        manifest['relationship_files']['memories.json'] = sha256(path)
        fixtures.dump(self.material / 'build.json', manifest)
        with self.assertRaises(ValueError):
            self.build()
        self.assertFalse(self.out.exists())

    def test_normalized_output_report_boundaries_reject_before_writes(self):
        for output in [self.root / 'people/mama/RAW/new-site',
                       self.root / 'alias/../current/new-site',
                       self.root / 'alias/../material/new-site']:
            with self.subTest(output=str(output)):
                with self.assertRaises(ValueError):
                    self.build(out=output)
                self.assertFalse(output.resolve().exists())
        for report in [self.root / 'alias/../staging/companion.html',
                       self.root / 'alias/../current/new-report.json',
                       self.root / 'alias/../material/new-report.json',
                       self.root / 'people/mama/RAW/report.json',
                       self.root / 'alias/../relationship.json',
                       self.root / 'alias/../staging']:
            with self.subTest(report=str(report)):
                with self.assertRaises(ValueError):
                    self.build(report=report)
                self.assertFalse(self.out.exists())
        self.assertFalse((self.current / 'new-report.json').exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows junction boundary')
    def test_junction_output_and_report_rejected(self):
        alias = self.root / 'junction'
        command = "New-Item -ItemType Junction -Path '" + str(alias) + "' -Target '" + str(self.current) + "' | Out-Null"
        result = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', command],
                                capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
        self.addCleanup(lambda: os.rmdir(alias) if alias.exists() else None)
        with self.assertRaises(ValueError):
            self.build(out=alias / 'new-site')
        with self.assertRaises(ValueError):
            self.build(report=alias / 'new-report.json')
        self.assertFalse(self.out.exists())
        self.assertFalse((self.current / 'new-site').exists())
        self.assertFalse((self.current / 'new-report.json').exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows external source junctions')
    def test_resolved_external_face_and_sessions_are_protected_inputs(self):
        for relative, external in [('data/avatar', 'external-avatar'),
                                   ('data_father/sessions', 'external/father')]:
            link = self.current / relative
            target = self.root / external
            target.parent.mkdir(parents=True, exist_ok=True)
            self.assertTrue(link.resolve().is_relative_to(self.root.resolve()))
            self.assertTrue(target.resolve().is_relative_to(self.root.resolve()))
            shutil.move(str(link), str(target))
            command = "New-Item -ItemType Junction -Path '" + str(link) + "' -Target '" + str(target) + "' | Out-Null"
            result = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', command],
                                    capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0)
            self.addCleanup(lambda p=link: os.rmdir(p) if p.exists() else None)
            with self.assertRaises(ValueError):
                self.build(out=target / 'new-site')
            with self.assertRaises(ValueError):
                self.build(report=target / 'report.json')
            self.assertFalse(self.out.exists())
            self.assertFalse((target / 'new-site').exists())
            self.assertFalse((target / 'report.json').exists())
        self.build()
        junction = self.out / 'data_father/sessions'
        self.assertEqual(junction.resolve(), (self.root / 'external/father').resolve())
        self.addCleanup(lambda: os.rmdir(junction) if junction.exists() else None)

    def test_staging_contains_only_scoped_text_face_and_father_sessions(self):
        self.build()
        context = json.loads((self.out / 'data/chat_context.json').read_text(encoding='utf-8'))
        self.assertEqual(context['relationship_id'], 'mama_father')
        self.assertTrue(context['message_shards'])
        self.assertIn('partial', context['system_prompt'])
        self.assertIn('Tier-3', context['system_prompt'])
        self.assertFalse((self.out / 'data/avatar/visemes.json').exists())
        self.assertFalse((self.out / 'data/media_index.json').exists())
        self.assertEqual(json.loads((self.out / 'data/memories.json').read_text())['entries'], [])
        html = (self.out / 'companion.html').read_text(encoding='utf-8')
        self.assertIn('synthetic-token', html)
        self.assertIn('夫妻', html)
        self.assertNotIn('来自儿子手机', html)
        self.assertIn('EXPECTED_SCOPE', html)
        face = (self.out / 'avatar.html').read_text(encoding='utf-8')
        self.assertIn('id="player"', face)
        self.assertIn('createMediaElementSource', face)
        self.assertNotIn('old-private-voice', face)
        with self.assertRaises(ValueError):
            self.build()

    def test_generated_site_can_be_used_for_next_build(self):
        config_path = self.current / 'data/avatar/mouth_patches.json'
        original = json.loads(config_path.read_text())
        original['private_voice_index'] = 'FORBIDDEN_ORIGINAL_AUDIO'
        fixtures.dump(config_path, original)
        self.build()
        second = self.root / 'staging-second'
        self.build(current_site=self.out, out=second)
        for site in (self.out, second):
            face_config = json.loads((site / 'data/avatar/mouth_patches.json').read_text())
            self.assertEqual(set(face_config), {'states', 'blink', 'viseme_map', 'rms_states'})
            self.assertEqual(face_config['states'], original['states'])
            self.assertEqual(face_config['blink'], original['blink'])
            self.assertNotIn('FORBIDDEN_ORIGINAL_AUDIO', json.dumps(face_config))
            self.assertFalse((site / 'data/avatar/visemes.json').exists())
            html = (site / 'avatar.html').read_text(encoding='utf-8')
            playlist = re.search(r'id="playlist-data">\s*(.*?)\s*</script>', html, re.S)
            self.assertEqual(json.loads(playlist[1]), [])
        for name in ['avatar.html', 'data/avatar/mouth_patches.json',
                     'data/avatar/emotions.json', 'companion.html']:
            self.assertEqual((self.out / name).read_bytes(), (second / name).read_bytes())

    def test_versioned_release_preserves_old_empty_bytes(self):
        from tests.test_couple_memory_release import fixture,resign
        from tools.couple_memory_release import text_hash
        packet,_=fixture();source=self.material/'relationship/messages.jsonl'
        rows=[json.loads(x) for x in source.read_text(encoding='utf-8').splitlines()]
        row=next(r for r in rows if r.get('content_type')=='text' and r.get('text'))
        packet['source_sha256']=sha256(source);card=packet['cards'][0];card['date']=row['timestamp'][:10]
        card['provenance'].update(source_sha256=sha256(source),sources=[dict(record_id=row['record_id'],timestamp=row['timestamp'],speaker_id=row['sender_person_id'],text_sha256=text_hash(row['text']))])
        resign(packet);packet_path=self.root/'release.json';fixtures.dump(packet_path,packet)
        legacy=b'{ "person": "mama", "relationship_id": "mama_father", "entries": [] }\n'
        (self.current/'data/memories.json').write_bytes(legacy)
        report=self.build(memory_release=packet_path)
        self.assertEqual((self.out/'data/memories.json').read_bytes(),legacy)
        # An already-loaded old client's unconditional Tier1 mapping sees zero cards.
        old_entries=json.loads((self.out/'data/memories.json').read_bytes())['entries']
        self.assertEqual([dict(tier=1,text=e) for e in old_entries],[])
        name='memories-'+packet['release_revision']+'.json'
        self.assertEqual(report['memory_filename'],name)
        self.assertEqual(report['memories'],1)
        self.assertEqual(json.loads((self.out/'data'/name).read_bytes())['entries'][0]['tier'],2)

    def test_source_changed_between_manifest_and_snapshot_refused(self):
        from unittest.mock import patch
        module=importlib.import_module('tools.build_relationship_site')
        original=module.sha256
        def mutate(source):
            result=original(source)
            if source.name == 'messages.jsonl':source.write_bytes(source.read_bytes()+b'\n')
            return result
        with patch.object(module,'sha256',side_effect=mutate):
            with self.assertRaises(ValueError):self.build()
        self.assertFalse(self.out.exists())

    def test_packet_changed_before_write_refused(self):
        from unittest.mock import patch
        from tests.test_couple_memory_release import fixture, resign
        from tools.couple_memory_release import text_hash
        module=importlib.import_module('tools.build_relationship_site')
        packet,_=fixture()
        source=self.material/'relationship/messages.jsonl'
        rows=[json.loads(x) for x in source.read_text(encoding='utf-8').splitlines()]
        row=next(r for r in rows if r.get('content_type')=='text' and r.get('text'))
        packet['source_sha256']=sha256(source);card=packet['cards'][0];card['date']=row['timestamp'][:10]
        card['provenance'].update(source_sha256=sha256(source),sources=[dict(record_id=row['record_id'],timestamp=row['timestamp'],speaker_id=row['sender_person_id'],text_sha256=text_hash(row['text']))])
        resign(packet);packet_path=self.root/'release.json';fixtures.dump(packet_path,packet)
        fixtures.dump(self.current/'data/memories.json',dict(person='mama',relationship_id='mama_father',entries=[]))
        original=module.face_files
        def mutate(current):
            result=original(current);packet_path.write_bytes(packet_path.read_bytes()+b'\n');return result
        with patch.object(module,'face_files',side_effect=mutate):
            with self.assertRaises(ValueError):self.build(memory_release=packet_path)
        self.assertFalse(self.out.exists())

    def test_source_changed_before_write_refused(self):
        from unittest.mock import patch
        module=importlib.import_module('tools.build_relationship_site')
        original=module.face_files
        source=self.material / 'relationship/messages.jsonl'
        def mutate(current):
            result=original(current)
            source.write_bytes(source.read_bytes()+b'\n')
            return result
        with patch.object(module,'face_files',side_effect=mutate):
            with self.assertRaises(ValueError):self.build()
        self.assertFalse(self.out.exists())

    def test_real_fetch_chain_reaches_proxy_and_scope_failure_blocks(self):
        from tests.test_couple_memory_release import fixture, resign
        from tools.couple_memory_release import text_hash, runtime_binding, validate_release
        packet, _ = fixture()
        source = self.material / 'relationship/messages.jsonl'
        rows = [json.loads(x) for x in source.read_text(encoding='utf-8').splitlines()]
        row = next(r for r in rows if r.get('content_type') == 'text' and r.get('text'))
        packet['source_sha256'] = sha256(source)
        card = packet['cards'][0]
        card['date'] = row['timestamp'][:10]
        card['provenance'].update(source_sha256=sha256(source), sources=[dict(record_id=row['record_id'],timestamp=row['timestamp'],speaker_id=row['sender_person_id'],text_sha256=text_hash(row['text']))])
        resign(packet)
        release_path = self.root / 'release.json'
        fixtures.dump(release_path, packet)
        fixtures.dump(self.current/'data/memories.json',dict(person='mama',relationship_id='mama_father',entries=[]))
        binding = runtime_binding(validate_release(packet, rows, sha256(source)))
        self.build(memory_release=release_path)
        requests = []
        root = self.out

        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(root), **kwargs)

            def log_message(self, *args):
                pass

            def do_POST(self):
                requests.append((self.path, self.headers.get('X-TTS-Token'),
                                 json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
                body = b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n'
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        html = (self.out / 'companion.html').read_text(encoding='utf-8')
        names = ['dataProgressSnapshot', 'reportDataProgress', 'drainDataQueue','boundedWait','dataFailure', 'dataError', 'fetchDataJson', 'checkScope', 'validateMemoryRelease', 'scoreText', 'retrieveSnippets', 'retrieveKnowledge',
                 'buildRetrievalBlock', 'buildMessages', 'loadShards', 'loadKnowledge',
                 'collectAllRecords', 'streamRequest', 'companionStream', 'newRequestDiagnostic', 'requestDiagnosticText', 'sseCreate', 'sseFeed',
                 'sseFinish', 'sseProcessLine', 'settingsComplete']
        functions = '\n'.join(re.search(r'^(?:async )?function ' + name + r'\([^\n]*\) \{.*?^\}|^function ' +
                              name + r'\([^\n]*\) \{[^\n]*\}', html, re.M | re.S).group()
                              for name in names)
        script = """
const assert = require('assert'); const crypto = require('crypto').webcrypto;var memorySourceDigests=new Map();var dataFailures=Object.create(null);var dataQueue=[],dataActive=0,dataBlocked=0,dataRequests=Object.create(null);
console.info = (...args) => process.stderr.write(JSON.stringify(args) + String.fromCharCode(10));
const nativeFetch = global.fetch;
const base = process.argv[2];
global.fetch = (url, opts) => nativeFetch(new URL(url, base), opts);
var EXPECTED_SCOPE={person:'mama',relationship_id:'mama_father',memory_release:RELEASE_BINDING}, VIEWER='father';
var scopeError=false, contextLoaded=false, shards=[], shardsLoading=false;
var dataReadyPhase='idle',dataProgress=Object.create(null),dataProgressListeners=[],knowledgePieces=Object.create(null);
var shardCache={}, shardStatus={}, knowledgeLoading=false, knowledgeCache=null;
var LLM_PROXY='/v1/chat/completions', TTS_TOKEN='synthetic-token', settings={};
var location={origin:base}, controller=null, streaming=false;
var sendBtn={textContent:'',classList:{add(){}}};
function loadSessionsData(){return Promise.resolve();}
function applySessionsCard(){}
""" + functions + """
(async()=>{
  let rejected=false;
  try {
    const ctx=await (await fetch('/data/chat_context.json')).json();
    checkScope(ctx,'context'); shards=ctx.message_shards; contextLoaded=true;
    await Promise.all([loadShards(),loadKnowledge()]);
    const all=collectAllRecords();
    const hits=retrieveSnippets(['synthetic'],all,{top:6});
    const knowledge=retrieveKnowledge(['synthetic'],(knowledgeCache||{}).memories,[],{});
    const block=buildRetrievalBlock(knowledge.memories.concat(hits));
    const messages=buildMessages(ctx.system_prompt,[],block,'synthetic');
    await new Promise((resolve)=>{
      streamRequest(messages,()=>{},()=>resolve(),()=>{rejected=true;resolve();},{provider:'deepseek',model:'deepseek-v4-pro'});
    });
    if(!rejected) {
      assert(block.includes('mama_father')); assert(block.includes('completion unknown')); assert(!block.includes('Tier-1'));
      assert(block.includes('source_sha256='));
      assert(!JSON.stringify(messages).includes('old-private-voice'));
    }
  } catch(e) { if(!scopeError) throw e; rejected=true; }
  console.log(rejected ? 'BLOCKED' : 'SENT');
})().catch(e=>{console.error(e);process.exitCode=1;});
"""
        script = script.replace('RELEASE_BINDING', json.dumps(binding))
        base = 'http://127.0.0.1:' + str(server.server_port)
        def run(expected):
            result = subprocess.run(['node', '-', base], input=script, text=True,
                                    encoding='utf-8', capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), expected)
        run('SENT')
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0][:2], ('/v1/chat/completions', 'synthetic-token'))
        self.assertIn('Tier-2', requests[0][2]['messages'][-1]['content'])
        ctx_path = self.out / 'data/chat_context.json'
        context = json.loads(ctx_path.read_text(encoding='utf-8'))
        shard_path = self.out / 'data' / context['message_shards'][0]
        original = shard_path.read_bytes()
        records = json.loads(original)
        records[0]['relationship_id'] = 'mama_owner'
        fixtures.dump(shard_path, records)
        run('BLOCKED')
        shard_path.write_bytes(original)
        shard_path.unlink()
        run('BLOCKED')
        shard_path.write_bytes(original)
        fixtures.dump(self.out / 'data' / ('memories-'+binding['release_revision']+'.json'), dict(person='mama', relationship_id='mama_owner', entries=[]))
        run('BLOCKED')
        context['viewer'] = 'owner'
        fixtures.dump(ctx_path, context)
        run('BLOCKED')
        self.assertEqual(len(requests), 1)


if __name__ == '__main__':
    unittest.main()
