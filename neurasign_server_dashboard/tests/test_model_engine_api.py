import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from neurasign import model_engine


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('NEURASIGN_ENV', 'local')
    monkeypatch.delenv('K_SERVICE', raising=False)
    monkeypatch.setenv('MODEL_ENGINE_ENABLED', 'true')
    monkeypatch.delenv('MODEL_ENGINE_TOKEN', raising=False)
    app = FastAPI()
    app.include_router(model_engine.router)
    return TestClient(app)


def test_research_catalog_is_opt_in_and_never_available_in_production(client, monkeypatch):
    monkeypatch.setenv('MODEL_ENGINE_ENABLED', 'false')
    assert client.get('/api/model-engine/catalog').status_code == 404
    monkeypatch.setenv('MODEL_ENGINE_ENABLED', 'true')
    monkeypatch.setenv('NEURASIGN_ENV', 'production')
    assert client.get('/api/model-engine/catalog').status_code == 404
    monkeypatch.setenv('NEURASIGN_ENV', 'local')
    monkeypatch.setenv('K_SERVICE', 'cloud-run-service')
    assert client.get('/api/model-engine/catalog').status_code == 404


def test_token_and_anonymous_record_contract(client, monkeypatch):
    calls = []

    async def runtime(method, path, body=None):
        calls.append((method, path, body))
        return {'scope': 'anonymous_research', 'production_enabled': False}

    monkeypatch.setattr(model_engine, 'runtime_request', runtime)
    monkeypatch.setenv('MODEL_ENGINE_TOKEN', 'private-unit-test-token')
    assert client.get('/api/model-engine/catalog').status_code == 403
    headers = {'X-Model-Engine-Token': 'private-unit-test-token'}
    assert client.get('/api/model-engine/catalog', headers=headers).status_code == 200
    response = client.post('/api/model-engine/models/stress/predict', json={'record_id': 'stress-001'}, headers=headers)
    assert response.status_code == 200
    assert calls[-1] == ('POST', '/models/stress/predict', {'record_id': 'stress-001'})
    assert 'private-unit-test-token' not in response.text
    before = len(calls)
    for field, value in [('worker_id', 'alex'), ('organization_id', 'company'), ('features', {'hr': 80}),
                         ('artifact_path', '/tmp/model.joblib'), ('confidence', .9)]:
        assert client.post('/api/model-engine/models/stress/predict',
                           json={'record_id': 'stress-001', field: value}, headers=headers).status_code == 422
    for record in ['../model', '', 'a' * 97, 123, 'model?worker_id=alex']:
        assert client.post('/api/model-engine/models/stress/predict', json={'record_id': record}, headers=headers).status_code == 422
    assert client.get('/api/model-engine/catalog?worker_id=alex', headers=headers).status_code == 422
    assert client.get('/api/model-engine/models/unknown/records', headers=headers).status_code == 422
    assert len(calls) == before


def test_nonlocal_access_requires_server_token(client, monkeypatch):
    remote = TestClient(client.app, client=('198.51.100.1', 50000))
    assert remote.get('/api/model-engine/catalog').status_code == 403


@pytest.mark.asyncio
async def test_runtime_failure_is_unavailable_without_heuristic_fallback(monkeypatch):
    class FailedClient:
        def __init__(self, **kwargs):
            assert kwargs['trust_env'] is False
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def request(self, *args, **kwargs):
            raise httpx.ConnectError('private upstream address must not leak')
    monkeypatch.setattr(model_engine.httpx, 'AsyncClient', FailedClient)
    with pytest.raises(model_engine.HTTPException) as error:
        await model_engine.runtime_request('GET', '/catalog')
    assert error.value.status_code == 503
    assert 'private upstream address' not in error.value.detail


@pytest.mark.asyncio
@pytest.mark.parametrize('status,body,expected', [(503, {'detail': '/secret/path'}, 503), (404, {}, 404),
                                                (200, ['invalid'], 503), (200, {'models': []}, 200)])
async def test_runtime_response_contract(monkeypatch, status, body, expected):
    class FakeClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def request(self, method, url, json):
            assert url.endswith('/catalog') and method == 'GET' and json is None
            return httpx.Response(status, json=body)
    monkeypatch.setattr(model_engine.httpx, 'AsyncClient', FakeClient)
    if expected == 200:
        assert await model_engine.runtime_request('GET', '/catalog') == body
    else:
        with pytest.raises(model_engine.HTTPException) as error:
            await model_engine.runtime_request('GET', '/catalog')
        assert error.value.status_code == expected
        assert '/secret/path' not in error.value.detail


def test_main_middleware_preserves_valid_record_body(client, monkeypatch):
    from neurasign.main import app

    async def runtime(method, path, body=None):
        assert body == {'record_id': 'stress-0001'}
        return {'scope': 'anonymous_research'}

    monkeypatch.setattr(model_engine, 'runtime_request', runtime)
    response = TestClient(app).post('/api/model-engine/models/stress/predict', json={'record_id': 'stress-0001'})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_main_rejects_streamed_body_before_reading_remaining_chunks(client):
    from neurasign.main import app
    reads = 0
    sent = []

    async def receive():
        nonlocal reads
        reads += 1
        assert reads <= 3, 'Middleware kept consuming an oversized body'
        return {'type': 'http.request', 'body': b'x' * 1024, 'more_body': True}

    async def send(message):
        sent.append(message)

    scope = {'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.4'},
             'http_version': '1.1', 'method': 'POST', 'scheme': 'http',
             'path': '/api/model-engine/models/stress/predict',
             'raw_path': b'/api/model-engine/models/stress/predict', 'query_string': b'',
             'root_path': '', 'headers': [(b'content-type', b'application/json')],
             'client': ('127.0.0.1', 50000), 'server': ('testserver', 80)}
    await app(scope, receive, send)
    assert reads == 3
    assert next(message['status'] for message in sent if message['type'] == 'http.response.start') == 413
