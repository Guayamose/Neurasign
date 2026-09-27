#!/usr/bin/env python3
"""Inventory unused manufacturer beat intervals without assigning task labels.

Raw recordings include unlabeled time. This inventory is not labeled-window
coverage, ECG validation or evidence of improved questionnaire prediction.
"""
import io
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from neurasign_engine.causal_data import source_manifest
from neurasign_engine.data import verified_bytes
from neurasign_engine.training import save_json


def run():
    source, manifest = source_manifest(ROOT)
    split = json.loads((ROOT / "experiments/split-v1.json").read_text())
    rows, exclusions = [], []
    for person in split["development"]:
        for path in sorted((source / "UNIVERSE" / person).glob("*/Raw/**/IBI.csv")):
            payload = verified_bytes(path, source, manifest)
            lines = payload.decode().strip().splitlines()
            key = path.relative_to(source).as_posix()
            try:
                origin = float(lines[0].split(",")[0])
                values = np.loadtxt(io.StringIO("\n".join(lines[1:])), delimiter=",", ndmin=2) if len(lines) > 1 else np.empty((0, 2))
                if values.shape[1] != 2 or not np.isfinite(values).all() or not np.isfinite(origin):
                    raise ValueError("Invalid raw IBI structure")
                if len(values) > 1 and np.any(np.diff(values[:, 0]) <= 0):
                    raise ValueError("Raw IBI timestamps are not strictly increasing")
            except (ValueError, IndexError) as error:
                exclusions.append({"member": key, "sha256": manifest[key]["sha256"], "reason": str(error)})
                continue
            dt = np.diff(values[:, 0])
            rows.append({"member": key, "sha256": manifest[key]["sha256"], "participant": person,
                         "session": path.relative_to(source / "UNIVERSE" / person).parts[0],
                         "origin_unix_seconds": origin, "intervals": len(values),
                         "intervals_300_to_2000_ms": int(((values[:, 1] >= .3) & (values[:, 1] <= 2)).sum()),
                         "interevent_gaps_over_2_5_seconds": int((dt > 2.5).sum()),
                         "interevent_gaps_over_60_seconds": int((dt > 60).sum()),
                         "maximum_interevent_gap_seconds": float(dt.max()) if len(dt) else None})
    report = {"development_only": True, "files_considered": len(rows) + len(exclusions),
              "files_parsed": len(rows), "files_excluded": len(exclusions), "exclusions": exclusions,
              "participants": len({r['participant'] for r in rows}),
              "observed_intervals": sum(r["intervals"] for r in rows),
              "intervals_300_to_2000_ms": sum(r["intervals_300_to_2000_ms"] for r in rows),
              "files_with_gaps_over_60_seconds": sum(r["interevent_gaps_over_60_seconds"] > 0 for r in rows),
              "current_v3_uses_native_ibi": False,
              "limitations": ["Counts include unlabeled recording time and cannot be compared with labeled-window coverage.",
                              "Manufacturer intervals come from the same PPG source; they are not ECG ground truth.",
                              "Native-to-labeled time alignment and gap-safe variability calculation are required before model evaluation.",
                              "No intervals are interpolated across gaps. No model was fitted to these intervals in this audit."],
              "records": rows}
    save_json(ROOT / "results/information-v4/native-ibi-inventory.json", report)
    print(json.dumps({k: v for k, v in report.items() if k != "records"}, indent=2))


if __name__ == "__main__":
    run()
