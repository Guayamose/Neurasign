"""Local-emulator acceptance for private company views and three real workflows.

Creates a new isolated company and disposable test accounts on every run. All
workflow writes go through the real public API; the browser error-recovery check
injects one explicit failed request. No provider, cloud or physical wearable is
used. Completion is automated acceptance, not a real-human usability study or a
backend capacity benchmark. Only aggregate results/screenshots go to artifacts.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
from urllib.parse import urlparse

from playwright.async_api import async_playwright, expect
from workspace_smoke import AUTH, PROJECT, WEB, call, test_user

ROOT = Path(__file__).resolve().parents[1]
PHYSIOLOGICAL_KEYS = {
    'heart_rate', 'hrv', 'eda', 'temperature', 'movement', 'bvp', 'ppg',
    'oxygen_saturation', 'respiratory_rate', 'skin_temperature', 'skin_conductance',
    'rr_interval', 'ibi', 'rmssd', 'sdnn', 'hr_average', 'hr_lowest',
}
ACCEPTANCE_TASKS = [
    'Set up a blank company, add missing work context and assign its first task.',
    'Find a scoped employee and distinguish missing data from an assessment.',
    'Create work, review matching reasons, explicitly assign and complete it.',
    'Record a human-reported concern, add support and confirm its resolution.',
    'Send pending work to a named colleague and have that colleague accept.',
    'Recover from empty filters and a failed save using keyboard and mobile.',
    'Find and select people with a larger real local roster and scoped access.',
]


def request_id():
    return 'applications-smoke-'+secrets.token_hex(12)


def no_measurements(value, path='payload'):
    """Allow compatibility null fields, never nonempty measurement payloads."""
    if isinstance(value, dict):
        for key, item in value.items():
            location = f'{path}.{key}'
            if key == 'metric_catalog':
                continue  # Public metric definitions contain no employee readings.
            if key in PHYSIOLOGICAL_KEYS:
                assert item is None, f'Physiological value exposed at {location}'
            if key in ('features', 'latest', 'signals', 'history', 'readings', 'observations'):
                if isinstance(item, dict):
                    assert all(v is None for v in item.values()), f'Measurements exposed at {location}'
                else:
                    assert item is None or item == [], f'Measurements exposed at {location}'
            no_measurements(item, location)
    elif isinstance(value, list):
        for i, item in enumerate(value):
            no_measurements(item, f'{path}[{i}]')


def local_only():
    for url in (WEB, AUTH):
        assert urlparse(url).hostname in ('localhost', '127.0.0.1', '::1'), 'Local hosts only'
    config = call('GET', '/config')
    assert config['firebase']['projectId'] == PROJECT == 'demo-neurasign'
    assert config['emulator_url'] == AUTH, 'Refusing non-emulator authentication'


def seed_fixture(roster_size):
    local_only()
    assert 4 <= roster_size <= 100, 'Stay within the documented local pilot profile limit'
    actors = {name: test_user(display) for name, display in (
        ('owner', 'AcceptanceOwner'), ('manager', 'AcceptanceManager'),
        ('recipient', 'AcceptanceRecipient'), ('outsider', 'AcceptanceOutsider'),
        ('employee', 'AcceptanceEmployee'))}
    owner = actors['owner']['token']
    org = call('POST', '/organizations', owner, {'name': 'Applications acceptance '+secrets.token_hex(4)}, 201)['id']
    base = f'/organizations/{org}'
    other_org = call('POST', '/organizations', actors['outsider']['token'], {'name': 'Unrelated acceptance tenant'}, 201)['id']
    teams = [call('POST', base+'/teams', owner, {'name': name}, 201) for name in ('Operations', 'Restricted team')]
    for role in ('manager', 'recipient', 'employee'):
        body = {'email': actors[role]['email'], 'role': 'employee' if role == 'employee' else 'manager'}
        if role != 'employee':
            body['team_ids'] = [teams[0]['id']]
        invite = call('POST', base+'/invitations', owner, body, 201)['token']
        call('POST', '/invitations/accept', actors[role]['token'], {'token': invite})
    people = []
    for i in range(roster_size):
        name = ('Avery Lane', 'Restricted Person', 'Jordan Park')[i] if i < 3 else f'Person {i+1:03}'
        people.append(call('POST', base+'/employees', owner, {'name': name, 'team_id': teams[i % 2]['id']}, 201))
    apps = base+'/applications'
    context = {'skills': ['inspection', 'first aid'], 'availability': 'available',
               'max_active_tasks': 3, 'context_note': 'Confirmed at the local test shift briefing.'}
    for index, availability in ((0, 'available'), (1, 'available'), (2, 'unavailable')):
        call('PATCH', apps+f'/people/{people[index]["id"]}/context', owner,
             {**context, 'availability': availability, 'version': 0})
    # One genuine local stored measurement proves redaction against nonempty data.
    token = call('POST', base+f'/employees/{people[0]["id"]}/enrollments', owner, {'source': 'recording'}, 201)['token']
    gateway = call('POST', '/gateway/enrollment/claim', body={
        'token': token, 'installation_id': secrets.token_hex(16), 'claim_secret': secrets.token_urlsafe(32),
        'phone_name': 'Applications acceptance recording', 'consent': True})
    source = call('POST', '/gateway/sources', gateway['credential'], {
        'client_source_id': 'acceptance-heart-rate', 'name': 'Explicit test recording',
        'adapter': {'id': 'test-recording', 'version': '1.0.0'}, 'transport': 'recording',
        'capabilities': [{'metric': 'heart_rate', 'unit': 'bpm', 'delivery_mode': 'stream',
                          'measurement_kind': 'sample', 'method': 'recorded-fixture', 'timestamp_basis': 'source_record'}]}, 201)['source']
    result = call('POST', '/observations', gateway['credential'], {'schema_version': 2, 'observations': [{
        'id': request_id(), 'source_id': source['id'], 'metric': 'heart_rate', 'value': 73.25,
        'unit': 'bpm', 'measured_at': datetime.now(timezone.utc).isoformat()}]})
    assert result['accepted'] == 1
    return {'actors': actors, 'org': org, 'other_org': other_org, 'base': base, 'apps': apps,
            'teams': teams, 'people': people, 'gateway': gateway['credential'],
            'recipient_id': hashlib.sha256(actors['recipient']['uid'].encode()).hexdigest()}


def snapshot(fixture, actor='manager'):
    result = call('GET', fixture['apps'], fixture['actors'][actor]['token'])
    no_measurements(result)
    return result


def privacy_and_permissions(fixture):
    actors, base, apps = fixture['actors'], fixture['base'], fixture['apps']
    person = fixture['people'][0]['id']
    call('GET', apps, expected=401)
    for actor in ('outsider', 'employee'):
        call('GET', apps, actors[actor]['token'], expected=403)
    call('GET', f'/organizations/{fixture["other_org"]}/applications', actors['manager']['token'], expected=403)
    for actor in ('owner', 'manager'):
        dashboard = call('GET', base+'/dashboard', actors[actor]['token'])
        no_measurements(dashboard)
        member = next(p for p in dashboard['members'] if p['id'] == person)
        assert member.get('latest') is None and not member.get('signals')
        call('GET', base+f'/members/{person}/history', actors[actor]['token'], expected=403)
        call('GET', base+f'/members/{person}/observations?series_id='+('0'*64), actors[actor]['token'], expected=403)
    state = snapshot(fixture)
    allowed = {p['id'] for p in fixture['people'] if p['team_id'] == fixture['teams'][0]['id']}
    assert {p['id'] for p in state['people']} == allowed, 'Manager received employees outside granted team'
    assert all(p.get('interpretation') is None for p in state['people']), 'Real people received invented interpretations'
    assert state['permissions']['can_manage']
    hidden = fixture['people'][1]['id']
    call('PATCH', apps+f'/people/{hidden}/context', actors['manager']['token'], {
        'version': 1, 'skills': [], 'availability': 'available', 'max_active_tasks': 3}, 403)
    return {'real_recording_uploaded': True, 'owner_and_manager_measurements_redacted': True,
            'raw_history_and_observations_denied': True, 'team_and_tenant_scope_enforced': True,
            'legacy_employee_application_access_denied': True, 'visible_manager_people': len(allowed)}


def api_lifecycles(fixture):
    token = fixture['actors']['manager']['token']
    apps, team = fixture['apps'], fixture['teams'][0]['id']
    person = fixture['people'][0]['id']
    task_body = {'request_id': request_id(), 'title': 'API inspection round', 'team_id': team,
                 'required_skills': ['inspection'], 'priority': 'normal', 'description': 'Isolated local acceptance task.'}
    task = call('POST', apps+'/tasks', token, task_body)
    assert call('POST', apps+'/tasks', token, task_body)['id'] == task['id'], 'Create retry duplicated a task'
    candidates = call('GET', apps+f'/tasks/{task["id"]}/candidates', token)
    no_measurements(candidates)
    best = next(p for p in candidates['candidates'] if p['employee_id'] == person)
    assert best['eligible'] and best['reasons'], 'Recommendation lacks eligibility or reasons'
    assert not any(p['employee_id'] == fixture['people'][1]['id'] for p in candidates['candidates'])
    assert not next(p for p in candidates['candidates'] if p['employee_id'] == fixture['people'][2]['id'])['eligible']
    call('POST', apps+f'/tasks/{task["id"]}/assign', token,
         {'request_id': request_id(), 'version': task['version']+100, 'employee_id': person}, 409)
    task = call('POST', apps+f'/tasks/{task["id"]}/assign', token,
                {'request_id': request_id(), 'version': task['version'], 'employee_id': person})
    assert task['status'] == 'assigned' and task['assignee_id'] == person
    for action, status in (('start', 'in_progress'), ('complete', 'completed')):
        task = call('POST', apps+f'/tasks/{task["id"]}/transition', token,
                    {'request_id': request_id(), 'version': task['version'], 'action': action, 'note': 'Local acceptance '+action})
        assert task['status'] == status
    call('POST', apps+f'/tasks/{task["id"]}/assign', token,
         {'request_id': request_id(), 'version': task['version'], 'employee_id': person}, 409)
    case = call('POST', apps+'/cases', token, {'request_id': request_id(), 'employee_id': person,
                'category': 'coverage', 'summary': 'API support for overlapping reception work', 'priority': 'normal'})
    case = call('POST', apps+f'/cases/{case["id"]}/actions', token,
                {'request_id': request_id(), 'version': case['version'], 'kind': 'coverage', 'note': 'A colleague agreed to cover reception.'})
    assert case['actions'] and case['actions'][-1]['kind'] == 'coverage'
    case = call('POST', apps+f'/cases/{case["id"]}/resolve', token,
                {'request_id': request_id(), 'version': case['version'], 'note': 'Coverage confirmed with the employee.'})
    assert case['status'] == 'resolved'
    pending = call('POST', apps+'/tasks', token, {**task_body, 'request_id': request_id(), 'title': 'API work for the next shift'})
    handover = call('POST', apps+'/handovers', token, {
        'request_id': request_id(), 'title': 'API next shift handover', 'team_id': team,
        'recipient_member_id': fixture['recipient_id'], 'task_ids': [pending['id']], 'case_ids': [],
        'note': 'Please review the pending inspection.'})
    accept_body = {'request_id': request_id(), 'version': handover['version']}
    call('POST', apps+f'/handovers/{handover["id"]}/accept', fixture['actors']['owner']['token'], accept_body, 403)
    handover = call('POST', apps+f'/handovers/{handover["id"]}/accept', fixture['actors']['recipient']['token'], accept_body)
    assert handover['status'] == 'accepted'
    state = snapshot(fixture)
    transferred = next(t for t in state['tasks'] if t['id'] == pending['id'])
    assert transferred['responsible_member_id'] == fixture['recipient_id']
    assert transferred['status'] == 'open' and transferred['assignee_id'] is None
    assert next(t for t in state['tasks'] if t['id'] == task['id'])['status'] == 'completed'
    assert next(c for c in state['cases'] if c['id'] == case['id'])['status'] == 'resolved'
    return {'task_create_recommend_assign_start_complete': True, 'support_case_action_resolution': True,
            'recipient_only_handover_and_responsibility_transfer': True,
            'idempotent_task_creation': True, 'stale_version_rejected': True}


async def sign_in(page, actor, *, expect_workspace=True):
    await page.goto(WEB, wait_until='domcontentloaded')
    await page.get_by_label('Work email').fill(actor['email'])
    await page.get_by_label('Password', exact=True).fill(actor['password'])
    await page.get_by_role('button', name='Sign in', exact=True).click()
    if expect_workspace:
        await expect(page.get_by_test_id('company-workspace')).to_be_visible(timeout=20000)


async def open_application(page, app):
    await page.get_by_test_id('company-tab-applications').click()
    hub = page.get_by_test_id('apps-hub')
    module = page.get_by_test_id('apps-module-'+app)
    await expect(page.locator('[data-testid="apps-hub"], [data-testid^="apps-module-"]')).to_be_visible(timeout=15000)
    if await hub.is_visible():
        await page.get_by_test_id('apps-open-'+app).click()
    elif not await module.is_visible():
        name = {'tasks': r'^Tasks\b', 'prevention': r'^Support cases\b', 'handover': r'^Handovers\b'}[app]
        await page.get_by_role('navigation', name='Applications', exact=True).get_by_role('button', name=re.compile(name)).click()
    await expect(module).to_be_visible()
    return module


async def no_overflow(page):
    assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), 'Page overflows horizontally'
    for dialog in await page.get_by_role('dialog').all():
        if await dialog.is_visible():
            assert await dialog.evaluate('el => el.scrollWidth <= el.clientWidth + 1'), 'Dialog overflows horizontally'


async def transient_refresh_acceptance(page, dialog, fixture):
    """Exercise both refresh branches without submitting the unsaved form."""
    mutations = []

    def observe_request(request):
        if (urlparse(request.url).path.startswith('/api/v1'+fixture['apps'])
                and request.method not in ('GET', 'HEAD', 'OPTIONS')):
            mutations.append(request.method)

    page.on('request', observe_request)
    try:
        for suffix in ('/dashboard', '/applications'):
            failed = 0

            async def fail_one_refresh(route):
                nonlocal failed
                if route.request.method == 'GET' and not failed:
                    failed += 1
                    await route.fulfill(status=503, content_type='application/json',
                                        body=json.dumps({'detail': 'Controlled temporary refresh failure.'}))
                else:
                    await route.continue_()

            url = WEB+'/api/v1'+fixture['base']+suffix
            await page.route(url, fail_one_refresh)
            try:
                # The native modal makes background controls inert. Check its
                # visible banner by CSS and let the normal poll recover, without
                # closing the form merely to click the background retry button.
                banner = page.locator('.co-message').filter(has_text='Updates interrupted.')
                await expect(banner).to_be_visible(timeout=15000)
                await expect(banner).to_contain_text('Showing the last received information.')
                await expect(banner.locator('button')).to_have_text('Retry now')
                await expect(dialog).to_be_visible()
                await expect(dialog.get_by_label('What needs to be done?', exact=True)).to_have_value('Browser safety inspection')
                await expect(dialog.get_by_label('Team')).to_have_value(fixture['teams'][0]['id'])
                await expect(dialog.get_by_label(re.compile(r'^Required skills'))).to_have_value('inspection')
                assert failed == 1, 'Exactly one refresh response should fail per endpoint'
            finally:
                await page.unroute(url, fail_one_refresh)
            await expect(banner).to_have_count(0, timeout=15000)
            await expect(page.locator('.co-refresh-status')).to_contain_text('Workspace up to date')
            await expect(dialog.get_by_label('What needs to be done?', exact=True)).to_have_value('Browser safety inspection')
        assert not mutations, 'Unsaved form issued a write during refresh failure/recovery'
    finally:
        page.remove_listener('request', observe_request)
    print('Dashboard and applications refresh failures preserved unsaved input and recovered.', flush=True)


async def first_time_acceptance(browser, local_route, inspect_response, errors):
    """No company, team, employee or operational context is pre-seeded."""
    owner = test_user('FirstUseOwner')
    context = await browser.new_context(viewport={'width': 1440, 'height': 1000})
    await context.route('**/*', local_route)
    page = await context.new_page()
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('response', inspect_response)
    await sign_in(page, owner, expect_workspace=False)
    await expect(page.get_by_role('heading', name='Set up your workspace', exact=True)).to_be_visible()
    await page.get_by_label('Company name', exact=True).fill('First use acceptance '+secrets.token_hex(4))
    await page.get_by_role('button', name='Create workspace', exact=True).click()
    await expect(page.get_by_test_id('company-workspace')).to_be_visible(timeout=15000)
    await page.get_by_role('button', name='Set up your team', exact=True).click()
    await page.get_by_label('New team', exact=True).fill('First operations')
    await page.get_by_role('button', name='Create team', exact=True).click()
    await expect(page.get_by_label('Employee name', exact=True)).to_be_enabled()
    await page.get_by_label('Employee name', exact=True).fill('Taylor Morgan')
    await page.get_by_label('Employee team', exact=True).select_option(label='First operations')
    await page.get_by_role('button', name='Add employee', exact=True).click()
    await expect(page.get_by_role('list', name='Employees', exact=True)).to_contain_text('Taylor Morgan')
    org = call('GET', '/me', owner['token'])['organizations'][0]['id']
    base = f'/organizations/{org}'
    state = call('GET', base+'/applications', owner['token'])
    person = next(p for p in state['people'] if p['name'] == 'Taylor Morgan')
    assert person['context_version'] == 0 and person['availability'] == 'unknown' and not person['skills']
    assert person['max_active_tasks'] is None, 'First-use context was silently invented'
    tasks = await open_application(page, 'tasks')
    await tasks.get_by_test_id('apps-create').click()
    form = page.get_by_role('dialog', name='Create a task', exact=True)
    await form.get_by_label('What needs to be done?', exact=True).fill('First reception inspection')
    await form.get_by_label(re.compile(r'^Required skills')).fill('inspection')
    await form.get_by_role('button', name='Create task', exact=True).click()
    detail = page.get_by_test_id('apps-task-detail')
    await expect(detail).to_contain_text('No eligible candidates yet.')
    await expect(detail.get_by_test_id('apps-confirm-assignment')).to_be_disabled()
    await detail.get_by_role('button', name='Review unavailable people', exact=True).click()
    await expect(detail.get_by_role('radio', name=re.compile('Taylor Morgan'))).to_be_disabled()
    await detail.get_by_test_id('apps-person-context-'+person['id']).click()
    editor = page.get_by_role('dialog', name='Operational context · Taylor Morgan', exact=True)
    await expect(editor).to_be_visible()
    await editor.get_by_label(re.compile(r'^Skills and qualifications')).fill('inspection')
    await editor.get_by_label('Availability').select_option('available')
    await editor.get_by_label('Agreed active task limit', exact=True).fill('3')
    await editor.get_by_role('button', name='Save context', exact=True).click()
    await expect(editor).not_to_be_visible()
    await expect(detail).to_be_visible()
    candidate = detail.get_by_role('radio', name=re.compile('Taylor Morgan'))
    await expect(candidate).to_be_enabled(timeout=15000)
    await candidate.check()
    await detail.get_by_test_id('apps-confirm-assignment').click()
    await expect(detail.locator('.apps-detail-meta')).to_contain_text('Assigned')
    saved = call('GET', base+'/applications', owner['token'])
    task = next(t for t in saved['tasks'] if t['title'] == 'First reception inspection')
    assert task['status'] == 'assigned' and task['assignee_id'] == person['id']
    await page.keyboard.press('Escape')

    # Follow the overview entry point instead of filling a blank case form.
    await page.get_by_test_id('company-tab-overview').click()
    await page.get_by_test_id('ops-person-'+person['id']).get_by_role('button', name='View Taylor Morgan', exact=True).click()
    person_dialog = page.get_by_role('dialog', name='Taylor Morgan', exact=True)
    await person_dialog.get_by_role('button', name='Open support case', exact=True).click()
    support = page.get_by_role('dialog', name='Open a support case', exact=True)
    await expect(support.get_by_label('Employee')).to_have_value(person['id'])
    await expect(support.get_by_label('Team')).to_have_value(person['team_id'])
    await support.get_by_label(re.compile(r'^What needs attention\?')).fill('First use requested support')
    await support.get_by_role('button', name='Open support case', exact=True).click()
    await expect(page.get_by_test_id('apps-case-detail')).to_contain_text('First use requested support')
    case = next(c for c in call('GET', base+'/applications', owner['token'])['cases']
                if c['summary'] == 'First use requested support')
    assert case['employee_id'] == person['id']
    await context.close()

    # Revoke a real separate manager while their saved task dialog is open.
    # This is a server permission change, not a mocked browser failure.
    manager = test_user('RevokedAcceptanceManager')
    invitation = call('POST', base+'/invitations', owner['token'], {
        'email': manager['email'], 'role': 'manager', 'team_ids': [person['team_id']]}, 201)
    call('POST', '/invitations/accept', manager['token'], {'token': invitation['token']})
    context = await browser.new_context(viewport={'width': 1280, 'height': 900})
    await context.route('**/*', local_route)
    revoked = await context.new_page()
    revoked.on('pageerror', lambda error: errors.append(str(error)))
    revoked.on('response', inspect_response)
    await sign_in(revoked, manager)
    await open_application(revoked, 'tasks')
    await revoked.get_by_test_id('apps-row-'+task['id']).click()
    await expect(revoked.get_by_test_id('apps-task-detail')).to_be_visible()
    member_id = hashlib.sha256(manager['uid'].encode()).hexdigest()
    call('DELETE', base+'/members/'+member_id, owner['token'])
    call('GET', base+'/applications', manager['token'], expected=403)
    await expect(revoked.get_by_test_id('apps-task-detail')).not_to_be_visible(timeout=15000)
    await expect(revoked.locator('body')).not_to_contain_text('First reception inspection')
    await expect(revoked.locator('body')).not_to_contain_text('Taylor Morgan')
    await context.close()
    print('Blank-company setup, context recovery, person support and permission-loss clearing passed.', flush=True)
    return {'blank_company_team_employee_and_first_assignment': True,
            'missing_context_blocks_then_editor_returns_to_assignment': True,
            'overview_support_case_preselects_person_and_team': True,
            'real_permission_revocation_clears_open_record_on_poll': True}


async def browser_acceptance(fixture):
    artifacts = ROOT/'artifacts'
    artifacts.mkdir(exist_ok=True)
    errors, external, exposed, received = [], [], [], []
    apps = fixture['apps']
    initial = snapshot(fixture)
    assert not initial['tasks'] and not initial['cases'] and not initial['handovers'], 'Fixture must begin without activity'

    async def local_route(route):
        url = route.request.url
        parsed = urlparse(url)
        if parsed.scheme in ('http', 'https') and parsed.hostname not in ('localhost', '127.0.0.1', '::1'):
            external.append(parsed.hostname)
            await route.abort()
        else:
            await route.continue_()

    async def inspect_response(response):
        parsed = urlparse(response.url)
        if response.status == 200 and parsed.path.endswith(('/applications', '/dashboard')):
            try:
                payload = await response.json()
                no_measurements(payload)
                received.append(parsed.path)
            except Exception as error:
                exposed.append(str(error))

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel='chrome', headless=True, args=['--no-sandbox'])
        context = await browser.new_context(viewport={'width': 1440, 'height': 1000})
        await context.route('**/*', local_route)
        page = await context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('response', inspect_response)
        await sign_in(page, fixture['actors']['manager'])
        await expect(page.locator('html')).to_have_attribute('lang', 'en')
        await expect(page.locator('body')).not_to_contain_text('73.25')
        tasks = await open_application(page, 'tasks')
        await expect(tasks.get_by_role('heading', name='Give the next task a clear owner.')).to_be_visible()
        trigger = tasks.get_by_test_id('apps-create')
        await trigger.focus()
        await page.keyboard.press('Enter')
        dialog = page.get_by_role('dialog', name='Create a task', exact=True)
        await expect(dialog).to_be_visible()
        for _ in range(8):
            await page.keyboard.press('Tab')
            # Chrome may focus browser chrome between native dialog cycles; no
            # background application control may receive focus while it is modal.
            assert await dialog.evaluate('el => el.contains(document.activeElement) || (document.activeElement === document.body && el.matches(":modal"))'), 'Focus escaped to background application controls'
        await page.keyboard.press('Escape')
        await expect(dialog).not_to_be_visible()
        await expect(trigger).to_be_focused()

        await trigger.click()
        await dialog.get_by_label('What needs to be done?', exact=True).fill('Browser safety inspection')
        await dialog.get_by_label('Team').select_option(fixture['teams'][0]['id'])
        await dialog.get_by_label(re.compile(r'^Required skills')).fill('inspection')
        await transient_refresh_acceptance(page, dialog, fixture)
        failure_count = 0

        async def fail_once(route):
            nonlocal failure_count
            if route.request.method == 'POST' and failure_count == 0:
                failure_count += 1
                await route.fulfill(status=503, content_type='application/json', body=json.dumps({'detail': 'Temporary local test failure. Try again.'}))
            else:
                await route.continue_()

        failure_url = WEB+'/api/v1'+apps+'/tasks'
        await page.route(failure_url, fail_once)
        await dialog.get_by_role('button', name='Create task', exact=True).click()
        await expect(dialog.get_by_role('alert')).to_contain_text('Temporary local test failure')
        await expect(dialog.get_by_label('What needs to be done?', exact=True)).to_have_value('Browser safety inspection')
        await page.unroute(failure_url, fail_once)
        await dialog.get_by_role('button', name='Create task', exact=True).click()
        detail = page.get_by_test_id('apps-task-detail')
        await expect(detail).to_be_visible()
        await expect(detail).to_contain_text('Based on recorded skills, availability and current commitments.')
        chosen = detail.get_by_role('radio', name=re.compile('Avery Lane'))
        await expect(chosen).to_be_enabled()
        await detail.get_by_role('button', name=re.compile(r'^Review unavailable \(')).click()
        await detail.get_by_label('Find a candidate', exact=True).fill('Jordan Park')
        await expect(detail.get_by_role('radio', name=re.compile('Jordan Park'))).to_be_disabled()
        await detail.get_by_label('Find a candidate', exact=True).fill('')
        await detail.get_by_role('button', name='Hide unavailable', exact=True).click()
        await chosen.check()
        await detail.get_by_test_id('apps-confirm-assignment').click()
        await expect(detail.locator('.apps-detail-meta')).to_contain_text('Assigned')
        await detail.get_by_role('button', name='Start task', exact=True).click()
        await expect(detail.locator('.apps-detail-meta')).to_contain_text('In progress')
        await detail.get_by_role('button', name='Complete task', exact=True).click()
        await expect(detail).to_contain_text('Work completed')
        state = snapshot(fixture)
        completed = [t for t in state['tasks'] if t['title'] == 'Browser safety inspection']
        assert len(completed) == 1 and completed[0]['status'] == 'completed'
        assert completed[0]['assignee_id'] == fixture['people'][0]['id']
        print('Browser task lifecycle and failed-save recovery passed.', flush=True)
        await page.keyboard.press('Escape')

        support = await open_application(page, 'prevention')
        await expect(support.get_by_role('heading', name='A clear place to follow through.')).to_be_visible()
        await support.get_by_test_id('apps-create').click()
        case_form = page.get_by_role('dialog', name='Open a support case', exact=True)
        await case_form.get_by_label('Team').select_option(fixture['teams'][0]['id'])
        await case_form.get_by_label('Employee').select_option(fixture['people'][0]['id'])
        await case_form.get_by_label('Type of concern').select_option('coverage')
        await case_form.get_by_label(re.compile(r'^What needs attention\?')).fill('Browser request for reception coverage')
        await case_form.get_by_role('button', name='Open support case', exact=True).click()
        case = page.get_by_test_id('apps-case-detail')
        await expect(case).to_be_visible()
        await expect(case.get_by_role('button', name='Resolve case', exact=True)).to_be_disabled()
        await case.get_by_label('Action taken').select_option('coverage')
        await case.get_by_label('What was agreed?', exact=True).fill('A colleague confirmed coverage for the next hour.')
        await case.get_by_role('button', name='Record action', exact=True).click()
        await expect(case.locator('.apps-action-history')).to_contain_text('A colleague confirmed coverage')
        await case.get_by_role('button', name='Resolve case', exact=True).click()
        await case.get_by_label('Resolution', exact=True).fill('Coverage received and confirmed with the employee.')
        await case.get_by_role('button', name='Confirm resolution', exact=True).click()
        await expect(case).to_contain_text('Case resolved')
        assert next(c for c in snapshot(fixture)['cases'] if c['summary'] == 'Browser request for reception coverage')['status'] == 'resolved'
        print('Browser support case, action and resolution passed.', flush=True)
        await page.keyboard.press('Escape')

        pending = call('POST', apps+'/tasks', fixture['actors']['manager']['token'], {
            'request_id': request_id(), 'title': 'Browser pending follow-up', 'team_id': fixture['teams'][0]['id'],
            'required_skills': [], 'priority': 'normal'})
        handovers = await open_application(page, 'handover')
        await expect(handovers.get_by_role('heading', name='Make the next shift a smooth one.')).to_be_visible()
        await handovers.get_by_test_id('apps-create').click()
        form = page.get_by_role('dialog', name='Prepare a handover', exact=True)
        await form.get_by_label('Handover title', exact=True).fill('Browser evening handover')
        await form.get_by_label('Team').select_option(fixture['teams'][0]['id'])
        await form.get_by_label('Who is taking over?').select_option(fixture['recipient_id'])
        await expect(form.get_by_role('checkbox', name=re.compile('Browser pending follow-up'))).to_be_visible(timeout=15000)
        await form.get_by_role('checkbox', name=re.compile('Browser pending follow-up')).check()
        await form.get_by_role('button', name='Send handover', exact=True).click()
        handover = page.get_by_test_id('apps-handover-detail')
        await expect(handover).to_contain_text('Only the designated recipient can accept.')
        await expect(handover.get_by_role('button', name='Accept handover', exact=True)).to_have_count(0)
        saved_handover = next(h for h in snapshot(fixture)['handovers'] if h['title'] == 'Browser evening handover')

        recipient_context = await browser.new_context(viewport={'width': 1280, 'height': 900})
        await recipient_context.route('**/*', local_route)
        recipient = await recipient_context.new_page()
        recipient.on('pageerror', lambda error: errors.append(str(error)))
        recipient.on('response', inspect_response)
        await sign_in(recipient, fixture['actors']['recipient'])
        await open_application(recipient, 'handover')
        await recipient.get_by_test_id('apps-row-'+saved_handover['id']).click()
        await recipient.get_by_test_id('apps-handover-detail').get_by_role('button', name='Accept handover', exact=True).click()
        await expect(recipient.get_by_test_id('apps-handover-detail')).to_contain_text('Accepted by AcceptanceRecipient')
        persisted = next(t for t in snapshot(fixture)['tasks'] if t['id'] == pending['id'])
        assert persisted['responsible_member_id'] == fixture['recipient_id'] and persisted['status'] == 'open'
        await recipient_context.close()
        await expect(handover).to_contain_text('Accepted by AcceptanceRecipient', timeout=15000)
        print('Browser two-session handover and persisted responsibility passed.', flush=True)
        await page.keyboard.press('Escape')

        tasks = await open_application(page, 'tasks')
        await tasks.get_by_label('Search', exact=True).fill('no-such-activity-acceptance')
        await expect(tasks.get_by_role('heading', name='No matching activity', exact=True)).to_be_visible()
        await tasks.get_by_role('button', name='Clear filters', exact=True).click()
        await expect(tasks.get_by_test_id('apps-row-'+completed[0]['id'])).to_be_visible()
        # Real saved records exercise list pagination, not a synthetic response fixture.
        for i in range(17):
            call('POST', apps+'/tasks', fixture['actors']['manager']['token'], {
                'request_id': request_id(), 'title': f'Roster acceptance task {i+1:02}',
                'team_id': fixture['teams'][0]['id'], 'required_skills': [], 'priority': 'low'})
        await expect(tasks.get_by_role('navigation', name='Activity pages')).to_be_visible(timeout=15000)
        await expect(tasks.locator('.apps-record-row')).to_have_count(15)
        await tasks.get_by_role('navigation', name='Activity pages').get_by_role('button', name='Next', exact=True).click()
        await expect(tasks.get_by_role('navigation', name='Activity pages').get_by_role('button', name='Previous', exact=True)).to_be_enabled()
        await tasks.get_by_label('Search', exact=True).fill('Roster acceptance task 17')
        await expect(tasks.locator('.apps-record-row')).to_have_count(1)
        await expect(tasks.get_by_role('navigation', name='Activity pages')).to_have_count(0)
        await tasks.get_by_label('Search', exact=True).fill('')
        await tasks.get_by_role('button', name='Team context', exact=True).click()
        visible_people = [p for p in fixture['people'] if p['team_id'] == fixture['teams'][0]['id']]
        last = visible_people[-1]
        await tasks.get_by_label('Search', exact=True).fill(last['name'])
        edit = tasks.get_by_test_id('apps-person-context-'+last['id'])
        await expect(edit).to_be_visible()
        await expect(tasks.locator('.apps-context-list > div')).to_have_count(1)
        await edit.focus()
        await page.keyboard.press('Enter')
        context_dialog = page.get_by_role('dialog', name='Operational context · '+last['name'], exact=True)
        await expect(context_dialog).to_be_visible()
        await page.keyboard.press('Escape')
        await expect(context_dialog).not_to_be_visible()
        await expect(edit).to_be_focused()
        await tasks.get_by_label('Search', exact=True).fill('')
        await tasks.get_by_role('button', name='Team context', exact=True).click()
        for width in (1440, 768, 390, 320):
            await page.set_viewport_size({'width': width, 'height': 900})
            await no_overflow(page)
        await page.set_viewport_size({'width': 390, 'height': 844})
        await tasks.get_by_test_id('apps-create').click()
        await expect(page.get_by_role('dialog', name='Create a task', exact=True)).to_be_visible()
        await no_overflow(page)
        await page.keyboard.press('Escape')
        await page.screenshot(path=str(artifacts/'applications-mobile.png'), full_page=True, animations='disabled')
        await page.set_viewport_size({'width': 1440, 'height': 1000})
        await page.screenshot(path=str(artifacts/'applications-desktop.png'), full_page=True, animations='disabled')
        first_use = await first_time_acceptance(browser, local_route, inspect_response, errors)
        assert failure_count == 1
        assert not errors, errors
        assert not external, f'Unexpected external browser hosts: {external}'
        assert not exposed, exposed
        assert any(path.endswith('/dashboard') for path in received) and any(path.endswith('/applications') for path in received)
        await browser.close()
    return {**first_use, 'task_lifecycle': True, 'support_lifecycle': True, 'two_session_handover': True,
            'empty_filter_and_pagination': True, 'keyboard_modal_focus_and_escape': True,
            'failed_save_preserves_input_and_retry_persists_once': True,
            'dashboard_and_applications_refresh_failures_preserve_unsaved_form_and_recover': True,
            'mobile_widths_checked': [1440, 768, 390, 320], 'real_scoped_people_search': len(visible_people),
            'manager_browser_payloads_redacted': True, 'browser_errors': 0, 'external_browser_requests': 0}


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-only', action='store_true')
    parser.add_argument('--roster-size', type=int, default=80)
    args = parser.parse_args()
    fixture = seed_fixture(args.roster_size)
    privacy = privacy_and_permissions(fixture)
    browser_result = None
    if not args.api_only:
        browser_result = await browser_acceptance(fixture)
    api_result = api_lifecycles(fixture)
    output = {'status': 'passed', 'scope': 'Isolated local Auth/Firestore emulators; no external provider calls.',
              'task_based_acceptance': ACCEPTANCE_TASKS, 'real_employee_profiles_created': len(fixture['people']),
              'privacy': privacy, 'api_workflows': api_result, 'browser': browser_result,
              'limits': ['Automated acceptance is not a human usability study.',
                         'A larger fixture is not a backend capacity benchmark.',
                         'No physical wearable, live health interpretation or cloud deployment was tested.']}
    artifacts = ROOT/'artifacts'
    artifacts.mkdir(exist_ok=True)
    (artifacts/'applications-acceptance.json').write_text(json.dumps(output, indent=2)+'\n')
    print(json.dumps(output, indent=2), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
