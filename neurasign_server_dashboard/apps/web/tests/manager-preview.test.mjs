import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const exports = {};
const source = fs.readFileSync(new URL('../lib/manager-preview.ts', import.meta.url), 'utf8');
const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
vm.runInNewContext(code, { exports });
const project = (snapshot, connection = 'connected', now = 1000) => JSON.parse(JSON.stringify(exports.toManagerView(snapshot, connection, now)));

function snapshot() {
  return {
    mode: 'replay', source: { kind: 'universe' },
    workers: [{ id: 'alex', name: 'Alex', role: 'Team member', private_note: 'PRIVATE_NOTE', cognitive_state: { cognitive_load: 70, fatigue: 30, readiness: 65, confidence: .77 } }],
    monitoring: { workers: [{
      worker_id: 'alex', status: 'recorded', quality: .95, reference_status: 'personal_recorded_reference_not_verified_rest',
      features: { heart_rate: 151.4321, hrv: 16.1234 }, reference: { heart_rate: 85.6789 },
      recording: { participant: 'PRIVATE_PARTICIPANT' },
      history: [{ time: 60, cognitive_load: 65, fatigue: 25, readiness: 70, heart_rate: 155.1234, eda: 2.54321 }],
    }] },
  };
}

test('manager projection retains individual conclusions even for one person, excluding raw and private fields', () => {
  const view = project(snapshot());
  assert.equal(view.people.length, 1);
  const person = view.people[0];
  assert.equal(person.name, 'Alex');
  assert.equal(person.status, 'review');
  assert.deepEqual(person.indices, { workload: 70, readiness: 65, fatigue: 30 });
  assert.deepEqual(person.history, [{ time: 60, workload: 65, readiness: 70, fatigue: 25 }]);
  assert.doesNotMatch(JSON.stringify(view), /heart_rate|hrv|eda|reference_status|confidence|PRIVATE|151\.4321|155\.1234/);
  assert.match(view.sourceLabel, /UNIVERSE replay/);
});

test('review uses existing demo thresholds and never means safe or fit to work', () => {
  for (const [indices, expected] of [
    [{ cognitive_load: 69.9, fatigue: 59.9, readiness: 45 }, 'no_flag'],
    [{ cognitive_load: 70, fatigue: 30, readiness: 65 }, 'review'],
    [{ cognitive_load: 20, fatigue: 60, readiness: 65 }, 'review'],
    [{ cognitive_load: 20, fatigue: 30, readiness: 44.9 }, 'review'],
  ]) {
    const input = snapshot();
    Object.assign(input.workers[0].cognitive_state, indices);
    const person = project(input).people[0];
    assert.equal(person.status, expected);
    if (expected === 'no_flag') assert.match(person.reason, /not a confirmation of fitness/);
  }
});

test('stale, absent, weak, invalid and offline estimates are unavailable, with no historical index leak', () => {
  const changes = [
    s => { s.monitoring.workers[0].status = 'stale'; },
    s => { s.monitoring.workers[0].status = 'waiting'; },
    s => { s.monitoring.workers = []; },
    s => { s.workers[0].cognitive_state.confidence = .24; },
    s => { s.workers[0].cognitive_state.confidence = NaN; },
    s => { s.workers[0].cognitive_state.fatigue = NaN; },
    s => { s.workers[0].cognitive_state.readiness = 101; },
  ];
  for (const change of changes) {
    const input = snapshot(); change(input);
    const person = project(input).people[0];
    assert.equal(person.status, 'unavailable');
    assert.equal(person.indices, null);
    assert.deepEqual(person.history, []);
  }
  for (const connection of ['offline', 'connecting']) {
    const person = project(snapshot(), connection).people[0];
    assert.equal(person.status, 'unavailable');
    assert.equal(person.indices, null);
    assert.deepEqual(person.history, []);
  }
});

test('live interpretations require recent input and a personal reference', () => {
  const input = snapshot(); input.mode = 'live';
  const signal = input.monitoring.workers[0]; signal.status = 'live';
  signal.last_sample_seconds = 990; signal.reference_status = 'personal_live_reference';
  assert.equal(project(input).people[0].status, 'review');
  signal.last_sample_seconds = 900;
  assert.equal(project(input).people[0].status, 'unavailable');
  signal.last_sample_seconds = 990; signal.reference_status = 'not_personally_calibrated';
  assert.equal(project(input).people[0].status, 'unavailable');
});

test('manual scenarios are explicitly presenter-set and cannot inherit recorded history', () => {
  const input = snapshot(); input.mode = 'manual'; input.workers[0].cognitive_state.confidence = 0;
  const view = project(input);
  assert.equal(view.sourceKind, 'manual');
  assert.match(view.sourceLabel, /presenter/);
  assert.equal(view.people[0].status, 'review');
  assert.deepEqual(view.people[0].history, []);
  assert.equal(project(null), null);
});
