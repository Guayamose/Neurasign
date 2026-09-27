"""Brand-independent observations. Transport adapters never choose the tenant.

Source capabilities are immutable: use a new client_source_id when measurement
semantics change. This keeps different methods and summary periods out of the
same series. The existing window ingestion contract remains supported.
"""
from datetime import datetime, timezone
import json
import math
import time
from typing import Annotated, Literal

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import Field, field_validator, model_validator

from .workspace import (
    RETENTION_DAYS, Store, Strict, User, device_access, digest,
    member, member_path,
)

from .company_access import employee_data_path, require_employee, require_measurements, can_view_measurement, team_at, capture_allowed

router = APIRouter(prefix='/api/v1', tags=['Wearable telemetry'])

# Unit transforms are scale + offset into the server's canonical unit.
# Limits validate the transport; they are not clinical thresholds.
METRICS = {
    'heart_rate': dict(name='Heart rate', unit='bpm', digits=0, minimum=0, maximum=300, positive=True, freshness_seconds=60,
        meaning='Heartbeats per minute.', units={'bpm': (1, 0), 'Hz': (60, 0)}),
    'hrv_rmssd': dict(name='HRV · RMSSD', unit='ms', digits=1, minimum=0, maximum=1000, freshness_seconds=60,
        meaning='Variation between successive beat intervals, using RMSSD. Compare the same method and measurement period.', units={'ms': (1, 0), 's': (1000, 0)}),
    'hrv_sdnn': dict(name='HRV · SDNN', unit='ms', digits=1, minimum=0, maximum=1000, freshness_seconds=60,
        meaning='Standard deviation of normal beat intervals. This is a different quantity from RMSSD.', units={'ms': (1, 0), 's': (1000, 0)}),
    'electrodermal_conductance': dict(name='Skin conductance', unit='µS', digits=2, minimum=0, maximum=1000, freshness_seconds=60,
        meaning='Electrical conductance at the skin. This does not identify an emotion or its cause.', units={'µS': (1, 0), 'uS': (1, 0), 'S': (1000000, 0)}),
    'skin_temperature': dict(name='Skin temperature', unit='°C', digits=1, minimum=-50, maximum=100, freshness_seconds=60,
        meaning='Absolute temperature at the skin sensor, not core body temperature.', units={'°C': (1, 0), 'Cel': (1, 0), '°F': (5 / 9, -160 / 9)}),
    'skin_temperature_delta': dict(name='Skin temperature change', unit='°C', digits=1, minimum=-50, maximum=50, freshness_seconds=60,
        meaning='Change from the source baseline. This is not an absolute skin temperature.', units={'°C': (1, 0), 'Cel': (1, 0), '°F': (5 / 9, 0)}),
    'acceleration_magnitude_std': dict(name='Movement', unit='g', digits=3, minimum=0, maximum=1000, freshness_seconds=60,
        meaning='Standard deviation of acceleration magnitude over the reported interval. This is not a step count.', units={'g': (1, 0), 'm/s²': (1 / 9.80665, 0)}),
    'respiratory_rate': dict(name='Respiratory rate', unit='breaths/min', digits=1, minimum=0, maximum=150, freshness_seconds=60,
        meaning='Breaths per minute over the reported measurement interval.', units={'breaths/min': (1, 0), 'Hz': (60, 0)}),
    'oxygen_saturation': dict(name='Oxygen saturation', unit='%', digits=1, minimum=0, maximum=100, freshness_seconds=60,
        meaning='Oxygen saturation reported by the sensor, with its measurement method preserved.', units={'%': (1, 0), 'fraction': (100, 0)}),
    'steps': dict(name='Steps', unit='count', digits=0, minimum=0, maximum=1000000, freshness_seconds=60,
        meaning='Steps counted during the reported interval. Counts from overlapping sources are not added together.', units={'count': (1, 0)}),
}

