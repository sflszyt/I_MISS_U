"""Only synthetic, reproducible small and 34-file ~8 MB fixtures."""
import json
import sys
from pathlib import Path
from tests.archive_cache_browser_fixture import generate
from tools.build_archive_cache_manifest import build_manifest
from tools.build_companion_page import build

out = Path(sys.argv[1])
generate(out, reset_ui_prefs=True, hide_ready_banner=True)
scope = dict(person='synthetic', relationship_id='synthetic_father')
if '--large' in sys.argv:
    context = json.loads((out/'data/chat_context.json').read_text())
    context['message_shards'] = [f'messages-{2000+i}.json' for i in range(31)]
    row = json.loads((out/'data/messages-2000.json').read_text())[0]
    for i, name in enumerate(context['message_shards']):
        rows = [dict(row, record_id=f'synthetic-{i}-{j}', provenance={'source_record_id':f'synthetic-{i}-{j}'},
                     sender='subject' if j % 2 else 'viewpoint_owner', sender_person_id='synthetic' if j % 2 else 'father',
                     text='synthetic archive '+('x'*650)) for j in range(260)]
        (out/'data'/name).write_text(json.dumps(rows), encoding='utf-8')
    (out/'data/chat_context.json').write_text(json.dumps(context), encoding='utf-8')
    (out/'data/archive-cache-manifest.json').write_text(json.dumps(build_manifest(out, 'data/chat_context.json', scope)), encoding='utf-8')
(out/'companion.html').write_text(build('synthetic', str(out), 'father', relationship_scope=scope,
    archive_manifest_path='data/archive-cache-manifest.json', intro_card=True,
    llm_proxy='/v1/chat/completions', tts_token='synthetic', tts_origin='same',
    voice_groups=True, auto_voice_session=True, reset_ui_prefs=True, hide_ready_banner=True), encoding='utf-8')
