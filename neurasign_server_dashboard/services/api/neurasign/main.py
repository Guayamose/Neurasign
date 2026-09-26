"""FastAPI boundary: authorized team physiology summaries and private research."""

import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import datetime
import hmac
import os
from pathlib import Path
from time import monotonic
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Read existing root credentials only on the server; never rewrite or log .env.
load_dotenv(Path(__file__).resolve().parents[3] / ".env", override=False)

from .orchestration import WorkflowOrchestrator  # noqa: E402
from .identity import production, validate_environment  # noqa: E402
from .workspace import router as workspace_router  # noqa: E402
from .telemetry import router as telemetry_router  # noqa: E402
from .onboarding import router as onboarding_router  # noqa: E402


class ControlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["play", "pause", "restart", "run_demo", "trigger_incident", "advance", "reset", "stress_aoi", "complete_diagnosis", "approve_decision"] | None = None
    speed: Literal[1, 5, 10, 30] | None = None
    mode: Literal["replay", "manual", "live"] | None = None
    provider: Literal["deterministic", "jev"] | None = None
    seconds: float = Field(10, gt=0, le=180, allow_inf_nan=False)


class ManualRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cognitive_load: float | None = Field(None, ge=0, le=100, allow_inf_nan=False)
    readiness: float | None = Field(None, ge=0, le=100, allow_inf_nan=False)
    fatigue: float | None = Field(None, ge=0, le=100, allow_inf_nan=False)
    interruption_cost: float | None = Field(None, ge=0, le=100, allow_inf_nan=False)


class PPG(BaseModel):
    model_config = ConfigDict(extra="forbid")
    heart_rate: float | None = Field(None, gt=0, le=300, allow_inf_nan=False)
    hrv: float | None = Field(None, ge=0, le=1000, allow_inf_nan=False)


