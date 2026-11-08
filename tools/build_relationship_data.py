"""显式多视角离线构建；完整本地档案与关系资料分开。"""
from __future__ import annotations

try:
    from .local_identity import owner_participant
except ImportError:
    from local_identity import owner_participant


import argparse
import copy
import html
import json
from collections import Counter
from pathlib import Path

try:
    from . import build_rhythm as rhythm
    from .viewpoint_manifest import load_dataset, read_json, read_jsonl, safe_path, sha256, slug, digest
    from .memory_evidence import guard_output, preflight_outputs, scope_candidate, dataset_fingerprint, decision_is_current
    from .extract_memory_candidates import extract_long_messages
    from .make_gate_page import render_page, build_card, initial_state_for
    from .extract_persona_digest import scoped_digest
    from .build_chat_context import scoped_context
    from .build_chat_knowledge import build_memories, build_transcript_entries
    from .merge_candidate_state import content_sig
    from .transcript_evidence import validate_verified_transcript, locate_source_row
except ImportError:
    import build_rhythm as rhythm
    from viewpoint_manifest import load_dataset, read_json, read_jsonl, safe_path, sha256, slug, digest
    from memory_evidence import guard_output, preflight_outputs, scope_candidate, dataset_fingerprint, decision_is_current
    from extract_memory_candidates import extract_long_messages
    from make_gate_page import render_page, build_card, initial_state_for
    from extract_persona_digest import scoped_digest
    from build_chat_context import scoped_context
    from build_chat_knowledge import build_memories, build_transcript_entries
    from merge_candidate_state import content_sig
    from transcript_evidence import validate_verified_transcript, locate_source_row


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')


def new_output(out, inputs):
    out = Path(out)
    guard_output(out)
    if out.exists():
        raise ValueError('output must be a new directory')
    # 守卫目录祖先本身，避免仅检查叶子而漏掉输入位于输出目录内。
    preflight_outputs([out], inputs)
    return out


def adapt_legacy(path, registry):
    path = Path(path)
    if (registry.get('schema_version') != 1 or registry.get('viewpoint') != owner_participant()
            or registry.get('source_sha256') != sha256(path)):
        raise ValueError('explicit frozen legacy mapping required')
    person = slug(registry.get('person'))
    batch = slug(registry.get('source_batch_id'))
    senders = registry.get('senders', {})
    scenes = registry.get('conversations', {})
    if not senders or not scenes:
        raise ValueError('empty legacy mapping')
    for value in senders.values():
        slug(value)
    rows = read_jsonl(path)
    ids = set()
    for source_index, row in enumerate(rows):
        if (row.get('person') != person or row.get('viewpoint') != owner_participant()
                or row.get('source') != 'wechat' or row.get('record_type') != 'message' or row.get('tier') != 2
                or not row.get('record_id') or row['record_id'] in ids
                or row.get('sender_wxid') not in senders or row.get('chat_room') not in scenes):
            raise ValueError('incomplete legacy identity mapping')
        ids.add(row['record_id'])
        scene = scenes[row['chat_room']]
        sender = senders[row['sender_wxid']]
        participants = scene.get('participant_ids', [])
        if (scene.get('kind') not in ('direct', 'group', 'unknown') or not participants
                or sender not in participants or len(participants) != len(set(participants))):
            raise ValueError('invalid legacy scene')
        slug(scene.get('conversation_id'))
        if scene['kind'] == 'direct' and set(participants) != {person, owner_participant()}:
            raise ValueError('legacy direct scene must be explicit mother/son dyad')
        row.update(sender_person_id=sender, conversation_id=scene['conversation_id'],
                   conversation_kind=scene['kind'], participant_ids=participants,
                   sender='subject' if sender == person else 'viewpoint_owner' if sender == owner_participant() else sender)
        row.pop('relationship_id', None)
        if scene['kind'] == 'direct':
            row['relationship_id'] = person + ('_' + owner_participant())
        row['provenance'] = dict(row.get('provenance', {}), source_batch_id=batch,
                                 legacy_source_sha256=registry['source_sha256'])
        row['quality'] = dict(row.get('quality', {}), usable_text=row.get('content_type') == 'text')
        row['source_order'] = source_index
        row['source_order_group'] = registry['source_sha256']
    return rows


