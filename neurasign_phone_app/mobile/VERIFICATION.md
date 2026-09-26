# Verification — 2026-09-26

## Wear OS and extended channel follow-up

| Check | Result |
| --- | --- |
| Complete server suite | 125 passed; includes 16-source / 96-channel bounds and integral quality-code validation |
| Gateway + controller + protocol suite | 33 passed; includes expanded Polar/standard fields, watch session isolation, persistence-before-ACK, conflicting/expired retries |
| Watch JVM block tests | 2 passed; preserves large ECG sequences and sparse irregular samples across count/time bounds |
| Native TypeScript / Expo lint | Passed |
| Android phone / base watch | Both APKs built; `com.neurasign.link` and signing certificates verified identical; development signing only |
| Generated contracts | Match server schemas; 81 definitions including sensor axes and quality fields, not 81 sensors on every device |
| Next.js production build / local containers | Passed with the quality-field display change |
| Actual UNIVERSE raw integration | Seven recorded channels verified again through authenticated ingestion, Firestore and browser graphs |

Base watch artifact: `../watch_app/artifacts/neurasign-watch.apk`. Phone artifact: `artifacts/neurasign-link.apk`. The watch application is a minimal sensor companion; enrollment and company credentials remain on the phone. The phone build script explicitly refreshes its JS bundle so changes in the shared gateway directory are included.

**Outstanding:** no physical wearable, Wear OS runtime, sustained multichannel load or iOS native execution was tested. Samsung binding source is present, but the official SDK download requires a Samsung account; the Samsung variant was not built or executed. Garmin/Apple/other proprietary adapters are not implied by the metric catalog. See [model coverage](../docs/model-coverage.md) and [watch setup and limits](../watch_app/README.md).

The earlier onboarding emulator checks below are historical and do not establish watch connectivity. No two-phone test is needed or claimed.

## Earlier multi-signal expansion

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
