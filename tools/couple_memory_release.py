"""Explicit, immutable batch adoption of source-derived Tier-2 relationship cards."""
import hashlib
import json
import re
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()


def text_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def require(ok):
    if not ok:
        raise ValueError('invalid or stale couple memory release')


def fields(value, names):
    require(isinstance(value, dict) and set(value) == set(names.split()))


def validate_release(packet, source_rows, source_sha256, person='mama', relationship_id='mama_father'):
    fields(packet, 'schema_version kind release_id person viewer relationship_id source_sha256 authorization cards release_revision')
    require(type(packet['schema_version']) is int and packet['schema_version'] == 1 and packet['kind'] == 'couple_memory_release')
    require(packet['person'] == person and packet['viewer'] == 'father' and packet['relationship_id'] == relationship_id)
    require(relationship_id == person + '_father')
    require(isinstance(packet['release_id'], str) and re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', packet['release_id']))
    require(isinstance(source_sha256, str) and re.fullmatch('[0-9a-f]{64}', source_sha256) and packet['source_sha256'] == source_sha256)
    require(packet['release_revision'] == digest({k:v for k,v in packet.items() if k != 'release_revision'}))
    auth = packet['authorization']
    fields(auth, 'mode source text content_sha256 individual_human_confirmed acoustic_listened')
    require(auth['mode'] == 'batch_adoption' and auth['individual_human_confirmed'] is False and auth['acoustic_listened'] is False)
    require(isinstance(auth['source'], str) and bool(auth['source'].strip()) and isinstance(auth['text'], str) and bool(auth['text'].strip()))
    require(auth['content_sha256'] == text_hash(auth['text']))
    public_auth = {k:v for k,v in auth.items() if k != 'text'}
    require(isinstance(source_rows, list))
    by_id = {r.get('record_id'):r for r in source_rows}
    require(len(by_id) == len(source_rows) and None not in by_id)
    cards = packet['cards']; require(isinstance(cards, list) and 0 < len(cards) <= 100)
    ids = set()
    for c in cards:
        fields(c, 'id title texts date person relationship_id tier release_id authorization provenance evidence_revision')
        require(isinstance(c['id'], str) and re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', c['id']) and c['id'] not in ids); ids.add(c['id'])
        require(c['person'] == person and c['relationship_id'] == relationship_id and c['tier'] == 2 and type(c['tier']) is int)
        require(c['release_id'] == packet['release_id'] and c['authorization'] == public_auth)
        require(c['authorization']['individual_human_confirmed'] is False and c['authorization']['acoustic_listened'] is False)
        require(isinstance(c['title'], str) and bool(c['title'].strip()) and len(c['title']) <= 100)
        require(isinstance(c['texts'], list) and len(c['texts']) == 1 and isinstance(c['texts'][0], str) and bool(c['texts'][0].strip()) and len(c['texts'][0]) <= 900)
        require(c['evidence_revision'] == digest({k:v for k,v in c.items() if k != 'evidence_revision'}))
        p = c['provenance']; fields(p, 'source_kind source_sha256 sources')
        require(p['source_kind'] == 'original_text' and p['source_sha256'] == source_sha256)
        require(isinstance(p['sources'], list) and 0 < len(p['sources']) <= 100)
        seen = set(); dates = []
        for ref in p['sources']:
            fields(ref, 'record_id timestamp speaker_id text_sha256')
            rid = ref['record_id']; require(isinstance(rid, str) and rid in by_id and rid not in seen); seen.add(rid)
            r = by_id[rid]
            require(r.get('person') == person and r.get('viewpoint') == 'father' and r.get('relationship_id') == relationship_id and r.get('tier') == 2)
            require(r.get('conversation_kind') == 'direct' and sorted(r.get('participant_ids', [])) == sorted([person, 'father']))
            require(r.get('content_type') == 'text' and r.get('sender_person_id') in (person, 'father') and r.get('sender') == ('subject' if r['sender_person_id'] == person else 'viewpoint_owner'))
            require(r.get('provenance', {}).get('source_record_id') == rid)
            require(isinstance(r.get('text'), str) and bool(r['text'].strip()))
            require(ref['timestamp'] == r.get('timestamp') and isinstance(ref['timestamp'], str) and re.match(r'^\d{4}-\d{2}-\d{2}T', ref['timestamp']))
            require(ref['speaker_id'] == r['sender_person_id'] and ref['text_sha256'] == text_hash(r['text']))
            dates.append(ref['timestamp'][:10])
        require(c['date'] == min(dates))
    return dict(schema_version=3, kind='memories', person=person, relationship_id=relationship_id,
                release_id=packet['release_id'], release_revision=packet['release_revision'], source_sha256=source_sha256, entries=cards)


def load_release(packet_path, source_rows, source_sha256, person='mama', relationship_id='mama_father'):
    return validate_release(json.loads(Path(packet_path).read_text(encoding='utf-8')), source_rows, source_sha256, person, relationship_id)


def runtime_binding(container):
    return {**{k:container[k] for k in ('release_id','release_revision','source_sha256')},
            'card_revisions':{c['id']:c['evidence_revision'] for c in container['entries']}}
