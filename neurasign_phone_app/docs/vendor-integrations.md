# WHOOP, Fitbit, Garmin and Apple routes

Implementation snapshot: 2026-09-26. These are real acquisition integrations, with no generated physiological fallback. **No physical wearable has been certified.** Vendor OAuth credentials, permissions and Apple build tools are separate prerequisites from the existing Jev/Gemini keys.

| Route | What the implementation reads | Delivery and current validation |
| --- | --- | --- |
| WHOOP API v2 | Overnight resting HR, RMSSD, SpO₂ and skin temperature; sleep respiratory rate; cycle/workout average HR | Synced summaries, with original start/end periods. OAuth, refresh, parsing, persistence and privacy boundaries pass tests using explicitly stubbed provider responses. No account has been connected here. |
| Fitbit / Google Health API v4 | Wearable HR, oxygen saturation, explicitly identified core body temperature and recorded ECG waveform | Synced records. Manual/non-wearable entries are excluded. ECG scaling/cadence and paginated imports tested. Google HRV and daily summaries currently lack an explicit period in the consumed schema; they are excluded instead of inventing one. No authorized Google Health account tested. |
| Garmin Connect IQ → Garmin Connect → Android Link | Available onboard HR/SpO₂, sensor temperature, pressure, beat intervals, acceleration, gyroscope and magnetometer | Watch app and real public Android companion SDK implemented. Android APK builds; Monkey C compiles without a device target with SDK 9.2.0. Installed target profiles and actual watch behavior remain unverified. This is **not** the enterprise Garmin Health SDK. |
| Apple Health → iPhone Link | Wearable HR, SDNN, oxygen, respiratory rate, body temperature, sleeping wrist temperature, steps and recorded ECG | Read-only HealthKit integration with per-type anchors, source/device provenance and stable IDs. Point records and interval summaries stay separate. No Xcode build or iOS runtime test has been possible on Linux. |
| Apple Watch → WatchConnectivity → iPhone Link | Available accelerometer/gyroscope/magnetometer and fresh point HR records | Minimal watchOS companion, explicit Start, foreground collection, bounded queue, ACKs and phone lease. Does not open a fake workout or promise continuous passive HR. Source code is present; Apple compilation/device testing is pending. |

## Phone flow

1. Enroll the phone with the employee's company QR.
2. For WHOOP/Fitbit, choose **Connect** under **Wearable accounts**, authorize in the provider browser, return, then **Sync**. Account linking alone does not resume sharing.
3. Linked cloud accounts also sync alongside an active BLE/watch connection while Link is in the foreground. This lets a WHOOP HR broadcast coexist with its synced summaries.
4. For Apple Health, choose **Connect Apple Health**, grant the desired read permissions and keep Link open. Apple does not disclose whether an empty query means denied read access or no records.
5. For Garmin/Apple Watch, install the corresponding watch companion, open it, select **Start**, then choose it in **Find wearable**. Garmin additionally needs Garmin Connect on Android.
6. **Pause sharing** stops acquisition and cloud imports; **Disconnect company** revokes the phone and removes stored provider credentials. Provider **Unlink** deletes local tokens and attempts remote revocation. If the provider is offline, revoke the app from the provider account settings as well.

Company identity never comes from a watch or a vendor response. The enrolled phone authorizes the server's employee/company binding. Vendor tokens remain encrypted on the API server and are never sent to the watch, dashboard or phone.

## WHOOP and Fitbit server setup

Use the reviewed [environment template](../../neurasign_server_dashboard/.env.example), preserving the existing local `.env`. Required variables:

- `INTEGRATIONS_PUBLIC_ORIGIN`: the public HTTPS origin of the dashboard/API proxy, without a trailing path. Loopback HTTP is allowed only outside production.
- `INTEGRATIONS_ENCRYPTION_KEY`: a persisted Fernet key. Generate once with `python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'` in your private setup shell; keep the value in local secrets or Secret Manager. Replacing it makes old connections unreadable and requires reconnection.
- `WHOOP_CLIENT_ID`, `WHOOP_CLIENT_SECRET`: an actual WHOOP developer OAuth application.
- `GOOGLE_HEALTH_CLIENT_ID`, `GOOGLE_HEALTH_CLIENT_SECRET`: an authorized Google OAuth web application with Google Health API access and the requested scopes. Provider approval/testing restrictions still apply.

Register exact callback URLs:

