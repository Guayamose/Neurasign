# Employee, team and phone onboarding

The company is the tenant. Dashboard accounts (`members`) authenticate through Firebase. Employee profiles (`employees`) identify measured people and do not require a Firebase account. Teams scope manager access inside the company. An enrolled phone credential is permanently bound to one company and employee; request bodies cannot choose another identity.

## Web flow

**People → Create team → Add employee → Connect phone.** The dashboard renders a five-minute single-use QR. NEURASIGN Link scans it, shows company/team/employee and server origin, then asks for confirmation. The phone starts collecting only after the user selects a supported wearable.

Owners can invite manager accounts and grant/revoke teams in **Dashboard access**. Managers see and administer only their assigned teams. An employee moved to another team keeps their identity and phone. New managers cannot read measurements captured for the previous team; delayed uploads are assigned using their original measurement timestamp. Owners retain company-wide access subject to sharing and retention.

## Endpoints

Authenticated dashboard requests use Firebase Bearer tokens:

| Method and path under `/api/v1` | Access / behavior |
| --- | --- |
| `POST /organizations/{org}/teams` | Owner; `{name}` |
| `POST /organizations/{org}/employees` | Owner / granted manager; `{name, team_id}` |
| `PATCH /organizations/{org}/employees/{employee}` | Change name/team; must manage both old and new team |
| `DELETE /organizations/{org}/employees/{employee}` | Deactivate profile and revoke all its phones; does not delete dashboard accounts or stored history |
| `PATCH /organizations/{org}/members/{account}/teams` | Owner; `{team_ids: [...]}`, manager accounts only |
| `POST /organizations/{org}/invitations` | Existing verified-email invitation; manager role accepts `team_ids` |
| `POST /organizations/{org}/employees/{employee}/enrollments` | `{source: "wearable"}`; response `{token, expires_at, employee_id}` |

The QR format is `neurasign://enroll#server=<encoded HTTPS origin>&token=<encoded grant>`. The fragment is not sent in browser requests. No long-lived credential is in the QR. Creating a newer unclaimed code invalidates older codes for that employee. The issuer must still be active and authorized for the employee's current team at redemption.

Phone bootstrap requests need only the grant:

| Method and path | Body / behavior |
| --- | --- |
| `POST /gateway/enrollment/preview` | `{token}` → company, employee, team, expiry, source |
| `POST /gateway/enrollment/claim` | `{token, installation_id, claim_secret, phone_name, consent: true}` → scoped credential and binding |

The phone generates a 32-byte random `claim_secret` (43 URL-safe base64 characters), persists the exact claim in secure storage **before** sending, and keeps it until receipt. The server atomically consumes the code and stores hashes only. Matching installation/secret retries return the same gateway credential; other claims return 409. Recovery lasts 24 hours and rechecks employee/issuer authorization and revocation. No credential is written to logs.

Authenticated phone requests use its scoped `nsd_...` credential:

| Method and path | Behavior |
| --- | --- |
| `GET /gateway/status` | Own company/employee name, sharing state and last receipt only |
| `PATCH /gateway/sharing` | `{enabled}`; QR-enrolled phones only |
| `DELETE /gateway/connection` | Revoke this phone; pause employee if this was their last phone |
| `GET /gateway/sources`, `POST /gateway/sources` | Bound sources and capability registration |
| `POST /observations` | Canonical observation upload contract |

Phone credentials cannot access rosters, account administration, another employee or dashboard history. Server pause blocks uploads immediately when received. Paused measurement intervals are recorded; later batches that overlap those intervals are rejected. Local pause aborts capture/uploads and clears unsent data. Offline privacy actions persist until acknowledged; already received measurements remain governed by server sharing/deletion controls.

## Limits and compatibility

Pilot bounds: 50 teams, 100 new independent employee profiles, 100 dashboard accounts, 10 phones per employee, 5 sources per phone, 200 enrollment codes per company/day. Existing account-backed employees can coexist; they preserve their old storage paths, IDs and credentials. Removing an independent employee does not alter a manager account.

Firestore TTL includes global `enrollments` (expiry or consumed recovery deadline), observations, legacy readings, latest values and audit/invitation records. Authorization rejects expired records even before TTL deletion. Google Cloud preparation adds the TTL configuration without deploying anything.

Legacy self-sharing, device credentials and `/readings` remain supported for existing accounts. New phone onboarding uses independent profiles and `/observations`. The demo's Jev/Gemini workflow remains separate from company sensor ingestion.

## Verification

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/workspace_smoke.py
.venv/bin/python scripts/browser_workspace_smoke.py
.venv/bin/python scripts/telemetry_smoke.py
.venv/bin/python scripts/onboarding_smoke.py
```

The smoke scripts require the local Docker Firebase emulators and refuse other project configurations. They create isolated test accounts/companies; physiological fixtures are labeled recordings. `test_onboarding.py` covers two companies, two managers, denied team actions/history, capture-time transfers, expiry/reuse/concurrent claims, recovery, pause/resume, revocation and legacy profile promotion. Native build/acceptance details are in [NEURASIGN Link](../../neurasign_phone_app/mobile/README.md). Physical wearable compatibility and iOS runtime tests remain unverified.
