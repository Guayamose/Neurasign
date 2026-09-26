"""Company workspaces, explicit sharing and durable authenticated measurements.

The demo orchestrator is never used as a company data store.
"""
from datetime import datetime, timezone
import hashlib
import hmac
import json
import math
import re
import secrets
import time
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .identity import Identity, bearer, get_store, identity, workspace_config
from .company_access import (employee, employee_data_path, save_employee, own_employee, self_employee, employees,
    can_view, can_manage, is_self, require_employee, can_view_measurement, team_at, set_sharing, capture_allowed, require_team)

router = APIRouter(prefix='/api/v1', tags=['Company workspace'])
User = Annotated[Identity, Depends(identity)]
Store = Annotated[object, Depends(get_store)]
FEATURES = ('heart_rate', 'hrv', 'eda', 'temperature', 'movement')
RETENTION_DAYS = 30


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def checked_id(value):
    if not re.fullmatch(r'[a-f0-9]{32,64}', value):
        raise HTTPException(404, 'Not found.')
    return value


def member_path(org, user_id):
    return f'organizations/{checked_id(org)}/members/{checked_id(user_id)}'


def member(store, org, user, manage=False, owner=False):
    value = store.get(member_path(org, digest(user.uid)))
    if not value or not value['active']:
        raise HTTPException(403, 'You do not have access to this workspace.')
    if owner and value['role'] != 'owner' or manage and value['role'] not in ('owner', 'manager'):
        raise HTTPException(403, 'Your role does not allow this action.')
    return value


def public_member(value):
    return {key: value.get(key, False if key == 'sharing' else None) for key in ('id', 'name', 'email', 'role', 'sharing', 'active', 'team_id')} | {'team_ids': value.get('team_ids', [])}


def audit(tx, org, actor, action, target=None):
    now = time.time()
    event = {'id': uuid4().hex, 'actor': actor, 'action': action, 'target': target, 'time': now, 'expires_at': now + 90 * 86400}
    tx.put(f'organizations/{org}/audit/{event["id"]}', event)


def new_member(user, role):
    return {'id': digest(user.uid), 'name': user.name, 'email': user.email, 'role': role, 'active': True, 'team_ids': [], 'joined_at': time.time()}


def device_access(tx, authorization, require_sharing=True):
    token = bearer(authorization)
    match = re.fullmatch(r'nsd_([a-f0-9]{32})\.[A-Za-z0-9_-]{40,64}', token)
    if not match:
        raise HTTPException(401, 'Use a valid device credential.')
    device_id = match.group(1)
    key = tx.get(f'device_keys/{device_id}')
    if not key or key['revoked'] or not hmac.compare_digest(key['token_hash'], digest(token)):
        raise HTTPException(401, 'Device access was revoked or is invalid.')
    org, person_id = key['org'], key['member_id']
    person = employee(tx, org, person_id)
    if not person or not person['active'] or require_sharing and (not person['sharing'] or person.get('deleting')):
        raise HTTPException(403, 'The employee is not currently sharing data.')
    device = tx.get(f'organizations/{org}/devices/{device_id}')
    if not device or device['revoked'] or device['member_id'] != person_id:
        raise HTTPException(401, 'Device access was revoked or is invalid.')
    if require_sharing and not device.get('sharing', True):
        raise HTTPException(403, 'This phone has paused sharing.')
    return device_id, org, person, device


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class CompanyInput(Strict):
    name: str = Field(min_length=2, max_length=80)

    @field_validator('name')
    @classmethod
    def clean_name(cls, value):
        value = value.strip()
        if len(value) < 2:
            raise ValueError('Use at least two characters.')
        return value