# Raw channels remain separate from derived metrics. Limits are transport bounds.
def raw_metric(name, unit, meaning, minimum, maximum, units=None, digits=3):
    return dict(name=name, unit=unit, digits=digits, minimum=minimum, maximum=maximum,
                freshness_seconds=60, meaning=meaning, units=units or {unit: (1, 0)})


METRICS.update({
    'rr_interval': raw_metric('Beat interval · RR', 'ms', 'Individual beat interval reported by the heart-rate sensor. This is not an HRV score.', 1, 65535, {'ms': (1, 0), 's': (1000, 0)}, 1),
    'ppi_interval': raw_metric('Pulse interval · PPI', 'ms', 'Raw interval between optical pulse peaks; check the accompanying PPI sensor flags. Zero denotes unavailable. This is not an HRV score.', 0, 65535, digits=1),
    'ppi_error': raw_metric('PPI error estimate', 'ms', 'Error estimate supplied by the optical sensor for its pulse interval.', 0, 65535, digits=1),
    'ppi_flags': raw_metric('PPI sensor flags', 'bitmask', 'Polar PPI flags: bit 0 invalid interval; bit 1 contact detected; bit 2 contact detection unsupported.', 0, 7, digits=0),
    'electrocardiogram': raw_metric('ECG', 'µV', 'Raw electrical cardiac waveform. No rhythm classification is performed.', -20000000, 20000000, {'µV': (1, 0), 'mV': (1000, 0)}),
    'blood_volume_pulse': raw_metric('Blood volume pulse', 'a.u.', 'Optical pulse waveform in source-specific arbitrary units. Values from different sensors are not interchangeable.', -2147483648, 2147483647),
    'core_body_temperature': raw_metric('Core body temperature', '°C', 'Temperature explicitly identified by the source as core body temperature.', 0, 100, {'°C': (1, 0), '°F': (5 / 9, -160 / 9)}, 2),
    'body_temperature': raw_metric('Body temperature', '°C', 'Temperature reported by a health thermometer. It is not automatically classified as skin or core temperature.', -50, 100, {'°C': (1, 0), '°F': (5 / 9, -160 / 9)}, 2),
    'sensor_temperature': raw_metric('Sensor temperature', '°C', 'Temperature stream with unspecified measurement location. Do not equate this with skin temperature.', -100, 200, digits=2),
    'barometric_pressure': raw_metric('Barometric pressure', 'hPa', 'Atmospheric pressure reported by the sensor. This is not blood pressure.', 0, 20000, digits=2),
})
for axis in ('x', 'y', 'z'):
    METRICS[f'acceleration_{axis}'] = raw_metric(f'Acceleration · {axis.upper()}', 'g', 'Raw acceleration along the sensor axis, including gravity.', -1000, 1000, {'g': (1, 0), 'mg': (.001, 0), 'm/s²': (1 / 9.80665, 0)})
    METRICS[f'angular_velocity_{axis}'] = raw_metric(f'Angular velocity · {axis.upper()}', '°/s', 'Raw gyroscope measurement along the sensor axis.', -100000, 100000)
    METRICS[f'magnetic_field_{axis}'] = raw_metric(f'Magnetic field · {axis.upper()}', 'gauss', 'Raw magnetic field along the sensor axis.', -100000, 100000)
for channel in (*map(str, range(1, 25)), 'ambient'):
    METRICS[f'ppg_{channel}'] = raw_metric(f'PPG · {channel}', 'a.u.', 'Raw optical sensor channel in source-specific units. No oxygen saturation or HRV is inferred.', -2147483648, 2147483647)

for color in ('green', 'red', 'ir'):
    METRICS[f'ppg_{color}'] = raw_metric(f'PPG · {color.upper()}', 'a.u.', 'Raw optical channel at the named LED wavelength. Arbitrary sensor units are not interchangeable across sources.', -2147483648, 2147483647)

