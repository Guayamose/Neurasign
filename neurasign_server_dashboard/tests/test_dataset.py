"""Meaningful import invariants: no calibration leakage, units, provenance, bounds."""
import csv
import json
import math
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from download_universe import RemoteZipReader, archive_for, safe_target, selected_member
from generate_fixtures import build_fixture
from preprocess_universe import FEATURES, RegularSignal, import_csv, read_regular, rmssd, window_features


def write_canonical(path, *, nonfinite=False):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["worker_id", "timestamp", *FEATURES, "quality"])
        writer.writeheader()
        for worker_id, offset in (("alex", 0), ("aoi", 10)):
            for index in range(8):
                writer.writerow({
                    "worker_id": worker_id,
                    "timestamp": index * 10,
                    "heart_rate": (70 + offset if index < 3 else 100 + offset),
                    "hrv": "" if index == 4 else ("nan" if nonfinite else 50 + index),
                    "eda": 2,
                    "temperature": 33,
                    "movement": 0.1,
                    "quality": 0.9,
                })


def test_csv_calibration_is_personal_and_excluded_from_playback(tmp_path):
    path = tmp_path / "signals.csv"
    write_canonical(path)
    result = import_csv(path, baseline_seconds=30, window_seconds=10, kind="fixture", source_url=None)
    assert result["baselines"]["alex"]["heart_rate"]["mean"] == 70
    assert result["baselines"]["aoi"]["heart_rate"]["mean"] == 80
    assert min(window["timestamp"] for window in result["windows"]) == 0
    assert len(result["windows"]) == 10
    first_alex = next(window for window in result["windows"] if window["worker_id"] == "alex")
    assert first_alex["features"]["heart_rate"] == 100
    missing = [window for window in result["windows"] if window.get("missing_features")]
    assert len(missing) == 2
    assert all("hrv" not in window["features"] and window["quality"] <= 0.35 for window in missing)


def test_csv_rejects_nonfinite_features(tmp_path):
    path = tmp_path / "signals.csv"
    write_canonical(path, nonfinite=True)
    with pytest.raises(ValueError, match="finite"):
        import_csv(path, 30, 10, "fixture", None)


def test_empatica_regular_signal_keeps_nan_timestamps(tmp_path):
    path = tmp_path / "HR.csv"
    path.write_text("1000\n1\n70\nnan\n90\n")
    signal = read_regular(path)
    assert signal.window(1002, 1003) == [[90]]
    assert math.isnan(signal.window(1001, 1002)[0][0])


def test_rmssd_uses_milliseconds_and_does_not_bridge_gaps():
    intervals = []
    timestamp = 0
    for index in range(12):
        interval = 0.8 if index % 2 == 0 else 0.82
        timestamp += interval
        intervals.append((timestamp, interval))
    value, count = rmssd(intervals)
    assert value == pytest.approx(20)
    assert count == 11
    gapped = [(index * 10.0, interval) for index, (_, interval) in enumerate(intervals)]
    assert rmssd(gapped) == (None, 0)


def test_window_units_use_accelerometer_counts_in_g():
    signals = {
        "heart_rate": RegularSignal(1000, 1, [[70]] * 60),
        "eda": RegularSignal(1000, 1, [[2]] * 60),
        "temperature": RegularSignal(1000, 1, [[33]] * 60),
        "movement": RegularSignal(1000, 1, [[0, 0, 64], [0, 0, 128]] * 30),
    }
    result = window_features(signals, [], [], 1000, 1060)
    assert result["features"]["movement"] == pytest.approx(0.5)
    assert result["features"]["heart_rate"] == 70
    assert result["features"]["hrv"] is None
    assert result["quality"] <= 0.35


def test_remote_reader_enforces_budget_before_network():
    reader = RemoteZipReader("https://example.invalid/never-fetched", size=1000, max_bytes=10)
    with pytest.raises(ValueError, match="budget"):
        reader.read(11)


def test_selected_archive_members_cannot_escape_output(tmp_path):
    with pytest.raises(ValueError, match="Unsafe"):
        safe_target(tmp_path, "../../credentials")
    assert archive_for("UN_103") == "UNIVERSE_UN_101_to_UN_112.zip"
    assert archive_for("UN_124") == "UNIVERSE_UN_113_to_UN_124.zip"
    with pytest.raises(ValueError):
        archive_for("UN_125")
    assert selected_member("UNIVERSE/UN_103/Lab1/Raw/Empatica/HR.csv", ["UN_103"], "Lab1", ["HR.csv"])
    assert not selected_member("UNIVERSE/UN_103/Lab1/Features/HRV_features.pickle", ["UN_103"], "Lab1", ["HR.csv"])


def test_fixture_is_deterministic_and_explicitly_synthetic():
    fixture = build_fixture()
    assert fixture == build_fixture()
    assert fixture["metadata"]["kind"] == "fixture"
    rows = {(row["worker_id"], row["timestamp"]): row["features"] for row in fixture["windows"]}
    assert rows[("aoi", 1050)]["heart_rate"] > rows[("aoi", 0)]["heart_rate"] + 25
    assert rows[("alex", 1050)]["heart_rate"] < rows[("alex", 0)]["heart_rate"] - 10
    assert all(math.isfinite(value) for features in rows.values() for value in features.values())
    assert all(features["hrv"] > 0 for features in rows.values())


def test_locally_imported_real_recording_has_two_participants_and_provenance():
    path = ROOT / "data/universe/replay.json"
    if not path.is_file():
        pytest.skip("Real data is locally imported, not required in a fresh checkout")
    replay = json.loads(path.read_text())
    metadata = replay["metadata"]
    assert metadata["kind"] == "universe"
    assert metadata["license"] == "CC-BY-4.0"
    assert metadata["recordings"]["alex"]["participant"] != metadata["recordings"]["aoi"]["participant"]
    assert len(replay["windows"]) == 362
    assert len(metadata["download_manifest"]["files"]) == 14
    assert all(len(member["sha256"]) == 64 for member in metadata["download_manifest"]["files"])
