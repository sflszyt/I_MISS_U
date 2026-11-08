"""SQLite 是提交事实来源；开放格式导出成功后才返回成功回执。"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path

try:
    from .build_mobile_review import separate, checked_path
    from .viewpoint_manifest import digest, no_links
except ImportError:
    from build_mobile_review import separate, checked_path
    from viewpoint_manifest import digest, no_links


class ReviewError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def reject(message='Invalid request', code='invalid_fields', status=422):
    raise ReviewError(status, code, message)


def exact(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        reject()


def string(value, limit):
    if not isinstance(value, str) or len(value) > limit:
        reject()


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00','Z')


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',',':'),allow_nan=False)


def default_values(task):
    values = {'position':0,'items':{}}
    if task['id'] == 'source':
        values['reviewer'] = ''
    for item in task['items']:
        if task['id'] == 'ab':
            state = dict(preference='unheard',note='',played_a=False,played_b=False)
        elif task['id'] == 'language':
            state = dict(language='unlabeled',note='')
        else:
            state = dict(text=item['text'],speaker=False,single=False,transcript=False,
                         transcript_confirmed_text=None,quality=False,duration=False,include=False,disposition='pending',note='')
        values['items'][item['id']] = state
    return values


def validate_values(task, values):
    exact(values, ['position','items']+(['reviewer'] if task['id']=='source' else []))
    if type(values['position']) is not int or not 0 <= values['position'] < len(task['items']):
        reject()
    if task['id']=='source':
        string(values['reviewer'],100)
    exact(values['items'],[i['id'] for i in task['items']])
    for item in task['items']:
        state = values['items'][item['id']]
        if task['id']=='ab':
            exact(state,('preference','note','played_a','played_b'))
            if state['preference'] not in ('unheard','A','B','same','neither'):
                reject()
            bools = ('played_a','played_b')
        elif task['id']=='language':
            exact(state,('language','note'))
            if state['language'] not in ('unlabeled','wu','mandarin','mixed','unknown'):
                reject()
            bools = ()
        else:
            exact(state,('text','speaker','single','transcript','transcript_confirmed_text','quality','duration','include','disposition','note'))
            string(state['text'],2000)
            bools = ('speaker','single','transcript','quality','duration','include')
            if state['disposition'] not in ('pending','review','exclude'):
                reject()
            if state['transcript']:
                if not state['text'].strip() or state['transcript_confirmed_text'] != state['text']:
                    reject('Transcript confirmation must match current text')
            elif state['transcript_confirmed_text'] is not None:
                reject()
            if state['include'] and state['disposition'] != 'review':
                reject('Included entries must be explicit reviews')
        string(state['note'],2000)
        if any(type(state[k]) is not bool for k in bools):
            reject()


class Store:
    def __init__(self, package, state_dir):
        self.package = package
        self.root = separate(state_dir,[package.path,*package.manifest['readonly_roots']])
        self.root.mkdir(parents=True,exist_ok=True)
        no_links(self.root/'state.sqlite3')
        self.lock = threading.RLock()
        self.tasks = {t['id']:t for t in package.tasks}
        # 派生界面任务，不改冻结包或原声核验决定。
        if 'source' in self.tasks:
            self.tasks['language'] = dict(id='language',title='语言标注',items=[
                {key:item[key] for key in ('id','number','audio','split')}
                for item in self.tasks['source']['items']])
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS drafts (task TEXT PRIMARY KEY, revision INTEGER NOT NULL, updated TEXT, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, response TEXT NOT NULL, receipt TEXT);
                CREATE TABLE IF NOT EXISTS receipts (id TEXT PRIMARY KEY, task TEXT NOT NULL, created TEXT NOT NULL, receipt TEXT NOT NULL, export TEXT NOT NULL, audit TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS latest (task TEXT PRIMARY KEY, receipt TEXT NOT NULL);
            ''')
            saved = db.execute("SELECT value FROM metadata WHERE key='package'").fetchone()
            if saved and saved[0] != package.revision:
                raise ValueError('state belongs to another package')
            db.execute("INSERT OR IGNORE INTO metadata VALUES ('package',?)",(package.revision,))
            for key,task in self.tasks.items():
                db.execute('INSERT OR IGNORE INTO drafts VALUES (?,0,NULL,?)',(key,encode(default_values(task))))

    @contextmanager
    def connect(self):
        no_links(self.root/'state.sqlite3')
        db = sqlite3.connect(self.root/'state.sqlite3',timeout=30)
        try:
            db.execute('PRAGMA synchronous=FULL')
            with db:
                yield db
        finally:
            db.close()

    def check(self, task, body, submit=False):
        if task not in self.tasks:
            reject('Not found','not_found',404)
        keys = ('package_revision','draft_revision','request_id','supersedes') if submit else ('package_revision','base_revision','request_id','values')
        exact(body,keys)
        try:
            if not isinstance(body['request_id'],str) or str(uuid.UUID(body['request_id'])) != body['request_id']:
                reject()
        except (ValueError,AttributeError):
            reject()
        rev = body['draft_revision' if submit else 'base_revision']
        if type(rev) is not int or rev < 0:
            reject()
        if body['package_revision'] != self.package.revision:
            reject('Package changed','package_conflict',409)
        self.package.verify()
        if submit:
            if body['supersedes'] is not None:
                string(body['supersedes'],100)
        else:
            validate_values(self.tasks[task],body['values'])

    def session(self):
        self.package.verify()
        with self.lock, self.connect() as db:
            drafts = {t:{'revision':r,'updated_at':u,'values':json.loads(v)} for t,r,u,v in db.execute('SELECT * FROM drafts')}
            latest = {t:None for t in self.tasks}
            for task,rid in db.execute('SELECT * FROM latest'):
                self.materialize(db,rid)
                latest[task] = json.loads(db.execute('SELECT receipt FROM receipts WHERE id=?',(rid,)).fetchone()[0])
            return dict(schema_version=1,package_revision=self.package.revision,tasks=copy.deepcopy(list(self.tasks.values())),drafts=drafts,latest_receipts=latest)

    def replay(self,db,request_id,fingerprint):
        row = db.execute('SELECT fingerprint,response,receipt FROM requests WHERE id=?',(request_id,)).fetchone()
        if not row:
            return None
        if row[0] != fingerprint:
            reject('Request ID already used','request_conflict',409)
        if row[2]:
            self.materialize(db,row[2])
        return json.loads(row[1])

    def save(self,task,body,identity):
        self.check(task,body)
        fingerprint = digest([task,'draft',body,identity])
        with self.lock, self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            replay = self.replay(db,body['request_id'],fingerprint)
            if replay is not None:
                return replay
            revision = db.execute('SELECT revision FROM drafts WHERE task=?',(task,)).fetchone()[0]
            if revision != body['base_revision']:
                reject('Draft changed on another device','revision_conflict',409)
            result = dict(revision=revision+1,updated_at=now(),values=body['values'])
            db.execute('UPDATE drafts SET revision=?,updated=?,value=? WHERE task=?',(result['revision'],result['updated_at'],encode(body['values']),task))
            db.execute('INSERT INTO requests VALUES (?,?,?,NULL)',(body['request_id'],fingerprint,encode(result)))
            return result

    def make_export(self,task,values,stamp):
        if task=='language':
            labels = []
            counts = dict(wu=0,mandarin=0,mixed=0,unknown=0,pending=0,labeled=0)
            for item in self.tasks[task]['items']:
                state = values['items'][item['id']]
                if state['language']=='unlabeled':
                    counts['pending'] += 1
                    continue
                candidate = self.package.manifest['candidates'][item['id']]
                labels.append(dict({key:candidate[key] for key in ('record_id','audio_sha256','revision','split')},
                                   language=state['language'],decided_at=stamp,note=state['note']))
                counts[state['language']] += 1
                counts['labeled'] += 1
            if not labels:
                reject('Make at least one explicit decision')
            return (dict(schema_version=1,decision_kind='source_language_annotation_only',training_approval=False,
                         package_revision=self.package.revision,exported_at=stamp,labels=labels),counts,[])
        if task=='ab':
            choices = [dict(group=item['number'],**values['items'][item['id']]) for item in self.tasks[task]['items']]
            judged = sum(c['preference']!='unheard' for c in choices)
            if not judged:
                reject('Make at least one explicit decision')
            return (dict(schema_version=1,study_id=self.package.manifest['study_id'],decision_kind='listening_preference_only',training_approval=False,generated_audio_tier=3,exported_at=stamp,choices=choices),
                    dict(judged=judged,unheard=len(choices)-judged),[])
        reviews,excluded = [],[]
        counts = dict(train=0,validation=0,pending=0,excluded=0)
        if not values['reviewer'].strip():
            reject('Reviewer is required')
        for item in self.tasks[task]['items']:
            s = values['items'][item['id']]
            c = self.package.manifest['candidates'][item['id']]
            if s['disposition']=='exclude':
                excluded.append(dict(record_id=c['record_id'],audio_sha256=c['audio_sha256'],revision=c['revision'],split=c['split'],note=s['note']))
                counts['excluded'] += 1
            elif (s['include'] and s['disposition']=='review' and s['speaker'] and s['single']
                  and s['transcript'] and s['transcript_confirmed_text']==s['text'] and s['quality']
                  and (not item['duration_requires_confirmation'] or s['duration'])):
                reviews.append(dict(record_id=c['record_id'],audio_sha256=c['audio_sha256'],revision=c['revision'],
                                    speaker_id=c['person'] if s['speaker'] else 'unknown',speaker_status='confirmed' if s['speaker'] else 'pending',
                                    single_speaker=s['single'],source_kind='real_recording' if s['single'] else 'recording_unverified',
                                    text=s['text'],transcript_status='corrected' if s['transcript'] else 'draft',
                                    quality_status='approved' if s['quality'] else 'pending',duration_approved=s['duration'],
                                    decided_by=values['reviewer'],decided_at=stamp))
                counts[c['split']] += 1
            else:
                counts['pending'] += 1
        if not reviews and not excluded:
            reject('Make at least one explicit decision')
        return dict(schema_version=1,reviews=reviews),counts,excluded

    def submit(self,task,body,identity):
        self.check(task,body,True)
        fingerprint = digest([task,'submit',body,identity])
        with self.lock:
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                replay = self.replay(db,body['request_id'],fingerprint)
                if replay is not None:
                    return replay
                revision,raw = db.execute('SELECT revision,value FROM drafts WHERE task=?',(task,)).fetchone()
                if revision != body['draft_revision']:
                    reject('Draft changed','revision_conflict',409)
                latest = db.execute('SELECT receipt FROM latest WHERE task=?',(task,)).fetchone()
                if body['supersedes'] != (latest[0] if latest else None):
                    reject('Explicit replacement required','supersedes_conflict',409)
                values = json.loads(raw)
                validate_values(self.tasks[task],values)
                stamp,rid = now(),uuid.uuid4().hex
                export,counts,excluded = self.make_export(task,values,stamp)
                audit = dict(package_revision=self.package.revision,draft_revision=revision,identity=identity,values=values,excluded=excluded,
                             splits={c['record_id']:c['split'] for c in self.package.manifest['candidates'].values()} if task=='source' else {})
                if task=='language':
                    # 与语言决定同一事务读取正式回执，绝不引用未提交草稿。
                    source = db.execute("SELECT r.id,r.receipt FROM latest l JOIN receipts r ON r.id=l.receipt WHERE l.task='source'").fetchone()
                    references = dict(source_review_receipt=source[0] if source else None,
                                      source_review_payload_sha256=json.loads(source[1])['payload_sha256'] if source else None)
                    export.update(references)
                    audit.update(references)
                receipt = dict(receipt_id=rid,task_id=task,submitted_at=stamp,counts=counts,payload_sha256=digest(export),supersedes=body['supersedes'])
                db.execute('INSERT INTO receipts VALUES (?,?,?,?,?,?)',(rid,task,stamp,encode(receipt),encode(export),encode(audit)))
                db.execute('INSERT OR REPLACE INTO latest VALUES (?,?)',(task,rid))
                db.execute('INSERT INTO requests VALUES (?,?,?,?)',(body['request_id'],fingerprint,encode(receipt),rid))
            # 事务先持久化。导出失败保留同一决定供原 request_id 恢复，不产生假成功。
            with self.connect() as db:
                self.materialize(db,rid)
            return receipt

    def write_immutable(self,path,content):
        checked_path(path,True)
        data = (content+'\n').encode('utf-8')
        if path.exists():
            if path.read_bytes() != data:
                raise OSError('immutable export mismatch')
            return
        path.parent.mkdir(parents=True,exist_ok=True)
        temporary = path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
        try:
            with temporary.open('xb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary,path)
        finally:
            if temporary.exists():
                temporary.unlink()

    def materialize(self,db,rid):
        row = db.execute('SELECT receipt,export,audit FROM receipts WHERE id=?',(rid,)).fetchone()
        if not row:
            reject('Not found','not_found',404)
        for folder,content in zip(('receipts','submissions','audit'),row):
            self.write_immutable(self.root/folder/(rid+'.json'),content)

    def receipt(self,rid,export=False):
        self.package.verify()
        with self.lock,self.connect() as db:
            self.materialize(db,rid)
            row = db.execute('SELECT receipt,export FROM receipts WHERE id=?',(rid,)).fetchone()
            return json.loads(row[1 if export else 0])
