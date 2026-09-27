import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const exports = {};
const source = fs.readFileSync(new URL('../lib/company-roster.ts', import.meta.url), 'utf8');
vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, { exports });
const { selectRoster, rosterPage, personDataStatus, lastReceived, personSource, hasCurrentWearable, legacyDataStatus } = exports;
const teams = [{ id: 'ward', name: 'Ward East' }, { id: 'control', name: 'Control' }];
const member = (id, extra = {}) => ({ id, name: `Person ${id}`, sharing: true, status: 'waiting', ...extra });
const ids = rows => Array.from(rows, row => row.id);

test('combines normalized name/team search, team and data-status filters without altering input order', () => {
  const people = [member('3', { name: 'Zoë Martin', team_id: 'ward', status: 'current', latest: { received_at: 200 } }), member('2', { name: 'Zoe Adams', team_id: 'control', status: 'current', latest: { received_at: 100 } }), member('1', { name: 'Zoe Allen', team_id: 'ward', sharing: false })];
  assert.deepEqual(ids(selectRoster(people, teams, { query: '  zoe   east ', team: 'ward', status: 'current' })), ['3']);
  assert.deepEqual(ids(people), ['3', '2', '1']);
  assert.deepEqual(ids(selectRoster(people, teams, { sharing: 'paused' })), ['1']);
  assert.equal(selectRoster(people, teams, { query: 'missing' }).length, 0);
});

test('paused sharing hides timestamps and source even if a stale response still contains readings', () => {
  const person = member('1', { sharing: false, status: 'current', latest: { received_at: 200, source: 'recording' }, signals: [{ status: 'current', source: 'wearable', latest: { received_at: 300 } }] });
  assert.equal(personDataStatus(person), 'paused');
  assert.equal(lastReceived(person), null);
  assert.equal(personSource(person), 'Measurements hidden');
});

test('uses canonical signal freshness and actual arrival time without treating summaries as live', () => {
  const person = member('1', { status: 'stale', latest: { received_at: 50, source: 'recording' }, signals: [{ status: 'summary', source: 'wearable', latest: { received_at: 250 } }] });
  assert.equal(personDataStatus(person), 'summary');
  assert.equal(lastReceived(person), 250);
  assert.equal(personSource(person), 'Wearable + DEMO RECORDING');
  assert.equal(personDataStatus(member('2', { signals: [{ status: 'current' }] })), 'current');
  assert.equal(personDataStatus(member('3', { status: 'stale', signals: [{ status: 'permission_required', latest: { received_at: 50 } }] })), 'permission_required');
  assert.equal(personDataStatus(member('4', { status: 'stale', signals: [{ status: 'unsupported', latest: { received_at: 50 } }] })), 'unsupported');
});

test('sorts only by name or data arrival, with deterministic ties and missing/paused records last', () => {
  const people = [member('10', { latest: { received_at: 100 } }), member('2', { latest: { received_at: 100 } }), member('3', { latest: { received_at: 300 } }), member('4'), member('5', { sharing: false, latest: { received_at: 500 } })];
  assert.deepEqual(ids(selectRoster(people, [], { sort: 'name' })), ['2', '3', '4', '5', '10']);
  assert.deepEqual(ids(selectRoster(people, [], { sort: 'recent' })), ['3', '2', '10', '4', '5']);
  assert.deepEqual(ids(selectRoster(people, [], { sort: 'oldest' })), ['2', '10', '3', '4', '5']);
});

test('paginates a large roster at25/50 and clamps a removed or filtered final page', () => {
  const people = Array.from({ length: 103 }, (_, index) => member(String(index + 1)));
  const all = selectRoster(people, []);
  const first = rosterPage(all, 0, 25), last = rosterPage(all, 99, 25);
  assert.equal(first.items.length, 25); assert.equal(first.first, 1); assert.equal(first.last, 25); assert.equal(first.pages, 5);
  assert.equal(last.items.length, 3); assert.equal(last.first, 101); assert.equal(last.last, 103); assert.equal(last.page, 4);
  assert.equal(rosterPage(all, 0, 50).items.length, 50);
  assert.equal(rosterPage(all.slice(0, 1), last.page, 25).page, 0);
  assert.equal(rosterPage([], 100, 25).first, 0);
  assert.equal(rosterPage(all, -1, 2000).items.length, 25);
});

test('supports unassigned teams and discards invalid timestamp values from recency', () => {
  assert.deepEqual(ids(selectRoster([member('1'), member('2', { team_id: 'ward' })], teams, { team: 'unassigned' })), ['1']);
  assert.equal(lastReceived(member('1', { latest: { received_at: NaN }, signals: [{ status: 'current', latest: { received_at: Infinity } }] })), null);
});

test('current recording cannot make stale wearable data current, and backfill receipt does not refresh measurement time', () => {
  const person = member('1', { status: 'current', last_received_at: 500, latest: { timestamp: 50, received_at: 100, source: 'wearable' }, signals: [{ status: 'current', source: 'recording', latest: { received_at: 400 } }] });
  assert.equal(lastReceived(person), 500);
  assert.equal(legacyDataStatus(person, 500), 'stale');
  assert.equal(hasCurrentWearable(person, 500), false);
  assert.equal(hasCurrentWearable({ ...person, latest: { ...person.latest, timestamp: 480 } }, 500), true);
  assert.equal(hasCurrentWearable({ ...person, sharing: false }, 500), false);
});
