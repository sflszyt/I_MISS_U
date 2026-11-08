"""校验 accepted 微信包，导入全新私有批次；不覆盖任何既有文件。"""
from __future__ import annotations

try:
    from .local_identity import owner_participant
except ImportError:
    from local_identity import owner_participant


import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys

try:
    from .viewpoint_manifest import (digest, load_dataset, load_registry, no_links,
        read_json, read_jsonl, safe_path, sha256, slug, validate_registry)
    from .parse_wechat import _content_type, _format_timestamp
except ImportError:
    from viewpoint_manifest import (digest, load_dataset, load_registry, no_links,
        read_json, read_jsonl, safe_path, sha256, slug, validate_registry)
    from parse_wechat import _content_type, _format_timestamp


def validate_package(source: Path) -> dict:
    no_links(source)
    manifest = read_json(source / 'package-manifest.json')
    if not isinstance(manifest, list) or not manifest:
        raise ValueError('invalid package manifest')
    entries = {}
    folded = set()
    for entry in manifest:
        if not isinstance(entry, dict) or set(entry) != {'path', 'bytes', 'sha256'}:
            raise ValueError('invalid package entry')
        relative = entry['path']
        path = safe_path(source, relative)
        if relative.casefold() in folded or relative.casefold() == 'package-manifest.json':
            raise ValueError('duplicate or self-referencing package entry')
        folded.add(relative.casefold())
        if (type(entry['bytes']) is not int or entry['bytes'] < 0 or not path.is_file()
                or path.stat().st_size != entry['bytes'] or sha256(path) != entry['sha256']):
            raise ValueError('package integrity mismatch')
        entries[relative] = entry
    actual = set()
    for path in source.rglob('*'):
        no_links(path)
        if path.is_file() and path != source / 'package-manifest.json':
            actual.add(path.relative_to(source).as_posix())
    if actual != set(entries):
        raise ValueError('package contains unlisted or missing files')
    return entries


def _one(values):
    if len(values) != 1 or not all(isinstance(v, str) and v for v in values):
        raise ValueError('ambiguous identity mapping')
    return next(iter(values))


def _registry(person, viewpoint, legacy, rows):
    if viewpoint != 'father' or person != 'mama':
        raise ValueError('automatic identity mapping supports mama/father only')
    if not legacy or any(r.get('person') != person or r.get('viewpoint') != owner_participant() for r in legacy):
        raise ValueError('invalid legacy identity evidence')
    mother = _one({r.get('sender_wxid') for r in legacy if r.get('sender') == 'subject'})
    son = _one({r.get('sender_wxid') for r in legacy if r.get('sender') == 'viewpoint_owner'})
    father = _one({r.get('sender_wxid') for _, r in rows if r.get('is_self') is True})
    voice_sender = _one({r.get('sender_wxid') for _, r in rows if r.get('voice_requested') is True})
    if mother != voice_sender or len({mother, son, father}) != 3:
        raise ValueError('identity cross-check failed')
    people = {mother: 'mama', son: owner_participant(), father: 'father'}
    registry = dict(schema_version=1, person=person, participants={p: {} for p in people.values()},
                    accounts={}, viewers={'owner': dict(participant_id=owner_participant(), relationship_id=('mama_' + owner_participant())),
                                          'father': dict(participant_id='father', relationship_id='mama_father')},
                    conversations={})
    for _, row in rows:
        native = row.get('sender_wxid')
        if not isinstance(native, str) or not native or type(row.get('is_self')) is not bool:
            raise ValueError('invalid sender identity evidence')
        if row['is_self'] != (native == father):
            raise ValueError('inconsistent account owner evidence')
        if native not in people:
            people[native] = 'unknown_' + digest(native)[:16]
            registry['participants'][people[native]] = {'identity_status': 'unknown'}
    for native, participant in people.items():
        registry['accounts']['wechat_' + participant] = dict(participant_id=participant, native_id=native)
    for _, row in rows:
        cid = row.get('conversation_id')
        kind = row.get('conversation_type')
        if not isinstance(cid, str) or not cid or kind not in ('direct', 'group') or row.get('is_group_chat') is not (kind == 'group'):
            raise ValueError('invalid conversation evidence')
        # 私聊只接受交叉核对过的妈妈与父亲，不能把其他私聊推断成夫妻。
        if kind == 'direct' and people[row['sender_wxid']] not in ('mama', 'father'):
            raise ValueError('unverified direct conversation participant')
        scene = registry['conversations'].setdefault(cid, dict(kind=kind, participant_ids=[]))
        if scene['kind'] != kind:
            raise ValueError('conflicting conversation kinds')
        if people[row['sender_wxid']] not in scene['participant_ids']:
            scene['participant_ids'].append(people[row['sender_wxid']])
    for scene in registry['conversations'].values():
        # 每个私聊必须独立具有双方发言证据，其他会话的妈妈身份不能补足本会话。
        if scene['kind'] == 'direct' and set(scene['participant_ids']) != {'mama', 'father'}:
            raise ValueError('insufficient direct conversation identity evidence')
        scene['participant_ids'].sort()
    return validate_registry(registry)


