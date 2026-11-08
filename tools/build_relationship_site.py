"""Build a fresh, scoped relationship site; never publish or fall back to legacy data."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

if __package__:
    from .couple_memory_release import validate_release, runtime_binding
    from . import build_avatar_page as avatar, build_companion_page as companion
    from .build_chat_context import scoped_context, build_rhythm_block
    from .viewpoint_manifest import no_links, safe_path, read_json, read_jsonl, sha256, slug
else:
    from couple_memory_release import validate_release, runtime_binding
    import build_avatar_page as avatar
    import build_companion_page as companion
    from build_chat_context import scoped_context, build_rhythm_block
    from viewpoint_manifest import no_links, safe_path, read_json, read_jsonl, sha256, slug


REQUIRED = {'messages.jsonl', 'examples.jsonl', 'rhythm.json', 'memories.json',
            'transcripts.json', 'chat_context.json', 'scope.json'}
ALLOWED = REQUIRED | {'persona_digest.json', 'persona.md', 'candidates.jsonl',
                      'gate.html', 'messages.json', 'index.html'}


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def validate_row(row, person, relationship):
    if (row.get('person') != person or row.get('relationship_id') != relationship or
            row.get('viewpoint') != 'father' or row.get('conversation_kind') != 'direct' or
            set(row.get('participant_ids', [])) != {person, 'father'} or
            row.get('sender_person_id') not in (person, 'father') or
            row.get('sender') != ('subject' if row.get('sender_person_id') == person else 'viewpoint_owner') or
            row.get('tier') != 2 or not row.get('record_id') or
            row.get('provenance', {}).get('source_record_id') != row.get('record_id')):
        raise ValueError('relationship record scope mismatch')


def rebuild_father_context(context, rhythm, examples, *, template):
    """Pure prompt rebuild from trusted scoped source artifacts; preserve all other bindings.

    The caller verifies source hashes and membership (as build() does below).
    This function never edits or heuristically strips a previously compiled prompt.
    """
    person = context.get('person')
    slug(person)
    relationship = person + '_father'
    if (context.get('schema_version') != 2 or context.get('viewer') != 'father' or
            context.get('relationship_id') != relationship or
            context.get('language') != 'mandarin' or context.get('coverage_status') != 'partial'):
        raise ValueError('father prompt context scope mismatch')
    if rhythm.get('person') != person or rhythm.get('relationship_id') != relationship:
        raise ValueError('rhythm scope mismatch')
    for example in examples:
        row = example.get('target', {})
        validate_row(row, person, relationship)
        if (example.get('person') != person or example.get('relationship_id') != relationship or
                row.get('sender_person_id') != person or not isinstance(row.get('text'), str)):
            raise ValueError('example scope mismatch')
    sample_lines = []
    # Keep the original deterministic sample and exact fragment/provenance bytes.
    count = min(12, len(examples))
    for i in range(count):
        row = examples[i * len(examples) // count]['target']
        sample_lines.append(json.dumps(dict(text=row['text'][:120], record_id=row['record_id'],
                                           provenance=row['provenance']), ensure_ascii=False))
    prompt = (template + '\n表达习惯（Tier-2，仅供措辞与语气参考）：\n' +
              build_rhythm_block(rhythm, expression_only=True)[:1800] +
              '\n原话片段（Tier-2，截取；不是回复长度范本，不是当下事实）：\n' +
              '\n'.join(sample_lines))
    return dict(context, system_prompt=prompt)


def current_options(current, person, viewer):
    """只提取已知常量；不执行旧 HTML，不记录 token。"""
    source = (current / 'companion.html').read_text(encoding='utf-8')
    def one(pattern):
        values = re.findall(pattern, source)
        if len(values) != 1:
            raise ValueError('current page configuration is ambiguous')
        return values[0]
    if one(r"var VIEWER = '([^']*)';") != viewer:
        raise ValueError('current viewer mismatch')
    token = one(r"var TTS_TOKEN = '([^']*)';")
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', token):
        raise ValueError('invalid current token')
    if one(r"lang: '([^']*)', session_id: sessionId") != 'mandarin':
        raise ValueError('father language must remain mandarin')
    if "var ttsBase = location.origin;" not in source:
        raise ValueError('same-origin TTS required')
    if one(r"var LLM_PROXY = '([^']*)';") != '/v1/chat/completions':
        raise ValueError('unexpected proxy')
    if 'var DEFAULT_PROFILE = null;' not in source:
        raise ValueError('unexpected embedded provider configuration')
    sessions = one(r"var SESSIONS_PATH = '([^']*)';")
    if sessions != 'data_father/sessions/sessions.json':
        raise ValueError('unexpected father sessions path')
    if 'id="intro-card"' not in source or "navigator.serviceWorker.register('/sw.js')" not in source:
        raise ValueError('required introduction/offline configuration missing')
    return dict(person=person, viewer=viewer, tts_token=token, lang='mandarin', tts_origin='same',
                llm_proxy='/v1/chat/completions', sessions_path=sessions,
                intro_card=True, intro_builder='儿子', offline_fallback=True)


def face_files(current):
    """从现役 face 资产重建页面，仅接收 patch 配置与 PNG，不读取原声索引。"""
    root = (current / 'data/avatar').resolve()
    cfg = read_json(root / 'mouth_patches.json')
    states = cfg.get('states')
    if not isinstance(states, dict) or not states:
        raise ValueError('patch face required')
    files = {}
    def png(name):
        if not isinstance(name, str) or not re.fullmatch(r'[a-zA-Z0-9_-]+\.png', name):
            raise ValueError('invalid face image name')
        path = safe_path(root, name)
        content = path.read_bytes()
        if not content.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError('face asset is not PNG')
        files['data/avatar/' + name] = content
        return name
    png('avatar.png')
    for key, name in states.items():
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', key):
            raise ValueError('invalid face state')
        png(name)
    blink = cfg.get('blink')
    if blink is not None:
        if not isinstance(blink, dict):
            raise ValueError('invalid blink')
        png(blink['file'])
        blink = {k: blink[k] for k in ('file', 'min_gap_ms', 'max_gap_ms', 'duration_ms') if k in blink}
    viseme_map, _ = avatar.resolve_viseme_map(cfg.get('viseme_map'), states)
    payload = dict(states=states, visemeMap=viseme_map,
                   rmsStates=avatar.resolve_rms_states(cfg.get('rms_states'), states), blink=blink)
    # 保存下一次构建需要的最小配置；不复制原配置中的声音索引或时间轴。
    files['data/avatar/mouth_patches.json'] = encode(dict(
        states=states, blink=blink, viseme_map=viseme_map, rms_states=payload['rmsStates']))
    block = avatar.patch_avatar_block(states, {}, blink['file'] if blink else None)
    script = '<script type="application/json" id="avatar-config">' + encode(payload).decode().replace('</', '<\\/') + '</script>'
    files['avatar.html'] = avatar.generate_html([], '合成声音 · 对话模拟', block, script).encode('utf-8')
    emotions_path = root / 'emotions.json'
    if emotions_path.exists():
        emotions = read_json(emotions_path)
        clean = {'neutral_delay_ms': emotions.get('neutral_delay_ms', 1800), 'emotions': {}}
        for key, value in emotions.get('emotions', {}).items():
            if not re.fullmatch(r'[a-z0-9_]+', key):
                raise ValueError('invalid emotion name')
            match = re.fullmatch(r'data/avatar/([a-zA-Z0-9_-]+\.png)(?:\?v=[a-zA-Z0-9]+)?', value.get('file', ''))
            if not match or not isinstance(value.get('keywords', []), list):
                raise ValueError('invalid emotion asset')
            name = png(match[1])
            clean['emotions'][key] = dict(file='data/avatar/' + name, keywords=value.get('keywords', []))
        files['data/avatar/emotions.json'] = encode(clean)
    return files


def session_source(current, relative):
    path = current.joinpath(*relative.split('/'))
    root = path.parent.resolve()
    payload = read_json(root / 'sessions.json')
    if payload.get('viewer') != 'father':
        raise ValueError('sessions viewer mismatch')
    # 允许现役的明确 father 联接；拒绝其他 viewer 或额外公开文件。
    for p in root.rglob('*'):
        no_links(p)
        rel = p.relative_to(root).as_posix()
        if p.is_file() and rel != 'sessions.json' and not re.fullmatch(r'audio/[A-Za-z0-9_.-]+\.(wav|mp3|ogg|m4a)', rel):
            raise ValueError('unexpected sessions file')
        if p.is_dir() and rel != 'audio':
            raise ValueError('unexpected sessions directory')
    if root.is_relative_to(current.resolve()):
        return root, False
    if root.name != 'father':
        raise ValueError('external sessions source must be father directory')
    return root, True


def build(*, person, viewer, relationship_build, relationship_config, current_site, out, report=None, memory_release=None):
    slug(person)
    if viewer != 'father':
        raise ValueError('this live-site mode requires father')
    manifest_path, current, out = Path(relationship_build), Path(current_site), Path(out)
    no_links(manifest_path)
    no_links(current)
    no_links(out)
    out = out.resolve()
    if out.exists() or any(part.casefold() == 'raw' for part in out.parts):
        raise ValueError('output must be new and outside raw')
    for source in (manifest_path.parent.resolve(), current.resolve(), Path(relationship_config).resolve()):
        if out.resolve().is_relative_to(source) or source.is_relative_to(out.resolve()):
            raise ValueError('output overlaps input')
    if report:
        report = Path(report)
        no_links(report)
        report = report.resolve()
        if (report.exists() or report.is_relative_to(out) or
                report.is_relative_to(current.resolve()) or
                any(part.casefold() == 'raw' for part in report.parts)):
            raise ValueError('report must be new and outside site')
        if report.is_relative_to(manifest_path.parent.resolve()):
            raise ValueError('report overlaps relationship input')
    manifest = read_json(manifest_path)
    context = scoped_context(manifest)
    relationship = person + '_father'
    if (manifest.get('person') != person or manifest.get('viewer') != viewer or
            manifest.get('relationship_path') != 'relationship' or
            manifest.get('coverage_status') != 'partial' or manifest.get('shared_facts') != []):
        raise ValueError('manifest scope mismatch')
    config = read_json(Path(relationship_config))
    if (config.get('person') != person or config.get('viewer') != viewer or
            config.get('relationship') != dict(subject_to_viewpoint='wife',
                viewpoint_to_subject='husband', viewpoint_user='father')):
        raise ValueError('relationship config mismatch')
    listed = manifest.get('relationship_files', {})
    if not isinstance(listed, dict) or not REQUIRED.issubset(listed):
        raise ValueError('incomplete relationship manifest')
    root = manifest_path.parent / 'relationship'
    for name, expected in listed.items():
        if name not in ALLOWED and not re.fullmatch(r'messages-\d{4}\.html', name):
            raise ValueError('unexpected relationship file')
        path = safe_path(root, name)
        if not path.is_file() or sha256(path) != expected:
            raise ValueError('relationship file missing or hash mismatch')
    for name in ('scope.json', 'chat_context.json'):
        value = read_json(root / name)
        if any(value.get(k) != context[k] for k in ('person', 'viewer', 'relationship_id', 'language', 'coverage_status')):
            raise ValueError('relationship metadata mismatch')
    source_path = root / 'messages.jsonl'
    source_bytes = source_path.read_bytes()
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    if source_hash != listed['messages.jsonl']:
        raise ValueError('source changed after manifest verification')
    rows = [json.loads(line) for line in source_bytes.decode('utf-8').splitlines() if line.strip()]
    if len(rows) != manifest['counts']['selected'] or len({r['record_id'] for r in rows}) != len(rows):
        raise ValueError('relationship record count mismatch')
    for row in rows:
        validate_row(row, person, relationship)
    text_rows = [r for r in rows if r.get('content_type') == 'text' and r.get('quality', {}).get('usable_text') and r.get('text')]
    if not text_rows:
        raise ValueError('no usable relationship text')
    by_id = {r['record_id']: r for r in text_rows}
    examples = read_jsonl(root / 'examples.jsonl')
    for example in examples:
        target = example.get('target', {})
        if (example.get('person') != person or example.get('relationship_id') != relationship or
                target.get('sender_person_id') != person or by_id.get(target.get('record_id')) != target):
            raise ValueError('example scope mismatch')
        if any(by_id.get(r.get('record_id')) != r for r in example.get('context', [])):
            raise ValueError('example context mismatch')
    rhythm = read_json(root / 'rhythm.json')
    if rhythm.get('person') != person or rhythm.get('relationship_id') != relationship:
        raise ValueError('rhythm scope mismatch')
    files = {}
    for name in ('memories.json', 'transcripts.json'):
        value = read_json(root / name)
        if value.get('person') != person or value.get('relationship_id') != relationship or not isinstance(value.get('entries'), list):
            raise ValueError('knowledge scope mismatch')
        # 本轮没有新的已确认资料；非空需单独审核证据合同，不能仅信 Tier 标签。
        if value['entries']:
            raise ValueError('nonempty reviewed knowledge requires explicit follow-up support')
        files['data/' + name] = encode(value)
    # Old loaded clients always fetch this fixed name and would label any entries Tier1.
    # Preserve its current exact empty payload, never expose release cards at that URL.
    legacy_memory_path = current / 'data/memories.json'
    legacy_memory_bytes = None
    if memory_release:
        legacy_memory_bytes = legacy_memory_path.read_bytes()
        legacy_memories = json.loads(legacy_memory_bytes.decode('utf-8'))
        if (legacy_memories.get('person') != person or legacy_memories.get('relationship_id') != relationship or legacy_memories.get('entries') != []):
            raise ValueError('legacy memory URL must remain empty and scoped')
        files['data/memories.json'] = legacy_memory_bytes
    memory_binding = None
    memory_filename = None
    packet_bytes = None
    if memory_release:
        packet_path = Path(memory_release)
        no_links(packet_path)
        packet_bytes = packet_path.read_bytes()
        memories = validate_release(json.loads(packet_bytes.decode('utf-8')), rows, source_hash, person, relationship)
        memory_filename = 'memories-' + memories['release_revision'] + '.json'
        files['data/' + memory_filename] = encode(memories)
        memory_binding = runtime_binding(memories)
        context['memory_release'] = memory_binding
    keys = ('record_id', 'person', 'viewpoint', 'relationship_id', 'tier', 'timestamp', 'text',
            'sender', 'sender_person_id', 'conversation_kind', 'participant_ids', 'conversation_id',
            'content_type', 'source_order', 'source_order_group', 'provenance')
    compact = [{k: r[k] for k in keys if k in r} for r in text_rows]
    shards, batch, size = [], [], 2
    for row in compact:
        length = len(encode(row)) + 1
        if length > 256000:
            raise ValueError('oversized text record')
        if batch and size + length > 256000:
            name = 'messages-%04d.json' % len(shards)
            files['data/' + name] = encode(batch)
            shards.append(name)
            batch, size = [], 2
        batch.append(row)
        size += length
    if batch:
        name = 'messages-%04d.json' % len(shards)
        files['data/' + name] = encode(batch)
        shards.append(name)
    template = (Path(__file__).resolve().parents[1] / 'prompts/chat_system.husband.scoped.zh.md').read_text(encoding='utf-8')
    context = rebuild_father_context(context, rhythm, examples, template=template)
    count = min(12, len(examples))
    context['message_shards'] = shards
    context.pop('paths', None)
    files['data/chat_context.json'] = encode(context)
    options = current_options(current, person, viewer)
    sessions_root, link_sessions = session_source(current, options['sessions_path'])
    # data 和 sessions 可为现役联接；其真实目标也属于不可写的输入。
    for source in ((current / 'data/avatar').resolve(), sessions_root):
        if out.is_relative_to(source) or source.is_relative_to(out):
            raise ValueError('output overlaps linked input')
        if report and (report.is_relative_to(source) or source.is_relative_to(report)):
            raise ValueError('report overlaps linked input')
    files.update(face_files(current))
    for name in ('offline.html', 'sw.js'):
        no_links(current / name)
        files[name] = (current / name).read_bytes()
    files['companion.html'] = companion.build(archive_dir=str(out), relationship_scope={
        'person': person, 'relationship_id': relationship, **({'memory_release': memory_binding} if memory_binding else {})}, **options).encode('utf-8')
    # 所有输入已检查完才写新目录；绝不覆盖、发布或修改旧站。
    if (source_path.read_bytes() != source_bytes or (packet_bytes is not None and packet_path.read_bytes() != packet_bytes) or
            (legacy_memory_bytes is not None and legacy_memory_path.read_bytes() != legacy_memory_bytes)):
        raise ValueError('source or release changed before output')
    out.mkdir(parents=True)
    for name, content in files.items():
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    destination = out / 'data_father/sessions'
    destination.parent.mkdir(parents=True, exist_ok=True)
    if link_sessions and os.name == 'nt':
        quote = lambda p: "'" + str(p).replace("'", "''") + "'"
        command = "$ErrorActionPreference='Stop'; New-Item -ItemType Junction -Path " + quote(destination) + " -Target " + quote(sessions_root) + " | Out-Null"
        result = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', command], capture_output=True)
        if result.returncode:
            raise ValueError('cannot create father sessions junction; staging not ready')
    elif link_sessions:
        destination.symlink_to(sessions_root, target_is_directory=True)
    else:
        shutil.copytree(sessions_root, destination)
    summary = dict(person=person, viewer=viewer, relationship_id=relationship, language='mandarin',
                   coverage_status='partial', records=len(compact), shards=len(shards), examples=count,
                   memories=len(memories['entries']) if memory_binding else 0, transcripts=0, memory_filename=memory_filename, source_build_sha256=sha256(manifest_path),
                   runtime_options_preserved=True, sessions_link=link_sessions,
                   files={name: sha256(out / name) for name in sorted(files)})
    if report:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_bytes(encode(summary))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('person', 'viewer', 'relationship-build', 'relationship-config', 'current-site', 'out'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--report')
    parser.add_argument('--memory-release')
    try:
        summary = build(**vars(parser.parse_args()))
        print(json.dumps({k: summary[k] for k in ('person', 'viewer', 'records', 'shards')}, ensure_ascii=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError):
        print('Relationship site build refused; check scope, hashes, paths and required configuration.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
