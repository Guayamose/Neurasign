import test from "node:test";
import assert from "node:assert/strict";
import { GatewaySession, GatewayError } from "../dist/gateway.js";
import { AdapterRegistry } from "../dist/contract.js";
import { decodeHeartRate, StandardHeartRateAdapter, HEART_RATE_SERVICE, HEART_RATE_MEASUREMENT } from "../dist/heart-rate.js";

// In-memory queue and transport are test fixtures, never shipped as native storage.
class TestQueue {
  rows = new Map();
  async append(key, row) { this.rows.set(key, [...(this.rows.get(key) ?? []), structuredClone(row)]); }
  async peek(key, limit) { return structuredClone((this.rows.get(key) ?? []).slice(0, limit)); }
  async acknowledge(key, ids) { this.rows.set(key, (this.rows.get(key) ?? []).filter(row => !ids.includes(row.id))); }
  get size() { return [...this.rows.values()].reduce((sum, rows) => sum + rows.length, 0); }
}
const sourceId = "a".repeat(64);
const descriptor = { client_source_id: "source-0001", name: "Test source", adapter: { id: "test-adapter", version: "1.0" }, transport: "ble", capabilities: [] };
const measurement = { metric: "heart_rate", value: 74, unit: "bpm", measured_at: "2026-09-26T10:00:00Z" };
const credential = id => `nsd_${id.repeat(32)}.${"z".repeat(43)}`;
function options(queue, fetch, extra = {}) {
  let count = 0;
  return { apiOrigin: "https://neurasign.example", enrollmentId: "same-user-label", credential: credential("1"), queue,
    newId: () => `reading-${String(++count).padStart(8, "0")}`, fetch, ...extra };
}
const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

test("standard parser handles 8/16-bit values, contact, energy and RR without computing HRV", () => {
  assert.deepEqual(decodeHeartRate(new Uint8Array([0, 74])), { heartRate: 74, contact: null, energyKj: null, rrIntervalsMs: [] });
  assert.deepEqual(decodeHeartRate(new Uint8Array([31, 44, 1, 12, 0, 0, 4, 0, 2])), { heartRate: 300, contact: true, energyKj: 12, rrIntervalsMs: [1000, 500] });
  assert.equal(decodeHeartRate(new Uint8Array([4, 75])).contact, false);
  for (const bytes of [[], [1, 80], [8, 80, 0], [16, 80, 0], [0, 80, 0], [128, 80]]) {
    assert.throws(() => decodeHeartRate(new Uint8Array(bytes)));
  }
});

test("adapter matches the standard service independently of brand and cleans up", async () => {
  let closed = 0;
  const transport = { async connect() { return {
    async *notifications(service, characteristic) {
      assert.equal(service, HEART_RATE_SERVICE); assert.equal(characteristic, HEART_RATE_MEASUREMENT);
      yield { bytes: new Uint8Array([4, 60]), receivedAt: measurement.measured_at };
      yield { bytes: new Uint8Array([0, 74]), receivedAt: measurement.measured_at };
    }, async close() { closed++; },
  }; } };
  const adapter = new StandardHeartRateAdapter(transport, () => "persistent-source-id");
  const registry = new AdapterRegistry(); registry.register(adapter);
  assert.throws(() => registry.register(adapter));
  for (const name of ["Unknown brand", "Another wearable", ""]) {
    assert.equal(registry.matching({ id: "local-id", name, services: ["180D"] }).length, 1);
  }
  assert.equal(registry.matching({ id: "local-id", name: "Heart rate", services: ["180f"] }).length, 0);
  const stream = await adapter.connect({ id: "local-id", name: "Unknown brand", services: [HEART_RATE_SERVICE] }, new AbortController().signal);
  const rows = [];
  for await (const row of stream.measurements) rows.push(row);
  assert.deepEqual(rows, [measurement]);
  assert.equal(stream.descriptor.capabilities[0].timestamp_basis, "phone_receipt");
  await stream.close(); assert.equal(closed, 1);
});