for metric, name, meaning, minimum, maximum in (
    ('ppi_status', 'Pulse interval quality', 'Samsung optical interval status: 0 normal, -1 error. This is separate from Polar PPI flags.', -1, 0),
    ('heart_rate_status', 'Heart rate quality', 'Samsung heart rate status: 1 successful; 0 measuring; negative values identify movement, contact or sensor errors.', -999, 1),
    ('eda_status', 'EDA quality', 'Samsung EDA status: 0 normal, -5 detached, -10 low signal quality.', -10, 0),
    ('skin_temperature_status', 'Temperature quality', 'Samsung temperature status: 0 normal, -1 error.', -1, 0),
    ('ecg_contact', 'ECG electrode contact', 'Samsung ECG lead-off code: 0 indicates electrode contact; other values indicate no contact.', 0, 255),
    ('oxygen_status', 'Oxygen measurement status', 'Samsung SpO2 status: 2 complete, 0 calculating, negative values identify timeout, movement or low quality.', -6, 2),
    ('ppg_green_status', 'Green PPG quality', 'Samsung optical channel status: 0 normal, -1 unavailable or blocked.', -1, 0),
    ('ppg_ir_status', 'Infrared PPG quality', 'Samsung optical channel status: 0 normal, -1 unavailable or blocked.', -1, 0),
    ('ppg_red_status', 'Red PPG quality', 'Samsung optical channel status: 0 normal, -1 unavailable or blocked.', -1, 0),
    ('heart_rate_contact', 'Heart sensor contact', 'Bluetooth heart sensor contact: 1 detected, 0 not detected. Only reported when the device supports contact detection.', 0, 1),
    ('body_temperature_site', 'Thermometer site', 'Bluetooth thermometer location code: 1 armpit, 2 body, 3 ear, 4 finger, 5 gastrointestinal, 6 mouth, 7 rectum, 8 toe, 9 eardrum.', 1, 9),
    ('magnetic_calibration', 'Magnetometer calibration', 'Polar calibration quality code: 0 unknown, 1 poor, 2 OK, 3 good.', 0, 3),
):
    METRICS[metric] = {**raw_metric(name, 'code', meaning, minimum, maximum, digits=0), 'integer': True, 'category': 'quality'}
for metric, name, maximum in (
    ('oximeter_measurement_status', 'Oximeter measurement flags', 65535),
    ('oximeter_sensor_status', 'Oximeter sensor flags', 16777215),
    ('ecg_raw_flags', 'ECG raw status', 16777215),
    ('ppg_raw_flags', 'PPG raw status', 16777215),
):
    METRICS[metric] = {**raw_metric(name, 'bitmask', 'Raw device status bits. Consult the source protocol; this is not a physiological score.', 0, maximum, digits=0), 'integer': True, 'category': 'quality'}
METRICS['ecg_sequence'] = {**raw_metric('ECG packet sequence', 'count', 'Samsung ECG sequence counter, wrapping at 255. It is not a beat count.', 0, 255, digits=0), 'integer': True, 'category': 'quality'}
for channel in (1, 2):
    METRICS[f'ecg_adc_{channel}'] = raw_metric(f'ECG ADC · {channel}', 'a.u.', 'Unscaled electrical sensor channel from Polar frame 3. It must not be treated as microvolts without a documented conversion.', -8388608, 8388607)
METRICS['energy_expended'] = raw_metric('Sensor energy counter', 'kJ', 'Cumulative energy reported by the heart-rate sensor. It may reset; do not sum successive readings.', 0, 65535, digits=0)
METRICS['pulse_amplitude_index'] = raw_metric('Pulse amplitude index', '%', 'Perfusion-related amplitude index reported by the oximeter. It is not oxygen saturation.', 0, 1000000)
for speed in ('fast', 'slow'):
    METRICS[f'oxygen_saturation_{speed}'] = raw_metric(f'Oxygen saturation · {speed}', '%', f'Device {speed} estimate from the pulse oximeter. Smoothing differs from the normal estimate.', 0, 100)
    METRICS[f'pulse_rate_{speed}'] = raw_metric(f'Pulse rate · {speed}', 'bpm', f'Device {speed} pulse estimate. Kept separate from normal pulse because its smoothing differs.', 0, 300)


