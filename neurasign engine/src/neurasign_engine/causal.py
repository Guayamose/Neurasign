"""Shared trailing-window extraction for recorded replay and incoming samples.

Every calculation sees only samples with timestamps in [end - 60, end).
Signal-quality checks are engineering checks, never confidence probabilities.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math

import numpy as np
from scipy.signal import butter, find_peaks, sosfilt, sosfilt_zi, welch

PIPELINE = "wrist_raw_causal_60s_v3"
WINDOW = 60.0
STEP = 10.0
CHANNELS = {"bvp": (64., "au"), "eda": (4., "uS"), "temperature": (4., "degC"),
            "acc_x": (32., "g"), "acc_y": (32., "g"), "acc_z": (32., "g"),
            "heart_rate": (1., "bpm")}
REQUIRED = tuple(name for name in CHANNELS if name != "heart_rate")
STAT_NAMES = ("mean", "median", "std", "range", "slope_per_second", "last20_minus_first20")
FEATURES = (
    [f"{name}_{stat}" for name in ("eda", "temperature", "motion", "heart_rate") for stat in STAT_NAMES]
    + ["eda_positive_derivative", "eda_fast_variation", "motion_enmo_mean_g", "motion_jerk_rms_g_s",
       "acc_x_std_g", "acc_y_std_g", "acc_z_std_g", "acc_clipped_fraction",
       "bvp_std", "bvp_spectral_concentration", "bvp_periodicity", "pulse_rate_bpm",
       "pulse_interval_mean_ms", "pulse_interval_sdnn_ms", "pulse_interval_rmssd_ms",
       "pulse_interval_pnn50", "pulse_interval_iqr_ms", "pulse_valid_interval_fraction",
       "pulse_rate_device_difference_bpm"]
)


@dataclass
class Trace:
    times: np.ndarray
    values: np.ndarray
    rate: float
    unit: str


def validate_trace(trace):
    t, x = trace.times, trace.values
    if t.ndim != 1 or x.ndim != 1 or len(t) != len(x):
        raise ValueError("One timestamp is required for each scalar sample")
    if not np.isfinite(t).all() or np.any(np.diff(t) <= 0):
        raise ValueError("Sample timestamps must be finite and strictly increasing")
    if not math.isfinite(trace.rate) or not 0 < trace.rate <= 1024:
        raise ValueError("A valid declared sampling rate is required")


def window_samples(trace, start, end):
    left, right = np.searchsorted(trace.times, [start, end], side="left")
    t, x = trace.times[left:right], trace.values[left:right]
    valid = np.isfinite(x)
    t, x = t[valid], x[valid]
    expected = (end - start) * trace.rate
    coverage = min(1., len(x) / expected)
    gaps = np.diff(np.r_[start, t, end])
    max_gap = float(gaps.max()) if len(gaps) else end - start
    cadence_error = float(np.median(abs(np.diff(t) * trace.rate - 1))) if len(t) > 1 else 1.
    quality = {"coverage": coverage, "max_gap_seconds": max_gap,
               "cadence_relative_error": cadence_error, "samples": len(x)}
    return t, x, quality


def statistics(t, x, start, end):
    if len(x) < 2:
        return {key: np.nan for key in STAT_NAMES}
    centered = t - t.mean()
    slope = np.dot(centered, x - x.mean()) / max(np.dot(centered, centered), 1e-12)
    first, last = x[t < start + 20], x[t >= end - 20]
    return dict(zip(STAT_NAMES, [float(x.mean()), float(np.median(x)), float(x.std()),
        float(np.quantile(x, .9) - np.quantile(x, .1)), float(slope),
        float(last.mean() - first.mean()) if len(first) and len(last) else np.nan]))


@lru_cache(maxsize=32)
def pulse_filter(rate):
    if rate < 16:
        raise ValueError("Pulse-wave profile requires at least 16 samples/second")
    return butter(2, [.5, 4.], btype="bandpass", fs=rate, output="sos")


def extract_window(traces: dict[str, Trace], end: float):
    if not math.isfinite(end):
        raise ValueError("Window end must be finite")
    start = end - WINDOW
    features = {key: np.nan for key in FEATURES}
    quality, samples, reasons, flags = {}, {}, [], []
    for name in REQUIRED:
        if name not in traces:
            reasons.append(f"missing_{name}")
    for name, trace in traces.items():
        if name not in CHANNELS or trace.unit != CHANNELS[name][1]:
            raise ValueError("Unknown channel or noncanonical unit")
        t, x, q = window_samples(trace, start, end)
        samples[name] = (t, x)
        quality[name] = q
        if name in REQUIRED and (q["coverage"] < .95 or
                q["max_gap_seconds"] > max(.5, 2.5 / trace.rate) or q["cadence_relative_error"] > .1):
            reasons.append(f"incomplete_{name}")
    result = {"pipeline_id": PIPELINE, "window_start": start, "window_end": end,
              "window_seconds": WINDOW, "features": features, "quality": quality,
              "quality_flags": flags, "reasons": reasons, "confidence": None,
              "status": "insufficient_data"}
    if reasons:
        return result
    for name in ("eda", "temperature", "heart_rate"):
        if name in samples:
            t, x = samples[name]
            features.update({f"{name}_{key}": value for key, value in statistics(t, x, start, end).items()})
    eda_t, eda = samples["eda"]
    if np.any(eda < 0) or np.any(eda > 100):
        reasons.append("invalid_eda_range")
    features["eda_positive_derivative"] = float(np.maximum(np.diff(eda), 0).sum() / WINDOW)
    features["eda_fast_variation"] = float(np.std(np.diff(eda)))
    temp = samples["temperature"][1]
    if np.any((temp < 10) | (temp > 45)):
        reasons.append("temperature_outside_sensor_profile")
    # Recompute magnitude from aligned axes; the published ACC_MAG has bad rows.
    at = samples["acc_x"][0]
    if not all(np.array_equal(at, samples[name][0]) for name in ("acc_y", "acc_z")):
        reasons.append("misaligned_acceleration_axes")
        return result
    axes = np.column_stack([samples[name][1] for name in ("acc_x", "acc_y", "acc_z")])
    magnitude = np.linalg.norm(axes, axis=1)
    features.update({f"motion_{key}": value for key, value in statistics(at, magnitude, start, end).items()})
    features["motion_enmo_mean_g"] = float(np.maximum(magnitude - 1., 0).mean())
    features["motion_jerk_rms_g_s"] = float(np.sqrt(np.mean(np.square(np.diff(magnitude) / np.diff(at)))))
    for i, name in enumerate(("acc_x", "acc_y", "acc_z")):
        features[f"{name}_std_g"] = float(axes[:, i].std())
    features["acc_clipped_fraction"] = float((np.abs(axes) >= 1.98).any(axis=1).mean())
    motion_artifact = features["motion_std"] > .2 or features["acc_clipped_fraction"] > .05
    if motion_artifact:
        flags.append("pulse_variability_masked_during_high_motion")
    bt, bvp = samples["bvp"]
    rate = traces["bvp"].rate
    if rate < 16 or np.std(bvp) < 1e-8:
        reasons.append("unusable_pulse_wave")
        return result
    sos = pulse_filter(rate)
    # Forward-only filtering; initialization and all statistics use this past window.
    filtered, _ = sosfilt(sos, bvp, zi=sosfilt_zi(sos) * bvp[0])
    settle = int(2 * rate)
    filtered, bt = filtered[settle:], bt[settle:]
    features["bvp_std"] = float(np.std(filtered))
    frequencies, power = welch(filtered, fs=rate, nperseg=min(len(filtered), int(8 * rate)))
    band = (frequencies >= .5) & (frequencies <= 4.)
    peak = int(np.argmax(np.where(band, power, -1)))
    concentration = power[np.abs(frequencies - frequencies[peak]) <= .25].sum() / max(power[band].sum(), 1e-12)
    features["bvp_spectral_concentration"] = float(min(1., concentration))
    centered = filtered - filtered.mean()
    lag = int(round(rate / max(frequencies[peak], .5)))
    features["bvp_periodicity"] = float(np.dot(centered[lag:], centered[:-lag]) /
        max(np.linalg.norm(centered[lag:]) * np.linalg.norm(centered[:-lag]), 1e-12))
    peaks, _ = find_peaks(filtered, distance=max(1, int(.3 * rate)), prominence=max(filtered.std() * .3, 1e-9))
    intervals = np.diff(bt[peaks]) * 1000.
    valid = (intervals >= 300) & (intervals <= 2000)
    fraction = float(valid.mean()) if len(valid) else 0.
    features["pulse_valid_interval_fraction"] = fraction
    if valid.sum() >= 20 and fraction >= .8 and features["bvp_periodicity"] >= .2 and not motion_artifact:
        rr = intervals[valid]
        features["pulse_rate_bpm"] = float(60000. / np.median(rr))
        features["pulse_interval_mean_ms"] = float(rr.mean())
        features["pulse_interval_sdnn_ms"] = float(rr.std(ddof=1))
        # Only adjacent valid intervals contribute; never bridge a rejected beat.
        adjacent = valid[1:] & valid[:-1]
        differences = np.diff(intervals)[adjacent]
        if len(differences) >= 10:
            features["pulse_interval_rmssd_ms"] = float(np.sqrt(np.mean(differences ** 2)))
            features["pulse_interval_pnn50"] = float(np.mean(abs(differences) > 50))
        features["pulse_interval_iqr_ms"] = float(np.quantile(rr, .75) - np.quantile(rr, .25))
        if np.isfinite(features["heart_rate_median"]):
            features["pulse_rate_device_difference_bpm"] = abs(features["pulse_rate_bpm"] - features["heart_rate_median"])
    else:
        flags.append("pulse_variability_unavailable")
    if not reasons:
        result["status"] = "features_ready"
    return result


class CausalStream:
    """One authorized person/source stream. Caller owns auth and scheduling.

    Pass a watermark only after delivering available channel blocks up to that
    time. Late/duplicate samples are rejected; missing channels cause abstention.
    """
    def __init__(self):
        self.traces: dict[str, Trace] = {}
        self.last_watermark = -np.inf
        self.next_end = None
        self.first_sample = None

    def push(self, channel, times, values, rate, unit):
        if channel not in CHANNELS or unit != CHANNELS[channel][1]:
            raise ValueError("Unsupported channel or unit; normalize in the source adapter")
        trace = Trace(np.asarray(times, dtype=float), np.asarray(values, dtype=float), float(rate), unit)
        validate_trace(trace)
        if not len(trace.times) or not np.isfinite(trace.values).all():
            raise ValueError("Provide a nonempty finite sample block")
        if trace.times[0] < self.last_watermark:
            raise ValueError("Late samples cannot revise emitted windows")
        previous = self.traces.get(channel)
        if previous is not None:
            if previous.rate != rate or (len(previous.times) and trace.times[0] <= previous.times[-1]):
                raise ValueError("Changing cadence, duplicates or out-of-order samples require a new stream")
            trace = Trace(np.r_[previous.times, trace.times], np.r_[previous.values, trace.values], rate, unit)
        if len(trace.times) > rate * 180:
            raise ValueError("Advance the watermark; stream buffers are limited to 180 seconds")
        self.traces[channel] = trace
        self.first_sample = min(self.first_sample if self.first_sample is not None else np.inf, float(trace.times[0]))

    def advance(self, watermark):
        if not math.isfinite(watermark) or watermark < self.last_watermark:
            raise ValueError("Watermarks must be finite and monotonic")
        if self.first_sample is None:
            return []
        if self.next_end is None:
            self.next_end = math.ceil((self.first_sample + WINDOW) / STEP) * STEP
        outputs = []
        while self.next_end <= watermark:
            outputs.append(extract_window(self.traces, self.next_end))
            self.next_end += STEP
        self.last_watermark = watermark
        cutoff = watermark - WINDOW
        for name, trace in self.traces.items():
            keep = trace.times >= cutoff
            self.traces[name] = Trace(trace.times[keep], trace.values[keep], trace.rate, trace.unit)
        return outputs


def json_ready(value):
    if isinstance(value, dict):
        return {key: json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.integer):
        return int(value)
    return value
