# Trained model execution in the dashboard

The local **Model engine** workspace at `/models` runs saved fitted models on verified anonymous research records. The browser requests a record; the API forwards its allowlisted ID to a separate model service; the service verifies the exact model and feature-file hashes, computes a prediction and returns it beside the recorded reference.

These are actual model executions. The server never replaces a missing model with a formula, fabricates missing measurements or loads a model supplied by a browser. The separate team demo still labels its earlier formula estimates explicitly. Company observations and employee identities are outside the model service.

## Models and evidence windows

| Dashboard card | Fitted artifact | Input contract | Available records |
| --- | --- | --- | ---: |
| Stress condition | Experiment 022 selected ExtraTrees, 300 trees | One complete synchronized 60-second WESAD wrist window | 86 held-out windows |
| Daily readiness | Experiment 016 selected SVR + two CatBoost ensemble | Completed sleep, previous activity and preceding physiological history | 684 held-out days |
| Daily fatigue | Experiment 018 selected cardiac ExtraTrees classifier | Qualifying daily wrist aggregates before the recorded daily cutoff | 96 held-out days |
| Completed-task workload | Experiment 021 selected model for each outer fold | A complete UNIVERSE task with its preceding physiological reference | 167 out-of-fold tasks |

Readiness approximates the vendor's daily Oura score. Fatigue predicts the recorded daily questionnaire category. Workload uses the overall NASA-TLX task rating and retains the documented rest/activity shortcut limitation. Stress distinguishes the experimental baseline and TSST conditions in WESAD. It does not establish actual instantaneous stress or workplace interpretation; its data license is scientific non-commercial.

The last-minute company telemetry summary cannot satisfy the daily or completed-task contracts. Current telemetry also lacks the sleep/activity fields required by the Oura model. The Model engine therefore does not populate employee state cards, rank people, generate workplace alerts or accept employee features. An anonymous-record-only interface keeps the trained psychological-state and emotional-component research outside the workplace product path.

All previously scored rows are included, without choosing examples by their label or correctness. The exporter checks that every person is absent from the associated artifact's training set. Workload uses each record's original outer-fold model; there is no invented universal deployment model. Recorded references are displayed for comparison and never supplied as predictor columns. Percentages in the evidence panel are evaluation metrics, not confidence in an individual prediction.

## Start locally

The engine's verified research datasets, completed evaluation files and original fitted artifacts must already exist locally. They are ignored by Git and are not included in the API or web image. From the repository root:

```sh
make models-prepare
docker compose up --build -d
```

Open **http://localhost:3000/models**, or choose **Model engine** from the local dashboard navigation. Select a model, choose an anonymous recorded example and press **Run recorded example**. The response includes prediction, recorded reference, input coverage, source dataset and artifact fingerprint.

`models-prepare` uses `neurasign engine/.venv/bin/python` to export the original artifacts and inputs to `neurasign_server_dashboard/var/model-engine/`. Set `MODEL_ENGINE_PYTHON` only when that verified Python environment is elsewhere. The exporter refuses to overwrite a destination. The wrapper retains an existing bundle; the running service verifies its pinned files before use.

The wrapper also creates `var/model-engine-access.env` with a random server-only proxy token and file mode 0600. This file is ignored, never printed and never exposed as a `NEXT_PUBLIC_` variable. Existing provider `.env` files are preserved. Docker injects the token only into API and Next server processes; the model service has no published host port and mounts its bundle read-only.

For native hot reload, run `make dev` after preparation, with the Docker API/web/models services stopped to avoid mixed server versions. The launcher starts the model service with the engine's Python environment when present. Missing bundles or failed hashes appear as unavailable instead of returning placeholder scores.

## API boundary

The same-origin Next proxy at `/api/model-engine/*` forwards to the API with the server-side `X-Model-Engine-Token`. The API then calls the internal worker:

```text
GET  /api/model-engine/catalog
GET  /api/model-engine/models/{stress|readiness|fatigue|workload}/records
POST /api/model-engine/models/{model}/predict
     {"record_id": "stress-0001"}
```

Additional POST fields and query parameters are rejected. No artifact path, feature vector, organization ID or employee ID is accepted. The inference code executes only hash-pinned local artifacts, with matching predictor columns and checks against the original saved evaluation output. No new training or tuning occurs on an HTTP request.

The API is opt-in through `MODEL_ENGINE_ENABLED=true`. Both the Next route and API reject production access, and the model worker refuses a production/Cloud Run environment. The existing Google Cloud production deployment configuration does not include this research service.

## Verification

The runtime tests replay all 1,033 records against the original saved predictions, exercise all four workload folds and reject modified model/data files before deserialization. API tests check production isolation, token handling, exact request schemas and unavailable-service behavior. Browser verification checks the visible predictions and references through the real local stack.

From the server directory:

```sh
.venv/bin/python -m pytest -q
../neurasign\ engine/.venv/bin/python -m unittest discover -s services/models/tests -v
.venv/bin/python scripts/browser_model_engine_smoke.py
cd apps/web
npm test
npm run typecheck
npm run build
```

Reproduction of the original training is documented in the [engine model evidence card](../../neurasign%20engine/MODEL_CARD.md). Model binaries, research rows, tokens and browser artifacts remain ignored; code, pinned dependency hashes and source-controlled artifact fingerprints are versioned.
