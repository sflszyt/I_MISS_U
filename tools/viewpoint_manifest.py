"""多视角私有注册表和显式数据集合同；仅使用标准库。"""
from __future__ import annotations

try:
    from .local_identity import owner_participant
except ImportError:
    from local_identity import owner_participant


import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import stat


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def slug(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z0-9_-]+', value):
        raise ValueError('invalid slug')
    if value.upper() in {'CON', 'PRN', 'AUX', 'NUL', *('COM'+str(i) for i in range(10)),
                         *('LPT'+str(i) for i in range(10))}:
        raise ValueError('reserved slug')
    return value


def no_links(path: Path):
    """拒绝符号链接和 Windows junction/reparse point，包括现存祖先。"""
    for part in [path, *path.parents]:
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('linked paths are not allowed')


def safe_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or '\\' in relative:
        raise ValueError('invalid relative path')
    parts = relative.split('/')
    if (PureWindowsPath(relative).drive or PurePosixPath(relative).is_absolute()
            or any(p in ('', '.', '..') or ':' in p or p.endswith((' ', '.')) for p in parts)):
        raise ValueError('unsafe relative path')
    path = root.joinpath(*parts)
    no_links(path)
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        raise ValueError('path escapes root') from None
    return path


def read_json(path: Path):
    no_links(path)
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        raise ValueError('invalid JSON input') from None


