import contextlib, io, json, threading, unittest, urllib.request, urllib.error
from types import SimpleNamespace
from tools.llm_proxy import ProxyConfig, ProxyHandler, ProxyServer
class CorrelationTests(unittest.TestCase):
    def test_early_auth_is_correlated_and_untrusted_metadata_is_not_reflected(self):
        args=SimpleNamespace(rpm=10,daily=20,log_dir='',model='synthetic',max_tokens=100,upstream='http://127.0.0.1:1',timeout=1)
        for supplied in ['a'*32, '<script>SECRET_CANARY</script>', 'a'*1000]:
            with self.subTest(supplied=supplied[:32]):
                finished=threading.Event()
                class CompletedHandler(ProxyHandler):
                    def do_POST(self):
                        try:super().do_POST()
                        finally:finished.set()
                server=ProxyServer(('127.0.0.1',0),CompletedHandler,ProxyConfig(args,{'synthetic_token':'owner'},'SECRET_KEY'))
                worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
                logs=io.StringIO()
                try:
                    with contextlib.redirect_stderr(logs):
                        req=urllib.request.Request('http://127.0.0.1:%d/v1/chat/completions'%server.server_port,data=b'{}',headers={'X-Request-ID':supplied,'CF-Ray':'BAD_SECRET_CANARY'})
                        with self.assertRaises(urllib.error.HTTPError) as cm: urllib.request.urlopen(req)
                        cm.exception.read()
                        self.assertTrue(finished.wait(2))
                        rid=cm.exception.headers.get('X-Request-ID')
                    self.assertRegex(rid or '',r'^[a-f0-9]{32}$')
                    if supplied=='a'*32:self.assertEqual(rid,supplied)
                    self.assertIn('request_received',logs.getvalue());self.assertIn('downstream_complete',logs.getvalue())
                    self.assertIn('"status":401',logs.getvalue());self.assertNotIn('SECRET',logs.getvalue())
                finally:server.shutdown();server.server_close();worker.join()

