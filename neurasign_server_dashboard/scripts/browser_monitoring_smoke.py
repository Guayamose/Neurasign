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
        await expect(page.get_by_role('heading', name='Team signals', exact=True)).to_be_visible()
        source_context = page.get_by_test_id('demo-source-context')
        await expect(source_context).to_contain_text('record', ignore_case=True)
        await expect(source_context).to_contain_text('UNIVERSE')
        await expect(page.get_by_test_id('monitoring-play')).to_contain_text('Pause recording')
        for action in (page.get_by_test_id('monitoring-play'),):
            bounds = await action.bounding_box()
            assert bounds and bounds['height'] >= 44 and bounds['y'] + bounds['height'] <= 1000, 'Main playback actions must be usable and visible without scrolling'
        await expect(page.get_by_role('button', name='Restart demo', exact=True)).not_to_be_visible()
        await expect(page.get_by_test_id('presenter-controls')).not_to_have_attribute('open', '')
        await expect(page.get_by_test_id('monitoring-source')).not_to_be_visible()
        await expect(page.get_by_test_id('demo-comparison')).not_to_have_attribute('open', '')
        await expect(page.get_by_test_id('demo-estimates')).not_to_have_attribute('open', '')
        await expect(page.locator('.data-chart:visible')).to_have_count(1)
        for metric, label in [('heart_rate', 'Heart rate'), ('hrv', 'Heart rate variability'), ('eda', 'Skin conductance'), ('temperature', 'Skin temperature'), ('movement', 'Movement')]:
            await expect(page.get_by_test_id('metric-' + metric)).to_have_text(label)
        await expect(page.get_by_test_id('monitor-worker-alex').get_by_role('button', name='View details for Alex')).to_be_visible()
        await expect(page.locator('html')).to_have_attribute('lang', 'en')
        await expect(page.get_by_test_id('monitoring-dashboard')).to_contain_text('bpm')
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
            await page.get_by_test_id('tab-examples').click()
            await page.get_by_test_id('tab-'+tab).click()
            await expect(source_context).to_contain_text('UNIVERSE')
            await expect(page.get_by_role('button', name='Back to examples', exact=True)).to_be_visible()
            await page.screenshot(path=str(artifacts/('example-'+tab+'.png')), full_page=True)
            current = await (await page.request.get(API+'/api/state')).json()
            assert current['source']['kind'] == 'universe'
            assert current['workflow'] is None, 'Opening an example must not launch an incident'
        await expect(page.get_by_test_id('start-incident')).to_be_visible()
        await page.get_by_role('button', name='Back to examples', exact=True).click()
        for tab in ('wellbeing', 'focus', 'incidents'):
            await expect(page.get_by_test_id('tab-' + tab)).to_be_visible()
        await expect(source_context).to_contain_text('UNIVERSE')
        await page.get_by_test_id('tab-monitoring').click()
        await expect(page.get_by_test_id('monitoring-dashboard')).to_be_visible()
        for width in (1440, 1024, 768, 390, 320):
            await page.set_viewport_size({'width':width, 'height':844})
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), f'Mobile horizontal overflow at {width}px'
            for tab in ('monitoring', 'manager', 'examples'):
                bounds = await page.get_by_test_id('tab-' + tab).bounding_box()
                assert bounds and bounds['x'] >= 0 and bounds['x'] + bounds['width'] <= width + 1, f'Hidden navigation: {tab} at {width}px'
        await page.set_viewport_size({'width':390, 'height':844})
        await page.screenshot(path=str(artifacts/'monitoring-mobile.png'), full_page=True)
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), 'Mobile horizontal overflow'
        await page.get_by_test_id('demo-estimates').locator('summary').click()
        await page.locator('[data-testid^="metric-help-readiness"]').first.click()
        await expect(help_dialog).to_contain_text('another task')
        await page.screenshot(path=str(artifacts/'metric-help-mobile.png'), full_page=True)
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), 'Metric help overflows mobile'
        await page.get_by_role('button', name='Close metric help').click()
        assert not errors, json.dumps(errors)
        await browser.close()
    print('PASS: English recorded monitoring at /demo; recorded profiles, physiological graphs/units, employee selection, one-chart first screen, collapsed presenter settings, full metric names, accessible metric definitions, shared-source examples, mobile layout and no browser errors.', flush=True)


if __name__ == '__main__':
    asyncio.run(main())
