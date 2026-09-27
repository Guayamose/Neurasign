import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const exports = {};
const source = fs.readFileSync(new URL('../lib/team-attention.ts', import.meta.url), 'utf8');
vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, { exports });
const { classifyAttention, hasCurrentWearableData, summarizeTeam, groupTeams } = exports;
const now = 1000;
const person = (id, extra = {}) => ({ id, name: `Person ${id}`, sharing: true, status: 'waiting', ...extra });
const signal = (status, extra = {}) => ({ status, source: 'wearable', latest: { timestamp: now - 5, received_at: now }, ...extra });
const plain = value => JSON.parse(JSON.stringify(value));

test('partial permission and delayed channels remain visible beside current measurements', () => {
  const partial = person('1', { status: 'current', signals: [signal('current'), signal('delayed'), signal('permission_required')] });
  const attention = classifyAttention(partial, now);
  assert.equal(attention.kind, 'permission');
  assert.equal(attention.issueCount, 2);
  assert.match(attention.nextStep, /permissions/);
  const delayed = { ...partial, signals: partial.signals.slice(0, 2) };
  assert.equal(classifyAttention(delayed, now).kind, 'stale');
  assert.deepEqual(plain(summarizeTeam([partial], now)), { total: 1, currentWearable: 1, attention: 1, paused: 0, summary: 0, waiting: 0 });
});

test('paused sharing suppresses every issue and count even when a response contains old readings', () => {
  const hidden = person('1', { sharing: false, status: 'current', latest: { timestamp: now, received_at: now, source: 'wearable' }, signals: [signal('permission_required'), signal('current')] });
  assert.deepEqual(plain(classifyAttention(hidden, now)), { kind: null, label: 'Sharing paused', nextStep: '', issueCount: 0, priority: 0 });
  assert.deepEqual(plain(summarizeTeam([hidden], now)), { total: 1, currentWearable: 0, attention: 0, paused: 1, summary: 0, waiting: 0 });
  assert.equal(classifyAttention({ ...hidden, sharing: true, status: 'paused' }, now).kind, null);
});

test('valid daily summaries override the aggregate stale flag and do not become live measurements', () => {
  const daily = person('1', { status: 'stale', signals: [signal('summary', { measurement_kind: 'summary', latest: { timestamp: now - 86400, received_at: now } })] });
  assert.equal(classifyAttention(daily, now).kind, null);
  assert.deepEqual(plain(summarizeTeam([daily], now)), { total: 1, currentWearable: 0, attention: 0, paused: 0, summary: 1, waiting: 0 });
});

test('recent uploads cannot freshen delayed measurements; a recording cannot stand in for a wearable', () => {
  const late = person('1', { status: 'current', latest: { timestamp: now - 300, received_at: now, source: 'wearable' }, signals: [signal('current', { source: 'recording' })] });
  assert.equal(classifyAttention(late, now).kind, 'stale');
  assert.equal(summarizeTeam([late], now).currentWearable, 0);
  assert.equal(classifyAttention(person('2', { signals: [signal('delayed', { latest: { timestamp: now - 300, received_at: now } })] }), now).kind, 'stale');
  const recording = person('3', { signals: [signal('current', { source: 'recording' })] });
  assert.equal(classifyAttention(recording, now).kind, null);
  assert.equal(summarizeTeam([recording], now).currentWearable, 0);
});

test('canonical and legacy wearable feeds remain independent because source is not a device identity', () => {
  const mixed = person('1', { latest: { timestamp: now - 300, received_at: now, source: 'wearable' }, signals: [signal('current')] });
  assert.equal(classifyAttention(mixed, now).kind, 'stale');
  assert.equal(summarizeTeam([mixed], now).currentWearable, 1);
  const dailyAndLive = person('2', { latest: { timestamp: now, received_at: now, source: 'wearable' }, signals: [signal('summary')] });
  assert.equal(classifyAttention(dailyAndLive, now).kind, null);
  assert.equal(summarizeTeam([dailyAndLive], now).currentWearable, 1);
});

test('unsupported capability is informative, never an attention alert by itself', () => {
  const unsupported = person('1', { signals: [signal('unsupported', { latest: null })] });
  const partial = person('2', { signals: [signal('current'), signal('unsupported', { latest: null })] });
  assert.equal(classifyAttention(unsupported, now).label, 'No supported measurements');
  assert.equal(classifyAttention(partial, now).label, 'Some signals unavailable');
  assert.equal(classifyAttention(partial, now).issueCount, 1);
  assert.equal(classifyAttention(partial, now).priority, 0);
  assert.equal(summarizeTeam([unsupported, partial], now).attention, 0);
});