def metric_definition(metric, unit=None):
    definition = METRICS.get(metric)
    if not definition or unit is not None and unit not in definition['units']:
        raise ValueError('Unknown metric or incompatible unit. See /api/v1/metrics.')
    return definition


def catalog():
    return [{**{key: value for key, value in definition.items() if key not in ('units', 'positive')},
             'id': key, 'accepted_units': list(definition['units'])} for key, definition in METRICS.items()]


class Capability(Strict):
    metric: str = Field(min_length=1, max_length=64)
    unit: str = Field(min_length=1, max_length=20)
    delivery_mode: Literal['stream', 'sync']
    measurement_kind: Literal['sample', 'window', 'summary']
    method: str = Field(min_length=1, max_length=256)
    timestamp_basis: Literal['device', 'phone_receipt', 'source_record'] = 'device'
    # A fixed period is part of a series' identity, not a brand-specific field.
    interval_seconds: int | None = Field(None, ge=1, le=7 * 86400)
    availability: Literal['available', 'unsupported', 'permission_required'] = 'available'
    interval_variable: bool = False

    @model_validator(mode='after')
    def semantics(self):
        metric_definition(self.metric, self.unit)
        if self.measurement_kind == 'sample' and self.interval_seconds is not None:
            raise ValueError('A point sample has no aggregation interval.')
        if self.interval_variable and (self.measurement_kind != 'summary' or self.interval_seconds is not None):
            raise ValueError('Variable periods require a summary with its period on each observation.')
        if self.measurement_kind != 'sample' and self.interval_seconds is None and not self.interval_variable:
            raise ValueError('Windows and summaries require their measurement interval.')
        if self.measurement_kind == 'window' and self.interval_seconds > 300:
            raise ValueError('Use summary for measurement intervals longer than five minutes.')
        if self.metric in ('hrv_rmssd', 'hrv_sdnn', 'acceleration_magnitude_std', 'steps') and self.measurement_kind == 'sample':
            raise ValueError('This metric requires a measurement interval.')
        if not self.method.strip():
            raise ValueError('Specify the measurement method.')
        return self


class AdapterInfo(Strict):
    id: str = Field(pattern=r'^[a-z0-9][a-z0-9._-]{0,63}$')
    version: str = Field(min_length=1, max_length=40)


class SourceInput(Strict):
    client_source_id: str = Field(pattern=r'^[A-Za-z0-9_-]{8,80}$')
    name: str = Field(min_length=1, max_length=80)
    adapter: AdapterInfo
    transport: Literal['ble', 'vendor_sdk', 'health_store', 'cloud_api', 'recording']
    manufacturer: str | None = Field(None, max_length=80)
    model: str | None = Field(None, max_length=80)
    firmware: str | None = Field(None, max_length=80)
    capabilities: list[Capability] = Field(min_length=1, max_length=64)

    @model_validator(mode='after')
    def unique_metrics(self):
        keys = [item.metric for item in self.capabilities]
        if len(keys) != len(set(keys)):
            raise ValueError('Use separate logical sources for different methods or periods of the same metric.')
        return self


