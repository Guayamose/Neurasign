"""Employee identity and team authorization, independent of dashboard accounts.

Old account-backed employees are read through a compatibility projection. The
first edit promotes their profile into employees, retaining its storage root so
existing readings/credentials never need a destructive migration.
"""
import re
import time

from fastapi import HTTPException


def identifier(value):
    if not re.fullmatch(r'[a-f0-9]{32,64}', value):
        raise HTTPException(404, 'Not found.')
    return value


def employee_path(org, employee_id):
    return f'organizations/{identifier(org)}/employees/{identifier(employee_id)}'


def employee(store, org, employee_id):
    value = store.get(employee_path(org, employee_id))
    if value:
        return value
    legacy = store.get(f'organizations/{org}/members/{employee_id}')
    if legacy and 'sharing' in legacy:
        return {**legacy, 'linked_member_id': legacy['id'], 'storage_root': 'members',
                'team_id': None, 'assignments': [], 'paused_intervals': []}
    return None


def employee_data_path(org, person):
    root = 'members' if person.get('storage_root') == 'members' else 'employees'
    return f'organizations/{identifier(org)}/{root}/{identifier(person["id"])}'


def save_employee(tx, org, person):
    tx.put(employee_path(org, person['id']), person)


def own_employee(store, org, actor):
    return employee(store, org, actor['id'])


def self_employee(actor):
    return {'id': actor['id'], 'name': actor['name'], 'email': actor['email'], 'role': actor['role'],
            'linked_member_id': actor['id'], 'storage_root': 'members', 'team_id': None, 'assignments': [],
            'paused_intervals': [], 'sharing': False, 'active': True, 'device_ids': [], 'joined_at': time.time()}


def employees(store, org):
    current = {value['id']: value for value in store.list(f'organizations/{org}/employees', limit=200, filters={'active': True})}
    for legacy in store.list(f'organizations/{org}/members', limit=100, filters={'active': True}):
        if legacy['id'] not in current and 'sharing' in legacy:
            projected = employee(store, org, legacy['id'])
            if projected and projected['active']:
                current[legacy['id']] = projected
    return [value for value in current.values() if value['active']]


def is_self(actor, person):
    return person.get('linked_member_id') == actor['id']


def can_manage(actor, person):
    return actor['role'] == 'owner' or (actor['role'] == 'manager' and person.get('team_id') in actor.get('team_ids', []))


def can_view(actor, person):
    return can_manage(actor, person) or is_self(actor, person)


def require_employee(store, org, actor, person_id, manage=False):
    if actor['role'] == 'employee' and (manage or person_id != actor['id']):
        raise HTTPException(403, 'You can only access your own employee profile.')
    person = employee(store, org, person_id)
    if not person or not person['active']:
        raise HTTPException(404, 'Employee not found.')
    if not (can_manage(actor, person) if manage else can_view(actor, person)):
        raise HTTPException(403, 'This employee is outside your assigned teams.')
    return person


def team_at(person, timestamp):
    for assignment in reversed(person.get('assignments', [])):
        if assignment['from'] <= timestamp and (assignment['until'] is None or timestamp < assignment['until']):
            return assignment['team_id']
    return None


def can_view_capture(actor, person, row):
    """Team scope for capture metadata, independently of measurement permission."""
    if actor['role'] == 'owner' or is_self(actor, person):
        return True
    measured_team = row.get('team_id') if 'team_id' in row else team_at(person, row['timestamp'])
    return can_manage(actor, person) and measured_team in actor.get('team_ids', [])


def can_view_measurements(actor, person):
    return is_self(actor, person) or (actor.get('can_view_measurements') is True and can_manage(actor, person))


def require_measurements(actor, person):
    if not can_view_measurements(actor, person):
        raise HTTPException(403, 'Measurement access requires a separate capability; a management role does not grant it.')


def can_view_measurement(actor, person, row):
    return can_view_measurements(actor, person) and can_view_capture(actor, person, row)


def set_sharing(person, enabled, now=None):
    now = time.time() if now is None else now
    if person.get('deleting') and enabled:
        raise HTTPException(409, 'Measurement deletion is still in progress. Retry deletion if it was interrupted.')
    periods = [dict(period) for period in person.get('paused_intervals', [])
               if period['until'] is None or period['until'] >= now - 7 * 86400]
    if person['sharing'] and not enabled:
        if len(periods) >= 256:
            # Coalesce the oldest pause periods conservatively; never lose a pause.
            periods = [{'from': periods[0]['from'], 'until': periods[1]['until']}, *periods[2:]]
        periods.append({'from': now, 'until': None})
    if enabled and periods and periods[-1]['until'] is None:
        periods[-1]['until'] = now
    return {**person, 'sharing': enabled, 'paused_intervals': periods}


def capture_allowed(person, timestamp, interval_seconds=0):
    start = timestamp - (interval_seconds or 0)
    for period in person.get('paused_intervals', []):
        if timestamp >= period['from'] and (period['until'] is None or start < period['until']):
            raise HTTPException(422, 'The measurement overlaps a paused sharing period.')


def require_team(store, org, actor, team_id):
    identifier(team_id)
    team = store.get(f'organizations/{org}/teams/{team_id}')
    if not team or not team['active']:
        raise HTTPException(404, 'Team not found.')
    if actor['role'] != 'owner' and team_id not in actor.get('team_ids', []):
        raise HTTPException(403, 'This team is outside your assigned teams.')
    return team
