"""Local engine bridge for the existing raw-observation shape.

Authentication, company/member binding and capability checks stay in the API.
Instantiate one bridge per already-authorized member/source; never share buffers.
"""
from collections import OrderedDict
from datetime import datetime
import hashlib
import json

import numpy as np

from .causal import CHANNELS, CausalStream, json_ready

METRICS = {"blood_volume_pulse": ("bvp", "a.u."),
           "electrodermal_conductance": ("eda", "µS"),
           "skin_temperature": ("temperature", "°C"),
           "heart_rate": ("heart_rate", "bpm"),
           "acceleration_x": ("acc_x", "g"),
           "acceleration_y": ("acc_y", "g"),
           "acceleration_z": ("acc_z", "g")}


class ObservationBridge:
    def __init__(self, stream, source_id, sample_rates):
        if not isinstance(source_id, str) or not source_id:
            raise ValueError("An authorized source binding is required")
        if any(metric not in METRICS or not np.isfinite(rate) or not 0 < rate <= 1024
               for metric, rate in sample_rates.items()):
            raise ValueError("Sample rates must describe supported raw channels")
        self.stream, self.source_id, self.sample_rates = stream, source_id, dict(sample_rates)
        self.seen = OrderedDict()

    def push(self, observation):
        if observation.get("source_id") != self.source_id:
            raise ValueError("Observation belongs to a different source binding")
        if (observation.get("interval_seconds") is not None or
                observation.get("measurement_kind", "sample") != "sample"):
            raise ValueError("Window/summary observations cannot substitute for raw samples")
        metric = observation.get("metric")
        if metric not in self.sample_rates:
            raise ValueError("No declared raw sampling rate for this metric")
        channel, unit = METRICS[metric]
        if observation.get("unit") != unit:
            raise ValueError("Pass canonical server units; engine does not guess source units")
        identifier = observation.get("id")
        if not isinstance(identifier, str) or not identifier:
            raise ValueError("Persistent observation ID is required")
        digest = hashlib.sha256(json.dumps(observation, sort_keys=True, allow_nan=False).encode()).hexdigest()
        if identifier in self.seen:
            if self.seen[identifier] != digest:
                raise ValueError("An observation ID was reused with different content")
            return False
        measured = observation["measured_at"]
        if isinstance(measured, (int, float)) and not isinstance(measured, bool):
            # The API stores normalized observations with Unix-second timestamps.
            timestamp = float(measured)
            if not np.isfinite(timestamp):
                raise ValueError("Measurement timestamp must be finite")
        elif isinstance(measured, str):
            measured = datetime.fromisoformat(measured.replace("Z", "+00:00"))
            if measured.utcoffset() is None:
                raise ValueError("Measurement timestamp requires a timezone")
            timestamp = measured.timestamp()
        else:
            raise ValueError("Expected an API Unix timestamp or timezone-qualified timestamp")
        samples = np.asarray(observation.get("samples", [observation["value"]]), dtype=float)
        offsets = np.asarray(observation.get("sample_offsets_ms", [0.]), dtype=float)
        if (samples.ndim != 1 or offsets.ndim != 1 or not 1 <= len(samples) <= 512 or
                len(samples) != len(offsets) or not np.isfinite(samples).all() or
                not np.isfinite(offsets).all() or np.any(np.diff(offsets) <= 0) or
                offsets[-1] != 0 or offsets[0] < -10000 or samples[-1] != observation["value"]):
            raise ValueError("Invalid raw block, offsets or final scalar")
        times = timestamp + offsets / 1000.
        self.stream.push(channel, times, samples, self.sample_rates[metric], CHANNELS[channel][1])
        self.seen[identifier] = digest
        while len(self.seen) > 2048:
            self.seen.popitem(last=False)
        return True


def dispatch(stream, event, model=None, bridge=None):
    kind = event.get("type")
    if kind == "samples":
        stream.push(event["channel"], event["timestamps"], event["values"], event["sample_rate_hz"], event["unit"])
        return []
    if kind == "observation":
        if bridge is None:
            raise ValueError("Configure an authorized source/rate binding before observations")
        bridge.push(event["observation"])
        return []
    if kind == "watermark":
        watermark = float(event["timestamp"])
        if stream.first_sample is not None:
            previous = max(stream.first_sample, stream.last_watermark)
            if watermark - previous > 180:
                raise ValueError("Watermark jump exceeds the buffer; start a new stream after a long interruption")
        outputs = stream.advance(watermark)
        return [model.predict(row) if model is not None else json_ready(row) for row in outputs]
    raise ValueError("Expected samples, observation or watermark event")
