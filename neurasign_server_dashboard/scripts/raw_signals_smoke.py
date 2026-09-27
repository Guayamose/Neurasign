"""Real UNIVERSE samples through the gateway/API/history/browser; local recording only."""
import asyncio
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

from playwright.async_api import async_playwright, expect

from preprocess_universe import read_regular, read_ibi
from workspace_smoke import WEB, call, test_user

ROOT = Path(__file__).resolve().parents[1]
PHONE = ROOT.parent / 'neurasign_phone_app'
RAW = ROOT / 'data/universe/raw/UNIVERSE/UN_101/Lab1/Raw/Empatica'


def recording():
    streams = {name: read_regular(RAW / f'{name}.csv', dimensions=3 if name == 'ACC' else 1)
               for name in ('HR', 'EDA', 'TEMP', 'ACC')}
    ibi = read_ibi(RAW / 'IBI.csv')
    # Preserve values, cadence and relative capture times. Explicitly remap the
    # historical recording to recent test time; original timestamps stay in provenance.
    start = next(stamp for stamp, value in ibi if stamp > max(item.start for item in streams.values()) + 60 and value > 0)
    end = start + 4
    anchor = time.time() - 2
    measurements = []
    for name, metric, unit, axes, scale in (
        ('HR', 'heart_rate', 'bpm', [None], 1),
        ('EDA', 'electrodermal_conductance', 'µS', [None], 1),
        ('TEMP', 'skin_temperature', '°C', [None], 1),
        ('ACC', 'acceleration', 'g', ['x', 'y', 'z'], 1 / 64),
    ):
        signal = streams[name]
        indices = range(math.ceil((start - signal.start) * signal.rate), math.ceil((end - signal.start) * signal.rate))
        indices = list(indices)
        assert indices and indices[-1] < len(signal.samples)
        last = signal.start + indices[-1] / signal.rate
        for axis_index, axis in enumerate(axes):
            samples = [signal.samples[index][axis_index] * scale for index in indices]
            assert all(math.isfinite(value) for value in samples)
            measurements.append(dict(metric=f'{metric}_{axis}' if axis else metric, unit=unit,
                value=samples[-1], samples=samples,
                sample_offsets_ms=[(index - indices[-1]) * 1000 / signal.rate for index in indices],
                measured_at=datetime.fromtimestamp(anchor + last - end, timezone.utc).isoformat(),
                source_record_id=f'UNIVERSE:UN_101:Lab1:{name}:{last:.6f}'))
    pulses = [(stamp, value * 1000) for stamp, value in ibi if start <= stamp < end]
    assert pulses
    measurements.append(dict(metric='ppi_interval', unit='ms', value=pulses[-1][1], samples=[value for _, value in pulses],
        sample_offsets_ms=[(stamp - pulses[-1][0]) * 1000 for stamp, _ in pulses],
        measured_at=datetime.fromtimestamp(anchor + pulses[-1][0] - end, timezone.utc).isoformat(),
        source_record_id=f'UNIVERSE:UN_101:Lab1:IBI:{pulses[-1][0]:.6f}'))
    descriptor = dict(client_source_id='universe-raw-local', name='UNIVERSE · recorded E4', transport='recording',
        adapter=dict(id='universe-raw-test', version='1.0.0'), manufacturer='Empatica', model='E4 recording',
        capabilities=[dict(metric=row['metric'], unit=row['unit'], delivery_mode='stream', measurement_kind='sample',
            method='recorded-universe-remapped-time', timestamp_basis='source_record') for row in measurements])
    return dict(descriptor=descriptor, measurements=measurements)