class Observation(Strict):
    id: str = Field(pattern=r'^[A-Za-z0-9_-]{8,80}$')
    source_id: str = Field(pattern=r'^[a-f0-9]{64}$')
    metric: str = Field(min_length=1, max_length=64)
    value: float = Field(strict=True)
    unit: str = Field(min_length=1, max_length=20)
    measured_at: datetime
    source_record_id: str | None = Field(None, min_length=1, max_length=120)
    interval_seconds: int | None = Field(None, ge=1, le=7 * 86400)
    samples: list[Annotated[float, Field(strict=True, allow_inf_nan=False)]] | None = Field(None, min_length=1, max_length=512)
    sample_offsets_ms: list[Annotated[float, Field(strict=True, allow_inf_nan=False)]] | None = Field(None, min_length=1, max_length=512)
    device_timestamp_ns: str | None = Field(None, pattern=r'^\d{1,20}$')

    @field_validator('measured_at')
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError('Use a timestamp with a timezone.')
        return value.astimezone(timezone.utc)

    @model_validator(mode='after')
    def quantity(self):
        definition = metric_definition(self.metric, self.unit)
        scale, offset = definition['units'][self.unit]
        value = self.value * scale + offset
        if not definition['minimum'] <= value <= definition['maximum'] or definition.get('positive') and value == 0:
            raise ValueError('Measurement is outside the accepted transport range.')
        if (self.metric in ('steps', 'ppi_flags') or definition.get('integer')) and value != int(value):
            raise ValueError('Counts and bitmasks must be whole numbers.')
        if (self.samples is None) != (self.sample_offsets_ms is None):
            raise ValueError('Samples and offsets must be provided together.')
        if self.samples is not None:
            offsets = self.sample_offsets_ms
            if len(self.samples) != len(offsets) or offsets[-1] != 0 or offsets[0] < -10000:
                raise ValueError('A sample block must end at measured_at and cover at most 10 seconds.')
            if any(not math.isfinite(item) or item > 0 for item in offsets) or any(a > b for a, b in zip(offsets, offsets[1:])):
                raise ValueError('Sample offsets must be finite, ordered and non-positive.')
            if self.samples[-1] != self.value:
                raise ValueError('The scalar value must equal the last sample.')
            for sample in self.samples:
                converted = sample * scale + offset
                if not definition['minimum'] <= converted <= definition['maximum'] or definition.get('positive') and converted == 0:
                    raise ValueError('A raw sample is outside the accepted transport range.')
                if (self.metric == 'ppi_flags' or definition.get('integer')) and converted != int(converted):
                    raise ValueError('Bitmasks must be whole numbers.')
        return self


class ObservationBatch(Strict):
    schema_version: Literal[2]
    observations: list[Observation] = Field(min_length=1, max_length=60)


@router.get('/metrics')
def metrics():
    return {'schema_version': 2, 'metrics': catalog()}


@router.get('/gateway/sources')
def sources(store: Store, authorization: str | None = Header(None)):
    def read(tx):
        _, org, person, device = device_access(tx, authorization, require_sharing=False)
        return {'sources': [public_source(tx.get(f'organizations/{org}/sources/{key}')) for key in device.get('source_ids', [])]}
    return store.atomic(read)


@router.post('/gateway/sources', status_code=201)
def register_source(body: SourceInput, store: Store, authorization: str | None = Header(None)):
    payload = body.model_dump(mode='json')
    for cap in payload['capabilities']:
        if not cap['interval_variable']:
            del cap['interval_variable']  # Preserve hashes for existing scalar/raw sources.
    def create(tx):
        device_id, org, person, device = device_access(tx, authorization)
        if body.transport == 'recording' and device['source'] != 'recording':
            raise HTTPException(422, 'Recorded inputs require a recording credential.')
        source_id = digest(f'{device_id}:{body.client_source_id}')
        path = f'organizations/{org}/sources/{source_id}'
        existing = tx.get(path)
        semantics = {**payload, 'capabilities': [{key: value for key, value in capability.items() if key != 'availability'}
                                                for capability in payload['capabilities']]}
        content_hash = digest(json.dumps(semantics, sort_keys=True, separators=(',', ':'), allow_nan=False))
        if existing:
            if existing['content_hash'] != content_hash:
                raise HTTPException(409, 'Source capabilities are immutable. Register a new source ID for changed semantics.')
            # Permissions may change without changing the meaning of a series.
            existing = {**existing, 'capabilities': payload['capabilities']}
            tx.put(path, existing)
            return {'source': public_source(existing)}
        source_ids = device.get('source_ids', [])
        if len(source_ids) >= 16:
            raise HTTPException(409, 'This gateway has reached its 16-source limit.')
        # Multiple protocols/SDKs can share a phone. Bound cached channel state
        # independently from the number of logical sources.
        channel_count = sum(len(tx.get(f'organizations/{org}/sources/{key}')['capabilities']) for key in source_ids)
        if channel_count + len(body.capabilities) > 96:
            raise HTTPException(409, 'This gateway has reached its 96-channel limit.')
        value = {**payload, 'id': source_id, 'device_id': device_id, 'member_id': person['id'],
                 'source': device['source'], 'content_hash': content_hash, 'created_at': time.time()}
        tx.put(path, value)
        tx.put(f'organizations/{org}/devices/{device_id}', {**device, 'source_ids': [*source_ids, source_id]})
        return {'source': public_source(value)}
    return store.atomic(create)


