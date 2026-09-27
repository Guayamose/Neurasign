# Interactive demo and example workflows

This document describes `/demo` and the legacy local demo API. These routes are disabled in production. For the company application, see [Company workspace](company-workspace.md).

Server and dashboard project inside the [NEURASIGN workspace](../../README.md). All commands and paths below are relative to `neurasign_server_dashboard/`. The implemented [NEURASIGN Link native app](../../neurasign_phone_app/mobile/README.md) uses the separate company [QR enrollment and gateway contract](phone-onboarding.md); the legacy `/api/live/readings` example below is not that app's upload endpoint.

**Monitor physiological signals.** The demo illustrates team monitoring and separate example use cases. A fresh checkout works with included synthetic signals and labels them **Illustrative data**. Imported UNIVERSE recordings are optional and appear as **Recorded wearable data**. Its relative state indices are demonstration estimates, not validated company-device measurements or predictions from the separate `/models` research service.

Next.js + TypeScript dashboard · FastAPI + Pydantic API · physiological monitoring and charts · personal reference normalization · Jev routing · Gemini analysis.

## Start locally

Requirements: Python 3.11+, Node.js 20.9+ (22 recommended), npm and Docker for the local Firebase emulators. `uv` is optional and speeds up Python setup.

```bash
make setup
make dev
```

Open **http://localhost:3000/demo**. API docs: http://localhost:8000/docs. `Ctrl+C` stops the development processes; `docker compose stop emulator` stops the emulators. The web app and API bind to loopback for a private local session. If ports 3000/8000 are occupied, stop the conflicting process first.

The server workspace's existing `.env` is preserved. **Do not copy `.env.example` over it.** Python loads the existing `JEV_API_key` and `Google_AI_API_key` names without printing them. These keys are optional for the local incident example; the demo starts without them. Jev and Gemini use configured credentials on the server; no API key is passed to Next.js or embedded in a browser bundle. Missing credentials and external failures have visible local fallbacks so the workflow remains usable.

Docker alternative (Docker Compose 2.24+):

```bash
docker compose up --build
```

Compose injects `.env` into the API container only. The build context excludes environment files. Existing imported recordings are mounted read-only. See the [verification record](verification.md) for checks performed on the current revision. Run one startup path at a time: `docker compose down` stops the containers before switching to `make dev`.

## Monitor the team

**Team signals** is the demo's starting point. It shows the same two fictional workers throughout: Alex and Sam. Select a person and a signal to inspect physiological summaries and time-series charts. **Experimental estimates** contains the workload, readiness and fatigue formula indices; interruption cost is also used in the secondary examples. Monitoring runs independently of those examples. The company application at `/` has a separate team roster and access controls.

When the imported recording is present, the dashboard starts with two minutes of actual replay history and continues at 10×. The charts show mean heart rate in bpm, pulse-derived HRV (RMSSD) in milliseconds, mean EDA in µS, skin temperature in °C, and movement variability in g. These are recorded window summaries, not raw PPG or ECG waveforms. The source indicator distinguishes real UNIVERSE recordings, synthetic replay, Manual controls, and Live gateway input.

Physiological measurements use physical units. Cognitive load, readiness, fatigue, and interruption cost are separate inferred relative indices on a 0–100 scale. Reference values come from each recording's calibration period; they are not clinical normal ranges. Recorded cognitive-history curves are recomputed estimates using the current staged work context, not observed historical diagnoses.

Replay history uses recording-relative seconds; Live history uses device timestamps. Missing features appear as gaps. Manual mode supplies cognitive indices directly and has no physiological measurements to display. Live input that becomes stale retains its earlier history while current physiological values become unavailable.

Use the question-mark button beside a metric or the metric guide for its plain-language meaning and units. **Compare with personal reference**, **Experimental estimates** and **Recording & signal details** reveal additional context without crowding the main chart. Signal colors identify chart series; they are not medical thresholds.

See [dataset processing and chart interpretation](dataset.md) for exact windows, units, provenance, missing data, and reference calculations.

## Manager perspective

