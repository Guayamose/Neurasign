import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import { NextRequest } from 'next/server.js';

function load(relative, globals = {}) {
  const exports = {};
  const source = fs.readFileSync(new URL(relative, import.meta.url), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  vm.runInNewContext(code, { exports, Response, AbortSignal, Buffer, URL, ...globals });
  return exports;
}

function proxy(fetch, env = {}) {
  return load('../app/api/model-engine/[...path]/route.ts', { process: { env: { API_INTERNAL_URL: 'http://api.internal:8000/', ...env } }, fetch });
}

function request(path, method = 'GET', body, headers = {}) {
  const value = new Request(`http://localhost:3000/api/model-engine/${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  value.nextUrl = new URL(value.url);
  return value;
}

const context = (...path) => ({ params: Promise.resolve({ path }) });
const unused = () => { throw new Error('The upstream must not be called.'); };

test('model proxy is unavailable in production and Cloud Run before any upstream request', async () => {
  for (const env of [{ NEURASIGN_ENV: 'production' }, { K_SERVICE: 'service' }]) {
    const api = proxy(unused, env);
    assert.equal((await api.GET(request('catalog'), context('catalog'))).status, 404);
    assert.equal((await api.POST(request('models/stress/predict', 'POST', { record_id: 'stress-0001' }), context('models', 'stress', 'predict'))).status, 404);
  }
});

test('proxy forwards only its server token, never browser credentials, and returns no-store JSON', async () => {
  const api = proxy(async (url, options) => {
    assert.equal(url, 'http://api.internal:8000/api/model-engine/catalog');
    assert.equal(options.headers['X-Model-Engine-Token'], 'server-test-token');
    assert.equal(options.headers.Authorization, undefined);
    assert.equal(options.cache, 'no-store');
    assert.equal(options.redirect, 'error');
    return Response.json({ scope: 'anonymous_research', models: [] });
  }, { MODEL_ENGINE_TOKEN: 'server-test-token' });
  const response = await api.GET(request('catalog', 'GET', undefined, { Authorization: 'Bearer browser-token', 'X-Model-Engine-Token': 'browser-supplied-token' }), context('catalog'));
  assert.equal(response.status, 200);
  assert.equal(response.headers.get('cache-control'), 'no-store');
  assert.equal(response.headers.get('referrer-policy'), 'no-referrer');
  assert.doesNotMatch(await response.text(), /server-test-token|browser-token/);
});

test('only allowlisted research routes and query-free requests reach the upstream', async () => {
  const api = proxy(unused);
  for (const path of [['organizations', 'employee'], ['models', 'stress', 'train'], ['models', '..', 'records'], ['models', 'stress', 'predict']]) {
    assert.equal((await api.GET(request(path.join('/')), context(...path))).status, 404);
  }
  assert.equal((await api.GET(request('catalog?member_id=employee'), context('catalog'))).status, 404);
  assert.equal((await api.POST(request('catalog', 'POST', {}), context('catalog'))).status, 404);
});

test('cross-origin and cross-site calls cannot use the server token proxy', async () => {
  const api = proxy(unused);
  for (const headers of [{ origin: 'https://other.example' }, { 'sec-fetch-site': 'cross-site' }]) {
    assert.equal((await api.GET(request('catalog', 'GET', undefined, headers), context('catalog'))).status, 403);
    assert.equal((await api.POST(request('models/stress/predict', 'POST', { record_id: 'stress-0001' }, headers), context('models', 'stress', 'predict'))).status, 403);
  }
});

test('actual NextRequest accepts matching browser loopback origins when its URL uses the Docker address', async () => {
  let calls = 0;
  const api = proxy(async () => { calls++; return Response.json({ model_id: 'stress' }); });
  for (const host of ['localhost:3000', '127.0.0.1:3000', '[::1]:3000', 'localhost:3100']) {
    const browserOrigin = `http://${host}`;
    const incoming = new NextRequest('http://0.0.0.0:3000/api/model-engine/models/stress/predict', {
      method: 'POST',
      headers: { host, origin: browserOrigin, 'sec-fetch-site': 'same-origin', 'content-type': 'application/json' },
      body: JSON.stringify({ record_id: 'stress-0001' }),
    });
    assert.equal(incoming.nextUrl.origin, 'http://0.0.0.0:3000');
    assert.equal((await api.POST(incoming, context('models', 'stress', 'predict'))).status, 200);
  }
  assert.equal(calls, 4);
});

