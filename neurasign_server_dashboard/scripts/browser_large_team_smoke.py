"""Exercise 200 measurement-free browser fixtures, not backend or pilot capacity.

The manager fixture mirrors the privacy-enforced operational response contract.
All fixture responses remain in the browser; every company write is rejected.
"""
import asyncio
import copy
import os
from pathlib import Path
import time
from urllib.parse import urlparse

from playwright.async_api import async_playwright, expect

WEB = os.getenv('NEURASIGN_WEB', 'http://localhost:3000')
ROOT = Path(__file__).resolve().parents[1]
TEAMS = [{'id': f'team-{i}', 'name': f'Team {i}'} for i in range(1, 9)]


def fixtures():
    people, members, cases, tasks = [], [], [], []
    now = time.time()
    for index in range(1, 201):
        person_id, team_id, kind = f'fixture-{index:03}', f'team-{(index - 1) % 8 + 1}', (index - 1) % 10
        availability = 'busy' if kind == 0 else 'unknown' if kind == 1 else 'unavailable' if kind == 2 else 'available'
        people.append({'id': person_id, 'name': f'Person {index:03}', 'team_id': team_id,
                       'skills': ['coordination'], 'availability': availability, 'max_active_tasks': 3,
                       'active_task_count': 0, 'open_case_count': int(kind == 0), 'context_note': 'Browser-only operational context.',
                       'context_provenance': 'human_reported', 'context_version': 1, 'can_edit': True,
                       'provenance': 'human_report', 'interpretation': None})
        members.append({'id': person_id, 'name': f'Person {index:03}', 'team_id': team_id, 'role': 'employee', 'email': None,
                        'sharing': kind != 3, 'status': 'paused' if kind == 3 else 'current',
                        'features': {key: None for key in ('heart_rate', 'hrv', 'eda', 'temperature', 'movement')},
                        'latest': None, 'signals': [], 'measurements_access': False, 'can_view_measurements': False,
                        'connection': {'status': 'paused' if kind == 3 else 'current', 'current_count': 0 if kind == 3 else 1,
                                       'issue_count': 0, 'last_received_at': None if kind == 3 else now - 5}})
        if kind == 0:
            cases.append({'id': f'case-{index}', 'employee_id': person_id, 'team_id': team_id, 'category': 'coverage',
                          'summary': f'Coverage check for Person {index:03}', 'priority': 'high', 'status': 'open',
                          'actions': [], 'resolution': None, 'responsible_member_id': 'fixture-manager', 'version': 1,
                          'provenance': 'human_report', 'created_at': now, 'updated_at': now})
    for index, team in enumerate(TEAMS):
        tasks.append({'id': f'task-{index}', 'title': f'Queue review for {team["name"]}', 'description': 'Browser-only work item.',
                      'team_id': team['id'], 'required_skills': ['coordination'], 'priority': 'normal', 'status': 'open',
                      'assignee_id': None, 'responsible_member_id': 'fixture-manager', 'due_at': None,
                      'created_by': 'fixture-manager', 'created_at': now, 'updated_at': now, 'version': 1, 'provenance': 'human_report'})
    return people, members, cases, tasks


async def no_overflow(page):
    assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), 'Document horizontal overflow'