Choose **Manager preview** next to **Team signals** to see each named employee’s interpreted state and experimental indices, without their physiological measurements. It uses the same replay/manual/live demo interpretations as Team signals. This is a browser presentation filter, not a server permission boundary, and it does not change company manager permissions. Open directly at `/demo#manager`. See [Manager preview](manager-preview.md) for scope and privacy limitations.

## Explore work examples

The main tabs are **Team signals**, **Manager preview** and **Use cases**. The Use cases page opens three secondary examples using the same current worker states. Switching sections preserves the signal source and does not start an incident.

| Section | What it shows or does |
| --- | --- |
| **Team signals** | Detailed demo measurements, personal references, trends, and experimental indices |
| **Manager preview** | Individual conclusions, experimental indices and their trends; physiological measurements omitted |
| **Use cases → Break suggestions** | Explains an illustrative pause suggestion; **Draft suggestion** creates a downloadable local draft |
| **Use cases → Team check-ins** | Explains whether to suggest an asynchronous update or a short check-in; **Draft agenda** creates a downloadable local draft |
| **Use cases → Incident walkthrough** | Runs a connected workflow with Jev assignments, Gemini artifacts, and explicit human decisions |

Wellbeing and focus use local rules, show their reasons, and disable suggestions when state confidence is insufficient. Their drafts are not sent to anyone and do not change a calendar.

For the incident example:

1. Open **Use cases → Incident walkthrough** and click **Start investigation**. The sample case, **Checkout is slow**, moves through **Investigate → Human decision → Check & report**. Jev chooses among eligible owners using the current monitoring source and states when configured; otherwise the labeled local routing policy is used.
2. Open **Read full analysis** when Gemini's diagnosis draft is ready. Each step shows its owner and result; **Assignment & execution details** provides routing and model provenance.
3. Click **Confirm diagnosis** after reviewing the evidence. This records the human review and unlocks the separate recovery decision.
4. Click **Approve recovery plan** when the decision is ready. Gemini checks the sample recovery data and writes the report. **Case complete** then offers **Read incident report**.

Worker identities, work context, and incident evidence are fictional demonstration inputs. **Gemini generates AI artifacts through real API calls**, and **Jev makes real routing selections** when configured. Starting an incident preserves the selected monitoring source. No production database is accessed, changed, or certified as recovered.

Model response time and the two human review actions determine completion time. Diagnosis and the critical decision do not complete on a timer. As state changes, the routing policy reconsiders unfinished work and explains any resulting reassignment. Model or network failures appear as explicit fallback results, not successful Gemini calls.

Open **Presenter controls** on **Team signals** to choose **Recorded playback**, **Manual scenario**, or **Live input**, and playback speeds of 1×, 5×, 10×, or 30×. Despite the playback control's label, a fresh checkout replays synthetic signals; the source banner identifies them. Manual mode exposes the relative-index sliders. **Pause recording** stops signal playback while eligible background AI work can continue. Example start, review, approval, and resolution preserve the monitoring playback choice. **Restart demo** resets the demo and reloads the preferred source; selecting playback alone resumes the currently loaded replay.

## Input modes

| Mode | Input | How to use |
| --- | --- | --- |
| Replay | Included synthetic fixture by default; imported UNIVERSE feature windows when present | Select Recorded playback; choose speed |
| Manual | Direct relative state indices | Select Manual scenario; adjust each worker's workload, readiness, fatigue and interruption cost |
| Live | Legacy local demo feature readings | Select Live input and POST the payload below; routing uses the same inference/orchestration path |

Manual changes immediately reroute unfinished work using the same policy. Completed steps are retained; dependencies and human-judgment requirements still apply. Scores are relative within-person estimates; a readiness index of 73 does **not** mean “73% medically ready.”

### UNIVERSE data

The adapter prefers `data/universe/replay.json` and falls back to `data/fixtures/replay.json`. Dataset provenance is visible in the dashboard. Real data can be imported without changing the rest of the application:

```bash
python3 scripts/download_universe.py --help
python3 scripts/preprocess_universe.py --help
```

