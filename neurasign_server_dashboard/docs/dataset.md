# Recorded signals and deterministic replay

Normal Replay uses **real physiological recordings from two UNIVERSE participants**, `UN_101/Lab1` and `UN_103/Lab1`, when the locally imported `data/universe/replay.json` exists. This workspace already includes that import; recorded data is excluded from version control, and a fresh checkout uses the synthetic fixture until the import commands below are run. The display names Alex and Sam are fictional; they do not identify the participants. No incident, occupational performance, readiness, or fatigue ground truth comes from this dataset.

The **developer guided-scenario API action** (`run_demo`) uses a separate, openly synthetic signal fixture in `data/fixtures/replay.json` for a repeatable capacity-change trajectory at 30×. An ordinary incident preserves the selected monitoring source. The `stress_aoi` API action can also introduce an explicit Manual state change. These developer controls are separate from the simplified incident tab. Diagnosis review and architecture approval require human actions, so there is no guaranteed presentation duration. The source label distinguishes recorded replay from synthetic or manual input. Synthetic trajectories must never be presented as study results.

## Source and attribution

[UNIVERSE, Zenodo record 10371068](https://zenodo.org/records/10371068), by Christoph Anders, Sidratul Moontaha, Samik Real, and Bert Arnrich, is distributed under **CC BY 4.0**. It contains recordings across controlled and uncontrolled sessions from 24 participants. The archive publishes Empatica E4 and Muse recordings along with processing products. See the [authors' processing code](https://github.com/HPI-CH/UNIVERSE) and [Scientific Data descriptor](https://doi.org/10.1038/s41597-024-03738-7).

The locally imported replay contains transformed Empatica features, not the original raw recording. Its `metadata` includes the attribution, selected participants/sessions, feature definitions, calibration intervals, and source-member checksums. Retain this attribution when redistributing these derived features.

## Download a small verified subset

The original files are two archives of approximately 10 GB each. Our downloader reads their ZIP directory and retrieves selected members using HTTP byte ranges. Downloading both chosen sessions used **5.51 MiB**, including approximately 4.56 MiB of archive directory. It never falls back to downloading a whole archive when a server ignores Range requests.

```sh
python3 scripts/download_universe.py --list
python3 scripts/download_universe.py --list-members --participants UN_101 UN_103 --session Lab1
python3 scripts/download_universe.py --download --participants UN_101 UN_103 --session Lab1
python3 scripts/preprocess_universe.py --participants UN_101 UN_103 --session Lab1
```

These scripts use only the Python standard library. They need no API key. Restart the API after importing to load the new replay. `--help` documents all options.

`--files HR.csv IBI.csv EDA.csv TEMP.csv ACC.csv` narrows the download further; `Task_Labels.csv` is included for provenance and inspection but is not used in cognitive inference. The default total download limit is 32 MiB, adjustable with `--max-download-mb`. A single decompressed member is limited to 50 MB. Files are written only within the output directory. ZIP member CRCs are checked and their SHA-256 hashes recorded in `data/universe/raw/manifest.json`; the entire archive's MD5 cannot be checked from a subset download. Raw files are excluded from version control.

Selected sessions currently come from `UNIVERSE_UN_101_to_UN_112.zip`. Other participants through `UN_124` and `Lab1`/`Lab2` sessions are supported. The native downloader does not currently select nested `Wild` recording folders; export those to the canonical feature CSV below, or extend the explicit path selector. The import script also accepts fully downloaded/extracted archives through `--input`.

## Raw Empatica processing

Empatica CSV files have the recording's Unix start time in the first row and sampling frequency in the second row. IBI is different: its first row has the start time, and subsequent rows contain time offsets and interbeat intervals in seconds. `info.txt` bundled with each recording documents the units. The importer respects independent signal start times, including the HR stream's offset.

| App feature | Recorded input | Transformation | Unit |
| --- | --- | --- | --- |
| `heart_rate` | `HR.csv` | Arithmetic mean of valid samples | beats/minute |
| `hrv` | `IBI.csv` | RMSSD over consecutive usable intervals; at least 10 pairs | milliseconds |
| `eda` | `EDA.csv` | Arithmetic mean of valid samples | microsiemens |
| `temperature` | `TEMP.csv` | Arithmetic mean of valid samples | °C |
| `movement` | `ACC.csv` | Standard deviation of acceleration vector magnitude; sensor counts divided by 64 | g |

HRV here is pulse-derived variability, not ECG-derived HRV. The importer does not execute upstream pickle files. It reads simple CSV data and re-derives only the features needed for this MVP.

For both selected sessions, the original CSV rates are HR 1 Hz, EDA and temperature 4 Hz, and three-axis acceleration 32 Hz. IBI observations are irregularly timed. These source rates are not the monitoring chart resolution: the replay contains one summary row every ten source seconds.

Each feature window covers the previous **60 seconds**, emitted every **10 seconds**. This produces 181 feature windows per worker over 1,800 seconds of playback. The application smooths the most recent three feature windows; these overlap, so they are not independent observations.

The monitoring charts display the direct recorded feature rows. Current cognitive inference separately smooths up to three rows, whose combined underlying support can span 80 seconds. A direct physical-unit reading and its inferred cognitive index therefore need not move in lockstep.

## Monitoring interpretation

The main team-lead view exposes these physiological summaries, selected personal reference values, and inferred state histories. It does not provide raw PPG, ECG, or continuous accelerometer waveforms. Label the EDA trace as mean conductance, the temperature trace as skin temperature, and the movement trace as acceleration-magnitude variability; no tonic/phasic EDA decomposition or core body temperature is available.

Replay time is measured in seconds relative to each participant's selected segment. The participants were recorded in separate sessions, so aligning them on the app's replay axis does not mean their signals were recorded simultaneously. No recording date is substituted with the current wall-clock time.

The dashboard begins at a 120-second source cursor using already available recording rows. It exposes at most the most recent 90 rows through the current cursor, never future data. Physiological history is observed feature data; cognitive history is recomputed with the existing heuristic and current staged work context. It is not a stored historical assessment of either participant.

The real import has a missing HRV value for Sam at source second 420. Monitoring represents it as a gap/null with reduced quality. Inference can still use available neighboring windows; a missing measurement must not be drawn as zero or silently presented as a new observation. Manual control mode has no physiological measurements. Stale live data remains available as past history while current values are marked unavailable.

By default, processing excludes the first 600 seconds after the common stream start, uses the next 300 seconds for personal calibration, and begins replay with a full trailing window after calibration. This interval and the choice of `UN_103` were selected for usable IBI coverage, without selecting for an incident outcome. `UN_102` was inspected but had many missing IBI windows. This is a recording reference period, **not a verified resting baseline** or a labeled low-workload segment. Override `--start-seconds`, `--baseline-seconds`, and `--duration-seconds` for other recordings.

Each baseline holds the mean and population standard deviation of that worker's calibration windows. Calibration windows are excluded from playback. Engineering standard-deviation floors are 3 bpm, 8 ms HRV, 0.10 µS EDA, 0.3 °C, and 0.02 g movement to avoid unstable division by very small variance. These are numerical safeguards, not clinical thresholds.

Physically implausible/nonfinite samples are rejected without shifting timestamps. Missing features are **omitted**, listed in `missing_features`, and given quality no greater than 0.35; they are not filled with fabricated recordings. Inference uses a neutral baseline contribution when a feature is unavailable after temporal smoothing. The included replay has zero windows with missing features for `UN_101` and one missing-HRV window for `UN_103`. Quality is a completeness heuristic capped at 0.85, not validated prediction confidence.

## Canonical feature CSV import

Any preprocessing pipeline can supply one CSV with these columns:

```csv
worker_id,timestamp,heart_rate,hrv,eda,temperature,movement,quality
alex,0,72,55,2.1,33.0,0.10,0.85
aoi,0,67,65,1.6,32.7,0.08,0.85
```

The example rows are **synthetic schema illustrations**, not UNIVERSE measurements. Include both `alex` and `aoi`, unique increasing timestamps in seconds per worker, at least three usable calibration windows for every feature, and additional playback windows. Blank feature cells mean missing measurements. `quality` is optional; if supplied it must be 0–1. Units must match the table. Raw EDA or BVP sample rows must first be converted to temporal features; renaming their columns is not sufficient.

```sh
# The default provenance is synthetic. This cannot silently claim real data.
python3 scripts/preprocess_universe.py --csv my_synthetic_features.csv --output data/fixtures/replay.json

# Use this only for features actually derived from the cited UNIVERSE recording.
python3 scripts/preprocess_universe.py --csv my_universe_features.csv \
  --kind universe --source-url https://zenodo.org/records/10371068 \
  --baseline-seconds 300 --window-seconds 60
```

The CSV importer computes separate baselines from each worker's first calibration segment, removes that segment, and shifts each playback timeline to zero. Column names are intentionally explicit; map external headers into this schema in your preprocessing. The citation requirement records provenance asserted by the importer; it does not authenticate the original measurements.

## Rebuild the presentation recording

```sh
python3 scripts/generate_fixtures.py
```

The fixture has its own explicit synthetic personal baselines. Alex starts at approximately 1.65 baseline deviations in the load-related channels and recovers. Sam remains near baseline, then rises between recording seconds 480 and 1,050 before recovering later. Small deterministic oscillations make the features less uniform. These trajectories flow through the same inference and routing code as real data. The separate `stress_aoi` API action applies an explicitly Manual state scenario through the common router.

The physiological fixture and `data/fixtures/incident.json` are **inputs** to the demonstration. They do not contain Gemini's generated answers. Configured Jev and Gemini make real provider calls, with successful model output distinguished from local fallback artifacts. The diagnosis remains open for human review before a separate architecture approval unlocks verification and documentation.

## Scientific and privacy limits

Directly observed values are sensor recordings; window summaries are derived features; personal z-scores are normalizations; cognitive load, readiness, fatigue, and interruption cost are **unvalidated product heuristics**. They are not diagnoses, productivity measurements, or validated estimates of a person's capacity. Movement, temperature, health, medication, exercise, sensor fit, and many other factors can affect the same signals. A high-load interpretation cannot be causally established from these features.

Real-data replay demonstrates data plumbing and changing estimates. It does not validate the routing algorithm or guarantee the presentation's deterioration pattern. The deterministic fixture demonstrates product behavior. Neither is evidence that a real participant should have been assigned or removed from work.

The manager snapshot intentionally includes selected physiological summary features, recording reference values, timestamped history, and inferred cognitive state. Full raw waveforms and detailed normalization/research diagnostics remain outside that ordinary monitoring view, and API credentials stay server-side. The optional research API is a local developer tool, disabled by default; this MVP does not implement the access controls, consent workflow, clinical validation, or worker protections needed for actual workforce deployment.