test("lost response preserves IDs and timestamps for an idempotent retry", async () => {
  const queue = new TestQueue(), payloads = [];
  let fail = true;
  const session = new GatewaySession(options(queue, async (url, init) => {
    if (url.endsWith("/sources")) return json({ source: { id: sourceId } });
    assert.equal(init.redirect, "error");
    assert.ok(init.headers.Authorization.startsWith("Bearer nsd_"));
    assert.ok(!url.includes("nsd_"));
    payloads.push(init.body);
    if (fail) { fail = false; throw new Error("Response lost after server accepted the batch"); }
    return json({ accepted: 0, duplicates: 1 });
  }));
  await session.registerSource(descriptor);
  await session.capture(sourceId, measurement);
  await assert.rejects(session.flush(), /Response lost/);
  assert.equal(queue.size, 1);
  assert.equal(await session.flush(), 1);
  assert.equal(queue.size, 0);
  assert.equal(payloads[0], payloads[1]);
  assert.equal(JSON.parse(payloads[0]).observations[0].measured_at, measurement.measured_at);
});

test("company/gateway switches cannot upload an earlier enrollment's queue", async () => {
  const queue = new TestQueue();
  const send = async url => url.endsWith("/sources") ? json({ source: { id: sourceId } }) : json({ accepted: 1, duplicates: 0 });
  const first = new GatewaySession(options(queue, send));
  const other = new GatewaySession(options(queue, send, { credential: credential("2") }));
  await first.registerSource(descriptor); await first.capture(sourceId, measurement);
  await assert.rejects(other.capture(sourceId, measurement), /Register/);
  assert.equal(await other.flush(), 0);
  assert.equal(queue.size, 1);
  assert.equal(await first.flush(), 1);
});

test("concurrent flush shares one request and does not remove readings captured during upload", async () => {
  const queue = new TestQueue();
  let uploads = 0, release, arrived;
  const uploading = new Promise(resolve => { arrived = resolve; });
  const receipt = new Promise(resolve => { release = resolve; });
  const session = new GatewaySession(options(queue, async url => {
    if (url.endsWith("/sources")) return json({ source: { id: sourceId } });
    uploads++; arrived(); await receipt; return json({ accepted: 1, duplicates: 0 });
  }));
  await session.registerSource(descriptor); await session.capture(sourceId, measurement);
  const first = session.flush(), second = session.flush();
  await uploading;
  await session.capture(sourceId, { ...measurement, value: 80 });
  release(); await Promise.all([first, second]);
  assert.equal(uploads, 1); assert.equal(queue.size, 1);
});

test("rejected or malformed receipts never acknowledge queued measurements", async () => {
  for (const response of [json({ detail: "Paused" }, 403), json({ accepted: 0, duplicates: 0 }), new Response("Unavailable", { status: 503 })]) {
    const queue = new TestQueue();
    const session = new GatewaySession(options(queue, async url => url.endsWith("/sources") ? json({ source: { id: sourceId } }) : response));
    await session.registerSource(descriptor); await session.capture(sourceId, measurement);
    await assert.rejects(session.flush()); assert.equal(queue.size, 1);
  }
  assert.equal(new GatewayError(403, "Paused").retryable, false);
  assert.equal(new GatewayError(429, "Slow down").retryable, true);
});

test("gateway requires HTTPS and an isolated local-development override", () => {
  for (const apiOrigin of ["http://company.example", "https://user:secret@company.example", "https://company.example/api", "https://company.example?token=value"]) {
    assert.throws(() => new GatewaySession(options(new TestQueue(), fetch, { apiOrigin, allowLocalHttp: true })));
  }
  assert.doesNotThrow(() => new GatewaySession(options(new TestQueue(), fetch, { apiOrigin: "http://localhost:3000", allowLocalHttp: true })));
});