```text
https://YOUR_ORIGIN/api/v1/integrations/whoop/callback
https://YOUR_ORIGIN/api/v1/integrations/fitbit/callback
```

WHOOP requests `offline read:recovery read:sleep read:cycles read:workout`. Google requests health metrics/measurements and ECG read scopes, offline access and S256 PKCE. A denied Google ECG scope leaves other permitted channels available. This connector uses Google Health v4, not the retiring legacy Fitbit Web API.

For future Google Cloud deployment, `scripts/deploy_gcloud.py` accepts `--integrations-origin`, `--integrations-key-secret`, `--whoop-client-id`, `--whoop-client-secret`, `--google-health-client-id` and `--google-health-client-secret`. The `*-secret` arguments are **existing Secret Manager resource names**, never secret values. The default command only generates manifests; `--apply` targets an explicitly supplied future account/project. No deployment was performed for this work.

## Time, limits and privacy

- Cloud/HealthKit import is driven by the enrolled phone, once per minute while foreground sharing is active. There is no autonomous server polling after the phone closes or pauses.
- Cloud imports revisit the recent six-day window for late manufacturer uploads. Google cursors advance only after persistence; each type uses a bounded page (500 samples or two ECGs). HealthKit reads at most 256 records/two ECGs per type per pass; anchors commit after encrypted queue storage. The server accepts only its seven-day observation window.
- Identical source records/content retain stable IDs across retry/restart. Corrected vendor content is a new observation; it can replace the latest card at the same measurement time. Imports do not rewrite history or automatically propagate vendor deletions; the company deletion controls manage already uploaded records.
- WHOOP recovery values use the linked sleep record as their overnight summary context; this does not expose WHOOP’s internal HRV sampling window. Summaries carry the original record/context duration on each observation. They are marked **Summary / Synced**, not live readings. HRV SDNN and RMSSD remain separate; no workload, fatigue or concentration inference was added.
- Pause periods and team changes are checked over the full sample block/summary interval. A pause, credential revocation or provider unlink during a fetch is checked again before transactional persistence.
- OAuth states are one-use and expire in ten minutes. Cloud credentials are encrypted, server-only, and have a 30-day inactivity TTL; deploy setup enables Firestore TTL. API access logging is disabled to keep callback query strings out of Uvicorn logs. Configure external proxy/platform logs with the same care.
- Watch buffers are bounded, and phone persistence precedes ACK. Slow/disconnected transport ends the session instead of allowing an unlimited buffer. Streams can outpace phone/radio/server limits; sustained throughput and battery testing remain necessary.
- There are still 16 logical source slots and 96 source/metric pairs per gateway. Changing accounts/negotiated semantics may use another slot. The catalog contains 82 quantities; this is not a promise that every model supplies them.

## Build guides and primary references

- [Garmin companion build](../garmin_watch/README.md), [Apple build](../apple_watch/README.md).
- [WHOOP API v2](https://developer.whoop.com/api/).
- [Google Health API](https://developers.google.com/health/about), [official v4 discovery schema](https://health.googleapis.com/$discovery/rest?version=v4).
- [Garmin public Android SDK](https://github.com/garmin/connectiq-android-sdk), [Sensor API](https://developer.garmin.com/connect-iq/api-docs/Toybox/Sensor.html).
- [HealthKit anchored queries](https://developer.apple.com/documentation/healthkit/hkanchoredobjectquery), [recorded ECG](https://developer.apple.com/documentation/healthkit/hkelectrocardiogramquery), [WatchConnectivity](https://developer.apple.com/documentation/watchconnectivity/wcsession).

## Verification of this implementation

- 140 Python server tests, 36 phone/core tests and one web proxy test passed.
- Mobile TypeScript and lint checks, the Next.js production build and Android APK builds passed.
- Garmin SDK 9.2.0 reported `BUILD SUCCESSFUL` for a generic compile without installed device profiles; target compilation remains pending.
- Local Docker/Firebase/Firestore/browser acceptance passed using seven actual UNIVERSE recording channels, including full raw arrays, retries, tenant isolation, plots, pause and deletion. This validates the common transport/dashboard, not vendor hardware.
- The updated Android native UI smoke could not run because this session lacks `/dev/kvm` access. No Android runtime regression claim is based on that attempted run. Apple compilation remains unavailable without Xcode.
- A scan of all Git candidate files found no secrets; existing environment values were also checked for exact accidental copies. `.env` files, signing keys, vendor binaries and build outputs remain ignored.