def public_source(value):
    return {key: item for key, item in value.items() if key not in ('content_hash', 'client_source_id')}


@router.post('/observations')
def observations(body: ObservationBatch, store: Store, authorization: str | None = Header(None)):
    return ingest_observations(body, store, authorization)


def ingest_observations(body, store, authorization, guard=None):
    now = time.time()
    for observation in body.observations:
        first = observation.measured_at.timestamp() + ((observation.sample_offsets_ms or [0])[0] / 1000)
        if not now - 7 * 86400 <= first <= observation.measured_at.timestamp() <= now + 5:
            raise HTTPException(422, 'Measurement time must be within the past 7 days and no more than 5 seconds ahead.')

    def write(tx):
        if guard:
            guard(tx)
        device_id, org, person, device = device_access(tx, authorization)
        minute = int(now // 60)
        requests = device.get('request_count', 0) if device.get('request_minute') == minute else 0
        if requests >= 120:
            raise HTTPException(429, 'Device upload rate exceeded. Batch measurements and retry later.')
        state_path = f'organizations/{org}/signal_state/{person["id"]}'
        state = tx.get(state_path) or {'id': person['id'], 'latest': {}}
        # Bound cached state across expired/replaced gateways. History is separate.
        active = set(person['device_ids'])
        state['latest'] = {key: row for key, row in state['latest'].items()
                           if row['device_id'] in active and row['expires_at'] > now}
        accepted = duplicates = 0
        for observation in body.observations:
            source = tx.get(f'organizations/{org}/sources/{observation.source_id}')
            if not source or source['device_id'] != device_id or source['member_id'] != person['id']:
                raise HTTPException(403, 'This source does not belong to the authenticated gateway.')
            capability = next((item for item in source['capabilities'] if item['metric'] == observation.metric), None)
            if not capability or capability['availability'] != 'available' or capability['unit'] != observation.unit:
                raise HTTPException(422, 'Measurement does not match the registered source capability.')
            interval = capability['interval_seconds']
            if capability.get('interval_variable'):
                if observation.interval_seconds is None:
                    raise HTTPException(422, 'This summary requires its original measurement period.')
                interval = observation.interval_seconds
            elif observation.interval_seconds is not None:
                raise HTTPException(422, 'This source has a fixed measurement period.')
            duration = -(observation.sample_offsets_ms or [0])[0] / 1000
            if observation.samples is not None and capability['measurement_kind'] != 'sample':
                raise HTTPException(422, 'Raw sample blocks require a point-sample capability.')
            timestamp = observation.measured_at.timestamp()
            capture_allowed(person, timestamp, duration or interval)
            # A block must not span a team boundary and disclose the old team's data.
            if any(timestamp - (duration or interval or 0) < assignment['from'] <= timestamp for assignment in person.get('assignments', [])):
                raise HTTPException(422, 'Measurements must not span team changes.')
            payload = observation.model_dump(mode='json')
            # Preserve the content hashes of previously accepted v2 scalar observations.
            for key in ('samples', 'sample_offsets_ms', 'device_timestamp_ns', 'interval_seconds'):
                if payload[key] is None:
                    del payload[key]
            content_hash = digest(json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False))
            sample_id = digest(f'{device_id}:{observation.id}')
            path = f'{employee_data_path(org, person)}/observations/{sample_id}'
            existing = tx.get(path)
            if existing:
                if existing['content_hash'] != content_hash:
                    raise HTTPException(409, 'An observation ID was reused with different data.')
                duplicates += 1
                continue
            definition = METRICS[observation.metric]
            scale, offset = definition['units'][observation.unit]
            timestamp = observation.measured_at.timestamp()
            series_id = digest(f'{source["id"]}:{observation.metric}')
            value = {**payload, **capability, 'interval_seconds': interval, 'id': sample_id, 'series_id': series_id,
                     'value': observation.value * scale + offset, 'unit': definition['unit'],
                     'input_value': observation.value, 'input_unit': observation.unit,
                     'timestamp': timestamp, 'measured_at': timestamp, 'received_at': now,
                     'team_id': team_at(person, timestamp), 'device_id': device_id, 'source': source['source'], 'source_name': source['name'],
                     'adapter': source['adapter'], 'expires_at': timestamp + RETENTION_DAYS * 86400,
                     'content_hash': content_hash}
            if observation.samples is not None:
                value.update(samples=[sample * scale + offset for sample in observation.samples],
                             input_samples=observation.samples, sample_count=len(observation.samples),
                             sample_duration_ms=duration * 1000)
            tx.put(path, value)
            previous = state['latest'].get(series_id)
            if previous is None or (timestamp, now, sample_id) > (previous['timestamp'], previous['received_at'], previous['id']):
                state['latest'][series_id] = {key: item for key, item in value.items()
                                             if key not in ('samples', 'input_samples', 'sample_offsets_ms')}
            accepted += 1
        if accepted:
            state['expires_at'] = max(row['expires_at'] for row in state['latest'].values())
            tx.put(state_path, state)
        tx.put(f'organizations/{org}/devices/{device_id}', {**device, 'last_received_at': now,
            'request_minute': minute, 'request_count': requests + 1})
        return {'accepted': accepted, 'duplicates': duplicates, 'received_at': now}
    return store.atomic(write)


