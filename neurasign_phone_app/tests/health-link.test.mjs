import test from 'node:test';
import assert from 'node:assert/strict';
import { importAllowed } from '../dist/health-link.js';
import { GatewaySession } from '../dist/gateway.js';

test('health imports cover the whole summary/raw duration at pause and team boundaries', () => {
  const row = { metric: 'hrv_sdnn', unit: 'ms', value: 40, measured_at: new Date(1000000).toISOString(), interval_seconds: 100 };
  assert.equal(importAllowed(row, { paused_intervals: [], team_boundaries: [] }, 1100), true);
  assert.equal(importAllowed(row, { paused_intervals: [{from: 940, until: 950}], team_boundaries: [] }, 1100), false);
  assert.equal(importAllowed(row, { paused_intervals: [], team_boundaries: [950] }, 1100), false);
  const raw = {...row, interval_seconds: undefined, samples: [1, 2], sample_offsets_ms: [-5000, 0]};
  assert.equal(importAllowed(raw, {paused_intervals: [{from: 997, until: null}], team_boundaries: []}, 1100), false);
  assert.equal(importAllowed(row, {paused_intervals: [], team_boundaries: []}, 700000), false);
});

test('a health record replay keeps its externally derived observation ID', async () => {
  const rows=[];
  const gateway = new GatewaySession({ apiOrigin: 'https://example.test', enrollmentId: 'one', credential: `nsd_${'a'.repeat(32)}.${'b'.repeat(43)}`, queue: {append: async (_,row)=>rows.push(row)}, newId: ()=>{throw Error('Replay must use the stable ID');}, fetch: async ()=>new Response(JSON.stringify({source:{id:'c'.repeat(64)}})) });
  const id = await gateway.registerSource({});
  const record = {metric:'heart_rate',unit:'bpm',value:65,measured_at:new Date().toISOString(),source_record_id:'healthkit-uuid'};
  await gateway.capture(id, record, 'same-record-hash'); await gateway.capture(id, record, 'same-record-hash');
  assert.deepEqual(rows[0], rows[1]); gateway.close();
});
