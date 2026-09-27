import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const exports = {};
const source = fs.readFileSync(new URL('../lib/applications.ts', import.meta.url), 'utf8');
vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, { exports });
const { matchesApplicationItem, eligibleRecipients, selectTaskCandidates, parseSkills, isTaskPending, isCasePending, provenanceLabel } = exports;

test('combines team, lifecycle and normalized multi-word search without mixing closed work into active lists', () => {
  const item = { team_id: 'north', status: 'in_progress' };
  assert.equal(matchesApplicationItem(item, '  zoe north ', 'north', 'active', 'Zoë Allen · North team'), true);
  assert.equal(matchesApplicationItem(item, 'zoe', 'south', 'active', 'Zoë Allen'), false);
  for (const status of ['completed', 'canceled', 'resolved', 'accepted']) {
    assert.equal(matchesApplicationItem({ ...item, status }, '', '', 'active', ''), false);
    assert.equal(matchesApplicationItem({ ...item, status }, '', '', 'closed', ''), true);
  }
});

test('handover recipient choices respect team grants while preserving organization owners', () => {
  const people = [{ id: 'owner', role: 'owner', team_ids: [] }, { id: 'north', role: 'manager', team_ids: ['north'] }, { id: 'south', role: 'manager', team_ids: ['south'] }, { id: 'employee', role: 'employee', team_ids: ['north'] }];
  assert.deepEqual(Array.from(eligibleRecipients(people, 'north'), item => item.id), ['owner', 'north']);
  assert.equal(people.length, 4);
});

test('candidate search never makes an excluded candidate selectable and preserves eligible recommendation order', () => {
  const people = [{ employee_id: '3', name: 'Zoë Reed', eligible: false }, { employee_id: '2', name: 'Zoe Allen', eligible: true }, { employee_id: '1', name: 'Sam Jones', eligible: true }];
  assert.deepEqual(Array.from(selectTaskCandidates(people, 'zoe', false), item => item.employee_id), ['2']);
  assert.deepEqual(Array.from(selectTaskCandidates(people, '', true), item => item.employee_id), ['2', '1', '3']);
  assert.deepEqual(people.map(item => item.employee_id), ['3', '2', '1']);
});

test('terminal work is not offered for new handovers and provenance stays explicit', () => {
  assert.equal(isTaskPending({ status: 'assigned' }), true);
  assert.equal(isTaskPending({ status: 'canceled' }), false);
  assert.equal(isTaskPending({ status: 'completed' }), false);
  assert.equal(isCasePending({ status: 'in_progress' }), true);
  assert.equal(isCasePending({ status: 'resolved' }), false);
  assert.equal(provenanceLabel('demo'), 'Demo scenario');
  assert.equal(provenanceLabel('human_report'), 'Human-reported');
  assert.equal(provenanceLabel('missing'), 'Not provided');
});

test('skill input normalizes case and duplicates but never invents missing qualifications', () => {
  assert.deepEqual(Array.from(parseSkills(' First Aid, reception, first aid, , ')), ['first aid', 'reception']);
  assert.deepEqual(Array.from(parseSkills(' , ')), []);
});
