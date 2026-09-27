"""Scoped operational applications. No measurement or research model inputs.

All transitions, eligibility checks and request receipts share one transaction.
The bounded manifest makes current work counts consistent across competing assigns.
"""
from datetime import datetime
import json
import time
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import Field, field_validator

from .company_access import employees, require_employee, require_team, can_manage
from .identity import local_test_account
from .workspace import Strict, User, Store, member, member_path, digest, audit, checked_id

router = APIRouter(prefix='/api/v1', tags=['Operational applications'])
BASE = '/organizations/{org}/applications'
Priority = Literal['low', 'normal', 'high', 'urgent']
OPEN_TASKS = ('open', 'assigned', 'in_progress')


def path(org, kind, key):
    return f'organizations/{checked_id(org)}/application_{kind}/{checked_id(key)}'


def manifest(tx, org):
    return tx.get(f'organizations/{org}/application_state/current') or {'tasks': [], 'cases': [], 'handovers': []}


def records(tx, org, kind):
    return [value for key in manifest(tx, org)[kind] if (value := tx.get(path(org, kind, key)))]


def insert(tx, org, kind, value):
    index = manifest(tx, org)
    if len(index[kind]) >= {'tasks': 300, 'cases': 300, 'handovers': 150}[kind]:
        raise HTTPException(409, 'This workspace has reached its application record limit.')
    tx.put(path(org, kind, value['id']), value)
    tx.put(f'organizations/{org}/application_state/current', {**index, kind: [*index[kind], value['id']]})


def versioned(value, version):
    if value['version'] != version:
        raise HTTPException(409, 'This record changed. Refresh and review the current version.')


def scoped(tx, org, actor, kind, key):
    value = tx.get(path(org, kind, key))
    if not value:
        raise HTTPException(404, 'Application record not found.')
    require_team(tx, org, actor, value['team_id'])
    return value


def mutate(store, org, user, body, operation, action):
    """Request IDs are scoped to actor and operation, and cannot change payload."""
    payload_hash = digest(json.dumps(body.model_dump(mode='json'), sort_keys=True))
    def change(tx):
        actor = member(tx, org, user, manage=True)
        request_path = path(org, 'requests', digest(f'{actor["id"]}:{operation}:{body.request_id}'))
        existing = tx.get(request_path)
        if existing:
            if existing['payload_hash'] != payload_hash:
                raise HTTPException(409, 'This request ID was already used with a different payload.')
            # Recheck current team authorization before returning a receipt.
            result = existing['result']
            if result.get('team_id'):
                require_team(tx, org, actor, result['team_id'])
            return result
        result = action(tx, actor)
        tx.put(request_path, {'payload_hash': payload_hash, 'result': result, 'expires_at': time.time() + 90 * 86400})
        audit(tx, org, actor['id'], f'application.{operation}', result.get('id'))
        return result
    return store.atomic(change)


class Request(Strict):
    request_id: str = Field(min_length=8, max_length=128, pattern=r'^[A-Za-z0-9_-]+$')


class VersionRequest(Request):
    version: int = Field(ge=1)


class Skills(Strict):
    skills: list[str] = Field(default_factory=list, max_length=30)

    @field_validator('skills')
    @classmethod
    def clean_skills(cls, value):
        cleaned = sorted(set(item.strip().lower() for item in value))
        if any(not item or len(item) > 60 for item in cleaned):
            raise ValueError('Skills must contain 1–60 characters.')
        return cleaned


class ContextInput(Skills):
    version: int = Field(ge=0)
    availability: Literal['available', 'busy', 'unavailable', 'unknown']
    max_active_tasks: int = Field(ge=1, le=20)
    context_note: str = Field('', max_length=500)


class TaskInput(Request):
    title: str = Field(min_length=2, max_length=120)
    description: str = Field('', max_length=1000)
    team_id: str = Field(pattern=r'^[a-f0-9]{32,64}$')
    required_skills: list[str] = Field(default_factory=list, max_length=30)
    priority: Priority = 'normal'
    due_at: datetime | None = None

    @field_validator('required_skills')
    @classmethod
    def clean_skills(cls, value):
        return Skills(skills=value).skills

    @field_validator('title')
    @classmethod
    def clean_title(cls, value):
        if len(value.strip()) < 2:
            raise ValueError('Use at least two characters.')
        return value.strip()

    @field_validator('due_at')
    @classmethod
    def aware_due(cls, value):
        if value and not value.tzinfo:
            raise ValueError('Use a due date with a timezone.')
        return value


