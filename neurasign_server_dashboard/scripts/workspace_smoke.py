"""Exercise real Auth/Firestore emulators through the public web proxy.

Never targets production; test accounts and measurements are local only.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import secrets
import subprocess
import time

import httpx

WEB = 'http://localhost:3000'
AUTH = 'http://localhost:9099'
PROJECT = 'demo-neurasign'
ROOT = Path(__file__).resolve().parents[1]


def auth_call(action, body):
    response = httpx.post(f'{AUTH}/identitytoolkit.googleapis.com/v1/accounts:{action}?key=demo-key', json=body, timeout=15)
    assert response.is_success, f'Auth {action}: {response.status_code}'
    return response.json()


def test_user(name, verified=True):
    email = f'{name.lower()}-{secrets.token_hex(6)}@example.test'
    password = secrets.token_urlsafe(24)
    result = auth_call('signUp', {'email': email, 'password': password, 'returnSecureToken': True})
    auth_call('update', {'idToken': result['idToken'], 'displayName': name})
    if verified:
        auth_call('sendOobCode', {'idToken': result['idToken'], 'requestType': 'VERIFY_EMAIL'})
        verify_email(email)
    result = auth_call('signInWithPassword', {'email': email, 'password': password, 'returnSecureToken': True})
    return {'email': email, 'password': password, 'token': result['idToken'], 'uid': result['localId']}


def verify_email(email):
    codes = httpx.get(f'{AUTH}/emulator/v1/projects/{PROJECT}/oobCodes', timeout=10).json()['oobCodes']
    code = next(item['oobCode'] for item in reversed(codes) if item['email'] == email and item['requestType'] == 'VERIFY_EMAIL')
    auth_call('update', {'oobCode': code})


def call(method, path, token=None, body=None, expected=200):
    response = httpx.request(method, WEB + '/api/v1' + path, headers={'Authorization': f'Bearer {token}'} if token else {}, json=body, timeout=30)
    assert response.status_code == expected, f'{method} {path}: {response.status_code} {response.text[:300]}'
    return response.json()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-restart', action='store_true', help='Exercise durable reads without restarting the shared API service.')
    args = parser.parse_args()
    config = call('GET', '/config')
    assert config['firebase']['projectId'] == PROJECT and config['emulator_url'] == AUTH, 'Only local demo emulators are allowed.'
    call('GET', '/me', expected=401)
    unverified = test_user('Unverified', verified=False)
    call('GET', '/me', unverified['token'], expected=403)
    owner, employee, stranger = test_user('Taylor'), test_user('Sam'), test_user('Jordan')
    org = call('POST', '/organizations', owner['token'], {'name': 'Integration Test Team'}, 201)['id']
    base = f'/organizations/{org}'
    invitation = call('POST', base + '/invitations', owner['token'], {'email': employee['email']}, 201)['token']
    call('POST', '/invitations/accept', stranger['token'], {'token': invitation}, 403)
    call('POST', '/invitations/accept', employee['token'], {'token': invitation})
    call('GET', base + '/dashboard', stranger['token'], expected=403)
    call('PATCH', base + '/me/sharing', employee['token'], {'enabled': True})
    device = call('POST', base + '/devices', employee['token'], {'name': 'Smoke recording', 'source': 'recording'}, 201)
    row = {'id': 'integration-0001', 'timestamp': datetime.now(timezone.utc).isoformat(), 'features': {'heart_rate': 74, 'hrv': 42}, 'window_seconds': 10}
    assert call('POST', '/readings', device['credential'], {'readings': [row]})['accepted'] == 1
    assert call('POST', '/readings', device['credential'], {'readings': [row]})['duplicates'] == 1
    older = {**row, 'id': 'integration-old', 'timestamp': (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(), 'features': {'heart_rate': 61}}
    call('POST', '/readings', device['credential'], {'readings': [older]})
    team = call('GET', base + '/dashboard', owner['token'])
    assert len(team['members']) == 1
    sam = next(member for member in team['members'] if member['name'] == 'Sam')
    assert not sam['measurements_access'] and sam['latest'] is None and not sam['signals']
    assert all(value is None for value in sam['features'].values())
    assert sam['connection']['status'] == 'current' and sam['connection']['last_received_at']
    own = call('GET', base + '/dashboard', employee['token'])['members']
    assert len(own) == 1 and own[0]['features']['heart_rate'] == 74 and own[0]['latest']['source'] == 'recording'
    call('GET', base + f'/members/{sam["id"]}/history', owner['token'], expected=403)
    owner_id = hashlib.sha256(owner['uid'].encode()).hexdigest()
    call('GET', base + f'/members/{owner_id}/history', employee['token'], expected=403)
    if not args.skip_restart:
        # Restart the API process, not the database. The company/history must survive.
        subprocess.run(['docker', 'compose', 'restart', 'api'], cwd=ROOT, check=True, capture_output=True)
        for _ in range(40):
            try:
                response = httpx.get(WEB + '/api/v1/config', timeout=2)
                if response.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(.5)
    assert len(call('GET', base + f'/members/{sam["id"]}/history', employee['token'])['readings']) == 2
    call('PATCH', base + '/me/sharing', employee['token'], {'enabled': False})
    assert next(person for person in call('GET', base + '/dashboard', owner['token'])['members'] if person['id'] == sam['id'])['latest'] is None
    call('POST', '/readings', device['credential'], {'readings': [row]}, 403)
    assert call('DELETE', base + '/me/readings', employee['token'])['deleted'] == 2
    call('DELETE', base + f'/devices/{device["device"]["id"]}', owner['token'])
    call('POST', '/readings', device['credential'], {'readings': [row]}, 401)
    persistence = 'durable readback; restart intentionally skipped' if args.skip_restart else 'API restart persistence'
    print(f'PASS: real Auth + Firestore emulators; owner privacy, employee self-access, identity/tenant scopes, sharing, ingestion, idempotency, timestamps, deletion, revocation and {persistence}. No cloud account used.')


if __name__ == '__main__':
    main()
