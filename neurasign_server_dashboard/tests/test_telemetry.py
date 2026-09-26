"""Wearable-independent server contract, including tenant and lifecycle boundaries."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import time

import pytest

from neurasign.telemetry import router
from neurasign.workspace import digest
from test_workspace import workspace, headers, company, add_member, device, PEOPLE


@pytest.fixture
def telemetry(workspace):
    client, store, app = workspace
    app.include_router(router)
    org = company(client)
    add_member(client, org)
    connection = device(client, org)
    return client, store, org, connection


def capability(metric='heart_rate', unit='bpm', **changes):
    return {'metric': metric, 'unit': unit, 'delivery_mode': 'stream', 'measurement_kind': 'sample',
            'method': 'device-reported', **changes}


def source(client, connection, capabilities=None, **changes):
    return client.post('/api/v1/gateway/sources', headers=headers(connection['credential']), json={
        'client_source_id': 'source-0001', 'name': 'Connected wearable',
        'adapter': {'id': 'test-connector', 'version': '1.0.0'}, 'transport': 'ble',
        'capabilities': capabilities or [capability()], **changes,
    })


def row(source_id, metric='heart_rate', value=74, unit='bpm', id='observation-0001', age=0):
    return {'id': id, 'source_id': source_id, 'metric': metric, 'value': value, 'unit': unit,
            'measured_at': (datetime.now(timezone.utc) - timedelta(seconds=age)).isoformat()}


def upload(client, connection, *rows):
    return client.post('/api/v1/observations', headers=headers(connection['credential']),
                       json={'schema_version': 2, 'observations': list(rows)})


def snapshot(client, org, user='owner'):
    return client.get(f'/api/v1/organizations/{org}/dashboard', headers=headers(user)).json()


def signals(client, org):
    return next(person for person in snapshot(client, org)['members'] if person['name'] == 'Sam')['signals']


def history(client, org, series):
    return client.get(f'/api/v1/organizations/{org}/members/{digest(PEOPLE["employee"].uid)}/observations',
                      headers=headers(), params={'series_id': series})


def test_async_metrics_are_normalized_on_server_without_erasing_other_metrics(telemetry):
    client, store, org, connection = telemetry
    result = source(client, connection, [capability(), capability('skin_temperature', '°F')], manufacturer='Any manufacturer')
    assert result.status_code == 201, result.text
    source_id = result.json()['source']['id']
    assert upload(client, connection, row(source_id, 'skin_temperature', 86, '°F', age=2)).status_code == 200
    assert upload(client, connection, row(source_id, id='observation-0002')).status_code == 200
    values = {signal['metric']: signal for signal in signals(client, org)}
    assert values['skin_temperature']['latest']['value'] == pytest.approx(30)
    assert values['skin_temperature']['latest']['unit'] == '°C'
    assert values['skin_temperature']['latest']['input_value'] == 86
    assert values['heart_rate']['latest']['value'] == 74
    assert all(signal['status'] == 'current' for signal in values.values())
    assert 'Any manufacturer' not in str(client.get('/api/v1/metrics').json())
    assert history(client, org, values['heart_rate']['series_id']).json()['observations'][0]['value'] == 74


def test_rmssd_sdnn_and_summaries_keep_their_semantics(telemetry):
    client, store, org, connection = telemetry
    caps = [capability('hrv_rmssd', 's', measurement_kind='window', interval_seconds=60),
            capability('hrv_sdnn', 'ms', measurement_kind='summary', interval_seconds=28800, delivery_mode='sync')]
    source_id = source(client, connection, caps).json()['source']['id']
    assert upload(client, connection, row(source_id, 'hrv_rmssd', .04, 's'), row(source_id, 'hrv_sdnn', 85, 'ms', id='sdnn-summary')).status_code == 200
    rmssd, sdnn = signals(client, org)
    assert rmssd['latest']['value'] == 40 and rmssd['status'] == 'current'
    assert sdnn['latest']['value'] == 85 and sdnn['status'] == 'summary'
    assert rmssd['series_id'] != sdnn['series_id']


def test_timestamp_order_retry_and_conflicts_are_atomic(telemetry):
    client, store, org, connection = telemetry
    source_id = source(client, connection).json()['source']['id']
    recent = row(source_id, age=2)
    assert upload(client, connection, recent).json()['accepted'] == 1
    result = upload(client, connection, recent, row(source_id, id='older-reading', value=65, age=3600)).json()
    assert result['accepted'] == 1 and result['duplicates'] == 1
    assert signals(client, org)[0]['latest']['value'] == 74
    conflict = upload(client, connection, row(source_id, id='must-rollback'), {**recent, 'value': 88})
    assert conflict.status_code == 409
    assert len(history(client, org, signals(client, org)[0]['series_id']).json()['observations']) == 2


def test_old_sync_is_delayed_and_never_refreshes_measurement_time(telemetry):
    client, store, org, connection = telemetry
    source_id = source(client, connection, [capability(delivery_mode='sync')]).json()['source']['id']
    assert upload(client, connection, row(source_id, age=7200)).status_code == 200
    signal = signals(client, org)[0]
    assert signal['status'] == 'delayed'
    assert signal['latest']['received_at'] - signal['latest']['timestamp'] > 7190
    assert upload(client, connection, row(source_id, id='expired-reading', age=8 * 86400)).status_code == 422
    assert upload(client, connection, row(source_id, id='future-reading', age=-60)).status_code == 422


def test_source_and_observation_credentials_cannot_cross_people_or_tenants(telemetry):
    client, store, org, connection = telemetry
    source_id = source(client, connection).json()['source']['id']
    owner = device(client, org, 'owner')
    other_org = company(client, 'outsider')
    outsider = device(client, other_org, 'outsider')
    for other in (owner, outsider):
        assert upload(client, other, row(source_id)).status_code == 403
        assert client.get('/api/v1/gateway/sources', headers=headers(other['credential'])).json()['sources'] == []
    assert client.post('/api/v1/observations', headers=headers(connection['credential']), json={
        'schema_version': 2, 'observations': [row(source_id)], 'organization_id': other_org}).status_code == 422
    assert client.get(f'/api/v1/organizations/{org}/members/{digest(PEOPLE["employee"].uid)}/observations',
        headers=headers('outsider'), params={'series_id': digest('fake')}).status_code == 403
    assert upload(client, {'credential': 'owner'}, row(source_id)).status_code == 401


def test_pause_revocation_removal_and_deletion_apply_to_all_observations(telemetry):
    client, store, org, connection = telemetry
    source_id = source(client, connection).json()['source']['id']
    assert upload(client, connection, row(source_id)).status_code == 200
    series = signals(client, org)[0]['series_id']
    client.patch(f'/api/v1/organizations/{org}/me/sharing', headers=headers('employee'), json={'enabled': False})
    assert signals(client, org)[0]['latest'] is None
    assert history(client, org, series).json()['observations'] == []
    assert upload(client, connection, row(source_id, id='paused-reading')).status_code == 403
    assert client.delete(f'/api/v1/organizations/{org}/me/readings', headers=headers('employee')).json()['deleted'] == 1
    assert store.get(f'organizations/{org}/signal_state/{digest(PEOPLE["employee"].uid)}') is None
    client.patch(f'/api/v1/organizations/{org}/me/sharing', headers=headers('employee'), json={'enabled': True})
    assert history(client, org, series).json()['observations'] == []
    assert upload(client, connection, row(source_id, id='new-reading-1')).status_code == 200
    client.delete(f'/api/v1/organizations/{org}/devices/{connection["device"]["id"]}', headers=headers())
    assert upload(client, connection, row(source_id, id='new-reading-2')).status_code == 401
    assert signals(client, org) == []
    replacement = device(client, org)
    new_id = source(client, replacement).json()['source']['id']
    client.delete(f'/api/v1/organizations/{org}/members/{digest(PEOPLE["employee"].uid)}', headers=headers())
    assert upload(client, replacement, row(new_id)).status_code == 401


def test_source_registration_is_idempotent_and_semantics_cannot_mutate(telemetry):
    client, store, org, connection = telemetry
    first = source(client, connection).json()['source']
    assert source(client, connection).json()['source'] == first
    assert source(client, connection, [capability(unit='Hz')]).status_code == 409
    assert source(client, connection, [capability('unknown_vendor_stress', 'score')], client_source_id='another-source').status_code == 422
    assert source(client, connection, transport='recording').status_code == 422
    assert source(client, connection, [capability('hrv_sdnn', 'ms')], client_source_id='another-source').status_code == 422
    assert source(client, connection, [capability(), capability()]).status_code == 422


def test_unavailable_capabilities_are_visible_and_do_not_accept_fake_values(telemetry):
    client, store, org, connection = telemetry
    source_id = source(client, connection, [capability(), capability('skin_temperature', '°C', availability='unsupported')]).json()['source']['id']
    values = {signal['metric']: signal for signal in signals(client, org)}
    assert values['heart_rate']['status'] == 'waiting'
    assert values['skin_temperature']['status'] == 'unsupported'
    assert all(signal['latest'] is None for signal in values.values())
    assert upload(client, connection, row(source_id, 'skin_temperature', 33, '°C')).status_code == 422
    assert upload(client, connection, row(source_id, unit='Hz', value=1.2)).status_code == 422
    assert upload(client, connection, row(source_id, value=True)).status_code == 422


def test_permission_changes_preserve_source_identity_and_gate_uploads(telemetry):
    client, store, org, connection = telemetry
    original = source(client, connection, [capability(availability='permission_required')]).json()['source']['id']
    assert upload(client, connection, row(original)).status_code == 422
    available = source(client, connection).json()['source']['id']
    assert available == original
    assert upload(client, connection, row(available)).status_code == 200
    assert source(client, connection, [capability(availability='permission_required')]).status_code == 201
    assert signals(client, org)[0]['status'] == 'permission_required'
    assert upload(client, connection, row(available, id='after-permission-loss')).status_code == 422


def test_observation_deletion_blocks_concurrent_upload_and_resume(telemetry, monkeypatch):
    client, store, org, connection = telemetry
    source_id = source(client, connection).json()['source']['id']
    assert upload(client, connection, row(source_id)).status_code == 200
    original_list = store.list
    attempted = []
    def during_delete(collection, *args, **kwargs):
        if collection.endswith('/observations'):
            attempted.append(True)
            assert upload(client, connection, row(source_id, id='during-delete')).status_code == 403
            assert client.patch(f'/api/v1/organizations/{org}/me/sharing', headers=headers('employee'), json={'enabled': True}).status_code == 409
        return original_list(collection, *args, **kwargs)
    monkeypatch.setattr(store, 'list', during_delete)
    assert client.delete(f'/api/v1/organizations/{org}/me/readings', headers=headers('employee')).json()['deleted'] == 1
    assert attempted


def test_multiple_sources_are_distinct_and_recordings_remain_labeled(telemetry):
    client, store, org, connection = telemetry
    first = source(client, connection).json()['source']['id']
    second = source(client, connection, client_source_id='another-source', transport='health_store').json()['source']['id']
    assert upload(client, connection, row(first), row(second, id='other-observation')).status_code == 200
    assert len(signals(client, org)) == 2
    recording = device(client, org, source='recording')
    recorded_id = source(client, recording, transport='recording').json()['source']['id']
    assert upload(client, recording, row(recorded_id)).status_code == 200
    assert next(signal for signal in signals(client, org) if signal['source_id'] == recorded_id)['source'] == 'recording'


def test_two_instances_accept_an_observation_only_once(telemetry):
    client, store, org, connection = telemetry
    source_id = source(client, connection).json()['source']['id']
    sample = row(source_id)
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: upload(client, connection, sample), range(4)))
    assert all(response.status_code == 200 for response in responses)
    assert sum(response.json()['accepted'] for response in responses) == 1
    assert sum(response.json()['duplicates'] for response in responses) == 3


def test_current_values_expire_independently(telemetry, monkeypatch):
    client, store, org, connection = telemetry
    source_id = source(client, connection, [capability(), capability('skin_temperature', '°C')]).json()['source']['id']
    assert upload(client, connection, row(source_id, age=2), row(source_id, 'skin_temperature', 33, '°C', id='temperature-old', age=120)).status_code == 200
    values = {signal['metric']: signal for signal in signals(client, org)}
    assert values['heart_rate']['status'] == 'current'
    assert values['skin_temperature']['status'] == 'delayed'
    current = time.time()
    monkeypatch.setattr('neurasign.telemetry.time.time', lambda: current + 31 * 86400)
    assert all(signal['latest'] is None for signal in signals(client, org))
    assert history(client, org, values['heart_rate']['series_id']).json()['observations'] == []
