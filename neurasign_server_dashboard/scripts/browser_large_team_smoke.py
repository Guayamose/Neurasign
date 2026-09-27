"""Exercise 100 browser-only roster records. Never upload or seed company fixtures."""
import asyncio
import copy
import json
import os
from pathlib import Path
import time
from urllib.parse import urlparse

from playwright.async_api import async_playwright, expect

WEB = os.getenv('NEURASIGN_WEB', 'http://localhost:3000')
ROOT = Path(__file__).resolve().parents[1]


def fixture_people(now):
    people = []
    for index in range(1, 101):
        status = ['current', 'stale', 'waiting', 'paused'][index % 4]
        timestamp = now - (10 if status == 'current' else 500)
        reading = {'id': f'fixture-reading-{index}', 'timestamp': timestamp, 'received_at': now - index,
                   'window_seconds': 10, 'source': 'recording', 'quality': None,
                   'features': {'heart_rate': 72, 'hrv': 44, 'eda': 1.2, 'temperature': 32.4, 'movement': None}}
        people.append({'id': f'fixture-{index:03}', 'name': f'Person {index:03}', 'email': '', 'role': 'employee',
                       'team_id': 'north' if index % 2 == 0 else 'south', 'sharing': status != 'paused',
                       'status': status, 'latest': reading if status in ('current', 'stale') else None,
                       'features': reading['features'] if status == 'current' else {key: None for key in reading['features']}, 'signals': []})
    # Match backend's aggregate stale status for valid canonical summaries.
    people[0].update(status='stale', latest=None, sharing=True, signals=[{
        'series_id': 'fixture-summary', 'metric': 'heart_rate', 'source_id': 'fixture-source',
        'source_name': 'Browser-only fixture', 'source': 'recording', 'unit': 'bpm', 'measurement_kind': 'summary',
        'delivery_mode': 'sync', 'interval_seconds': 86400, 'method': 'fixture', 'status': 'summary',
        'latest': {'id': 'fixture-day', 'value': 72, 'timestamp': now - 500, 'received_at': now,
                   'method': 'fixture', 'interval_seconds': 86400}}])
    return people


async def main():
    if urlparse(WEB).hostname not in ('localhost', '127.0.0.1'):
        raise RuntimeError('Browser fixtures may only run on the local stack.')
    state = {'people': fixture_people(time.time()), 'requests': 0, 'writes': 0}
    errors = []
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
                payload = await original.json()
                payload.update(members=copy.deepcopy(state['people']), devices=[],
                               teams=[{'id': 'north', 'name': 'North team'}, {'id': 'south', 'name': 'South team'}],
                               metric_catalog=[{'id': 'heart_rate', 'name': 'Heart rate', 'unit': 'bpm', 'digits': 0,
                                                'meaning': 'Beats per minute.', 'freshness_seconds': 60}], server_time=time.time())
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
        rows = page.locator('.co-roster-row')
        pager = page.get_by_role('navigation', name='Team members pagination')
        await expect(rows).to_have_count(25)
        await expect(pager).to_contain_text('1–25 of 100 people')
        await pager.get_by_role('button', name='Next page').click()
        await expect(rows.first).to_contain_text('Person 026')
        await page.get_by_label('Team members rows per page').select_option('50')
        await expect(rows).to_have_count(50)
        await pager.get_by_role('button', name='Next page').click()
        await expect(rows.first).to_contain_text('Person 051')
        await page.get_by_label('Search team members').fill('Person 080')
        await expect(rows).to_have_count(1)
        await expect(pager).to_contain_text('1–1 of 1 people')
        await rows.get_by_role('button', name='View signals for Person 080').click()
        detail = page.get_by_test_id('company-selected-signals')
        await expect(detail).to_be_focused()
        await expect(page.get_by_role('heading', name='Signal detail · Person 080')).to_be_visible()
        # A new polling snapshot may reorder source rows; selected identity must hold.
        state['people'].reverse()
        async with page.expect_response('**/dashboard'):
            pass
        await expect(page.get_by_role('heading', name='Signal detail · Person 080')).to_be_visible()
        await detail.get_by_role('button', name='Back to list').click()
        await expect(rows.get_by_role('button', name='View signals for Person 080')).to_be_focused()
        state['people'] = [person for person in state['people'] if person['id'] != 'fixture-080']
        async with page.expect_response('**/dashboard'):
            pass
        await expect(rows).to_have_count(0)
        await expect(detail.get_by_role('heading', name='View one person’s signals')).to_be_visible()
        await page.get_by_label('Search team members').fill('')
        await page.get_by_label('Filter by data status').select_option('summary')
        await expect(rows).to_have_count(1)
        await expect(rows).to_contain_text('Period summary')
        await page.get_by_label('Filter by data status').select_option('paused')
        await expect(rows).to_have_count(25)
        assert await rows.locator('time').count() == 0, 'Paused people exposed a receipt timestamp'
        await page.get_by_label('Filter by data status').select_option('')
        await page.get_by_label('Filter by team').select_option('north')
        await page.get_by_label('Filter by data status').select_option('current')
        await expect(rows).to_have_count(24)
        await page.get_by_role('button', name='Clear filters', exact=True).click()
        await page.get_by_label('Sort team members').select_option('name_desc')
        await expect(rows.first).to_contain_text('Person 100')
        await page.get_by_label('Sort team members').select_option('recent')
        await expect(rows.first).to_contain_text('Person 001')
        await page.get_by_label('Team members rows per page').select_option('25')
        await page.screenshot(path=str(ROOT / 'artifacts/company-large-roster-desktop.png'), full_page=True)
        await page.set_viewport_size({'width': 390, 'height': 844})
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), 'Mobile roster overflow'
        await rows.first.get_by_role('button', name='View signals for Person 001').click()
        await expect(detail).to_be_focused()
        await page.screenshot(path=str(ROOT / 'artifacts/company-large-roster-mobile.png'), full_page=True)
        await page.get_by_test_id('company-tab-people').click()
        employee_rows = page.get_by_role('list', name='Employees').get_by_role('listitem')
        await expect(employee_rows).to_have_count(25)
        await page.get_by_label('Employees rows per page').select_option('50')
        await expect(employee_rows).to_have_count(50)
        await page.get_by_label('Search employees or teams').fill('Person 099')
        await expect(employee_rows).to_have_count(1)
        await page.get_by_label('Search employees or teams').fill('')
        await page.get_by_label('Filter employee team').select_option('south')
        await page.get_by_label('Filter employee sharing').select_option('paused')
        await expect(employee_rows).to_have_count(25)
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), 'Mobile employee list overflow'
        assert state['writes'] == 0, 'Fixture attempted a company mutation'
        assert not errors, errors
        await browser.close()
    print('PASS: 100 browser-only people; 25/50 paging, combined filters, sorting, canonical summary, paused privacy, detail focus/return, polling/removal, mobile layout and employee administration. No company fixture writes or browser errors.')


if __name__ == '__main__':
    asyncio.run(main())
