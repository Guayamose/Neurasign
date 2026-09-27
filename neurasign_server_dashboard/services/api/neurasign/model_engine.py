"""Local anonymous model execution, isolated from company and employee data."""

import hmac
import os
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from .identity import production


def model_engine_access(request: Request, x_model_engine_token: str | None = Header(None)):
    if production() or os.getenv('MODEL_ENGINE_ENABLED', 'false').lower() != 'true':
        raise HTTPException(404, 'Model engine is disabled.')
    expected = os.getenv('MODEL_ENGINE_TOKEN')
    if expected:
        if not x_model_engine_token or not hmac.compare_digest(expected, x_model_engine_token):
            raise HTTPException(403, 'Model engine access is restricted to the local dashboard.')
    elif request.client is None or request.client.host not in {'127.0.0.1', '::1', 'localhost', 'testclient'}:
        raise HTTPException(403, 'Configure a server-side model engine token for proxy access.')
    if request.query_params:
        raise HTTPException(422, 'This interface accepts recorded research examples only, without query parameters.')


router = APIRouter(prefix='/api/model-engine', tags=['Anonymous model research'],
                   dependencies=[Depends(model_engine_access)])
ModelId = Literal['stress', 'readiness', 'fatigue', 'workload']


class RecordedPrediction(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    record_id: str = Field(min_length=1, max_length=96, pattern=r'^[A-Za-z0-9_-]+$')


async def runtime_request(method: str, path: str, body: dict | None = None):
    """Forward only server-constructed paths and the validated recorded-example ID."""
    base = os.getenv('MODEL_ENGINE_URL', 'http://127.0.0.1:8010').rstrip('/')
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30., connect=3.), trust_env=False) as client:
            response = await client.request(method, f'{base}{path}', json=body)
    except httpx.HTTPError:
        raise HTTPException(503, 'Model service is unavailable. Start the model service and prepare its verified bundle.') from None
    if response.status_code != 200:
        messages = {
            404: 'Unknown recorded example or model.',
            422: 'This recorded example does not satisfy the model input contract.',
            503: 'The verified model bundle is unavailable. No formula was used as a substitute.',
        }
        status = response.status_code if response.status_code in messages else 503
        raise HTTPException(status, messages[status])
    try:
        payload = response.json()
    except ValueError:
        raise HTTPException(503, 'The model service returned an invalid response.') from None
    if not isinstance(payload, dict):
        raise HTTPException(503, 'The model service returned an invalid response.')
    return payload


@router.get('/health')
async def health():
    return await runtime_request('GET', '/health')


@router.get('/catalog')
async def catalog():
    return await runtime_request('GET', '/catalog')


@router.get('/models/{model_id}/records')
async def records(model_id: ModelId):
    return await runtime_request('GET', f'/models/{model_id}/records')


@router.post('/models/{model_id}/predict')
async def predict(model_id: ModelId, command: RecordedPrediction):
    return await runtime_request('POST', f'/models/{model_id}/predict', command.model_dump())