class AssignmentInput(VersionRequest):
    employee_id: str = Field(pattern=r'^[a-f0-9]{32,64}$')


class TransitionInput(VersionRequest):
    action: Literal['start', 'complete', 'cancel']
    note: str = Field('', max_length=500)


class CaseInput(Request):
    employee_id: str = Field(pattern=r'^[a-f0-9]{32,64}$')
    category: Literal['workload', 'break_request', 'coverage', 'other']
    summary: str = Field(min_length=2, max_length=500)
    priority: Priority = 'normal'

    @field_validator('summary')
    @classmethod
    def clean_summary(cls, value):
        if len(value.strip()) < 2:
            raise ValueError('Describe the reported support need.')
        return value.strip()


class CaseActionInput(VersionRequest):
    kind: Literal['check_in', 'break', 'coverage', 'adjust_work', 'note']
    note: str = Field(min_length=2, max_length=500)

    @field_validator('note')
    @classmethod
    def clean_note(cls, value):
        if len(value.strip()) < 2:
            raise ValueError('Record a concrete action or resolution.')
        return value.strip()


class ResolveInput(VersionRequest):
    note: str = Field(min_length=2, max_length=500)

    @field_validator('note')
    @classmethod
    def clean_note(cls, value):
        return CaseActionInput.clean_note(value)


class HandoverInput(Request):
    title: str = Field(min_length=2, max_length=120)
    team_id: str = Field(pattern=r'^[a-f0-9]{32,64}$')
    recipient_member_id: str = Field(pattern=r'^[a-f0-9]{32,64}$')
    task_ids: list[str] = Field(default_factory=list, max_length=30)
    case_ids: list[str] = Field(default_factory=list, max_length=30)
    note: str = Field('', max_length=1000)

    @field_validator('title')
    @classmethod
    def clean_title(cls, value):
        return TaskInput.clean_title(value)

    @field_validator('task_ids', 'case_ids')
    @classmethod
    def clean_ids(cls, value):
        if len(set(value)) != len(value):
            raise ValueError('Do not repeat a work item.')
        return [checked_id(item) for item in value]


def counts(tasks, cases, employee_id):
    return (sum(task['assignee_id'] == employee_id and task['status'] in ('assigned', 'in_progress') for task in tasks),
            sum(case['employee_id'] == employee_id and case['status'] != 'resolved' for case in cases))


def person_context(tx, org, person, tasks, cases, is_demo=False):
    context = tx.get(path(org, 'context', person['id'])) or {}
    active, opened = counts(tasks, cases, person['id'])
    availability = context.get('availability', 'unknown')
    at_capacity = context.get('max_active_tasks') is not None and active >= context['max_active_tasks']
    status = ('support_needed' if opened else 'unavailable' if availability == 'unavailable'
              else 'available' if availability == 'available' and not at_capacity else 'check_in')
    return {'id': person['id'], 'name': person['name'], 'team_id': person.get('team_id'),
            'skills': context.get('skills', []), 'availability': availability,
            'max_active_tasks': context.get('max_active_tasks'), 'active_task_count': active, 'open_case_count': opened,
            'context_note': context.get('context_note', ''), 'context_provenance': context.get('provenance', 'missing'),
            'context_version': context.get('version', 0), 'can_edit': True, 'status': status,
            'provenance': 'demo' if context.get('provenance') == 'demo' else 'human_report' if context else 'none',
            'interpretation': context.get('interpretation') if is_demo else None}


def candidate(tx, org, person, task, tasks, cases):
    context = person_context(tx, org, person, tasks, cases)
    reasons, missing = [], []
    if context['context_version'] == 0:
        missing.append('Operational context has not been recorded.')
    if context['availability'] == 'unknown':
        missing.append('Availability is unknown.')
    elif context['availability'] != 'available':
        reasons.append('Reported availability is not available.')
    absent = sorted(set(task['required_skills']) - set(context['skills']))
    if absent:
        missing.append('Required skills not recorded: ' + ', '.join(absent) + '.')
    cap = context['max_active_tasks']
    if cap is None:
        missing.append('An active-task limit has not been recorded.')
    elif context['active_task_count'] >= cap:
        reasons.append('The recorded active-task limit has been reached.')
    if context['open_case_count']:
        reasons.append('An open support case needs review before adding work.')
    eligible = not reasons and not missing and task['status'] == 'open'
    if task['status'] != 'open':
        reasons.append('This task is no longer open for assignment.')
    return {'employee_id': person['id'], 'name': person['name'], 'eligible': eligible,
            'score': max(0, 100 - context['active_task_count'] * 15) if eligible else None,
            'reasons': reasons or (['Required skills are recorded, availability is available, and capacity remains.'] if eligible else []),
            'missing': missing, 'active_task_count': context['active_task_count'], 'open_case_count': context['open_case_count']}


