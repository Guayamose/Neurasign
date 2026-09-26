"""Verify monitoring operates independently of example workflows.
Requires the locally imported UNIVERSE replay for real-data assertions.
"""
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import httpx
import websockets

BASE = os.getenv('NEURASIGN_API_URL', 'http://localhost:8000')
ROOT = Path(__file__).resolve().parents[1]
FEATURES = ('heart_rate', 'hrv', 'eda', 'temperature', 'movement')


async def main():
    async with httpx.AsyncClient(base_url=BASE, timeout=15) as client:
        async def control(**data):
            response = await client.post('/api/control', json=data)
            response.raise_for_status()
            return response.json()

        async def state():
            response = await client.get('/api/state')
            response.raise_for_status()
            return response.json()

        await control(action='reset')
        s = await control(action='pause')
        assert s['workflow'] is None
        m = s['monitoring']
        assert m['source_kind'] == 'universe'
        assert m['signal_seconds'] >= 120
        assert m['window_seconds'] == 60
        assert m['units'] == {'heart_rate':'bpm', 'hrv':'ms', 'eda':'µS', 'temperature':'°C', 'movement':'g'}
        source = json.loads((ROOT/'data/universe/replay.json').read_text())
        assert len(m['workers']) == len(s['workers']) == 2
        for worker in m['workers']:
            observed = [row for row in source['windows'] if row['worker_id'] == worker['worker_id'] and row['timestamp'] <= m['signal_seconds']]
            assert 2 <= len(worker['history']) <= 90
            assert worker['status'] == 'recorded'
            assert worker['recording']['participant']
            assert all(point['time'] <= m['signal_seconds'] for point in worker['history'])
            assert [point['time'] for point in worker['history']] == sorted(point['time'] for point in worker['history'])
            for feature in FEATURES:
                expected = observed[-1]['features'].get(feature)
                actual = worker['features'][feature]
                assert actual is None if expected is None else abs(actual - expected) < .011, (worker['worker_id'], feature)
        cursor = m['signal_seconds']
        await asyncio.sleep(1.1)
        assert (await state())['monitoring']['signal_seconds'] == cursor
        advanced = await control(action='advance', seconds=2)
        assert advanced['monitoring']['signal_seconds'] > cursor
        assert advanced['workflow'] is None
        async with websockets.connect(BASE.replace('http://','ws://').replace('https://','wss://')+'/ws') as socket:
            payload = json.loads(await asyncio.wait_for(socket.recv(),5))
            assert payload['type'] == 'snapshot' and payload['data']['monitoring']['workers']
            for private in ('JEV_API_key','Google_AI_API_key','baselines','buffers'):
                assert json.dumps(private) not in json.dumps(payload)
        print('PASS: actual UNIVERSE values/history/units, no future samples, pause/playback and monitoring WebSocket without any incident.', flush=True)

        manual = await control(mode='manual')
        assert manual['monitoring']['source_kind'] == 'manual'
        for worker in manual['monitoring']['workers']:
            assert all(worker['features'][key] is None for key in FEATURES)
            assert not worker['history']
        await control(mode='live')
        live = await state()
        assert all(worker['status'] == 'waiting' for worker in live['monitoring']['workers'])
        response = await client.post('/api/live/readings', json={'worker_id':'aoi','timestamp':datetime.now(timezone.utc).isoformat(),'ppg':{'heart_rate':75},'quality':.9})
        response.raise_for_status()
        live = response.json()
        aoi = next(worker for worker in live['monitoring']['workers'] if worker['worker_id'] == 'aoi')
        assert aoi['features']['heart_rate'] == 75
        assert aoi['features']['hrv'] is None
        assert aoi['last_sample_at']
        await control(action='reset')
        print('PASS: manual mode does not fabricate physiology, live summaries preserve missing readings and source isolation. Dashboard reset to recorded monitoring.', flush=True)


if __name__ == '__main__':
    asyncio.run(main())
