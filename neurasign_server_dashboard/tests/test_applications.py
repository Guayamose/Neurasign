"""Persistent operational transitions, concurrent assignment, scopes and privacy."""
from concurrent.futures import ThreadPoolExecutor
import json
from uuid import uuid4

import pytest

from neurasign import applications
from neurasign.identity import Identity, get_store
from neurasign.store import SQLiteStore
from neurasign.workspace import digest
from test_workspace import workspace, headers, company, add_member, device, upload, reading, PEOPLE
from test_onboarding import setup, create_person, manager
from test_telemetry import source, row, upload as observations_upload


@pytest.fixture
def apps(setup):
    client, store, org, team_a, team_b = setup
    client.app.include_router(applications.router)
    return client, store, org, team_a, team_b


def base(org):
    return f'/api/v1/organizations/{org}/applications'


def request(**values):
    return {'request_id': uuid4().hex, **values}


def context(client, org, person, **changes):
    value = {'version': 0, 'skills': ['Triage'], 'availability': 'available', 'max_active_tasks': 2, 'context_note': 'Availability confirmed for this shift.', **changes}
    response = client.patch(base(org) + f'/people/{person}/context', headers=headers(), json=value)
    assert response.status_code == 200, response.text
    return response.json()


def task(client, org, team, **changes):
    response = client.post(base(org) + '/tasks', headers=headers(), json=request(title='Review the queue', team_id=team, required_skills=['triage'], priority='normal', **changes))
    assert response.status_code == 200, response.text
    return response.json()


def case(client, org, person):
    response = client.post(base(org) + '/cases', headers=headers(), json=request(employee_id=person, category='workload', summary='Employee requested additional queue coverage.', priority='high'))
    assert response.status_code == 200, response.text
    return response.json()


def test_assignment_requires_human_context_and_is_persisted_idempotent(apps):
    client, store, org, team, _ = apps
    person = create_person(client, org, team)
    work = task(client, org, team)
    candidates = client.get(base(org) + f'/tasks/{work["id"]}/candidates', headers=headers()).json()['candidates']
    assert not candidates[0]['eligible'] and candidates[0]['missing']
    body = request(version=1, employee_id=person)
    url = base(org) + f'/tasks/{work["id"]}/assign'
    assert client.post(url, headers=headers(), json=body).status_code == 409
    saved_context = context(client, org, person)
    assert saved_context['skills'] == ['triage'] and saved_context['interpretation'] is None
    assert client.patch(base(org) + f'/people/{person}/context', headers=headers(), json={'version': 0, 'skills': [], 'availability': 'busy', 'max_active_tasks': 2}).status_code == 409
    result = client.post(url, headers=headers(), json=body)
    assert result.status_code == 200, result.text
    assert result.json()['status'] == 'assigned' and result.json()['version'] == 2
    assert client.post(url, headers=headers(), json=body).json() == result.json()
    assert client.post(url, headers=headers(), json={**body, 'version': 2}).status_code == 409
    client.app.dependency_overrides[get_store] = lambda: SQLiteStore(store.path)
    snapshot = client.get(base(org), headers=headers()).json()
    assert snapshot['tasks'][0]['assignee_id'] == person and snapshot['people'][0]['active_task_count'] == 1
    assert snapshot['people'][0]['provenance'] == 'human_report'
    transition = base(org) + f'/tasks/{work["id"]}/transition'
    done = client.post(transition, headers=headers(), json=request(version=2, action='complete')).json()
    assert done['status'] == 'completed'
    assert client.post(transition, headers=headers(), json=request(version=done['version'], action='start')).status_code == 409


def test_competing_assignments_cannot_exceed_capacity(apps):
    client, store, org, team, _ = apps
    person = create_person(client, org, team)
    context(client, org, person, max_active_tasks=1)
    work = [task(client, org, team) for _ in range(2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda value: client.post(base(org) + f'/tasks/{value["id"]}/assign', headers=headers(), json=request(version=1, employee_id=person)), work))
    assert sorted(value.status_code for value in results) == [200, 409]
    assert client.get(base(org), headers=headers()).json()['people'][0]['active_task_count'] == 1


