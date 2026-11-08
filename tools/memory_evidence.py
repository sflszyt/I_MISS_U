"""记忆候选的范围、完整证据版本与人工决定合同。"""
from __future__ import annotations

try:
    from .local_identity import owner_participant
except ImportError:
    from local_identity import owner_participant


import copy
import hashlib
import json
import re
from pathlib import Path

SEMANTIC_FIELDS = ('kind', 'kind_label', 'date', 'chat_room', 'group', 'title',
                   'excerpts', 'counts', 'tier', 'user_title', 'user_note', 'has_asr_draft')
DECISION_FIELDS = ('status', 'decided_at', 'decided_by', 'decision', 'user_title', 'user_note')


def guard_output(path):
    """拒绝任何人的 raw 路径与链接祖先，大小写和 .. 经规范化处理。"""
    try:
        from .viewpoint_manifest import no_links
    except ImportError:
        from viewpoint_manifest import no_links
    path = Path(path)
    no_links(path)
    parts = [part.casefold() for part in path.resolve().parts]
    if any(parts[i] == 'people' and parts[i+2] == 'raw' for i in range(len(parts)-2)):
        raise ValueError('raw output is forbidden')


def preflight_outputs(outputs, readonly_inputs, *, inplace_inputs=()):
    """首次写入前核验文件目标、祖先与输入别名；只允许明确的原地更新。"""
    try:
        from .viewpoint_manifest import no_links
    except ImportError:
        from viewpoint_manifest import no_links

    outputs = [Path(p) for p in outputs]
    readonly_inputs = [Path(p) for p in readonly_inputs if p is not None]
    inplace_inputs = [Path(p) for p in inplace_inputs]

    def key(path):
        return tuple(part.casefold() for part in path.resolve().parts)

    def overlap(a, b):
        ka, kb = key(a), key(b)
        if ka[:len(kb)] == kb or kb[:len(ka)] == ka:
            return True
        return a.exists() and b.exists() and a.samefile(b)

    for path in readonly_inputs + inplace_inputs:
        no_links(path)
    for index, output in enumerate(outputs):
        guard_output(output)
        if output.exists() and not output.is_file():
            raise ValueError('output must be a file')
        if any(parent.exists() and not parent.is_dir() for parent in output.parents):
            raise ValueError('output has a file ancestor')
        if any(overlap(output, other) for other in outputs[:index]):
            raise ValueError('outputs overlap')
        if any(overlap(output, source) for source in readonly_inputs):
            raise ValueError('output overlaps read-only input')
        for source in inplace_inputs:
            if overlap(output, source) and key(output) != key(source):
                raise ValueError('in-place input permits only exact output path')


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def stable_evidence(value):
    if isinstance(value, dict):
        return {k: stable_evidence(v) for k, v in value.items()
                if k not in ('generated_at', 'extracted_at')}
    if isinstance(value, list):
        return [stable_evidence(v) for v in value]
    return value


def evidence_revision(candidate):
    return digest({'schema_version': 2, 'person': candidate['person'],
                   'relationship_id': candidate['relationship_id'],
                   'source_records': stable_evidence(candidate['evidence_records']),
                   'content': {k: candidate[k] for k in SEMANTIC_FIELDS if k in candidate}})


