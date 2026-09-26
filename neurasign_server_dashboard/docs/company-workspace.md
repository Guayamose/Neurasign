> New employee/team/QR enrollment is implemented. See [phone onboarding](phone-onboarding.md) for the current company model and scoped phone endpoints. The self-enrollment examples below remain available for legacy dashboard accounts.

# Company workspace and gateway contract

The company application monitors received physiological measurements. It has no preloaded employees, generated physiological readings, automatic work reassignment or uncalibrated mental-state scoring. The local `/demo` provides the separate recorded hackathon examples, including Jev/Gemini incident workflows.

This document retains the **v1 compatibility contract**. The [phone onboarding contract](phone-onboarding.md) describes the implemented employee/dashboard separation, QR enrollment and team grants. The [telemetry extension](telemetry.md) describes source capabilities, independent observations and normalization. The native phone app is a wearable connection and upload gateway.

## Access

Users authenticate with Firebase email/password and must verify their email. The backend verifies ID tokens, including revocation and disabled accounts. Firebase client configuration is public; it is not a company-data access credential.

| Role | Visibility and actions |
| --- | --- |
| Owner | Organization-wide measurements for active sharing members; invite employees/managers; remove members; revoke devices |
| Manager | Measurements and employee administration within granted teams; capture-time team restrictions also apply to history |
| Employee | Own measurements and own devices only |

Organizations isolate companies; team grants additionally restrict managers inside a company. The server enforces both.

Employees control their sharing through the phone; existing account-backed employees retain the self-sharing controls. A manager cannot enable another employee’s sharing or authorize a device for them. Sharing is initially off. Pausing rejects new uploads and hides history from the workspace view. Re-enabling makes retained history visible again. Sharing controls are product permissions, not a claim of legal compliance or a determination of an employer’s lawful basis.

Invitations are bound to an email and role, expire after 72 hours and are single-use (a retry by the same account is idempotent). Links use a URL fragment so the invitation token is not part of server request logs. The app does not automatically send invitation messages. Removed members cannot access the company or upload data. Membership reinstatement, role changes and owner transfer do not yet have workflows; removed accounts cannot accept a new invitation to the same company.

Companies have a 100-active-member pilot limit. Accounts can join up to 20 workspaces. Invitations are capped at 100 per company/day and devices at ten active credentials per person. Credentials are revocable and stored as SHA-256 hashes; the original is returned only at creation. An authenticated company user cannot select another company or employee in an upload payload.

## Request conventions

The public base is the dashboard origin, for example `https://YOUR_SERVICE.run.app/api/v1`. Send JSON, with the following authorization:

- User requests: `Authorization: Bearer FIREBASE_ID_TOKEN`.
- Device upload: `Authorization: Bearer DEVICE_CREDENTIAL`.
- `GET /config` and the non-sensitive `GET /metrics` catalog are public. Device credentials cannot access user endpoints.

| Method | Path after `/api/v1` | Purpose |
| --- | --- | --- |
| GET | `/config` | Public Firebase configuration and local-demo availability |
| GET | `/me` | Account’s active companies |
| POST | `/organizations` | Create company with `{ "name": "Company" }` |
| GET | `/organizations/{org}/dashboard` | Role-filtered members, latest readings and device status |
| POST | `/organizations/{org}/invitations` | `{ "email": "person@example.com", "role": "employee" }`; owner may use `manager` |
| POST | `/invitations/accept` | `{ "token": "INVITATION_TOKEN" }` |
| PATCH | `/organizations/{org}/me/sharing` | `{ "enabled": true }` or false |
| POST | `/organizations/{org}/devices` | `{ "name": "My wearable", "source": "wearable" }`; `recording` for labeled tests |
| DELETE | `/organizations/{org}/devices/{device}` | Revoke credential |
| DELETE | `/organizations/{org}/members/{member}` | Owner removes a member |
| GET | `/organizations/{org}/members/{member}/history` | Latest 90 stored windows within retention, ordered oldest first |
| DELETE | `/organizations/{org}/me/readings` | Pause sharing, delete own stored windows/latest reading |
| POST | `/readings` | Authenticated batch upload below |

