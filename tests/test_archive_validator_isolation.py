import json
import re
import subprocess
import unittest
from tools.build_companion_page import build
from tools.couple_memory_release import validate_release, runtime_binding
from tests.test_couple_memory_release import fixture


class ArchiveValidatorIsolationTests(unittest.TestCase):
    def test_late_digest_rejection_cannot_publish_global_diagnostics(self):
        packet, rows = fixture()
        memory = validate_release(packet, rows, '0' * 64)
        scope = dict(person='mama', relationship_id='mama_father', memory_release=runtime_binding(memory))
        html = build('mama', '.', 'father', relationship_scope=scope,
                     archive_manifest_path='data/archive-cache-manifest.json')
        funcs = '\n'.join(re.search(r'^(?:async )?function ' + name + r'\([^\n]*\) \{.*?^\}', html, re.M | re.S).group()
                          for name in ['checkScope', 'validateMemoryRelease', 'archiveResource'])
        integration = html[html.index('function checkArchiveScope(data, kind) {'):html.index('var archiveCache =')]
        script = "const assert=require('node:assert/strict');var EXPECTED_SCOPE=" + json.dumps(scope) + ";var VIEWER='father',scopeError=false,memorySourceDigests=new Map(),failures=0;\n"
        script += "var archiveOptions={contextPath:'data/chat_context.json'};function dataFailure(){failures++;}function dataError(){failures++;return Error('bad');}function boundedWait(p){return p;}let entered,rejectOld;const atDigest=new Promise(r=>entered=r);const crypto={subtle:{digest(){entered();return new Promise((_,r)=>rejectOld=r);}}};\n"
        script += funcs + '\n' + integration + '\nconst memory=' + json.dumps(memory) + ';\n'
        script += "(async()=>{const pending=archiveOptions.validate('data/memories-test.json',memory);const rejected=assert.rejects(pending);await atDigest;scopeError=false;failures=0;rejectOld(Error('old digest rejected'));await rejected;assert.equal(scopeError,false);assert.equal(failures,0);console.log('PASS isolated late validator diagnostics');})().catch(e=>{console.error(e);process.exitCode=1;});"
        result = subprocess.run(['node', '-'], input=script, text=True, encoding='utf-8', capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_versioned_context_validation_and_safe_failure_labels(self):
        scope = dict(person='test', relationship_id='test_father')
        context_path = 'data/chat_context.language-lines-20261105-v1.json'
        html = build('test', '.', 'father', context_path=context_path, relationship_scope=scope,
                     archive_manifest_path='data/archive-cache-manifest.json')
        funcs = '\n'.join(re.search(r'^(?:async )?function ' + name + r'\([^\n]*\) \{.*?^\}', html, re.M | re.S).group()
                          for name in ['checkScope', 'validateMemoryRelease', 'archiveResource', 'publishArchiveFailure'])
        integration = html[html.index('function checkArchiveScope(data, kind) {'):html.index('var archiveCache =')]
        script = "const assert=require('node:assert/strict');var EXPECTED_SCOPE=" + json.dumps(scope) + ";var VIEWER='father',scopeError=false,memorySourceDigests=new Map();\n"
        script += "var archiveOptions={contextPath:" + json.dumps(context_path) + "};var archiveCache={epoch:1,operationOwner:2},dataReadyPhase='',reported;function dataFailure(r,c){reported=[r,c];}function updateArchiveRevision(){}function reportDataProgress(){}\n"
        script += funcs + '\n' + integration
        script += """
(async()=>{
 const context={...EXPECTED_SCOPE,viewer:'father',coverage_status:'partial',language:'mandarin',system_prompt:'synthetic',message_shards:['messages-2000.json']};
 await archiveOptions.validate(archiveOptions.contextPath,context);
 await assert.rejects(archiveOptions.validate(archiveOptions.contextPath,{...context,viewer:'owner'}),e=>e.authority && e.dataResource==='CONTEXT' && e.dataCode==='SCOPE');
 for(const [message,code] of [['ARCHIVE_HASH','HASH'],['ARCHIVE_JSON','JSON'],['ARCHIVE_AUTHORITY','AUTHORITY'],['ARCHIVE_REFRESH_REQUIRED','REFRESH_REQUIRED'],['private response body','VALIDATION'],['toString','VALIDATION'],['constructor','VALIDATION'],['__proto__','VALIDATION']]){
  publishArchiveFailure(Error(message),{epoch:1,owner:2});assert.deepEqual(reported,['archive',code]);
 }
 publishArchiveFailure(Object.assign(Error('redacted'),{dataResource:'IDENTITY',dataCode:'HTTP_403'}),{epoch:1,owner:2});
 assert.deepEqual(reported,['IDENTITY','HTTP_403']);
 for(const fields of [
  {dataResource:'private body',dataCode:'private body'},
  {dataResource:'constructor',dataCode:'toString'},
  {dataResource:'__proto__',dataCode:'__proto__'},
  {dataResource:{toString(){throw Error('must not coerce');}},dataCode:{toString(){throw Error('must not coerce');}}},
  {dataResource:'SHARD_2000/sensitive',dataCode:'HTTP_403 sensitive'},
  {dataResource:'IDENTITY\\nprivate',dataCode:'HTTP_403\\nprivate'},
  {dataResource:'IDENTITY\\n',dataCode:'HTTP_403\\n'},
  {dataResource:'SHARD_123',dataCode:'HTTP_999'}]) {
  publishArchiveFailure(Object.assign(Error('unknown'),fields),{epoch:1,owner:2});assert.deepEqual(reported,['archive','VALIDATION']);
 }
 for(const resource of ['IDENTITY','MANIFEST','CONTEXT','MEMORY','TRANSCRIPTS','SHARD_2000']) {
  for(const code of ['HTTP_403','SCHEMA','SCOPE','BINDING','FETCH_TIMEOUT','BODY_TIMEOUT','CRYPTO_FAILED','CARD_HASH']) {
   publishArchiveFailure(Object.assign(Error('redacted'),{dataResource:resource,dataCode:code}),{epoch:1,owner:2});assert.deepEqual(reported,[resource,code]);
  }
 }
 publishArchiveFailure({message:'ARCHIVE_HASH',dataResource:'private',dataCode:'private'},{epoch:1,owner:2});assert.deepEqual(reported,['archive','HASH']);
 publishArchiveFailure(null,{epoch:1,owner:2});assert.deepEqual(reported,['archive','VALIDATION']);
 reported=null;publishArchiveFailure(Error('ARCHIVE_HASH'),{epoch:0,owner:2});assert.equal(reported,null);
})().catch(e=>{console.error(e);process.exitCode=1;});
"""
        result = subprocess.run(['node', '-'], input=script, text=True, encoding='utf-8', capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