def test_support_case_blocks_assignment_until_recorded_action_and_resolution(apps):
    client, store, org, team, _ = apps
    person = create_person(client, org, team)
    context(client, org, person)
    support = case(client, org, person)
    work = task(client, org, team)
    assign = base(org) + f'/tasks/{work["id"]}/assign'
    assert client.post(assign, headers=headers(), json=request(version=1, employee_id=person)).status_code == 409
    endpoint = base(org) + f'/cases/{support["id"]}'
    assert client.post(endpoint + '/resolve', headers=headers(), json=request(version=1, note='Coverage agreed')).status_code == 409
    action_body = request(version=1, kind='coverage', note='Manager arranged queue coverage with the employee.')
    acted = client.post(endpoint + '/actions', headers=headers(), json=action_body).json()
    assert acted['status'] == 'in_progress' and len(acted['actions']) == 1
    assert client.post(endpoint + '/actions', headers=headers(), json=action_body).json() == acted
    resolved = client.post(endpoint + '/resolve', headers=headers(), json=request(version=2, note='Employee confirmed the coverage is sufficient.')).json()
    assert resolved['status'] == 'resolved'
    assert client.post(assign, headers=headers(), json=request(version=1, employee_id=person)).status_code == 200


def test_handover_recipient_accepts_atomically_and_preserves_employee(apps):
    client, store, org, team, _ = apps
    manager(client, org, [team])
    person = create_person(client, org, team)
    context(client, org, person)
    work = task(client, org, team)
    assigned = client.post(base(org) + f'/tasks/{work["id"]}/assign', headers=headers(), json=request(version=1, employee_id=person)).json()
    support = case(client, org, person)
    body = request(title='Shift coverage', team_id=team, recipient_member_id=digest(PEOPLE['manager'].uid), task_ids=[work['id']], case_ids=[support['id']], note='Review these pending items.')
    result = client.post(base(org) + '/handovers', headers=headers(), json=body)
    assert result.status_code == 200, result.text
    handover = result.json()
    url = base(org) + f'/handovers/{handover["id"]}/accept'
    acceptance = request(version=1)
    assert client.post(url, headers=headers(), json=acceptance).status_code == 403
    accepted = client.post(url, headers=headers('manager'), json=acceptance)
    assert accepted.status_code == 200, accepted.text
    assert client.post(url, headers=headers('manager'), json=acceptance).json() == accepted.json()
    snapshot = client.get(base(org), headers=headers()).json()
    assert snapshot['tasks'][0]['assignee_id'] == person
    assert snapshot['cases'][0]['employee_id'] == person
    assert snapshot['tasks'][0]['responsible_member_id'] == snapshot['cases'][0]['responsible_member_id'] == digest(PEOPLE['manager'].uid)


def test_changed_handover_work_rolls_back_every_transfer(apps):
    client, store, org, team, _ = apps
    manager(client, org, [team])
    person = create_person(client, org, team)
    work, support = task(client, org, team), case(client, org, person)
    handover = client.post(base(org) + '/handovers', headers=headers(), json=request(title='Shift coverage', team_id=team, recipient_member_id=digest(PEOPLE['manager'].uid), task_ids=[work['id']], case_ids=[support['id']])).json()
    client.post(base(org) + f'/cases/{support["id"]}/actions', headers=headers(), json=request(version=1, kind='check_in', note='Discussed queue coverage.'))
    result = client.post(base(org) + f'/handovers/{handover["id"]}/accept', headers=headers('manager'), json=request(version=1))
    assert result.status_code == 409
    snapshot = client.get(base(org), headers=headers()).json()
    assert snapshot['tasks'][0]['responsible_member_id'] == digest(PEOPLE['owner'].uid)
    assert snapshot['tasks'][0]['version'] == 1 and snapshot['handovers'][0]['status'] == 'pending'


def test_scope_enforced_on_every_mutation_and_receipt_replay(apps):
    client, store, org, team_a, team_b = apps
    manager(client, org, [team_a])
    add_member(client, org, 'employee')
    other = company(client, 'outsider')
    person = create_person(client, org, team_b)
    work = task(client, org, team_b)
    assert client.get(base(org), headers=headers('employee')).status_code == 403
    assert client.get(base(org), headers=headers('outsider')).status_code == 403
    snapshot = client.get(base(org), headers=headers('manager')).json()
    assert not snapshot['people'] and not snapshot['tasks'] and len(snapshot['teams']) == 1
    assert client.get(base(org) + f'/tasks/{work["id"]}/candidates', headers=headers('manager')).status_code == 403
    assert client.post(base(org) + '/cases', headers=headers('manager'), json=request(employee_id=person, category='other', summary='Check coverage')).status_code == 403
    assert client.patch(base(org) + f'/people/{person}/context', headers=headers('manager'), json={'version': 0, 'skills': [], 'availability': 'available', 'max_active_tasks': 2}).status_code == 403
    body = request(title='Scoped task', team_id=team_a, required_skills=[])
    assert client.post(base(org) + '/tasks', headers=headers('manager'), json=body).status_code == 200
    key = f'organizations/{org}/members/{digest(PEOPLE["manager"].uid)}'
    store.atomic(lambda tx: tx.put(key, {**tx.get(key), 'team_ids': []}))
    assert client.post(base(org) + '/tasks', headers=headers('manager'), json=body).status_code == 403


