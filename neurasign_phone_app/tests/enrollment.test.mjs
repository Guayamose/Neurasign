import test from 'node:test';
import assert from 'node:assert/strict';
import { parseEnrollmentLink, gatewayRequest } from '../dist/enrollment.js';
import { GatewaySession } from '../dist/gateway.js';
const token = `nse_${'a'.repeat(32)}.${'b'.repeat(43)}`;
const link = server => `neurasign://enroll#${new URLSearchParams({ server, token })}`;
test('connection QR pins a strict HTTPS origin and a single bootstrap token', () => {
  assert.deepEqual(parseEnrollmentLink(link('https://company.example')), { apiOrigin: 'https://company.example', token });
  for (const server of ['http://company.example','https://user:password@company.example','https://company.example/path','https://company.example?query','https://company.example#fragment']) assert.throws(() => parseEnrollmentLink(link(server)));
  assert.throws(() => parseEnrollmentLink(link('http://localhost:3000')));
  assert.equal(parseEnrollmentLink(link('http://localhost:3000'), true).apiOrigin, 'http://localhost:3000');
  assert.throws(() => parseEnrollmentLink(link('http://192.168.1.4'), true));
  assert.throws(() => parseEnrollmentLink(`${link('https://company.example')}&token=${token}`));
  assert.throws(() => parseEnrollmentLink(`${link('https://company.example')}&company=spoofed`));
});
test('enrollment preview never sends an existing credential; failed claims preserve their error status', async () => {
  let request;
  await gatewayRequest('https://company.example','/enrollment/preview',{method:'POST',body:{token},fetch:async (url, init)=>{request={url,...init};return new Response(JSON.stringify({company:'Northstar'}));}});
  assert.equal(request.headers.Authorization,undefined);
  assert.equal(request.redirect,'error');
  await assert.rejects(gatewayRequest('https://company.example','/enrollment/claim',{fetch:async()=>new Response(JSON.stringify({detail:'Code expired'}),{status:410})}),e=>e.status===410&&e.message==='Code expired');
});
test('stopping a gateway aborts uploads and retains its unacknowledged queue', async () => {
  let acknowledged=false, began;
  const started=new Promise(resolve=>{began=resolve});
  const session=new GatewaySession({apiOrigin:'https://company.example',enrollmentId:'test',credential:`nsd_${'a'.repeat(32)}.${'b'.repeat(43)}`,newId:()=> 'observation-1',queue:{append:async()=>{},peek:async()=>[{id:'observation-1'}],acknowledge:async()=>{acknowledged=true}},fetch:async(_url,init)=>new Promise((_resolve,reject)=>{init.signal.addEventListener('abort',()=>reject(new Error('aborted')));began();})});
  const flush=session.flush();await started;session.close();await assert.rejects(flush,/aborted/);assert.equal(acknowledged,false);
});
