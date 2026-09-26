import json

import httpx
import pytest

from neurasign.gemini import GeminiExecutor, sample_evidence


@pytest.mark.asyncio
async def test_live_gemini_request_and_result_have_truthful_provenance(monkeypatch):
    monkeypatch.setenv("Google_AI_API_key", "test-google-placeholder")
    monkeypatch.setenv("GEMINI_ENABLED", "true")
    def respond(request):
        assert request.headers["x-goog-api-key"] == "test-google-placeholder"
        assert "key=" not in str(request.url)
        body = json.loads(request.content)
        prompt = body["contents"][0]["parts"][0]["text"]
        assert "heart_rate" not in prompt and "secret-worker-data" not in prompt
        assert "telemetry_after" not in prompt
        assert "connection_pool_timeout" in prompt
        return httpx.Response(200, json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "The sample evidence points to connection-pool saturation following v2.8.1."}]}}]})
    executor = GeminiExecutor(httpx.MockTransport(respond))
    result = await executor.execute_step({"id": "gather"}, {"heart_rate": 90, "workers": ["secret-worker-data"]})
    assert result["provider"] == "gemini" and result["error"] is None
    assert executor.completed_calls == 1 and executor.fallback_calls == 0


@pytest.mark.asyncio
async def test_gemini_failure_is_labeled_and_never_returns_secret(monkeypatch):
    monkeypatch.setenv("Google_AI_API_key", "test-google-placeholder")
    monkeypatch.setenv("GEMINI_ENABLED", "true")
    calls = []
    def fail(request):
        calls.append(1)
        return httpx.Response(429, text="private upstream error test-google-placeholder")
    executor = GeminiExecutor(httpx.MockTransport(fail))
    first = await executor.execute_step({"id": "gather"}, {})
    second = await executor.execute_step({"id": "diagnose"}, {})
    assert first["provider"] == second["provider"] == "local_fallback"
    assert "Gemini did not produce" in first["text"]
    assert "test-google-placeholder" not in json.dumps(first)
    assert len(calls) == 1 and executor.fallback_calls == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("candidate", [{"content": {"parts": []}}, {"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "partial response"}]}}])
async def test_incomplete_model_response_never_passes_as_completed_gemini(monkeypatch, candidate):
    monkeypatch.setenv("Google_AI_API_key", "test-google-placeholder")
    monkeypatch.setenv("GEMINI_ENABLED", "true")
    executor = GeminiExecutor(httpx.MockTransport(lambda _: httpx.Response(200, json={"candidates": [candidate]})))
    result = await executor.execute_step({"id": "document"}, {})
    assert result["provider"] == "local_fallback"
    assert executor.completed_calls == 0


@pytest.mark.asyncio
async def test_local_verification_calculates_failures_instead_of_claiming_success(monkeypatch):
    monkeypatch.setenv("GEMINI_ENABLED", "false")
    executor = GeminiExecutor()
    result = await executor.execute_step({"id": "verify"}, {"telemetry_after": {"checkout_p95_ms": 900, "connection_timeouts": 30, "integrity_checks_passed": False}})
    assert result["text"].count("FAIL") == 3
    assert result["provider"] == "local_fallback"


def test_sample_evidence_is_labeled_and_does_not_contain_worker_signals():
    evidence = sample_evidence()
    assert "Example incident" in evidence["provenance"]
    assert not {"workers", "baselines", "ppg", "eda"} & evidence.keys()
