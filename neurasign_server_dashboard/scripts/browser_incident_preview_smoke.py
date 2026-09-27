"""Browser-only incident state fixtures; no workflow request reaches the API."""
import asyncio
import copy
import json
import os
from pathlib import Path
from urllib.request import urlopen

from playwright.async_api import async_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / 'var' / 'demo-incident-review'
WEB = os.getenv('NEURASIGN_WEB_URL', 'http://localhost:3000').rstrip('/')
API = os.getenv('NEURASIGN_API_URL', 'http://localhost:8000').rstrip('/')
BASE = json.load(urlopen(API + '/api/state', timeout=15))


def fixture(phase):
    snapshot = copy.deepcopy(BASE)
    snapshot['revision'] = BASE['revision'] + 100000 + phase
    snapshot['provider']['status'] = 'Fixture ready'
    snapshot['playing'] = False
    if phase == 0:
        snapshot['workflow'] = None
        return snapshot
    tasks = []
    for index, task_id in enumerate(('gather', 'diagnose', 'decide', 'verify', 'document')):
        completed = phase == 3 or index < (1 if phase == 1 else 2)
        active = (phase == 1 and index == 1) or (phase == 2 and index == 2)
        has_output = completed or phase == 1 and task_id == 'diagnose'
        human = task_id == 'decide'
        tasks.append({
            'id': task_id, 'title': task_id, 'description': 'Browser fixture',
            'required_skills': {}, 'complexity': 0, 'risk': 0, 'urgency': 0,
            'human_judgment_requirement': 1 if human else 0,
            'ai_suitability': 0 if human else 1, 'estimated_duration': 1,
            'dependencies': [],
            'status': 'completed' if completed else 'active' if active else 'pending',
            'assignment': {
                'provider': 'deterministic', 'kind': 'HUMAN' if human else 'HUMAN_AI' if task_id == 'diagnose' else 'AI',
                'worker_id': snapshot['workers'][0]['id'] if human or task_id == 'diagnose' else None,
                'label': 'Browser fixture', 'score': 1, 'confidence': 1,
                'explanation': {'summary': 'Browser fixture', 'factors': []},
                'previous_label': None, 'changed_at': None,
            },
            'output': ('# Sample incident report\nBrowser fixture: sample recovery checks complete.' if task_id == 'document' else '# Sample findings\nBrowser fixture: checkout requests exceeded the timeout.') if has_output else None,
            'execution': {
                'provider': 'human' if human else 'local_fallback',
                'status': 'completed' if has_output else 'idle',
                'model': None, 'error': None, 'latency_ms': None,
            },
        })
    snapshot['workflow'] = {
        'id': 'browser-only-fixture', 'title': 'Sample checkout outage',
        'description': 'No provider request is made', 'urgency': 0, 'risk': 0,
        'complexity': 0, 'required_skills': {}, 'estimated_duration': 0,
        'human_judgment_requirement': 1,
        'status': 'resolved' if phase == 3 else 'active',
        'revision': phase, 'subtasks': tasks,
    }
    return snapshot


async def main():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    phase = 0
    writes = []
    errors = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='chrome', headless=True, args=['--no-sandbox'])
        page = await browser.new_page(viewport={'width': 1440, 'height': 900})
        page.on('pageerror', lambda error: errors.append(str(error)))

        async def api_route(route):
            nonlocal phase
            request = route.request
            if request.method == 'OPTIONS':
                await route.fulfill(status=204, headers={'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'GET,POST,OPTIONS', 'Access-Control-Allow-Headers': 'content-type'})
                return
            if request.url.endswith('/api/control'):
                assert request.method == 'POST'
                action = request.post_data_json
                writes.append(action)
                expected = ('trigger_incident', 'complete_diagnosis', 'approve_decision')[phase]
                assert action == {'action': expected}, action
                phase += 1
            else:
                assert request.url.endswith('/api/state') and request.method == 'GET', request.url
            await route.fulfill(json=fixture(phase), headers={'Access-Control-Allow-Origin': '*'})

        # Intercept every API path so an unexpected write cannot reach the server.
        await page.route('**/api/**', api_route)
        await page.route_web_socket('**/ws', lambda socket: socket.send(json.dumps({'type': 'snapshot', 'data': fixture(phase)})))
        await page.goto(WEB + '/signals', wait_until='domcontentloaded')
        await page.get_by_test_id('tab-examples').click()
        await page.get_by_test_id('tab-incidents').click()
        await expect(page.get_by_test_id('start-incident')).to_have_text('Start example')
        await expect(page.locator('.ic-step-details')).not_to_have_attribute('open', '')
        await expect(page.locator('.ic-how-it-works')).not_to_have_attribute('open', '')
        await expect(page.locator('.ic-primary:visible')).to_have_count(1)
        assert not writes
        start_box = await page.get_by_test_id('start-incident').bounding_box()
        assert start_box and start_box['y'] + start_box['height'] <= 900, 'Start action must be visible without scrolling'
        await page.screenshot(path=str(ARTIFACTS / 'initial-desktop.png'), full_page=True)
        await page.get_by_test_id('start-incident').click()
        await expect(page.get_by_test_id('complete-diagnosis')).to_be_enabled()
        await expect(page.get_by_test_id('approve-decision')).to_have_count(0)
        await page.get_by_role('button', name='Read findings', exact=True).click()
        await expect(page.get_by_test_id('output-dialog')).to_be_visible()
        await expect(page.get_by_test_id('output-dialog')).to_contain_text('Local fallback')
        await expect(page.get_by_test_id('evidence-result')).to_contain_text('Browser fixture')
        await page.keyboard.press('Escape')
        await expect(page.get_by_role('button', name='Read findings', exact=True)).to_be_focused()
        await page.get_by_test_id('complete-diagnosis').click()
        await expect(page.get_by_test_id('approve-decision')).to_be_enabled()
        assert len(writes) == 2
        await page.screenshot(path=str(ARTIFACTS / 'approval-desktop.png'), full_page=True)
        await page.set_viewport_size({'width': 390, 'height': 844})
        await page.screenshot(path=str(ARTIFACTS / 'approval-mobile.png'), full_page=True)
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        await expect(page.locator('.ic-progress [aria-current="step"]')).to_contain_text('Approve')
        await page.get_by_test_id('approve-decision').click()
        await expect(page.get_by_role('button', name='Read incident report', exact=True)).to_be_visible()
        await expect(page.locator('.ic-progress .is-complete')).to_have_count(3)
        await page.get_by_role('button', name='Read incident report', exact=True).click()
        await expect(page.get_by_test_id('evidence-result')).to_contain_text('sample recovery checks complete')
        await page.keyboard.press('Escape')
        await page.locator('.ic-step-details > summary').click()
        await page.get_by_test_id('workflow-step-document').click()
        await expect(page.get_by_test_id('output-dialog')).to_be_visible()
        await page.keyboard.press('Escape')
        await expect(page.get_by_test_id('workflow-step-document')).to_be_focused()
        assert len(writes) == 3 and not errors, (writes, errors)
        await browser.close()
    print('PASS: initial, review, approval, report; disclosures, result provenance, keyboard focus, mobile overflow. Three intercepted fixture controls; zero workflow requests reached backend.')


asyncio.run(main())