test('waiting means setup and a missing partial signal does not imply an unpaired phone', () => {
  const waiting = person('1');
  assert.equal(classifyAttention(waiting, now).kind, 'setup');
  assert.match(classifyAttention(waiting, now).nextStep, /phone setup/);
  const partial = person('2', { signals: [signal('current'), signal('waiting', { latest: null })] });
  assert.equal(classifyAttention(partial, now).label, 'Waiting for a signal');
  assert.doesNotMatch(classifyAttention(partial, now).nextStep, /connect a phone/);
  assert.equal(summarizeTeam([partial], now).waiting, 1);
  assert.equal(classifyAttention(person('3', { signals: [signal('current', { latest: null })] }), now).kind, 'setup');
});

test('freshness uses measurement time, accepts permitted skew and rejects impossible current readings', () => {
  const legacy = timestamp => person('1', { status: 'current', latest: { timestamp, received_at: now, source: 'wearable' } });
  assert.equal(classifyAttention(legacy(now - 60), now).kind, null);
  assert.equal(classifyAttention(legacy(now - 61), now).kind, 'stale');
  assert.equal(classifyAttention(legacy(now + 5), now).kind, null);
  assert.equal(classifyAttention(legacy(now + 6), now).kind, 'stale');
  for (const timestamp of [undefined, NaN, Infinity, 0]) assert.equal(classifyAttention(legacy(timestamp), now).kind, 'stale');
  const future = person('2', { signals: [signal('current', { latest: { timestamp: now + 30, received_at: now } })] });
  assert.equal(classifyAttention(future, now).kind, 'stale');
  assert.equal(summarizeTeam([future], now).currentWearable, 0);
});

test('current wearable drill-down exactly matches its summary count through legacy and canonical edge cases', () => {
  const people = [
    person('fresh', { signals: [signal('current')] }),
    person('partial', { signals: [signal('current'), signal('permission_required')] }),
    person('recording', { signals: [signal('current', { source: 'recording' })] }),
    person('paused', { sharing: false, signals: [signal('current')] }),
    person('future', { signals: [signal('current', { latest: { timestamp: now + 6, received_at: now } })] }),
    person('late', { signals: [signal('current', { latest: { timestamp: now - 61, received_at: now } })] }),
    person('daily', { signals: [signal('summary')] }),
    person('independent', { latest: { timestamp: now, received_at: now, source: 'wearable' }, signals: [signal('permission_required')] }),
    person('legacy', { latest: { timestamp: now, received_at: now, source: 'wearable' } }),
  ];
  const filtered = people.filter(row => hasCurrentWearableData(row, now));
  assert.deepEqual(filtered.map(row => row.id), ['fresh', 'partial', 'independent', 'legacy']);
  assert.equal(summarizeTeam(people, now).currentWearable, filtered.length);
});

test('empty and filtered team groups are stable, preserve people, and sort by connection attention then name', () => {
  assert.deepEqual(plain(summarizeTeam([], now)), { total: 0, currentWearable: 0, attention: 0, paused: 0, summary: 0, waiting: 0 });
  assert.deepEqual(plain(groupTeams([], [], now)), []);
  const teams = [{ id: 'south', name: 'South' }, { id: 'north', name: 'North' }, { id: 'empty', name: 'Empty' }];
  const people = [person('1', { team_id: 'north', signals: [signal('current')] }), person('2', { team_id: 'south' }), person('3'), person('4', { team_id: 'hidden', sharing: false })];
  const before = JSON.stringify({ teams, people });
  const groups = groupTeams(people, teams, now);
  assert.deepEqual(Array.from(groups, group => group.id), ['south', 'unassigned', 'empty', 'north', 'hidden']);
  assert.equal(groups.reduce((total, group) => total + group.summary.total, 0), people.length);
  assert.equal(JSON.stringify({ teams, people }), before);
  const filtered = groupTeams(people.filter(row => row.team_id === 'north'), teams, now);
  assert.equal(filtered.find(group => group.id === 'south').summary.total, 0);
  assert.equal(filtered.find(group => group.id === 'north').summary.currentWearable, 1);
});
