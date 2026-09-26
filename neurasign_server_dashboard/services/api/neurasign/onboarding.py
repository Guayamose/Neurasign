"""Team-scoped administration and single-use employee phone enrollment."""
import hmac
import re
import secrets
import time
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException
from pydantic import Field

from .workspace import (Store, User, Strict, CompanyInput, SharingInput, member, member_path,
                        public_member, audit, digest, device_access)
from .company_access import (employee, employee_path, save_employee, require_employee, require_team,
                             can_manage, identifier, set_sharing)

router = APIRouter(prefix='/api/v1', tags=['Teams and phone enrollment'])


class EmployeeInput(CompanyInput):
    team_id: str = Field(pattern=r'^[a-f0-9]{32,64}$')


class TeamGrants(Strict):
    team_ids: list[str] = Field(max_length=50)


class EnrollmentInput(Strict):
    source: Literal['wearable', 'recording'] = 'wearable'


class EnrollmentToken(Strict):
    token: str = Field(pattern=r'^nse_[a-f0-9]{32}\.[A-Za-z0-9_-]{43}$')


class EnrollmentClaim(EnrollmentToken):
    installation_id: str = Field(pattern=r'^[A-Za-z0-9_-]{16,80}$')
    claim_secret: str = Field(pattern=r'^[A-Za-z0-9_-]{43}$')
    phone_name: str = Field(min_length=2, max_length=80)
    consent: Literal[True]


@router.post('/organizations/{org}/teams', status_code=201)
def create_team(org: str, body: CompanyInput, user: User, store: Store):
    team_id = uuid4().hex
    def create(tx):
        actor = member(tx, org, user, owner=True)
        company = tx.get(f'organizations/{org}')
        if company.get('team_count', 0) >= 50:
            raise HTTPException(409, 'This workspace has reached its 50-team pilot limit.')
        value = {'id': team_id, 'name': body.name, 'active': True, 'created_at': time.time()}
        tx.put(f'organizations/{org}/teams/{team_id}', value)
        tx.put(f'organizations/{org}', {**company, 'team_count': company.get('team_count', 0) + 1})
        audit(tx, org, actor['id'], 'team.created', team_id)
        return value
    return store.atomic(create)


@router.post('/organizations/{org}/employees', status_code=201)
def create_employee(org: str, body: EmployeeInput, user: User, store: Store):
    person_id = uuid4().hex
    def create(tx):
        actor = member(tx, org, user, manage=True)
        require_team(tx, org, actor, body.team_id)
        company = tx.get(f'organizations/{org}')
        if company.get('employee_count', 0) >= 100:
            raise HTTPException(409, 'This workspace has reached its 100-employee pilot limit.')
        now = time.time()
        value = {'id': person_id, 'name': body.name, 'email': None, 'role': 'employee',
                 'linked_member_id': None, 'storage_root': 'employees', 'team_id': body.team_id,
                 'assignments': [{'team_id': body.team_id, 'from': now, 'until': None}],
                 'sharing': False, 'active': True, 'device_ids': [], 'paused_intervals': [], 'joined_at': now}
        save_employee(tx, org, value)
        tx.put(f'organizations/{org}', {**company, 'employee_count': company.get('employee_count', 0) + 1})
        audit(tx, org, actor['id'], 'employee.created', person_id)
        return public_member(value)
    return store.atomic(create)


@router.patch('/organizations/{org}/employees/{person_id}')
def update_employee(org: str, person_id: str, body: EmployeeInput, user: User, store: Store):
    def update(tx):
        actor = member(tx, org, user, manage=True)
        person = require_employee(tx, org, actor, person_id, manage=True)
        require_team(tx, org, actor, body.team_id)
        now = time.time()
        assignments = [dict(value) for value in person.get('assignments', [])]
        if body.team_id != person.get('team_id'):
            assignments = [value for value in assignments if value['until'] is None or value['until'] >= now - 30 * 86400]
            if len(assignments) >= 128:
                raise HTTPException(429, 'Too many team changes in the retention period.')
            if assignments and assignments[-1]['until'] is None:
                assignments[-1]['until'] = now
            assignments.append({'team_id': body.team_id, 'from': now, 'until': None})
        value = {**person, 'name': body.name, 'team_id': body.team_id, 'assignments': assignments}
        save_employee(tx, org, value)
        audit(tx, org, actor['id'], 'employee.updated', person_id)
        return public_member(value)
    return store.atomic(update)


