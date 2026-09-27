"""Capture real, read-only NEURASIGN demo states for the film.

The initial /api/state response is kept intact and replayed in the browser.
This freezes time for the camera; no physiological or interpretation values
are invented, and all application writes are blocked.
"""
import asyncio
import hashlib
import json
import re
import struct
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

from playwright.async_api import async_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'public' / 'capture'
WEB = 'http://localhost:3000'
API = 'http://localhost:8000'

async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with urlopen(API + '/api/state') as response:
        snapshot = json.load(response)
    if snapshot['mode'] != 'replay' or snapshot['source']['kind'] != 'universe':
        raise RuntimeError('Capture requires the existing real UNIVERSE replay. No automatic server mutation is permitted.')
    (OUT / 'recorded-snapshot.json').write_text(json.dumps(snapshot, indent=2))
    manifest = {
        'captured_at': datetime.now(timezone.utc).isoformat(),
        'source': snapshot['source'],
        'snapshot_sha256': hashlib.sha256((OUT / 'recorded-snapshot.json').read_bytes()).hexdigest(),
        'viewport': {'width': 2560, 'height': 1440},
        'assets': [],
        'application_writes': [],
        'browser_errors': [],
    }
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='chrome', headless=True, args=['--no-sandbox'])
        context = await browser.new_context(viewport=manifest['viewport'], device_scale_factor=1, reduced_motion='reduce', color_scheme='dark')
        page = await context.new_page()
        page.on('pageerror', lambda e: manifest['browser_errors'].append(str(e)))
        async def intercept(route):
            request = route.request
            if request.method not in ('GET', 'HEAD', 'OPTIONS'):
                manifest['application_writes'].append({'method': request.method, 'url': request.url})
                await route.abort()
            elif '/api/state' in request.url:
                await route.fulfill(json=snapshot, headers={'access-control-allow-origin': '*'})
            else:
                await route.continue_()
        async def websocket(socket):
            socket.send(json.dumps({'type': 'snapshot', 'data': snapshot}))
        await page.route('**/*', intercept)
        await page.route_web_socket(re.compile(r'/ws(?:\?|$)'), websocket)

        async def photograph(name, locator=None):
            await page.mouse.move(0, 0)
            await page.evaluate('document.activeElement?.blur()')
            await page.evaluate('document.fonts.ready')
            await page.wait_for_timeout(350)
            path = OUT / name
            if locator:
                bounds = await locator.bounding_box()
                await locator.screenshot(path=str(path), animations='disabled', caret='hide')
                manifest['assets'].append({'file': name, 'crop_in_css_pixels': bounds})
            else:
                await page.screenshot(path=str(path), animations='disabled', caret='hide')
                manifest['assets'].append({'file': name, 'width': 2560, 'height': 1440})

        await page.goto(WEB + '/demo#manager', wait_until='networkidle')
        await expect(page.get_by_test_id('manager-person-alex')).to_be_visible()
        await expect(page.get_by_test_id('demo-source-context')).to_contain_text('UNIVERSE recordings')
        await photograph('manager-overview-2560.png')
        await photograph('manager-overview-panel.png', page.get_by_test_id('manager-overview'))
        await photograph('source-context.png', page.get_by_test_id('demo-source-context'))

        await page.get_by_test_id('tab-monitoring').click()
        await expect(page.get_by_test_id('selected-physiology-chart')).to_be_visible()
        await photograph('team-signals-2560.png')
        await photograph('team-rows.png', page.locator('.demo-people-list'))
        await photograph('alex-heart-rate-panel.png', page.get_by_test_id('selected-physiology-chart'))
        await page.get_by_test_id('select-person-aoi').click()
        await page.get_by_test_id('metric-hrv').click()
        await photograph('sam-hrv-2560.png')
        await photograph('sam-hrv-panel.png', page.get_by_test_id('selected-physiology-chart'))

        await page.get_by_test_id('tab-manager').click()
        await page.get_by_role('button', name='View details for Alex', exact=True).click()
        await photograph('manager-detail-2560.png')
        await photograph('manager-detail-panel.png', page.get_by_test_id('manager-detail'))
        await context.close()
        # Retina components remain legible when composited onto a large screen.
        context = await browser.new_context(viewport=manifest['viewport'], device_scale_factor=2, reduced_motion='reduce', color_scheme='dark')
        page = await context.new_page()
        page.on('pageerror', lambda e: manifest['browser_errors'].append(str(e)))
        await page.route('**/*', intercept)
        await page.route_web_socket(re.compile(r'/ws(?:\?|$)'), websocket)
        await page.goto(WEB + '/demo#manager', wait_until='networkidle')
        await expect(page.get_by_test_id('manager-person-alex')).to_be_visible()
        await photograph('manager-overview-panel@2x.png', page.get_by_test_id('manager-overview'))
        await photograph('source-context@2x.png', page.get_by_test_id('demo-source-context'))
        await page.get_by_test_id('tab-monitoring').click()
        await photograph('team-rows@2x.png', page.locator('.demo-people-list'))
        await photograph('alex-heart-rate-panel@2x.png', page.get_by_test_id('selected-physiology-chart'))
        await page.get_by_test_id('select-person-aoi').click()
        await page.get_by_test_id('metric-hrv').click()
        await photograph('sam-hrv-panel@2x.png', page.get_by_test_id('selected-physiology-chart'))
        await context.close()
        await browser.close()
    if manifest['browser_errors'] or manifest['application_writes']:
        raise AssertionError(manifest)
    for asset in manifest['assets']:
        with (OUT / asset['file']).open('rb') as stream:
            stream.seek(16)
            asset['pixel_width'], asset['pixel_height'] = struct.unpack('>II', stream.read(8))
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))

if __name__ == '__main__':
    asyncio.run(main())