def scope_candidate(candidate: dict, person: str, relationship_id: str,
                    source_records: list[dict]) -> dict:
    """返回新 v2 pending 候选；保留全部原始证据，不沿用输入裁决。"""
    if not isinstance(person, str) or not re.fullmatch(r'[a-z0-9_-]+', person):
        raise ValueError('invalid person')
    if relationship_id not in (person + ('_' + owner_participant()), person + '_father'):
        raise ValueError('unsupported relationship')
    viewpoint = relationship_id[len(person) + 1:]
    if not source_records or any(not isinstance(r, dict) for r in source_records):
        raise ValueError('complete source records required')
    ids = [r.get('record_id') for r in source_records]
    if any(not isinstance(r, str) or not r for r in ids) or len(set(ids)) != len(ids):
        raise ValueError('invalid or duplicate source ID')
    for record in source_records:
        if record.get('person') != person or record.get('viewpoint') != viewpoint:
            raise ValueError('source scope mismatch')
    declared = candidate.get('provenance', {}).get('source_records', [])
    if declared and set(declared) != set(ids):
        raise ValueError('incomplete source evidence')
    out = copy.deepcopy(candidate)
    for field in (*DECISION_FIELDS, 'previous_versions', 'carried_forward', 'content_changed'):
        out.pop(field, None)
    out.update(schema_version=2, person=person, relationship_id=relationship_id,
               status='pending', evidence_records=sorted(copy.deepcopy(source_records),
                                                        key=lambda r: r['record_id']))
    out.setdefault('provenance', {})['source_records'] = sorted(ids)
    out['candidate_id'] = digest([2, person, relationship_id, out['kind'], out.get('group'), sorted(ids)])
    out['evidence_revision'] = evidence_revision(out)
    return out


def validate_candidate(candidate):
    if not isinstance(candidate, dict):
        raise ValueError('candidate must be an object')
    if type(candidate.get('schema_version')) is not int or candidate['schema_version'] != 2:
        raise ValueError('expected candidate schema 2')
    rebuilt = scope_candidate(candidate, candidate.get('person'), candidate.get('relationship_id'),
                              candidate.get('evidence_records'))
    if rebuilt['candidate_id'] != candidate.get('candidate_id'):
        raise ValueError('candidate identity mismatch')
    if evidence_revision(candidate) != candidate.get('evidence_revision'):
        raise ValueError('candidate evidence revision mismatch')


def dataset_fingerprint(candidates: list[dict], *, legacy=False) -> str:
    ids = [c.get('candidate_id') for c in candidates]
    if any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
        raise ValueError('invalid or duplicate candidate ID')
    if legacy:
        if any(c.get('schema_version', 1) != 1 for c in candidates):
            raise ValueError('legacy/v2 mixture')
        return hashlib.md5('\n'.join(sorted(ids)).encode('utf-8')).hexdigest()[:12]
    for candidate in candidates:
        validate_candidate(candidate)
    scopes = {(c['person'], c['relationship_id']) for c in candidates}
    if len(scopes) != 1:
        raise ValueError('one nonempty dataset scope required')
    return digest([2, sorted(scopes), sorted((c['candidate_id'], c['evidence_revision'])
                                            for c in candidates)])


def validate_legacy_freeze(candidates, raw_bytes, freeze_path, person, relationship_id):
    """冻结文件必须由操作者显式提供；本工具不自动登记或确认旧数据。"""
    if not freeze_path or relationship_id != person + ('_' + owner_participant()):
        raise ValueError('explicit legacy freeze and original relationship required')
    freeze = json.loads(Path(freeze_path).read_text(encoding='utf-8'))
    expected = {'schema_version': 1, 'person': person, 'relationship_id': relationship_id,
                'source_sha256': hashlib.sha256(raw_bytes).hexdigest(),
                'source_dataset': dataset_fingerprint(candidates, legacy=True)}
    if any(freeze.get(k) != v for k, v in expected.items()):
        raise ValueError('legacy freeze mismatch')
    return expected['source_dataset']


def decision_is_current(candidate):
    decision = candidate.get('decision', {})
    return (candidate.get('status') in ('confirmed', 'rejected')
            and decision.get('evidence_revision') == candidate.get('evidence_revision')
            and decision.get('person') == candidate.get('person')
            and decision.get('relationship_id') == candidate.get('relationship_id')
            and decision.get('action') == ('confirm' if candidate.get('status') == 'confirmed' else 'reject')
            and bool(decision.get('decided_by')) and bool(decision.get('decided_at')))
