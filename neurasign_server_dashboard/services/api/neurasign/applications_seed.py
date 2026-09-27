"""Explicit local-only sample organization. Never writes wearable observations."""
import time

from .workspace import digest, new_member
from .applications import insert, path
from fastapi import HTTPException


CASE_SCENARIOS = [
    ('break_request', 'Break requested after a busy period on the customer support queue.'),
    ('coverage', 'Extra coverage needed to review incoming platform changes.'),
    ('workload', 'Check-in requested before the next fulfilment assignment.'),
    ('other', 'Handover follow-up pending for afternoon service coverage.'),
]


def readiness_level(score):
    return 'limited' if score < 40 else 'fair' if score < 70 else 'good'


def migrate_seed(tx, org, existing):
    """Explicit demo-opening migration; preserve all human-modified work."""
    if existing.get('applications_demo_seed_version', 1) >= 2:
        return existing
    now = time.time()
    company = {**existing, 'applications_demo_seed_version': 2}
    if company['name'] == 'Northstar Operations — Sample Company':
        company['name'] = 'Northstar Operations'
    changed_cases = {}
    for index, (category, summary) in enumerate(CASE_SCENARIOS):
        key = digest(f'{org}:case:{index}')[:32]
        value = tx.get(path(org, 'cases', key))
        if (value and value['provenance'] == 'demo' and value['version'] == 1
                and value['summary'] == 'Sample report: extra queue coverage is needed during this shift.'):
            value = {**value, 'category': category, 'summary': summary, 'version': 2, 'updated_at': now}
            tx.put(path(org, 'cases', key), value)
            changed_cases[key] = 2
    for index in range(2):
        key = digest(f'{org}:handover:{index}')[:32]
        value = tx.get(path(org, 'handovers', key))
        if value and value['provenance'] == 'demo' and value['version'] == 1 and value['status'] == 'pending':
            versions = dict(value['item_versions'])
            changed = False
            for case_id, version in changed_cases.items():
                if f'cases:{case_id}' in versions:
                    versions[f'cases:{case_id}'] = version
                    changed = True
            if changed:
                tx.put(path(org, 'handovers', key), {**value, 'item_versions': versions, 'version': 2, 'updated_at': now})
    for index in range(36):
        key = digest(f'{org}:person:{index}')[:32]
        value = tx.get(path(org, 'context', key))
        if value and value.get('provenance') == 'demo' and value.get('version') == 1 and value.get('interpretation'):
            interpretation = dict(value['interpretation'])
            readiness = interpretation['readiness']
            interpretation['readiness'] = {**readiness, 'level': readiness_level(readiness['score'])}
            tx.put(path(org, 'context', key), {**value, 'interpretation': interpretation, 'version': 2})
    tx.put(f'organizations/{org}', company)
    return company


