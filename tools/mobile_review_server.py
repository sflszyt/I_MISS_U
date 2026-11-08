"""仅 loopback 的私有评测 HTTP 服务；无静态目录或未鉴权运行开关。"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import re
import secrets
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

# Direct execution needs the repository root, including in the staging tree.
if not __package__:
    for _root in Path(__file__).resolve().parents:
        if (_root / 'tools' / 'build_mobile_review.py').is_file():
            sys.path.insert(0, str(_root))
            break

from tools.build_mobile_review import Package, checked_path, separate
from tools.mobile_review_auth import AccessAuth, AuthenticationError
from tools.mobile_review_store import Store, ReviewError, reject
if __package__:
    from . import memory_review
else:
    import memory_review


def validate_config(config, test=False):
    expected = {'package_dir','state_dir','host','port','public_origin','access_issuer','access_audience'}
    if not isinstance(config,dict) or not expected <= set(config) or set(config)-expected-{'batches','memory_batches'}:
        raise ValueError('invalid config keys')
    if config['host']!='127.0.0.1' or type(config['port']) is not int or not (0<=config['port']<=65535):
        raise ValueError('loopback required')
    if not test and config['port']!=8025:
        raise ValueError('production port must be 8025')
    for k in ('package_dir','state_dir'):
        if not isinstance(config[k],str) or not Path(config[k]).is_absolute():
            raise ValueError('absolute private directories required')
    batches = config.get('batches', {})
    if not isinstance(batches, dict):
        raise ValueError('invalid batches')
    directories = [checked_path(config['package_dir']), checked_path(config['state_dir'], True)]
    separate(directories[1], directories[:1])
    for key, entry in batches.items():
        if (not isinstance(key, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', key)
                or key == 'default' or not isinstance(entry, dict)
                or set(entry) != {'package_dir','state_dir','title'}
                or not isinstance(entry['title'], str) or not entry['title'].strip()
                or len(entry['title']) > 120 or any(ord(c) < 32 for c in entry['title'])):
            raise ValueError('invalid batch metadata')
        for field in ('package_dir','state_dir'):
            if not isinstance(entry[field], str) or not Path(entry[field]).is_absolute():
                raise ValueError('absolute private directories required')
            path = separate(entry[field], directories)
            directories.append(path)
    origin = urlsplit(config['public_origin'])
    if (origin.scheme not in (('http','https') if test else ('https',)) or not origin.hostname
            or origin.username or origin.password or origin.path or origin.query or origin.fragment):
        raise ValueError('invalid public origin')
    return origin.netloc


class ReviewServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False


def create_server(config, *, test_keys=None):
    host = validate_config(config,test_keys is not None)
    entries = {'default':dict(package_dir=config['package_dir'], state_dir=config['state_dir'], title='原有评测')}
    entries.update(config.get('batches', {}))
    packages, metadata = {}, {}
    # 先验证所有包和目录，失败时不可先创建旧/新状态。
    for key, entry in entries.items():
        package = Package(entry['package_dir'])
        packages[key] = package
        base = '/review/' if key == 'default' else '/review/batches/'+key+'/'
        metadata[key] = dict(id=key, title=entry['title'], base_path=base)
        if test_keys is not None:
            # 注入公钥只准用于完全人工生成、无源路径的隔离 fixture。
            if (package.manifest.get('synthetic') is not True or package.manifest['source_hashes']
                    or package.manifest['readonly_roots'] or 'people' in [p.casefold() for p in package.path.parts]
                    or 'people' in [p.casefold() for p in Path(entry['state_dir']).parts]):
                raise ValueError('test keys require isolated synthetic package')
        for task in package.tasks:
            for item in task['items']:
                for field in ('audio','audio_a','audio_b'):
                    if field in item and not re.fullmatch(re.escape(base)+r'audio/[0-9a-f]{32}\.wav', item[field]):
                        raise ValueError('package media namespace mismatch')
    protected = [root for p in packages.values() for root in (p.path, *p.manifest['readonly_roots'])]
    for entry in entries.values():
        separate(entry['state_dir'], protected)
    memory_pending = memory_review.prepare(config, protected + [e['state_dir'] for e in entries.values()], test_keys is not None)
    auth = AccessAuth(config['access_issuer'],config['access_audience'],test_keys=test_keys)
    stores = {key:Store(packages[key],entry['state_dir']) for key,entry in entries.items()}
    memory_stores = {k:memory_review.MemoryStore(*v) for k,v in memory_pending.items()}
    csrf_secret = secrets.token_bytes(32)
    static = {'/review/':('mobile_review_ui.html','text/html; charset=utf-8'),
              '/review/app.js':('mobile_review_ui.js','text/javascript; charset=utf-8'),
              '/review/app.css':('mobile_review_ui.css','text/css; charset=utf-8')}
    class Handler(BaseHTTPRequestHandler):
        server_version = 'Review'
        sys_version = ''

        def log_message(self,*args):
            # 默认请求日志会包含 URL 或私人字段；不记录客户端输入。
            pass

        def send_data(self,status,data,kind='application/json; charset=utf-8',extra=None):
            self.send_response(status)
            self.send_header('Content-Type',kind)
            self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'self'; style-src 'self'; media-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
            for k,v in (extra or {}).items():
                self.send_header(k,v)
            self.end_headers()
            if self.command!='HEAD':
                self.wfile.write(data)

        def json(self,status,value):
            self.send_data(status,json.dumps(value,ensure_ascii=False,allow_nan=False).encode('utf-8'))

        def one_header(self,key):
            values = self.headers.get_all(key,[])
            if len(values)!=1:
                return None
            return values[0]

        def dispatch(self):
            self.connection.settimeout(15)
            try:
                if self.one_header('Host')!=host:
                    reject('Host rejected','host_rejected',403)
                try:
                    identity = auth.authenticate(self.one_header('Cf-Access-Jwt-Assertion'))
                except AuthenticationError:
                    reject('Login required','authentication_required',401)
                path = self.path
                if '?' in path or '#' in path or '%' in path or '\\' in path or '..' in path or not path.startswith('/review/'):
                    reject('Not found','not_found',404)
                if path.startswith('/review/memory/'):
                    memory_review.dispatch(self,path,identity,memory_stores,csrf_secret,config)
                    return
                batch_id = 'default'
                if path.startswith('/review/batches/'):
                    match = re.match(r'/review/batches/([a-z0-9][a-z0-9-]{0,63})/', path)
                    if not match or match[1] not in stores or match[1] == 'default':
                        reject('Not found','not_found',404)
                    batch_id = match[1]
                    path = '/review/'+path[len(metadata[batch_id]['base_path']):]
                store, package = stores[batch_id], packages[batch_id]
                csrf = hmac.new(csrf_secret,(identity+'|'+metadata[batch_id]['base_path']+'|'+package.revision).encode(),hashlib.sha256).hexdigest()
                if self.command in ('POST','PUT'):
                    if self.one_header('Origin')!=config['public_origin'] or not hmac.compare_digest(self.one_header('X-Review-CSRF') or '',csrf):
                        reject('Origin or CSRF rejected','csrf_rejected',403)
                    if self.headers.get('Transfer-Encoding') is not None or self.one_header('Content-Type') not in ('application/json','application/json; charset=utf-8'):
                        reject()
                    length = self.one_header('Content-Length')
                    if not length or not re.fullmatch(r'[0-9]+',length):
                        reject()
                    length = int(length)
                    if length>256*1024:
                        reject('Body too large','body_too_large',413)
                    raw = self.rfile.read(length)
                    if len(raw)!=length:
                        reject()
                    def unique(pairs):
                        result = {}
                        for k,v in pairs:
                            if k in result:
                                raise ValueError('duplicate key')
                            result[k]=v
                        return result
                    try:
                        body = json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                    except (ValueError,UnicodeError):
                        reject()
                    match = re.fullmatch(r'/review/api/tasks/(ab|source|language)/(draft|submit)',path)
                    if not match or (match[2]=='draft' and self.command!='PUT') or (match[2]=='submit' and self.command!='POST'):
                        reject('Not found','not_found',404)
                    result = store.save(match[1],body,identity) if match[2]=='draft' else store.submit(match[1],body,identity)
                    self.json(200,result)
                    return
                if self.command not in ('GET','HEAD'):
                    reject('Not found','not_found',404)
                if path in static:
                    filename,kind=static[path]
                    self.send_data(200,(Path(__import__('tools.mobile_review_server',fromlist=['__file__']).__file__).parent/filename).read_bytes(),kind)
                elif path=='/review/api/session':
                    self.json(200,dict(store.session(),csrf_token=csrf,batch=metadata[batch_id],batches=list(metadata.values())))
                elif re.fullmatch(r'/review/api/receipts/[0-9a-f]{32}(/export)?',path):
                    parts=path.split('/')
                    self.json(200,store.receipt(parts[4],len(parts)==6))
                elif re.fullmatch(r'/review/audio/[0-9a-f]{32}\.wav',path):
                    package.verify()
                    key=path.rsplit('/',1)[1][:-4]
                    if key not in package.manifest['media']:
                        reject('Not found','not_found',404)
                    data=package.audio(key)
                    extra={'Accept-Ranges':'bytes'}
                    range_value=self.one_header('Range')
                    if range_value is not None:
                        match=re.fullmatch(r'bytes=(\d*)-(\d*)',range_value)
                        if not match or not any(match.groups()):
                            self.send_data(416,b'',extra={'Content-Range':f'bytes */{len(data)}'})
                            return
                        start,end=match.groups()
                        if start:
                            start=int(start);end=min(int(end),len(data)-1) if end else len(data)-1
                        else:
                            suffix=int(end);start=max(0,len(data)-suffix);end=len(data)-1
                        if start>end or start>=len(data):
                            self.send_data(416,b'',extra={'Content-Range':f'bytes */{len(data)}'})
                            return
                        extra['Content-Range']=f'bytes {start}-{end}/{len(data)}'
                        self.send_data(206,data[start:end+1],'audio/wav',extra)
                    else:
                        self.send_data(200,data,'audio/wav',extra)
                else:
                    reject('Not found','not_found',404)
            except ReviewError as error:
                self.json(error.status,{'error':{'code':error.code,'message':error.message}})
            except (ValueError,KeyError):
                self.json(409,{'error':{'code':'evidence_changed','message':'Evidence changed; contact the archive owner'}})
            except (OSError,Exception):
                # 不把异常路径、转写、凭据或 SQLite 内容发给浏览器。
                self.json(503,{'error':{'code':'storage_unavailable','message':'Not confirmed saved; retry the same request'}})

        do_GET=dispatch
        do_HEAD=dispatch
        do_POST=dispatch
        do_PUT=dispatch
        do_OPTIONS=dispatch
        do_DELETE=dispatch

    server=ReviewServer((config['host'],config['port']),Handler)
    server.store,server.auth=stores['default'],auth
    server.stores=stores
    server.memory_stores=memory_stores
    return server


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    args=parser.parse_args()
    config=json.loads(checked_path(args.config).read_text(encoding='utf-8-sig'))
    with create_server(config) as server:
        server.serve_forever()


if __name__=='__main__':
    main()
