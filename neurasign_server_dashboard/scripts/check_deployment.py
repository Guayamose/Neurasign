"""Read-only checks of a deployed company service; uses no account credentials."""
import json
import sys
import urllib.error
import urllib.request


def check(base):
    if not base.startswith('https://'):
        raise ValueError('Use the public HTTPS service URL.')
    def get(path, expected):
        try:
            response = urllib.request.urlopen(base.rstrip('/') + path, timeout=30)
        except urllib.error.HTTPError as error:
            response = error
        assert response.status == expected, f'{path}: expected {expected}, received {response.status}'
        return response.read()
    config = json.loads(get('/api/v1/config', 200))
    assert config['enabled'] and not config['emulator_url'] and not config['demo_available']
    get('/api/v1/me', 401)
    get('/api/state', 404)
    for path in ('/demo', '/signals', '/models', '/api/model-engine/catalog'):
        get(path, 404)
    get('/', 200)
    print('PASS: HTTPS workspace available, unauthenticated data access rejected, emulators and legacy demo disabled.')


if __name__ == '__main__':
    check(sys.argv[1])