def seed_demo(tx, user):
    org = digest(f'neurasign-operational-demo-v1:{user.uid}')[:32]
    existing = tx.get(f'organizations/{org}')
    if existing:
        return {'organization': migrate_seed(tx, org, existing), 'created': False}
    account_path = f'accounts/{digest(user.uid)}'
    account = tx.get(account_path) or {'organizations': []}
    if len(account['organizations']) >= 20:
        raise HTTPException(409, 'This account has reached its workspace limit.')
    now = time.time()
    company = {'id': org, 'name': 'Northstar Operations', 'is_demo': True, 'applications_demo_seed_version': 2,
               'demo_label': 'Fictional operational scenario. Illustrative states; no wearable readings.',
               'created_at': now, 'retention_days': 30, 'member_count': 1, 'employee_count': 36, 'team_count': 4}
    owner = new_member(user, 'owner')
    tx.put(f'organizations/{org}', company)
    tx.put(f'organizations/{org}/members/{owner["id"]}', owner)
    tx.put(account_path, {**account, 'organizations': [*account['organizations'], org]})
    team_names = ['Customer Support', 'Platform Operations', 'Fulfilment', 'Service Delivery']
    skills = [['customer support', 'triage'], ['systems', 'incident coordination'], ['logistics', 'inventory'], ['scheduling', 'quality review']]
    teams = []
    for index, name in enumerate(team_names):
        team = {'id': digest(f'{org}:team:{index}')[:32], 'name': name, 'active': True, 'created_at': now}
        teams.append(team)
        tx.put(f'organizations/{org}/teams/{team["id"]}', team)
    first_names = ['Avery', 'Morgan', 'Riley', 'Casey', 'Jordan', 'Quinn', 'Cameron', 'Parker', 'Skyler',
                   'Rowan', 'Drew', 'Sage', 'Reese', 'Emerson', 'Finley', 'Blake', 'Charlie', 'Dakota',
                   'Harper', 'Jamie', 'Jules', 'Kendall', 'Lane', 'Marley', 'Noel', 'Payton', 'River',
                   'Robin', 'Shawn', 'Spencer', 'Tatum', 'Taylor', 'Terry', 'Wren', 'Alexis', 'Bailey']
    surnames = ['Chen', 'Patel', 'Brooks', 'Silva', 'Reed', 'Park', 'Morgan', 'Lopez', 'Taylor']
    people = []
    for index, name in enumerate(first_names):
        team_index = index // 9
        person = {'id': digest(f'{org}:person:{index}')[:32], 'name': f'{name} {surnames[index % 9]}',
                  'email': None, 'role': 'employee', 'linked_member_id': None, 'storage_root': 'employees',
                  'team_id': teams[team_index]['id'], 'assignments': [{'team_id': teams[team_index]['id'], 'from': now, 'until': None}],
                  'sharing': False, 'active': True, 'device_ids': [], 'paused_intervals': [], 'joined_at': now}
        people.append(person)
        tx.put(f'organizations/{org}/employees/{person["id"]}', person)
        elevated = index % 9 == 0
        values = {'stress': 74 if elevated else 22 + index % 5 * 7,
                  'workload': 83 if elevated else 28 + index % 6 * 8,
                  'fatigue': 69 if elevated else 18 + index % 4 * 9,
                  'readiness': 34 if elevated else 90 - index % 5 * 6}
        interpretation = {key: {'score': score, 'level': 'low' if score < 40 else 'moderate' if score < 70 else 'elevated'} for key, score in values.items()}
        interpretation['readiness']['level'] = readiness_level(values['readiness'])
        interpretation.update(source='illustrative', updated_at=now)
        context = {'skills': skills[team_index], 'availability': 'busy' if elevated else 'unavailable' if index % 9 == 8 else 'available',
                   'max_active_tasks': 3, 'context_note': 'Fictional shift scenario: requested workload review.' if elevated else 'Fictional shift scenario: operational availability recorded.',
                   'version': 1, 'provenance': 'demo', 'updated_by': owner['id'], 'updated_at': now, 'interpretation': interpretation}
        tx.put(path(org, 'context', person['id']), context)
    task_titles = [('Review the morning support queue', 'Prepare escalation coverage', 'Update the response checklist'),
                   ('Review the service change plan', 'Prepare the on-call handover', 'Check the incident runbook'),
                   ('Review pending dispatches', 'Prepare inventory coverage', 'Check the packing checklist'),
                   ('Confirm afternoon coverage', 'Review the service checklist', 'Prepare the next shift brief')]
    for team_index, team in enumerate(teams):
        ids = []
        for offset, title in enumerate(task_titles[team_index]):
            person = people[team_index * 9 + offset + 1]
            task = {'id': digest(f'{org}:task:{team_index}:{offset}')[:32], 'title': title,
                    'description': 'Sample operational work item for exploring human-confirmed assignment.',
                    'team_id': team['id'], 'required_skills': [skills[team_index][offset % 2]], 'priority': 'high' if offset == 0 else 'normal',
                    'status': 'open' if offset == 0 else 'assigned' if offset == 1 else 'in_progress',
                    'assignee_id': None if offset == 0 else person['id'], 'responsible_member_id': owner['id'],
                    'due_at': now + 8 * 3600, 'created_by': owner['id'], 'created_at': now, 'updated_at': now, 'version': 1, 'provenance': 'demo'}
            insert(tx, org, 'tasks', task)
            ids.append(task['id'])
        person = people[team_index * 9]
        case = {'id': digest(f'{org}:case:{team_index}')[:32], 'employee_id': person['id'], 'team_id': team['id'],
                'category': CASE_SCENARIOS[team_index][0], 'summary': CASE_SCENARIOS[team_index][1],
                'priority': 'high', 'status': 'open', 'actions': [], 'resolution': None, 'responsible_member_id': owner['id'],
                'version': 1, 'provenance': 'demo', 'created_at': now, 'updated_at': now}
        insert(tx, org, 'cases', case)
        if team_index < 2:
            handover = {'id': digest(f'{org}:handover:{team_index}')[:32], 'title': f'{team["name"]} shift handover', 'team_id': team['id'],
                        'sender_member_id': owner['id'], 'recipient_member_id': owner['id'], 'task_ids': [ids[2]], 'case_ids': [case['id']],
                        'note': 'Review the pending work, then accept to complete this sample handover.',
                        'status': 'pending', 'accepted_at': None, 'version': 1, 'created_at': now, 'updated_at': now, 'provenance': 'demo',
                        'item_versions': {f'tasks:{ids[2]}': 1, f'cases:{case["id"]}': 1}}
            insert(tx, org, 'handovers', handover)
    return {'organization': company, 'created': True}
