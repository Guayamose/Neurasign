"""End-to-end authorization: accounts, teams, employees, QR claims and ingestion."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import secrets
import time

import pytest

from neurasign.onboarding import router
from neurasign.telemetry import router as telemetry_router
from neurasign.workspace import digest
from test_workspace import workspace, headers, company, PEOPLE, device, reading, upload as legacy_upload
from test_telemetry import source, row, upload


@pytest.fixture
def setup(workspace):
    client, store, app = workspace
    app.include_router(router)
    app.include_router(telemetry_router)
    org = company(client)
    def team(name):
        result = client.post(f'/api/v1/organizations/{org}/teams', headers=headers(), json={'name': name})
        assert result.status_code == 201, result.text
        return result.json()['id']
    return client, store, org, team('Operations'), team('Engineering')


def create_person(client, org, team, name='Sam', user='owner'):
    response = client.post(f'/api/v1/organizations/{org}/employees', headers=headers(user), json={'name': name, 'team_id': team})
    assert response.status_code == 201, response.text
    return response.json()['id']


def manager(client, org, teams, user='manager'):
    result = client.post(f'/api/v1/organizations/{org}/invitations', headers=headers(),
        json={'email': PEOPLE[user].email, 'role': 'manager', 'team_ids': teams})
    assert result.status_code == 201, result.text
    result = client.post('/api/v1/invitations/accept', headers=headers(user), json={'token': result.json()['token']})
    assert result.status_code == 200, result.text


def enrollment(client, org, person, user='owner', source='wearable'):
    return client.post(f'/api/v1/organizations/{org}/employees/{person}/enrollments', headers=headers(user), json={'source': source})


def claim_body(token):
    return {'token': token, 'installation_id': secrets.token_hex(16), 'claim_secret': secrets.token_urlsafe(32), 'phone_name': 'Sam’s phone', 'consent': True}


def claim(client, token):
    response = client.post('/api/v1/gateway/enrollment/claim', json=claim_body(token))
    assert response.status_code == 200, response.text
    return response.json()


def snapshot(client, org, user='owner'):
    return client.get(f'/api/v1/organizations/{org}/dashboard', headers=headers(user)).json()


def test_employees_need_no_login_and_qr_connects_to_the_right_company(setup):
    client, store, org, team_a, team_b = setup
    person = create_person(client, org, team_a)
    assert store.get(f'organizations/{org}/members/{person}') is None
    assert len(snapshot(client, org)['accounts']) == 1
    token = enrollment(client, org, person).json()['token']
    preview = client.post('/api/v1/gateway/enrollment/preview', json={'token': token}).json()
    assert preview['employee'] == 'Sam' and preview['team'] == 'Operations'
    connection = claim(client, token)
    assert connection['organization_id'] == org and connection['employee_id'] == person
    assert connection['credential'] not in str(store.get(f'device_keys/{connection["gateway_id"]}'))
    status = client.get('/api/v1/gateway/status', headers=headers(connection['credential'])).json()
    assert status['employee'] == 'Sam' and status['sharing']
    src = source(client, connection).json()['source']['id']
    assert upload(client, connection, row(src)).status_code == 200
    employee = snapshot(client, org)['members'][0]
    assert employee['id'] == person and employee['signals'][0]['latest']['value'] == 74
    assert len(store.list(f'organizations/{org}/employees/{person}/observations')) == 1
    assert client.get('/api/v1/me', headers=headers(connection['credential'])).status_code == 401


def test_managers_see_only_assigned_teams_and_cannot_escalate(setup):
    client, store, org, team_a, team_b = setup
    a = create_person(client, org, team_a)
    b = create_person(client, org, team_b, 'Morgan')
    manager(client, org, [team_a])
    manager(client, org, [team_b], 'outsider')
    assert [person['id'] for person in snapshot(client, org, 'manager')['members']] == [a]
    assert [person['id'] for person in snapshot(client, org, 'outsider')['members']] == [b]
    assert snapshot(client, org, 'manager')['audit'] == []
    assert len(snapshot(client, org, 'manager')['accounts']) == 1
    for method, path, body in [
        ('POST', f'/employees/{b}/enrollments', {}),
        ('PATCH', f'/employees/{b}', {'name': 'Changed', 'team_id': team_a}),
        ('DELETE', f'/employees/{b}', None),
        ('POST', '/employees', {'name': 'Wrong team', 'team_id': team_b}),
        ('PATCH', f'/members/{digest(PEOPLE["manager"].uid)}/teams', {'team_ids': [team_b]}),
        ('GET', f'/members/{b}/history', None),
        ('GET', f'/members/{b}/observations?series_id={digest("not-a-series")}', None),
    ]:
        assert client.request(method, f'/api/v1/organizations/{org}{path}', headers=headers('manager'), json=body).status_code == 403
    phone_b = claim(client, enrollment(client, org, b).json()['token'])
    assert client.delete(f'/api/v1/organizations/{org}/devices/{phone_b["gateway_id"]}', headers=headers('manager')).status_code == 403
    assert not snapshot(client, org, 'manager')['devices']
    assert enrollment(client, org, a, 'manager').status_code == 201


def test_cross_company_team_and_employee_ids_are_rejected(setup):
    client, store, org, team_a, team_b = setup
    other = company(client, 'outsider')
    person = create_person(client, org, team_a)
    assert client.post(f'/api/v1/organizations/{other}/employees', headers=headers('outsider'), json={'name': 'Invalid', 'team_id': team_a}).status_code == 404
    assert enrollment(client, other, person, 'outsider').status_code == 404
    assert client.get(f'/api/v1/organizations/{org}/dashboard', headers=headers('outsider')).status_code == 403


def test_qr_expiry_one_use_and_exact_client_recovery(setup):
    client, store, org, team_a, team_b = setup
    person = create_person(client, org, team_a)
    token = enrollment(client, org, person).json()['token']
    body = claim_body(token)
    assert client.post('/api/v1/gateway/enrollment/claim', json={**body, 'consent': False}).status_code == 422
    first = client.post('/api/v1/gateway/enrollment/claim', json=body)
    assert first.status_code == 200
    assert client.post('/api/v1/gateway/enrollment/claim', json=body).json() == first.json()
    assert len(snapshot(client, org)['devices']) == 1
    assert client.post('/api/v1/gateway/enrollment/claim', json=claim_body(token)).status_code == 409
    assert client.post('/api/v1/gateway/enrollment/preview', json={'token': token}).status_code == 409
    expired = enrollment(client, org, person).json()['token']
    key = expired.split('.')[0][4:]
    store.atomic(lambda tx: tx.put(f'enrollments/{key}', {**tx.get(f'enrollments/{key}'), 'expires_at': time.time() - 1}))
    assert client.post('/api/v1/gateway/enrollment/claim', json=claim_body(expired)).status_code == 410


def test_new_qr_replaces_unclaimed_qr_and_lost_permission_invalidates_it(setup):
    client, store, org, team_a, team_b = setup
    person = create_person(client, org, team_a)
    manager(client, org, [team_a])
    old = enrollment(client, org, person, 'manager').json()['token']
    latest = enrollment(client, org, person, 'manager').json()['token']
    assert client.post('/api/v1/gateway/enrollment/claim', json=claim_body(old)).status_code == 410
    client.patch(f'/api/v1/organizations/{org}/members/{digest(PEOPLE["manager"].uid)}/teams', headers=headers(), json={'team_ids': []})
    assert client.post('/api/v1/gateway/enrollment/preview', json={'token': latest}).status_code == 410
    assert not snapshot(client, org, 'manager')['members']


def test_concurrent_claims_only_create_one_gateway(setup):
    client, store, org, team_a, team_b = setup
    person = create_person(client, org, team_a)
    token = enrollment(client, org, person).json()['token']
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: client.post('/api/v1/gateway/enrollment/claim', json=claim_body(token)), range(4)))
    assert sorted(result.status_code for result in results) == [200, 409, 409, 409]
    assert len(snapshot(client, org)['devices']) == 1


def test_team_transfer_hides_prior_history_including_delayed_uploads(setup, monkeypatch):
    client, store, org, team_a, team_b = setup
    clock = [time.time()]
    monkeypatch.setattr('neurasign.onboarding.time.time', lambda: clock[0])
    person = create_person(client, org, team_a)
    manager(client, org, [team_a])
    manager(client, org, [team_b], 'outsider')
    phone = claim(client, enrollment(client, org, person).json()['token'])
    src = source(client, phone).json()['source']['id']
    def sample(id):
        return {**row(src, id=id), 'measured_at': datetime.fromtimestamp(clock[0], timezone.utc).isoformat()}
    clock[0] += 2
    first = sample('before-transfer')
    assert upload(client, phone, first).status_code == 200
    old_series = snapshot(client, org, 'manager')['members'][0]['signals'][0]['series_id']
    clock[0] += 10
    assert client.patch(f'/api/v1/organizations/{org}/employees/{person}', headers=headers(), json={'name': 'Sam', 'team_id': team_b}).status_code == 200
    assert not snapshot(client, org, 'manager')['members']
    assert snapshot(client, org, 'outsider')['members'][0]['signals'][0]['latest'] is None
    # A delayed original-team measurement keeps its old team even after transfer.
    delayed = {**first, 'id': 'late-before-transfer', 'value': 72}
    assert upload(client, phone, delayed).status_code == 200
    clock[0] += 10
    assert upload(client, phone, sample('after-transfer')).status_code == 200
    path = f'/api/v1/organizations/{org}/members/{person}/observations?series_id={old_series}'
    assert client.get(path, headers=headers('manager')).status_code == 403
    assert len(client.get(path, headers=headers('outsider')).json()['observations']) == 1
    assert len(client.get(path, headers=headers()).json()['observations']) == 3


def test_pause_resume_rejects_measurements_collected_during_pause(setup, monkeypatch):
    client, store, org, team_a, team_b = setup
    clock = [time.time()]
    monkeypatch.setattr('neurasign.onboarding.time.time', lambda: clock[0])
    person = create_person(client, org, team_a)
    phone = claim(client, enrollment(client, org, person).json()['token'])
    src = source(client, phone).json()['source']['id']
    clock[0] += 1
    assert client.patch('/api/v1/gateway/sharing', headers=headers(phone['credential']), json={'enabled': False}).status_code == 200
    clock[0] += 1
    during = {**row(src), 'measured_at': datetime.fromtimestamp(clock[0], timezone.utc).isoformat()}
    assert upload(client, phone, during).status_code == 403
    assert not client.get('/api/v1/gateway/status', headers=headers(phone['credential'])).json()['sharing']
    clock[0] += 1
    assert client.patch('/api/v1/gateway/sharing', headers=headers(phone['credential']), json={'enabled': True}).status_code == 200
    assert upload(client, phone, during).status_code == 422
    assert client.delete('/api/v1/gateway/connection', headers=headers(phone['credential'])).status_code == 200
    assert client.get('/api/v1/gateway/status', headers=headers(phone['credential'])).status_code == 401


def test_remove_employee_revokes_phones_without_removing_dashboard_accounts(setup):
    client, store, org, team_a, team_b = setup
    person = create_person(client, org, team_a)
    phone = claim(client, enrollment(client, org, person).json()['token'])
    token = enrollment(client, org, person).json()['token']
    assert client.delete(f'/api/v1/organizations/{org}/employees/{person}', headers=headers()).status_code == 200
    assert client.get('/api/v1/gateway/status', headers=headers(phone['credential'])).status_code == 401
    assert client.post('/api/v1/gateway/enrollment/claim', json=claim_body(token)).status_code == 410
    assert snapshot(client, org)['members'] == []
    assert len(snapshot(client, org)['accounts']) == 1


def test_existing_account_backed_employee_and_history_survive_promotion(workspace):
    client, store, app = workspace
    app.include_router(router)
    org = company(client)
    key = digest(PEOPLE['owner'].uid)
    path = f'organizations/{org}/members/{key}'
    store.atomic(lambda tx: tx.put(path, {**tx.get(path), 'sharing': False, 'device_ids': []}))
    assert snapshot(client, org)['members'][0]['id'] == key
    connection = device(client, org, 'owner')
    assert legacy_upload(client, connection['credential'], [reading()]).status_code == 200
    assert store.get(f'organizations/{org}/employees/{key}')['storage_root'] == 'members'
    assert len(client.get(f'/api/v1/organizations/{org}/members/{key}/history', headers=headers()).json()['readings']) == 1


def test_inactive_profiles_do_not_consume_the_active_roster_limit(setup):
    client, store, org, team_a, _ = setup
    person = create_person(client, org, team_a)
    def seed(tx):
        for index in range(220):
            key = f'{index:032x}'
            tx.put(f'organizations/{org}/employees/{key}', {'id': key, 'active': False})
    store.atomic(seed)
    assert [value['id'] for value in snapshot(client, org)['members']] == [person]


def test_removed_legacy_profile_is_not_reintroduced_by_account_projection(workspace):
    client, store, app = workspace
    app.include_router(router)
    org = company(client)
    key = digest(PEOPLE['owner'].uid)
    path = f'organizations/{org}/members/{key}'
    store.atomic(lambda tx: tx.put(path, {**tx.get(path), 'sharing': False, 'device_ids': []}))
    assert snapshot(client, org)['members']
    assert client.delete(f'/api/v1/organizations/{org}/employees/{key}', headers=headers()).status_code == 200
    assert snapshot(client, org)['members'] == []
    assert snapshot(client, org)['accounts'][0]['active']
