# Verification record

## Cobalto identity and large-team interface — 2026-09-26

The approved logo and favicon now accompany the cobalt/navy palette across access, company monitoring, the recorded demo and Model engine. Main operational headings are compact, body copy is 14–16 px, metadata is at least 12 px and main controls are at least 44 px high. Company overview and People & teams use searchable, filtered and paginated rosters with 25/50 rows per page.

- **23 web tests passed**, including seven roster checks for combined filters, stable sorting, pagination, paused-data suppression, canonical status precedence and mixed-source/backfill freshness. TypeScript checking and the production web image build passed.
- **100-person browser fixture passed**: paging, name/team/data-status/sharing filters, ordering, summary labels, paused receipts, selected-person focus/return, polling/reordering/removal and mobile layouts. Fixtures only intercept browser responses; company writes are blocked. This verifies UI behavior, not backend load capacity.
- **Full workspace browser acceptance passed**: signup/verification, invitations, employee isolation, sharing, device authorization, measurement receipt, charts, mobile, revocation and sign-out.
- **Recorded demo, controls and manager browser checks passed**: metrics/help, playback/source handling, local drafts, individual history, missing-data states, navigation and responsive layout. No external Jev/Gemini calls were needed.
- **Model engine browser acceptance passed** for all four real recorded predictions, reference values, artifact provenance, invalid-input rejection and failure recovery. Inference artifacts and interpretation rules are unchanged.
- Desktop/mobile screenshots of access, company roster, demo and models were reviewed. Additional access-page checks at 390/768 px confirmed no horizontal overflow. The logo and favicon return HTTP 200 and exactly match the approved copied SVG assets.
- Credential scanning passed across **431** source, artifact and client-build files; `.env` files remain ignored. Whitespace checks passed. The local Docker web service was rebuilt and restarted; no Google Cloud deployment was performed.
- The user's 17-slide presentation was reviewed read-only. Original PDF and PPTX SHA-256 hashes were unchanged after review. Its original files are not included in these application commits.

See [interface direction](interface-design.md) for navigation and the client-side pagination boundary. Screenshots remain ignored under `artifacts/`, including `company-large-roster-{desktop,mobile}.png` and `cobalt-login-{desktop,390,768}.png`.

## Editorial interface redesign — 2026-09-26

Company access, company monitoring, the recorded demo and Model engine share a black/ivory/orange design, SVG dot-matrix branding, large typography and flatter layouts. Secondary details expand on demand; demo examples are grouped under **Use cases**. See the [interface direction and navigation](interface-design.md).

- **16 web tests passed**; TypeScript and the final production web image build passed.
- Monitoring browser checks passed for physiological charts, person/signal selection, metric-help focus containment, source-preserving example navigation and mobile layout. Control checks passed for playback, manual indices, partial live measurements and local drafts.
- Manager preview browser checks passed for existing filters, individual history, missing-data behavior, navigation and presentation boundaries. No interpretation logic changed.
- Company browser acceptance passed for signup/verification, invitations, sharing, received measurements, charts, help, revocation and sign-out. Additional checks covered password visibility, test-account access, employee setup, readable phone QR codes and mobile form navigation. A regression assertion verifies that the two mobile chart time labels do not overlap.
- Model engine browser checks passed for all four real predictions, references/fingerprints, failure recovery, record changes and desktop/mobile presentation. Evaluation evidence and input periods remain visible.
- Final checks covered keyboard opening/Escape/focus return in the Use cases menu, the mobile access shortcut, 360/390/768 px layouts and screenshots of the main views. No browser errors were reported.
- Credential scanning and whitespace checks passed. Provider credentials and generated screenshots remain ignored. No external Jev/Gemini requests or Google Cloud deployment were needed for this revision.

## Anonymous trained-model workspace — 2026-09-26

The local `/models` workspace executes the unchanged selected research artifacts and compares their predictions with recorded references. It does not connect employee features to these models or replace the team demo's labeled formula estimates. Production access remains disabled. See [model execution and input contracts](model-engine.md).

