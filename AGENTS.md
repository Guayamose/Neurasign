# Repository orientation

NEURASIGN connects supported wearable measurements to company/team monitoring. The phone is a gateway; the server owns ingestion, identity and access; the dashboard is the manager's workspace. Hospitals are an illustrative use case, not the product's entire scope.

## Read first

1. [README.md](README.md): product, quick start and repository map.
2. [Project overview](docs/PROJECT_OVERVIEW.md): implemented behavior, demo walkthrough, research results and remaining milestones.
3. The relevant component README and any nested `AGENTS.md` before editing that area. Nested guidance exists in `neurasign_server_dashboard/apps/web/` and `neurasign_phone_app/mobile/`.

## Areas and source of truth

| Area | Start here |
| --- | --- |
| API, company dashboard, Docker and deployment | [Server README](neurasign_server_dashboard/README.md) |
| Operational tasks, support cases, handovers and manager privacy | [Applications guide](neurasign_server_dashboard/docs/applications.md), [API contract](neurasign_server_dashboard/docs/applications-contract.md) |
| Tenant/team access and employee-bound phone credentials | [Onboarding contract](neurasign_server_dashboard/docs/phone-onboarding.md) |
| Measurement format, sources and timestamps | [Telemetry contract](neurasign_server_dashboard/docs/telemetry.md) |
| Native phone, BLE adapters and vendor routes | [Gateway README](neurasign_phone_app/README.md), [native build](neurasign_phone_app/mobile/README.md), [coverage matrix](neurasign_phone_app/docs/model-coverage.md) |
| Training, evaluation and scientific claims | [Engine README](<neurasign engine/README.md>), [model card](<neurasign engine/MODEL_CARD.md>), individual experiment reports |
| Frozen model execution through the dashboard | [Model engine](neurasign_server_dashboard/docs/model-engine.md) |
| Animation, narration and final exports | [Film README](<demo video/README.md>) |
| Prior verification | [Dated verification record](neurasign_server_dashboard/docs/verification.md) |

## Keep these surfaces distinct

- **`/` — company workspace:** authenticated company/team access, operational overview, employee profiles, phone enrollment and three persisted applications. Owner/manager roles do not grant physiological access. Task eligibility uses confirmed operational context; support cases are human-reported.
- **`/demo` — local sample company:** enters the same company UI with 36 fictional people across four teams. Edits persist in this isolated local example. Four state indicators are explicitly illustrative, not live model predictions.
- **`/signals` — local signal explorer:** included synthetic fixture by default; imported UNIVERSE replay when available. Derived indices are illustrative formulas. Jev/Gemini optionally power the incident example with labeled fallbacks and human review. Its Manager preview is presentation only; company privacy is separately enforced by the API.
- **`/models` — local research execution:** saved fitted estimators on pinned anonymous records. Requires separately prepared ignored artifacts and a server-side token. It does not accept employee features or feed live employee state cards, and is disabled in production.
- **`demo video/` — animated concept film:** fictional people, scripted values and an illustrated recommendation. This is not captured application behavior or model evaluation evidence.

Company dashboard payloads redact physiological values for owners/managers and raw-history endpoints reject them. Legacy employee self-access and a separate explicit measurement capability are distinct. Do not infer live physiological diagnosis, AI task matching or regulatory certification from the operational workflows.

`docs/architecture.md` and `docs/api-contract.md` inside the server directory describe the local Signal explorer runtime. Use company/onboarding/telemetry documents for the company platform. Read dated verification entries as historical checks, not the current aggregate test count.

## Working conventions

- Keep product UI and repository documentation in English. Follow the user's language in conversation.
- Quote paths containing spaces, notably `"neurasign engine"` and `"demo video"`.
- Preserve measurement units, source identity, timing, missing values and observed-versus-derived distinctions. A missing signal is not zero; simulated and recorded sources must remain labeled.
- Keep participant-separated evaluation, original reference labels and artifact fingerprints intact when working on research. Report the target, cohort, timescale and baseline alongside results; score error is not accuracy and evaluation accuracy is not individual confidence.
- Check the route-specific coverage status before calling a wearable supported. Code or emulator tests are not physical-device validation.
- Keep `.env` files, credentials, raw datasets and intermediate artifacts out of Git. Public local emulator credentials in the README are intentional. Do not print provider secrets or use the terminal's active Google Cloud account implicitly.
- Preserve the supplied presentation and brand originals unless the user asks to edit them. Generated film exports have narrow Git ignore exceptions; consult the film README before rebuilding assets.

## Local commands and verification

Run the app from the root with `docker compose up --build -d`. The local test login and URLs are in the root README. Run `make models-prepare` only after the required research datasets, evaluations and fitted artifacts exist; it does not download them.

The root Makefile forwards server commands (`make test`, `make build`, `make smoke`) and exposes gateway checks (`make phone-test`, `make contract-check`, `make mobile-check`). Use the component guide for environment prerequisites and the checks appropriate to a change. The model service has its own engine-environment tests, documented in its guide. Film checks and renders are documented separately.

For documentation changes, verify relative links and `git diff --check`. For behavior changes, run the relevant tests and describe what was actually executed. Historical test logs, UI fixtures and emulator runs must not be reported as a new run, a capacity benchmark or wearable acceptance.