class EDA(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tonic: float | None = Field(None, ge=0, le=1000, allow_inf_nan=False)


class Movement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    magnitude: float | None = Field(None, ge=0, le=1000, allow_inf_nan=False)


class LiveReading(BaseModel):
    model_config = ConfigDict(extra="forbid")
    worker_id: Literal["alex", "aoi"]
    timestamp: datetime
    ppg: PPG | None = None
    eda: EDA | None = None
    movement: Movement | None = None
    temperature: float | None = Field(None, ge=-50, le=100, allow_inf_nan=False)
    quality: float = Field(.9, ge=0, le=1, allow_inf_nan=False)

    @field_validator("timestamp")
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None:
            raise ValueError("timestamp must include a timezone")
        return value

    @model_validator(mode="after")
    def require_feature(self):
        features = [self.temperature]
        for group in (self.ppg, self.eda, self.movement):
            if group:
                features.extend(group.model_dump().values())
        if all(value is None for value in features):
            raise ValueError("Provide at least one sensor feature")
        return self


engine = WorkflowOrchestrator()
lock = engine.lock


class Connections:
    def __init__(self):
        self.clients: set[WebSocket] = set()

    async def broadcast(self, snapshot: dict):
        async def send(client):
            try:
                await asyncio.wait_for(client.send_json({"type": "snapshot", "data": snapshot}), timeout=2)
            except Exception:
                self.clients.discard(client)
        await asyncio.gather(*(send(client) for client in tuple(self.clients)))


connections = Connections()
engine.on_change = connections.broadcast


async def ticker():
    previous = monotonic()
    while True:
        await asyncio.sleep(1)
        now = monotonic()
        elapsed = min(3., now-previous)
        previous = now
        async with lock:
            await engine.tick(elapsed)
            # Even while paused, live confidence ages honestly.
            if not engine.playing and engine.mode == "live":
                engine._update_signals()
                await engine.reconsider()
                engine.touch()
            snapshot = engine.snapshot()
        await connections.broadcast(snapshot)


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_environment()
    from .local_setup import ensure_local_test_account
    await asyncio.to_thread(ensure_local_test_account)
    task = None if production() else asyncio.create_task(ticker())
    yield
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
    await engine.close()


app = FastAPI(title="NEURASIGN", version="0.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if origin.strip()],
    allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Content-Type", "Authorization", "X-Research-Token"], allow_credentials=False)
app.include_router(workspace_router)
app.include_router(telemetry_router)
app.include_router(onboarding_router)


@app.middleware('http')
async def workspace_boundary(request: Request, call_next):
    if production() and request.url.path != '/api/health' and not request.url.path.startswith('/api/v1/'):
        return JSONResponse({'detail': 'Not found.'}, status_code=404)
    if request.url.path.startswith('/api/v1/') and request.method in ('POST', 'PATCH', 'PUT'):
        try:
            length = int(request.headers.get('content-length', '0'))
        except ValueError:
            return JSONResponse({'detail': 'Invalid request length.'}, status_code=400)
        if length > 131072 or len(await request.body()) > 131072:
            return JSONResponse({'detail': 'Request body is too large.'}, status_code=413)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@app.get("/api/health")
async def health():
    if production():
        return {"status": "ok", "service": "neurasign-api", "mode": "company"}
    return {"status": "ok", "service": "neurasign-api", "version": "0.2.0", "sample_incident_inputs": True, "live_ai_configured": engine.ai.configured}


@app.get("/api/state")
async def state():
    async with lock:
        return engine.snapshot()


@app.post("/api/control")
async def control(command: ControlRequest):
    async with lock:
        if command.action in ("restart", "reset"):
            engine.reset()
        elif command.action == "run_demo":
            await engine.run_demo()
        if command.provider:
            engine.router.selected = command.provider
            engine.router.active = "deterministic"
            await engine.reconsider(force=True)
        if command.mode:
            await engine.set_mode(command.mode)
        if command.speed is not None:
            engine.speed = command.speed
        if command.action == "play":
            engine.playing = True
        elif command.action == "pause":
            engine.playing = False
        elif command.action == "trigger_incident":
            await engine.trigger_incident()
        elif command.action == "advance":
            await engine.tick(command.seconds, force=True)
        elif command.action in ("stress_aoi", "complete_diagnosis", "approve_decision"):
            try:
                await getattr(engine, command.action)()
            except ValueError as error:
                raise HTTPException(409, str(error)) from None
        engine.touch()
        snapshot = engine.snapshot()
    await connections.broadcast(snapshot)
    return snapshot


@app.patch("/api/workers/{worker_id}/state")
async def manual_state(worker_id: str, update: ManualRequest):
    if worker_id not in ("alex", "aoi"):
        raise HTTPException(404, "Unknown worker")
    values = update.model_dump(exclude_none=True)
    if not values:
        raise HTTPException(422, "Provide at least one cognitive index")
    async with lock:
        await engine.set_manual(worker_id, values)
        snapshot = engine.snapshot()
    await connections.broadcast(snapshot)
    return snapshot


@app.post("/api/live/readings")
async def live_reading(reading: LiveReading):
    async with lock:
        try:
            await engine.ingest_live(reading.model_dump(mode="json", exclude_none=True))
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        snapshot = engine.snapshot()
    await connections.broadcast(snapshot)
    return snapshot


@app.get("/api/research")
async def research(request: Request, x_research_token: str | None = Header(None)):
    if os.getenv("RESEARCH_ENABLED", "false").lower() != "true":
        raise HTTPException(404, "Research view is disabled")
    token = os.getenv("RESEARCH_TOKEN")
    local = request.client is not None and request.client.host in ("127.0.0.1", "::1", "localhost", "testclient")
    if token:
        if not x_research_token or not hmac.compare_digest(token, x_research_token):
            raise HTTPException(403, "Private research token required")
    elif not local:
        raise HTTPException(403, "Research view is local-only without a private research token")
    async with lock:
        return engine.research()


@app.websocket("/ws")
async def websocket(websocket: WebSocket):
    if production():
        await websocket.close(code=1008)
        return
    origin = websocket.headers.get("origin")
    allowed = {origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")}
    if origin and origin not in allowed:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    connections.clients.add(websocket)
    try:
        async with lock:
            await websocket.send_json({"type": "snapshot", "data": engine.snapshot()})
        while True:
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        connections.clients.discard(websocket)