- **150 API tests passed**, including server-token access, production isolation, strict record-only schemas and streamed request size limits.
- **11 model-service tests passed**, replaying all **1,033** original evaluation records, preserving each workload record's held-out fold and rejecting modified artifacts before loading them.
- **16 web tests passed**, including Docker's internal-versus-browser origin regression; TypeScript and the final Docker web/API/model builds passed.
- **Browser acceptance passed** against the running Docker stack: all four real model executions, visible reference values and artifact fingerprints, result clearing on record changes, invalid employee input rejection, service errors and recovery, company/demo navigation, mobile layout and no JavaScript errors. Run `scripts/browser_model_engine_smoke.py`; screenshots are ignored under `artifacts/model-engine-*.png`.
- Credential scanning passed. The model bundle, private proxy token and generated screenshots remain ignored. The token is absent from versionable source and client assets; its local file uses mode 0600.

These checks verify software execution and reproducibility. They add no new scientific validation, physical-wearable acceptance or production deployment claim.

## Demo navigation and local test login

The demo now has a visible **Back to login** link, including on mobile. It returns to sign-in even with an existing company session. The local login displays a verified emulator-only test account and a **Sign in with test account** shortcut. Its test workspace is created on API startup without adding physiological readings.

- **82 automated tests passed**, including guards against test-account creation or credential exposure outside the local emulators.
- API/web Docker builds and TypeScript checks passed; the production container smoke passed.
- Browser checks passed for demo → login, visible credentials, one-click/manual sign-in, the precreated workspace, active-session return, mobile layout and no browser errors.
- Screenshots: `artifacts/test-login-desktop.png`, `artifacts/test-login-mobile.png`, `artifacts/demo-return-mobile.png`.

## Company workspace and cloud preparation — 2026-09-22

The company application is now `/`; the recorded hackathon dashboard remains at `/demo` locally and is disabled in production. No resources have been deployed to Google Cloud. The future account/project have not yet been supplied; the current terminal account was not used for deployment.

- **77 automated tests passed**, with two upstream deprecation warnings. New checks cover tenant/role isolation, verified-identity boundaries, email-bound invitations, device-token scoping, hashing/revocation, sharing, deletion races, idempotency/concurrent retries, timestamp handling, durable SQLite storage, production route/environment restrictions and offline deployment targeting.
- **Docker API and web builds passed**; Next.js compilation and TypeScript checks passed. The API image uses the hash-locked dependency file.
- **Actual Firebase Auth and Firestore emulator integration passed** through the public web proxy: verified/unverified accounts, isolated companies, employee permissions, invitations, sharing, authenticated batches, partial measurements, late data, duplicate retries, deletion and revocation. Company and measurement history survived an API restart. A separate emulator restart check verified persisted Auth accounts, company membership, device credentials, physiological history and retry deduplication; direct Firestore client access was denied. The export directory is a child of the mounted volume so Firebase can replace it safely. Imported emulator accounts require a fresh sign-in.
- **Two-session browser acceptance passed**: signup/email verification, company creation, invitation link, employee sign-in/join, sharing, device authorization, labeled recording upload, manager charts/metric help, desktop/mobile layouts, pause/revoke, sign-out and no browser errors. Screenshots are in ignored `artifacts/company-*.png`.
- **Legacy browser regression passed at `/demo`**: recorded profiles, physiological units/charts, metric-help keyboard behavior, example navigation and responsive layout. No new external Jev/Gemini call was needed; prior real-provider results below describe the demo revision.
- **Local production-container check passed**: the same API/web images run with a shared network namespace, only web ingress published, runtime port 8080 and non-root users. Anonymous requests and oversized bodies (including chunked uploads) are rejected; demo routes are disabled. This uses placeholder public Firebase configuration and does not claim cloud identity/database connectivity was tested.
- The **deployment plan generated offline** without any gcloud/network call. Explicit account/project flags are covered by tests. The local Cloud Build upload listing excluded `.env`, provider credentials, recordings, dependencies and local data. The credential scan passed; the original provider `.env` was verified byte-for-byte unchanged.

Company workspaces contain only their own received data; they do not reuse the demo’s global in-memory orchestrator. Charts show physical metrics and freshness, without invented fatigue/readiness scores. Emulator tests use explicitly labeled test recordings, not physical wearables.

Remaining acceptance: deploy to the future account; validate real Auth email delivery, Firebase password policy, IAM/rules, managed Firestore, TTL/backups and restore, expected load and operational monitoring. Phone application/Bluetooth integration remains unimplemented and requires physical-device validation. See [deployment](gcloud-deployment.md) and [company contract and limitations](company-workspace.md).

## Workspace split

The existing project now lives in `neurasign_server_dashboard/`. `neurasign_phone_app/` contains its scope README only; no mobile application is claimed to exist yet. Root Make and Docker Compose entry points continue to work.

