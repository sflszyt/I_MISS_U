"""Staged, isolated memory review. Never applies decisions to an archive."""
from __future__ import annotations

import copy
import hashlib
import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

from tools.build_mobile_review import checked_path, separate
from tools.viewpoint_manifest import digest, no_links
from tools.mobile_review_store import ReviewError, reject, exact, now, encode

ID = re.compile(r'[a-z0-9][a-z0-9-]{0,63}')
HEX = re.compile(r'[0-9a-f]{32}')
STATES = ('unset', 'confirm', 'correct', 'reject', 'defer')
TEXT_FIELDS = ('date','source_id','boundary','candidate','original_text','machine_asr',
               'verbatim_wu','mandarin_gloss','inference','speaker','language',
               'listening_status','asr_status','wu_status','gloss_status','text_review_status')


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate key')
        result[key] = value
    return result


def read_manifest(path):
    raw = checked_path(path).read_bytes()
    if len(raw) > 8*1024*1024:
        raise ValueError('oversized bundle')
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('constant')))


class Bundle:
    """All displayed evidence lives in one immutable, hash-bound bundle."""
    def __init__(self, path, batch_id):
        self.path = checked_path(path)
        self.manifest = read_manifest(self.path/'manifest.json')
        m = self.manifest
        if (set(m) != {'schema_version','batch_id','synthetic','items','media','revision'}
                or type(m['schema_version']) is not int or m['schema_version'] != 1
                or not isinstance(batch_id,str) or not ID.fullmatch(batch_id)
                or m['batch_id'] != batch_id or type(m['synthetic']) is not bool
                or not isinstance(m['items'],list) or not 1 <= len(m['items']) <= 2000
                or not isinstance(m['media'],dict)):
            raise ValueError('invalid memory bundle')
        self.batch_id, self.revision = batch_id, m['revision']
        if self.revision != digest({k:v for k,v in m.items() if k!='revision'}):
            raise ValueError('bundle revision mismatch')
        ids = set()
        for item in m['items']:
            if (not isinstance(item,dict) or set(item) != set(TEXT_FIELDS)|{'id','kind','audio'}
                    or not isinstance(item['id'],str) or not ID.fullmatch(item['id']) or item['id'] in ids
                    or item['kind'] not in ('memory','audio','missing-source')):
                raise ValueError('invalid memory item')
            ids.add(item['id'])
            if any(not isinstance(item[k],str) or len(item[k])>12000 for k in TEXT_FIELDS):
                raise ValueError('invalid evidence text')
            if any(not item[k].strip() for k in ('source_id','boundary','speaker','language','listening_status')):
                raise ValueError('missing evidence status')
            if any(item[k] not in ('unknown','unverified','verified','missing') for k in
                   ('listening_status','asr_status','wu_status','gloss_status','text_review_status')):
                raise ValueError('invalid evidence status')
            if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}',item['source_id']):
                raise ValueError('source id must be opaque, not a filesystem path')
            if item['audio'] is not None and (not isinstance(item['audio'],str)
                    or not HEX.fullmatch(item['audio']) or item['audio'] not in m['media']):
                raise ValueError('invalid media reference')
            if item['kind']=='audio' and item['audio'] is None:
                raise ValueError('audio item requires hash-bound media; use missing-source for absent media')
            if item['audio'] is None and item['listening_status']=='verified':
                raise ValueError('listening verification requires actual media')
            if item['kind']=='missing-source' and (item['audio'] is not None or item['listening_status']=='verified'):
                raise ValueError('missing source cannot be verified')
        for key, value in m['media'].items():
            if not HEX.fullmatch(key) or not isinstance(value,str) or not re.fullmatch('[0-9a-f]{64}',value):
                raise ValueError('invalid media allowlist')
        self.items = copy.deepcopy(m['items'])
        self.verify()

    def verify(self):
        if read_manifest(self.path/'manifest.json') != self.manifest:
            raise ValueError('bundle changed')
        for key in self.manifest['media']:
            self.audio(key)

    def audio(self, key):
        if key not in self.manifest['media']:
            reject('Not found','not_found',404)
        data = checked_path(self.path/'audio'/(key+'.wav')).read_bytes()
        if hashlib.sha256(data).hexdigest() != self.manifest['media'][key]:
            raise ValueError('media changed')
        return data