def handover_public(value, actor):
    return {key: item for key, item in value.items() if key != 'item_versions'} | {
        'can_accept': value['status'] == 'pending' and value['recipient_member_id'] == actor['id'],
        'can_cancel': value['status'] == 'pending' and (value['sender_member_id'] == actor['id'] or actor['role'] == 'owner')}


@router.get(BASE)
def application_snapshot(org: str, user: User, store: Store):
    actor = member(store, org, user, manage=True)
    organization = store.get(f'organizations/{org}')
    teams = [team for team in store.list(f'organizations/{org}/teams', limit=50, filters={'active': True})
             if actor['role'] == 'owner' or team['id'] in actor.get('team_ids', [])]
    team_ids = {team['id'] for team in teams}
    tasks, cases, handovers = (records(store, org, kind) for kind in ('tasks', 'cases', 'handovers'))
    tasks, cases, handovers = ([value for value in values if value['team_id'] in team_ids] for values in (tasks, cases, handovers))
    people = [person_context(store, org, person, tasks, cases, organization.get('is_demo', False))
              for person in employees(store, org) if can_manage(actor, person)]
    recipients = [{'id': account['id'], 'name': account['name'], 'role': account['role'],
                   'team_ids': sorted(team_ids) if account['role'] == 'owner' else [key for key in account.get('team_ids', []) if key in team_ids]}
                  for account in store.list(f'organizations/{org}/members', limit=100, filters={'active': True})
                  if account['role'] in ('owner', 'manager') and (account['role'] == 'owner' or team_ids.intersection(account.get('team_ids', [])))]
    return {'organization': {key: organization.get(key, False if key == 'is_demo' else None) for key in ('id', 'name', 'is_demo', 'demo_label')},
            'permissions': {'can_manage': True, 'can_create_cases': True, 'can_accept_handovers': any(item['recipient_member_id'] == actor['id'] and item['status'] == 'pending' for item in handovers)},
            'people': people, 'teams': [{'id': team['id'], 'name': team['name']} for team in teams], 'recipients': recipients,
            'tasks': sorted(tasks, key=lambda item: item['updated_at'], reverse=True),
            'cases': sorted(cases, key=lambda item: item['updated_at'], reverse=True),
            'handovers': [handover_public(item, actor) for item in sorted(handovers, key=lambda item: item['updated_at'], reverse=True)],
            'server_time': time.time()}


@router.patch(BASE + '/people/{person_id}/context')
def update_context(org: str, person_id: str, body: ContextInput, user: User, store: Store):
    def change(tx):
        actor = member(tx, org, user, manage=True)
        person = require_employee(tx, org, actor, person_id, manage=True)
        previous = tx.get(path(org, 'context', person_id)) or {'version': 0}
        versioned(previous, body.version)
        value = {**body.model_dump(), 'version': body.version + 1, 'provenance': 'human_reported', 'updated_by': actor['id'], 'updated_at': time.time()}
        # Manual operational edits do not claim to update illustrative state indices.
        is_demo = bool(tx.get(f'organizations/{org}').get('is_demo'))
        if is_demo and previous.get('interpretation'):
            value['interpretation'] = previous['interpretation']
        tx.put(path(org, 'context', person_id), value)
        audit(tx, org, actor['id'], 'application.context.updated', person_id)
        return person_context(tx, org, person, records(tx, org, 'tasks'), records(tx, org, 'cases'), is_demo)
    return store.atomic(change)


@router.post(BASE + '/tasks')
def create_task(org: str, body: TaskInput, user: User, store: Store):
    def create(tx, actor):
        require_team(tx, org, actor, body.team_id)
        now = time.time()
        value = {key: item for key, item in body.model_dump(exclude={'request_id', 'due_at'}).items()}
        value.update(id=uuid4().hex, status='open', assignee_id=None, responsible_member_id=actor['id'], due_at=body.due_at.timestamp() if body.due_at else None,
                     created_by=actor['id'], created_at=now, updated_at=now, version=1, provenance='human_report')
        insert(tx, org, 'tasks', value)
        return value
    return mutate(store, org, user, body, 'task.create', create)