def read_jsonl(path: Path) -> list[dict]:
    no_links(path)
    try:
        rows = [json.loads(line) for line in path.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    except (OSError, ValueError):
        raise ValueError('invalid JSONL input') from None
    if any(not isinstance(r, dict) for r in rows):
        raise ValueError('JSONL records must be objects')
    return rows


def validate_registry(registry: dict) -> dict:
    if not isinstance(registry, dict) or type(registry.get('schema_version')) is not int or registry['schema_version'] != 1:
        raise ValueError('unsupported registry version')
    slug(registry.get('person'))
    participants = registry.get('participants')
    if not isinstance(participants, dict) or not {'mama', owner_participant(), 'father'} <= participants.keys():
        raise ValueError('missing participants')
    accounts = registry.get('accounts')
    if not isinstance(accounts, dict) or not accounts:
        raise ValueError('missing accounts')
    native = set()
    for alias, account in accounts.items():
        slug(alias)
        if (not isinstance(account, dict) or account.get('participant_id') not in participants
                or not isinstance(account.get('native_id'), str) or not account['native_id']
                or account['native_id'] in native):
            raise ValueError('invalid account mapping')
        native.add(account['native_id'])
    viewers = registry.get('viewers')
    if not isinstance(viewers, dict):
        raise ValueError('missing viewers')
    for viewer, participant in [('owner', owner_participant()), ('father', 'father')]:
        if viewers.get(viewer) != {'participant_id': participant, 'relationship_id': 'mama_' + participant}:
            raise ValueError('invalid viewer mapping')
    conversations = registry.get('conversations')
    if not isinstance(conversations, dict) or not conversations:
        raise ValueError('missing conversations')
    for cid, scene in conversations.items():
        if (not isinstance(cid, str) or not cid or not isinstance(scene, dict)
                or scene.get('kind') not in ('direct', 'group', 'unknown')
                or not isinstance(scene.get('participant_ids'), list)
                or any(p not in participants for p in scene['participant_ids'])):
            raise ValueError('invalid conversation mapping')
        if scene['kind'] == 'direct' and len(set(scene['participant_ids'])) != 2:
            raise ValueError('direct conversation requires two participants')
    return registry


def load_registry(path: Path) -> dict:
    return validate_registry(read_json(Path(path)))


def load_dataset(path: Path) -> tuple[dict, list[dict]]:
    path = Path(path)
    data = read_json(path)
    required = {'schema_version', 'person', 'viewpoint', 'source_batch_id', 'records_path',
                'records_sha256', 'media_manifest_path', 'media_manifest_sha256',
                'registry_path', 'registry_sha256', 'coverage_status', 'counts'}
    if not isinstance(data, dict) or not required <= data.keys() or type(data['schema_version']) is not int or data['schema_version'] != 1:
        raise ValueError('invalid dataset manifest')
    for key in ['person', 'viewpoint', 'source_batch_id']:
        slug(data[key])
    # manifest 固定位于 person/normalized/wechat/<viewpoint>/<batch>/dataset.json。
    if path.name != 'dataset.json' or path.parent.name != data['source_batch_id'] or path.parent.parent.name != data['viewpoint']:
        raise ValueError('dataset location mismatch')
    root = path.parents[4]
    if root.name != data['person'] or path.parents[2].name != 'wechat' or path.parents[3].name != 'normalized':
        raise ValueError('dataset person root mismatch')
    files = {}
    for prefix in ['records', 'media_manifest', 'registry']:
        f = safe_path(root, data[prefix + '_path'])
        if not re.fullmatch('[0-9a-f]{64}', str(data[prefix + '_sha256'])) or not f.is_file() or sha256(f) != data[prefix + '_sha256']:
            raise ValueError('dataset file hash mismatch')
        files[prefix] = f
    registry = load_registry(files['registry'])
    if registry['person'] != data['person']:
        raise ValueError('registry person mismatch')
    records = read_jsonl(files['records'])
    ids = set()
    checked_sources = {}
    native_people = {a['native_id']: a['participant_id'] for a in registry['accounts'].values()}
    for row in records:
        provenance = row.get('provenance', {})
        if (row.get('person') != data['person'] or row.get('viewpoint') != data['viewpoint']
                or row.get('source') != 'wechat' or row.get('record_type') != 'message'
                or row.get('tier') != 2 or not isinstance(row.get('record_id'), str)
                or row['record_id'] in ids or row.get('sender_person_id') not in registry['participants']
                or row.get('conversation_id') not in registry['conversations']
                or row.get('conversation_kind') != registry['conversations'][row['conversation_id']]['kind']
                or provenance.get('source_batch_id') != data['source_batch_id']
                or provenance.get('source_account_id') not in registry['accounts']):
            raise ValueError('invalid dataset record')
        sender = row['sender_person_id']
        scene = registry['conversations'][row['conversation_id']]
        expected_sender = 'subject' if sender == data['person'] else 'viewpoint_owner' if sender == data['viewpoint'] else sender
        if (native_people.get(row.get('sender_wxid')) != sender or row.get('sender') != expected_sender
                or sender not in scene['participant_ids']
                or registry['accounts'][provenance['source_account_id']]['participant_id'] != data['viewpoint']
                or row.get('participant_ids') != scene['participant_ids']
                or row.get('content_type') not in ('text', 'voice', 'image', 'video', 'file', 'sticker', 'link', 'location', 'system')
                or not isinstance(row.get('quality'), dict)):
            raise ValueError('record identity or scene mismatch')
        if scene['kind'] != 'direct' and ('addressee_ids' in row or 'relationship_id' in row):
            raise ValueError('unverified group relationship attribution')
        if scene['kind'] == 'direct':
            peers = set(scene['participant_ids']) - {data['person']}
            if (data['person'] not in scene['participant_ids'] or len(peers) != 1
                    or row.get('relationship_id') != data['person'] + '_' + next(iter(peers))
                    or row.get('addressee_ids') != [p for p in scene['participant_ids'] if p != sender]):
                raise ValueError('direct relationship or addressee mismatch')
        quality = row['quality']
        status = quality.get('export_status')
        if status not in ('existing_normalized', 'recovered_normalized', 'transport_content_withheld', 'empty_or_unparsed', 'unsupported_type'):
            raise ValueError('invalid export status')
        usable = status in ('existing_normalized', 'recovered_normalized') and row['content_type'] == 'text'
        if quality.get('usable_text') is not usable or (usable and not isinstance(row.get('text'), str)) or (not usable and 'text' in row):
            raise ValueError('content does not match export status and type')
        if row['content_type'] == 'voice' and (quality.get('speaker_status') != 'pending' or quality.get('transcript_status') != 'pending'):
            raise ValueError('imported voice must remain pending')
        if provenance.get('source_row') is None or not provenance.get('parser') or not provenance.get('parser_version') or not provenance.get('extracted_at'):
            raise ValueError('missing provenance fields')
        source = safe_path(root, provenance.get('source_file'))
        expected_hash = provenance.get('source_file_sha256')
        if not isinstance(expected_hash, str) or not re.fullmatch('[0-9a-f]{64}', expected_hash) or not source.is_file():
            raise ValueError('source evidence file or hash missing')
        if source not in checked_sources:
            checked_sources[source] = sha256(source)
        if checked_sources[source] != expected_hash:
            raise ValueError('source evidence hash mismatch')
        ids.add(row['record_id'])
    media = read_jsonl(files['media_manifest'])
    voices = {r['record_id']: r for r in records if r['content_type'] == 'voice'}
    media_ids = set()
    for item in media:
        record_id = item.get('record_id')
        if record_id not in voices or record_id in media_ids or not isinstance(item.get('representations'), list):
            raise ValueError('invalid media reference')
        parent = voices[record_id]
        if (item.get('person') != parent['person'] or item.get('viewpoint') != parent['viewpoint']
                or item.get('provenance') != parent['provenance']
                or item.get('speaker_id') != 'unknown' or item.get('speaker_status') != 'pending'
                or item.get('transcript_status') != 'pending' or item.get('training_eligible') is not False
                or item.get('source_kind') != 'recording_unverified'
                or item.get('missing') is not (not item['representations'])
                or parent['quality'].get('media_missing') is not item.get('missing')):
            raise ValueError('media scope or verification state mismatch')
        media_ids.add(record_id)
        for rep in item['representations']:
            f = safe_path(root, rep.get('path'))
            if not f.is_file() or sha256(f) != rep.get('sha256'):
                raise ValueError('media evidence hash mismatch')
    if media_ids != set(voices):
        raise ValueError('voice media correspondence incomplete')
    if not isinstance(data['counts'], dict) or data['counts'].get('records') != len(records) or data['counts'].get('media') != len(media):
        raise ValueError('dataset counts mismatch')
    if data['coverage_status'] not in ('partial', 'complete'):
        raise ValueError('invalid coverage status')
    return data, records