class MemoryStore:
    def __init__(self, bundle, state_dir):
        self.bundle = bundle
        self.root = separate(state_dir,[bundle.path])
        self.root.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS binding (revision TEXT PRIMARY KEY)')
            binding = db.execute('SELECT revision FROM binding').fetchall()
            if binding and binding != [(bundle.revision,)]:
                raise ValueError('state belongs to another evidence revision')
            db.execute('INSERT OR IGNORE INTO binding VALUES (?)',(bundle.revision,))
            db.execute('CREATE TABLE IF NOT EXISTS drafts (identity TEXT PRIMARY KEY, revision INTEGER NOT NULL, decisions TEXT NOT NULL, receipt TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS requests (identity TEXT, key TEXT, payload TEXT NOT NULL, result TEXT NOT NULL, PRIMARY KEY(identity,key))')

    @contextmanager
    def connect(self):
        checked_path(self.root, True)
        for suffix in ('','-journal','-wal','-shm'):
            path=self.root/('memory.sqlite3'+suffix)
            no_links(path)
            try:
                if path.stat().st_nlink != 1:
                    raise ValueError('linked state files are not allowed')
            except FileNotFoundError:
                pass
        db=sqlite3.connect(self.root/'memory.sqlite3',timeout=10)
        db.execute('PRAGMA synchronous=FULL')
        try:
            with db:
                yield db
        finally:
            db.close()

    def defaults(self):
        return {i['id']:dict(status='unset',correction='') for i in self.bundle.items}

    def row(self, db, identity):
        row=db.execute('SELECT revision,decisions,receipt FROM drafts WHERE identity=?',(identity,)).fetchone()
        return (row[0],json.loads(row[1]),json.loads(row[2]) if row[2] else None) if row else (0,self.defaults(),None)

    def session(self, identity):
        self.bundle.verify()
        with self.connect() as db:
            revision,decisions,receipt=self.row(db,identity)
        return dict(batch_id=self.bundle.batch_id,revision=self.bundle.revision,items=self.bundle.items,
                    draft_revision=revision,decisions=decisions,receipt=receipt)

    def validate(self, body, final):
        exact(body,('batch_id','revision','base_revision','request_id','decisions'))
        if body['batch_id']!=self.bundle.batch_id or body['revision']!=self.bundle.revision:
            reject('Evidence changed; reload','stale_evidence',409)
        if (type(body['base_revision']) is not int or body['base_revision']<0
                or not isinstance(body['request_id'],str) or not HEX.fullmatch(body['request_id'])):
            reject()
        exact(body['decisions'],self.defaults())
        for value in body['decisions'].values():
            exact(value,('status','correction'))
            if (not isinstance(value['status'],str) or value['status'] not in STATES
                    or not isinstance(value['correction'],str) or len(value['correction'])>4000
                    or (value['status']=='correct' and not value['correction'].strip())
                    or (value['status']!='correct' and value['correction']!='')):
                reject()
            if final and value['status']=='unset':
                reject('Choose a decision for every item','incomplete',422)

    def write(self, body, identity, final):
        self.bundle.verify()
        self.validate(body,final)
        payload=encode(dict(final=final,body=body))
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            previous=db.execute('SELECT payload,result FROM requests WHERE identity=? AND key=?',
                                (identity,body['request_id'])).fetchone()
            if previous:
                if previous[0]!=payload:reject('Request conflict','request_conflict',409)
                return json.loads(previous[1])
            revision,_,receipt=self.row(db,identity)
            if receipt:reject('Batch already submitted','already_submitted',409)
            if revision!=body['base_revision']:reject('Draft changed; reload','draft_conflict',409)
            decisions=body['decisions']
            result=dict(draft_revision=revision+1)
            if final:
                counts={s:sum(d['status']==s for d in decisions.values()) for s in STATES}
                evidence_unresolved=sum(i['kind']=='missing-source' or
                    ((i['kind']=='audio' or i['audio'] is not None) and i['listening_status']!='verified') for i in self.bundle.items)
                receipt=dict(id=uuid.uuid4().hex,batch_id=self.bundle.batch_id,revision=self.bundle.revision,
                    reviewer=identity,submitted_at=now(),counts=counts,decisions=decisions,
                    fully_confirmed=counts['confirm']+counts['correct']==len(decisions) and evidence_unresolved==0,
                    evidence_unresolved=evidence_unresolved,
                    decision_scope='candidate/transcript text only; never changes source or listening verification',
                    unresolved=counts['defer'],original_items=self.bundle.items,
                    disposition='review receipt only; no archive or training update')
                result=receipt
            db.execute('INSERT OR REPLACE INTO drafts VALUES (?,?,?,?)',
                       (identity,revision+1,encode(decisions),encode(receipt) if receipt else None))
            db.execute('INSERT INTO requests VALUES (?,?,?,?)',(identity,body['request_id'],payload,encode(result)))
        return result

    def receipt(self, receipt_id, identity):
        self.bundle.verify()
        with self.connect() as db:
            result=self.row(db,identity)[2]
        if not result or result['id']!=receipt_id:reject('Not found','not_found',404)
        return result


