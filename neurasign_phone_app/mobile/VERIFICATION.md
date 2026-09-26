# Verification — 2026-09-26

## Multi-signal expansion

| Check | Result |
| --- | --- |
| Complete server suite | 123 passed; includes full-block sharing/team boundaries, unit conversion, raw history and scalar-v2 retry compatibility |
| Gateway + controller + protocol suite | 24 passed; includes HR/RR, thermometer, oximeter, Polar frames/deltas/settings, concurrent subscriptions and byte-bounded retries |
| Native TypeScript / Expo lint | Passed |
| Generated contracts | Match server schemas |
| Next.js production build / local containers | Passed; API and dashboard rebuilt |
| Real UNIVERSE raw integration | Seven channels through gateway core, Auth/Firestore, API and browser: HR, optical intervals, EDA, temperature, acceleration X/Y/Z |
| Raw integration assertions | Exact samples/offsets/provenance; lost-response duplicates; separate-company rejection; graph sample counts; mobile layout; pause/deletion |
| Android default APK | Rebuilt with multi-signal acquisition and embedded catalog; HTTPS required; development signing |

Raw integration command: `../../neurasign_server_dashboard/.venv/bin/python ../../neurasign_server_dashboard/scripts/raw_signals_smoke.py` from this directory, with Docker running, phone core built and UNIVERSE files downloaded. Screenshot: `../../neurasign_server_dashboard/artifacts/raw-signals.png`.

This expansion does not add a physical-device validation claim. The native emulator lifecycle results below are from the earlier onboarding build; they were not rerun against a physical sensor. See [connector scope and gaps](../docs/wearable-connectivity.md). The local HTTP APK and earlier Android screenshots below belong to that earlier build unless rebuilt explicitly.

## Earlier onboarding baseline

Completed locally without using a Google Cloud account:

| Check | Result |
| --- | --- |
| Server test suite | 107 passed |
| Gateway + native-controller unit tests | 13 passed |
| Generated metric/source/observation contract | Matches server schemas |
| Next.js production build | Passed; local web/API containers updated |
| Real Firebase Auth + Firestore workspace smoke | Passed, including persistence after API restart |
| Legacy browser flow | Passed: verified sign-up, invitations, sharing, labeled recording charts, revoke, sign-out |
| Generic telemetry browser flow | Passed: independent metrics, normalization, freshness, history, pause/deletion |
| New onboarding browser flow | Passed: teams, independent employees, QR/link, claim/recovery/reuse, company isolation, manager grant, telemetry, pause/revoke, desktop/mobile layout |
| Android native build | Standalone APK, arm64-v8a and x86_64, Expo 55 / RN 0.83; development signing |
| Android 15 emulator | Actual APK installed and tested against the local web proxy and Firestore |
| Native onboarding | Company/employee preview, consent, single-use claim and stored identity after process restart |
| Native privacy controls | Offline pause survives process restart, is acknowledged on reconnection; disconnect revokes server credential and survives restart |
| Native Bluetooth | OS permissions and discovery exercised; no physical sensor or fabricated measurements |
| Native storage | SQLCipher startup and encrypted on-disk SQLite header verified; enrollment persists via SecureStore |
| APK configuration | Local build explicitly allows loopback HTTP; default build requires HTTPS |
| iOS | Native project generated and JavaScript/Hermes bundle exported; no Xcode build or device execution |

Artifacts: `artifacts/neurasign-link-local.apk`, `artifacts/neurasign-link.apk`, `artifacts/android-connect.png`, `artifacts/android-confirm.png`, `artifacts/android-status.png`, `artifacts/android-paused.png`. Browser captures live under `../../neurasign_server_dashboard/artifacts/`.

Still requiring external hardware/accounts: optical camera QR scan, real BLE heart-rate notification stream, locked-screen/background/long-duration battery tests on physical Android/iOS phones, manufacturer-specific adapters, Apple signing/build, company Android release signing and the deferred Google Cloud deployment. The installed app contains no test sensor feed. Automatic physiological fixtures run only in separately labeled test workspaces.
