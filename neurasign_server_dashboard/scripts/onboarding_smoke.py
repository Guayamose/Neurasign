"""Browser -> single-use QR -> scoped gateway -> Firestore -> manager view.
Only local Auth/Firestore emulators; fixtures explicitly use recording source.
"""
import asyncio
import hashlib
from datetime import datetime, timezone
from pathlib import Path
import secrets
from urllib.parse import urlparse, parse_qs
from playwright.async_api import async_playwright, expect
from workspace_smoke import WEB, call, test_user

ROOT = Path(__file__).resolve().parents[1]

async def main():
    assert call('GET','/config')['firebase']['projectId'] == 'demo-neurasign'
    owner, manager, outsider = test_user('Taylor'), test_user('Jamie'), test_user('Morgan')
    org = call('POST','/organizations',owner['token'],{'name':'Phone onboarding test'},201)['id']
    base=f'/organizations/{org}'
    other_org=call('POST','/organizations',outsider['token'],{'name':'Other company'},201)['id']
    errors=[]
    artifacts=ROOT/'artifacts';artifacts.mkdir(exist_ok=True)
    async with async_playwright() as p:
        browser=await p.chromium.launch(channel='chrome',headless=True,args=['--no-sandbox'])
        page=await browser.new_page(viewport={'width':1440,'height':1000})
        page.on('pageerror',lambda e:errors.append(str(e)))
        await page.goto(WEB)
        await page.get_by_label('Work email').fill(owner['email'])
        await page.get_by_label('Password',exact=True).fill(owner['password'])
        await page.get_by_role('button',name='Sign in',exact=True).click()
        await page.get_by_role('button',name='Set up your team').click(timeout=15000)
        await page.get_by_label('New team').fill('Operations')
        await page.get_by_role('button',name='Create team',exact=True).click()
        await expect(page.get_by_role('option',name='Operations',exact=True)).to_have_count(1)
        await page.get_by_label('Employee name',exact=True).fill('Alex Morgan')
        await page.locator('select[name=team]').select_option(label='Operations')
        await page.get_by_role('button',name='Add employee',exact=True).click()
        await page.get_by_role('button',name='Connect phone',exact=True).click()
        dialog=page.get_by_role('dialog',name='Connect employee phone')
        await expect(dialog.locator('.co-qr svg')).to_be_visible()
        await dialog.get_by_text('Use a connection link',exact=True).click()
        link=await dialog.get_by_label('Phone connection link').input_value()
        params=parse_qs(urlparse(link).fragment);token=params['token'][0]
        preview=call('POST','/gateway/enrollment/preview',body={'token':token})
        assert preview['employee']=='Alex Morgan' and preview['company']=='Phone onboarding test'
        await page.screenshot(path=str(artifacts/'phone-qr-desktop.png'),full_page=True)
        await page.set_viewport_size({'width':390,'height':844})
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        await page.screenshot(path=str(artifacts/'phone-qr-mobile.png'),full_page=True)
        await page.get_by_role('button',name='Close connection code').click()
        snapshot=call('GET',base+'/dashboard',owner['token'])
        person=snapshot['members'][0];team=snapshot['teams'][0]
        assert len(snapshot['members'])==1 and len(snapshot['accounts'])==1
        # Use a separately issued recording code for automated sensor data.
        record=call('POST',base+f'/employees/{person["id"]}/enrollments',owner['token'],{'source':'recording'},201)['token']
        call('POST','/gateway/enrollment/preview',body={'token':token},expected=410)
        body={'token':record,'installation_id':secrets.token_hex(16),'claim_secret':secrets.token_urlsafe(32),'phone_name':'Recorded test gateway','consent':True}
        gateway=call('POST','/gateway/enrollment/claim',body=body)
        assert call('POST','/gateway/enrollment/claim',body=body)==gateway
        call('POST','/gateway/enrollment/claim',body={**body,'claim_secret':secrets.token_urlsafe(32)},expected=409)
        call('POST',f'/organizations/{other_org}/employees/{person["id"]}/enrollments',outsider['token'],{},404)
        invite=call('POST',base+'/invitations',owner['token'],{'email':manager['email'],'role':'manager','team_ids':[team['id']]},201)['token']
        call('POST','/invitations/accept',manager['token'],{'token':invite})
        source=call('POST','/gateway/sources',gateway['credential'],{'client_source_id':'smoke-heart-rate','name':'Recorded HRS','adapter':{'id':'test-recording','version':'1.0.0'},'transport':'recording','capabilities':[{'metric':'heart_rate','unit':'bpm','delivery_mode':'stream','measurement_kind':'sample','method':'recorded-fixture','timestamp_basis':'source_record'}]},201)['source']['id']
        row={'id':'onboard-measurement-1','source_id':source,'metric':'heart_rate','value':76,'unit':'bpm','measured_at':datetime.now(timezone.utc).isoformat()}
        assert call('POST','/observations',gateway['credential'],{'schema_version':2,'observations':[row]})['accepted']==1
        for actor in (owner, manager):
            private = call('GET',base+'/dashboard',actor['token'])['members'][0]
            assert private['signals'] == [] and private['latest'] is None and not private['measurements_access']
            assert private['connection']['status'] == 'current'
            series = hashlib.sha256(f'{source}:heart_rate'.encode()).hexdigest()
            call('GET',base+f'/members/{person["id"]}/observations?series_id={series}',actor['token'],expected=403)
        await page.get_by_test_id('company-tab-overview').click()
        card=page.get_by_test_id(f'ops-person-{person["id"]}')
        await expect(card).to_contain_text('Data received',timeout=15000)
        await card.get_by_role('button',name='View Alex Morgan',exact=True).click()
        detail=page.get_by_role('dialog',name='Alex Morgan',exact=True)
        await expect(detail).to_contain_text('Physiological measurements are protected')
        await expect(detail.locator('.data-chart, .co-chart-value')).to_have_count(0)
        await expect(card).to_contain_text('Operations')
        await page.screenshot(path=str(artifacts/'onboard-signals-mobile.png'))
        call('PATCH','/gateway/sharing',gateway['credential'],{'enabled':False})
        await expect(card).to_contain_text('Sharing paused',timeout=15000)
        await expect(detail).to_contain_text('Sharing paused')
        await expect(detail.locator('.data-chart, .co-chart-value')).to_have_count(0)
        call('POST','/observations',gateway['credential'],{'schema_version':2,'observations':[row]},403)
        call('DELETE','/gateway/connection',gateway['credential'])
        call('GET','/gateway/status',gateway['credential'],expected=401)
        assert not errors,errors
        await browser.close()
    print('PASS: browser team/employee creation, QR rendering, preview, scoped claim/recovery/reuse, cross-company isolation, manager grant, recorded telemetry receipt with protected values, dashboard refresh, pause, revocation and responsive layout.')

if __name__=='__main__': asyncio.run(main())
