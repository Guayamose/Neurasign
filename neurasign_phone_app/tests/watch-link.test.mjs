import test from 'node:test';
import assert from 'node:assert/strict';
import { watchHello, watchMeasurements, connectWatch } from '../dist/watch-link.js';
import { mergeWearable } from '../dist/multisignal.js';
const session = 'test-session-0001';
const caps = [{ metric: 'electrodermal_conductance', unit: 'µS', method: 'samsung-health-sensor-1.4:continuous', measurement_kind: 'sample', delivery_mode: 'stream', timestamp_basis: 'device' }];
const hello = { version: 1, kind: 'hello', session, manufacturer: 'Samsung', model: 'Protocol fixture', sources: [{ id: 'samsung-continuous', name: 'Samsung sensors', capabilities: caps }], warnings: [] };
const sample = { metric: 'electrodermal_conductance', unit: 'µS', value: .5, samples: [.2, .5], sample_offsets_ms: [-1000, 0], measured_at: '2026-09-26T10:00:00.000Z' };
const message = { version: 1, kind: 'samples', session, sequence: 0, source: 'samsung-continuous', measurements: [sample] };
test('watch declarations reject arbitrary quantities, forged session IDs and incorrect units', () => {
  assert.deepEqual(watchHello(hello, session), hello);
  assert.throws(() => watchHello(hello, 'another-session'));
  for (const changes of [{ metric: 'fatigue' }, { unit: 'S' }, { timestamp_basis: 'phone_receipt' }, { interval_seconds: 60 }]) {
    assert.throws(() => watchHello({ ...hello, sources: [{ ...hello.sources[0], capabilities: [{ ...caps[0], ...changes }] }] }, session));
  }
});
test('watch samples retain all values and irregular timing while stripping untrusted identity fields', () => {
  const decoded = watchMeasurements({ ...message, measurements: [{ ...sample, organization_id: 'another-company', source_id: 'forged', method: 'fake' }] }, hello.sources, session);
  assert.deepEqual(decoded.measurements, [sample]);
  for (const changes of [{ unit: 'S' }, { samples: [.3] }, { sample_offsets_ms: [1, 0] }, { value: 2 }, { measured_at: '2026-09-26T10:00:00' }]) assert.throws(() => watchMeasurements({ ...message, measurements: [{ ...sample, ...changes }] }, hello.sources, session));
});
test('watch retries are acknowledged only after persistence and cannot leak old sessions or other nodes', async () => {
  const abort = new AbortController(), sent = [];
  let receiver, detached = false;
  const transport = { listen(fn) { receiver = fn; return () => { detached = true; }; }, async send(node, json) {
    assert.equal(node, 'selected-watch'); const body = JSON.parse(json); sent.push(body);
    if (body.kind === 'start') receiver(node, JSON.stringify(hello));
  } };
  const connected = await connectWatch(transport, 'selected-watch', session, abort.signal, async () => 'a'.repeat(64));
  assert.equal(connected.sources[0].descriptor.transport, 'vendor_sdk');
  const stream = mergeWearable(connected.sources)[Symbol.asyncIterator]();
  receiver('other-watch', JSON.stringify(message)); receiver('selected-watch', JSON.stringify({ ...message, session: 'old-session' }));
  receiver('selected-watch', JSON.stringify(message)); receiver('selected-watch', JSON.stringify(message));
  assert.equal(sent.filter(row => row.kind === 'ack').length, 0);
  const row = await stream.next(); assert.deepEqual(row.value.measurement.samples, [.2, .5]);
  assert.equal(sent.filter(row => row.kind === 'ack').length, 0, 'Yielding a row does not mean encrypted persistence succeeded.');
  const pending = stream.next(); await new Promise(resolve => setImmediate(resolve));
  assert.equal(sent.filter(row => row.kind === 'ack').length, 1);
  receiver('selected-watch', JSON.stringify(message)); await new Promise(resolve => setImmediate(resolve));
  assert.equal(sent.filter(row => row.kind === 'ack').length, 2);
  abort.abort(); await connected.close(); await pending;
  assert.ok(detached); assert.equal(sent.at(-1).kind, 'stop');
});
test('conflicting watch retries fail explicitly and clear listeners on close', async () => {
  const abort = new AbortController(); let receive;
  const transport = { listen(fn) { receive = fn; return () => {}; }, async send(node, json) { if (JSON.parse(json).kind === 'start') receive(node, JSON.stringify(hello)); } };
  const connected = await connectWatch(transport, 'watch', session, abort.signal, async () => 'a'.repeat(64));
  receive('watch', JSON.stringify(message)); receive('watch', JSON.stringify({ ...message, measurements: [{ ...sample, value: .6, samples: [.2, .6] }] }));
  await assert.rejects(connected.sources[0].measurements[Symbol.asyncIterator]().next(), /reused a sequence/);
  abort.abort(); await connected.close();
});

test('watch retries outside the bounded deduplication window fail instead of recording a second copy', async () => {
  const abort = new AbortController(); let receive;
  const transport = { listen(fn) { receive = fn; return () => {}; }, async send(node, json) { if (JSON.parse(json).kind === 'start') receive(node, JSON.stringify(hello)); } };
  const connected = await connectWatch(transport, 'watch', session, abort.signal, async () => 'a'.repeat(64));
  const stream = connected.sources[0].measurements[Symbol.asyncIterator]();
  try {
    let next = stream.next();
    for (let sequence = 0; sequence < 130; sequence++) {
      receive('watch', JSON.stringify({ ...message, sequence }));
      assert.equal((await next).value.value, sample.value);
      next = stream.next(); await new Promise(resolve => setImmediate(resolve));
    }
    receive('watch', JSON.stringify(message));
    await assert.rejects(next, /deduplication window/);
  } finally { abort.abort(); await connected.close(); }
});
