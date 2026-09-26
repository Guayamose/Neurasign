# Repository timeline

The initial GitHub import groups the existing local implementation into eight commits in development order. Commit timestamps record the import itself, not the dates when individual features were originally written. Each commit contains the current version of its feature, including later corrections; this is not a reconstruction of earlier application versions.

| Order | Commit | Contents |
| --- | --- | --- |
| 1 | `chore(repo): establish monorepo and secret exclusions` | Workspace layout, environment exclusions and pinned Python dependencies. |
| 2 | `feat(demo): add physiological replay and incident workflows` | Signal processing, labeled replay fixtures, monitoring, demo heuristics, Jev/Gemini integrations and regression tests. |
| 3 | `feat(api): add company tenancy and authenticated wearable ingestion` | Company and team permissions, employee profiles, Firebase identity, persistence, single-use phone enrollment, normalized telemetry and local Docker services. |
| 4 | `feat(dashboard): add team monitoring and company administration` | English company dashboard, physiological charts, metric explanations, people/teams, device enrollment and the separate recorded demo. |
| 5 | `feat(gateway): add wearable contracts and reliable observation upload` | Brand-independent observation contracts, the standard Bluetooth heart-rate adapter, enrollment, upload queue and core tests. |
| 6 | `feat(mobile): add native QR and BLE phone gateway` | Expo application, QR enrollment, native Bluetooth transport, encrypted persistence, sharing controls, Android build tooling and controller tests. |
| 7 | `build(gcloud): prepare deployment and persistence verification` | Offline Google Cloud deployment preparation, Firestore rules and production-container checks. |
| 8 | `docs(project): document setup and verified capabilities` | Entrypoints, architecture, test results, setup instructions and this timeline. |

The phone application is a wearable gateway. Company access control, measurement normalization and presentation belong to the server/dashboard. Demo workload, fatigue and readiness scores are unvalidated heuristics; the unsupported “deep work” classification is absent from the imported implementation. Company workspaces show received measurements without inventing cognitive scores.

No Google Cloud resources are provisioned by this import. Physical wearable compatibility and an actual iOS build still require validation. The native connector currently supports the standard Bluetooth Heart Rate Service; other protocols require additional adapters.

## Local files kept out of Git

All `.env*` and `*.env` files are ignored at every depth, except the reviewed `.env.example` template. Credentials and signing files, dependencies, native generated projects, APKs, screenshots, emulator state, local databases and raw study recordings are excluded. The dataset downloader and preprocessing instructions remain available to reproduce the local recording setup.

The original Expo scaffold Git metadata was retained locally under `.git/local-backups/mobile.git` before importing the mobile application as an ordinary folder. It is not a submodule and its local metadata is not published.

## Import verification

- Server: 107 tests passed; gateway and native controller: 13 tests passed.
- A clean export of the committed source passed 106 server tests; the one test that requires an optional local study recording was skipped as intended.
- Generated gateway contracts match server validation.
- Dashboard TypeScript checks and production build passed.
- Native TypeScript and Expo lint checks passed. Expo lint configuration is included so the check is repeatable.
- The staged source and all eight commits were checked for locally configured credential values and scanned with Gitleaks; no secrets were found.
