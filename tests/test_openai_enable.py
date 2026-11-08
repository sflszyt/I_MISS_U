import contextlib, ctypes, io, json, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock
from tools import windows_credential as cred, llm_proxy as proxy
from tools.father_model_policy import load_policy, OPENAI_MODELS
from tests.test_llm_proxy import args, TOKENS
from tests import test_llm_proxy as route_tests

class Policy(unittest.TestCase):
    def test_release_policy_enabled(self): self.assertEqual(load_policy(), OPENAI_MODELS)
    def test_invalid_contract(self):
        bad=[{}, [], {"version":True,"enabled_models":[]}, {"version":2,"enabled_models":[]},
             {"version":1,"enabled_models":"gpt-6-luna"}, {"version":1,"enabled_models":["unknown"]},
             {"version":1,"enabled_models":["gpt-6-luna","gpt-6-luna"]},
             {"version":1,"enabled_models":[1]}, {"version":1,"enabled_models":[],"secret":"SYNTHETIC"}]
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as d:
            p=Path(d)/'policy.json'
            for value in bad:
                p.write_text(json.dumps(value))
                with self.assertRaisesRegex(ValueError,'^invalid father OpenAI policy$'):load_policy(p)
            p.write_text(json.dumps(dict(version=1,enabled_models=list(OPENAI_MODELS))))
            self.assertEqual(load_policy(p),OPENAI_MODELS)
    def test_gate_matrix(self):
        invoke=route_tests.ModelRoutes().invoke
        for allowed,key,model,expected in [([], 'SYNTHETIC','gpt-6-luna',409),
                (['gpt-6-luna'],'','gpt-6-luna',409), (['gpt-6-luna'],'SYNTHETIC','gpt-6.1-sol',409),
                (['gpt-6-luna'],'SYNTHETIC','gpt-6-luna',200)]:
            sent,res=invoke('synthetic_father',{'model':model,'stream':True},proxy.ProxyConfig(args(openai_model=allowed),TOKENS,'SYNTHETIC_DS',key))
            self.assertIn(('HTTP/1.1 '+str(expected)).encode(),res)
            self.assertEqual(bool(sent),expected==200)
    def test_startup_disabled_never_reads_credentials(self):
        argv=['proxy','--upstream','https://synthetic.invalid','--model','deepseek-v4-flash','--tokens','father:synthetic_father', '--openai-credential-target',cred.TARGET]
        with patch.object(proxy,'load_policy',return_value=()), patch.object(proxy.sys,'argv',argv), patch.dict(proxy.os.environ,{'DEEPSEEK_API_KEY':'SYNTHETIC'},clear=True), patch.object(proxy,'read_openai_credential') as read, patch.object(proxy,'ProxyServer') as server, contextlib.redirect_stderr(io.StringIO()):
            server.return_value.serve_forever.return_value=None
            proxy.main();read.assert_not_called()
            self.assertEqual(server.call_args.args[2].openai_models,())
    def test_startup_enabled_explicit_target_only(self):
        argv=['proxy','--upstream','https://synthetic.invalid','--model','deepseek-v4-flash','--tokens','father:synthetic_father','--openai-credential-target',cred.TARGET]
        with patch.object(proxy.sys,'argv',argv), patch.dict(proxy.os.environ,{'DEEPSEEK_API_KEY':'SYNTHETIC'},clear=True), patch.object(proxy,'load_policy',return_value=('gpt-6-luna',)), patch.object(proxy,'read_openai_credential',return_value='SYNTHETIC_OPENAI') as read, patch.object(proxy,'ProxyServer') as server, contextlib.redirect_stderr(io.StringIO()):
            proxy.main();read.assert_called_once_with(cred.TARGET)
            self.assertEqual(server.call_args.args[2].openai_models,('gpt-6-luna',))

class Credential(unittest.TestCase):
    def test_no_target_and_wrong_target_do_not_load_dll(self):
        with patch.object(cred,'_api') as api:
            self.assertEqual(cred.read_openai_credential(), '')
            with self.assertRaisesRegex(ValueError,'unsupported OpenAI credential target'):cred.read_openai_credential('OTHER_SYNTHETIC')
            api.assert_not_called()
    def test_credread_exact_and_free_success_and_invalid(self):
        for raw,valid in [('SYNTHETIC_KEY'.encode('utf-16-le'),True),(b'x',False),('SYNTHETIC\nKEY'.encode('utf-16-le'),False),(b'\x00\x00',False)]:
            blob=(ctypes.c_ubyte*len(raw)).from_buffer_copy(raw)
            item=cred.CREDENTIALW();item.Type=1;item.CredentialBlobSize=len(raw);item.CredentialBlob=blob
            api=Mock()
            def read(target,kind,flags,out):
                self.assertEqual((target,kind,flags),(cred.TARGET,1,0))
                ctypes.cast(out,ctypes.POINTER(ctypes.POINTER(cred.CREDENTIALW)))[0]=ctypes.pointer(item)
                return True
            api.CredReadW.side_effect=read
            with patch.object(cred,'_api',return_value=api):
                if valid:self.assertEqual(cred.read_openai_credential(cred.TARGET),'SYNTHETIC_KEY')
                else:
                    with self.assertRaisesRegex(ValueError,'^OpenAI credential unavailable or invalid$'):cred.read_openai_credential(cred.TARGET)
            api.CredReadW.assert_called_once();api.CredFree.assert_called_once()
    def test_failure_fixed_no_exception_leak(self):
        for api in [Mock(CredReadW=Mock(return_value=False)),None]:
            with patch.object(cred,'_api',**({'return_value':api} if api else {'side_effect':OSError('SYNTHETIC_SECRET')})):
                with self.assertRaisesRegex(ValueError,'^OpenAI credential unavailable or invalid$'):cred.read_openai_credential(cred.TARGET)
            if api:api.CredFree.assert_not_called()

if __name__=='__main__':unittest.main(verbosity=2)
