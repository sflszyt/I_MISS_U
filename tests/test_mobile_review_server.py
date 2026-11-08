import copy
import http.client
import json
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path

from tests.mobile_review_fixture import fixture,credentials,config

try:
    import jwt
    from tools.mobile_review_auth import AccessAuth,AuthenticationError
    from tools.mobile_review_server import create_server,validate_config
    JWT_AVAILABLE=True
except ImportError:
    JWT_AVAILABLE=False


@unittest.skipUnless(JWT_AVAILABLE,'PyJWT crypto unavailable; run mobile-review-venv')
class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);fixture(self.root)
        self.key,self.claims,self.token=credentials()
        self.config=config(self.root)
        self.server=create_server(self.config,test_keys={'synthetic-key':self.key.public_key()})
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown();self.server.server_close();self.thread.join()

    def request(self,path='/review/api/session',method='GET',body=None,headers=None,auth=True):
        h={'Host':'127.0.0.1:0'}
        if auth:h['Cf-Access-Jwt-Assertion']=self.token
        if body is not None:
            body=json.dumps(body).encode();h['Content-Type']='application/json'
        h.update(headers or {})
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=10)
        c.request(method,path,body,h);r=c.getresponse();raw=r.read();result=(r.status,dict(r.getheaders()),raw);c.close()
        return result

    def test_auth_required_every_route_and_fake_header(self):
        session=json.loads(self.request()[2]);audio=session['tasks'][0]['items'][0]['audio_a']
        for path in ('/review/','/review/app.js','/review/app.css','/review/api/session',audio):
            status,headers,body=self.request(path,headers={'Cf-Access-Authenticated-User-Email':'fake@example.invalid'},auth=False)
            self.assertEqual(status,401,path);self.assertEqual(json.loads(body)['error']['code'],'authentication_required')
        self.assertEqual(self.request(audio,method='HEAD',headers={'Range':'bytes=0-10'},auth=False)[0],401)
        self.assertEqual(self.request(headers={'Cf-Access-Jwt-Assertion':'fake'})[0],401)

    def test_jwt_claims_signature_and_header(self):
        auth=AccessAuth(self.config['access_issuer'],self.config['access_audience'],test_keys={'synthetic-key':self.key.public_key()})
        self.assertEqual(auth.authenticate(self.token),'synthetic-owner')
        for changes in ({'exp':int(time.time())-1},{'iss':'https://other.invalid'},{'aud':'wrong'},{'iat':int(time.time())+300},{'sub':''}):
            claims=dict(self.claims,**changes)
            token=jwt.encode(claims,self.key,algorithm='RS256',headers={'kid':'synthetic-key'})
            with self.assertRaises(AuthenticationError):auth.authenticate(token)
        for header in ({'kid':'unknown'},{'kid':'synthetic-key','jku':'https://attacker.invalid'}):
            token=jwt.encode(self.claims,self.key,algorithm='RS256',headers=header)
            with self.assertRaises(AuthenticationError):auth.authenticate(token)
        token=jwt.encode(self.claims,'not-a-real-secret-not-a-real-secret',algorithm='HS256',headers={'kid':'synthetic-key'})
        with self.assertRaises(AuthenticationError):auth.authenticate(token)
        other,_,_=credentials()
        token=jwt.encode(self.claims,other,algorithm='RS256',headers={'kid':'synthetic-key'})
        with self.assertRaises(AuthenticationError):auth.authenticate(token)

    def test_host_origin_csrf_and_strict_json(self):
        session=json.loads(self.request()[2]);body=dict(package_revision=session['package_revision'],base_revision=0,request_id=str(uuid.uuid4()),values=session['drafts']['ab']['values'])
        url='/review/api/tasks/ab/draft'
        self.assertEqual(self.request(headers={'Host':'evil.invalid'})[0],403)
        self.assertEqual(self.request(url,'PUT',body)[0],403)
        h={'Origin':self.config['public_origin'],'X-Review-CSRF':session['csrf_token']}
        self.assertEqual(self.request(url,'PUT',body,dict(h,Origin='https://evil.invalid'))[0],403)
        self.assertEqual(self.request(url,'PUT',body,h)[0],200)
        body['values']['extra']='unknown';body['request_id']=str(uuid.uuid4());body['base_revision']=1
        self.assertEqual(self.request(url,'PUT',body,h)[0],422)
        body['values']['extra']='a'*(256*1024)
        self.assertEqual(self.request(url,'PUT',body,h)[0],413)

    def test_no_leak_paths_and_ranges(self):
        status,headers,raw=self.request();self.assertEqual(status,200);self.assertEqual(headers['Cache-Control'],'no-store')
        for name in ('condition','record_id','source_take','experiment_path','source_hashes'):
            self.assertNotIn(name,raw.decode())
        for path in ('/review/manifest.json','/review/answer-key.json','/review/../state','/review/%2e%2e/state','/review/audio/','/review/api/receipts/'+('0'*32)):
            self.assertEqual(self.request(path)[0],404,path)
        audio=json.loads(raw)['tasks'][0]['items'][0]['audio_a']
        status,h,b=self.request(audio,headers={'Range':'bytes=0-43'})
        self.assertEqual(status,206);self.assertEqual(len(b),44);self.assertEqual(b[:4],b'RIFF')
        self.assertEqual(self.request(audio,headers={'Range':'bytes=0-1,5-9'})[0],416)
        self.assertEqual(self.request(audio,method='HEAD')[2],b'')

    def test_real_package_cannot_use_test_keys(self):
        path=self.root/'package'/'manifest.json'
        data=json.loads(path.read_text(encoding='utf-8'));data['synthetic']=False
        from tools.viewpoint_manifest import digest
        data['package_revision']=digest({k:v for k,v in data.items() if k!='package_revision'})
        path.write_text(json.dumps(data),encoding='utf-8')
        with self.assertRaises(ValueError):create_server(self.config,test_keys={'synthetic-key':self.key.public_key()})
        with self.assertRaises(ValueError):validate_config(self.config)


if __name__=='__main__':unittest.main()