test('Docker origin handling preserves host and port isolation and ignores untrusted forwarded hosts', async () => {
  const api = proxy(unused);
  for (const headers of [
    { host: 'localhost:3000', origin: 'http://localhost:3100' },
    { host: '127.0.0.1:3000', origin: 'http://localhost:3000' },
    { host: 'localhost:3000', origin: 'https://localhost:3000' },
    { host: 'attacker.example', origin: 'http://attacker.example' },
    { host: 'localhost.attacker.example:3000', origin: 'http://localhost.attacker.example:3000' },
    { host: 'web:3000', origin: 'http://localhost:3000', 'x-forwarded-host': 'localhost:3000' },
    { host: 'localhost:3000', origin: 'http://attacker.example', 'x-forwarded-host': 'attacker.example' },
    { host: 'localhost:3000', origin: 'http://localhost:3000', 'sec-fetch-site': 'cross-site' },
    { host: 'localhost:99999', origin: 'http://localhost:99999' },
  ]) {
    const incoming = new NextRequest('http://0.0.0.0:3000/api/model-engine/models/stress/predict', {
      method: 'POST', headers, body: JSON.stringify({ record_id: 'stress-0001' }),
    });
    assert.equal((await api.POST(incoming, context('models', 'stress', 'predict'))).status, 403);
  }
});

test('prediction accepts only a recorded example ID and rejects identifiers and uploaded features', async () => {
  const api = proxy(unused);
  for (const body of [null, [], {}, { record_id: 123 }, { record_id: '../model.pkl' }, { record_id: 'stress-0001', employee_id: 'named-person' }, { record_id: 'stress-0001', features: [1, 2] }, { record_id: '' }]) {
    assert.equal((await api.POST(request('models/stress/predict', 'POST', body), context('models', 'stress', 'predict'))).status, 422);
  }
  const forwarded = proxy(async (url, options) => {
    assert.equal(url, 'http://api.internal:8000/api/model-engine/models/stress/predict');
    assert.deepEqual(JSON.parse(options.body), { record_id: 'stress-0001' });
    return Response.json({ model_id: 'stress' });
  });
  assert.equal((await forwarded.POST(request('models/stress/predict', 'POST', { record_id: 'stress-0001' }, { origin: 'http://localhost:3000' }), context('models', 'stress', 'predict'))).status, 200);
});

test('request size is enforced on actual streamed bytes even without a content-length header', async () => {
  const api = proxy(unused);
  const large = request('models/stress/predict', 'POST', { record_id: 'a'.repeat(3000) });
  assert.equal((await api.POST(large, context('models', 'stress', 'predict'))).status, 413);
  const declaredLarge = request('models/stress/predict', 'POST', { record_id: 'stress-0001' }, { 'content-length': '3000' });
  assert.equal((await api.POST(declaredLarge, context('models', 'stress', 'predict'))).status, 413);
});

test('unavailable and non-JSON upstream responses produce readable errors without fallback predictions', async () => {
  const invalid = proxy(async () => new Response('proxy failure', { status: 502, headers: { 'content-type': 'text/html' } }));
  const response = await invalid.GET(request('catalog'), context('catalog'));
  assert.equal(response.status, 502);
  assert.match((await response.json()).detail, /invalid response/);
  const offline = proxy(async () => { throw new Error('private upstream information'); });
  const failure = await offline.GET(request('catalog'), context('catalog'));
  assert.equal(failure.status, 503);
  assert.doesNotMatch(await failure.text(), /private upstream information/);
});

test('research values preserve classification labels and distinguish error points from accuracy percentages', () => {
  const ui = load('../lib/model-engine.ts');
  assert.equal(ui.evidenceLabel({ value: 94.1860465, unit: '%', metric: 'Accuracy' }), '94.2%');
  assert.equal(ui.evidenceLabel({ value: 3.975, unit: 'points', metric: 'Mean absolute error' }), '3.98 points');
  assert.equal(ui.valueLabel({ value: 1, label: 'Stress task', unit: 'class' }, 'classification'), 'Stress task');
  assert.equal(ui.valueLabel({ value: 73.28, label: '73.28 /100', unit: 'points' }, 'regression'), '73.3');
  assert.equal(ui.comparison({ prediction: { value: 1 }, reference: { value: 0 } }, 'classification'), 'Differs from this recorded reference');
  assert.equal(ui.comparison({ prediction: { value: 73.28 }, reference: { value: 68 } }, 'regression'), '5.3-point difference on this record');
  assert.match(ui.modelInputNotes.readiness, /daily readiness/);
  assert.match(ui.modelInputNotes.workload, /completed task/);
  assert.equal(ui.modelStatusLabels.invalid_hash, 'Verification failed');
});
