# Anonymous model inference service

Runs actual frozen NEURASIGN model predictions on allowlisted public-research records. It has no employee, company or telemetry interface. All 1,033 previously scored records are included: WESAD 86, Oura 684, DailySense 96 and UNIVERSE 167. There is no cherry-picking of correct predictions. Each UNIVERSE record runs through its own held-out fold artifact.

The service refuses production startup (`NEURASIGN_ENV=production` or `K_SERVICE`). Native startup binds localhost; the Docker image listens internally on port 8010 and must not publish that port. The application proxies access using its own server-side authentication. This isolated research view does not replace company/dashboard formulas.

## Prepare and run

From the repository root, with the existing verified engine data and model artifacts:

```sh
'neurasign engine/.venv/bin/python' 'neurasign engine/scripts/export_dashboard_models.py'
'neurasign engine/.venv/bin/python' neurasign_server_dashboard/services/models/server.py
```

`--output` changes the export destination. An existing destination is never overwritten. The ignored bundle defaults to `neurasign_server_dashboard/var/model-engine`; use `MODEL_BUNDLE_DIR` to select an operator-controlled bundle directory. Exporter checks original frozen experiment hashes, held-out membership and prediction equality. No retraining occurs. Bundle data and artifacts are not committed.

`catalog.json` pins artifact and prepared-record hashes in versioned code. The service checks exact bytes before deserializing locally produced joblib artifacts, and rechecks integrity on requests. No uploaded models or arbitrary feature values are accepted. Python dependencies are pinned in `requirements.txt` and hash-locked in `requirements.lock`.

## HTTP contract

- `GET /health`: availability of each configured bundle.
- `GET /catalog`: methods, target definitions, evidence limits and availability.
- `GET /models/{id}/records`: anonymous record IDs, sequence and feature coverage.
- `POST /models/{id}/predict` with exactly `{"record_id":"stress-0001"}`: computed prediction, observed reference, horizon, artifact fingerprint and evaluation provenance.

Model IDs: `stress`, `readiness`, `fatigue`, `workload`. Unknown IDs return 404; invalid inputs return 422; missing/inconsistent bundles return 503. JSON bodies are limited to 2 KiB. Duplicate fields, nonfinite JSON, arbitrary identity, features, model paths and queries are rejected. Responses contain no source participant identifiers or raw feature values. Class predictions are labels, not calibrated confidence; `confidence` is always null.

Readiness predicts the daily **vendor Oura score**. Fatigue predicts overall **daily** questionnaire class using the original experiment 018 decision threshold. Stress recognizes baseline versus TSST **laboratory condition**. Workload estimates **completed-task** weighted NASA-TLX, whose apparent physiological benefit is not established. WESAD is limited to scientific non-commercial research. These models do not provide diagnosis, live employee emotional-state monitoring or fitness-for-duty clearance.

## Verify

From the repository root:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 'neurasign engine/.venv/bin/python' \
  -m unittest discover -s neurasign_server_dashboard/services/models/tests -v
```

Artifact integration tests replay all exported rows against their saved predictions, require matching fold provenance, and test tamper rejection before deserialization, cached-data revalidation, missing bundles, production blocking and HTTP input validation. They skip when local research artifacts have not been exported; the lightweight API has separate proxy tests.