- Every original top-level entry was relocated. The server `.env` was verified byte-for-byte unchanged.
- The Python environment was recreated at its new path using exactly the same installed package versions; the relocated Uvicorn executable runs successfully.
- Root `make test`: **63 passed**, with two existing upstream deprecation warnings.
- Root `make build`: **passed**, including TypeScript checking.
- Compose configurations from the workspace root and server folder resolve to identical services, the same project name, and the new build paths.
- Root `docker compose up -d --build`: **passed**. Both images built, the API health check passed, and the dashboard started.
- Relocated `scripts/monitoring_smoke.py`: **passed** against Docker, checking the actual UNIVERSE data mount, physiological values/history, playback, source isolation and WebSocket updates.
- Relocated `scripts/browser_monitoring_smoke.py`: **passed** against Docker, including Sam's details, English metric help, navigation, keyboard behavior and mobile layout, without browser errors.
- The credential scan found no configured secret values in **202 source, artifact and client-build files**.

The stack is running at `localhost:3000` and `localhost:8000`. No new external Jev/Gemini requests were needed for this structural change; the preceding real-provider results below are historical checks.

## Previous revision: English interface and metric help

The primary product is the English team-lead monitoring dashboard. Physiological summaries, history, references, and estimated states are visible independently of the secondary examples. Metric explanations use a shared help dialog; the incident tab shows one next action and three phases.

## Checks completed on the previous demo revision

Final interface acceptance passed against the deployed Docker stack at `localhost:3000` and `localhost:8000`.

- The production frontend build, including compilation/type checking, passed. Docker services are running and healthy.
- `scripts/browser_monitoring_smoke.py`: **passed**. It covered English monitoring, both recording profiles, chart units/history, person/metric selection, source-preserving tabs, keyboard containment in metric help, Escape/focus return, and mobile help/layout.
- `scripts/browser_controls_smoke.py`: **passed**. It exercised playback, Manual controls, partial Live input, and both local example drafts, including their English download contents.
- `scripts/browser_smoke.py --require-live`: **passed** for the simplified incident. It verified the diagnosis assignment's actual Jev provenance, four Gemini artifacts, explicit human review and approval, and continued monitoring with the UNIVERSE source preserved. Start/approval actions were visible within a 1440 × 900 viewport; the mobile incident had no horizontal overflow.
- Browser checks reported no JavaScript errors.
- A separate language audit inspected the overview, document language/title, aria labels, tooltips, select options, all **16** expanded metric definitions, and both draft bodies. No Spanish text remained in those surfaces. Source review also covered the rewritten incident component.
- After the workflow check, approval guidance was clarified to **“Read the full analysis, then approve the recovery plan to start the checks.”** The final copy-only Docker rebuild/deployment completed, and HTTP/served-JavaScript inspection confirmed that exact text and the English page.
- The final credential scan passed across **201 source, artifact, and client files**. The existing root `.env` remained byte-for-byte unchanged.

The stack was left running on **Team overview** with actual UNIVERSE replay, autoplay enabled, and no active workflow. Staging processes were stopped. Screenshots are saved under ignored `artifacts/`, including `monitoring-desktop.png`, `monitoring-mobile.png`, `metric-help-mobile.png`, and the incident start/review/approval/result views.

The unchanged backend retains the preceding monitoring revision's **63 passing tests** (1.08 seconds, two upstream deprecation warnings) and passing `scripts/monitoring_smoke.py` data checks. Those checks compared direct features/history against the imported JSON, verified units and no future rows, and exercised source isolation, null Manual physiology, autoplay/pause, and HTTP/WebSocket monitoring independently of incidents.

## Scope and remaining limits of the previous demo revision

Physiological charts show recorded or received feature summaries, not raw PPG/ECG waveforms. Cognitive histories are heuristic estimates recomputed from source windows and current staged work context. They are not observed mental-state measurements or clinical diagnoses. The two workers map to two real UNIVERSE sessions when recorded replay is selected; fixture and Manual modes remain explicitly distinguished.

Wellbeing and focus examples provide local illustrative suggestions/drafts from the current worker states. They do not create calendar events or send notifications. The incident example makes actual Jev/Gemini calls when configured; its operational evidence is sample data, and no production system is accessed or changed.

The legacy demo is a single-session, in-memory local application without physical hardware, production incident execution, authentication/tenancy, or durable audit storage. Live input uses a provisional reference until device calibration exists. Full raw waveforms, detailed private research, and API credentials remain outside ordinary monitoring access.
