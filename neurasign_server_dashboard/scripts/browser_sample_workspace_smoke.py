"""Verify local sample entry, company/deep-link refresh and navigation.

Uses the public local sample only, without changing workflow records or
connecting phones. Fictional-profile screenshots stay in ignored artifacts.
"""
import asyncio
import json
from pathlib import Path
from urllib.parse import urlparse
from playwright.async_api import async_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
WEB = 'http://localhost:3000'


async def main():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(executable_path='/usr/bin/google-chrome', headless=True)
        context = await browser.new_context(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
        page = await context.new_page()
        errors, external = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: external.append(request.url) if urlparse(request.url).hostname not in ('localhost', '127.0.0.1', None) else None)
        artifacts = ROOT / 'artifacts'
        artifacts.mkdir(exist_ok=True)
        await page.goto(WEB + '/demo')
        await expect(page.get_by_test_id('command-center')).to_be_visible(timeout=30000)
        await expect(page.get_by_label('Sample workspace', exact=True)).to_be_visible()
        company = await page.get_by_label('Company workspace', exact=True).input_value()
        assert company
        await expect(page.get_by_test_id('ops-summary-people')).to_contain_text('36')
        await page.screenshot(path=str(artifacts / 'sample-overview-desktop.png'))
        await page.locator('.ops-view-person').first.click()
        await expect(page.get_by_role('dialog')).to_be_visible()
        await expect(page.get_by_text('Illustrative estimates', exact=True)).to_be_visible()
        await page.screenshot(path=str(artifacts / 'sample-person-desktop.png'))
        await page.keyboard.press('Escape')
        await page.get_by_test_id('company-tab-applications').click()
        await expect(page.get_by_test_id('apps-hub')).to_be_visible()
        await page.get_by_test_id('apps-open-tasks').click()
        await page.locator('.apps-record-row').first.click()
        await expect(page.get_by_role('dialog')).to_be_visible()
        title = await page.locator('dialog h2').inner_text()
        link = page.url
        await page.reload()
        await expect(page.get_by_role('dialog')).to_be_visible(timeout=30000)
        await expect(page.get_by_label('Company workspace', exact=True)).to_have_value(company)
        await expect(page.locator('dialog h2')).to_have_text(title)
        assert page.url == link, 'Record deep link was lost on refresh'
        await page.keyboard.press('Escape')
        for width in (1440, 390, 320):
            await page.set_viewport_size({'width': width, 'height': 1000 if width > 1000 else 844})
            for tab in ('overview', 'people', 'devices', 'sharing', 'applications'):
                await page.get_by_test_id('company-tab-' + tab).click()
                await expect(page.get_by_test_id('company-workspace')).to_be_visible()
                await page.evaluate('document.fonts.ready')
                assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth+1'), f'Overflow: {tab}, {width}'
                if width in (1440, 390):
                    await page.screenshot(path=str(artifacts / f'sample-{tab}-{width}.png'))
        await page.get_by_role('link', name='Back to sign in', exact=True).click()
        await expect(page.get_by_role('button', name='Sign in', exact=True)).to_be_visible(timeout=15000)
        await expect(page.get_by_test_id('company-workspace')).to_have_count(0)
        assert not errors, errors
        assert not external, external
        summary = {'entry': '/demo', 'profiles': 36, 'sample_company_refresh': True, 'record_deep_link_refresh': True, 'return_to_sign_in': True, 'widths': [1440, 390, 320], 'page_errors': len(errors), 'external_requests': len(external)}
        (artifacts / 'sample-workspace-acceptance.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps(summary))
        await browser.close()


if __name__ == '__main__':
    asyncio.run(main())
