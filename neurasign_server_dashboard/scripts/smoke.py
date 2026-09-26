"""Test actual providers, human gates, capacity rerouting, HTTP and WebSocket.
Use --require-live to require real Jev/Gemini success (uses configured API keys).
"""
import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
import time
import httpx
import websockets

BASE = os.getenv("NEURASIGN_API_URL", "http://localhost:8000")


async def main(require_live=False):
    async with httpx.AsyncClient(base_url=BASE, timeout=35) as client:
        async def control(**command):
            response = await client.post("/api/control", json=command)
            response.raise_for_status()
            return response.json()

        async def state():
            response = await client.get("/api/state")
            response.raise_for_status()
            return response.json()

        async def until(predicate, label, seconds=70):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                snapshot = await state()
                if predicate(snapshot):
                    return snapshot
                await asyncio.sleep(.25)
            raise AssertionError("Timed out: " + label)

        def task(snapshot, name):
            return next(t for t in snapshot["workflow"]["subtasks"] if t["id"] == name)

        (await client.get("/api/health")).raise_for_status()
        await control(action="reset")
        async with websockets.connect(BASE.replace("https://", "wss://").replace("http://", "ws://") + "/ws") as socket:
            message = json.loads(await asyncio.wait_for(socket.recv(), timeout=5))
            assert message["type"] == "snapshot"
            # Physiological summaries are now part of the monitoring product.
            # Private calibration payloads and credentials remain server-side.
            for private in ('"baselines"', '"JEV_API_key"', '"Google_AI_API_key"'):
                assert private not in json.dumps(message)

        await control(action="run_demo")
        await control(action="pause")
        snapshot = await until(lambda s: bool(s["workflow"]) and bool(task(s, "diagnose")["output"]), "diagnosis draft")
        assert len(snapshot["workflow"]["subtasks"]) == 5
        diagnosis = task(snapshot, "diagnose")
        assert diagnosis["assignment"]["worker_id"] == "aoi"
        assert diagnosis["status"] == "active", "A model draft must await human review"
        if require_live:
            assert snapshot["provider"]["selected"] == "jev"
            assert diagnosis["assignment"]["provider"] == "jev"
        gather_output = task(snapshot, "gather")["output"]
        early = await client.post("/api/control", json={"action": "approve_decision"})
        assert early.status_code in (409, 422)
        await control(action="stress_aoi")
        snapshot = await until(lambda s: task(s, "diagnose")["assignment"]["worker_id"] == "alex" and "evaluating" not in s["provider"]["status"].lower(), "new routing")
        assert task(snapshot, "diagnose")["assignment"]["kind"] == "HUMAN_AI"
        if require_live:
            assert task(snapshot, "diagnose")["assignment"]["provider"] == "jev"
        assert task(snapshot, "gather")["output"] == gather_output
        assert snapshot["metrics"]["reroutes"] >= 1
        print("PASS: model draft, human-review gate, capacity reroute and preserved completed evidence", flush=True)
        snapshot = await control(action="complete_diagnosis")
        assert task(snapshot, "decide")["status"] == "active"
        await asyncio.sleep(.5)
        assert task(await state(), "decide")["status"] == "active"
        await control(action="approve_decision")
        snapshot = await until(lambda s: s["workflow"]["status"] == "resolved", "verification and report")
        providers = {t["id"]: t["execution"]["provider"] for t in snapshot["workflow"]["subtasks"]}
        assert providers["decide"] == "human"
        assert all(t["status"] == "completed" and t["output"] for t in snapshot["workflow"]["subtasks"])
        if require_live:
            assert all(providers[t] == "gemini" for t in ("gather", "diagnose", "verify", "document")), providers
        print("PASS: explicit approval and completed artifacts " + json.dumps(providers), flush=True)

        await control(action="reset", mode="live")
        reading = {"worker_id": "aoi", "timestamp": datetime.now(timezone.utc).isoformat(), "ppg": {"heart_rate": 74, "hrv": 65}, "eda": {"tonic": 1.5}, "movement": {"magnitude": .1}, "temperature": 32.5, "quality": .9}
        (await client.post("/api/live/readings", json=reading)).raise_for_status()
        assert (await client.patch("/api/workers/aoi/state", json={"readiness": 900})).status_code == 422
        await control(action="reset")
    print("NEURASIGN integration smoke passed.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-live", action="store_true")
    asyncio.run(main(parser.parse_args().require_live))
