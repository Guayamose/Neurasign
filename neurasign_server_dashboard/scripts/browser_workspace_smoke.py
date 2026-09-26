"""Browser acceptance against local Firebase emulators, with two real sessions."""
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import secrets

from playwright.async_api import async_playwright, expect
from workspace_smoke import WEB, call, test_user, verify_email

ROOT = Path(__file__).resolve().parents[1]


async def main():
    config = call('GET', '/config')
    assert config['firebase']['projectId'] == 'demo-neurasign' and config['emulator_url']
    errors = []
    artifacts = ROOT / 'artifacts'
    artifacts.mkdir(exist_ok=True)
    email = f'browser-owner-{secrets.token_hex(5)}@example.test'
    password = secrets.token_urlsafe(24)
    sam = test_user('Sam')
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='chrome', headless=True, args=['--no-sandbox'])
        owner_context = await browser.new_context(viewport={'width': 1440, 'height': 1000})
        owner = await owner_context.new_page()
        owner.on('pageerror', lambda error: errors.append(str(error)))
        await owner.goto(WEB, wait_until='domcontentloaded')
        await expect(owner.get_by_role('heading', name='Welcome to NEURASIGN')).to_be_visible()
        await owner.screenshot(path=str(artifacts / 'company-sign-in.png'), full_page=True)
        await owner.get_by_role('button', name='New here? Create an account').click()
        await owner.get_by_label('Full name').fill('Taylor')
        await owner.get_by_label('Work email').fill(email)
        await owner.get_by_label('Password', exact=True).fill(password)
        await owner.get_by_role('button', name='Create account', exact=True).click()
        await expect(owner.get_by_role('heading', name='Verify your email')).to_be_visible(timeout=15000)
        await expect(owner.get_by_role('status')).to_contain_text('Verification email sent')
        verify_email(email)
        await owner.get_by_role('button', name='I have verified my email').click()
        await expect(owner.get_by_role('heading', name='Set up your workspace')).to_be_visible(timeout=15000)
        await owner.get_by_label('Company name').fill('Northstar Team')
        await owner.get_by_role('button', name='Create workspace', exact=True).click()
        await expect(owner.get_by_test_id('company-workspace')).to_be_visible(timeout=15000)
        await expect(owner.get_by_role('heading', name='Connect your first employee')).to_be_visible()
        # Compatibility coverage for existing employee logins; new phone-only
        # onboarding has its own browser/native acceptance suite.
        from workspace_smoke import auth_call
        owner_token = auth_call('signInWithPassword', {'email': email, 'password': password, 'returnSecureToken': True})['idToken']
        org = call('GET', '/me', owner_token)['organizations'][0]['id']
        token = call('POST', f'/organizations/{org}/invitations', owner_token, {'email': sam['email']}, 201)['token']
        link = f'{WEB}/#invite={token}'
        employee_context = await browser.new_context(viewport={'width': 1280, 'height': 900})
        employee = await employee_context.new_page()
        employee.on('pageerror', lambda error: errors.append(str(error)))
        await employee.goto(link, wait_until='domcontentloaded')
        await employee.get_by_label('Work email').fill(sam['email'])
        await employee.get_by_label('Password', exact=True).fill(sam['password'])
        await employee.get_by_role('button', name='Sign in', exact=True).click()
        await expect(employee.get_by_role('heading', name='Join your team')).to_be_visible(timeout=15000)
        await employee.get_by_role('button', name='Join workspace', exact=True).click()
        await expect(employee.get_by_test_id('company-workspace')).to_be_visible(timeout=15000)
        await employee.get_by_test_id('company-tab-sharing').click()
        await employee.get_by_role('button', name='Enable sharing', exact=True).click()
        await expect(employee.get_by_role('button', name='Pause sharing', exact=True)).to_be_visible()
        await employee.get_by_test_id('company-tab-devices').click()
        await employee.get_by_text('Advanced · personal gateway credential', exact=True).click()
        await employee.get_by_label('Device name').fill('Example recording')
        await employee.get_by_label('Signal source').select_option('recording')
        await employee.get_by_role('button', name='Authorize device', exact=True).click()
        await expect(employee.get_by_label('Device credential')).to_be_visible()
        credential = await employee.get_by_label('Device credential').input_value()
        now = datetime.now(timezone.utc)
        rows = [{'id': f'browser-{i:08}', 'timestamp': (now - timedelta(seconds=(11-i)*10)).isoformat(), 'features': {'heart_rate': 70 + i % 5, 'hrv': 40 + i % 7, 'eda': 1.2, 'temperature': 32.4}, 'window_seconds': 10} for i in range(12)]
        assert call('POST', '/readings', credential, {'readings': rows})['accepted'] == 12
        await owner.get_by_test_id('company-tab-overview').click()
        sam_id = hashlib.sha256(sam['uid'].encode()).hexdigest()
        card = owner.get_by_test_id(f'company-person-{sam_id}')
        await expect(card).to_contain_text('DEMO RECORDING', timeout=15000)
        await card.click()
        await expect(owner.get_by_role('heading', name='Signal detail · Sam')).to_be_visible()
        await expect(card).to_contain_text('Current')
        await owner.get_by_role('button', name='HRV', exact=True).click()
        await owner.locator('.co-chart-value summary').click()
        await expect(owner.locator('.co-chart-value')).to_contain_text('successive beat intervals')
        await owner.screenshot(path=str(artifacts / 'company-desktop.png'), full_page=True)
        await owner.set_viewport_size({'width': 390, 'height': 844})
        await owner.screenshot(path=str(artifacts / 'company-mobile.png'), full_page=True)
        assert await owner.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), 'Mobile overflow'
        await employee.get_by_test_id('company-tab-overview').click()
        await expect(employee.locator('.co-person')).to_have_count(1)
        await employee.get_by_test_id('company-tab-sharing').click()
        await employee.get_by_role('button', name='Pause sharing', exact=True).click()
        await expect(card).to_contain_text('Sharing paused', timeout=15000)
        await expect(card).not_to_contain_text('DEMO RECORDING')
        await employee.get_by_test_id('company-tab-devices').click()
        await employee.get_by_role('button', name='Revoke Example recording').click()
        await expect(employee.get_by_role('button', name='Revoke Example recording')).not_to_be_visible()
        call('POST', '/readings', credential, {'readings': rows}, expected=401)
        await owner.get_by_role('button', name='Sign out', exact=True).click()
        await expect(owner.get_by_role('heading', name='Welcome to NEURASIGN')).to_be_visible()
        await expect(owner.get_by_test_id('company-workspace')).not_to_be_visible()
        assert not errors, errors
        await browser.close()
    print('PASS: browser signup/email verification, workspace creation, invitation, isolated employee session, sharing, device authorization, labeled measurements, charts/help, mobile layout, revocation and sign-out; no browser errors.')


if __name__ == '__main__':
    asyncio.run(main())
