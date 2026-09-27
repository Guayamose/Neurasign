#!/usr/bin/env python3
"""Recalculate saved SWELL test metrics and reload the frozen model artifact."""
import hashlib
import json
from pathlib import Path
import sys

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from neurasign_engine.swell import predict
from neurasign_engine.training import save_json


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify():
    output = ROOT / "results/swell-v1"
    report = json.loads((output / "report.json").read_text())
    protocol = report["protocol"]
    assert digest(ROOT / protocol["workbook_name"]) == protocol["workbook_sha256"]
    assert digest(ROOT / "src/neurasign_engine/swell.py") == protocol["code_sha256"]
    data_path = ROOT / "data/prepared/swell-v1/minutes.csv.gz"
    assert digest(data_path) == report["prepared_sha256"]
    model_path = ROOT / "models/swell-v1-research.joblib"
    assert digest(model_path) == report["artifact_sha256"]
    # Only the locally produced artifact with the verified digest is loaded.
    bundle = joblib.load(model_path)
    data = pd.read_csv(data_path)
    test = data[data.participant.isin(protocol["split"]["test"])].reset_index(drop=True)
    assert len(test) == 431 and test.unit_id.nunique() == 15 and test.participant.nunique() == 5
    checked = []
    with threadpool_limits(limits=2):
        for target, result in report["targets"].items():
            expected = test[test[target].notna()].reset_index(drop=True)
            for role, metric in result["heldout"].items():
                path = output / f"{target}__{role}.csv.gz"
                rows = pd.read_csv(path)
                for column in ("participant", "unit_id", "session"):
                    assert rows[column].equals(expected[column])
                np.testing.assert_allclose(rows[target], expected[target], atol=1e-12, rtol=0)
                assert set(rows.participant).isdisjoint(protocol["split"]["development"])
                errors = abs(rows.prediction - rows[target])
                scores = rows[["participant", "unit_id"]].assign(error=errors, one=errors <= 1., two=errors <= 2.)
                measured = scores.groupby(["participant", "unit_id"])[["error", "one", "two"]].mean().groupby("participant").mean().mean()
                np.testing.assert_allclose(measured.to_numpy(), [metric["participant_macro_mae"], metric["within_one_point_fraction"], metric["within_two_points_fraction"]], rtol=1e-12, atol=1e-12)
                if role == "selected":
                    head = bundle["heads"][target]
                    np.testing.assert_allclose(predict(head["model"], head["config"], expected, target), rows.prediction, rtol=1e-10, atol=1e-10)
                checked.append({"target": target, "role": role, "sha256": digest(path)})
    assert len(checked) == 30
    save_json(output / "verification.json", {"status": "passed", "comparison_tables": 30,
        "numeric_metrics_recalculated": 90, "reloaded_selected_heads": 6, "heldout_people": protocol["split"]["test"],
        "report_sha256": digest(output / "report.json"), "predictions": checked})
    print("Verified 90 metrics from 30 prediction tables, six reloaded heads, participant isolation and source/artifact digests.")


if __name__ == "__main__":
    verify()