def attach_source_order(records, root):
    """由已核验源文件中的数组位置恢复平局顺序，不用 record hash 排序。"""
    indexes = {}
    for row in records:
        prov = row['provenance']
        row['source_order'] = locate_source_row(row, root, indexes) - 1
        row['source_order_group'] = digest([prov['source_batch_id'], prov['source_file_sha256']])


def public_record(row):
    """只允许稳定匿名引用进入预览，不复制账号、源路径或导出账户映射。"""
    keys = ('record_id', 'person', 'viewpoint', 'source', 'record_type', 'tier', 'timestamp',
            'content_type', 'text', 'sender', 'sender_person_id', 'conversation_kind',
            'participant_ids', 'relationship_id', 'quality', 'duration_ms', 'source_order', 'source_order_group')
    out = {k: copy.deepcopy(row[k]) for k in keys if k in row}
    out['conversation_id'] = 'scene-' + digest(row.get('conversation_id', row.get('chat_room')))[:16]
    out['chat_room'] = out['conversation_id']
    out['provenance'] = {k: row.get('provenance', {})[k] for k in
                         ('source_batch_id', 'source_file_sha256', 'legacy_source_sha256')
                         if k in row.get('provenance', {})}
    out['provenance']['source_record_id'] = row['record_id']
    out.setdefault('relationship_id', None)
    return out


def render_records(title, records, links=()):
    """纯 HTML 分页，file:// 可用，不发出网络请求。"""
    nav = ' · '.join('<a href="%s">%s</a>' % (html.escape(p, quote=True), html.escape(t)) for p, t in links)
    cards = []
    for r in records:
        label = ' | '.join(str(r.get(k) or '未确定') for k in
                           ('timestamp', 'viewpoint', 'relationship_id', 'sender_person_id'))
        cards.append('<article><small>%s · Tier-%s · %s</small><p>%s</p></article>' %
                     (html.escape(label), html.escape(str(r.get('tier', 2))), html.escape(r['record_id']),
                      html.escape(r.get('text') or '[%s，待核验]' % r.get('content_type', 'media'))))
    return '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>%s</title><style>body{max-width:900px;margin:auto;padding:24px;font:16px sans-serif;background:#f4f0e9}article{background:white;padding:12px;margin:12px 0}small{color:#555}p{white-space:pre-wrap}</style><h1>%s</h1><nav>%s</nav>%s' % (html.escape(title), html.escape(title), nav, ''.join(cards))


