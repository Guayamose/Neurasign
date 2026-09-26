"""Local-only gateway SDK -> public API -> Firestore -> browser acceptance.

Creates a separate test account/workspace. Recorded inputs are explicitly labeled
and never inserted into the user's company or the quick-login workspace.
"""
import asyncio
import json
import os
from pathlib import Path
import re
import subprocess

from playwright.async_api import async_playwright, expect

from workspace_smoke import WEB, call, test_user

ROOT = Path(__file__).resolve().parents[1]
PHONE = ROOT.parent / 'neurasign_phone_app'


async def main():
    config = call('GET', '/config')
    assert config['firebase']['projectId'] == 'demo-neurasign' and config['emulator_url']
    owner = test_user('Taylor')
    org = call('POST', '/organizations', owner['token'], {'name': 'Gateway contract test'}, 201)['id']
    base = f'/organizations/{org}'
    call('PATCH', base + '/me/sharing', owner['token'], {'enabled': True})
    gateway = call('POST', base + '/devices', owner['token'], {'name': 'Recorded gateway test', 'source': 'recording'}, 201)
    result = subprocess.run(['node', 'tests/transport-smoke.mjs'], cwd=PHONE, check=True, capture_output=True, text=True,
        env={**os.environ, 'NEURASIGN_TEST_ORIGIN': WEB, 'NEURASIGN_TEST_GATEWAY_CREDENTIAL': gateway['credential']})
    assert json.loads(result.stdout)['uploaded'] == 6
    person = call('GET', base + '/dashboard', owner['token'])['members'][0]
    signals = {item['metric']: item for item in person['signals']}
    assert signals['heart_rate']['status'] == 'current' and signals['heart_rate']['latest']['value'] == 75
    assert signals['skin_temperature']['status'] == 'delayed' and abs(signals['skin_temperature']['latest']['value'] - 30) < .000001
    assert signals['hrv_sdnn']['status'] == 'summary'
    assert signals['electrodermal_conductance']['status'] == 'unsupported'
    history_path = base + f'/members/{person["id"]}/observations?series_id={signals["heart_rate"]["series_id"]}'
    assert len(call('GET', history_path, owner['token'])['observations']) == 4
    outsider = test_user('Jordan')
    call('GET', history_path, outsider['token'], expected=403)
    errors = []
    artifacts = ROOT / 'artifacts'
    artifacts.mkdir(exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='chrome', headless=True, args=['--no-sandbox'])
        page = await browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.goto(WEB, wait_until='domcontentloaded')
        await page.get_by_label('Work email').fill(owner['email'])
        await page.get_by_label('Password', exact=True).fill(owner['password'])
        await page.get_by_role('button', name='Sign in', exact=True).click()
        panel = page.get_by_test_id('canonical-signals')
        await expect(panel).to_be_visible(timeout=15000)
        card = page.get_by_test_id(f'company-person-{person["id"]}')
        await expect(card).to_contain_text('Delayed')
        await expect(card).to_contain_text('Summary')
        await expect(card).to_contain_text('Unavailable')
        await expect(panel.get_by_role('img')).to_be_visible(timeout=10000)
        await expect(panel).to_contain_text('DEMO RECORDING')
        await page.screenshot(path=str(artifacts / 'gateway-desktop.png'), full_page=True)
        await panel.get_by_role('button', name=re.compile('HRV · SDNN')).click()
        await expect(panel.locator('.co-chart-value')).to_contain_text('58')
        await expect(panel.get_by_role('img')).to_have_attribute('aria-label', re.compile('HRV · SDNN. 1 samples.'))
        await panel.get_by_text('About this metric').click()
        await expect(panel).to_contain_text('different quantity from RMSSD')
        await page.set_viewport_size({'width': 390, 'height': 844})
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), 'Mobile overflow'
        await page.screenshot(path=str(artifacts / 'gateway-mobile.png'), full_page=True)
        call('PATCH', base + '/me/sharing', owner['token'], {'enabled': False})
        await expect(card).to_contain_text('Sharing paused', timeout=15000)
        await expect(panel.get_by_role('img')).to_have_count(0)
        assert not errors, errors
        await browser.close()
    assert not call('GET', history_path, owner['token'])['observations']
    assert call('DELETE', base + '/me/readings', owner['token'])['deleted'] == 6
    call('DELETE', base + f'/devices/{gateway["device"]["id"]}', owner['token'])
    print('PASS: gateway SDK, Firestore persistence, server normalization, independent freshness, summary semantics, company isolation, history, pause/deletion and desktop/mobile browser. Recorded fixtures only; no hardware claim.')


if __name__ == '__main__':
    asyncio.run(main())
