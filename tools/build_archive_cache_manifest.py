"""Content manifest for the explicitly opted-in father archive (never sessions)."""
import hashlib
import json
from pathlib import Path
import re

if __package__:
    from .viewpoint_manifest import safe_path, no_links, digest, slug
else:
    from viewpoint_manifest import safe_path, no_links, digest, slug


def cache_scope(scope):
    if not isinstance(scope, dict) or set(scope) - {'person', 'relationship_id', 'memory_release'}:
        raise ValueError('invalid archive scope')
    slug(scope.get('person'))
    if scope.get('relationship_id') != scope['person'] + '_father':
        raise ValueError('father scope required')
    binding = scope.get('memory_release')
    if binding is not None:
        if (not isinstance(binding, dict) or set(binding) != {'release_id', 'release_revision', 'source_sha256', 'card_revisions'}
                or not isinstance(binding['release_id'], str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', binding['release_id'])
                or not isinstance(binding['card_revisions'], dict) or not binding['card_revisions']):
            raise ValueError('invalid memory binding')
        for value in [binding['release_revision'], binding['source_sha256'], *binding['card_revisions'].values()]:
            if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
                raise ValueError('invalid binding digest')
    return dict(person=scope['person'], relationship_id=scope['relationship_id'], viewer='father', memory_release=binding)


def build_manifest(site_root, context_path, scope):
    """Read exact bytes from the allowlist and return a deterministic public pointer.

    This does not write files or discover material recursively. The release builder
    remains responsible for provenance/source validation before compiling this data.
    """
    root = Path(site_root)
    no_links(root)
    expected = cache_scope(scope)
    if not isinstance(context_path, str) or not re.fullmatch(r'data/chat_context[A-Za-z0-9_.-]*\.json', context_path):
        raise ValueError('invalid context path')
    snapshots = {}

    def read(name):
        path = safe_path(root, name)
        try:
            raw = path.read_bytes()
            obj = json.loads(raw.decode('utf-8'))
        except (OSError, UnicodeError, ValueError):
            raise ValueError('missing or invalid archive file') from None
        snapshots[name] = raw
        return obj

    def scoped(obj):
        if not isinstance(obj, dict) or any(obj.get(k) != expected[k] for k in ('person', 'relationship_id')):
            raise ValueError('archive scope mismatch')

    context = read(context_path)
    scoped(context)
    names = context.get('message_shards')
    if (context.get('viewer') != 'father' or context.get('language') != 'mandarin'
            or context.get('coverage_status') != 'partial' or not isinstance(context.get('system_prompt'), str)
            or not context['system_prompt'] or context.get('memory_release') != expected['memory_release']
            or not isinstance(names, list) or not names
            or any(not isinstance(n, str) or not re.fullmatch(r'messages-\d{4}\.json', n) for n in names)
            or len(names) != len(set(names))):
        raise ValueError('invalid scoped context')
    record_ids = set()
    for name in names:
        rows = read('data/' + name)
        if not isinstance(rows, list):
            raise ValueError('invalid shard')
        for row in rows:
            scoped(row)
            rid = row.get('record_id')
            if (not isinstance(rid, str) or not rid.strip() or rid in record_ids
                    or row.get('viewpoint') != 'father' or row.get('conversation_kind') != 'direct'
                    or row.get('content_type') != 'text' or type(row.get('tier')) is not int or row['tier'] != 2
                    or row.get('sender_person_id') not in (expected['person'], 'father')
                    or row.get('sender') != ('subject' if row.get('sender_person_id') == expected['person'] else 'viewpoint_owner')
                    or sorted(row.get('participant_ids', [])) != sorted([expected['person'], 'father'])
                    or row.get('provenance', {}).get('source_record_id') != rid):
                raise ValueError('invalid message scope')
            record_ids.add(rid)
    binding = expected['memory_release']
    memory_path = 'data/memories' + ('-' + binding['release_revision'] if binding else '') + '.json'
    for name in (memory_path, 'data/transcripts.json'):
        obj = read(name)
        scoped(obj)
        if not isinstance(obj.get('entries'), list):
            raise ValueError('invalid knowledge')
        if not binding or name.endswith('/transcripts.json'):
            if obj['entries']:
                raise ValueError('unbound knowledge')
        else:
            if (obj.get('schema_version') != 3 or any(obj.get(k) != binding[k] for k in ('release_id', 'release_revision', 'source_sha256'))
                    or len(obj['entries']) != len(binding['card_revisions'])):
                raise ValueError('memory binding mismatch')
            seen = set()
            for card in obj['entries']:
                scoped(card)
                cid = card.get('id')
                if (cid in seen or cid not in binding['card_revisions'] or card.get('tier') != 2
                        or card.get('evidence_revision') != binding['card_revisions'][cid]
                        or digest({k: v for k, v in card.items() if k != 'evidence_revision'}) != card['evidence_revision']):
                    raise ValueError('memory card mismatch')
                seen.add(cid)
    files = [dict(path=name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()) for name, raw in sorted(snapshots.items())]
    # Detect a changing build instead of returning a mixed-time snapshot.
    if any(safe_path(root, name).read_bytes() != raw for name, raw in snapshots.items()):
        raise ValueError('archive changed during manifest build')
    result = dict(schema_version=1, scope=expected, scope_revision=digest(expected),
                  context_path=context_path, files=files)
    return dict(result, revision=digest(result))