class ProxyHTTPTests(unittest.TestCase):
    def test_real_upstream_statuses_payload_and_early_returns(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from unittest.mock import patch
        import concurrent.futures
        captured=[]; events=[]
        class Upstream(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                captured.append((dict(self.headers),body))
                code=int(self.path[1:]); self.send_response(code)
                self.send_header('Content-Type','text/event-stream'); self.end_headers()
                self.wfile.write(b'data: {"choices":[{"delta":{"content":"SECRET_REPLY"}}]}\n\ndata: [DONE]\n\n')
        up=ThreadingHTTPServer(('127.0.0.1',0),Upstream);ut=threading.Thread(target=up.serve_forever,daemon=True);ut.start()
        args=SimpleNamespace(rpm=100,daily=200,log_dir='',model='synthetic',max_tokens=100,upstream='',timeout=2)
        finished_by_id={}
        class CompletedHTTPHandler(ProxyHandler):
            def do_POST(self):
                try:super().do_POST()
                finally:finished_by_id[self.headers['X-Request-ID']].set()
        server=ProxyServer(('127.0.0.1',0),CompletedHTTPHandler,ProxyConfig(args,{'synthetic_token':'owner'},'SECRET_KEY'));worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        def call(rid,path='/v1/chat/completions',body=b'{"messages":[{"role":"user","content":"SECRET_PROMPT"}],"stream":true}',token='synthetic_token'):
            finished_by_id[rid]=threading.Event()
            req=urllib.request.Request('http://127.0.0.1:%d%s'%(server.server_port,path),data=body,headers={'X-TTS-Token':token,'X-Request-ID':rid,'CF-Ray':'0123456789abcdef-LHR'})
            try:r=urllib.request.urlopen(req,timeout=3)
            except urllib.error.HTTPError as exc:r=exc
            with r:result=r.status,r.headers.get('X-Request-ID'),r.read()
            self.assertTrue(finished_by_id[rid].wait(2))
            return result
        try:
            with patch('tools.llm_proxy.log_line',side_effect=lambda args,text:events.append(text)),patch('tools.llm_proxy.diagnostic_log_line',side_effect=lambda args,text:events.append(text)):
                for code,expected in [(200,200),(520,520),(503,424),(401,401)]:
                    args.upstream='http://127.0.0.1:%d/%d'%(up.server_port,code);rid=('%032x'%code)
                    status,returned,_=call(rid);self.assertEqual((status,returned),(expected,rid))
                    records=[json.loads(x.split(' ',1)[1]) for x in events if x.startswith('request_diag ') and rid in x]
                    self.assertIn({'request_id':rid,'stage':'upstream_headers','status':code,'cf_ray':'0123456789abcdef-LHR'},records)
                    self.assertTrue(any(x['stage']=='downstream_complete' and x['status']==expected for x in records))
                for path,body,expected in [('/bad',b'{}',404),('/v1/chat/completions',b'bad',400),('/v1/chat/completions',b'',400)]:
                    self.assertEqual(call('b'*32,path,body)[0],expected)
                args.upstream='http://127.0.0.1:%d/200'%up.server_port
                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                    results=list(pool.map(call,[('%032x'%n) for n in range(1,5)]))
                self.assertEqual(len({x[1] for x in results}),4)
            for headers,body in captured:
                self.assertFalse(any(k.lower() in ('x-request-id','cf-ray','x-tts-token') for k in headers))
                self.assertEqual(set(body),{'model','messages','stream','max_tokens'})
                self.assertEqual(body['messages'][0]['content'],'SECRET_PROMPT')
            diagnostics='\n'.join(x for x in events if x.startswith('request_diag '));self.assertNotIn('SECRET',diagnostics)
            self.assertNotIn('http',diagnostics)
        finally:
            server.shutdown();server.server_close();worker.join();up.shutdown();up.server_close();ut.join()

class FailureStageTests(unittest.TestCase):
    def test_upstream_read_failure_is_not_claimed_as_client_disconnect_or_completion(self):
        from unittest.mock import patch
        from email.message import Message
        events=[]
        args=SimpleNamespace(rpm=10,daily=20,log_dir='',model='synthetic',max_tokens=100,upstream='http://synthetic.invalid',timeout=1)
        class Upstream:
            status=200
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):raise ConnectionResetError('SECRET_EXCEPTION')
        h=ProxyHandler.__new__(ProxyHandler);h.server=SimpleNamespace(proxy=ProxyConfig(args,{'synthetic_token':'owner'},'SECRET_KEY'))
        h.headers=Message();h.headers['Content-Length']='15';h.headers['X-TTS-Token']='synthetic_token';h.headers['X-Request-ID']='c'*32
        h.rfile=io.BytesIO(b'{"stream":true} ');h.wfile=io.BytesIO();h.path='/v1/chat/completions';h.request_version='HTTP/1.1';h.requestline='POST /v1/chat/completions HTTP/1.1';h.command='POST'
        with patch('tools.llm_proxy.log_line',side_effect=lambda args,text:events.append(text)),patch('tools.llm_proxy.diagnostic_log_line',side_effect=lambda args,text:events.append(text)),patch('tools.llm_proxy.urllib.request.urlopen',return_value=Upstream()):h.do_POST()
        records=[json.loads(x.split(' ',1)[1]) for x in events if x.startswith('request_diag ')]
        stages=[x['stage'] for x in records]
        self.assertIn('upstream_headers',stages);self.assertIn('error',stages)
        self.assertNotIn('downstream_complete',stages);self.assertNotIn('downstream_disconnected',stages)
        self.assertNotIn('SECRET',''.join(x for x in events if x.startswith('request_diag ')))
    def test_actual_downstream_write_failure_is_marked_disconnected(self):
        from unittest.mock import patch
        from email.message import Message
        events=[]
        args=SimpleNamespace(rpm=10,daily=20,log_dir='',model='synthetic',max_tokens=100,upstream='http://synthetic.invalid',timeout=1)
        class Upstream:
            status=200
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return b'SECRET_REPLY'
        class Writer:
            def write(self,data):
                if data.startswith(b'HTTP/'):return len(data)
                raise BrokenPipeError('SECRET_EXCEPTION')
            def flush(self):pass
        h=ProxyHandler.__new__(ProxyHandler);h.server=SimpleNamespace(proxy=ProxyConfig(args,{'synthetic_token':'owner'},'SECRET_KEY'))
        h.headers=Message();h.headers['Content-Length']='15';h.headers['X-TTS-Token']='synthetic_token';h.headers['X-Request-ID']='d'*32
        h.rfile=io.BytesIO(b'{"stream":true} ');h.wfile=Writer();h.path='/v1/chat/completions';h.request_version='HTTP/1.1';h.requestline='POST /v1/chat/completions HTTP/1.1';h.command='POST'
        with patch('tools.llm_proxy.log_line',side_effect=lambda args,text:events.append(text)),patch('tools.llm_proxy.diagnostic_log_line',side_effect=lambda args,text:events.append(text)),patch('tools.llm_proxy.urllib.request.urlopen',return_value=Upstream()):h.do_POST()
        records=[json.loads(x.split(' ',1)[1]) for x in events if x.startswith('request_diag ')]
        stages=[x['stage'] for x in records]
        self.assertIn('downstream_disconnected',stages);self.assertNotIn('downstream_complete',stages)
        self.assertNotIn('SECRET',''.join(x for x in events if x.startswith('request_diag ')))

class DiagnosticSinkTests(unittest.TestCase):
    def handler(self, log_dir=''):
        from email.message import Message
        h=ProxyHandler.__new__(ProxyHandler)
        args=SimpleNamespace(log_dir=log_dir,rpm=10,daily=20)
        h.server=SimpleNamespace(proxy=ProxyConfig(args,{},'SYNTHETIC_KEY'))
        h.headers=Message();h.headers['X-Request-ID']='e'*32
        h.rfile=io.BytesIO(b'{}');h.wfile=io.BytesIO();h.path='/v1/chat/completions'
        h.request_version='HTTP/1.1';h.requestline='POST /v1/chat/completions HTTP/1.1';h.command='POST'
        return h

    def test_each_diagnostic_stage_sink_failure_preserves_401_and_clears_context(self):
        from unittest.mock import patch
        for stage in ('request_received','downstream_headers','downstream_complete'):
            for error in (BrokenPipeError, OSError, ValueError):
                with self.subTest(stage=stage,error=error.__name__):
                    class Sink(io.StringIO):
                        def write(self,text):
                            if stage in text:raise error('SECRET_SINK_CANARY')
                            return super().write(text)
                    h=self.handler();sink=Sink()
                    with patch('tools.llm_proxy.sys.stderr',sink):h.do_POST()
                    self.assertIn(b'HTTP/1.1 401',h.wfile.getvalue())
                    self.assertIn(b'{"error": "unauthorized"}',h.wfile.getvalue())
                    self.assertIsNone(h._request_id)
                    self.assertNotIn('SECRET_SINK_CANARY',sink.getvalue())

    def test_directory_error_never_prints_exception_canary(self):
        from unittest.mock import patch
        h=self.handler('synthetic-diagnostic-dir');sink=io.StringIO()
        with patch('tools.llm_proxy.sys.stderr',sink),patch('tools.llm_proxy.os.makedirs',side_effect=OSError('SECRET_DIRECTORY_CANARY')):h.do_POST()
        self.assertIn(b'HTTP/1.1 401',h.wfile.getvalue());self.assertIsNone(h._request_id)
        self.assertNotIn('SECRET_DIRECTORY_CANARY',sink.getvalue())
        self.assertEqual(sink.getvalue().count('request_diag '),3)

    def test_closed_stderr_still_writes_safe_correlated_file(self):
        from unittest.mock import patch
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            h=self.handler(folder);sink=io.StringIO();sink.close()
            with patch('tools.llm_proxy.sys.stderr',sink):h.do_POST()
            self.assertIn(b'HTTP/1.1 401',h.wfile.getvalue());self.assertIsNone(h._request_id)
            logs=list(Path(folder).glob('llm_proxy_*.log'));self.assertEqual(len(logs),1)
            records=[json.loads(x.split(' ',1)[1]) for x in logs[0].read_text().splitlines()]
            self.assertEqual([x['stage'] for x in records],['request_received','downstream_headers','downstream_complete'])
            self.assertTrue(all(x['request_id']=='e'*32 for x in records))

    def test_file_write_error_never_prints_exception_canary(self):
        from unittest.mock import patch
        h=self.handler('synthetic-diagnostic-dir');sink=io.StringIO()
        with patch('tools.llm_proxy.sys.stderr',sink),patch('tools.llm_proxy.os.makedirs'),patch('builtins.open',side_effect=OSError('SECRET_FILE_CANARY')):h.do_POST()
        self.assertIn(b'HTTP/1.1 401',h.wfile.getvalue());self.assertIsNone(h._request_id)
        self.assertNotIn('SECRET_FILE_CANARY',sink.getvalue())
