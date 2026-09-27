# NEURASIGN server and dashboard

NEURASIGN connects wearable inputs, company teams and three operational applications. Employees authorize their phone and control sharing; owners/managers see permitted work context and connection status. The API protects physiological values from these roles.

The **company application is `/`**: Overview, People & teams, Applications and Connections. **`/demo`** opens the same UI with an isolated sample company of 36 fictional employees across four teams. Task assignment, support cases and handovers use real persisted workflows. **`/signals`** retains the separate physiological explorer and optional Jev/Gemini incident walkthrough. All sample/research entry routes are disabled in production. New company workspaces start empty.

The local **Model engine at `/models`** runs saved fitted models on anonymous research records and compares their predictions with recorded references. It uses experiments **022** (60-second stress condition), **016** (daily Oura readiness), **018** (daily fatigue) and **021** (completed-task workload, with the matching evaluation-fold model). The Signal explorer's indices remain labeled formula estimates; sample-company indicators are scripted examples. Employee telemetry is outside this research service, which is disabled in production. See [model execution and evidence limits](docs/model-engine.md).

## Run locally

From this folder or the parent workspace:

```bash
docker compose up --build -d
```

- Company workspace: **http://localhost:3000**
- Interactive company demo: **http://localhost:3000/demo**
- Signal explorer: **http://localhost:3000/signals**
- Model engine: **http://localhost:3000/models**
- Local Firebase tools: **http://localhost:4000**
- Local API docs: **http://localhost:8000/docs**

Docker starts the web app, API, internal model service, Firebase Auth emulator and Firestore emulator. No Google Cloud account is required or used. All host ports bind to loopback. **Quick access:** click **Sign in with test account** on the login page, or use `demo@neurasign.test` / `Neurasign2026!`. The verified account and its test workspace are created automatically in the local emulators. The sample banner’s **Back to sign in** link returns to sign-in, including when a previous session is active. These test credentials are not enabled in production.

The company workspace and demo run without research datasets, model bundles or Jev/Gemini keys. Missing model bundles do not prevent the Docker stack from starting. To replace the Signal explorer’s synthetic fixture with recordings, follow [dataset import](docs/dataset.md).

For model inference, run **`make models-prepare` before starting Docker**. It exports the engine's existing verified artifacts and research inputs, then creates a private local proxy token. A clean clone first needs the verified research data and completed training artifacts described in the [model setup guide](docs/model-engine.md). The bundle and token remain ignored: without the token, the Docker dashboard's model proxy rejects access; with the token but no valid bundle, inference is unavailable.

To create your own account: the emulator does not send real email. Open Authentication in the local Firebase tools, edit that test user and mark their email verified, then click **I have verified my email** in NEURASIGN. You can also use the verification URL printed by the local Auth emulator.

In the workspace, open **People & teams → Create team → Add employee → Connect phone**. Scan the QR with NEURASIGN Link, confirm the company and employee, then select a supported wearable. Employees do not need dashboard accounts. Owners use **Dashboard access** to invite managers and grant their teams; invitation links are shared manually. See [phone onboarding and permissions](docs/phone-onboarding.md).

Legacy account-backed self-sharing remains available under **My privacy**, with credentials under **Connections → Advanced · personal gateway credential**. An explicitly labeled **Demo recording** credential can test that upload contract. Without received gateway measurements or labeled test uploads, the company dashboard has no physiological readings.

Emulator data is exported on graceful shutdown into the `emulator-state` Docker volume and imported at restart. Sign out and sign in again after an emulator restart: imported Auth accounts invalidate earlier sessions. Use `docker compose down` to stop; `down -v` deletes that local volume. Emulators are development tools, not production databases.

For hot reload (Python 3.11+, Node 22, npm, Docker; optional `uv`):

```bash
docker compose stop api web models
make setup
make dev
```

`make dev` starts the local emulators and the API/web development processes, plus the model service when the engine's Python environment is available. Run `make models-prepare` first to use the models. `Ctrl+C` stops the development processes; `docker compose stop emulator` stops the emulators. The API privately loads the existing `.env`; do not overwrite it with `.env.example`. Jev/Gemini credentials are used only by the local incident example and are never included in frontend or cloud build uploads.

## Deploy when the new account arrives

Follow [Google Cloud deployment](docs/gcloud-deployment.md). Preparation is entirely offline:

```bash
python3 scripts/deploy_gcloud.py \
  --project YOUR_NEW_PROJECT_ID \
  --account YOUR_NEW_ACCOUNT_EMAIL \
  --firebase-api-key YOUR_FIREBASE_WEB_API_KEY
```

This produces reviewed configuration under `var/deploy/`. Only an explicit `--apply` provisions resources and deploys. Every gcloud invocation supplies its account and project; the script never changes the active gcloud configuration.

Cloud Run runs the web ingress and private API sidecar together. Firebase Auth verifies users; Firestore persists company data. Production rejects emulator/SQLite configuration and disables sample-company seeding, the Signal explorer/demo API and Model engine. The three company operational applications remain available to authorized managers. The production deployment does not include the research model service.

The native NEURASIGN Link app implements QR enrollment, multi-signal transport, native Bluetooth bindings, secure credential storage and an encrypted offline queue. Standard BLE heart rate/RR, thermometer and pulse oximeter connectors are implemented alongside an experimental Polar connector and separate vendor/platform routes; available channels depend on the device and integration. See [native app setup and validation limits](../neurasign_phone_app/mobile/README.md). Cloud deployment, physical wearable/vendor integration, iOS runtime behavior and operational acceptance still need validation before a company rollout.

## Verify

```bash
make test
make build
.venv/bin/python scripts/workspace_smoke.py
.venv/bin/python scripts/emulator_persistence_smoke.py
.venv/bin/python scripts/production_container_smoke.py
.venv/bin/python scripts/browser_workspace_smoke.py
.venv/bin/python scripts/browser_applications_smoke.py
.venv/bin/python scripts/browser_monitoring_smoke.py
.venv/bin/python scripts/check_secrets.py
```

The smoke scripts require the Docker stack. Browser checks require Chrome and Playwright (`uv pip install --python .venv/bin/python playwright`). The workspace checks use only local Auth/Firestore emulators and create disposable test accounts with explicitly labeled test data. No external Jev/Gemini call is needed for company checks.

## Documentation

- [Company permissions, API and mobile upload contract](docs/company-workspace.md)
- [Wearable adapters, independent observations and server normalization](docs/telemetry.md)
- [Google Cloud setup, deployment and acceptance](docs/gcloud-deployment.md)
- [Three applications, manager privacy and the complete product demo](docs/applications.md)
- [Operational API contract](docs/applications-contract.md)
- [Signal explorer and AI incident examples](docs/demo-workspace.md)
- [Trained model execution, preparation and evidence limits](docs/model-engine.md)
- [Interface design and simplified navigation](docs/interface-design.md)
- [Physiological dataset and processing](docs/dataset.md)
- [Verification results and remaining limits](docs/verification.md)
- [Phone app workspace](../neurasign_phone_app/README.md)

## Employee phones and team access

Use **People & teams** to create teams, add employees without login accounts, issue phone QR codes and assign manager access. [Phone onboarding and permissions](docs/phone-onboarding.md) documents the API, migration and verification. The installable native app lives in [`../neurasign_phone_app/mobile`](../neurasign_phone_app/mobile/README.md). Cloud deployment remains deferred.
