"""Optional TypeSafe Jev routing. Only derived work context leaves the API.

Wire contract: https://docs.typesafe.ai/introduction/quickstart
The deterministic router supplies eligible candidates first. Jev can choose
among them, but cannot introduce an unsafe/unavailable assignment.
"""
from __future__ import annotations

import copy
import math
import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv


class JevRoutingProvider:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        load_dotenv(Path(__file__).resolve().parents[3] / ".env", override=False)
        self._key = os.getenv("JEV_API_key") or os.getenv("JEV_API_KEY") or os.getenv("TYPESAFE_API_KEY") or ""
        self.configured = bool(self._key)
        self.status = "Ready for Jev routing" if self.configured else "Not configured; deterministic fallback"
        self._url = os.getenv("JEV_API_URL", "https://api.typesafe.ai/v1/systemone")
        self._model = os.getenv("JEV_MODEL", "jev-latest")
        self._timeout = min(10, max(0.2, float(os.getenv("JEV_TIMEOUT_SECONDS", "3"))))
        self._retry_after = 0.0
        self._transport = transport

    async def choose_assignment(self, subtask: dict, workers: list[dict], candidates: list[dict]) -> dict | None:
        if not self.configured or not candidates or time.monotonic() < self._retry_after:
            return None
        # Explicit allow-list prevents future raw-signal additions from leaking.
        public_workers = [{key: worker[key] for key in (
            "id", "skills", "availability", "current_task_priority", "time_on_task",
            "cognitive_state",
        ) if key in worker} for worker in workers]
        public_task = {key: subtask[key] for key in (
            "title", "required_skills", "complexity", "risk", "urgency",
            "human_judgment_requirement", "ai_suitability", "estimated_duration",
        ) if key in subtask}
        choices = {f"option_{i}": candidate for i, candidate in enumerate(candidates)}
        payload = {
            "model": self._model,
            "state": {"task": public_task, "workers": public_workers,
                      "candidates": {key: {field: value for field, value in candidate.items()
                                           if field in ("kind", "worker_id", "label", "score")}
                                     for key, candidate in choices.items()}},
            "questions": {"assignment": {
                "type": "choice",
                "instructions": "Select the best eligible assignment for this task. Account for low readiness. Preserve human judgment for risky decisions. Cognitive values are heuristic relative estimates, not medical facts. Consider expertise, availability, current work and interruption cost. AI assistance reduces human burden. Select delay if no suitable capacity.",
                "criteria": {key: f"{candidate.get('label', key)}; kind={candidate.get('kind')}; deterministic compatibility={candidate.get('score', 0)}"
                             for key, candidate in choices.items()},
            }},
        }
        try:
            # Disable redirects: credentials must never be forwarded elsewhere.
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport, follow_redirects=False) as client:
                response = await client.post(self._url, headers={"Authorization": f"Bearer {self._key}"}, json=payload)
            response.raise_for_status()
            answer = response.json()["answers"]["assignment"]
            confidence = float(answer["confidence"])
            if not math.isfinite(confidence) or not 0.35 <= confidence <= 1 or answer["choice"] not in choices:
                self.status = "Jev uncertain; deterministic fallback"
                return None
            selected = copy.deepcopy(choices[answer["choice"]])
            selected["confidence"] = confidence
            explanation = selected.setdefault("explanation", {})
            explanation["summary"] = f"Jev selected this eligible route. {explanation.get('summary', '')}".strip()
            explanation.setdefault("factors", []).append("Jev choice validated against local eligibility rules; factors are local policy explanations.")
            self.status = "Connected; validated Jev decisions"
            return selected
        except (httpx.HTTPError, ValueError, KeyError, TypeError, OverflowError):
            # Never log exception text, headers, request/response bodies or keys.
            self.status = "Jev unavailable; deterministic fallback (retry in 30s)"
            self._retry_after = time.monotonic() + 30
            return None