@router.get(BASE + '/tasks/{task_id}/candidates')
def task_candidates(org: str, task_id: str, user: User, store: Store):
    actor = member(store, org, user, manage=True)
    task = scoped(store, org, actor, 'tasks', task_id)
    tasks, cases = records(store, org, 'tasks'), records(store, org, 'cases')
    candidates = [candidate(store, org, person, task, tasks, cases) for person in employees(store, org) if person.get('team_id') == task['team_id']]
    return {'task_id': task_id, 'version': task['version'], 'candidates': sorted(candidates, key=lambda item: (not item['eligible'], -(item['score'] or 0), item['name']))}


@router.post(BASE + '/tasks/{task_id}/assign')
def assign_task(org: str, task_id: str, body: AssignmentInput, user: User, store: Store):
    def assign(tx, actor):
        task = scoped(tx, org, actor, 'tasks', task_id)
        versioned(task, body.version)
        person = require_employee(tx, org, actor, body.employee_id, manage=True)
        if person.get('team_id') != task['team_id']:
            raise HTTPException(409, 'The employee must belong to the task team.')
        choice = candidate(tx, org, person, task, records(tx, org, 'tasks'), records(tx, org, 'cases'))
        if not choice['eligible']:
            raise HTTPException(409, 'Assignment is not eligible: ' + ' '.join(choice['reasons'] + choice['missing']))
        value = {**task, 'assignee_id': person['id'], 'status': 'assigned', 'version': task['version'] + 1, 'updated_at': time.time()}
        tx.put(path(org, 'tasks', task_id), value)
        return value
    return mutate(store, org, user, body, f'task.assign.{task_id}', assign)


@router.post(BASE + '/tasks/{task_id}/transition')
def transition_task(org: str, task_id: str, body: TransitionInput, user: User, store: Store):
    def transition(tx, actor):
        task = scoped(tx, org, actor, 'tasks', task_id)
        versioned(task, body.version)
        allowed = {'start': ('assigned',), 'complete': ('assigned', 'in_progress'), 'cancel': OPEN_TASKS}
        if task['status'] not in allowed[body.action]:
            raise HTTPException(409, 'This task cannot perform that transition from its current state.')
        value = {**task, 'status': {'start': 'in_progress', 'complete': 'completed', 'cancel': 'canceled'}[body.action],
                 'version': task['version'] + 1, 'updated_at': time.time(), 'last_note': body.note}
        tx.put(path(org, 'tasks', task_id), value)
        return value
    return mutate(store, org, user, body, f'task.transition.{task_id}', transition)


@router.post(BASE + '/cases')
def create_case(org: str, body: CaseInput, user: User, store: Store):
    def create(tx, actor):
        person = require_employee(tx, org, actor, body.employee_id, manage=True)
        if not person.get('team_id'):
            raise HTTPException(409, 'Assign the employee to a team before opening a support case.')
        require_team(tx, org, actor, person['team_id'])
        now = time.time()
        value = {**body.model_dump(exclude={'request_id'}), 'id': uuid4().hex, 'team_id': person['team_id'], 'status': 'open', 'actions': [],
                 'resolution': None, 'responsible_member_id': actor['id'], 'version': 1, 'provenance': 'human_report', 'created_at': now, 'updated_at': now}
        insert(tx, org, 'cases', value)
        return value
    return mutate(store, org, user, body, 'case.create', create)


@router.post(BASE + '/cases/{case_id}/actions')
def case_action(org: str, case_id: str, body: CaseActionInput, user: User, store: Store):
    def change(tx, actor):
        case = scoped(tx, org, actor, 'cases', case_id)
        versioned(case, body.version)
        if case['status'] == 'resolved':
            raise HTTPException(409, 'This support case is already resolved.')
        if len(case['actions']) >= 50:
            raise HTTPException(409, 'This case has reached its action limit.')
        action = {'id': uuid4().hex, 'kind': body.kind, 'note': body.note, 'actor_id': actor['id'], 'created_at': time.time()}
        value = {**case, 'status': 'in_progress', 'actions': [*case['actions'], action], 'updated_at': time.time(), 'version': case['version'] + 1}
        tx.put(path(org, 'cases', case_id), value)
        return value
    return mutate(store, org, user, body, f'case.action.{case_id}', change)