async def main():
    if urlparse(WEB).hostname not in ('localhost', '127.0.0.1'):
        raise RuntimeError('Browser fixtures may only run on the local stack.')
    people, members, cases, tasks = fixtures()
    state = {'people': people, 'members': members, 'requests': 0, 'writes': 0, 'measurement_requests': 0}
    errors = []
    artifacts = ROOT / 'artifacts'
    artifacts.mkdir(exist_ok=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel='chrome', headless=True, args=['--no-sandbox'])
        page = await browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.on('pageerror', lambda error: errors.append(str(error)))

        async def intercept(route):
            path = urlparse(route.request.url).path
            if route.request.method != 'GET':
                state['writes'] += 1
                await route.fulfill(status=403, json={'detail': 'Browser fixtures forbid company writes.'})
            elif path.endswith('/history') or path.endswith('/observations'):
                state['measurement_requests'] += 1
                await route.fulfill(status=403, json={'detail': 'Manager measurements are protected.'})
            elif path.endswith('/dashboard'):
                original = await route.fetch()
                payload = await original.json()
                payload.update(members=copy.deepcopy(state['members']), devices=[], teams=TEAMS, server_time=time.time())
                payload['organization']['is_demo'] = False
                await route.fulfill(response=original, json=payload)
            elif path.endswith('/applications'):
                original = await route.fetch()
                payload = await original.json()
                payload.update(people=copy.deepcopy(state['people']), teams=TEAMS, tasks=tasks, cases=cases, handovers=[],
                               permissions={'can_manage': True, 'can_create_cases': True, 'can_accept_handovers': False},
                               server_time=time.time())
                payload['organization']['is_demo'] = False
                state['requests'] += 1
                await route.fulfill(response=original, json=payload)
            else:
                await route.continue_()

        await page.route('**/api/v1/**', intercept)
        await page.goto(WEB + '/?login=1', wait_until='domcontentloaded')
        await page.get_by_role('button', name='Sign in with test account', exact=True).click()
        await expect(page.get_by_test_id('command-center')).to_be_visible(timeout=20000)
        rows = page.locator('.ops-people-table tbody tr')
        pager = page.get_by_role('navigation', name='Team members pagination')
        search = page.get_by_label('Search team members', exact=True)
        team_filter = page.get_by_label('Filter by team', exact=True)
        status_filter = page.get_by_label('Filter by team status', exact=True)
        await expect(page.get_by_test_id('ops-summary-people')).to_contain_text('200')
        await expect(page.get_by_test_id('ops-summary-support')).to_contain_text('20')
        await expect(page.get_by_test_id('ops-summary-tasks')).to_contain_text('8')
        await expect(rows).to_have_count(25)
        await expect(pager).to_contain_text('1–25 of 200 people')
        await expect(rows.first).to_contain_text('Person 001')
        await page.get_by_test_id('ops-summary-support').click()
        await expect(rows).to_have_count(20)
        await expect(rows.first).to_contain_text('Support requested')
        await status_filter.select_option('available')
        await expect(pager).to_contain_text('1–25 of 140 people')
        await status_filter.select_option('unconfirmed')
        await expect(rows).to_have_count(20)
        await expect(rows.first).to_contain_text('Not confirmed')
        await status_filter.select_option('all')
        await pager.get_by_role('button', name='Next page').click()
        await expect(pager).to_contain_text('26–50 of 200 people')
        await page.get_by_label('Team members rows per page').select_option('50')
        await expect(rows).to_have_count(50)
        await expect(pager).to_contain_text('1–50 of 200 people')
        await search.fill('Person 080')
        await expect(rows).to_have_count(1)
        trigger = rows.get_by_role('button', name='View Person 080', exact=True)
        await trigger.focus()
        await page.keyboard.press('Enter')
        detail = page.get_by_role('dialog', name='Person 080', exact=True)
        await expect(detail).to_be_visible()
        await expect(detail).to_contain_text('Physiological measurements are protected')
        await expect(detail.locator('.data-chart, .co-chart-value, .ops-estimates')).to_have_count(0)
        assert await detail.evaluate('node => node.matches(":modal")'), 'Details must make the background inert'
        for _ in range(10):
            await page.keyboard.press('Tab')
            assert await detail.evaluate('node => node.contains(document.activeElement) || document.activeElement === document.body'), 'Person detail focus escaped into the background workspace'
        await page.keyboard.press('Escape')
        await expect(detail).not_to_be_visible()
        await expect(trigger).to_be_focused()
        await trigger.click()
        state['people'].reverse()
        async with page.expect_response('**/applications', timeout=15000):
            pass
        await expect(detail).to_be_visible()
        state['people'] = [person for person in state['people'] if person['id'] != 'fixture-080']
        state['members'] = [person for person in state['members'] if person['id'] != 'fixture-080']
        async with page.expect_response('**/applications', timeout=15000):
            pass
        await expect(detail).not_to_be_visible()
        await expect(rows).to_have_count(0)
        await expect(page.get_by_role('heading', name='No people match these filters')).to_be_visible()
        state['people'], state['members'], _, _ = fixtures()
        async with page.expect_response('**/applications', timeout=15000):
            pass
        await search.fill('')
        await team_filter.select_option('team-1')
        await expect(rows).to_have_count(25)
        await expect(page.get_by_test_id('ops-summary-people')).to_contain_text('25')
        await team_filter.select_option('')
        await page.get_by_role('group', name='Team display').get_by_role('button', name='Teams', exact=True).click()
        groups = page.locator('.ops-team-cards > button')
        await expect(groups).to_have_count(8)
        await groups.filter(has=page.get_by_role('heading', name='Team 2', exact=True)).click()
        await expect(team_filter).to_have_value('team-2')
        await expect(rows).to_have_count(25)
        await team_filter.select_option('')
        await page.get_by_label('Team members rows per page').select_option('25')
        await no_overflow(page)
        await page.screenshot(path=str(artifacts / 'company-large-roster-desktop.png'), full_page=True, animations='disabled')
        await page.set_viewport_size({'width': 390, 'height': 844})
        await no_overflow(page)
        await search.fill('Person 199')
        await expect(rows).to_have_count(1)
        await rows.get_by_role('button', name='View Person 199', exact=True).click()
        mobile_detail = page.get_by_role('dialog', name='Person 199', exact=True)
        await expect(mobile_detail).to_be_visible()
        assert await mobile_detail.evaluate('node => node.scrollWidth <= node.clientWidth + 1'), 'Mobile detail overflow'
        await page.screenshot(path=str(artifacts / 'company-large-roster-mobile-dialog.png'), animations='disabled')
        await page.keyboard.press('Escape')
        await page.screenshot(path=str(artifacts / 'company-large-roster-mobile.png'), full_page=True, animations='disabled')
        assert state['requests'] >= 4 and state['writes'] == 0 and state['measurement_requests'] == 0, state
        assert not errors, errors
        await browser.close()
    print('PASS: 200 measurement-free browser fixtures, eight teams, operational summaries, search/status/team filters, 25/50 paging, team grouping, protected person details, keyboard focus, polling/removal and mobile layout. No company writes or measurement requests. UI coverage, not backend capacity.')


if __name__ == '__main__':
    asyncio.run(main())