Errors include 401 for invalid/revoked credentials, 403 for insufficient access or paused sharing, 409 for conflicting reading IDs or action state, 410 for expired invitations, 413 for bodies over 128 KiB, 422 for invalid readings and 429 for limits. Retry 429/503 with bounded exponential backoff. Do not endlessly retry invalid credentials or paused sharing.

## Mobile upload

Legacy v1 clients sign in, accept an invitation, enable sharing and create their own credential. NEURASIGN Link instead uses the implemented QR gateway enrollment without an employee login. Store the credential in platform secure storage. Upload over HTTPS; never put credentials in URLs, logs or bundled application code.

```json
{
  "readings": [{
    "id": "stable-window-0001",
    "timestamp": "2026-09-22T12:00:00Z",
    "window_seconds": 10,
    "features": {
      "heart_rate": 74,
      "hrv": 42.1,
      "eda": null,
      "temperature": 32.4,
      "movement": null
    },
    "quality": null
  }]
}
```

The sample timestamp is illustrative: send the actual original window timestamp. At least one feature is required. HR is in bpm; HRV is RMSSD in milliseconds, not SDNN or a vendor recovery score; EDA is skin conductance in µS; temperature is skin-contact °C; movement is the standard deviation of acceleration magnitude in g over the window. Adapters must normalize these definitions and units. Omit unavailable values or send null; never derive HRV from heart rate alone. Quality, when supplied, is the gateway’s reported 0–1 estimate, not independently measured by NEURASIGN.

Maximum 60 windows per batch, 1–300 seconds per window, and 120 batch requests per device/minute. Timestamps must include a timezone, be no older than seven days and no more than five seconds ahead. Generate each reading ID once, preserve it across retries, and keep the payload unchanged. Successful replies contain `accepted`, `duplicates` and server `received_at`. Upload IDs are scoped to the device; reusing an ID with different data fails the whole batch with 409.

Late windows enter history but cannot move the latest measurement backward. Current values disappear after 60 seconds without a sufficiently recent measurement; charts retain measured timestamps. The browser polls every four seconds, so this is near-real-time monitoring, not a guaranteed emergency alert system. Signal source is fixed when the credential is created; recording input is visibly labeled and excluded from the current-wearable count. This label does not authenticate the hardware model or attest that a real sensor produced the data.

V1 stores one latest feature window per member. It does not track the latest value/freshness independently for each metric and source: an HR-only latest window has no temperature even if an earlier window contained one. Adapters must respect v1's metric definitions and window bounds; the implemented [observation contract](telemetry.md) addresses asynchronous metrics and source-specific measurement periods.

## Storage and retention

Production uses Firestore. Company data lives under `organizations/{id}`; membership is checked on every API operation. Device-key lookup and hashed-account company indexes are global internal collections. Backend service accounts use IAM; browser and phone Firestore access is denied by rules. Transactions cover invitation redemption, quotas, ingestion/deduplication, sharing and revocation so API instances can scale without process-local state.

Readings and latest readings expire after 30 days; audit metadata after 90 days. Deployment configures Firestore TTL for those groups and invitations. API responses immediately exclude readings beyond retention even when Firestore’s asynchronous TTL deletion has not yet completed. The chart shows the latest 90 windows, not a full 30-day explorer. SQLite and emulators are development alternatives; they do not implement automatic physical TTL cleanup.

Deleting measurements pauses sharing and removes active stored windows and the latest reading. A deletion lock blocks concurrent re-enabling. If a large deletion is interrupted, retry the same delete request; sharing stays paused. The deletion does not remove Firebase accounts, company membership or audit records. The prepared cloud configuration enables seven-day PITR and daily backups retained seven days, so historical backup copies can remain during that interval. Restoration must reapply subsequent deletions before allowing access. Workspace/account lifecycle and large asynchronous erasure jobs remain follow-up work.

## Current readiness

Auth, tenancy, roles, explicit sharing, persistent storage, authenticated ingestion, visible freshness and the dashboard are implemented and locally tested with actual Firebase/Firestore emulators. Cloud deployment configuration is prepared but has not been applied to the future account. The portable gateway core and standard BLE heart-rate decoder are implemented; the installable phone app, native Bluetooth/storage bindings, validated hardware support matrix, production load/restore tests and operational monitoring setup remain outstanding. Local test recordings verify transport and UI only; they do not demonstrate wearable integration.
