"""Replaceable heuristic inference, deliberately separate from task routing.

Observed: windowed HR, HRV, EDA, temperature and movement features.
Normalized: z-scores against this person's reference period.
Inferred: load/readiness/fatigue; unvalidated demo indices, not diagnoses.
Work context: scenario priority and time-on-task drive interruption cost.
Confounders (motion, environment, caffeine, illness) prevent causal claims.
"""

from .models import CognitiveState, Worker
from .signals import FEATURES, SignalWindow


def clamp(value: float, low: float = 0, high: float = 100) -> float:
    return round(max(low, min(high, value)), 1)


def normalize(features: dict[str, float], baseline: dict) -> dict[str, float]:
    """Missing features stay neutral; confidence separately reflects coverage."""
    return {key: max(-4., min(4., (features.get(key, baseline[key]["mean"]) - baseline[key]["mean"]) / max(abs(baseline[key]["std"]), 1e-6))) for key in FEATURES}


class InferenceEngine:
    def infer(self, window: SignalWindow, baseline: dict, worker: Worker) -> CognitiveState:
        previous = worker.cognitive_state
        if window.manual_state is not None:
            values = {key: clamp(window.manual_state.get(key, getattr(previous, key))) for key in ("cognitive_load", "readiness", "fatigue", "interruption_cost")}
            return CognitiveState(**values, confidence=1, trend=self._trend(values["readiness"] - previous.readiness))
        z = normalize(window.features, baseline)
        strain = .44*z["heart_rate"] - .40*z["hrv"] + .25*z["eda"] + .06*z["temperature"] + .08*z["movement"]
        load = clamp(30 + 15*strain)
        fatigue = clamp(18 + 8*(.35*z["heart_rate"] - .4*z["hrv"] + .15*z["eda"]) + min(12, worker.time_on_task/600))
        readiness = clamp(105 - .58*load - .35*fatigue)
        interruption = clamp(8 + worker.current_task_priority*12 + load*.22 + min(8, worker.time_on_task/300))
        confidence = round(min(.94, window.quality * (len(window.features)/len(FEATURES)) * .9), 2)
        return CognitiveState(cognitive_load=load, readiness=readiness, fatigue=fatigue, interruption_cost=interruption,
                              confidence=confidence, trend=self._trend(readiness-previous.readiness))

    @staticmethod
    def _trend(change: float) -> str:
        return "up" if change > .3 else "down" if change < -.3 else "stable"