@router.post(BASE + '/cases/{case_id}/resolve')
def resolve_case(org: str, case_id: str, body: ResolveInput, user: User, store: Store):
    def change(tx, actor):
        case = scoped(tx, org, actor, 'cases', case_id)
        versioned(case, body.version)
        if case['status'] == 'resolved' or not case['actions']:
            raise HTTPException(409, 'Record a support action before resolving an open case.')
        value = {**case, 'status': 'resolved', 'resolution': body.note, 'updated_at': time.time(), 'version': case['version'] + 1}
        tx.put(path(org, 'cases', case_id), value)
        return value
    return mutate(store, org, user, body, f'case.resolve.{case_id}', change)


def recipient(tx, org, team_id, recipient_id):
    account = tx.get(member_path(org, recipient_id))
    if not account or not account['active'] or account['role'] not in ('owner', 'manager'):
        raise HTTPException(409, 'The recipient must be an active manager or owner account.')
    require_team(tx, org, account, team_id)
    return account


@router.post(BASE + '/handovers')
def create_handover(org: str, body: HandoverInput, user: User, store: Store):
    def create(tx, actor):
        require_team(tx, org, actor, body.team_id)
        recipient(tx, org, body.team_id, body.recipient_member_id)
        if not body.task_ids and not body.case_ids:
            raise HTTPException(422, 'Select at least one pending task or support case.')
        item_versions = {}
        pending = records(tx, org, 'handovers')
        for kind, keys in (('tasks', body.task_ids), ('cases', body.case_ids)):
            for key in keys:
                item = scoped(tx, org, actor, kind, key)
                if item['team_id'] != body.team_id or item['status'] not in (OPEN_TASKS if kind == 'tasks' else ('open', 'in_progress')):
                    raise HTTPException(409, 'All work must be pending and belong to the selected team.')
                if any(value['status'] == 'pending' and key in value['task_ids' if kind == 'tasks' else 'case_ids'] for value in pending):
                    raise HTTPException(409, 'A selected work item already has a pending handover.')
                item_versions[f'{kind}:{key}'] = item['version']
        now = time.time()
        value = {**body.model_dump(exclude={'request_id'}), 'id': uuid4().hex, 'sender_member_id': actor['id'], 'status': 'pending',
                 'accepted_at': None, 'created_at': now, 'updated_at': now, 'version': 1, 'provenance': 'human_report', 'item_versions': item_versions}
        insert(tx, org, 'handovers', value)
        return handover_public(value, actor)
    return mutate(store, org, user, body, 'handover.create', create)


@router.post(BASE + '/handovers/{handover_id}/{action}')
def transition_handover(org: str, handover_id: str, action: Literal['accept', 'cancel'], body: VersionRequest, user: User, store: Store):
    def change(tx, actor):
        handover = scoped(tx, org, actor, 'handovers', handover_id)
        versioned(handover, body.version)
        if handover['status'] != 'pending':
            raise HTTPException(409, 'Only a pending handover can be changed.')
        if action == 'accept':
            if actor['id'] != handover['recipient_member_id']:
                raise HTTPException(403, 'Only the designated recipient can accept this handover.')
            recipient(tx, org, handover['team_id'], actor['id'])
            changes = []
            for kind, keys in (('tasks', handover['task_ids']), ('cases', handover['case_ids'])):
                for key in keys:
                    item = scoped(tx, org, actor, kind, key)
                    if item['status'] not in (OPEN_TASKS if kind == 'tasks' else ('open', 'in_progress')):
                        raise HTTPException(409, 'Included work is no longer pending. Cancel and prepare a new handover.')
                    versioned(item, handover['item_versions'][f'{kind}:{key}'])
                    changes.append((kind, key, {**item, 'responsible_member_id': actor['id'], 'version': item['version'] + 1, 'updated_at': time.time()}))
            for kind, key, item in changes:
                tx.put(path(org, kind, key), item)
        elif actor['id'] != handover['sender_member_id'] and actor['role'] != 'owner':
            raise HTTPException(403, 'Only the sender or owner can cancel this handover.')
        value = {**handover, 'status': 'accepted' if action == 'accept' else 'canceled', 'accepted_at': time.time() if action == 'accept' else None,
                 'updated_at': time.time(), 'version': handover['version'] + 1}
        tx.put(path(org, 'handovers', handover_id), value)
        return handover_public(value, actor)
    return mutate(store, org, user, body, f'handover.{action}.{handover_id}', change)


@router.post('/applications/demo')
def create_application_demo(user: User, store: Store):
    credentials = local_test_account()
    if not credentials or user.email != credentials['email'] or user.uid != 'neurasign-local-test-user':
        raise HTTPException(403, 'This sample company is available only to the authenticated local emulator test account.')
    from .applications_seed import seed_demo
    return store.atomic(lambda tx: seed_demo(tx, user))
