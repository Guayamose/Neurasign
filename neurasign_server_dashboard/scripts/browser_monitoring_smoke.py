"""Exercise the primary team monitoring dashboard and example navigation."""
import asyncio
import json
import os
from pathlib import Path
from playwright.async_api import async_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
WEB = os.getenv('NEURASIGN_WEB_URL', 'http://localhost:3000')
API = os.getenv('NEURASIGN_API_URL', 'http://localhost:8000')


async def main():
    artifacts = ROOT / 'artifacts'
    artifacts.mkdir(exist_ok=True)
    errors = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='chrome', headless=True, args=['--no-sandbox'])
        page = await browser.new_page(viewport={'width':1440, 'height':1000})
        page.on('pageerror', lambda error: errors.append(str(error)))
        response = await page.request.post(API+'/api/control', data={'action':'reset'})
        assert response.ok
        await page.goto(WEB+'/demo', wait_until='domcontentloaded')
        await expect(page.get_by_test_id('monitoring-dashboard')).to_be_visible(timeout=30000)
        await expect(page.get_by_test_id('monitor-worker-alex')).to_be_visible()
        await expect(page.get_by_test_id('monitor-worker-aoi')).to_be_visible()
        await expect(page.get_by_test_id('selected-physiology-chart')).to_be_visible()
        await expect(page.locator('html')).to_have_attribute('lang', 'en')
        await expect(page.get_by_test_id('monitoring-dashboard')).to_contain_text('bpm')
        await expect(page.get_by_test_id('monitoring-dashboard')).to_contain_text('UNIVERSE')
        initial = await (await page.request.get(API+'/api/state')).json()
        assert initial['workflow'] is None
        assert initial['monitoring']['source_kind'] == 'universe'
        assert all(len(worker['history']) >= 2 for worker in initial['monitoring']['workers'])
        await page.screenshot(path=str(artifacts/'monitoring-desktop.png'), full_page=True)
        await page.get_by_test_id('select-person-aoi').click()
        await expect(page.get_by_test_id('selected-physiology-chart')).to_contain_text('Signal detail · Sam')
        await page.get_by_test_id('metric-hrv').click()
        await expect(page.get_by_test_id('metric-hrv')).to_have_attribute('aria-pressed','true')
        await page.screenshot(path=str(artifacts/'monitoring-aoi.png'), full_page=True)
        help_button = page.locator('[data-testid^="metric-help-hrv"]').first
        await help_button.focus()
        await page.keyboard.press('Enter')
        help_dialog = page.get_by_test_id('metric-help-dialog')
        await expect(help_dialog).to_be_visible()
        await expect(help_dialog).to_contain_text('successive pulse beats')
        await expect(help_dialog.get_by_text('How it works & limitations')).to_be_visible()
        for _ in range(6):
            await page.keyboard.press('Tab')
            assert await help_dialog.evaluate('(dialog) => dialog.contains(document.activeElement)'), 'Metric help must contain keyboard focus'
        await page.keyboard.press('Escape')
        await expect(help_dialog).not_to_be_visible()
        await expect(help_button).to_be_focused()
        for tab in ('wellbeing', 'focus', 'incidents'):
            await page.get_by_test_id('tab-'+tab).click()
            await page.screenshot(path=str(artifacts/('example-'+tab+'.png')), full_page=True)
            current = await (await page.request.get(API+'/api/state')).json()
            assert current['source']['kind'] == 'universe'
            assert current['workflow'] is None, 'Opening an example must not launch an incident'
        await expect(page.get_by_test_id('start-incident')).to_be_visible()
        await page.get_by_test_id('tab-monitoring').click()
        await expect(page.get_by_test_id('monitoring-dashboard')).to_be_visible()
        await page.set_viewport_size({'width':390, 'height':844})
        await page.screenshot(path=str(artifacts/'monitoring-mobile.png'), full_page=True)
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), 'Mobile horizontal overflow'
        await page.locator('[data-testid^="metric-help-readiness"]').first.click()
        await expect(help_dialog).to_contain_text('another task')
        await page.screenshot(path=str(artifacts/'metric-help-mobile.png'), full_page=True)
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), 'Metric help overflows mobile'
        await page.get_by_role('button', name='Close metric help').click()
        assert not errors, json.dumps(errors)
        await browser.close()
    print('PASS: English recorded monitoring at /demo; recorded profiles, physiological graphs/units, employee selection, accessible metric definitions, shared-source examples, mobile layout and no browser errors.', flush=True)


if __name__ == '__main__':
    asyncio.run(main())
