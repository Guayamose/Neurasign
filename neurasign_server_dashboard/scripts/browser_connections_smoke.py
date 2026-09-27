"""Local, browser-only large connection list; no fixture data reaches storage."""
import asyncio
import copy
import os
from pathlib import Path
import time
from urllib.parse import urlparse

from playwright.async_api import async_playwright, expect

WEB = os.getenv('NEURASIGN_WEB', 'http://localhost:3000')
ROOT = Path(__file__).resolve().parents[1]


async def main():
    if urlparse(WEB).hostname not in ('localhost', '127.0.0.1'):
        raise RuntimeError('Only the local stack may use connection browser fixtures.')
    people, devices = [], []
    for index in range(1, 138):
        person_id = f'connection-person-{index}'
        people.append({'id': person_id, 'name': f'Person {index:03}', 'email': '', 'role': 'employee',
                       'team_id': 'connection-team', 'sharing': index != 1, 'status': 'paused' if index == 1 else 'waiting',
                       'latest': None, 'signals': [],
                       'features': {'heart_rate': None, 'hrv': None, 'eda': None, 'temperature': None, 'movement': None}})
        devices.append({'id': f'connection-device-{index}', 'name': f'Phone {index:03}', 'member_id': person_id,
                        'source': 'wearable', 'revoked': index % 11 == 0, 'last_received_at': time.time() - 120})
    # Same display name must not cause reconnect to target the wrong person.
    people[131]['name'] = people[130]['name']
    state = {'writes': 0}
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
                await route.fulfill(status=403, json={'detail': 'Company writes are disabled for browser fixtures.'})
            elif path.endswith('/dashboard'):
                response = await route.fetch()
                payload = await response.json()
                payload.update(members=copy.deepcopy(people), devices=copy.deepcopy(devices),
                               teams=[{'id': 'connection-team', 'name': 'Operations'}], server_time=time.time())
                await route.fulfill(response=response, json=payload)
            else:
                await route.continue_()

        await page.route('**/api/v1/**', intercept)
        await page.goto(WEB + '/?login=1', wait_until='domcontentloaded')
        await page.get_by_role('button', name='Sign in with test account', exact=True).click()
        await expect(page.get_by_test_id('company-workspace')).to_be_visible(timeout=20000)
        await expect(page.get_by_role('link', name='Model engine', exact=True)).not_to_be_visible()
        await page.locator('.co-research-nav > summary').focus()
        await page.keyboard.press('Enter')
        await expect(page.get_by_role('link', name='Model engine', exact=True)).to_be_visible()
        await page.locator('.co-research-nav > summary').click()
        await page.get_by_test_id('company-tab-devices').click()
        await expect(page.get_by_role('heading', name='Phone connections', exact=True)).to_be_visible()
        await expect(page.locator('.co-nav [aria-current=page]')).to_have_count(1)
        rows = page.locator('.co-connections-table tbody tr')
        pager = page.get_by_role('navigation', name='Connections pagination')
        await expect(rows).to_have_count(25)
        await expect(pager).to_contain_text('1–25 of 125 connections')
        await expect(page.get_by_test_id('connection-connection-device-1')).to_contain_text('Hidden while sharing is paused')
        await pager.get_by_role('button', name='Next page').click()
        await expect(pager).to_contain_text('26–50 of 125 connections')
        await page.get_by_label('Connections rows per page').select_option('50')
        await expect(rows).to_have_count(50)
        await expect(pager).to_contain_text('1–50 of 125 connections')
        await page.get_by_label('Search connections').fill('Person 100')
        await expect(rows).to_have_count(1)
        await expect(rows).to_contain_text('Phone 100')
        await page.get_by_label('Search connections').fill('Phone 099')
        await expect(rows).to_have_count(0)
        await page.get_by_label('Filter connection access').select_option('revoked')
        await expect(rows).to_have_count(1)
        await expect(rows).to_contain_text('Revoked')
        await expect(rows.get_by_role('button', name='Revoke Phone 099', exact=True)).to_have_count(0)
        await page.get_by_label('Search connections').fill('Phone 132')
        await rows.get_by_role('button', name='Reconnect phone', exact=True).click()
        await expect(page.get_by_role('heading', name='People & teams', exact=True)).to_be_visible()
        await expect(page.locator('.co-employee-row')).to_have_count(1)
        targeted = page.locator('.co-employee-row.targeted')
        await expect(targeted).to_contain_text('Person 131')
        await expect(targeted).to_have_attribute('data-person-id', 'connection-person-132')
        await expect(targeted.get_by_role('button', name='Remove Person 131', exact=True)).to_be_visible()
        await expect(targeted.get_by_role('button', name='Connect phone', exact=True)).to_be_focused()
        await expect(page.get_by_label('Search employees or teams')).to_have_value('Person 131')
        await page.get_by_role('button', name='Show all employees', exact=True).click()
        await expect(page.locator('.co-employee-row')).to_have_count(25)
        await expect(page.get_by_role('navigation', name='Employees pagination')).to_contain_text('137 people')
        await expect(page.get_by_label('Employee name', exact=True)).not_to_be_visible()
        await page.get_by_role('button', name='Add employee', exact=True).click()
        await expect(page.get_by_label('Employee name', exact=True)).to_be_focused()
        await page.get_by_test_id('company-tab-devices').click()
        assert await page.evaluate('scrollY') == 0, 'Changing sections should show the new heading'
        await page.get_by_label('Filter connection access').select_option('all')
        await expect(pager).to_contain_text('137 connections')
        await page.screenshot(path=str(artifacts / 'connections-large-desktop.png'), full_page=True)
        await page.set_viewport_size({'width': 390, 'height': 844})
        await expect(page.get_by_test_id('company-tab-devices')).to_be_visible()
        await expect(page.get_by_test_id('company-tab-sharing')).to_be_visible()
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), 'Mobile overflow'
        await page.get_by_label('Search connections').fill('Phone 137')
        await expect(rows).to_have_count(1)
        await expect(rows).to_contain_text('Phone 137')
        await page.screenshot(path=str(artifacts / 'connections-large-mobile.png'), full_page=True)
        assert state['writes'] == 0, state
        assert not errors, errors
        await browser.close()
    print('PASS: 137 browser-only connections, search, allowed/revoked separation, 25/50 pagination, paused timestamps hidden, exact-person reconnect with duplicate names, progressive employee setup, keyboard navigation and mobile layout; no company writes.')


if __name__ == '__main__':
    asyncio.run(main())
