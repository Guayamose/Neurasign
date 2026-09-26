# NEURASIGN server and dashboard

NEURASIGN brings a team’s received physiological measurements into one company workspace. Employees authorize their own device and control sharing; owners and managers view team measurements, freshness and recent trends.

The **company application is `/`**. The existing recorded hackathon demo and its Jev/Gemini example workflows are at **`/demo`**, available only in local development. Company workspaces start empty and never invent employee readings or cognitive scores.

## Run locally

From this folder or the parent workspace:

```bash
docker compose up --build -d
```

- Company workspace: **http://localhost:3000**
- Recorded demo: **http://localhost:3000/demo**
- Local Firebase tools: **http://localhost:4000**
- Local API docs: **http://localhost:8000/docs**

Docker starts the web app, API, Firebase Auth emulator and Firestore emulator. No Google Cloud account is required or used. All host ports bind to loopback. **Quick access:** click **Sign in with test account** on the login page, or use `demo@neurasign.test` / `Neurasign2026!`. The verified account and its test workspace are created automatically in the local emulators. The demo header’s **Back to login** link returns to sign-in, including when a previous session is active. These test credentials are not enabled in production.

To create your own account: the emulator does not send real email. Open Authentication in the local Firebase tools, edit that test user and mark their email verified, then click **I have verified my email** in NEURASIGN. You can also use the verification URL printed by the local Auth emulator.

Create a workspace, invite a colleague, and share the invitation link manually. The colleague verifies their account, accepts the invitation, enables **My sharing**, then authorizes their device in **Wearables**. Without a mobile gateway or hardware, readings remain empty. An explicitly labeled **Demo recording** credential can test the upload contract.

Emulator data is exported on graceful shutdown into the `emulator-state` Docker volume and imported at restart. Sign out and sign in again after an emulator restart: imported Auth accounts invalidate earlier sessions. Use `docker compose down` to stop; `down -v` deletes that local volume. Emulators are development tools, not production databases.

For hot reload (Python 3.11+, Node 22, npm, Docker; optional `uv`):

```bash
docker compose stop api web
make setup
make dev
```

`make dev` starts the local emulators and the API/web development processes. `Ctrl+C` stops the latter; `docker compose stop emulator` stops the emulators. The API privately loads the existing `.env`; do not overwrite it with `.env.example`. Jev/Gemini credentials are used only by the local incident example and are never included in frontend or cloud build uploads.

## Deploy when the new account arrives

Follow [Google Cloud deployment](docs/gcloud-deployment.md). Preparation is entirely offline:

```bash
python3 scripts/deploy_gcloud.py \
  --project YOUR_NEW_PROJECT_ID \
  --account YOUR_NEW_ACCOUNT_EMAIL \
  --firebase-api-key YOUR_FIREBASE_WEB_API_KEY
```

This produces reviewed configuration under `var/deploy/`. Only an explicit `--apply` provisions resources and deploys. Every gcloud invocation supplies its account and project; the script never changes the active gcloud configuration.

Cloud Run runs the web ingress and private API sidecar together. Firebase Auth verifies users; Firestore persists company data. Production rejects emulator/SQLite configuration and disables the legacy demo/API. The phone workspace includes the native NEURASIGN Link application with BLE heart-rate transport and encrypted storage. Cloud deployment, physical wearable compatibility and operational acceptance must be verified on the future account before a company rollout.

## Verify

```bash
make test
make build
.venv/bin/python scripts/workspace_smoke.py
.venv/bin/python scripts/emulator_persistence_smoke.py
.venv/bin/python scripts/production_container_smoke.py
.venv/bin/python scripts/browser_workspace_smoke.py
.venv/bin/python scripts/browser_monitoring_smoke.py
.venv/bin/python scripts/check_secrets.py
```

The smoke scripts require the Docker stack. Browser checks require Chrome and Playwright (`uv pip install --python .venv/bin/python playwright`). The workspace checks use only local Auth/Firestore emulators and create disposable test accounts with explicitly labeled test data. No external Jev/Gemini call is needed for company checks.

## Documentation

- [Company permissions, API and mobile upload contract](docs/company-workspace.md)
- [Wearable adapters, independent observations and server normalization](docs/telemetry.md)
- [Google Cloud setup, deployment and acceptance](docs/gcloud-deployment.md)
- [Recorded demo and AI example workflows](docs/demo-workspace.md)
- [Physiological dataset and processing](docs/dataset.md)
- [Verification results and remaining limits](docs/verification.md)
- [Phone app workspace](../neurasign_phone_app/README.md)

## Employee phones and team access

Use **People** to create teams, add employees without login accounts, issue phone QR codes and assign manager access. [Phone onboarding and permissions](docs/phone-onboarding.md) documents the API, migration and verification. The installable native app lives in [`../neurasign_phone_app/mobile`](../neurasign_phone_app/mobile/README.md). Cloud deployment remains deferred.
