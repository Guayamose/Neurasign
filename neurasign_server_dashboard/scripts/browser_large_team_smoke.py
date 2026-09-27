"""Exercise 200 browser-only records, not backend throughput or pilot capacity.

Company fixtures are intercepted in the local browser and never uploaded.
"""
import asyncio
import copy
import os
from pathlib import Path
import re
import time
from urllib.parse import urlparse

from playwright.async_api import async_playwright, expect

WEB = os.getenv('NEURASIGN_WEB', 'http://localhost:3000')
ROOT = Path(__file__).resolve().parents[1]
TEAMS = [{'id': f'team-{i}', 'name': f'Team {i}'} for i in range(1, 9)]
METRICS = [{'id': metric, 'name': name, 'unit': unit, 'digits': 1, 'meaning': meaning, 'freshness_seconds': 60}
           for metric, name, unit, meaning in [('heart_rate', 'Heart rate', 'bpm', 'Heartbeats per minute.'),
           ('eda', 'Skin conductance', 'µS', 'Skin conductance at the sensor.'),
           ('skin_temperature', 'Skin temperature', '°C', 'Temperature at the sensor.')]]


def signal(index, now, status='current', metric='heart_rate'):
    summary = status == 'summary'
    latest = None if status in ('waiting', 'unsupported', 'permission_required') else {
        'id': f'fixture-observation-{index}-{metric}', 'value': 72 if metric == 'heart_rate' else 1.2,
        'timestamp': now - (86400 if status == 'delayed' else 3600 if summary else 10),
        'received_at': now - 5, 'method': 'fixture', 'interval_seconds': 86400 if summary else 10}
    return {'series_id': f'fixture-series-{index}-{metric}', 'metric': metric,
            'source_id': f'fixture-source-{index}', 'source_name': 'Browser fixture wearable',
            'source': 'wearable', 'unit': 'bpm' if metric == 'heart_rate' else 'µS',
            'measurement_kind': 'summary' if summary else 'window', 'delivery_mode': 'sync' if summary else 'stream',
            'interval_seconds': 86400 if summary else 10, 'method': 'fixture', 'status': status, 'latest': latest}


def fixture_people(now):
    people, devices = [], []
    for index in range(1, 201):
        kind, person_id = (index - 1) % 10, f'fixture-{index:03}'
        reading = {'id': f'fixture-reading-{index}', 'timestamp': now - 10, 'received_at': now - 5,
                   'window_seconds': 10, 'source': 'recording' if kind == 8 else 'wearable', 'quality': None,
                   'features': {'heart_rate': 72, 'hrv': 44, 'eda': 1.2, 'temperature': 32.4, 'movement': None}}
        statuses = ['current', 'stale', 'waiting', 'paused', 'stale', 'current', 'current', 'waiting', 'current', 'current']
        person = {'id': person_id, 'name': f'Person {index:03}', 'email': '', 'role': 'employee',
                  'team_id': f'team-{(index - 1) % 8 + 1}', 'sharing': kind != 3, 'status': statuses[kind],
                  'latest': reading if kind in (3, 8, 9) else None,
                  'features': reading['features'] if kind in (3, 8, 9) else {key: None for key in reading['features']}, 'signals': []}
        if kind in (0, 3):
            person['signals'] = [signal(index, now)]  # Paused payload intentionally retains stale readings.
        elif kind == 1:
            person['signals'] = [signal(index, now, 'delayed')]
        elif kind == 4:
            person['signals'] = [signal(index, now, 'summary')]
        elif kind == 5:
            person['signals'] = [signal(index, now), signal(index, now, 'permission_required', 'eda'), signal(index, now, 'permission_required', 'skin_temperature')]
        elif kind == 6:
            person['signals'] = [signal(index, now), signal(index, now, 'delayed', 'eda')]
        elif kind == 7:
            person['signals'] = [signal(index, now, 'unsupported')]
        people.append(person)
        if kind != 2:
            devices.append({'id': f'fixture-device-{index}', 'name': f'Phone {index:03}', 'member_id': person_id,
                            'source': 'recording' if kind == 8 else 'wearable', 'revoked': False, 'last_received_at': now - 5})
    return people, devices


async def no_overflow(page):
    assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), 'Document horizontal overflow'


async def poll(page):
    async with page.expect_response('**/dashboard', timeout=10000):
        pass


