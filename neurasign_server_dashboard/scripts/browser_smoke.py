"""Exercise the secondary incident example using the current monitored team.
--require-live requires genuine Jev selections and four Gemini responses.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import time
from playwright.async_api import async_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
WEB = os.getenv('NEURASIGN_WEB_URL', 'http://localhost:3000')
API = os.getenv('NEURASIGN_API_URL', 'http://localhost:8000')


async def main(require_live=False):
    artifacts = ROOT/'artifacts'
    artifacts.mkdir(exist_ok=True)
    errors = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='chrome', headless=True, args=['--no-sandbox'])
        page = await browser.new_page(viewport={'width':1440, 'height':900})
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.request.post(API+'/api/control', data={'action':'reset'})
        await page.goto(WEB+'/demo', wait_until='domcontentloaded')
        await expect(page.get_by_test_id('monitoring-dashboard')).to_be_visible(timeout=30000)
        await page.locator('.monitor-examples-nav > summary').click()
        await page.get_by_test_id('tab-incidents').click()
        await expect(page.get_by_test_id('start-incident')).to_be_enabled(timeout=10000)
        start_box = await page.get_by_test_id('start-incident').bounding_box()
        assert start_box and start_box['y'] + start_box['height'] <= 900, 'The first action must be visible without scrolling'
        await page.screenshot(path=str(artifacts/'incident-start.png'), full_page=True)

        async def state():
            response = await page.request.get(API+'/api/state')
            assert response.ok
            return await response.json()

        def task(snapshot, name):
            return next(t for t in snapshot['workflow']['subtasks'] if t['id'] == name)

        async def until(predicate, label, seconds=70):
            deadline = time.monotonic()+seconds
            while time.monotonic() < deadline:
                snapshot = await state()
                if predicate(snapshot):
                    return snapshot
                await asyncio.sleep(.25)
            raise AssertionError('Timed out: '+label)

        original = await state()
        await page.get_by_test_id('start-incident').click()
        snapshot = await until(lambda s: bool(s['workflow']) and bool(task(s,'diagnose')['output']) and 'evaluating' not in s['provider']['status'].lower(), 'real diagnosis draft')
        assert snapshot['source']['kind'] == original['source']['kind'] == 'universe'
        assert not snapshot['demo_running'], 'The ordinary example must preserve real monitoring'
        assert task(snapshot,'diagnose')['status'] == 'active'
        if require_live:
            assert task(snapshot,'diagnose')['assignment']['provider'] == 'jev'
        await page.get_by_test_id('workflow-step-diagnose').click()
        await expect(page.get_by_test_id('output-dialog')).to_be_visible()
        await expect(page.get_by_test_id('evidence-result')).not_to_be_empty()
        await page.screenshot(path=str(artifacts/'incident-real-diagnosis.png'), full_page=True)
        await page.keyboard.press('Escape')
        await expect(page.get_by_test_id('complete-diagnosis')).to_be_enabled(timeout=30000)
        await page.get_by_test_id('complete-diagnosis').click()
        await expect(page.get_by_test_id('approve-decision')).to_be_enabled(timeout=30000)
        await page.evaluate('window.scrollTo(0, 0)')
        approval_box = await page.get_by_test_id('approve-decision').bounding_box()
        assert approval_box and approval_box['y'] + approval_box['height'] <= 900, 'Human approval must be visible without scrolling'
        waiting = await state()
        cursor = waiting['monitoring']['signal_seconds']
        await asyncio.sleep(1.4)
        waiting = await state()
        assert task(waiting,'decide')['status'] == 'active'
        assert waiting['monitoring']['signal_seconds'] > cursor, 'Monitoring must continue during human approval'
        await page.screenshot(path=str(artifacts/'incident-human-approval.png'), full_page=True)
        await page.set_viewport_size({'width':390, 'height':844})
        await page.screenshot(path=str(artifacts/'incident-mobile.png'), full_page=True)
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), 'Incident view overflows mobile'
        await page.set_viewport_size({'width':1440, 'height':900})
        await page.get_by_test_id('approve-decision').click()
        snapshot = await until(lambda s: s['workflow']['status'] == 'resolved', 'verification and report')
        providers = {t['id']:t['execution']['provider'] for t in snapshot['workflow']['subtasks']}
        assert providers['decide'] == 'human'
        if require_live:
            assert all(providers[t]=='gemini' for t in ('gather','diagnose','verify','document')),providers
        assert snapshot['source']['kind'] == 'universe' and snapshot['playing']
        await page.screenshot(path=str(artifacts/'incident-resolved.png'), full_page=True)
        await page.get_by_test_id('workflow-step-document').click()
        await expect(page.get_by_role('dialog')).to_be_visible()
        await expect(page.get_by_role('dialog')).to_contain_text('Gemini' if providers['document']=='gemini' else 'fallback')
        await page.keyboard.press('Escape')
        await page.get_by_test_id('tab-monitoring').click()
        await expect(page.get_by_test_id('monitoring-dashboard')).to_be_visible()
        assert not errors,json.dumps(errors)
        await page.request.post(API+'/api/control', data={'action':'reset'})
        await browser.close()
    print('PASS: secondary incident preserves recorded monitoring; actual review/approval, independent signal playback and model artifacts '+json.dumps(providers),flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-live',action='store_true')
    asyncio.run(main(parser.parse_args().require_live))