@router.patch('/organizations/{org}/members/{account_id}/teams')
def grant_teams(org: str, account_id: str, body: TeamGrants, user: User, store: Store):
    def update(tx):
        actor = member(tx, org, user, owner=True)
        path = member_path(org, account_id)
        account = tx.get(path)
        if not account or not account['active'] or account['role'] != 'manager':
            raise HTTPException(404, 'Manager account not found.')
        for team_id in body.team_ids:
            require_team(tx, org, actor, team_id)
        account = {**account, 'team_ids': sorted(set(body.team_ids))}
        tx.put(path, account)
        audit(tx, org, actor['id'], 'manager.teams_updated', account_id)
        return public_member(account)
    return store.atomic(update)


@router.delete('/organizations/{org}/employees/{person_id}')
def remove_employee(org: str, person_id: str, user: User, store: Store):
    def remove(tx):
        actor = member(tx, org, user, manage=True)
        person = require_employee(tx, org, actor, person_id, manage=True)
        for device_id in person['device_ids']:
            for provider in ('whoop', 'fitbit'):
                tx.delete('vendor_connections/'+digest(device_id+':'+provider))
            for path in (f'device_keys/{device_id}', f'organizations/{org}/devices/{device_id}'):
                record = tx.get(path)
                if record:
                    tx.put(path, {**record, 'revoked': True})
        save_employee(tx, org, {**set_sharing(person, False), 'active': False, 'device_ids': [], 'enrollment_id': None})
        if person.get('linked_member_id') is None:
            company = tx.get(f'organizations/{org}')
            tx.put(f'organizations/{org}', {**company, 'employee_count': max(0, company.get('employee_count', 0) - 1)})
        audit(tx, org, actor['id'], 'employee.removed', person_id)
        return {'removed': True}
    return store.atomic(remove)


