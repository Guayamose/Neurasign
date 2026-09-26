"""Interchangeable, private signal sources producing temporal feature windows.

The checked-in fixture is illustrative synthetic data. Imported UNIVERSE windows
are observed summary features; neither source proves a cognitive diagnosis.
"""

from abc import ABC, abstractmethod
from collections import defaultdict, deque
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from statistics import mean
from time import monotonic

ROOT = Path(__file__).resolve().parents[3]
FEATURES = ("heart_rate", "hrv", "eda", "temperature", "movement")
DEFAULT_BASELINES = {
    "alex": {"heart_rate": {"mean": 70., "std": 8.}, "hrv": {"mean": 55., "std": 10.},
             "eda": {"mean": 2., "std": .8}, "temperature": {"mean": 33., "std": .5},
             "movement": {"mean": .1, "std": .1}},
    "aoi": {"heart_rate": {"mean": 74., "std": 8.}, "hrv": {"mean": 65., "std": 12.},
            "eda": {"mean": 1.5, "std": .6}, "temperature": {"mean": 32.5, "std": .5},
            "movement": {"mean": .1, "std": .1}},
}


@dataclass
class SignalWindow:
    worker_id: str
    timestamp: float
    features: dict[str, float] = field(default_factory=dict)
    quality: float = .9
    sample_count: int = 1
    manual_state: dict[str, float] | None = None


class SignalSource(ABC):
    @abstractmethod
    def get_next_window(self, elapsed_seconds: float) -> list[SignalWindow]:
        """Return window summaries. Only inference receives these private values."""


def synthetic_fixture() -> dict:
    """Fallback for an incomplete checkout, never represented as UNIVERSE data."""
    windows = []
    for second in range(0, 1801, 10):
        for worker_id in ("alex", "aoi"):
            z = max(0, 1.5 * (1 - max(0, second - 300) / 400)) if worker_id == "alex" else min(4., max(0, (second - 480) / 570 * 4))
            if worker_id == "aoi" and second > 1350:
                z = max(1., 4 - (second - 1350) / 450 * 3)
            baseline = DEFAULT_BASELINES[worker_id]
            values = {name: baseline[name]["mean"] + baseline[name]["std"] * z * (-1 if name == "hrv" else (0.12 if name in ("temperature", "movement") else 1)) for name in FEATURES}
            windows.append({"worker_id": worker_id, "timestamp": second, "features": values, "quality": .92})
    return {"metadata": {"kind": "fixture", "name": "Synthetic workload replay",
            "description": "Illustrative synthetic feature windows; not measured UNIVERSE observations.", "window_seconds": 10},
            "baselines": DEFAULT_BASELINES, "windows": windows}


class UniverseReplaySource(SignalSource):
    """Accept the same preprocessed schema from real data or a labeled fixture."""

    def __init__(self, fixture_only: bool = False, path: Path | None = None):
        candidates = [path] if path else ([ROOT / "data/fixtures/replay.json"] if fixture_only else [ROOT / "data/universe/replay.json", ROOT / "data/fixtures/replay.json"])
        self.payload = None
        for candidate in candidates:
            try:
                payload = json.loads(candidate.read_text())
                if not payload.get("windows") or not all(w in payload.get("baselines", {}) for w in ("alex", "aoi")):
                    continue
                if not all(any(row.get("worker_id") == worker for row in payload["windows"]) for worker in ("alex", "aoi")):
                    continue
                for worker in ("alex", "aoi"):
                    for key in FEATURES:
                        baseline = payload["baselines"][worker][key]
                        if not all(math.isfinite(float(baseline[k])) for k in ("mean", "std")) or float(baseline["std"]) < 0:
                            raise ValueError("Invalid personal baseline")
                for row in payload["windows"]:
                    if row["worker_id"] not in ("alex", "aoi") or not math.isfinite(float(row["timestamp"])) or not row["features"]:
                        raise ValueError("Invalid feature window")
                    if not all(key in FEATURES and math.isfinite(float(value)) for key, value in row["features"].items()):
                        raise ValueError("Invalid feature value")
                    if not 0 <= row.get("quality", .8) <= 1:
                        raise ValueError("Invalid quality")
                if payload["metadata"]["kind"] not in ("fixture", "universe"):
                    raise ValueError("Invalid source provenance")
                self.payload = payload
                break
            except (OSError, ValueError, TypeError, KeyError, AttributeError):
                continue
        if self.payload is None:
            self.payload = synthetic_fixture()
        self.baselines = self.payload["baselines"]
        self.metadata = self.payload["metadata"]
        self.rows = {worker: sorted([row for row in self.payload["windows"] if row["worker_id"] == worker], key=lambda row: row["timestamp"]) for worker in ("alex", "aoi")}
        self.duration_seconds = min(rows[-1]["timestamp"] for rows in self.rows.values())

    def get_next_window(self, elapsed_seconds: float) -> list[SignalWindow]:
        result = []
        for worker, rows in self.rows.items():
            eligible = [row for row in rows if row["timestamp"] <= elapsed_seconds]
            # These are already windows of sensor data, then smoothed over 30 s.
            recent = (eligible or rows[:1])[-3:]
            features = {key: mean([float(row["features"][key]) for row in recent if key in row["features"]]) for key in FEATURES if any(key in row["features"] for row in recent)}
            result.append(SignalWindow(worker, recent[-1]["timestamp"], features, mean([row.get("quality", .8) for row in recent]), len(recent)))
        return result


