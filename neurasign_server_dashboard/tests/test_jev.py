import json

import httpx
import pytest

from neurasign.jev import JevRoutingProvider


@pytest.mark.asyncio
async def test_jev_validated_choice_and_private_payload(monkeypatch):
    monkeypatch.setenv("JEV_API_key", "test-placeholder")
    def respond(request):
        body = json.loads(request.content)
        assert "ppg" not in json.dumps(body)
        assert "secret-note" not in json.dumps(body)
        assert request.headers["Authorization"] == "Bearer test-placeholder"
        return httpx.Response(200, json={"answers": {"assignment": {"choice": "option_0", "confidence": .8}}})
    provider = JevRoutingProvider(httpx.MockTransport(respond))
    candidate = {"kind": "AI", "label": "AI Agent", "score": .9, "explanation": {"summary": "Routine task", "factors": []}}
    chosen = await provider.choose_assignment({"title": "Gather logs"}, [{"id": "alex", "ppg": {}, "name": "secret-note"}], [candidate])
    assert chosen["kind"] == "AI"
    assert chosen["confidence"] == .8
    assert candidate["explanation"]["summary"] == "Routine task"


@pytest.mark.asyncio
@pytest.mark.parametrize("answer", [{"choice": "unapproved", "confidence": .9}, {"choice": "option_0", "confidence": .1}, {"choice": "option_0", "confidence": float("nan")}])
async def test_jev_rejects_invalid_or_uncertain_choice(monkeypatch, answer):
    monkeypatch.setenv("JEV_API_key", "test-placeholder")
    provider = JevRoutingProvider(httpx.MockTransport(lambda _: httpx.Response(200, content=json.dumps({"answers": {"assignment": answer}}))))
    assert await provider.choose_assignment({}, [], [{"kind": "AI"}]) is None


@pytest.mark.asyncio
async def test_failure_falls_back_with_circuit_breaker(monkeypatch):
    monkeypatch.setenv("JEV_API_key", "test-placeholder")
    calls = []
    def fail(request):
        calls.append(1)
        return httpx.Response(503)
    provider = JevRoutingProvider(httpx.MockTransport(fail))
    assert await provider.choose_assignment({}, [], [{"kind": "AI"}]) is None
    assert await provider.choose_assignment({}, [], [{"kind": "AI"}]) is None
    assert len(calls) == 1
    assert "fallback" in provider.status
