/** Local integration fixture: explicit recorded input, no hardware claim. */
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { GatewaySession } from "../dist/gateway.js";
import { decodeHeartRate } from "../dist/heart-rate.js";

const origin = process.env.NEURASIGN_TEST_ORIGIN;
assert.equal(origin, "http://localhost:3000", "This fixture only targets local development.");
const config = await (await fetch(`${origin}/api/v1/config`)).json();
assert.equal(config.firebase.projectId, "demo-neurasign");
assert.ok(config.emulator_url);
const data = new Map();
const queue = {
  async append(key, row) { data.set(key, [...(data.get(key) ?? []), structuredClone(row)]); },
  async peek(key, limit) { return structuredClone((data.get(key) ?? []).slice(0, limit)); },
  async acknowledge(key, ids) { data.set(key, (data.get(key) ?? []).filter(row => !ids.includes(row.id))); },
};
const session = new GatewaySession({ apiOrigin: origin, enrollmentId: "local-contract-fixture", credential: process.env.NEURASIGN_TEST_GATEWAY_CREDENTIAL,
  queue, newId: randomUUID, allowLocalHttp: true });
const capability = (metric, unit, changes = {}) => ({ metric, unit, delivery_mode: "stream", measurement_kind: "sample", method: "recorded-fixture", ...changes });
const sourceId = await session.registerSource({ client_source_id: "contract-fixture-001", name: "Recorded test input", transport: "recording",
  adapter: { id: "contract-fixture", version: "1.0.0" }, capabilities: [
    capability("heart_rate", "bpm"), capability("skin_temperature", "°F"),
    capability("hrv_sdnn", "ms", { delivery_mode: "sync", measurement_kind: "summary", interval_seconds: 28800 }),
    capability("electrodermal_conductance", "µS", { availability: "unsupported" }),
  ] });
const now = Date.now();
for (let index = 0; index < 4; index++) {
  const decoded = decodeHeartRate(new Uint8Array([0, 72 + index]));
  await session.capture(sourceId, { metric: "heart_rate", value: decoded.heartRate, unit: "bpm", measured_at: new Date(now - (3 - index) * 10000).toISOString() });
}
await session.capture(sourceId, { metric: "skin_temperature", value: 86, unit: "°F", measured_at: new Date(now - 120000).toISOString() });
await session.capture(sourceId, { metric: "hrv_sdnn", value: 58, unit: "ms", measured_at: new Date(now - 3600000).toISOString() });
assert.equal(await session.flush(), 6);
assert.equal(await session.flush(), 0);
process.stdout.write(JSON.stringify({ source_id: sourceId, uploaded: 6 }));
