"""Real HTTP/storage boundaries with explicitly stubbed vendor HTTP responses."""
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse
import time

from cryptography.fernet import Fernet
from fastapi import HTTPException
import pytest

from neurasign import integrations as api
from neurasign.telemetry import router as telemetry_router
from neurasign.vendor.providers import whoop_records, google_records
from neurasign.onboarding import router as phone_router
from test_workspace import workspace, company, add_member, device, headers, PEOPLE
from test_telemetry import signals, source, capability, row, upload


@pytest.fixture
def linked(workspace, monkeypatch):
    client, store, app = workspace
    app.include_router(api.router); app.include_router(telemetry_router); app.include_router(phone_router)
    org = company(client); add_member(client, org); connection = device(client, org)
    for key, value in dict(INTEGRATIONS_ENCRYPTION_KEY=Fernet.generate_key().decode(), INTEGRATIONS_PUBLIC_ORIGIN='https://gateway.example.com', WHOOP_CLIENT_ID='whoop-client', WHOOP_CLIENT_SECRET='test-client-secret', GOOGLE_HEALTH_CLIENT_ID='google-client', GOOGLE_HEALTH_CLIENT_SECRET='test-google-secret').items():
        monkeypatch.setenv(key, value)
    return client, store, org, connection


def connect(linked, monkeypatch, provider='whoop'):
    client, store, org, connection = linked
    result = client.post(f'/api/v1/gateway/integrations/{provider}/connect', headers=headers(connection['credential']))
    assert result.status_code == 200, result.text
    params = parse_qs(urlparse(result.json()['authorization_url']).query)
    monkeypatch.setattr(api, 'vendor_request', lambda *args, **kwargs: dict(access_token='provider-access', refresh_token='provider-refresh', expires_in=3600))
    callback = client.get(f'/api/v1/integrations/{provider}/callback', params={'state': params['state'][0], 'code': 'provider-code'})
    assert callback.status_code == 200, callback.text
    return params


def sync(linked, provider='whoop'):
    client, _, _, connection = linked
    return client.post(f'/api/v1/gateway/integrations/{provider}/sync', headers=headers(connection['credential']))


def records():
    end = datetime.now(timezone.utc)-timedelta(hours=1); start = end-timedelta(hours=7)
    sleep = {'id': 'sleep1', 'start': start.isoformat(), 'end': end.isoformat(), 'score_state': 'SCORED', 'score': {'respiratory_rate': 15.2}}
    recovery = {'cycle_id': 12, 'sleep_id': 'sleep1', 'score_state': 'SCORED', 'score': {'resting_heart_rate': 52, 'hrv_rmssd_milli': 48.5, 'spo2_percentage': 97, 'skin_temp_celsius': 33.1}}
    return whoop_records([sleep], [recovery], [], [])


def test_oauth_state_one_use_and_tokens_never_leave_server(linked, monkeypatch):
    client, store, _, connection = linked
    params = connect(linked, monkeypatch)
    assert params['redirect_uri'] == ['https://gateway.example.com/api/v1/integrations/whoop/callback']
    assert 'provider-access' not in str(store.list('vendor_connections'))
    assert 'provider-refresh' not in str(store.list('vendor_connections'))
    status = client.get('/api/v1/gateway/integrations', headers=headers(connection['credential']))
    assert status.json()['integrations'][0]['connected']
    assert 'provider-' not in status.text
    assert client.get('/api/v1/integrations/whoop/callback', params={'state': params['state'][0], 'code': 'again'}).status_code == 400
    assert client.get('/api/v1/gateway/integrations', headers=headers()).status_code == 401


def test_google_oauth_uses_pkce_and_current_health_api_scopes(linked, monkeypatch):
    params = connect(linked, monkeypatch, 'fitbit')
    assert params['code_challenge_method'] == ['S256']
    assert 'googlehealth.ecg.readonly' in params['scope'][0]