async def main():
    if urlparse(WEB).hostname not in ('localhost', '127.0.0.1'):
        raise RuntimeError('Browser fixtures may only run on the local stack.')
    people, devices = fixture_people(time.time())
    state = {'people': people, 'devices': devices, 'requests': 0, 'writes': 0}
    errors = []
    artifacts = ROOT / 'artifacts'
    artifacts.mkdir(exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='chrome', headless=True, args=['--no-sandbox'])
        page = await browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.on('pageerror', lambda error: errors.append(str(error)))

        async def intercept(route):
            path = urlparse(route.request.url).path
            if route.request.method != 'GET':
                state['writes'] += 1
                await route.fulfill(status=403, json={'detail': 'Browser fixture forbids company writes.'})
                return
            if path.endswith('/dashboard'):
                original = await route.fetch()
                payload, members, now = await original.json(), copy.deepcopy(state['people']), time.time()
                for person in members:
                    if person['latest'] and person['status'] == 'current':
                        person['latest'].update(timestamp=now - 10, received_at=now - 5)
                    for item in person['signals']:
                        if item['status'] == 'current' and item['latest']:
                            item['latest'].update(timestamp=now - 10, received_at=now - 5)
                payload.update(members=members, devices=copy.deepcopy(state['devices']), teams=TEAMS, metric_catalog=METRICS, server_time=now)
                state['requests'] += 1
                await route.fulfill(response=original, json=payload)
            elif '/members/fixture-' in path and path.endswith('/history'):
                person_id = path.split('/members/')[1].split('/')[0]
                person = next(item for item in state['people'] if item['id'] == person_id)
                latest = person['latest']
                rows = [{**latest, 'id': f'fixture-{i}', 'timestamp': latest['timestamp'] - (11-i)*10} for i in range(12)] if latest else []
                await route.fulfill(json={'readings': rows})
            elif '/members/fixture-' in path and path.endswith('/observations'):
                await route.fulfill(json={'observations': []})
            else:
                await route.continue_()

        await page.route('**/api/v1/**', intercept)
        await page.goto(WEB + '/?login=1', wait_until='domcontentloaded')
        await page.get_by_role('button', name='Sign in with test account', exact=True).click()
        await expect(page.get_by_test_id('company-workspace')).to_be_visible(timeout=20000)
        rows, pager = page.locator('.co-roster-row'), page.get_by_role('navigation', name='Team members pagination')
        detail, search = page.get_by_test_id('company-selected-signals'), page.get_by_label('Search team members')
        team_filter, status_filter = page.get_by_label('Filter by team', exact=True), page.get_by_label('Filter by data status')
        for key, count in [('all', 200), ('current', 80), ('attention', 80), ('paused', 20)]:
            await expect(page.get_by_test_id(f'summary-{key}')).to_contain_text(str(count))
        await expect(detail).not_to_be_visible()
        await expect(rows).to_have_count(25)
        await expect(pager).to_contain_text('1–25 of 200 people')
        await expect(rows.first).to_contain_text('Person 006')
        await page.get_by_test_id('summary-current').click()
        await expect(pager).to_contain_text('1–25 of 80 people')
        await search.fill('Person 009')
        await expect(rows).to_have_count(0)  # A current recording is never live wearable coverage.
        await page.get_by_test_id('summary-attention').click()
        await expect(page.get_by_test_id('view-attention')).to_have_attribute('aria-pressed', 'true')
        await expect(pager).to_contain_text('1–25 of 80 people')
        await search.fill('Person 006')
        await expect(rows).to_have_count(1)
        await expect(rows).to_contain_text('Permission needed')
        await expect(rows).to_contain_text('2 data issues')
        await search.fill('Person 007')
        await expect(rows).to_have_count(1)
        await expect(rows).to_contain_text('Current')
        await expect(rows).to_contain_text('No recent measurements')
        for name in ('Person 005', 'Person 004', 'Person 008'):
            await search.fill(name)
            await expect(rows).to_have_count(0)  # Summary, paused, unsupported are not connection incidents.
        await search.fill('')
        await page.get_by_test_id('view-all').click()
        await page.get_by_label('Sort team members').select_option('name')
        await expect(rows.first).to_contain_text('Person 001')
        await pager.get_by_role('button', name='Next page').click()
        await expect(rows.first).to_contain_text('Person 026')
        await page.get_by_label('Team members rows per page').select_option('50')
        await expect(rows).to_have_count(50)
        await pager.get_by_role('button', name='Next page').click()
        await expect(rows.first).to_contain_text('Person 051')
        await search.fill('Person 080')
        await expect(rows).to_have_count(1)
        await expect(pager).to_contain_text('1–1 of 1 people')
        trigger = rows.get_by_role('button', name='View signals for Person 080')
        await trigger.focus()
        await page.keyboard.press('Enter')
        await expect(detail).to_be_visible()
        await expect(page.get_by_role('heading', name='Signal detail · Person 080')).to_be_visible()
        assert await detail.evaluate('node => node.contains(document.activeElement)'), 'Detail did not receive keyboard focus'
        for _ in range(16):
            await page.keyboard.press('Tab')
            assert await detail.evaluate('node => node.contains(document.activeElement) || document.activeElement === document.body'), 'Modal focus escaped to workspace'
        await page.keyboard.press('Escape')
        await expect(detail).not_to_be_visible()
        await expect(trigger).to_be_focused()
        await trigger.click()
        state['people'].reverse()
        await poll(page)
        await expect(page.get_by_role('heading', name='Signal detail · Person 080')).to_be_visible()
        await detail.get_by_role('button', name='Back to list').click()
        await expect(detail).not_to_be_visible()
        await expect(trigger).to_be_focused()
        await trigger.click()
        state['people'] = [person for person in state['people'] if person['id'] != 'fixture-080']
        await poll(page)
        await expect(rows).to_have_count(0)
        await expect(detail).not_to_be_visible()
        await expect(page.get_by_role('heading', name=re.compile('No matching'))).to_be_visible()
        state['people'], state['devices'] = fixture_people(time.time())
        await poll(page)
        await search.fill('')
        await status_filter.select_option('summary')
        await expect(rows).to_have_count(20)
        await expect(rows.first).to_contain_text('Period summary')
        await status_filter.select_option('')
        await page.get_by_test_id('summary-paused').click()
        await expect(rows).to_have_count(20)
        assert await rows.locator('time').count() == 0, 'Paused people exposed receipt timestamps'
        await expect(rows.first).not_to_contain_text('Wearable measurements')
        await rows.first.get_by_role('button', name='View signals for Person 004').click()
        await expect(detail).to_contain_text('Sharing is paused')
        assert await detail.locator('.co-readings, .co-signal-tiles, .co-chart-value').count() == 0, 'Paused dialog exposed readings'
        await page.keyboard.press('Escape')
        await page.get_by_test_id('view-all').click()
        await team_filter.select_option('team-1')
        await expect(page.get_by_test_id('summary-all')).to_contain_text('25')
        await expect(rows).to_have_count(25)
        await status_filter.select_option('summary')
        await expect(rows).to_have_count(5)
        await search.fill('Person 025')
        await expect(rows).to_have_count(1)
        await expect(page.get_by_test_id('summary-all')).to_contain_text('25')
        await search.fill('')
        await status_filter.select_option('')
        await team_filter.select_option('')
        await page.get_by_test_id('view-teams').click()
        team_row = page.get_by_test_id('team-summary-team-2')
        await expect(team_row).to_contain_text('25')
        await team_row.get_by_role('button', name='View team Team 2').click()
        await expect(team_filter).to_have_value('team-2')
        await expect(page.get_by_test_id('view-all')).to_have_attribute('aria-pressed', 'true')
        await expect(rows).to_have_count(25)
        await team_filter.select_option('')
        await search.fill('Person 002')
        await expect(rows).to_contain_text('No recent data')
        await expect(rows.locator('time')).to_be_visible()  # Receipt does not freshen an old measurement.
        await search.fill('')
        await page.get_by_label('Team members rows per page').select_option('25')
        await no_overflow(page)
        await page.evaluate('window.scrollTo({top: 0, behavior: "instant"})')
        await page.screenshot(path=str(artifacts / 'company-large-roster-desktop.png'), full_page=True, animations='disabled')
        await page.set_viewport_size({'width': 390, 'height': 844})
        await no_overflow(page)
        await page.get_by_test_id('summary-attention').click()
        await expect(pager).to_contain_text('1–25 of 80 people')
        await page.evaluate('window.scrollTo({top: 0, behavior: "instant"})')
        await page.screenshot(path=str(artifacts / 'company-large-roster-mobile.png'), full_page=True, animations='disabled')
        await rows.first.get_by_role('button', name=re.compile('View signals for')).click()
        await expect(detail).to_be_visible()
        assert await detail.evaluate('node => node.scrollWidth <= node.clientWidth + 1'), 'Mobile detail dialog overflow'
        await page.screenshot(path=str(artifacts / 'company-large-roster-mobile-dialog.png'), animations='disabled')
        await page.keyboard.press('Escape')
        await no_overflow(page)
        await page.get_by_test_id('view-all').click()
        await search.fill('Person 003')
        await rows.get_by_role('button', name='Set up phone for Person 003').click()
        employee_rows = page.get_by_role('list', name='Employees').get_by_role('listitem')
        await expect(employee_rows).to_have_count(1)
        await expect(employee_rows).to_contain_text('Person 003')
        await expect(employee_rows.get_by_role('button', name='Connect phone')).to_be_focused()
        await page.get_by_role('button', name='Show all employees', exact=True).click()
        await expect(employee_rows).to_have_count(25)
        await page.get_by_label('Employees rows per page').select_option('50')
        await expect(employee_rows).to_have_count(50)
        await page.get_by_label('Search employees or teams').fill('Person 199')
        await expect(employee_rows).to_have_count(1)
        await page.get_by_label('Search employees or teams').fill('')
        await page.get_by_label('Filter employee sharing').select_option('paused')
        await expect(employee_rows).to_have_count(20)
        await no_overflow(page)
        assert state['requests'] >= 4, 'Polling scenarios did not run'
        assert state['writes'] == 0, 'Fixture attempted a company mutation'
        assert not errors, errors
        await browser.close()
    print('PASS: 200 browser-only people, eight teams; scoped summaries, partial-signal connection help, summary/paused/unsupported exclusions, freshness, 25/50 paging, filters, team drill-down, keyboard modal focus/return, polling/removal, mobile and employee administration. No company writes or browser errors. UI coverage, not backend capacity.')


if __name__ == '__main__':
    asyncio.run(main())
