"""User-authorized physiological summaries for the primary team dashboard.

These are observed device features, not generated waveforms. Recorded feature
points are copied exactly from their source window; absent measurements remain
null. Inference is separately recomputed over trailing features and current work
context, and is explicitly identified as a heuristic rather than an observation.
"""

from datetime import datetime, timezone
from statistics import mean
from time import monotonic

from .models import MonitoringFeatures, MonitoringPoint, MonitoringWorker
from .signals import FEATURES, SignalWindow

UNITS = {"heart_rate": "bpm", "hrv": "ms", "eda": "µS", "temperature": "°C", "movement": "g"}
HISTORY_POINTS = 90


def feature_values(values: dict) -> MonitoringFeatures:
    # Never substitute a baseline mean for an absent physiological observation.
    return MonitoringFeatures(**{key: float(values[key]) if values.get(key) is not None else None for key in FEATURES})


def _aggregate(rows: list[dict], worker_id: str) -> SignalWindow:
    features = {key: mean(float(row["features"][key]) for row in rows if key in row["features"]) for key in FEATURES if any(key in row["features"] for row in rows)}
    return SignalWindow(worker_id, float(rows[-1]["timestamp"]), features,
                        mean(row.get("quality", .8) for row in rows), len(rows))


def _point(engine, worker, row: dict, window: SignalWindow, baseline: dict) -> MonitoringPoint:
    # Current work context is intentionally held fixed when comparing historical
    # signal windows; this is not a claim to have measured past mental states.
    state = engine.inference.infer(window, baseline, worker)
    return MonitoringPoint(time=float(row["timestamp"]), **feature_values(row["features"]).model_dump(),
                           cognitive_load=state.cognitive_load, readiness=state.readiness, fatigue=state.fatigue)


def _replay_worker(engine, worker) -> MonitoringWorker:
    source = engine.replay
    rows = [row for row in source.rows[worker.id] if row["timestamp"] <= engine.signal_seconds]
    baseline = source.baselines[worker.id]
    kind = source.metadata["kind"]
    recordings = source.metadata.get("recordings", {}).get(worker.id, {})
    recording = {key: str(recordings[key]) for key in ("participant", "session", "sensor") if key in recordings} or None
    history = []
    for index in range(max(0, len(rows)-HISTORY_POINTS), len(rows)):
        row = rows[index]
        history.append(_point(engine, worker, row, _aggregate(rows[max(0, index-2):index+1], worker.id), baseline))
    return MonitoringWorker(worker_id=worker.id,
        quality=rows[-1].get("quality", .8) if rows else 0,
        status=("recorded" if kind == "universe" else "synthetic") if rows else "waiting",
        last_sample_seconds=float(rows[-1]["timestamp"]) if rows else None,
        features=feature_values(rows[-1]["features"]) if rows else MonitoringFeatures(),
        reference=feature_values({key: baseline[key]["mean"] for key in FEATURES}),
        reference_status="personal_recorded_reference_not_verified_rest" if kind == "universe" else "synthetic_demo_reference",
        recording=recording, history=history)


def _live_worker(engine, worker) -> MonitoringWorker:
    source = engine.live
    buffer = list(source.buffers.get(worker.id, []))
    baseline = source.baselines[worker.id]
    reference = feature_values({key: baseline[key]["mean"] for key in FEATURES})
    if not buffer:
        return MonitoringWorker(worker_id=worker.id, quality=0, status="waiting", reference=reference, reference_status=source.baseline_status)
    rows = [{"timestamp": row[0], "features": row[1], "quality": row[2]} for row in buffer]
    latest = rows[-1]["timestamp"]
    age = max(monotonic()-source.last_received[worker.id], datetime.now(timezone.utc).timestamp()-latest)
    stale = age > 15
    window = next(window for window in source.get_next_window() if window.worker_id == worker.id)
    history = []
    for index in range(max(0, len(rows)-HISTORY_POINTS), len(rows)):
        row = rows[index]
        trailing = [prior for prior in rows[:index+1] if row["timestamp"]-source.window_seconds <= prior["timestamp"]]
        history.append(_point(engine, worker, row, _aggregate(trailing, worker.id), baseline))
    return MonitoringWorker(worker_id=worker.id, quality=0 if stale else window.quality,
        status="stale" if stale else "live", last_sample_at=datetime.fromtimestamp(latest, timezone.utc).isoformat(),
        last_sample_seconds=latest, features=MonitoringFeatures() if stale else feature_values(window.features),
        reference=reference, reference_status=source.baseline_status, history=history)


def monitoring_snapshot(engine) -> dict:
    if engine.mode == "manual":
        workers = [MonitoringWorker(worker_id=worker.id, quality=0, status="manual", reference_status="manual_indices_have_no_physiological_reference") for worker in engine.workers]
        window_seconds = 0
        feature_method = "Manual capacity settings have no measured physiology; sensor features and history are unavailable."
    elif engine.mode == "live":
        workers = [_live_worker(engine, worker) for worker in engine.workers]
        window_seconds = engine.live.window_seconds
        feature_method = "Current features are trailing 10-second means of received device feature readings. History shows received feature values, not raw PPG or ECG waveforms. Current features are hidden after 15 seconds without fresh readings."
    else:
        workers = [_replay_worker(engine, worker) for worker in engine.workers]
        window_seconds = engine.replay.metadata.get("window_seconds", 10)
        feature_method = engine.replay.metadata.get("feature_method", "Labeled synthetic physiological feature windows; not recorded human measurements.")
    source = engine.source_description()
    return {"source_kind": source["kind"], "source_name": source["name"], "description": source["description"],
            "signal_seconds": round(engine.signal_seconds, 3), "window_seconds": window_seconds,
            "units": UNITS.copy(), "feature_method": feature_method,
            "inference_method": "Capacity history is a relative heuristic recomputed from trailing feature windows using the current staged work context. Replay inference smooths three source windows; physiological history preserves each original source window. These are not measured or clinical mental states.",
            "workers": [worker.model_dump() for worker in workers]}