def test_provider_summary_normalization_and_idempotent_sync(linked, monkeypatch):
    client, store, org, connection = linked; connect(linked, monkeypatch)
    rows = records(); monkeypatch.setattr(api, 'fetch_records', lambda *args: (rows, [], {}))
    result = sync(linked); assert result.status_code == 200, result.text
    assert result.json()['accepted'] == 5
    imported = signals(client, org)
    assert {s['metric'] for s in imported} == {'heart_rate', 'hrv_rmssd', 'oxygen_saturation', 'skin_temperature', 'respiratory_rate'}
    assert all(s['status'] == 'summary' and s['latest']['interval_seconds'] == 25200 for s in imported)
    assert all(s['delivery_mode'] == 'sync' and s['latest']['timestamp'] < time.time()-3500 for s in imported)
    path = api.path_for(connection['device']['id'], 'whoop'); current = store.get(path)
    store.atomic(lambda tx: tx.put(path, {**current, 'attempt_at': 0}))
    repeated = sync(linked); assert repeated.json()['duplicates'] == 5 and repeated.json()['accepted'] == 0


def test_pause_before_and_during_import_is_authoritative(linked, monkeypatch):
    client, store, org, connection = linked; connect(linked, monkeypatch)
    def fetch(*args):
        client.patch(f'/api/v1/organizations/{org}/me/sharing', headers=headers('employee'), json={'enabled': False})
        return records(), [], {}
    monkeypatch.setattr(api, 'fetch_records', fetch)
    response = sync(linked)
    assert response.status_code == 403
    assert not store.list(f'organizations/{org}/members/{api.digest(PEOPLE["employee"].uid)}/observations')
    assert sync(linked).status_code == 403


def test_unlink_during_fetch_prevents_late_writes(linked, monkeypatch):
    client, store, org, connection = linked; connect(linked, monkeypatch)
    def fetch(*args):
        result = client.delete('/api/v1/gateway/integrations/whoop', headers=headers(connection['credential']))
        assert result.status_code == 200
        return records(), [], {}
    monkeypatch.setattr(api, 'fetch_records', fetch)
    assert sync(linked).status_code == 410
    assert not store.list(f'organizations/{org}/sources')


def test_revocation_erases_provider_secrets(linked, monkeypatch):
    client, store, org, connection = linked; connect(linked, monkeypatch)
    assert store.list('vendor_connections')
    result = client.delete(f'/api/v1/organizations/{org}/devices/{connection["device"]["id"]}', headers=headers('employee'))
    assert result.status_code == 200, result.text
    assert not store.list('vendor_connections')
    assert sync(linked).status_code == 401


def test_missing_configuration_is_explicit_and_not_simulated(linked, monkeypatch):
    client, _, _, connection = linked; monkeypatch.delenv('INTEGRATIONS_ENCRYPTION_KEY')
    result = client.post('/api/v1/gateway/integrations/whoop/connect', headers=headers(connection['credential']))
    assert result.status_code == 503
    assert not client.get('/api/v1/gateway/integrations', headers=headers(connection['credential'])).json()['integrations'][0]['configured']


def test_google_ecg_conversion_and_manual_entries(linked):
    start = datetime.now(timezone.utc)-timedelta(hours=1)
    base = {'dataSource': {'recordingMethod': 'PASSIVELY_MEASURED', 'device': {'formFactor': 'WATCH', 'manufacturer': 'Fitbit', 'displayName': 'Sense'}}}
    ecg = {**base, 'electrocardiogram': {'interval': {'startTime': start.isoformat(), 'endTime': start.isoformat()}, 'samplingFrequencyHertz': 250, 'millivoltsScalingFactor': 1000, 'waveformSamples': list(range(1000))}}
    rows = google_records('electrocardiogram', [ecg])
    assert len(rows) == 2 and rows[0]['measurement']['samples'][-1] == .511
    assert rows[1]['measurement']['sample_offsets_ms'][-1] == 0
    assert rows[1]['measurement']['value'] == .999
    ecg['dataSource']['recordingMethod'] = 'MANUAL'
    assert google_records('electrocardiogram', [ecg]) == []