def test_roles_do_not_grant_physiology_but_connection_and_own_readings_work(apps):
    client, store, org, team, _ = apps
    add_member(client, org, 'employee')
    connection = device(client, org)
    assert upload(client, connection['credential'], [reading()]).status_code == 200
    person = digest(PEOPLE['employee'].uid)
    dashboard = f'/api/v1/organizations/{org}/dashboard'
    owner = client.get(dashboard, headers=headers()).json()['members'][0]
    assert owner['latest'] is None and not owner['signals'] and all(value is None for value in owner['features'].values())
    assert owner['connection']['status'] == 'current' and owner['connection']['last_received_at']
    assert not owner['measurements_access']
    assert client.get(f'/api/v1/organizations/{org}/members/{person}/history', headers=headers()).status_code == 403
    assert client.get(dashboard, headers=headers('employee')).json()['members'][0]['features']['heart_rate'] == 75
    src = source(client, connection).json()['source']['id']
    assert observations_upload(client, connection, row(src)).status_code == 200
    series = client.get(dashboard, headers=headers('employee')).json()['members'][0]['signals'][0]['series_id']
    endpoint = f'/api/v1/organizations/{org}/members/{person}/observations?series_id={series}'
    assert client.get(endpoint, headers=headers()).status_code == 403
    key = f'organizations/{org}/members/{digest(PEOPLE["owner"].uid)}'
    store.atomic(lambda tx: tx.put(key, {**tx.get(key), 'can_view_measurements': True}))
    assert client.get(endpoint, headers=headers()).json()['observations'][0]['value'] == 74


def test_demo_is_explicit_local_isolated_reusable_and_has_no_measurements(apps, monkeypatch):
    client, store, org, team, _ = apps
    assert client.post('/api/v1/applications/demo', headers=headers()).status_code == 403
    demo_user = Identity('neurasign-local-test-user', 'demo@neurasign.test', 'Taylor')
    monkeypatch.setitem(PEOPLE, 'demo', demo_user)
    monkeypatch.setattr(applications, 'local_test_account', lambda: {'email': demo_user.email})
    response = client.post('/api/v1/applications/demo', headers=headers('demo'))
    assert response.status_code == 200, response.text
    demo = response.json()['organization']['id']
    assert demo != org and response.json()['created']
    snapshot = client.get(base(demo), headers=headers('demo')).json()
    assert len(snapshot['people']) == 36 and len(snapshot['teams']) == 4
    assert snapshot['organization']['is_demo'] and all(person['interpretation']['source'] == 'illustrative' for person in snapshot['people'])
    assert all(person['provenance'] == 'demo' for person in snapshot['people'])
    assert client.get(base(org), headers=headers()).json()['people'] == []
    assert client.get(base(demo), headers=headers()).status_code == 403
    assert not client.post('/api/v1/applications/demo', headers=headers('demo')).json()['created']
    assert len(client.get(base(demo), headers=headers('demo')).json()['tasks']) == 12
    dashboard = client.get(f'/api/v1/organizations/{demo}/dashboard', headers=headers('demo')).json()
    assert not dashboard['devices'] and all(not person['signals'] and person['latest'] is None for person in dashboard['members'])
    assert all(person['connection']['status'] == 'demo' for person in dashboard['members'])
    assert {case['category'] for case in snapshot['cases']} == {'break_request', 'coverage', 'workload', 'other'}
    assert all(person['interpretation']['readiness']['level'] in ('limited', 'fair', 'good') for person in snapshot['people'])
    for key in ('heart_rate', 'hrv', 'eda', 'temperature', 'movement', 'samples'):
        assert key not in json.dumps(snapshot)
    monkeypatch.setattr(applications, 'local_test_account', lambda: None)
    assert client.post('/api/v1/applications/demo', headers=headers('demo')).status_code == 403


