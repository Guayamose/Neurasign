# Streaming engine interface

The engine accepts timestamped raw samples, computes a trailing 60-second window every 10 seconds and optionally evaluates a research model. The first result needs 60 seconds of evidence. It does not wait for a task to finish or receive a task identifier. Computation latency and the evidence-window duration are separate.

This interface is implemented and exercised with recorded UNIVERSE data. It is not connected to the company dashboard or a deployed background worker. Wearable hardware, transport latency, device clock synchronization and cross-device inference remain unvalidated.

## Signals and normalization

| Engine channel | Canonical engine unit | Existing API metric | Existing API canonical unit |
| --- | --- | --- | --- |
| bvp | au | blood_volume_pulse | a.u. |
| eda | uS | electrodermal_conductance | µS |
| temperature | degC | skin_temperature | °C |
| acc_x | g | acceleration_x | g |
| acc_y | g | acceleration_y | g |
| acc_z | g | acceleration_z | g |
| heart_rate | bpm | heart_rate | bpm |

The current model profile requires the first six channels. Heart rate is optional because pulse intervals can sometimes be extracted from BVP; untrustworthy intervals remain missing. Actual sampling rates must be supplied, never inferred from the wearable's brand. The training recordings use 64-Hz BVP, 4-Hz EDA/temperature, 32-Hz acceleration and 1-Hz heart rate. Pulse extraction requires at least 16 Hz; accepting a rate at the interface does not establish model accuracy at that rate.

No generic PPG channel, ECG signal, optical beat interval, overnight HRV summary or device-relative temperature is silently substituted for another quantity. The model uses pulse-interval variability, not ECG-derived HRV. Missing required channels produce `insufficient_data`.

## Local raw-sample stream

From the engine directory:

```bash
.venv/bin/python scripts/stream_causal.py < samples.jsonl
```

Each line is one event. Example shape (illustrative values only):

```json
{"type":"samples","channel":"eda","unit":"uS","sample_rate_hz":4,"timestamps":[0,0.25,0.5,0.75],"values":[1.1,1.12,1.13,1.11]}
{"type":"watermark","timestamp":1}
```

Deliver blocks for every available channel, then advance the watermark after all available samples strictly before that time have arrived. All channels must share a clock. Receive-time timestamps from unrelated device packets are not automatically synchronized. Future buffered samples cannot affect an earlier window. Late samples and out-of-order blocks are rejected; the upstream ingestion queue must order accepted records before calling the engine.

Buffers are bounded to 180 seconds per channel, and normal advancement prunes them to the last 60 seconds. A watermark jump over 180 seconds is rejected; a long interruption requires a fresh stream and warmup. Gaps do not get interpolated. An optional `--features-only` mode runs sensor processing before a model is available.

## Existing observation blocks

`ObservationBridge` accepts the current observation shape after the server has authorized the member/source and converted units. The bridge reconstructs sample timestamps from `measured_at` and `sample_offsets_ms`; it accepts both the API's persisted Unix-second timestamps and timezone-qualified timestamp strings. It verifies the final scalar, rejects summaries and keeps identical retries idempotent within its bounded retry cache. A changed duplicate ID or different source is rejected.

Pass `--binding binding.json` to the CLI, with a trusted source ID and sampling rates:

```json
{
  "source_id": "authorized-source-id",
  "sample_rates": {
    "blood_volume_pulse": 64,
    "electrodermal_conductance": 4,
    "skin_temperature": 4,
    "acceleration_x": 32,
    "acceleration_y": 32,
    "acceleration_z": 32,
    "heart_rate": 1
  }
}
```

Input lines then use `{"type":"observation","observation":{...}}`, interspersed with watermark events. This local CLI is not an HTTP endpoint or an authentication mechanism. A production consumer must create one buffer per authorized organization/member/source, obtain the binding from trusted server state and process only newly accepted records. It must clear buffers on pause, revocation, deletion or source/cadence changes. This research turn does not implement that consumer or its persistence/restart lifecycle.

## Output semantics

- `features_ready`: physiological features are available when running without a model.
- `insufficient_data`: channels, timing or basic signal checks do not support this profile; no state estimates are emitted.
- `experimental_estimates`: a research model evaluated the causal window. Ratings target questionnaire intervals, not independently observed instantaneous states.
- Per-head `no_predictive_model_selected`: selection preferred a constant; the engine omits a rating instead of presenting that constant as signal interpretation.

`confidence` is null. Quality flags describe missingness, motion and pulse extraction heuristics, not probability of a correct prediction. Internal training imputes missing feature values inside fitting folds; the external feature output retains missing values as null.

## Recorded end-to-end check

```bash
.venv/bin/python scripts/train_causal.py
.venv/bin/python scripts/replay_causal.py --participant UN_101 --session Lab1 --seconds 180 --write-events results/causal-v3/replay-events.jsonl --output results/causal-v3/replay.json
.venv/bin/python scripts/stream_causal.py < results/causal-v3/replay-events.jsonl > results/causal-v3/stream-output.jsonl
```

The replay sends real sensor values in one-second blocks, advances time in 10-second steps and compares every streamed feature vector with the same timestamp's recording prefix. The output explicitly identifies recorded input. Synthetic signals exist only in unit tests for causality, known pulse recovery and failure cases.

The [experiment report](003-causal-results.md) separates successful streaming computation from predictive accuracy against weak questionnaire labels.
