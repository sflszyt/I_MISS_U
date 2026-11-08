"""Cloudflare Access RS256 验签；只访问配置固定的证书地址。"""
from __future__ import annotations

import json
import threading
import time
import urllib.request
from urllib.parse import urlsplit

import jwt


class AuthenticationError(Exception):
    pass


class AccessAuth:
    def __init__(self, issuer, audience, *, test_keys=None):
        parsed = urlsplit(issuer)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.path or parsed.query or parsed.fragment or parsed.port is not None):
            raise ValueError('issuer must be an HTTPS origin')
        if not isinstance(audience,str) or not audience.strip():
            raise ValueError('audience required')
        self.issuer,self.audience = issuer,audience
        self.url = issuer+'/cdn-cgi/access/certs'
        self.keys = dict(test_keys or {})
        self.test_keys = test_keys is not None
        self.expires = time.monotonic()+300 if self.test_keys else 0
        self.last_refresh = 0
        self.lock = threading.Lock()

    def refresh(self):
        # 不跟随重定向，避免配置之外的网络位置。
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):
                return None
        request = urllib.request.Request(self.url,headers={'Accept':'application/json'})
        with urllib.request.build_opener(NoRedirect).open(request,timeout=5) as response:
            raw = response.read(256*1024+1)
        if len(raw)>256*1024:
            raise AuthenticationError()
        rows = json.loads(raw)['keys']
        if not isinstance(rows,list) or not 1<=len(rows)<=16:
            raise AuthenticationError()
        keys = {}
        for row in rows:
            if row.get('kty') != 'RSA' or row.get('use','sig') != 'sig' or row.get('alg','RS256') != 'RS256':
                continue
            kid = row.get('kid')
            if not isinstance(kid,str) or not kid or len(kid)>200 or kid in keys:
                raise AuthenticationError()
            keys[kid] = jwt.PyJWK.from_dict(row,algorithm='RS256').key
        if not keys:
            raise AuthenticationError()
        self.keys,self.expires = keys,time.monotonic()+300

    def authenticate(self,token):
        try:
            if not isinstance(token,str) or not token or len(token)>16384:
                raise AuthenticationError()
            header = jwt.get_unverified_header(token)
            if (header.get('alg') != 'RS256' or any(k in header for k in ('jku','jwk','x5u','crit'))
                    or not isinstance(header.get('kid'),str) or len(header['kid'])>200):
                raise AuthenticationError()
            with self.lock:
                moment = time.monotonic()
                if not self.test_keys and (moment>=self.expires or header['kid'] not in self.keys):
                    if moment-self.last_refresh<30:
                        raise AuthenticationError()
                    self.last_refresh=moment
                    self.refresh()
                if header['kid'] not in self.keys or (not self.test_keys and moment>=self.expires):
                    raise AuthenticationError()
                key = self.keys[header['kid']]
            claims = jwt.decode(token,key,algorithms=['RS256'],audience=self.audience,issuer=self.issuer,
                                options={'require':['exp','iat','sub','iss','aud']})
            if (not isinstance(claims['sub'],str) or not claims['sub'] or len(claims['sub'])>512
                    or type(claims['exp']) not in (int,float) or type(claims['iat']) not in (int,float)
                    or claims['exp']<=claims['iat']):
                raise AuthenticationError()
            return claims['sub']
        except Exception:
            raise AuthenticationError() from None