def _event_key(row):
    """仅强证据关联；缺原生消息或会话标识时不产生事件链接。"""
    native = row.get('provenance', {}).get('native_id')
    conversation = row.get('conversation_id')
    if not native or not conversation or row.get('content_type') != 'text' or 'text' not in row:
        return None
    return digest([str(native), conversation, row.get('sender_wxid'), row['content_type'], row['text']])


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')


def _jsonl_bytes(rows):
    return ''.join(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n' for r in rows).encode('utf-8')


def import_package(*, person: str, viewpoint: str, source: Path, legacy_uif: Path,
                   batch: str, repo_root: Path, registry: Path | None = None) -> Path:
    for value in (person, viewpoint, batch):
        slug(value)
    repo_root, source, legacy_uif = Path(repo_root).absolute(), Path(source).absolute(), Path(legacy_uif).absolute()
    no_links(repo_root)
    no_links(source)
    person_root = safe_path(repo_root, 'people/' + person)
    raw_relative = f'raw/wechat/{viewpoint}/{batch}'
    out_relative = f'normalized/wechat/{viewpoint}/{batch}'
    raw = safe_path(person_root, raw_relative)
    out = safe_path(person_root, out_relative)
    for target in (raw, out):
        if source.resolve() == target.resolve() or source.resolve() in target.resolve().parents or target.resolve() in source.resolve().parents:
            raise ValueError('source and destination overlap')
    entries = validate_package(source)
    summary = read_json(source / 'acceptance-summary.json')
    if summary.get('coverage_status') not in ('partial', 'complete'):
        raise ValueError('invalid package coverage')
    source_rows = []
    for relative in sorted(entries):
        parts = relative.split('/')
        if len(parts) == 3 and parts[0] == 'records' and parts[2] == 'messages.json':
            rows = read_json(safe_path(source, relative))
            if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
                raise ValueError('invalid source messages')
            source_rows.extend((relative, r) for r in rows)
    if not source_rows:
        raise ValueError('no explicitly listed messages')
    legacy = read_jsonl(legacy_uif)
    inferred = _registry(person, viewpoint, legacy, source_rows)
    if registry is not None:
        supplied = load_registry(Path(registry))
        if supplied != inferred:
            raise ValueError('explicit registry differs from verified identities')
    registry_path = safe_path(person_root, f'registry.{viewpoint}.{batch}.json')
    registry_bytes = _json_bytes(inferred)
    account_map = {v['native_id']: v['participant_id'] for v in inferred['accounts'].values()}
    extracted_at = datetime.now(timezone.utc).isoformat(timespec='seconds')
    records, media, quarantine, events = [], [], [], []
    seen = {}
    legacy_events = {}
    for row in legacy:
        event = _event_key(row)
        if event:
            legacy_events.setdefault(event, []).append(row['record_id'])
    for relative, row in source_rows:
        native = row.get('server_id')
        source_row = row.get('source_row')
        if source_row is None or isinstance(source_row, (dict, list, bool)):
            raise ValueError('missing stable source row')
        if native is not None and not isinstance(native, (str, int)):
            raise ValueError('invalid native ID')
        native = str(native) if native not in (None, '', 0, '0') else None
        cid = row['conversation_id']
        record_id = digest(['wechat', 'wechat_' + viewpoint, cid,
                            ['native', native] if native else ['fallback', entries[relative]['sha256'], source_row]])
        if record_id in seen:
            # 重复也不得被静默丢弃；同包重复 native key 必须上游明确处理。
            raise ValueError('duplicate native identity or conflicting record')
        seen[record_id] = True
        status = row.get('record_status')
        usable = status in ('existing_normalized', 'recovered_normalized')
        if status not in ('existing_normalized', 'recovered_normalized', 'transport_content_withheld', 'empty_or_unparsed', 'unsupported_type'):
            raise ValueError('unknown source record status')
        msg_type = row.get('msg_type')
        if type(msg_type) is not int:
            raise ValueError('invalid message type')
        sender = account_map[row['sender_wxid']]
        scene = inferred['conversations'][cid]
        provenance = dict(source_file=f'{raw_relative}/{relative}', parser='import_wechat_viewpoint',
                          parser_version='1.0.0', extracted_at=extracted_at,
                          source_account_id='wechat_' + viewpoint, source_batch_id=batch,
                          source_row=source_row, source_file_sha256=entries[relative]['sha256'])
        if native:
            provenance['native_id'] = native
        record = dict(record_id=record_id, record_type='message', person=person,
                      viewpoint=viewpoint, source='wechat', tier=2, lang='zh', provenance=provenance,
                      conversation_id=cid, conversation_kind=scene['kind'], participant_ids=scene['participant_ids'],
                      sender_person_id=sender, sender='subject' if sender == person else 'viewpoint_owner' if sender == viewpoint else sender,
                      sender_wxid=row['sender_wxid'], content_type=_content_type(msg_type),
                      quality=dict(export_status=status, usable_text=usable and msg_type == 1,
                                   media_status=row.get('media_status', [])))
        try:
            record['timestamp'] = _format_timestamp(float(row['ts']))
            record['timestamp_precision'] = 'exact'
        except (KeyError, ValueError, TypeError, OverflowError, OSError):
            record['timestamp'], record['timestamp_precision'] = None, 'unknown'
        if scene['kind'] == 'direct':
            record['addressee_ids'] = [p for p in scene['participant_ids'] if p != sender]
            record['relationship_id'] = 'mama_father'
        if usable and msg_type == 1:
            if not isinstance(row.get('content'), str):
                raise ValueError('invalid text content')
            record['text'] = row['content']
        if not usable or row.get('media_status'):
            quarantine.append(dict(record_id=record_id, provenance=provenance, record_status=status,
                                   media_status=row.get('media_status', [])))
        if msg_type == 34:
            representations = []
            if not isinstance(row.get('media', []), list):
                raise ValueError('invalid media list')
            for item in row.get('media', []):
                media_path = str(Path(relative).parent.as_posix()) + '/' + item.get('path', '')
                safe_path(source, media_path)
                if media_path not in entries:
                    raise ValueError('media absent from package manifest')
                evidence = entries[media_path]
                if item.get('sha256', evidence['sha256']) != evidence['sha256'] or item.get('bytes', evidence['bytes']) != evidence['bytes']:
                    raise ValueError('media metadata integrity mismatch')
                representations.append(dict(path=f'{raw_relative}/{media_path}', sha256=evidence['sha256'],
                    bytes=evidence['bytes'], format=item.get('format'), kind=item.get('kind'),
                    duration_check=item.get('duration_check'), duration_seconds=item.get('duration_seconds')))
            media.append(dict(record_id=record_id, person=person, viewpoint=viewpoint, provenance=provenance,
                              representations=representations, missing=not representations,
                              speaker_id='unknown', speaker_status='pending', transcript_status='pending',
                              source_kind='recording_unverified', training_eligible=False))
            record['quality'].update(speaker_status='pending', transcript_status='pending', media_missing=not representations)
        event = _event_key(record)
        if event:
            record['canonical_event_id'] = event
            if event in legacy_events:
                events.append(dict(canonical_event_id=event, record_ids=legacy_events[event] + [record_id]))
        records.append(record)
    request = dict(schema_version=1, person=person, viewpoint=viewpoint, source_batch_id=batch,
                   package_manifest_sha256=sha256(source / 'package-manifest.json'), legacy_uif_sha256=sha256(legacy_uif),
                   registry_sha256=digest(inferred))
    dataset_path = out / 'dataset.json'
    if raw.exists() or out.exists() or registry_path.exists():
        if not raw.is_dir() or not out.is_dir() or not registry_path.is_file():
            raise ValueError('incomplete or preexisting destination')
        validate_package(raw)
        prior = read_json(out / 'import_manifest.json')
        if prior.get('request') != request or registry_path.read_bytes() != registry_bytes:
            raise ValueError('existing batch differs; overwrite forbidden')
        if sha256(raw / 'package-manifest.json') != request['package_manifest_sha256']:
            raise ValueError('existing raw package differs')
        for name, expected in prior.get('outputs', {}).items():
            f = safe_path(out, name)
            if not f.is_file() or sha256(f) != expected:
                raise ValueError('existing output integrity mismatch')
        if set(prior.get('outputs', {})) != {'messages.uif.jsonl', 'media_manifest.jsonl', 'quarantine.jsonl', 'canonical_events.jsonl', 'dataset.json'}:
            raise ValueError('incomplete import manifest')
        load_dataset(dataset_path)
        return dataset_path
    # 所有输入及目标检查已通过。新目录以独占创建；失败保留现场，绝不删除 raw。
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.mkdir()
    for relative in ['package-manifest.json', *sorted(entries)]:
        target = safe_path(raw, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        with safe_path(source, relative).open('rb') as src, target.open('xb') as dst:
            shutil.copyfileobj(src, dst)
    validate_package(raw)
    if sha256(raw / 'package-manifest.json') != request['package_manifest_sha256']:
        raise ValueError('source changed during copy')
    out.mkdir(parents=True, exist_ok=False)
    with registry_path.open('xb') as stream:
        stream.write(registry_bytes)
    files = {'messages.uif.jsonl': _jsonl_bytes(records), 'media_manifest.jsonl': _jsonl_bytes(media),
             'quarantine.jsonl': _jsonl_bytes(quarantine), 'canonical_events.jsonl': _jsonl_bytes(events)}
    for name, data in files.items():
        with (out / name).open('xb') as stream:
            stream.write(data)
    dataset = dict(schema_version=1, person=person, viewpoint=viewpoint, source_batch_id=batch,
                   records_path=f'{out_relative}/messages.uif.jsonl', records_sha256=sha256(out / 'messages.uif.jsonl'),
                   media_manifest_path=f'{out_relative}/media_manifest.jsonl', media_manifest_sha256=sha256(out / 'media_manifest.jsonl'),
                   registry_path=registry_path.relative_to(person_root).as_posix(), registry_sha256=sha256(registry_path),
                   coverage_status=summary['coverage_status'], counts=dict(records=len(records), media=len(media), quarantined=len(quarantine)))
    with dataset_path.open('xb') as stream:
        stream.write(_json_bytes(dataset))
    receipt = dict(request=request, outputs={name: sha256(out / name) for name in [*files, 'dataset.json']})
    with (out / 'import_manifest.json').open('xb') as stream:
        stream.write(_json_bytes(receipt))
    load_dataset(dataset_path)
    return dataset_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['person', 'viewpoint', 'source', 'legacy-uif', 'batch']:
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--repo-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--registry', type=Path, help='Optional private registry, must match verified identities')
    args = parser.parse_args(argv)
    try:
        import_package(person=args.person, viewpoint=args.viewpoint, source=Path(args.source),
                       legacy_uif=Path(args.legacy_uif), batch=args.batch, repo_root=args.repo_root, registry=args.registry)
    except (ValueError, OSError, TypeError, KeyError):
        print('error: import validation or I/O failed; existing data was not overwritten', file=sys.stderr)
        return 1
    print('ok: dataset verified')
    return 0


if __name__ == '__main__':
    sys.exit(main())
