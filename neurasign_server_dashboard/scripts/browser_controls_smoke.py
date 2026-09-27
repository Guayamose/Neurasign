"""Exercise monitoring playback, source controls and local use-case drafts."""
import asyncio
import json
import os
from datetime import datetime, timezone
from urllib.parse import unquote
from playwright.async_api import async_playwright, expect

WEB = os.getenv('NEURASIGN_WEB_URL', 'http://localhost:3000')
API = os.getenv('NEURASIGN_API_URL', 'http://localhost:8000')


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='chrome', headless=True, args=['--no-sandbox'])
        page = await browser.new_page(viewport={'width':1440,'height':1000})
        errors=[]
        page.on('pageerror',lambda error: errors.append(str(error)))
        await page.request.post(API+'/api/control',data={'action':'reset'})
        await page.goto(WEB+'/demo',wait_until='domcontentloaded')
        await expect(page.get_by_test_id('monitoring-play')).to_be_enabled(timeout=30000)

        async def state():
            return await (await page.request.get(API+'/api/state')).json()

        await page.get_by_test_id('monitoring-play').click()
        paused = await state()
        assert not paused['playing']
        await expect(page.get_by_test_id('monitoring-play')).to_contain_text('Resume recording')
        await page.get_by_test_id('tab-examples').click()
        await page.get_by_test_id('tab-focus').click()
        await page.get_by_test_id('tab-monitoring').click()
        await asyncio.sleep(1.1)
        assert (await state())['monitoring']['signal_seconds'] == paused['monitoring']['signal_seconds']
        await page.get_by_test_id('metric-temperature').click()
        await expect(page.get_by_test_id('metric-temperature')).to_have_attribute('aria-pressed','true')
        await page.get_by_test_id('presenter-controls').locator('summary').click()
        await page.get_by_test_id('monitoring-source').select_option('manual')
        await expect(page.get_by_test_id('demo-source-context')).to_contain_text('manual', ignore_case=True)
        slider=page.locator('#monitor-aoi-readiness')
        await expect(slider).to_be_visible()
        await slider.focus()
        await slider.press('End')
        await slider.press('ArrowLeft')
        await asyncio.sleep(.4)
        manual=await state()
        assert manual['mode']=='manual'
        assert next(worker for worker in manual['workers'] if worker['id']=='aoi')['cognitive_state']['readiness']==99
        assert all(value is None for worker in manual['monitoring']['workers'] for value in worker['features'].values())
        for tab, action in [('wellbeing','Draft suggestion'),('focus','Draft agenda')]:
            await page.get_by_test_id('tab-examples').click()
            await page.get_by_test_id('tab-'+tab).click()
            await page.get_by_role('button',name=action,exact=True).first.click()
            await expect(page.get_by_text('Draft ready · not sent',exact=True)).to_be_visible()
            await expect(page.get_by_test_id('demo-source-context')).to_contain_text('manual', ignore_case=True)
            await expect(page.get_by_role('link',name='Download draft',exact=True)).to_have_attribute('download')
            draft = unquote(await page.get_by_role('link',name='Download draft',exact=True).get_attribute('href'))
            assert 'Local example draft.' in draft and 'Relative readiness:' in draft
            assert all(word not in draft.lower() for word in ('borrador', 'sugerencia', 'preparado', 'reuniones'))
            current=await state()
            assert current['workflow'] is None and current['mode']=='manual'
        await page.get_by_test_id('tab-monitoring').click()
        await page.get_by_test_id('presenter-controls').locator('summary').click()
        await page.get_by_test_id('monitoring-source').select_option('live')
        await expect(page.get_by_test_id('demo-source-context')).to_contain_text('device', ignore_case=True)
        live=await state()
        assert all(worker['status']=='waiting' for worker in live['monitoring']['workers'])
        await expect(page.get_by_test_id('monitoring-dashboard')).to_contain_text('Waiting for data')
        payload={'worker_id':'aoi','timestamp':datetime.now(timezone.utc).isoformat(),'ppg':{'heart_rate':75},'quality':.9}
        response=await page.request.post(API+'/api/live/readings',data=payload)
        assert response.ok
        await page.get_by_test_id('select-person-aoi').click()
        await page.get_by_test_id('metric-heart_rate').click()
        await expect(page.get_by_test_id('selected-physiology-chart')).to_contain_text('75')
        await page.get_by_role('button',name='Restart demo',exact=True).click()
        await expect(page.get_by_test_id('demo-source-context')).to_contain_text('UNIVERSE')
        current=await state()
        assert current['source']['kind']=='universe' and current['playing'] and current['workflow'] is None
        assert not errors,json.dumps(errors)
        await browser.close()
    print('PASS: pause survives navigation; physical metrics and manual indices; local case drafts; live partial readings/insufficient signal; restart restores recorded monitoring.',flush=True)


if __name__=='__main__':
    asyncio.run(main())
