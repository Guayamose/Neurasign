"""Recorded summary fidelity, source isolation, and explicit missing/stale values."""

from datetime import datetime, timedelta, timezone
from time import monotonic

import pytest

from neurasign.orchestration import WorkflowOrchestrator
from neurasign.signals import FEATURES


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("ROUTING_PROVIDER", "deterministic")
    monkeypatch.setenv("GEMINI_ENABLED", "false")


def by_worker(snapshot, worker_id):
    return next(worker for worker in snapshot["monitoring"]["workers"] if worker["worker_id"] == worker_id)


def test_initial_monitoring_has_history_without_an_incident():
    engine = WorkflowOrchestrator()
    snapshot = engine.snapshot()
    assert snapshot["workflow"] is None
    assert snapshot["playing"] and snapshot["speed"] == 10
    assert snapshot["monitoring"]["signal_seconds"] == 120
    assert [w["worker_id"] for w in snapshot["monitoring"]["workers"]] == ["alex", "aoi"]
    assert all(len(worker["history"]) == 13 for worker in snapshot["monitoring"]["workers"])
    assert snapshot["monitoring"]["units"] == {"heart_rate": "bpm", "hrv": "ms", "eda": "µS", "temperature": "°C", "movement": "g"}


def test_every_recorded_point_and_current_value_matches_the_original_source_window():
    engine = WorkflowOrchestrator()
    engine.signal_seconds = 420
    snapshot = engine.snapshot()
    for worker_id in ("alex", "aoi"):
        data = by_worker(snapshot, worker_id)
        expected = [row for row in engine.replay.rows[worker_id] if row["timestamp"] <= 420]
        assert len(data["history"]) == len(expected)
        for point, row in zip(data["history"], expected):
            assert point["time"] == row["timestamp"]
            for feature in FEATURES:
                assert point[feature] == row["features"].get(feature)
            assert all(0 <= point[index] <= 100 for index in ("cognitive_load", "readiness", "fatigue"))
        assert data["features"] == {key: expected[-1]["features"].get(key) for key in FEATURES}
        assert data["last_sample_seconds"] == 420
        assert data["last_sample_at"] is None
        assert data["reference"] == {key: engine.replay.baselines[worker_id][key]["mean"] for key in FEATURES}
        assert all(point["time"] <= engine.signal_seconds for point in data["history"])


def test_missing_measurement_remains_null_instead_of_becoming_a_reference_value():
    engine = WorkflowOrchestrator()
    row = next(row for row in engine.replay.rows["aoi"] if row["timestamp"] == 120)
    row["features"].pop("hrv", None)
    row["quality"] = .35
    worker = by_worker(engine.snapshot(), "aoi")
    assert worker["features"]["hrv"] is None
    assert worker["history"][-1]["hrv"] is None
    assert worker["reference"]["hrv"] is not None
    assert worker["quality"] == .35


def test_history_is_bounded_and_cannot_reveal_future_recording_windows():
    engine = WorkflowOrchestrator()
    engine.signal_seconds = 1405
    for worker in engine.snapshot()["monitoring"]["workers"]:
        assert len(worker["history"]) == 90
        assert worker["history"][-1]["time"] == 1400
        assert worker["history"][0]["time"] == 510
    engine.signal_seconds = -1
    for worker in engine.snapshot()["monitoring"]["workers"]:
        assert worker["status"] == "waiting"
        assert worker["history"] == []
        assert all(value is None for value in worker["features"].values())


@pytest.mark.asyncio
async def test_manual_source_has_no_inherited_recorded_physiology_or_reference():
    engine = WorkflowOrchestrator()
    await engine.set_manual("aoi", {"readiness": 44})
    monitoring = engine.snapshot()["monitoring"]
    assert monitoring["source_kind"] == "manual"
    for worker in monitoring["workers"]:
        assert worker["status"] == "manual"
        assert worker["history"] == []
        assert worker["quality"] == 0
        assert all(value is None for value in worker["features"].values())
        assert all(value is None for value in worker["reference"].values())
        assert worker["recording"] is None


@pytest.mark.asyncio
async def test_live_current_window_and_history_use_only_received_values():
    engine = WorkflowOrchestrator()
    await engine.set_mode("live")
    now = datetime.now(timezone.utc)
    assert by_worker(engine.snapshot(), "alex")["status"] == "waiting"
    for index, rate in enumerate((72, 80)):
        await engine.ingest_live({"worker_id": "aoi", "timestamp": (now-timedelta(seconds=2-index)).isoformat(), "ppg": {"heart_rate": rate}})
    data = by_worker(engine.snapshot(), "aoi")
    assert data["status"] == "live"
    assert data["features"]["heart_rate"] == 76
    assert data["features"]["hrv"] is None
    assert [point["heart_rate"] for point in data["history"]] == [72, 80]
    assert data["history"][-1]["time"] == (now-timedelta(seconds=1)).timestamp()
    assert datetime.fromisoformat(data["last_sample_at"]).timestamp() == data["last_sample_seconds"]
    assert "provisional" in data["reference_status"]
    assert by_worker(engine.snapshot(), "alex")["history"] == []


@pytest.mark.asyncio
async def test_stale_live_hides_current_values_but_preserves_observed_history():
    engine = WorkflowOrchestrator()
    await engine.ingest_live({"worker_id": "aoi", "timestamp": datetime.now(timezone.utc).isoformat(), "ppg": {"heart_rate": 74}})
    engine.live.last_received["aoi"] = monotonic()-16
    data = by_worker(engine.snapshot(), "aoi")
    assert data["status"] == "stale"
    assert data["quality"] == 0
    assert all(value is None for value in data["features"].values())
    assert data["history"][-1]["heart_rate"] == 74


def test_fixture_provenance_is_never_labeled_as_a_real_participant_recording():
    engine = WorkflowOrchestrator()
    engine.reset(fixture_only=True)
    data = engine.snapshot()["monitoring"]
    assert data["source_kind"] == "fixture"
    assert data["signal_seconds"] == 0
    assert all(worker["status"] == "synthetic" and worker["recording"] is None for worker in data["workers"])