@router.post('/organizations/{org}/employees/{person_id}/enrollments', status_code=201)
def create_enrollment(org: str, person_id: str, body: EnrollmentInput, user: User, store: Store):
    enrollment_id = uuid4().hex
    token = f'nse_{enrollment_id}.{secrets.token_urlsafe(32)}'
    now = time.time()
    def create(tx):
        actor = member(tx, org, user, manage=True)
        person = require_employee(tx, org, actor, person_id, manage=True)
        if person.get('deleting'):
            raise HTTPException(409, 'Measurement deletion is still in progress.')
        quota_path = f'organizations/{org}/limits/enrollments'
        quota = tx.get(quota_path) or {}
        day = int(now // 86400)
        count = quota.get('count', 0) if quota.get('day') == day else 0
        if count >= 200:
            raise HTTPException(429, 'Daily phone-enrollment limit reached.')
        tx.put(quota_path, {'day': day, 'count': count + 1})
        tx.put(f'enrollments/{enrollment_id}', {'id': enrollment_id, 'token_hash': digest(token), 'org': org,
            'employee_id': person_id, 'issued_by': actor['id'], 'expires_at': now + 300,
            'source': body.source, 'claimed': False})
        save_employee(tx, org, {**person, 'enrollment_id': enrollment_id})
        audit(tx, org, actor['id'], 'phone.enrollment_created', person_id)
        return {'token': token, 'expires_at': now + 300, 'employee_id': person_id}
    return store.atomic(create)


def enrollment_context(tx, token, allow_claimed=False):
    enrollment_id = token.split('.')[0][4:]
    grant = tx.get(f'enrollments/{enrollment_id}')
    if not grant or not hmac.compare_digest(grant['token_hash'], digest(token)):
        raise HTTPException(410, 'This connection code is invalid or expired.')
    org = grant['org']
    person = employee(tx, org, grant['employee_id'])
    issuer = tx.get(member_path(org, grant['issued_by']))
    if (not person or not person['active'] or person.get('deleting') or person.get('enrollment_id') != enrollment_id
            or not issuer or not issuer['active'] or not can_manage(issuer, person)):
        raise HTTPException(410, 'This connection code is no longer authorized. Ask for a new code.')
    if grant['expires_at'] <= time.time():
        raise HTTPException(410, 'This connection code has expired. Ask for a new code.')
    if grant['claimed']:
        if not allow_claimed:
            raise HTTPException(409, 'This connection code has already been used.')
    return grant, person


@router.post('/gateway/enrollment/preview')
def preview_enrollment(body: EnrollmentToken, store: Store):
    def preview(tx):
        grant, person = enrollment_context(tx, body.token)
        company = tx.get(f'organizations/{grant["org"]}')
        team = tx.get(f'organizations/{grant["org"]}/teams/{person["team_id"]}') if person.get('team_id') else None
        return {'company': company['name'], 'employee': person['name'], 'team': team['name'] if team else None,
                'source': grant['source'], 'expires_at': grant['expires_at']}
    return store.atomic(preview)


@router.post('/gateway/enrollment/claim')
def claim_enrollment(body: EnrollmentClaim, store: Store):
    device_id = uuid4().hex
    def claim(tx):
        grant, person = enrollment_context(tx, body.token, allow_claimed=True)
        org = grant['org']
        if grant['claimed']:
            if grant['installation_id'] != body.installation_id or not hmac.compare_digest(grant['claim_hash'], digest(body.claim_secret)):
                raise HTTPException(409, 'This connection code has already been used.')
            assigned_id = grant['device_id']
            device = tx.get(f'organizations/{org}/devices/{assigned_id}')
            key = tx.get(f'device_keys/{assigned_id}')
            if not device or device['revoked'] or not key or key['revoked']:
                raise HTTPException(410, 'Phone access has been revoked. Ask for a new code.')
        else:
            if len(person['device_ids']) >= 10:
                raise HTTPException(409, 'Revoke an old phone before connecting another.')
            assigned_id = device_id
            credential = f'nsd_{assigned_id}.{body.claim_secret}'
            device = {'id': assigned_id, 'name': body.phone_name.strip(), 'source': grant['source'], 'member_id': person['id'],
                      'created_at': time.time(), 'last_received_at': None, 'revoked': False, 'sharing': True,
                      'enrollment_id': grant['id'], 'installation_id': body.installation_id}
            tx.put(f'organizations/{org}/devices/{assigned_id}', device)
            tx.put(f'device_keys/{assigned_id}', {'org': org, 'member_id': person['id'], 'token_hash': digest(credential), 'revoked': False})
            save_employee(tx, org, {**set_sharing(person, True), 'device_ids': [*person['device_ids'], assigned_id]})
            # Keep the consumed grant briefly for exact-client recovery after a lost response.
            tx.put(f'enrollments/{grant["id"]}', {**grant, 'claimed': True, 'device_id': assigned_id,
                'installation_id': body.installation_id, 'claim_hash': digest(body.claim_secret), 'expires_at': time.time() + 86400})
            audit(tx, org, person['id'], 'phone.connected', assigned_id)
        company = tx.get(f'organizations/{org}')
        return {'credential': f'nsd_{assigned_id}.{body.claim_secret}', 'gateway_id': assigned_id,
                'organization_id': org, 'employee_id': person['id'], 'company': company['name'], 'employee': person['name']}
    return store.atomic(claim)


@router.get('/gateway/status')
def gateway_status(store: Store, authorization: str | None = Header(None)):
    def read(tx):
        device_id, org, person, device = device_access(tx, authorization, require_sharing=False)
        company = tx.get(f'organizations/{org}')
        return {'gateway_id': device_id, 'company': company['name'], 'employee': person['name'],
                'sharing': person['sharing'] and device.get('sharing', True), 'last_received_at': device['last_received_at'],
                'paused_intervals': person.get('paused_intervals', []),
                'team_boundaries': [assignment['from'] for assignment in person.get('assignments', [])]}
    return store.atomic(read)


@router.patch('/gateway/sharing')
def gateway_sharing(body: SharingInput, store: Store, authorization: str | None = Header(None)):
    def update(tx):
        device_id, org, person, device = device_access(tx, authorization, require_sharing=False)
        if not device.get('enrollment_id'):
            raise HTTPException(403, 'Legacy device credentials cannot change employee sharing.')
        save_employee(tx, org, set_sharing(person, body.enabled))
        tx.put(f'organizations/{org}/devices/{device_id}', {**device, 'sharing': body.enabled})
        audit(tx, org, person['id'], 'sharing.enabled' if body.enabled else 'sharing.paused', device_id)
        return {'sharing': body.enabled}
    return store.atomic(update)


@router.delete('/gateway/connection')
def disconnect_gateway(store: Store, authorization: str | None = Header(None)):
    def disconnect(tx):
        device_id, org, person, device = device_access(tx, authorization, require_sharing=False)
        key = tx.get(f'device_keys/{device_id}')
        tx.put(f'device_keys/{device_id}', {**key, 'revoked': True})
        for provider in ('whoop', 'fitbit'):
            tx.delete('vendor_connections/'+digest(device_id+':'+provider))
        tx.put(f'organizations/{org}/devices/{device_id}', {**device, 'revoked': True, 'sharing': False})
        remaining = [key for key in person['device_ids'] if key != device_id]
        save_employee(tx, org, {**(set_sharing(person, False) if not remaining else person), 'device_ids': remaining})
        audit(tx, org, person['id'], 'phone.disconnected', device_id)
        return {'disconnected': True}
    return store.atomic(disconnect)