async def main():
    config = call('GET', '/config')
    assert config['firebase']['projectId'] == 'demo-neurasign' and config['emulator_url']
    assert RAW.is_dir(), 'Download UNIVERSE first; this test never substitutes synthetic data.'
    fixture = recording()
    admin, employee = test_user('RawSignalsAdmin'), test_user('RawSignals')
    org = call('POST', '/organizations', admin['token'], {'name': 'UNIVERSE raw transport test'}, 201)['id']
    base = f'/organizations/{org}'
    # The chart session is the employee's own account; management roles do not grant measurement access.
    invitation = call('POST', base + '/invitations', admin['token'], {'email': employee['email'], 'role': 'employee'}, 201)['token']
    call('POST', '/invitations/accept', employee['token'], {'token': invitation})
    call('PATCH', base + '/me/sharing', employee['token'], {'enabled': True})
    gateway = call('POST', base + '/devices', employee['token'], {'name': 'UNIVERSE recording test', 'source': 'recording'}, 201)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json') as file:
        json.dump(fixture, file, allow_nan=False)
        file.flush()
        result = subprocess.run(['node', 'tests/raw-transport-smoke.mjs', file.name], cwd=PHONE, check=True, capture_output=True, text=True,
            env={**os.environ, 'NEURASIGN_TEST_ORIGIN': WEB, 'NEURASIGN_TEST_GATEWAY_CREDENTIAL': gateway['credential']})
        assert json.loads(result.stdout)['uploaded'] == 7
    person = call('GET', base + '/dashboard', employee['token'])['members'][0]
    redacted = call('GET', base + '/dashboard', admin['token'])['members'][0]
    assert redacted['latest'] is None and not redacted['signals'] and not redacted['measurements_access']
    assert redacted['connection']['last_received_at']
    call('GET', base + f'/members/{person["id"]}/history', admin['token'], expected=403)
    signals = {item['metric']: item for item in person['signals']}
    outsider = test_user('OutsideRaw')
    for expected in fixture['measurements']:
        signal = signals[expected['metric']]
        assert 'samples' not in signal['latest'], 'Dashboard snapshots must remain bounded.'
        path = base + f'/members/{person["id"]}/observations?series_id={signal["series_id"]}'
        rows = call('GET', path, employee['token'])['observations']
        assert len(rows) == 1, 'Retry created duplicate frames.'
        assert rows[0]['samples'] == expected['samples']
        assert rows[0]['sample_offsets_ms'] == expected['sample_offsets_ms']
        assert rows[0]['source_record_id'] == expected['source_record_id']
        call('GET', path, outsider['token'], expected=403)
        call('GET', path, admin['token'], expected=403)
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='chrome', headless=True, args=['--no-sandbox'])
        page = await browser.new_page(viewport={'width': 1440, 'height': 1000})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.goto(WEB, wait_until='domcontentloaded')
        await page.get_by_label('Work email').fill(employee['email'])
        await page.get_by_label('Password', exact=True).fill(employee['password'])
        await page.get_by_role('button', name='Sign in', exact=True).click()
        await expect(page.get_by_test_id('company-workspace')).to_be_visible(timeout=15000)
        card = page.get_by_test_id(f'company-person-{person["id"]}')
        await card.get_by_role('button', name=re.compile('View signals for')).click()
        panel = page.get_by_test_id('canonical-signals')
        await expect(panel).to_be_visible(timeout=15000)
        await expect(panel).to_contain_text('DEMO RECORDING')
        for metric, label in [('electrodermal_conductance', 'Skin conductance'), ('skin_temperature', 'Skin temperature'), ('acceleration_x', 'Acceleration · X'), ('ppi_interval', 'Pulse interval · PPI')]:
            count = len(next(row['samples'] for row in fixture['measurements'] if row['metric'] == metric))
            await panel.get_by_role('button', name=re.compile(re.escape(label))).click()
            await expect(panel.get_by_role('img')).to_have_attribute('aria-label', re.compile(re.escape(f'{label}. {count} samples.')), timeout=15000)
        await page.set_viewport_size({'width': 390, 'height': 844})
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        artifacts = ROOT / 'artifacts'
        artifacts.mkdir(exist_ok=True)
        await page.screenshot(path=str(artifacts / 'raw-signals.png'), full_page=True)
        call('PATCH', base + '/me/sharing', employee['token'], {'enabled': False})
        await expect(page.get_by_test_id('company-selected-signals').get_by_role('img')).to_have_count(0, timeout=15000)
        assert not errors, errors
        await browser.close()
    assert call('DELETE', base + '/me/readings', employee['token'])['deleted'] == 7
    call('DELETE', base + f'/devices/{gateway["device"]["id"]}', employee['token'])
    print('PASS: seven actual UNIVERSE channels, complete arrays/timing, lost-response retry, tenant isolation, Firestore history, browser curves, mobile layout and pause/deletion. Recording replay; no physical wearable claim.')


if __name__ == '__main__':
    asyncio.run(main())
