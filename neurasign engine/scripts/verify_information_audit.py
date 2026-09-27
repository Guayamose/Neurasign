#!/usr/bin/env python3
"""Independently recalculate every v4 MAE from saved prediction rows and verify inputs."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results/information-v4"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify():
    report = json.loads((OUTPUT / "report.json").read_text())
    protocol = report["protocol"]
    data_path = ROOT / "data/prepared/causal-v3/windows.csv.gz"
    assert digest(data_path) == protocol["dataset_sha256"]
    assert digest(ROOT / "src/neurasign_engine/information_audit.py") == report["code_sha256"]
    data = pd.read_csv(data_path)
    checked = []
    for target, variants in report["ablation"]["targets"].items():
        original = data[data[target].notna()].reset_index(drop=True)
        for name, metric in variants.items():
            variant, model = name.split("/")
            path = OUTPUT / f"{target}__{variant}__{model}.csv.gz"
            rows = pd.read_csv(path)
            assert len(rows) == len(original)
            for column in ("participant", "session", "unit_id"):
                assert rows[column].equals(original[column])
            np.testing.assert_allclose(rows.source_end, original.source_end, rtol=0, atol=1e-6)
            np.testing.assert_array_equal(rows[target], original[target])
            assert set(rows.participant) == set(protocol["development"])
            assert not (set(rows.participant) & set(protocol["excluded_original_test"]))
            low, high = (1, 5) if target == "mental_effort" else (0, 100)
            assert np.isfinite(rows.prediction).all() and rows.prediction.between(low, high).all()
            rows["absolute_error"] = abs(rows[target] - rows.prediction)
            tasks = rows.groupby(["participant", "unit_id"]).absolute_error.mean()
            measured = tasks.groupby("participant").mean().mean()
            assert np.isclose(measured, metric["participant_macro_mae"], rtol=1e-12, atol=1e-12)
            checked.append({"target": target, "variant": variant, "model": model,
                            "mae": float(measured), "prediction_sha256": digest(path)})
    assert len(checked) == 132
    extraction = json.loads((OUTPUT / "extraction.json").read_text())
    assert extraction["output_sha256"] == digest(OUTPUT / "diagnostics.csv.gz")
    assert extraction["verified_unmasked_windows"] == 20725
    saved = {"checked_comparisons": len(checked), "source_dataset_sha256": digest(data_path),
             "report_sha256": digest(OUTPUT / "report.json"), "original_test_evaluated": False,
             "unmasked_pulse_feature_equality_checks": extraction["verified_unmasked_windows"],
             "comparisons": checked}
    (OUTPUT / "verification.json").write_text(json.dumps(saved, indent=2, allow_nan=False) + "\n")
    print("Verified all 132 MAEs, prediction rows, development boundary, feature equality count and artifact digests.")


if __name__ == "__main__":
    verify()