class ManualSignalSource(SignalSource):
    """Direct, transparent demo controls, not fabricated physiological readings."""

    def __init__(self):
        self.states: dict[str, dict[str, float]] = {}

    def set_state(self, worker_id: str, state: dict[str, float]):
        self.states[worker_id] = state

    def get_next_window(self, elapsed_seconds: float) -> list[SignalWindow]:
        return [SignalWindow(worker, elapsed_seconds, quality=1., manual_state=state) for worker, state in self.states.items()]


class LiveWearableSource(SignalSource):
    """HTTP-ingested samples averaged inside a trailing 10-second device window.

    PPG feature extraction (heart rate/HRV) occurs on the device or its private
    gateway. This adapter intentionally does not pretend a single PPG amplitude
    is an HRV measurement. No hardware or device authentication is implemented.
    """

    def __init__(self, window_seconds: float = 10):
        self.window_seconds = window_seconds
        self.buffers = defaultdict(lambda: deque(maxlen=500))
        self.last_received: dict[str, float] = {}
        # This is an explicit provisional reference, never an inherited recording.
        # A future device calibration replaces it with that wearer's own baseline.
        self.baselines = deepcopy(DEFAULT_BASELINES)
        self.baseline_status = "provisional_synthetic_reference_not_personally_calibrated"
        self.reference_quality = .6

    def ingest(self, payload: dict):
        timestamp = datetime.fromisoformat(str(payload["timestamp"]).replace("Z", "+00:00")).timestamp()
        now = datetime.now(timezone.utc).timestamp()
        if timestamp < now-30 or timestamp > now+5:
            raise ValueError("Live timestamp must be within the past 30 seconds and no more than 5 seconds in the future")
        worker_id = payload["worker_id"]
        buffer = self.buffers.get(worker_id)
        if buffer and timestamp <= buffer[-1][0]:
            raise ValueError("Live timestamps must increase strictly; duplicate or out-of-order readings are rejected")
        features = {}
        for group, input_key, output_key in (("ppg", "heart_rate", "heart_rate"), ("ppg", "hrv", "hrv"), ("eda", "tonic", "eda"), ("movement", "magnitude", "movement")):
            value = (payload.get(group) or {}).get(input_key)
            if value is not None:
                features[output_key] = float(value)
        if payload.get("temperature") is not None:
            features["temperature"] = float(payload["temperature"])
        if not features or not all(math.isfinite(v) for v in features.values()):
            raise ValueError("Provide at least one finite sensor feature")
        quality = float(payload.get("quality", .9))
        if not math.isfinite(quality) or not 0 <= quality <= 1:
            raise ValueError("Sensor quality must be between 0 and 1")
        self.buffers[worker_id].append((timestamp, features, quality))
        self.last_received[worker_id] = monotonic()

    def get_next_window(self, elapsed_seconds: float = 0) -> list[SignalWindow]:
        result = []
        for worker, buffer in self.buffers.items():
            latest = max(row[0] for row in buffer)
            rows = [row for row in buffer if latest - self.window_seconds <= row[0] <= latest]
            features = {key: mean([row[1][key] for row in rows if key in row[1]]) for key in FEATURES if any(key in row[1] for row in rows)}
            # A single sample is usable for connectivity but explicitly uncertain.
            age = max(monotonic()-self.last_received[worker], datetime.now(timezone.utc).timestamp()-latest)
            freshness = max(0., 1-max(0., age-15)/45)
            span = max(row[0] for row in rows)-min(row[0] for row in rows)
            coverage = min(1., len(rows)/5) * min(1., span/8)
            quality = round(mean([row[2] for row in rows]) * coverage * freshness * self.reference_quality, 3)
            result.append(SignalWindow(worker, latest, features, quality, len(rows)))
        return result
