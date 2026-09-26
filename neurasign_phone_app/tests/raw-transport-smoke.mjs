/** Explicit UNIVERSE recording -> real gateway core -> local test API. */
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { GatewaySession } from '../dist/gateway.js';

const origin = process.env.NEURASIGN_TEST_ORIGIN;
assert.equal(origin, 'http://localhost:3000');
const config = await (await fetch(`${origin}/api/v1/config`)).json();
assert.equal(config.firebase.projectId, 'demo-neurasign');
assert.ok(config.emulator_url);
const { descriptor, measurements } = JSON.parse(readFileSync(process.argv[2], 'utf8'));
assert.equal(descriptor.transport, 'recording');
const pending = [];
const queue = {
  async append(_key, row) { pending.push(structuredClone(row)); },
  async peek(_key, limit) { return structuredClone(pending.slice(0, limit)); },
  async acknowledge(_key, ids) { for (let i = pending.length - 1; i >= 0; i--) if (ids.includes(pending[i].id)) pending.splice(i, 1); },
};
let lost = false;
const receipts = [];
const session = new GatewaySession({ apiOrigin: origin, enrollmentId: 'universe-raw-test',
  credential: process.env.NEURASIGN_TEST_GATEWAY_CREDENTIAL, queue, newId: randomUUID, allowLocalHttp: true,
  fetch: async (url, init) => {
    const result = await fetch(url, init);
    if (url.endsWith('/observations') && result.ok) {
      receipts.push(await result.clone().json());
      if (!lost) { lost = true; throw new Error('Intentional lost acknowledgment'); }
    }
    return result;
  },
});
const source = await session.registerSource(descriptor);
for (const row of measurements) await session.capture(source, row);
await assert.rejects(session.flush(), /Intentional lost acknowledgment/);
assert.equal(pending.length, measurements.length);
while (pending.length) await session.flush();
assert.ok(receipts.some(receipt => receipt.duplicates > 0));
process.stdout.write(JSON.stringify({ uploaded: measurements.length }));
