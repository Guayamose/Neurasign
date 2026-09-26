import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

function proxy(fetch) {
  const exports = {};
  const source = fs.readFileSync(new URL('../app/api/v1/[...path]/route.ts', import.meta.url), 'utf8');
  const code = ts.transpileModule(source, {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  vm.runInNewContext(code, {exports, process:{env:{API_INTERNAL_URL:'http://api.internal:8000'}}, fetch, Response, AbortSignal, Buffer});
  return exports;
}
test('OAuth return survives the web proxy as an HTML page with its security headers', async () => {
  const api = proxy(async url => {
    assert.equal(url, 'http://api.internal:8000/api/v1/integrations/whoop/callback?state=opaque&code=once');
    return new Response('<h1>Wearable account connected</h1>', {headers:{'content-type':'text/html; charset=utf-8','content-security-policy':"default-src 'none'; frame-ancestors 'none'"}});
  });
  const request = new Request('https://example.test/api/v1/integrations/whoop/callback?state=opaque&code=once');
  request.nextUrl = new URL(request.url);
  const result = await api.GET(request, {params:Promise.resolve({path:['integrations','whoop','callback']})});
  assert.match(result.headers.get('content-type'), /text\/html/);
  assert.equal(result.headers.get('cache-control'), 'no-store');
  assert.equal(result.headers.get('referrer-policy'), 'no-referrer');
  assert.match(result.headers.get('content-security-policy'), /frame-ancestors 'none'/);
  assert.match(await result.text(), /account connected/);
});
