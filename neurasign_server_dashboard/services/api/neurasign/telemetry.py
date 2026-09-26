"""Brand-independent observations. Transport adapters never choose the tenant.

Source capabilities are immutable: use a new client_source_id when measurement
semantics change. This keeps different methods and summary periods out of the
same series. The existing window ingestion contract remains supported.
"""
from datetime import datetime, timezone
import json
import time
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import Field, field_validator, model_validator

from .workspace import (
    RETENTION_DAYS, Store, Strict, User, device_access, digest,
    member, member_path,
)

from .company_access import employee_data_path, require_employee, can_view_measurement, team_at, capture_allowed

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
    method: str = Field(min_length=1, max_length=100)
    timestamp_basis: Literal['device', 'phone_receipt', 'source_record'] = 'device'
    # A fixed period is part of a series' identity, not a brand-specific field.
    interval_seconds: int | None = Field(None, ge=1, le=7 * 86400)
    availability: Literal['available', 'unsupported', 'permission_required'] = 'available'

    @model_validator(mode='after')
    def semantics(self):
        metric_definition(self.metric, self.unit)
        if self.measurement_kind == 'sample' and self.interval_seconds is not None:
            raise ValueError('A point sample has no aggregation interval.')
        if self.measurement_kind != 'sample' and self.interval_seconds is None:
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
    capabilities: list[Capability] = Field(min_length=1, max_length=20)

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
        if self.metric == 'steps' and value != int(value):
            raise ValueError('Step counts must be whole numbers.')
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
        if len(source_ids) >= 5:
            raise HTTPException(409, 'This gateway has reached its five-source limit.')
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
    now = time.time()
    for observation in body.observations:
        if not now - 7 * 86400 <= observation.measured_at.timestamp() <= now + 5:
            raise HTTPException(422, 'Measurement time must be within the past 7 days and no more than 5 seconds ahead.')

    def write(tx):
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
            capture_allowed(person, observation.measured_at.timestamp(), capability['interval_seconds'])
            payload = observation.model_dump(mode='json')
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
            value = {**payload, **capability, 'id': sample_id, 'series_id': series_id,
                     'value': observation.value * scale + offset, 'unit': definition['unit'],
                     'input_value': observation.value, 'input_unit': observation.unit,
                     'timestamp': timestamp, 'measured_at': timestamp, 'received_at': now,
                     'team_id': team_at(person, timestamp), 'device_id': device_id, 'source': source['source'], 'source_name': source['name'],
                     'adapter': source['adapter'], 'expires_at': timestamp + RETENTION_DAYS * 86400,
                     'content_hash': content_hash}
            tx.put(path, value)
            previous = state['latest'].get(series_id)
            if previous is None or (timestamp, sample_id) > (previous['timestamp'], previous['id']):
                state['latest'][series_id] = value
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
    if not person['sharing']:
        return {'observations': []}
    # Firestore uses the observations series_id + timestamp composite index.
    rows = store.list(f'{employee_data_path(org, person)}/observations', limit=90, order='timestamp', filters={'series_id': series_id})
    now = time.time()
    return {'observations': [public_observation(row) for row in reversed(rows) if row['expires_at'] > now and can_view_measurement(actor, person, row)]}
