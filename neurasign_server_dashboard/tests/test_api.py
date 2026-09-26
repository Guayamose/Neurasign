import json
import asyncio
import time
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
import pytest

from neurasign.main import app, engine


class FakeGemini:
    configured = True
    status = "Test model ready"
    model = "test-model"
    completed_calls = 0
    fallback_calls = 0
    delay = .01
    async def execute_step(self, step, context):
        await asyncio.sleep(self.delay)
        return {"text": f"Mock model output for {step['id']}", "provider": "gemini", "model": self.model, "latency_ms": 1, "error": None}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ROUTING_PROVIDER", "deterministic")
    monkeypatch.setattr(engine, "ai", FakeGemini())
    with TestClient(app) as client:
        client.post("/api/control", json={"action": "reset", "provider": "deterministic"})
        yield client


def wait_state(client, predicate, timeout=2):
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        state = client.get("/api/state").json()
        if predicate(state):
            return state
        time.sleep(.01)
    raise AssertionError("State did not reach expected condition")


def test_api_full_demo_and_live_websocket_contract(client):
    assert client.get("/api/health").json()["status"] == "ok"
    with client.websocket_connect("/ws") as websocket:
        initial = websocket.receive_json()
        assert initial["type"] == "snapshot"
        assert "workers" in initial["data"]
        response = client.post("/api/control", json={"action": "run_demo"})
        assert response.status_code == 200
        update = websocket.receive_json()
        assert update["data"]["demo_running"]
        assert "heart_rate" in update["data"]["monitoring"]["workers"][0]["features"]
        assert "heart_rate" not in json.dumps(update["data"]["workers"])
        assert "normalized_features" not in json.dumps(update)
    assert client.post("/api/control", json={"action": "approve_decision"}).status_code == 409
    wait_state(client, lambda state: state["workflow"]["subtasks"][1]["execution"]["status"] == "completed")
    response = client.post("/api/control", json={"action": "stress_aoi"})
    assert response.json()["workflow"]["subtasks"][1]["assignment"]["worker_id"] == "alex"
    assert client.post("/api/control", json={"action": "complete_diagnosis"}).status_code == 200
    assert client.post("/api/control", json={"action": "approve_decision"}).status_code == 200
    state = wait_state(client, lambda state: state["workflow"]["status"] == "resolved")
    assert state["workflow"]["status"] == "resolved"
    assert state["metrics"]["reroutes"] == 1
    assert state["ai"]["completed_calls"] == 4


def test_slow_model_does_not_block_controls_and_reset_fences_outputs(client):
    engine.ai.delay = .4
    started = time.monotonic()
    response = client.post("/api/control", json={"action": "run_demo"})
    assert time.monotonic()-started < .2
    assert response.json()["workflow"]["subtasks"][0]["execution"]["status"] == "running"
    assert client.get("/api/state").status_code == 200
    assert client.post("/api/control", json={"action": "pause"}).status_code == 200
    assert client.post("/api/control", json={"action": "reset"}).status_code == 200
    time.sleep(.45)
    state = client.get("/api/state").json()
    assert state["workflow"] is None
    assert state["ai"]["completed_calls"] == 0


def test_manual_and_live_validation_and_temporal_aggregation(client):
    assert client.patch("/api/workers/missing/state", json={"readiness": 10}).status_code == 404
    assert client.patch("/api/workers/aoi/state", json={"readiness": 101}).status_code == 422
    state = client.patch("/api/workers/aoi/state", json={"readiness": 24}).json()
    assert state["mode"] == "manual"
    assert next(w for w in state["workers"] if w["id"] == "aoi")["cognitive_state"]["readiness"] == 24
    assert client.post("/api/live/readings", json={"worker_id": "aoi", "timestamp": "2026-01-01T00:00:00Z"}).status_code == 422
    assert client.post("/api/live/readings", json={"worker_id": "aoi", "timestamp": "2026-01-01T00:00:00", "ppg": {"heart_rate": 75}}).status_code == 422
    payload = {"worker_id": "aoi", "timestamp": datetime.now(timezone.utc).isoformat(), "ppg": {"heart_rate": 75}, "quality": .9}
    response = client.post("/api/live/readings", json=payload)
    assert response.status_code == 200
    assert response.json()["mode"] == "live"
    assert next(w for w in response.json()["workers"] if w["id"] == "aoi")["cognitive_state"]["confidence"] < .2
    monitoring = next(w for w in response.json()["monitoring"]["workers"] if w["worker_id"] == "aoi")
    assert monitoring["features"]["heart_rate"] == 75
    assert monitoring["status"] == "live"
    assert "normalized_features" not in response.text
    assert client.post("/api/live/readings", json=payload).status_code == 422
    assert client.post("/api/live/readings", json={**payload, "timestamp": (datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()}).status_code == 422


def test_research_gate_and_private_token(client, monkeypatch):
    monkeypatch.delenv("RESEARCH_ENABLED", raising=False)
    assert client.get("/api/research").status_code == 404
    monkeypatch.setenv("RESEARCH_ENABLED", "true")
    monkeypatch.setenv("RESEARCH_TOKEN", "local-test-token")
    assert client.get("/api/research").status_code == 403
    result = client.get("/api/research", headers={"X-Research-Token": "local-test-token"})
    assert result.status_code == 200
    assert "baseline" in result.json()["workers"]["alex"]
    assert "local-test-token" not in client.get("/api/state").text


def test_websocket_rejects_untrusted_browser_origin(client):
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws", headers={"origin": "https://untrusted.example"}):
            pass
