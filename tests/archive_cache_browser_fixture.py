"""Generate a synthetic-only opt-in browser fixture in the requested new directory."""
import json
from pathlib import Path
import sys
from tools.build_companion_page import build
from tools.build_archive_cache_manifest import build_manifest


def generate(out, memory=False, revision_v2=False, reset_ui_prefs=False, hide_ready_banner=False):
    out = Path(out)
    out.mkdir(exist_ok=False)
    (out / 'data').mkdir()
    scope = dict(person='synthetic', relationship_id='synthetic_father')
    memory_container = None
    if memory:
        from tests.test_couple_memory_release import fixture
        from tools.couple_memory_release import validate_release, runtime_binding
        packet, rows = fixture()
        if revision_v2:
            from tests.test_couple_memory_release import resign
            packet['cards'][0]['title'] = 'synthetic updated plan'
            packet['cards'][0]['texts'] = ['synthetic updated plan; completion unknown']
            resign(packet)
        memory_container = validate_release(packet, rows, '0' * 64)
        scope = dict(person='mama', relationship_id='mama_father', memory_release=runtime_binding(memory_container))
    context = dict(scope, viewer='father', schema_version=2, language='mandarin',
        coverage_status='partial', system_prompt='Synthetic only',
        message_shards=['messages-2000.json', 'messages-2001.json'])
    row = dict(scope, viewpoint='father', conversation_kind='direct', content_type='text', tier=2,
        record_id='synthetic-1', provenance={'source_record_id':'synthetic-1'}, sender_person_id='father',
        sender='viewpoint_owner', participant_ids=['synthetic','father'], text='synthetic archive')
    files = {'chat_context.json':context,'messages-2000.json':[row], 'messages-2001.json':[],
             'memories.json':dict(scope, entries=[]),'transcripts.json':dict(person=scope['person'],relationship_id=scope['relationship_id'],entries=[])}
    if memory:
        files['messages-2000.json'] = rows
        del files['memories.json']
        files['memories-' + memory_container['release_revision'] + '.json'] = memory_container
    for name, value in files.items():
        (out/'data'/name).write_text(json.dumps(value), encoding='utf-8')
    (out/'data/archive-cache-manifest.json').write_text(json.dumps(build_manifest(out, 'data/chat_context.json', scope)), encoding='utf-8')
    html = build(scope['person'], str(out), 'father', relationship_scope=scope,
        archive_manifest_path='data/archive-cache-manifest.json', intro_card=True,
        llm_proxy='/v1/chat/completions', tts_token='synthetic', tts_origin='same',
        voice_groups=True, auto_voice_session=True, reset_ui_prefs=reset_ui_prefs, hide_ready_banner=hide_ready_banner)
    (out/'companion.html').write_text(html, encoding='utf-8')
    # Test the default byte path separately: no archive cache module should be embedded.
    (out/'owner.html').write_text(build('synthetic', str(out), 'owner'), encoding='utf-8')


if __name__ == '__main__':
    generate(sys.argv[1], '--memory' in sys.argv[2:], '--memory-revision-v2' in sys.argv[2:], '--reset-ui-prefs' in sys.argv[2:], '--hide-ready-banner' in sys.argv[2:])
