"""Real storage + HTTP contracts: company isolation, sharing and device ingestion."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import time

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
import pytest

from neurasign.identity import Identity, get_store, identity, validate_environment
from neurasign.store import SQLiteStore
from neurasign.workspace import digest, router


PEOPLE = {
    'owner': Identity('owner-user', 'owner@example.com', 'Taylor'),
    'employee': Identity('employee-user', 'employee@example.com', 'Sam'),
    'outsider': Identity('other-company', 'other@example.com', 'Jordan'),
    'manager': Identity('manager-user', 'manager@example.com', 'Robin'),
}


@pytest.fixture
def workspace(tmp_path):
    app = FastAPI()
    app.include_router(router)
    store = SQLiteStore(tmp_path / 'workspace.sqlite3')
    def signed_in(authorization: str | None = Header(None)):
        user = PEOPLE.get((authorization or '').removeprefix('Bearer '))
        if not user:
            raise HTTPException(401, 'Sign in required.')
        return user
    app.dependency_overrides[identity] = signed_in
    app.dependency_overrides[get_store] = lambda: store
    with TestClient(app) as client:
        yield client, store, app


def headers(user='owner'):
    return {'Authorization': f'Bearer {user}'}


def company(client, user='owner'):
    response = client.post('/api/v1/organizations', headers=headers(user), json={'name': 'Example Team'})
    assert response.status_code == 201, response.text
    return response.json()['id']


def add_member(client, org, user='employee', role='employee'):
    response = client.post(f'/api/v1/organizations/{org}/invitations', headers=headers(), json={'email': PEOPLE[user].email, 'role': role})
    assert response.status_code == 201, response.text
    token = response.json()['token']
    response = client.post('/api/v1/invitations/accept', headers=headers(user), json={'token': token})
    assert response.status_code == 200, response.text
    return token


def device(client, org, user='employee', source='wearable'):
    response = client.patch(f'/api/v1/organizations/{org}/me/sharing', headers=headers(user), json={'enabled': True})
    assert response.status_code == 200, response.text
    response = client.post(f'/api/v1/organizations/{org}/devices', headers=headers(user), json={'name': 'Test wearable', 'source': source})
    assert response.status_code == 201, response.text
    return response.json()


def reading(id='sample-001', age=0, heart_rate=75):
    return {'id': id, 'timestamp': (datetime.now(timezone.utc) - timedelta(seconds=age)).isoformat(), 'features': {'heart_rate': heart_rate}, 'window_seconds': 10}


def upload(client, credential, rows):
    return client.post('/api/v1/readings', headers=headers(credential), json={'readings': rows})


def test_company_requires_identity_and_excludes_outsiders(workspace):
    client, store, app = workspace
    assert client.get('/api/v1/me').status_code == 401
    org, other = company(client), company(client, 'outsider')
    assert client.get(f'/api/v1/organizations/{org}/dashboard', headers=headers('outsider')).status_code == 403
    assert client.get(f'/api/v1/organizations/{other}/dashboard', headers=headers()).status_code == 403
    snapshot = client.get(f'/api/v1/organizations/{org}/dashboard', headers=headers()).json()
    assert snapshot['members'] == []  # A dashboard account does not create an employee.
    assert not snapshot['devices'] and snapshot['me']['name'] == 'Taylor'
    assert snapshot['accounts'][0]['role'] == 'owner' and not snapshot['me']['sharing']
    assert 'Alex' not in json.dumps(snapshot) and 'UNIVERSE' not in json.dumps(snapshot)


def test_invite_email_binding_expiry_and_employee_permissions(workspace):
    client, store, app = workspace
    org = company(client)
    response = client.post(f'/api/v1/organizations/{org}/invitations', headers=headers(), json={'email': PEOPLE['employee'].email})
    token = response.json()['token']
    assert client.post('/api/v1/invitations/accept', headers=headers('outsider'), json={'token': token}).status_code == 403
    assert client.post('/api/v1/invitations/accept', headers=headers('employee'), json={'token': token}).status_code == 200
    assert client.post('/api/v1/invitations/accept', headers=headers('employee'), json={'token': token}).status_code == 200
    own = client.get(f'/api/v1/organizations/{org}/dashboard', headers=headers('employee')).json()
    assert [person['name'] for person in own['members']] == ['Sam']
    assert not own['audit']
    assert client.post(f'/api/v1/organizations/{org}/invitations', headers=headers('employee'), json={'email': 'other@example.com'}).status_code == 403
    assert client.get(f'/api/v1/organizations/{org}/members/{digest(PEOPLE["owner"].uid)}/history', headers=headers('employee')).status_code == 403
    another = client.post(f'/api/v1/organizations/{org}/invitations', headers=headers(), json={'email': 'other@example.com'}).json()['token']
    store.atomic(lambda tx: tx.put(f'invitations/{digest(another)}', {**tx.get(f'invitations/{digest(another)}'), 'expires_at': time.time() - 1}))
    assert client.post('/api/v1/invitations/accept', headers=headers('outsider'), json={'token': another}).status_code == 410


def test_manager_cannot_escalate_roles_or_remove_owner(workspace):
    client, store, app = workspace
    org = company(client)
    add_member(client, org, 'manager', 'manager')
    assert client.post(f'/api/v1/organizations/{org}/invitations', headers=headers('manager'), json={'email': 'employee@example.com', 'role': 'manager'}).status_code == 403
    assert client.delete(f'/api/v1/organizations/{org}/members/{digest(PEOPLE["owner"].uid)}', headers=headers('manager')).status_code == 403
    assert client.delete(f'/api/v1/organizations/{org}/members/{digest(PEOPLE["owner"].uid)}', headers=headers()).status_code == 409


def test_device_credential_bound_to_member_no_identity_spoofing(workspace):
    client, store, app = workspace
    org = company(client)
    add_member(client, org)
    assert client.post(f'/api/v1/organizations/{org}/devices', headers=headers('employee'), json={'name': 'Phone', 'source': 'wearable'}).status_code == 409
    connection = device(client, org)
    credential = connection['credential']
    assert credential not in json.dumps(store.get(f'device_keys/{connection["device"]["id"]}'))
    assert client.get('/api/v1/me', headers=headers(credential)).status_code == 401
    assert upload(client, 'invalid-token', [reading()]).status_code == 401
    assert client.post('/api/v1/readings', headers=headers(credential), json={'readings': [reading()], 'worker_id': 'other'}).status_code == 422
    assert upload(client, credential, [reading()]).status_code == 200
    snapshot = client.get(f'/api/v1/organizations/{org}/dashboard', headers=headers('employee')).json()
    sam = next(person for person in snapshot['members'] if person['name'] == 'Sam')
    assert sam['features']['heart_rate'] == 75 and sam['features']['hrv'] is None
    assert sam['latest']['source'] == 'wearable' and sam['status'] == 'current'
    assert all(person['name'] != 'Taylor' for person in snapshot['members'])
    assert credential not in json.dumps(snapshot)


def test_batch_idempotency_out_of_order_and_stale_history(workspace):
    client, store, app = workspace
    org = company(client)
    add_member(client, org)
    credential = device(client, org)['credential']
    recent, old = reading('reading-new', age=2, heart_rate=82), reading('reading-old', age=3600, heart_rate=65)
    assert upload(client, credential, [recent]).json()['accepted'] == 1
    result = upload(client, credential, [recent, old]).json()
    assert result['accepted'] == 1 and result['duplicates'] == 1
    changed = {**recent, 'features': {'heart_rate': 88}}
    assert upload(client, credential, [changed]).status_code == 409
    snapshot = client.get(f'/api/v1/organizations/{org}/dashboard', headers=headers('employee')).json()
    assert next(person for person in snapshot['members'] if person['name'] == 'Sam')['features']['heart_rate'] == 82
    history = client.get(f'/api/v1/organizations/{org}/members/{digest(PEOPLE["employee"].uid)}/history', headers=headers('employee')).json()['readings']
    assert [row['features']['heart_rate'] for row in history] == [65, 82]
    assert upload(client, credential, [reading('future-data', age=-20)]).status_code == 422
    assert upload(client, credential, [reading('expired-data', age=8*86400)]).status_code == 422
    assert upload(client, credential, [{**reading(), 'features': {}}]).status_code == 422


def test_recording_source_stale_and_cross_restart_persistence(workspace):
    client, store, app = workspace
    org = company(client)
    connection = device(client, org, 'owner', 'recording')
    assert upload(client, connection['credential'], [reading(age=120)]).status_code == 200
    app.dependency_overrides[get_store] = lambda: SQLiteStore(store.path)
    snapshot = client.get(f'/api/v1/organizations/{org}/dashboard', headers=headers()).json()
    person = snapshot['members'][0]
    assert person['status'] == 'stale' and person['features']['heart_rate'] is None
    assert person['latest']['source'] == 'recording' and person['latest']['features']['heart_rate'] == 75
    assert client.get('/api/v1/me', headers=headers()).json()['organizations'][0]['id'] == org


def test_pause_revoke_remove_and_delete_block_ingestion(workspace):
    client, store, app = workspace
    org = company(client)
    add_member(client, org)
    connection = device(client, org)
    credential = connection['credential']
    assert upload(client, credential, [reading()]).status_code == 200
    assert client.patch(f'/api/v1/organizations/{org}/me/sharing', headers=headers('employee'), json={'enabled': False}).status_code == 200
    assert upload(client, credential, [reading('after-pause')]).status_code == 403
    snapshot = client.get(f'/api/v1/organizations/{org}/dashboard', headers=headers()).json()
    assert next(person for person in snapshot['members'] if person['name'] == 'Sam')['latest'] is None
    assert client.delete(f'/api/v1/organizations/{org}/me/readings', headers=headers('employee')).json()['deleted'] == 1
    assert not store.list(f'organizations/{org}/members/{digest(PEOPLE["employee"].uid)}/readings')
    assert client.delete(f'/api/v1/organizations/{org}/devices/{connection["device"]["id"]}', headers=headers()).status_code == 200
    assert upload(client, credential, [reading()]).status_code == 401
    replacement = device(client, org)
    assert client.delete(f'/api/v1/organizations/{org}/members/{digest(PEOPLE["employee"].uid)}', headers=headers()).status_code == 200
    assert upload(client, replacement['credential'], [reading()]).status_code == 401
    assert not client.get(f'/api/v1/organizations/{org}/dashboard', headers=headers()).json()['devices']
    assert client.get(f'/api/v1/organizations/{org}/dashboard', headers=headers('employee')).status_code == 403


def test_two_instances_concurrently_accept_same_reading_once(workspace):
    client, store, app = workspace
    org = company(client)
    connection = device(client, org, 'owner')
    row = reading()
    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(lambda _: upload(client, connection['credential'], [row]), range(6)))
    assert all(response.status_code == 200 for response in results)
    assert sum(response.json()['accepted'] for response in results) == 1
    assert sum(response.json()['duplicates'] for response in results) == 5


def test_deletion_cannot_race_with_reenabling_sharing(workspace, monkeypatch):
    client, store, app = workspace
    org = company(client)
    connection = device(client, org, 'owner')
    assert upload(client, connection['credential'], [reading()]).status_code == 200
    original = store.list
    attempts = []
    def during_deletion(collection, *args, **kwargs):
        if collection.endswith('/readings'):
            attempts.append(client.patch(f'/api/v1/organizations/{org}/me/sharing', headers=headers(), json={'enabled': True}).status_code)
            assert upload(client, connection['credential'], [reading('while-deleting')]).status_code == 403
        return original(collection, *args, **kwargs)
    monkeypatch.setattr(store, 'list', during_deletion)
    response = client.delete(f'/api/v1/organizations/{org}/me/readings', headers=headers())
    assert response.status_code == 200 and response.json()['deleted'] == 1
    assert attempts and all(status == 409 for status in attempts)
    assert client.patch(f'/api/v1/organizations/{org}/me/sharing', headers=headers(), json={'enabled': True}).status_code == 200


def test_production_rejects_ephemeral_or_emulated_configuration(monkeypatch):
    monkeypatch.setenv('NEURASIGN_ENV', 'production')
    monkeypatch.setenv('FIREBASE_PROJECT_ID', 'neurasign-test')
    monkeypatch.setenv('FIREBASE_WEB_API_KEY', 'public-browser-key')
    monkeypatch.setenv('WORKSPACE_STORE', 'sqlite')
    monkeypatch.delenv('FIREBASE_AUTH_EMULATOR_HOST', raising=False)
    monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    with pytest.raises(RuntimeError, match='Firestore'):
        validate_environment()
    monkeypatch.setenv('WORKSPACE_STORE', 'firestore')
    monkeypatch.setenv('FIREBASE_AUTH_EMULATOR_HOST', 'localhost:9099')
    with pytest.raises(RuntimeError, match='Emulators'):
        validate_environment()


@pytest.mark.parametrize('override', [
    {'NEURASIGN_ENV': 'production'}, {'K_SERVICE': 'deployed-service'},
    {'FIREBASE_PROJECT_ID': 'real-company-project'},
    {'FIREBASE_AUTH_EMULATOR_HOST': ''}, {'FIRESTORE_EMULATOR_HOST': ''},
])
def test_public_test_account_is_exclusive_to_local_emulators(monkeypatch, override):
    from neurasign.identity import local_test_account, workspace_config
    from neurasign import local_setup
    environment = {
        'NEURASIGN_ENV': 'local', 'K_SERVICE': '', 'WORKSPACE_STORE': 'firestore',
        'FIREBASE_PROJECT_ID': 'demo-neurasign',
        'FIREBASE_AUTH_EMULATOR_HOST': 'localhost:9099', 'FIRESTORE_EMULATOR_HOST': 'localhost:8088',
    }
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    assert local_test_account()['email'] == 'demo@neurasign.test'
    for key, value in override.items():
        monkeypatch.setenv(key, value)
    assert workspace_config()['test_account'] is None
    def forbidden():
        pytest.fail('Test account creation must not access Firebase outside the local emulators.')
    monkeypatch.setattr(local_setup, 'firebase_app', forbidden)
    local_setup.ensure_local_test_account()


def test_production_blocks_legacy_demo_routes_and_socket(monkeypatch):
    from neurasign.main import app
    monkeypatch.setenv('NEURASIGN_ENV', 'production')
    # No lifespan here: exercise the production HTTP/WS boundary in isolation.
    with TestClient(FastAPI()) as unused:
        client = TestClient(app)
        assert client.get('/api/state').status_code == 404
        assert client.post('/api/control', json={'action': 'reset'}).status_code == 404
        assert client.post('/api/live/readings', json={}).status_code == 404
        assert client.get('/api/research').status_code == 404
        assert client.get('/api/health').status_code == 200
        from starlette.websockets import WebSocketDisconnect
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect('/ws'):
                pass