def test_demo_seed_migration_preserves_human_work_and_pending_handover_versions(apps, monkeypatch):
    client, store, org, team, _ = apps
    demo_user = Identity('neurasign-local-test-user', 'demo@neurasign.test', 'Taylor')
    monkeypatch.setitem(PEOPLE, 'demo', demo_user)
    monkeypatch.setattr(applications, 'local_test_account', lambda: {'email': demo_user.email})
    demo = client.post('/api/v1/applications/demo', headers=headers('demo')).json()['organization']['id']
    case_ids = [digest(f'{demo}:case:{index}')[:32] for index in range(2)]
    handover_id = digest(f'{demo}:handover:0')[:32]
    def previous_seed(tx):
        organization = tx.get(f'organizations/{demo}')
        tx.put(f'organizations/{demo}', {**organization, 'name': 'Northstar Operations — Sample Company', 'applications_demo_seed_version': 1})
        for index, key in enumerate(case_ids):
            value = tx.get(applications.path(demo, 'cases', key))
            tx.put(applications.path(demo, 'cases', key), {**value, 'summary': 'Human-reviewed coverage plan.' if index else 'Sample report: extra queue coverage is needed during this shift.', 'version': 2 if index else 1})
    store.atomic(previous_seed)
    result = client.post('/api/v1/applications/demo', headers=headers('demo')).json()
    assert not result['created'] and result['organization']['name'] == 'Northstar Operations'
    migrated = store.get(applications.path(demo, 'cases', case_ids[0]))
    untouched_human = store.get(applications.path(demo, 'cases', case_ids[1]))
    assert migrated['version'] == 2 and migrated['summary'].startswith('Break requested')
    assert untouched_human['summary'] == 'Human-reviewed coverage plan.' and untouched_human['version'] == 2
    handover = store.get(applications.path(demo, 'handovers', handover_id))
    assert handover['item_versions'][f'cases:{case_ids[0]}'] == 2
    accepted = client.post(base(demo) + f'/handovers/{handover_id}/accept', headers=headers('demo'), json=request(version=handover['version']))
    assert accepted.status_code == 200, accepted.text
    client.post('/api/v1/applications/demo', headers=headers('demo'))
    assert store.get(applications.path(demo, 'handovers', handover_id))['status'] == 'accepted'


def test_manager_measurement_capability_is_not_implied_by_team_membership(apps):
    from test_onboarding import claim, enrollment
    client, store, org, team, other_team = apps
    manager(client, org, [team])
    person = create_person(client, org, team)
    connection = claim(client, enrollment(client, org, person).json()['token'])
    src = source(client, connection).json()['source']['id']
    assert observations_upload(client, connection, row(src)).status_code == 200
    snapshot = client.get(f'/api/v1/organizations/{org}/dashboard', headers=headers('manager')).json()['members'][0]
    assert snapshot['connection']['current_count'] == 1 and snapshot['connection']['last_received_at']
    assert not snapshot['measurements_access'] and not snapshot['signals'] and snapshot['latest'] is None
    series = next(iter(store.get(f'organizations/{org}/signal_state/{person}')['latest']))
    url = f'/api/v1/organizations/{org}/members/{person}/observations?series_id={series}'
    assert client.get(url, headers=headers('manager')).status_code == 403
    key = f'organizations/{org}/members/{digest(PEOPLE["manager"].uid)}'
    store.atomic(lambda tx: tx.put(key, {**tx.get(key), 'can_view_measurements': True}))
    assert client.get(url, headers=headers('manager')).json()['observations'][0]['value'] == 74
    store.atomic(lambda tx: tx.put(key, {**tx.get(key), 'team_ids': [other_team]}))
    assert client.get(url, headers=headers('manager')).status_code == 403


def test_assignment_eligibility_checks_skills_availability_team_and_terminal_state(apps):
    client, store, org, team, other_team = apps
    person = create_person(client, org, team)
    wrong_team = create_person(client, org, other_team, 'Morgan')
    context(client, org, person, skills=['inventory'], availability='busy')
    context(client, org, wrong_team)
    work = task(client, org, team)
    url = base(org) + f'/tasks/{work["id"]}/assign'
    assert client.post(url, headers=headers(), json=request(version=1, employee_id=person)).status_code == 409
    assert client.post(url, headers=headers(), json=request(version=1, employee_id=wrong_team)).status_code == 409
    context(client, org, person, version=1)
    assert client.post(url, headers=headers(), json=request(version=1, employee_id=person)).status_code == 200
    complete = client.post(base(org) + f'/tasks/{work["id"]}/transition', headers=headers(), json=request(version=2, action='complete')).json()
    assert client.post(url, headers=headers(), json=request(version=complete['version'], employee_id=person)).status_code == 409