See [dataset processing and exact import commands](dataset.md) for the bounded downloader, Empatica feature extraction, participant mapping, baseline calculation, attribution, and canonical CSV import. Restart the API after importing new data. Raw participant recordings and processed real data are excluded from version control; the deterministic fixture is included.

Source: [UNIVERSE dataset, Zenodo record 10371068](https://zenodo.org/records/10371068). This app makes no claim that the workload dataset validates the heuristic readiness/fatigue indices or the fictional enterprise scenario.

### Legacy local live-input example: ESP32 / MAX30102 / GSR

This development-only endpoint illustrates a custom device or test gateway. It has no company enrollment or device authentication. The implemented phone app instead uses authenticated company `/api/v1` endpoints, as described in [phone onboarding](phone-onboarding.md) and [multi-signal telemetry](telemetry.md).

The device or its private gateway derives heart-rate/variability features from a temporal PPG window. A raw PPG amplitude is insufficient to estimate HRV. Send normalized-schema physiological features (physical feature units, before personal z-score normalization) to:

```http
POST http://localhost:8000/api/live/readings
Content-Type: application/json

{
  "worker_id": "aoi",
  "timestamp": "2026-09-19T12:00:00Z",
  "ppg": {"heart_rate": 74, "hrv": 65},
  "eda": {"tonic": 1.5},
  "temperature": 32.5,
  "movement": {"magnitude": 0.1},
  "quality": 0.9
}
```

Use a current UTC timestamp. `heart_rate` is beats/minute, `hrv` is RMSSD in milliseconds, EDA is microsiemens, skin temperature is °C, and movement is the standard deviation of acceleration magnitude in g. Send at least five readings spanning eight seconds for a populated ten-second live window. Readings must be strictly increasing per worker and no more than 30 seconds old or five seconds in the future; invalid readings return HTTP 422. After 15 seconds without fresh readings, current monitoring features become unavailable while history is retained. Inference confidence decays and reaches zero after 60 seconds. Stable worker IDs are `alex` (displayed as Alex) and `aoi` (displayed as Sam). HTTP is this demo's ingestion interface; `/ws` carries the monitoring snapshot and workflow updates.

Live input uses an independent **provisional personal reference**, never the imported replay participants' baselines. Until hardware calibration is implemented, live confidence is capped at 0.54. Human assignments require confidence of at least 0.25; falling below that threshold queues human work while eligible AI steps remain available. The confidence threshold is a demo policy, not a scientifically calibrated cutoff. Custom ESP32 firmware and device-specific baseline calibration are not implemented here. Company phone credential authentication is implemented separately; it does not secure this legacy local endpoint.

## Routing and inference

```text
SignalSource → temporal windows → feature extraction → personal baseline
→ CognitiveState → expertise + availability + work context → routing
→ dependency-aware workflow → WebSocket → dashboard
```

`UniverseReplaySource`, `ManualSignalSource` and `LiveWearableSource` implement one acquisition interface. Inference and routing are separate, replaceable modules. Personal means and standard deviations normalize features within each participant. Load, readiness and fatigue are deliberately documented statistical/demo heuristics; interruption cost also incorporates scenario priority and time on task.

Routing chooses **HUMAN**, **AI**, **HUMAN + AI**, or **DELAY**. It respects expertise and human judgment, uses state/work context to rank eligible candidates, and reconsideration changes only unfinished work. Assignment explanations connect meaningful state changes to work allocation.

See [architecture, scientific scope and privacy boundaries](architecture.md) and [API contract](api-contract.md).

Developer API controls retain `run_demo` for a synthetic 30× replay scenario and `stress_aoi` for an explicit Manual capacity change. These are separate from the simplified incident interface; they use the same inference/routing implementation.

### Jev integration

Jev is selected by default when its existing key is configured. It calls the official [TypeSafe System One API](https://docs.typesafe.ai/introduction/quickstart) with typed Choice questions over locally eligible candidates. It uses `JEV_API_key`; `JEV_API_KEY` and `TYPESAFE_API_KEY` are supported aliases. Use `ROUTING_PROVIDER=deterministic` or the provider control API to select the local policy explicitly. Optional settings are in `.env.example`.

Only allow-listed derived work context is sent. Raw sensor samples, baselines, and other API credentials never leave through this integration. Low-confidence, invalid, timed-out or failed responses fall back to the deterministic policy, with a bounded retry circuit. Assignment details identify whether Jev or the local router selected that owner. Local eligibility rules remain binding even when Jev makes the choice.

### Gemini execution

Gemini uses the existing `Google_AI_API_key` and the [generateContent API](https://ai.google.dev/api/generate-content) to analyze the supplied incident logs, draft a diagnosis, evaluate the supplied recovery evidence, and write documentation. Its work appears as inspectable artifacts. `GEMINI_MODEL` selects the model (default `gemini-3.8-flash`); `GEMINI_TIMEOUT_SECONDS` bounds each request, and `GEMINI_ENABLED=false` explicitly selects fallback execution. The configured model and each result's execution provenance are exposed without credentials. Network requests run in the background so worker-state updates and controls remain responsive.

Gemini receives bounded incident evidence and earlier workflow outputs, not worker biometric recordings. Diagnosis requires an explicit human review action; the critical architecture decision requires a separate approval. Neither AI provider can authorize or execute production changes. A failed or unconfigured Gemini call produces a clearly labeled `local_fallback` artifact. Each result exposes its execution provenance; the API also records provider status and successful/fallback call counts.

## Physiological summaries and private research

The team-lead dashboard and WebSocket expose physiological feature summaries, recording references, timestamped histories, and inferred work-relevant state. This is an intentional monitoring surface. Full raw sensor waveforms, private research diagnostics, and API credentials are not part of that ordinary snapshot.

A developer can enable the separate `GET /api/research` endpoint for detailed source/window, normalization, and inference inspection:

```bash
RESEARCH_ENABLED=true make dev
```

Restart required. Requests must also originate from loopback, or provide a configured `RESEARCH_TOKEN` through the `X-Research-Token` header. Research inspection is a developer API surface, separate from the dashboard. This gate protects optional developer diagnostics; ordinary demo physiological-summary monitoring does not require it. The legacy demo has no company authentication, tenant isolation or durable retention; the separate [company workspace](company-workspace.md) implements those controls.

## Verify

```bash
make test                       # inference, routing, human gates, providers, source and API tests
make build                      # production frontend compilation/type checks
.venv/bin/python scripts/monitoring_smoke.py     # monitoring data/controls independent of incidents
make smoke                      # running HTTP + WebSocket integration (start make dev first)
.venv/bin/python scripts/smoke.py --require-live  # require actual Jev and Gemini success
.venv/bin/python scripts/check_secrets.py
```

Optional browser regression (requires Chrome and Playwright):

```bash
uv pip install --python .venv/bin/python playwright
.venv/bin/python scripts/browser_monitoring_smoke.py
.venv/bin/python scripts/browser_controls_smoke.py
.venv/bin/python scripts/browser_smoke.py --require-live
```

The primary browser regression covers the monitoring dashboard, physiological charts, and secondary tabs. The controls regression covers playback, Manual/Live sources, and local example drafts. The incident browser check requires real provider provenance, both human review gates, and generated artifacts while preserving the selected monitoring source. Screenshots are saved under ignored `artifacts/`.

See [the verification record](verification.md) for the scope and results of checks actually performed on this revision.

## Project map

```text
apps/web/                    Next.js dashboard, UI types, real-time client
services/api/neurasign/       Models, sources, inference, routing, orchestration, API, Jev, Gemini
data/fixtures/               Reproducible labeled synthetic windows
data/universe/               Locally downloaded/imported participant data (ignored)
scripts/                     Setup, startup, dataset import, integration checks
tests/                       Core behavior and failure-path tests
docs/                        API contract, architecture, dataset provenance
```

Demo state lives in one API process and resets when the process restarts. Run a single API worker for the local demo. These examples use unvalidated formula indices and optional real AI calls over sample operational evidence. Company persistence, phone enrollment and deployment are separate from this legacy demo contract; see the [server overview](../README.md).