def test_google_pagination_keeps_original_filter_and_cursor(monkeypatch):
    calls = []
    def request(*args, **kwargs):
        calls.append((args[1], kwargs['params']))
        return {'dataPoints': [], 'nextPageToken': 'page2'}
    monkeypatch.setattr(api, 'vendor_request', request)
    _, _, cursors = api.fetch_records('fitbit', {'access_token': 'token'}, time.time())
    assert calls[0][0].startswith('https://health.googleapis.com/v4/users/me/dataTypes/')
    def next_page(*args, **kwargs):
        assert kwargs['params']['pageToken'] == 'page2'
        return {'dataPoints': []}
    monkeypatch.setattr(api, 'vendor_request', next_page)
    _, _, next_cursors = api.fetch_records('fitbit', {'access_token': 'token'}, time.time()+60, cursors)
    assert next_cursors == {}


def test_refresh_rotation_saved_before_provider_reads(linked, monkeypatch):
    _, store, _, connection = linked; connect(linked, monkeypatch)
    path = api.path_for(connection['device']['id'], 'whoop'); current = store.get(path)
    store.atomic(lambda tx: tx.put(path, {**current, 'tokens': api.seal({'access_token': 'expired', 'refresh_token': 'old-refresh', 'expires_at': 0})}))
    monkeypatch.setattr(api, 'vendor_request', lambda *a, **k: {'access_token': 'new-access', 'refresh_token': 'rotated', 'expires_in': 3600})
    def fetch(*args):
        assert api.unseal(store.get(path)['tokens'])['refresh_token'] == 'rotated'
        raise HTTPException(502, 'Provider offline')
    monkeypatch.setattr(api, 'fetch_records', fetch)
    assert sync(linked).status_code == 502
    assert store.get(path)['lease_until'] == 0


def test_variable_summary_requires_original_period(linked):
    client, _, _, connection = linked
    cap = capability('hrv_sdnn', 'ms', measurement_kind='summary', delivery_mode='sync', interval_variable=True)
    source_id = source(client, connection, [cap]).json()['source']['id']
    observation = row(source_id, 'hrv_sdnn', 40, 'ms')
    assert upload(client, connection, observation).status_code == 422
    assert upload(client, connection, {**observation, 'interval_seconds': 300}).status_code == 200


def test_google_denied_ecg_scope_does_not_discard_other_channels(monkeypatch):
    def request(method, url, **kwargs):
        if '/electrocardiogram/' in url:
            raise api.ProviderPermissionError()
        return {'dataPoints': []}
    monkeypatch.setattr(api, 'vendor_request', request)
    _, warnings, _ = api.fetch_records('fitbit', {'access_token': 'token'}, time.time())
    assert any('electrocardiogram: permission unavailable' in warning for warning in warnings)


def test_oauth_callback_rejects_revoked_gateway(linked, monkeypatch):
    client, store, org, connection = linked
    start = client.post('/api/v1/gateway/integrations/whoop/connect', headers=headers(connection['credential']))
    state = parse_qs(urlparse(start.json()['authorization_url']).query)['state'][0]
    client.delete(f'/api/v1/organizations/{org}/devices/{connection["device"]["id"]}', headers=headers('employee'))
    monkeypatch.setattr(api, 'vendor_request', lambda *a, **k: pytest.fail('Revoked gateway must not exchange OAuth tokens'))
    assert client.get('/api/v1/integrations/whoop/callback', params={'state': state, 'code': 'code'}).status_code == 410


def test_summary_crossing_a_paused_interval_is_skipped(linked, monkeypatch):
    client, store, org, connection = linked; connect(linked, monkeypatch)
    path = f'organizations/{org}/employees/{api.digest(PEOPLE["employee"].uid)}'
    old_path = f'organizations/{org}/members/{api.digest(PEOPLE["employee"].uid)}'
    person = store.get(path) or store.get(old_path)
    store.atomic(lambda tx: tx.put(path, {**person, 'storage_root':'members', 'active':True, 'paused_intervals':[{'from': time.time()-7200, 'until': time.time()-7100}]}))
    monkeypatch.setattr(api, 'fetch_records', lambda *args: (records(), [], {}))
    result = sync(linked)
    assert result.status_code == 200, result.text
    assert result.json()['accepted'] == 0 and result.json()['skipped'] == 5
