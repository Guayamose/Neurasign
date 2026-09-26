# NEURASIGN

A company workspace for monitoring received physiological signals from employees’ compatible wearables.

```text
neurasign/
├── neurasign_phone_app/          Native phone gateway, shared core and adapter contract
└── neurasign_server_dashboard/   Company API, dashboard, demo, deployment and tests
```

Start locally, without any Google Cloud account:

```bash
docker compose up --build -d
```

Open **http://localhost:3000** for company sign-in. The recorded hackathon demo is at **http://localhost:3000/demo**. Local Firebase tools for test users and email verification are at **http://localhost:4000**.

See [server setup and verification](neurasign_server_dashboard/README.md). Root `make setup`, `make dev`, `make test` and `make build` delegate to that folder. Use Docker or the development processes on ports 3000/8000, one at a time.

[Google Cloud deployment preparation](neurasign_server_dashboard/docs/gcloud-deployment.md) uses an explicit future project/account and is offline by default. Nothing has been deployed to the terminal’s current account.

Existing provider credentials remain in `neurasign_server_dashboard/.env`; they are excluded from builds and cloud uploads. Do not copy them into the phone app or browser.

The connection is **wearable → Bluetooth → NEURASIGN Link → Internet → authenticated API → team dashboard**. The [native app](neurasign_phone_app/mobile/README.md) scans a company QR, discovers supported measurement services, collects multiple signals, stores unsent observations in SQLCipher and supports pause/disconnect. Implemented connectors include standard heart rate/beat intervals, thermometer, pulse oximeter and experimental Polar PMD raw streams. The server retains complete sample blocks. See the [exact connector scope and validation limits](neurasign_phone_app/docs/wearable-connectivity.md); no physical wearable has been validated.

The dashboard now separates employee profiles from login accounts. Owners create teams and assign manager permissions. Each phone connects to one employee/company through a single-use QR, with no employee dashboard login. See the [onboarding contract](neurasign_server_dashboard/docs/phone-onboarding.md) and [telemetry contract](neurasign_server_dashboard/docs/telemetry.md).

For watches that require an app on the wearable, [`watch_app/`](neurasign_phone_app/watch_app/README.md) adds a minimal Wear OS sensor companion and a paired Android-phone transport. It collects exposed Android sensors; optional Samsung bindings add continuous HR/IBI, PPG, EDA and temperature plus wearer-triggered ECG/SpO₂ when the official SDK, watch model, permissions and policy permit. The base Wear OS APK compiles; the Samsung SDK download requires a Samsung account and was not available in this environment. [The coverage matrix](neurasign_phone_app/docs/model-coverage.md) records this distinction and other vendor dependencies.

Run `make phone-setup` for the shared core, `make mobile-setup` for native dependencies, and `make test-all` for server/core/contracts. `make mobile-check` runs native lint and TypeScript checks. The native build guide explains Android APK installation, USB loopback forwarding and the outstanding physical-device/iOS validation.

The [repository timeline](docs/repository-timeline.md) explains the ordered import commits. Environment files, credentials, raw recordings, local databases and build artifacts are excluded from Git; `.env.example` contains only empty credential fields and public configuration examples.
