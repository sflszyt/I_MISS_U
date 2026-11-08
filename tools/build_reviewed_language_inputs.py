"""只读消费正式语言快照；分语言准备索引不授予训练许可。"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import uuid
import wave
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

try:
    from .audit_voice_training_inputs import approved_inputs
    from .build_mobile_review import Package, checked_path, separate
    from .build_relationship_data import new_output, write_json, write_jsonl
    from .mobile_review_store import Store, validate_values
    from .viewpoint_manifest import digest, no_links, read_json, safe_path, sha256
except ImportError:
    from audit_voice_training_inputs import approved_inputs
    from build_mobile_review import Package, checked_path, separate
    from build_relationship_data import new_output, write_json, write_jsonl
    from mobile_review_store import Store, validate_values
    from viewpoint_manifest import digest, no_links, read_json, safe_path, sha256


def require(condition, message):
    if not condition:
        raise ValueError(message)


def hashes(paths):
    return {str(checked_path(p)):sha256(checked_path(p)) for p in sorted(set(paths), key=str)}


def files(root):
    result = []
    for path in root.rglob('*'):
        no_links(path)
        if path.is_file():
            result.append(path)
    return result


def ledger(state):
    """只读一致事务；草稿保存不改变本次消费的正式提交事实。"""
    path = checked_path(state/'state.sqlite3')
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, timeout=30)) as db:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        require(db.execute('PRAGMA integrity_check').fetchall() == [('ok',)], 'SQLite integrity failed')
        metadata = dict(db.execute('SELECT key,value FROM metadata'))
        latest = dict(db.execute('SELECT task,receipt FROM latest'))
        receipts = list(db.execute('SELECT id,task,created,receipt,export,audit FROM receipts ORDER BY id'))
        requests = list(db.execute('SELECT id,fingerprint,response,receipt FROM requests WHERE receipt IS NOT NULL ORDER BY id'))
        return dict(metadata=metadata, latest=latest, receipts=receipts, requests=requests)


def verify_receipts(package, state, snapshot):
    require(snapshot['metadata'].get('package') == package.revision, 'state package mismatch')
    tasks = {task['id']:task for task in package.tasks}
    tasks['language'] = dict(id='language', items=[
        {key:item[key] for key in ('id', 'number', 'audio', 'split')}
        for item in tasks['source']['items']])
    # make_export 是现有无 I/O 的纯投影；这里只传值对象，绝不初始化 Store。
    projection = SimpleNamespace(package=package, tasks=tasks)
    rows = {row[0]:row for row in snapshot['receipts']}
    requests = {}
    for request in snapshot['requests']:
        requests.setdefault(request[3], []).append(request)
    verified, paths = {}, []

    def visit(rid, task, visiting):
        require(isinstance(rid, str) and re.fullmatch('[0-9a-f]{32}', rid), 'invalid receipt ID')
        require(rid not in visiting, 'receipt chain cycle')
        require(rid in rows, 'broken receipt chain')
        row = rows[rid]
        require(row[1] == task, 'cross-task receipt chain')
        if rid in verified:
            return verified[rid]
        visiting = visiting | {rid}
        receipt, export, audit = [json.loads(raw) for raw in row[3:]]
        require(set(receipt) == {'receipt_id', 'task_id', 'submitted_at', 'counts', 'payload_sha256', 'supersedes'},
                'invalid receipt fields')
        require(receipt['receipt_id'] == rid and receipt['task_id'] == task and receipt['submitted_at'] == row[2],
                'receipt identity mismatch')
        require(isinstance(row[2], str) and bool(row[2]), 'missing submission time')
        require(receipt['payload_sha256'] == digest(export), 'payload digest mismatch')
        for folder, raw in zip(('receipts', 'submissions', 'audit'), row[3:]):
            path = checked_path(state/folder/(rid+'.json'))
            require(path.read_bytes() == (raw+'\n').encode('utf-8'), 'sidecar bytes mismatch')
            paths.append(path)
        audit_keys = {'package_revision', 'draft_revision', 'identity', 'values', 'excluded', 'splits'}
        if task == 'language':
            audit_keys |= {'source_review_receipt', 'source_review_payload_sha256'}
        require(set(audit) == audit_keys and audit['package_revision'] == package.revision, 'audit package/fields mismatch')
        require(type(audit['draft_revision']) is int and audit['draft_revision'] >= 0, 'invalid draft revision')
        require(isinstance(audit['identity'], str) and bool(audit['identity']), 'missing submit identity')
        validate_values(tasks[task], audit['values'])
        expected, counts, excluded = Store.make_export(projection, task, audit['values'], row[2])
        if task == 'language':
            reference = audit['source_review_receipt']
            if reference is None:
                require(audit['source_review_payload_sha256'] is None, 'invalid empty source reference')
            else:
                source_receipt, _, _ = visit(reference, 'source', visiting)
                require(audit['source_review_payload_sha256'] == source_receipt['payload_sha256'], 'source digest mismatch')
            expected.update({key:audit[key] for key in ('source_review_receipt', 'source_review_payload_sha256')})
        expected_splits = {c['record_id']:c['split'] for c in package.manifest['candidates'].values()} if task == 'source' else {}
        require(digest(export) == digest(expected) and digest(receipt['counts']) == digest(counts)
                and digest(audit['excluded']) == digest(excluded)
                and digest(audit['splits']) == digest(expected_splits), 'export differs from audited human values')
        formal = requests.get(rid, [])
        require(len(formal) == 1, 'missing or duplicate formal submit request')
        request_id, fingerprint, response, _ = formal[0]
        require(str(uuid.UUID(request_id)) == request_id, 'invalid request ID')
        body = dict(package_revision=package.revision, draft_revision=audit['draft_revision'],
                    request_id=request_id, supersedes=receipt['supersedes'])
        require(fingerprint == digest([task, 'submit', body, audit['identity']])
                and response == row[3], 'formal submit fingerprint/response mismatch')
        if receipt['supersedes'] is not None:
            previous, _, previous_audit = visit(receipt['supersedes'], task, visiting)
            require(previous['submitted_at'] <= receipt['submitted_at']
                    and previous_audit['draft_revision'] <= audit['draft_revision'], 'receipt chain order mismatch')
        verified[rid] = (receipt, export, audit)
        return verified[rid]

    current = {}
    for task in ('source', 'language'):
        require(task in snapshot['latest'], 'missing latest '+task+' receipt')
        current[task] = visit(snapshot['latest'][task], task, set())
        # latest 必须是该任务全部正式提交的唯一链头，不能回退到旧快照。
        chain, rid = set(), snapshot['latest'][task]
        while rid is not None:
            chain.add(rid)
            rid = verified[rid][0]['supersedes']
        require(chain == {row[0] for row in rows.values() if row[1] == task}, 'latest is not complete task chain')
    source, language = current['source'], current['language']
    require(language[1]['source_review_receipt'] == source[0]['receipt_id']
            and language[1]['source_review_payload_sha256'] == source[0]['payload_sha256'],
            'language must reference latest source; refresh language/reviewed build')
    return current, paths


def build(package_dir, state_dir, training_dir, split_plan, out):
    package = Package(package_dir)
    state, training, plan = [checked_path(p) for p in (state_dir, training_dir, split_plan)]
    snapshot = ledger(state)
    current, sidecars = verify_receipts(package, state, snapshot)
    summary = read_json(training/'summary.json')
    anchors = [checked_path(entry['path']) for entry in summary['inputs']]
    inputs = set(files(package.path) + files(training) + anchors + sidecars + [plan])
    inputs.update(checked_path(p) for p in package.manifest['source_hashes'])
    for root in package.manifest.get('source_inventories', {}):
        inputs.update(files(checked_path(root)))
    before = hashes(inputs)
    protected = [package.path, state, training, *package.manifest['readonly_roots'],
                 *(p.parent for p in anchors), *inputs]
    output = new_output(separate(out, protected), list(inputs))
    approved, proof_inputs = approved_inputs(training, plan)
    require(set(map(str, proof_inputs)) <= set(before), 'reviewed evidence not frozen by package/input inventory')
    overlays = []
    for path in anchors:
        if path.suffix.lower() == '.json':
            value = read_json(path)
            if isinstance(value, dict) and 'reviews' in value:
                overlays.append(value)
    require(len(overlays) == 1 and digest(overlays[0]) == digest(current['source'][1]),
            'reviewed build must anchor latest source export; refresh reviewed build')
    approved = {row['record_id']:row for row in approved}
    package_candidates = package.manifest['candidates']
    require(len({c['record_id'] for c in package_candidates.values()}) == len(package_candidates), 'duplicate package identity')
    source_items = next(task['items'] for task in package.tasks if task['id'] == 'source')
    require({item['id'] for item in source_items} == set(package_candidates), 'package source identity mismatch')
    labels = {row['record_id']:row for row in current['language'][1]['labels']}
    refs = dict(language_receipt=current['language'][0]['receipt_id'],
                language_payload_sha256=current['language'][0]['payload_sha256'],
                source_review_receipt=current['source'][0]['receipt_id'],
                source_review_payload_sha256=current['source'][0]['payload_sha256'])
    grouped = {(language, split):[] for language in ('wu', 'mandarin') for split in ('train', 'validation')}
    excluded = []
    for item in source_items:
        candidate = package_candidates[item['id']]
        rid = candidate['record_id']
        label = labels.get(rid)
        language = label['language'] if label else 'unlabeled'
        reasons = []
        if rid not in approved:
            reasons.append('not_source_approved')
        if language not in ('wu', 'mandarin'):
            reasons.append(language)
        evidence = dict({key:candidate[key] for key in ('record_id', 'audio_sha256', 'revision', 'split')},
                        item_number=item['number'], effective_language=language, language_annotation=label,
                        ready_for_training=False, **refs)
        if reasons:
            excluded.append(dict(evidence, exclusion_reasons=reasons))
            continue
        row = approved[rid]
        require(all(row[key] == candidate[key] for key in ('record_id', 'audio_sha256', 'revision', 'split')),
                'approved/package identity mismatch')
        audio = checked_path(safe_path(training, row['audio_file']))
        with wave.open(str(audio), 'rb') as stream:
            duration = stream.getnframes()*1000/stream.getframerate()
        grouped[language, row['split']].append(dict(row, **{**evidence, 'audio_file':str(audio), 'actual_duration_ms':duration}))
    report = dict(schema_version=1, package_revision=package.revision, **refs,
                  language_counts=current['language'][0]['counts'], total_items=len(source_items),
                  groups={language:{split:dict(count=len(grouped[language, split]),
                          duration_ms=sum(row['actual_duration_ms'] for row in grouped[language, split]))
                          for split in ('train', 'validation')} for language in ('wu', 'mandarin')},
                  excluded_count=len(excluded), pending=excluded, input_sha256=before,
                  formal_ledger_sha256=digest(snapshot), ready_for_training=False,
                  training_started=False, legacy_samples_added=0,
                  remaining_gates=['source_verification', 'independent_train_validation_features', 'training_configuration'],
                  source_gate_passed=False, waveform_comparison_rerun=False)

    def stable():
        package.verify()
        # 基线采集不是校验：sidecar 可能在首次核对后、首次 hash 前变化。
        verify_receipts(package, state, snapshot)
        require(hashes(inputs) == before and ledger(state) == snapshot, 'protected inputs or formal latest changed during build')

    stable()
    # 全部校验完成才创建新目录；report 最后发布，异常目录没有成功标记。
    output.mkdir(parents=True, exist_ok=False)
    for (language, split), rows in grouped.items():
        write_jsonl(output/language/(split+'.jsonl'), rows)
    write_jsonl(output/'excluded.jsonl', excluded)
    stable()
    try:
        write_json(output/'report.json', report)
        stable()
    except Exception:
        (output/'report.json').unlink(missing_ok=True)
        raise
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('package-dir', 'state-dir', 'training-dir', 'split-plan', 'out'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    build(args.package_dir, args.state_dir, args.training_dir, args.split_plan, args.out)
    print('Reviewed language preparation written; training remains disabled')


if __name__ == '__main__':
    main()