def archive_pages(root, records, title, links=()):
    write_json(root / 'messages.json', records)
    pages = []
    for offset in range(0, len(records), 500):
        name = 'messages-%04d.html' % (offset // 500)
        pages.append((name, '%d–%d' % (offset + 1, min(offset + 500, len(records)))))
        (root / name).write_text(render_records(title, records[offset:offset+500], [('index.html', '索引')]), encoding='utf-8')
    (root / 'index.html').write_text(render_records(title, [], [*links, *pages]), encoding='utf-8')


def build(*, person, datasets, viewer, out, legacy_uif=None, legacy_registry=None, memory_candidates=None, language='mandarin', verified_transcripts=None):
    slug(person)
    if viewer not in ('owner', 'father') or not datasets:
        raise ValueError('explicit viewer and datasets required')
    if language not in ('wu', 'mandarin') or (viewer == 'father' and language != 'mandarin'):
        raise ValueError('invalid language; father must remain mandarin')
    if bool(legacy_uif) != bool(legacy_registry):
        raise ValueError('legacy input requires explicit registry')
    participant = owner_participant() if viewer == 'owner' else 'father'
    relationship = person + '_' + participant
    records, inputs, manifests = [], [], []
    source_anchors = {}
    for path in map(Path, datasets):
        manifest, rows = load_dataset(path)
        if manifest['person'] != person:
            raise ValueError('dataset person mismatch')
        root = path.parents[4]
        media_by_id = {r['record_id']:r for r in read_jsonl(safe_path(root, manifest['media_manifest_path']))}
        for row in rows:
            if row['record_id'] in media_by_id:
                source_anchors[row['record_id']] = (row, media_by_id[row['record_id']], root)
        attach_source_order(rows, root)
        registry = read_json(safe_path(root, manifest['registry_path']))
        if registry['viewers'][viewer]['relationship_id'] != relationship:
            raise ValueError('viewer registry mismatch')
        inputs.extend([path, root / manifest['records_path'], root / manifest['registry_path'], root / manifest['media_manifest_path']])
        records.extend(rows)
        manifests.append({'sha256': sha256(path), 'viewpoint': manifest['viewpoint'],
                          'source_batch_id': manifest['source_batch_id'], 'coverage_status': manifest['coverage_status']})
    if legacy_uif:
        mapping = read_json(Path(legacy_registry))
        if mapping.get('person') != person:
            raise ValueError('legacy person mismatch')
        records.extend(adapt_legacy(Path(legacy_uif), mapping))
        inputs.extend([Path(legacy_uif), Path(legacy_registry)])
    if len({r['record_id'] for r in records}) != len(records):
        raise ValueError('duplicate record IDs across inputs')
    selected = [public_record(r) for r in records if r.get('conversation_kind') == 'direct'
                and set(r.get('participant_ids', [])) == {person, participant}
                and r.get('relationship_id') == relationship and r['viewpoint'] == participant]
    if not selected:
        raise ValueError('no direct evidence for selected relationship')
    if memory_candidates:
        inputs.append(Path(memory_candidates))
    if verified_transcripts:
        inputs.append(Path(verified_transcripts))
    out = new_output(out, inputs)
    selected.sort(key=lambda r: (r['conversation_id'], r.get('timestamp') or '9999',
                                 r['source_order_group'], r['source_order']))
    texts = [r for r in selected if r.get('content_type') == 'text' and r.get('quality', {}).get('usable_text') and r.get('text')]
    subjects = [r for r in texts if r['sender_person_id'] == person]
    transcripts = []
    if verified_transcripts:
        selected_by_id = {r['record_id']:r for r in selected}
        raw_transcripts = read_jsonl(Path(verified_transcripts))
        if any(r.get('schema_version') != 2 for r in raw_transcripts):
            raise ValueError('explicit verified transcripts must use schema 2')
        if len({r.get('record_id') for r in raw_transcripts}) != len(raw_transcripts):
            raise ValueError('duplicate verified transcript IDs')
        source_cache = {}
        for transcript in raw_transcripts:
            anchor = source_anchors.get(transcript.get('record_id'))
            if anchor is None:
                raise ValueError('verified transcript has no selected dataset media anchor')
            parent, media, root = anchor
            validate_verified_transcript(transcript, parent=parent, media=media, root=root, source_cache=source_cache)
        for transcript in build_transcript_entries(raw_transcripts, 'voice'):
            parent = selected_by_id.get(transcript['record_id'])
            if parent is None:
                continue
            if (transcript.get('person') != person or transcript.get('relationship_id') != relationship
                    or transcript.get('viewpoint') != participant or parent['content_type'] != 'voice'
                    or transcript.get('provenance') != parent['provenance']
                    or not transcript.get('evidence_revision')):
                raise ValueError('verified transcript scope/source mismatch')
            transcripts.append(transcript)
    examples = []
    for index, row in enumerate(texts):
        if row['sender_person_id'] == person:
            context = [r for r in texts[max(0, index-3):index]
                       if r['conversation_id'] == row['conversation_id']
                       and r['source_order_group'] == row['source_order_group']
                       and rhythm.parse_timestamp(r.get('timestamp')) is not None
                       and rhythm.parse_timestamp(row.get('timestamp')) is not None]
            examples.append({'person':person, 'relationship_id':relationship, 'tier':2,
                             'target':row, 'context':context})
    skipped = Counter()
    stats = {'person':person, 'relationship_id':relationship, 'tier':2,
             'source_records':[r['record_id'] for r in selected],
             'totals':rhythm.compute_totals([r for r in selected if r['sender_person_id'] == person], skipped),
             'text_stats':rhythm.compute_text_stats(subjects, skipped),
             'time_pattern':rhythm.compute_time_pattern(subjects, skipped),
             'burst':rhythm.compute_burst(subjects, skipped),
             'reply_latency':rhythm.compute_reply_latency(selected, set(), skipped,
                                                        direct_rooms={r['chat_room'] for r in selected}),
             'punctuation_habits':rhythm.compute_punctuation(subjects, skipped),
             'catchphrases':rhythm.compute_catchphrases(subjects, skipped)}
    candidates = []
    by_id = {r['record_id']:r for r in texts}
    for candidate in extract_long_messages(texts, 1):
        candidate['kind_label'] = '文字记忆候选'
        candidate['title'] = candidate['title'].replace('长消息', '文字记忆候选', 1)
        evidence = [by_id[i] for i in candidate['provenance']['source_records']]
        candidates.append(scope_candidate(candidate, person, relationship, evidence))
    if memory_candidates:
        reviewed = read_jsonl(Path(memory_candidates))
        dataset_fingerprint(reviewed)
        by_candidate = {c['candidate_id']:c for c in candidates}
        for old in reviewed:
            current = by_candidate.get(old['candidate_id'])
            if (not current or old['person'] != person or old['relationship_id'] != relationship
                    or content_sig(old) != content_sig(current)):
                raise ValueError('memory evidence does not match this selected build')
            if decision_is_current(old):
                by_candidate[old['candidate_id']] = old
        candidates = list(by_candidate.values())
    manifest = {'schema_version':2, 'person':person, 'viewer':viewer, 'relationship_id':relationship,
                'language':language, 'coverage_status':'partial', 'datasets':manifests,
                'inputs':[{'path':str(p.resolve()), 'sha256':sha256(p)} for p in inputs],
                'selection_rule':'matching viewpoint + explicit direct dyad only; shared facts empty',
                'count_unit':'source observations, not deduplicated events',
                'counts':{'all':len(records), 'selected':len(selected), 'excluded':len(records)-len(selected),
                          'examples':len(examples), 'candidates':len(candidates), 'verified_transcripts':len(transcripts)},
                'shared_facts':[], 'relationship_path':'relationship'}
    out.mkdir(parents=True)
    write_json(out / 'build.json', manifest)
    relationship_dir = out / 'relationship'
    write_jsonl(relationship_dir / 'messages.jsonl', selected)
    write_jsonl(relationship_dir / 'examples.jsonl', examples)
    write_json(relationship_dir / 'rhythm.json', stats)
    write_json(relationship_dir / 'persona_digest.json', scoped_digest(texts, person, relationship))
    write_jsonl(relationship_dir / 'candidates.jsonl', candidates)
    write_json(relationship_dir / 'memories.json', dict(build_memories(candidates, person), relationship_id=relationship))
    write_json(relationship_dir / 'transcripts.json', dict(schema_version=2, person=person,
                                                         relationship_id=relationship, entries=transcripts))
    write_json(relationship_dir / 'scope.json', {k:v for k,v in manifest.items() if k != 'inputs'})
    context = scoped_context(manifest)
    write_json(relationship_dir / 'chat_context.json', context)
    (relationship_dir / 'persona.md').write_text('# 关系人格草案 · Tier-3\n\n尚未人工确认人格判断。请结合 examples.jsonl 和 rhythm.json 审阅；保留矛盾、争吵与负面记录，不自动归纳共同人格。\n', encoding='utf-8')
    if candidates:
        cards = [build_card(c, [], initial_state_for(c)) for c in candidates]
        (relationship_dir / 'gate.html').write_text(render_page(person, cards, dataset_fingerprint(candidates), len(cards)), encoding='utf-8')
    else:
        (relationship_dir / 'gate.html').write_text('<meta charset="utf-8">无文字记忆候选', encoding='utf-8')
    archive_pages(relationship_dir, selected, relationship + ' · partial',
                  [('gate.html','记忆人工闸门（新候选默认待确认）'), ('persona.md','人格草案 Tier-3'),
                   ('rhythm.json','关系节律'), ('persona_digest.json','带来源摘要'),
                   ('examples.jsonl','真实回复范例'), ('chat_context.json','范围声明')])
    all_public = [public_record(r) for r in records]
    source_links = []
    for viewpoint in sorted({r['viewpoint'] for r in records}):
        slug(viewpoint)
        subdir = 'source-' + viewpoint
        source_links.append((subdir + '/index.html', '来源 ' + viewpoint))
        archive_pages(out / 'local_archive' / subdir, [r for r in all_public if r['viewpoint'] == viewpoint], '来源 ' + viewpoint)
    archive_pages(out / 'local_archive', all_public, '完整本地档案 · 来源观察数（未去重事件）', source_links)
    (out / 'index.html').write_text(render_records('离线档案构建', [], [('local_archive/index.html','完整本地档案'),
        ('relationship/index.html','关系预览'), ('relationship/gate.html','记忆人工闸门'), ('training/review.html','声音核验（另行显式构建）')]), encoding='utf-8')
    manifest['relationship_files'] = {p.relative_to(relationship_dir).as_posix():sha256(p)
                                      for p in relationship_dir.rglob('*') if p.is_file()}
    write_json(out / 'build.json', manifest)
    return out


def package_relationship(manifest_path, out, person):
    """仅复制本次选中关系的显式清单，绝不回退根 persona/memories。"""
    import shutil
    manifest_path = Path(manifest_path)
    manifest = read_json(manifest_path)
    scoped_context(manifest)
    if manifest['person'] != person or manifest.get('relationship_path') != 'relationship':
        raise ValueError('invalid package scope')
    root = manifest_path.parent / 'relationship'
    files = manifest.get('relationship_files')
    if not isinstance(files, dict) or not files:
        raise ValueError('missing explicit relationship file manifest')
    allowed = {'messages.jsonl','examples.jsonl','rhythm.json','persona_digest.json','candidates.jsonl',
               'memories.json','transcripts.json','scope.json','chat_context.json','persona.md','gate.html','messages.json','index.html'}
    sources = []
    import re
    for name, expected in files.items():
        if name not in allowed and not re.fullmatch(r'messages-\d{4}\.html', name):
            raise ValueError('unexpected relationship package file')
        source = safe_path(root, name)
        if sha256(source) != expected:
            raise ValueError('relationship package hash mismatch')
        sources.append(source)
    out = new_output(out, [manifest_path, root, *sources])
    out.mkdir(parents=True)
    for source in sources:
        shutil.copyfile(source, out / source.name)
    write_json(out / 'package.json', {'person':person, 'viewer':manifest['viewer'],
               'relationship_id':manifest['relationship_id'], 'files':files})
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--person', required=True)
    parser.add_argument('--dataset', action='append', required=True)
    parser.add_argument('--viewer', choices=['owner','father'], required=True)
    parser.add_argument('--language', choices=['wu','mandarin'], default='mandarin', help='owner 可选；father 必须 mandarin')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--legacy-uif', type=Path)
    parser.add_argument('--legacy-registry', type=Path)
    parser.add_argument('--memory-candidates', type=Path, help='显式 v2 人工裁决候选；必须匹配当前证据')
    parser.add_argument('--verified-transcripts', type=Path, help='声音构建生成的 verified_transcripts.jsonl；仅选当前 direct 关系')
    args = vars(parser.parse_args())
    args['datasets'] = args.pop('dataset')
    build(**args)
    print('relationship build written')


if __name__ == '__main__':
    main()