def public_observation(row):
    return {key: value for key, value in row.items() if key not in ('content_hash', 'expires_at')}


def signal_snapshot(person, state, sources, now):
    """Do not return paused data, or treat recent receipt as recent measurement."""
    latest = (state or {}).get('latest', {}) if person['sharing'] else {}
    signals = []
    for source in sources:
        for capability in source['capabilities']:
            series_id = digest(f'{source["id"]}:{capability["metric"]}')
            row = latest.get(series_id)
            if row and row['expires_at'] <= now:
                row = None
            if not person['sharing']:
                status = 'paused'
            elif capability['availability'] != 'available':
                status = capability['availability']
            elif not row:
                status = 'waiting'
            elif capability['measurement_kind'] == 'summary':
                status = 'summary'
            else:
                status = 'current' if now - row['timestamp'] <= METRICS[capability['metric']]['freshness_seconds'] else 'delayed'
            signals.append({**capability, 'series_id': series_id, 'source_id': source['id'], 'source_name': source['name'],
                            'source': source['source'], 'unit': METRICS[capability['metric']]['unit'], 'status': status,
                            'latest': public_observation(row) if row else None})
    return signals


@router.get('/organizations/{org}/members/{person_id}/observations')
def observation_history(org: str, person_id: str, user: User, store: Store, series_id: str = Query(pattern=r'^[a-f0-9]{64}$')):
    actor = member(store, org, user)
    person = require_employee(store, org, actor, person_id)
    require_measurements(actor, person)
    if not person['sharing']:
        return {'observations': []}
    # Firestore uses the observations series_id + timestamp composite index.
    rows = store.list(f'{employee_data_path(org, person)}/observations', limit=90, order='timestamp', filters={'series_id': series_id})
    now = time.time()
    return {'observations': [public_observation(row) for row in reversed(rows) if row['expires_at'] > now and can_view_measurement(actor, person, row)]}
