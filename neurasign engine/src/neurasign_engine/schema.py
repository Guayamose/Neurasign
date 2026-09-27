"""Explicit feature and output schema; questionnaire targets are never inputs."""

FEATURE_GROUPS = {
    "HRV_features.pickle": ["HRV_MeanNN", "HRV_SDNN", "HRV_RMSSD", "HRV_LFn", "HRV_HFn", "HRV_ratio_LFn_HFn"],
    "EDA_features.pickle": ["SCR_Peaks_N", "SCR_Peaks_Amplitude_Mean"],
    "TEMP_features.pickle": ["mean_temp", "std_temp"],
}
FEATURES = [name for names in FEATURE_GROUPS.values() for name in names]
TARGETS = {
    "mental_effort": {"column": "Mental effort level", "range": [1, 5], "kind": "ordinal", "meaning": "Self-reported mental effort, very low to very high"},
    "mental_demand": {"column": "Mental Demand", "range": [0, 100], "kind": "rating", "meaning": "Self-reported mental demand"},
    "physical_demand": {"column": "Physical Demand", "range": [0, 100], "kind": "rating", "meaning": "Self-reported physical demand; not physical fatigue"},
    "temporal_demand": {"column": "Temporal Demand", "range": [0, 100], "kind": "rating", "meaning": "Self-reported time pressure"},
    "perceived_performance": {"column": "Performance", "range": [0, 100], "kind": "rating", "meaning": "Recorded self-rating of task performance; not an objective productivity assessment"},
    "effort": {"column": "Effort", "range": [0, 100], "kind": "rating", "meaning": "Self-reported effort"},
}
EXCLUDED_TARGETS = {
    "Mental stress level": "No workplace biometric inference of mental-health states.",
    "Frustration": "No workplace biometric inference of emotions.",
    "Weighted Nasa Score": "Composite includes frustration; not used directly or reconstructed as a proxy.",
    "PANAS": "Affective questionnaire; no workplace biometric emotion inference.",
    "Affective Sliders": "Affective questionnaire; no workplace biometric emotion inference.",
}
PIPELINE_ID = "universe_published_wrist_features_offline_v1"
WINDOW_SECONDS = 60
STEP_SECONDS = 12
SEED = 20260926


def normalize_likert(value):
    import re
    text = re.sub(r"[,\s]+", " ", str(value).strip().lower())
    return {
        "very very low": 1, "very low": 1, "low": 2,
        "neither low nor high": 3, "neighter low nor high": 3,
        "high": 4, "very high": 5, "very very high": 5,
    }.get(text)