class InvitationInput(Strict):
    email: str = Field(min_length=3, max_length=254)
    role: Literal['employee', 'manager'] = 'employee'
    team_id: str | None = Field(None, pattern=r'^[a-f0-9]{32,64}$')
    team_ids: list[str] = Field(default_factory=list, max_length=50)

    @field_validator('email')
    @classmethod
    def email_format(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
            raise ValueError('Enter an email address.')
        return value


class InvitationAccept(Strict):
    token: str = Field(min_length=32, max_length=128)


class SharingInput(Strict):
    enabled: bool


class DeviceInput(CompanyInput):
    source: Literal['wearable', 'recording']


class Measurements(Strict):
    heart_rate: float | None = Field(None, gt=0, le=300)
    hrv: float | None = Field(None, ge=0, le=1000)
    eda: float | None = Field(None, ge=0, le=1000)
    temperature: float | None = Field(None, ge=-50, le=100)
    movement: float | None = Field(None, ge=0, le=1000)

    @model_validator(mode='after')
    def at_least_one(self):
        if all(getattr(self, key) is None for key in FEATURES):
            raise ValueError('At least one measured feature is required.')
        return self


class Reading(Strict):
    id: str = Field(pattern=r'^[A-Za-z0-9_-]{8,80}$')
    timestamp: datetime
    features: Measurements
    window_seconds: int = Field(ge=1, le=300)
    quality: float | None = Field(None, ge=0, le=1)

    @field_validator('timestamp')
    @classmethod
    def aware_time(cls, value):
        if value.tzinfo is None:
            raise ValueError('Use a timestamp with a timezone.')
        return value.astimezone(timezone.utc)


class ReadingBatch(Strict):
    readings: list[Reading] = Field(min_length=1, max_length=60)


@router.get('/config')
def config():
    return workspace_config()


@router.get('/me')
def me(user: User, store: Store):
    account = store.get(f'accounts/{digest(user.uid)}') or {'organizations': []}
    companies = []
    for org in account['organizations']:
        membership = store.get(member_path(org, digest(user.uid)))
        company = store.get(f'organizations/{org}')
        if membership and membership['active'] and company:
            companies.append({**company, 'role': membership['role']})
    return {'name': user.name, 'email': user.email, 'organizations': companies}


@router.post('/organizations', status_code=201)
def create_company(body: CompanyInput, user: User, store: Store):
    org = uuid4().hex
    company = {'id': org, 'name': body.name, 'created_at': time.time(), 'retention_days': RETENTION_DAYS, 'member_count': 1, 'employee_count': 0, 'team_count': 0}
    def create(tx):
        account_path = f'accounts/{digest(user.uid)}'
        account = tx.get(account_path) or {'organizations': []}
        if len(account['organizations']) >= 20:
            raise HTTPException(409, 'The account workspace limit has been reached.')
        tx.put(f'organizations/{org}', company)
        tx.put(member_path(org, digest(user.uid)), new_member(user, 'owner'))
        tx.put(account_path, {'organizations': [*account['organizations'], org]})
        audit(tx, org, digest(user.uid), 'workspace.created')
        return company
    return store.atomic(create)


@router.post('/organizations/{org}/invitations', status_code=201)
def invite(org: str, body: InvitationInput, user: User, store: Store):
    token = secrets.token_urlsafe(32)
    now = time.time()
    def create(tx):
        actor = member(tx, org, user, manage=True)
        if body.role == 'manager' and actor['role'] != 'owner':
            raise HTTPException(403, 'Only the owner can invite another manager.')
        if body.role == 'employee':
            if body.team_ids:
                raise HTTPException(422, 'Employee invitations use a single team.')
            if body.team_id:
                require_team(tx, org, actor, body.team_id)
            elif actor['role'] != 'owner':
                raise HTTPException(403, 'Choose one of your assigned teams.')
        else:
            if body.team_id:
                raise HTTPException(422, 'Manager invitations use assigned teams.')
            for team_id in body.team_ids:
                require_team(tx, org, actor, team_id)
        quota_path = f'organizations/{org}/limits/invitations'
        quota = tx.get(quota_path) or {'day': 0, 'count': 0}
        day = int(now // 86400)
        count = quota['count'] if quota['day'] == day else 0
        if count >= 100:
            raise HTTPException(429, 'Invitation limit reached. Try again tomorrow.')
        value = {'org': org, 'email': body.email, 'role': body.role, 'created_at': now, 'expires_at': now + 72 * 3600, 'accepted_by': None, 'issued_by': actor['id'], 'team_id': body.team_id, 'team_ids': list(set(body.team_ids))}
        tx.put(f'invitations/{digest(token)}', value)
        tx.put(quota_path, {'day': day, 'count': count + 1})
        audit(tx, org, actor['id'], 'invitation.created')
    store.atomic(create)
    return {'token': token, 'email': body.email, 'role': body.role, 'expires_at': now + 72 * 3600}


@router.post('/invitations/accept')
def accept_invite(body: InvitationAccept, user: User, store: Store):
    def accept(tx):
        path = f'invitations/{digest(body.token)}'
        invitation = tx.get(path)
        if not invitation or invitation['expires_at'] <= time.time():
            raise HTTPException(410, 'This invitation is invalid or expired.')
        if invitation['email'] != user.email:
            raise HTTPException(403, 'Sign in with the email address this invitation was sent to.')
        key = digest(user.uid)
        if invitation['accepted_by']:
            if invitation['accepted_by'] == key:
                return {'organization_id': invitation['org']}
            raise HTTPException(409, 'This invitation has already been used.')
        org = invitation['org']
        company = tx.get(f'organizations/{org}')
        if not company or company['member_count'] >= 100:
            raise HTTPException(409, 'This pilot workspace has reached its 100-member limit.')
        existing = tx.get(member_path(org, key))
        if existing:
            raise HTTPException(409, 'This account already has a membership. Ask the workspace owner to manage it.')
        account_path = f'accounts/{key}'
        account = tx.get(account_path) or {'organizations': []}
        if len(account['organizations']) >= 20:
            raise HTTPException(409, 'The account workspace limit has been reached.')
        inviter = tx.get(member_path(org, invitation['issued_by'])) if invitation.get('issued_by') else None
        if invitation.get('issued_by') and (not inviter or not inviter['active'] or inviter['role'] not in ('owner', 'manager')):
            raise HTTPException(410, 'The invitation issuer no longer has access.')
        for team_id in ([invitation['team_id']] if invitation.get('team_id') else invitation.get('team_ids', [])):
            require_team(tx, org, inviter, team_id)
        account_member = {**new_member(user, invitation['role']), 'team_ids': invitation.get('team_ids', [])}
        tx.put(member_path(org, key), account_member)
        if invitation['role'] == 'employee':
            profile = self_employee(account_member)
            if invitation.get('team_id'):
                profile.update(team_id=invitation['team_id'], assignments=[{'team_id': invitation['team_id'], 'from': time.time(), 'until': None}])
            save_employee(tx, org, profile)
        tx.put(f'organizations/{org}', {**company, 'member_count': company['member_count'] + 1})
        tx.put(account_path, {'organizations': [*account['organizations'], org]})
        tx.put(path, {**invitation, 'accepted_by': key})
        audit(tx, org, key, 'invitation.accepted')
        return {'organization_id': org}
    return store.atomic(accept)


def visible_signal(person, latest):
    latest = latest if person['sharing'] else None
    if latest and latest['timestamp'] < time.time() - RETENTION_DAYS * 86400:
        latest = None
    recent = bool(latest and time.time() - latest['timestamp'] <= 60)
    return {**public_member(person), 'status': 'paused' if not person['sharing'] else 'waiting' if not latest else 'current' if recent else 'stale',
            'latest': latest, 'features': latest['features'] if recent else {key: None for key in FEATURES}}


@router.get('/organizations/{org}/dashboard')
def dashboard(org: str, user: User, store: Store):
    from .telemetry import catalog, signal_snapshot
    actor = member(store, org, user)
    people = [person for person in employees(store, org) if can_view(actor, person)]
    device_paths = [f'organizations/{org}/devices/{device_id}' for person in people for device_id in person.get('device_ids', [])]
    devices = [device for device in store.get_many(device_paths).values() if device and not device['revoked']]
    latest = store.get_many([f'organizations/{org}/latest/{person["id"]}' for person in people if person['active'] and person['sharing']])
    states = store.get_many([f'organizations/{org}/signal_state/{person["id"]}' for person in people if person['sharing']])
    source_paths = [f'organizations/{org}/sources/{key}' for device in devices for key in device.get('source_ids', [])]
    sources = [value for value in store.get_many(source_paths).values() if value]
    members = []
    now = time.time()
    for person in people:
        legacy_latest = latest.get(f'organizations/{org}/latest/{person["id"]}')
        if legacy_latest and not can_view_measurement(actor, person, legacy_latest):
            legacy_latest = None
        value = visible_signal(person, legacy_latest)
        state = states.get(f'organizations/{org}/signal_state/{person["id"]}')
        if state:
            state = {**state, 'latest': {key: row for key, row in state['latest'].items() if can_view_measurement(actor, person, row)}}
        value['signals'] = signal_snapshot(person, state,
                                          [source for source in sources if source['member_id'] == person['id']], now)
        if person['sharing'] and value['signals']:
            if any(signal['status'] == 'current' for signal in value['signals']):
                value['status'] = 'current'
            elif value['status'] != 'current' and any(signal['latest'] for signal in value['signals']):
                value['status'] = 'stale'
        members.append(value)
    own = own_employee(store, org, actor)
    teams = [team for team in store.list(f'organizations/{org}/teams', limit=50, filters={'active': True}) if actor['role'] == 'owner' or team['id'] in actor.get('team_ids', [])]
    accounts = store.list(f'organizations/{org}/members', limit=100, filters={'active': True}) if actor['role'] == 'owner' else [actor]
    return {'organization': store.get(f'organizations/{org}'), 'me': {**public_member(actor), 'sharing': bool(own and own['active'] and own['sharing'])},
            'teams': teams, 'accounts': [public_member(account) for account in accounts],
            'members': members, 'metric_catalog': catalog(),
            'devices': devices, 'server_time': now,
            'audit': store.list(f'organizations/{org}/audit', limit=12, order='time') if actor['role'] == 'owner' else []}


@router.get('/organizations/{org}/members/{person_id}/history')
def history(org: str, person_id: str, user: User, store: Store):
    actor = member(store, org, user)
    person = require_employee(store, org, actor, person_id)
    if not person['sharing']:
        return {'readings': []}
    rows = store.list(f'{employee_data_path(org, person)}/readings', limit=90, order='timestamp')
    return {'readings': list(reversed([row for row in rows if row['timestamp'] >= time.time() - RETENTION_DAYS * 86400 and can_view_measurement(actor, person, row)]))}


@router.patch('/organizations/{org}/me/sharing')
def sharing(org: str, body: SharingInput, user: User, store: Store):
    def change(tx):
        actor = member(tx, org, user)
        person = own_employee(tx, org, actor) or self_employee(actor)
        if not person['active']:
            raise HTTPException(403, 'Your employee profile has been removed.')
        person = set_sharing(person, body.enabled)
        save_employee(tx, org, person)
        audit(tx, org, actor['id'], 'sharing.enabled' if body.enabled else 'sharing.paused')
        return public_member(person)
    return store.atomic(change)


@router.post('/organizations/{org}/devices', status_code=201)
def create_device(org: str, body: DeviceInput, user: User, store: Store):
    device_id = uuid4().hex
    token = f'nsd_{device_id}.{secrets.token_urlsafe(32)}'
    def create(tx):
        actor = member(tx, org, user)
        person = own_employee(tx, org, actor)
        if not person or not person['active'] or not person['sharing']:
            raise HTTPException(409, 'Enable your own data sharing before authorizing a device.')
        if len(person['device_ids']) >= 10:
            raise HTTPException(409, 'Revoke an existing device before adding another.')
        device = {'id': device_id, 'name': body.name.strip(), 'source': body.source, 'member_id': actor['id'], 'created_at': time.time(), 'revoked': False, 'last_received_at': None}
        tx.put(f'organizations/{org}/devices/{device_id}', device)
        tx.put(f'device_keys/{device_id}', {'org': org, 'member_id': actor['id'], 'token_hash': digest(token), 'revoked': False})
        save_employee(tx, org, {**person, 'device_ids': [*person['device_ids'], device_id]})
        audit(tx, org, actor['id'], 'device.authorized', device_id)
        return {'device': device, 'credential': token}
    return store.atomic(create)


@router.delete('/organizations/{org}/devices/{device_id}')
def revoke_device(org: str, device_id: str, user: User, store: Store):
    checked_id(device_id)
    def revoke(tx):
        actor = member(tx, org, user)
        path = f'organizations/{org}/devices/{device_id}'
        device = tx.get(path)
        if not device:
            raise HTTPException(404, 'Device not found.')
        target = require_employee(tx, org, actor, device['member_id'])
        key = tx.get(f'device_keys/{device_id}')
        tx.put(path, {**device, 'revoked': True})
        tx.put(f'device_keys/{device_id}', {**key, 'revoked': True})
        save_employee(tx, org, {**target, 'device_ids': [item for item in target['device_ids'] if item != device_id]})
        audit(tx, org, actor['id'], 'device.revoked', device_id)
        return {'revoked': True}
    return store.atomic(revoke)


@router.delete('/organizations/{org}/members/{person_id}')
def remove_member(org: str, person_id: str, user: User, store: Store):
    def remove(tx):
        actor = member(tx, org, user, owner=True)
        path = member_path(org, person_id)
        target = tx.get(path)
        if not target:
            raise HTTPException(404, 'Member not found.')
        if target['role'] == 'owner':
            raise HTTPException(409, 'The workspace owner cannot be removed.')
        company = tx.get(f'organizations/{org}')
        profile = own_employee(tx, org, target)
        for device_id in (profile or {}).get('device_ids', []):
            key_path = f'device_keys/{device_id}'
            device_path = f'organizations/{org}/devices/{device_id}'
            key, device = tx.get(key_path), tx.get(device_path)
            if key:
                tx.put(key_path, {**key, 'revoked': True})
            if device:
                tx.put(device_path, {**device, 'revoked': True})
        tx.put(path, {**target, 'active': False})
        if profile:
            save_employee(tx, org, {**profile, 'active': False, 'sharing': False, 'device_ids': []})
        if target['active']:
            tx.put(f'organizations/{org}', {**company, 'member_count': max(1, company['member_count'] - 1)})
        audit(tx, org, actor['id'], 'member.removed', person_id)
        return {'removed': True}
    return store.atomic(remove)


@router.delete('/organizations/{org}/me/readings')
def delete_my_readings(org: str, user: User, store: Store):
    # Disable ingestion transactionally first. Concurrent uploads must recheck
    # this same member document before committing, including Firestore retries.
    def begin(tx):
        actor = member(tx, org, user)
        person = own_employee(tx, org, actor)
        if not person:
            raise HTTPException(404, 'No employee measurements exist for this account.')
        person = {**set_sharing(person, False), 'deleting': True}
        save_employee(tx, org, person)
        return person
    actor = store.atomic(begin)
    removed = 0
    for kind in ('readings', 'observations'):
        collection = f'{employee_data_path(org, actor)}/{kind}'
        while rows := store.list(collection, limit=200):
            def remove(tx):
                for row in rows:
                    tx.delete(f'{collection}/{row["id"]}')
            store.atomic(remove)
            removed += len(rows)
    def finish(tx):
        current = employee(tx, org, actor['id'])
        save_employee(tx, org, {**current, 'deleting': False, 'sharing': False})
        tx.delete(f'organizations/{org}/latest/{actor["id"]}')
        tx.delete(f'organizations/{org}/signal_state/{actor["id"]}')
        audit(tx, org, actor['id'], 'readings.deleted')
    store.atomic(finish)
    return {'deleted': removed, 'sharing': False}


@router.post('/readings')
def ingest(body: ReadingBatch, store: Store, authorization: str | None = Header(None)):
    token = bearer(authorization)
    match = re.fullmatch(r'nsd_([a-f0-9]{32})\.[A-Za-z0-9_-]{40,64}', token)
    if not match:
        raise HTTPException(401, 'Use a valid device credential.')
    device_id = match.group(1)
    now = time.time()
    readings = []
    for reading in body.readings:
        timestamp = reading.timestamp.timestamp()
        if timestamp < now - 7 * 86400 or timestamp > now + 5:
            raise HTTPException(422, 'Measurement time must be within the past 7 days and no more than 5 seconds ahead.')
        row = reading.model_dump(mode='json')
        row['timestamp'] = timestamp
        readings.append(row)
    def write(tx):
        _, org, membership, device = device_access(tx, authorization)
        person = membership['id']
        device_path = f'organizations/{org}/devices/{device_id}'
        # Limit each device to 120 accepted batches/minute across all instances.
        minute = int(now // 60)
        requests = device.get('request_count', 0) if device.get('request_minute') == minute else 0
        if requests >= 120:
            raise HTTPException(429, 'Device upload rate exceeded. Batch measurements and retry later.')
        latest_path = f'organizations/{org}/latest/{person}'
        latest = tx.get(latest_path)
        accepted = duplicate = 0
        for row in readings:
            capture_allowed(membership, row['timestamp'], row['window_seconds'])
            sample_id = digest(f'{device_id}:{row["id"]}')
            path = f'{employee_data_path(org, membership)}/readings/{sample_id}'
            content_hash = digest(json.dumps(row, sort_keys=True, separators=(',', ':'), allow_nan=False))
            existing = tx.get(path)
            if existing:
                if existing['content_hash'] != content_hash:
                    raise HTTPException(409, 'A reading ID was reused with different data.')
                duplicate += 1
                continue
            value = {**row, 'team_id': team_at(membership, row['timestamp']), 'id': sample_id, 'device_id': device_id, 'source': device['source'], 'received_at': now, 'expires_at': row['timestamp'] + RETENTION_DAYS * 86400, 'content_hash': content_hash}
            tx.put(path, value)
            if latest is None or value['timestamp'] > latest['timestamp']:
                latest = value
            accepted += 1
        if accepted:
            tx.put(latest_path, latest)
        tx.put(device_path, {**device, 'last_received_at': now, 'request_minute': minute, 'request_count': requests + 1})
        return {'accepted': accepted, 'duplicates': duplicate, 'received_at': now}
    return store.atomic(write)
