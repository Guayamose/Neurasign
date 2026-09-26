"""Raw channel preservation and the same authorization boundaries as scalar data."""
from datetime import datetime, timezone
import time

import pytest

from neurasign.telemetry import Observation
from neurasign.workspace import digest
from neurasign.company_access import employee, save_employee
from test_telemetry import telemetry, source, capability, row, upload, signals, history
from test_workspace import workspace, PEOPLE


def test_raw_blocks_preserve_samples_timing_units_and_retry_identity(telemetry):
    client, store, org, connection = telemetry
    source_id = source(client, connection, [capability('acceleration_x', 'mg')]).json()['source']['id']
    sample = {**row(source_id, 'acceleration_x', 1000, 'mg', age=2),
              'samples': [-1000, 0, 1000], 'sample_offsets_ms': [-20, -10, 0], 'device_timestamp_ns': '999999999999999999'}
    assert upload(client, connection, sample).json()['accepted'] == 1
    assert upload(client, connection, sample).json()['duplicates'] == 1
    signal = signals(client, org)[0]
    assert signal['latest']['value'] == 1
    assert signal['latest']['sample_count'] == 3
    assert 'samples' not in signal['latest']  # dashboard snapshots are bounded
    saved = history(client, org, signal['series_id']).json()['observations'][0]
    assert saved['samples'] == [-1, 0, 1]
    assert saved['input_samples'] == [-1000, 0, 1000]
    assert saved['sample_offsets_ms'] == [-20, -10, 0]
    assert saved['device_timestamp_ns'] == sample['device_timestamp_ns']
    assert saved['sample_duration_ms'] == 20
    assert upload(client, connection, {**sample, 'samples': [0, 0, 1000]}).status_code == 409


@pytest.mark.parametrize('changes', [
    {'samples': [1, 2]}, {'sample_offsets_ms': [-1, 0]},
    {'samples': [1, 2], 'sample_offsets_ms': [0]},
    {'samples': [1, 2], 'sample_offsets_ms': [1, 0]},
    {'samples': [1, 2], 'sample_offsets_ms': [-10001, 0]},
    {'samples': [1, 2], 'sample_offsets_ms': [-1, -1]},
    {'samples': [1, 3], 'sample_offsets_ms': [-1, 0]},
    {'samples': [1] * 513 + [2], 'sample_offsets_ms': [0] * 514},
    {'samples': [True, 2], 'sample_offsets_ms': [-1, 0]},
    {'samples': [1, 2], 'sample_offsets_ms': ['-1', 0]},
    {'samples': [float('nan'), 2], 'sample_offsets_ms': [-1, 0]},
])
def test_malformed_or_lossy_blocks_are_rejected(changes):
    with pytest.raises(ValueError):
        Observation.model_validate({**row('a' * 64, 'acceleration_x', 2, 'g'), **changes})


def test_raw_block_cannot_overlap_a_paused_sharing_interval(telemetry):
    client, store, org, connection = telemetry
    source_id = source(client, connection, [capability('electrocardiogram', 'µV')]).json()['source']['id']
    now = time.time()
    store.atomic(lambda tx: save_employee(tx, org, {**employee(tx, org, digest(PEOPLE['employee'].uid)), 'paused_intervals': [{'from': now - 3, 'until': now - 1}]}))
    sample = {**row(source_id, 'electrocardiogram', 5, 'µV'), 'samples': [4, 5], 'sample_offsets_ms': [-4000, 0]}
    assert upload(client, connection, sample).status_code == 422


def test_raw_blocks_do_not_cross_team_assignment_boundaries(telemetry):
    client, store, org, connection = telemetry
    source_id = source(client, connection, [capability('electrocardiogram', 'µV')]).json()['source']['id']
    now = time.time()
    store.atomic(lambda tx: save_employee(tx, org, {**employee(tx, org, digest(PEOPLE['employee'].uid)), 'assignments': [{'from': 0, 'until': now - 1, 'team_id': 'old'}, {'from': now - 1, 'until': None, 'team_id': 'new'}]}))
    sample = {**row(source_id, 'electrocardiogram', 5, 'µV'), 'samples': [4, 5], 'sample_offsets_ms': [-2000, 0]}
    assert upload(client, connection, sample).status_code == 422


def test_raw_blocks_reject_summary_capabilities_and_expired_first_samples(telemetry):
    client, store, org, connection = telemetry
    source_id = source(client, connection, [capability('skin_temperature', '°C', measurement_kind='summary', interval_seconds=60)]).json()['source']['id']
    sample = {**row(source_id, 'skin_temperature', 32, '°C'), 'samples': [31, 32], 'sample_offsets_ms': [-1000, 0]}
    assert upload(client, connection, sample).status_code == 422
    sample['measured_at'] = datetime.fromtimestamp(time.time() - 7 * 86400 + .5, timezone.utc).isoformat()
    assert upload(client, connection, sample).status_code == 422


def test_all_universe_channel_classes_coexist_without_scores(telemetry):
    client, store, org, connection = telemetry
    channels = [('heart_rate', 'bpm', 72), ('rr_interval', 'ms', 810), ('blood_volume_pulse', 'a.u.', -3),
                ('electrodermal_conductance', 'µS', .3), ('skin_temperature', '°C', 32),
                ('acceleration_x', 'g', .1), ('acceleration_y', 'g', -.2), ('acceleration_z', 'g', 1)]
    source_id = source(client, connection, [capability(metric, unit) for metric, unit, _ in channels]).json()['source']['id']
    batch = [{**row(source_id, metric, value, unit, id=f'channel-{index:04}'), 'samples': [value, value], 'sample_offsets_ms': [-100, 0]} for index, (metric, unit, value) in enumerate(channels)]
    assert upload(client, connection, *batch).json()['accepted'] == len(channels)
    assert {signal['metric'] for signal in signals(client, org)} == {metric for metric, _, _ in channels}
    assert all(signal['latest']['sample_count'] == 2 for signal in signals(client, org))
    assert not {'fatigue', 'workload', 'deep_work'} & {signal['metric'] for signal in signals(client, org)}
