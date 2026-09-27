"""Run the built images with production boundaries, locally and without cloud auth.

The web shares the API container's network namespace, as Cloud Run sidecars do.
Only the web port is published. Uses placeholder public Firebase config; does not
verify real cloud authentication or database connectivity.
"""
import json
import subprocess
import time
from uuid import uuid4

import httpx


def docker(*args):
    return subprocess.run(['docker', *args], check=True, capture_output=True, text=True).stdout.strip()


def main():
    suffix = uuid4().hex[:8]
    api, web = f'neurasign-check-api-{suffix}', f'neurasign-check-web-{suffix}'
    try:
        docker('run', '-d', '--name', api, '-p', '127.0.0.1::8080',
               '-e', 'NEURASIGN_ENV=production', '-e', 'WORKSPACE_STORE=firestore',
               '-e', 'FIREBASE_PROJECT_ID=neurasign-offline-test', '-e', 'FIREBASE_WEB_API_KEY=public-offline-test-key', 'neurasign-api')
        docker('run', '-d', '--name', web, '--network', f'container:{api}',
               '-e', 'NEURASIGN_ENV=production', '-e', 'PORT=8080',
               '-e', 'API_INTERNAL_URL=http://127.0.0.1:8000', 'neurasign-web')
        port = json.loads(docker('inspect', api))[0]['NetworkSettings']['Ports']['8080/tcp'][0]['HostPort']
        base = f'http://127.0.0.1:{port}'
        for _ in range(60):
            try:
                if httpx.get(base + '/api/v1/config', timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(.5)
        config = httpx.get(base + '/api/v1/config').json()
        assert config['enabled'] and not config['demo_available'] and not config['emulator_url']
        for path, expected in [('/', 200), ('/api/v1/me', 401), ('/demo', 404), ('/signals', 404), ('/models', 404), ('/api/model-engine/catalog', 404), ('/api/state', 404), ('/docs', 404)]:
            response = httpx.get(base + path, timeout=10)
            assert response.status_code == expected, (path, response.status_code)
        response = httpx.post(base + '/api/v1/readings', content='x' * 131073)
        assert response.status_code == 413
        response = httpx.post(base + '/api/v1/readings', content=iter([b'x' * 65536] * 3))
        assert response.status_code == 413, 'Chunked uploads must also be bounded.'
        assert docker('exec', api, 'id', '-u') != '0'
        assert docker('exec', web, 'id', '-u') != '0'
        print('PASS: production images, shared sidecar network, runtime port 8080, same-origin API, protected data, body limit, disabled demo and non-root users. No cloud account or external identity/database request used.')
    finally:
        for name in (web, api):
            subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == '__main__':
    main()
