"""Verify local emulator volume persistence and deny direct client Firestore access."""
from datetime import datetime, timezone
import hashlib
import subprocess
import time

import httpx

from workspace_smoke import AUTH, PROJECT, ROOT, WEB, auth_call, call, test_user


def main():
    config = call('GET', '/config')
    assert config['firebase']['projectId'] == PROJECT and config['emulator_url'] == AUTH
    user = test_user('PersistenceCheck')
    org = call('POST', '/organizations', user['token'], {'name': 'Restart verification'}, 201)['id']
    base = f'/organizations/{org}'
    call('PATCH', base + '/me/sharing', user['token'], {'enabled': True})
    device = call('POST', base + '/devices', user['token'], {'name': 'Persistence recording', 'source': 'recording'}, 201)
    row = {'id': 'persistence-0001', 'timestamp': datetime.now(timezone.utc).isoformat(), 'features': {'heart_rate': 73}, 'window_seconds': 10}
    call('POST', '/readings', device['credential'], {'readings': [row]})
    direct = f'http://localhost:8088/v1/projects/{PROJECT}/databases/(default)/documents/organizations/{org}'
    assert httpx.get(direct, headers={'Authorization': f'Bearer {user["token"]}'}, timeout=10).status_code == 403
    subprocess.run(['docker', 'compose', 'restart', 'emulator'], cwd=ROOT, check=True, capture_output=True)
    # Auth emulator imports reset session validity; sign in again after restart.
    for _ in range(60):
        try:
            if httpx.get(AUTH + '/', timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(.5)
    user['token'] = auth_call('signInWithPassword', {'email': user['email'], 'password': user['password'], 'returnSecureToken': True})['idToken']
    result = None
    for _ in range(60):
        try:
            result = httpx.get(WEB + '/api/v1' + base + '/dashboard', headers={'Authorization': f'Bearer {user["token"]}'}, timeout=3)
            if result.status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(.5)
    assert result is not None and result.status_code == 200, f'Emulator persistence failed: {result.status_code if result is not None else "unavailable"}'
    assert result.json()['organization']['id'] == org
    person = hashlib.sha256(user['uid'].encode()).hexdigest()
    history = call('GET', base + f'/members/{person}/history', user['token'])['readings']
    assert len(history) == 1 and history[0]['features']['heart_rate'] == 73
    assert call('POST', '/readings', device['credential'], {'readings': [row]})['duplicates'] == 1
    print('PASS: verified Auth account, company, device credential and measurements survive emulator export/import; direct Firestore client access denied. Auth emulator requires a fresh sign-in after import.')


if __name__ == '__main__':
    main()
