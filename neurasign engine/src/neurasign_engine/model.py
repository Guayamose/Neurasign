"""One research bundle with independently masked regression/ordinal heads."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .schema import FEATURES, FEATURE_GROUPS, TARGETS, PIPELINE_ID


class MultiOutputEngine:
    def __init__(self, heads, metadata):
        if set(heads) != set(TARGETS):
            raise ValueError("Bundle must contain exactly the supported research targets")
        self.heads = heads
        self.metadata = metadata

    def predict(self, features: dict, pipeline_id: str):
        if pipeline_id != PIPELINE_ID:
            raise ValueError("Feature pipeline differs from training; live-device transfer is not validated")
        if set(features) - set(FEATURES):
            raise ValueError("Unexpected input fields; only the physiological feature allowlist is accepted")
        row = {}
        for key in FEATURES:
            value = features.get(key)
            if value is None:
                row[key] = np.nan
            elif isinstance(value, bool) or not isinstance(value, (float, int)) or not np.isfinite(value):
                raise ValueError(f"Feature must be a finite number or null: {key}")
            else:
                row[key] = float(value)
        missing = [key for key,value in row.items() if not np.isfinite(value)]
        if len(missing)>2 or any(all(key in missing for key in group) for group in FEATURE_GROUPS.values()):
            return {"status":"insufficient_data", "research_only":True, "missing_features":missing, "estimates":{}}
        frame = pd.DataFrame([row], columns=FEATURES)
        estimates = {}
        for name, model in self.heads.items():
            spec = TARGETS[name]
            prediction = float(np.clip(model.predict(frame)[0], *spec["range"]))
            estimates[name] = {
                "predicted_rating":round(prediction,3), "scale":spec["range"],
                "meaning":spec["meaning"],
                "held_out_mean_absolute_error":self.metadata["targets"][name]["test"]["participant_macro_mae"],
                "beat_baseline_on_holdout":self.metadata["targets"][name]["beat_baseline_on_holdout"],
            }
            if spec["kind"] == "ordinal":
                estimates[name]["nearest_level"] = int(np.clip(np.floor(prediction+0.5),*spec["range"]))
        return {"status":"experimental_estimates", "research_only":True,
                "pipeline_id":PIPELINE_ID,"missing_features":missing,"estimates":estimates}