def prepare(config, protected, test):
    registry=config.get('memory_batches',{})
    if not isinstance(registry,dict):raise ValueError('invalid memory registry')
    pending={}
    paths=list(protected)
    for batch,entry in registry.items():
        if not isinstance(batch,str) or not ID.fullmatch(batch):raise ValueError('invalid batch id')
        if not isinstance(entry,dict) or set(entry)!={'package_dir','state_dir'}:raise ValueError('invalid registry entry')
        for field in ('package_dir','state_dir'):
            if not isinstance(entry[field],str) or not Path(entry[field]).is_absolute():raise ValueError('absolute directory required')
            paths.append(separate(entry[field],paths))
        bundle=Bundle(entry['package_dir'],batch)
        if test and (bundle.manifest['synthetic'] is not True or any('people' in [p.casefold() for p in Path(entry[f]).parts] for f in ('package_dir','state_dir'))):
            raise ValueError('test keys require synthetic memory bundle')
        pending[batch]=(bundle,entry['state_dir'])
    return pending


def dispatch(handler, path, identity, stores, secret, config):
    """Only entered after the existing server's Host and Access JWT checks."""
    import hmac
    match=re.fullmatch(r'/review/memory/([a-z0-9][a-z0-9-]{0,63})/(.*)',path)
    if not match or match[1] not in stores:reject('Not found','not_found',404)
    store=stores[match[1]]; tail=match[2]
    csrf=hmac.new(secret,(identity+'|'+path[:len(path)-len(tail)]+'|'+store.bundle.revision).encode(),hashlib.sha256).hexdigest()
    if handler.command in ('PUT','POST'):
        if handler.one_header('Origin')!=config['public_origin'] or not hmac.compare_digest(handler.one_header('X-Review-CSRF') or '',csrf):
            reject('Origin or CSRF rejected','csrf_rejected',403)
        if (handler.headers.get('Transfer-Encoding') is not None or
                handler.one_header('Content-Type') not in ('application/json','application/json; charset=utf-8')):reject()
        length=handler.one_header('Content-Length')
        if not length or not re.fullmatch('[0-9]+',length):reject()
        if int(length)>256*1024:reject('Body too large','body_too_large',413)
        raw=handler.rfile.read(int(length))
        if len(raw)!=int(length):reject()
        try:body=json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except (ValueError,UnicodeError):reject()
        if (handler.command,tail) not in (('PUT','api/draft'),('POST','api/submit')):reject('Not found','not_found',404)
        handler.json(200,store.write(body,identity,tail=='api/submit'));return
    if handler.command not in ('GET','HEAD'):reject('Not found','not_found',404)
    static={'':('html','text/html; charset=utf-8'),'app.js':('js','text/javascript; charset=utf-8'),'app.css':('css','text/css; charset=utf-8')}
    if tail in static:
        suffix,kind=static[tail]
        handler.send_data(200,(Path(__file__).parent/('memory_review_ui.'+suffix)).read_bytes(),kind)
    elif tail=='api/session':handler.json(200,dict(store.session(identity),csrf_token=csrf))
    elif re.fullmatch(r'api/receipts/[0-9a-f]{32}',tail):handler.json(200,store.receipt(tail.rsplit('/',1)[1],identity))
    elif re.fullmatch(r'audio/[0-9a-f]{32}\.wav',tail):
        store.bundle.verify();data=store.bundle.audio(tail[6:-4]);extra={'Accept-Ranges':'bytes'}
        r=handler.one_header('Range')
        if r is None:handler.send_data(200,data,'audio/wav',extra);return
        m=re.fullmatch(r'bytes=(\d*)-(\d*)',r)
        start=end=None
        if m and any(m.groups()):
            a,b=m.groups()
            start=int(a) if a else max(0,len(data)-int(b))
            end=min(int(b),len(data)-1) if a and b else len(data)-1
        if start is None or start>end or start>=len(data):
            handler.send_data(416,b'',extra={'Content-Range':f'bytes */{len(data)}'});return
        extra['Content-Range']=f'bytes {start}-{end}/{len(data)}'
        handler.send_data(206,data[start:end+1],'audio/wav',extra)
    else:reject('Not found','not_found',404)