def test_recipient_scope_revocation_and_cross_team_handover_cannot_transfer(apps):
    client, store, org, team, other_team = apps
    manager(client, org, [team])
    work = task(client, org, team)
    other = task(client, org, other_team)
    body = request(title='Shift change', team_id=team, recipient_member_id=digest(PEOPLE['manager'].uid), task_ids=[other['id']], case_ids=[])
    assert client.post(base(org) + '/handovers', headers=headers(), json=body).status_code == 409
    body['task_ids'] = [work['id']]
    handover = client.post(base(org) + '/handovers', headers=headers(), json=body).json()
    key = f'organizations/{org}/members/{digest(PEOPLE["manager"].uid)}'
    store.atomic(lambda tx: tx.put(key, {**tx.get(key), 'team_ids': []}))
    url = base(org) + f'/handovers/{handover["id"]}/accept'
    assert client.post(url, headers=headers('manager'), json=request(version=1)).status_code == 403
    assert store.get(applications.path(org, 'tasks', work['id']))['responsible_member_id'] == digest(PEOPLE['owner'].uid)
    assert store.get(applications.path(org, 'handovers', handover['id']))['status'] == 'pending'


def test_connection_receipt_is_hidden_when_sharing_pauses_with_stored_data(apps):
    client, store, org, _, _ = apps
    add_member(client, org, 'employee')
    connection = device(client, org)
    person_id = digest(PEOPLE['employee'].uid)
    assert upload(client, connection['credential'], [reading()]).status_code == 200
    source_id = source(client, connection).json()['source']['id']
    assert observations_upload(client, connection, row(source_id)).status_code == 200
    endpoint = f'/api/v1/organizations/{org}/dashboard'
    before = client.get(endpoint, headers=headers()).json()['members'][0]['connection']
    assert before['last_received_at'] is not None and before['status'] == 'current'
    assert client.patch(f'/api/v1/organizations/{org}/me/sharing', headers=headers('employee'), json={'enabled': False}).status_code == 200
    # Pausing leaves persisted readings and gateway receipt metadata intact.
    assert store.get(f'organizations/{org}/latest/{person_id}')['received_at']
    assert store.get(f'organizations/{org}/signal_state/{person_id}')['latest']
    assert store.get(f'organizations/{org}/devices/{connection["device"]["id"]}')['last_received_at']
    after = client.get(endpoint, headers=headers()).json()['members'][0]['connection']
    assert after == {'status': 'paused', 'current_count': 0, 'issue_count': 0,
                     'last_received_at': None, 'issue_kind': None, 'next_step': None}


@pytest.mark.parametrize('kind', ['unsupported', 'summary', 'mixed'])
def test_unsupported_and_period_summary_do_not_raise_connection_attention(apps, kind):
    from test_telemetry import capability
    client, store, org, _, _ = apps
    add_member(client, org, 'employee')
    connection = device(client, org)
    capabilities = []
    if kind != 'summary':
        capabilities.append(capability(availability='unsupported'))
    if kind != 'unsupported':
        capabilities.append(capability('hrv_sdnn', 'ms', measurement_kind='summary', delivery_mode='sync', interval_seconds=28800))
    source_id = source(client, connection, capabilities).json()['source']['id']
    if kind != 'unsupported':
        assert observations_upload(client, connection, row(source_id, 'hrv_sdnn', 85, 'ms')).status_code == 200
    person = client.get(f'/api/v1/organizations/{org}/dashboard', headers=headers()).json()['members'][0]
    metadata = person['connection']
    assert metadata['status'] == ('unsupported' if kind == 'unsupported' else 'summary')
    assert metadata['issue_count'] == 0 and metadata['current_count'] == 0
    assert metadata['issue_kind'] is None and metadata['next_step'] is None
    assert bool(metadata['last_received_at']) == (kind != 'unsupported')
    assert person['latest'] is None and not person['signals'] and not person['measurements_access']


@pytest.mark.parametrize('kind', ['waiting', 'delayed', 'permission_required'])
def test_actionable_connection_states_still_raise_attention(apps, kind):
    from test_telemetry import capability
    client, store, org, _, _ = apps
    add_member(client, org, 'employee')
    connection = device(client, org)
    source_id = source(client, connection, [capability(availability='permission_required' if kind == 'permission_required' else 'available')]).json()['source']['id']
    if kind == 'delayed':
        assert observations_upload(client, connection, row(source_id, age=120)).status_code == 200
    metadata = client.get(f'/api/v1/organizations/{org}/dashboard', headers=headers()).json()['members'][0]['connection']
    assert metadata['issue_count'] == 1
    assert metadata['issue_kind'] == ('stale' if kind == 'delayed' else kind)
    assert metadata['next_step']
