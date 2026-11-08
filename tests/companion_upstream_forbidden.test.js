const fs = require('fs'), vm = require('vm'), assert = require('node:assert/strict'), test = require('node:test');
const source = fs.readFileSync(__dirname + '/../tools/build_companion_page.py', 'utf8');
const funcs = [...source.matchAll(/^function (?:requestDiagnosticText|companionStream)\([^\n]*\) \{.*?^\}/gms)].map(m => m[0]).join('\n');
test('upstream forbidden requires fixed header, status and matching valid correlation', async () => {
  const id = 'a'.repeat(32);
  for (const [status, header, proxyId, requestId, expected] of [
    [403, 'upstream_forbidden', id, id, 'UPSTREAM_FORBIDDEN'],
    [403, null, id, id, 'HTTP_403'],
    [403, 'PRIVATE_CANARY', id, id, 'HTTP_403'],
    [401, 'upstream_forbidden', id, id, 'HTTP_401'],
    [403, 'upstream_forbidden', 'b'.repeat(32), id, 'HTTP_403'],
    [403, 'upstream_forbidden', 'invalid', 'invalid', 'HTTP_403'],
    [403, 'upstream_forbidden', id, null, 'HTTP_403'],
  ]) {
    let calls = 0, reads = 0, cancels = 0, completed = 0, errors = [];
    const h = { AbortController, TextDecoder, console: {info(){}},
      fetch: async () => { calls++; return {ok:false, status,
        headers:{get:name=>({'X-LLM-Error':header,'X-Request-ID':proxyId}[name] || null)},
        body:{cancel(){cancels++;return Promise.resolve();},getReader(){reads++;throw Error('PRIVATE_CANARY');}},
        text(){reads++;throw Error('PRIVATE_CANARY');}}; }
    };
    vm.createContext(h); vm.runInContext(funcs, h);
    const diag = requestId === null ? null : {request_id:requestId};
    h.companionStream('https://synthetic.invalid', {}, {}, 'openai', new AbortController(),
      ()=>assert.fail('no delta'), ()=>completed++, e=>errors.push(e), diag);
    await new Promise(resolve=>setTimeout(resolve,5));
    assert.equal(errors.length,1); assert.ok(errors[0].startsWith('LLM_'+expected));
    assert.equal(completed,0); assert.equal(calls,1); assert.equal(reads,0); assert.equal(cancels,1);
    assert.ok(!errors[0].includes('PRIVATE_CANARY'));
  }
});
