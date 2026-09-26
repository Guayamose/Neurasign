# NEURASIGN Link — native application

Minimal screens: company QR / connection link, assignment confirmation, wearable discovery, connection status, pause and disconnect. No employee dashboard or login account.

## Build locally

Requires Node 22.13+ (Node 22.23 tested), Java 17+ (Java 21 tested), Android SDK 36, accepted SDK licenses and the Android NDK/CMake downloaded by Gradle. Expo Go cannot load BLE or SQLCipher; use a native build.

```bash
npm ci
npm run typecheck
npx expo prebuild --platform android --no-install
cd android
./gradlew assembleRelease -PreactNativeArchitectures=arm64-v8a,x86_64 --max-workers=4
```

Expo's generated release variant currently uses the **development signing key**. The APK is suitable for local installation/pilot evaluation; configure company release signing before store distribution. Native directories are generated from `app.config.js` and `plugins/withGateway.js`, not hand-maintained. Do not embed API/provider credentials in the application.

To use the existing loopback Docker environment:

```bash
LOCAL_GATEWAY_HTTP=1 npx expo prebuild --platform android --no-install
LOCAL_GATEWAY_HTTP=1 NODE_ENV=production npm run android:apk
adb reverse tcp:3000 tcp:3000
adb install -r artifacts/neurasign-link-local.apk
```

`android:apk` builds a standalone APK with embedded JavaScript and copies it into `artifacts/`. With `LOCAL_GATEWAY_HTTP=1`, only loopback HTTP origins are accepted in connection codes and a development label is visible. USB-connected Android phones can use `adb reverse`; a phone cannot reach the computer through its own localhost otherwise. A deployed HTTPS dashboard needs no localhost override or reverse port.

1. Open the web dashboard → **People** → create a team → add an employee.
2. Choose **Connect phone**.
3. Scan with NEURASIGN Link, or expand **Use a connection link** and paste it in the app.
4. Confirm company and employee. Find a wearable broadcasting the Bluetooth Heart Rate Service.
5. Keep the wearable nearby. Confirm incoming measurements in **Team overview**.

The QR server must be the intended company origin; the app displays it before consent. The bootstrap token is used once. A lost response can be recovered with **Retry connection** using the exact locally persisted claim. The persistent gateway credential never appears in a URL or on the screen.

## Native behavior

- Android: camera, Nearby Devices/Bluetooth, optional notifications; `connectedDevice` foreground service starts only from a foreground user action. On older Android versions, discovery needs location permission.
- iOS: camera/Bluetooth permissions, `bluetooth-central` background mode. Restoration cancels stale OS connections; collection resumes only through an explicit user action. Building/signing an IPA requires macOS/Xcode and an Apple development team; no IPA is built on Linux.
- Storage: SecureStore credentials and random SQLCipher key, encrypted SQLite WAL queue. App startup fails closed if SQLCipher is unavailable. Android backup is disabled. iOS keys use `AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY`.
- Offline: bounded reconnect/upload backoff; stable IDs and original timestamps; max 20,000 records / seven days. Oldest records are removed at that bound. A restart preserves the queue but does not automatically resume collection.
- Pause: abort capture/uploads, clear the queue and persist server-pause intent. If offline, the app says **Paused on phone · waiting for server**. Already received data cannot be withdrawn by stopping an HTTP request; server pause hides the employee's measurements from the team view.
- Disconnect: stop locally immediately; revoke server access when reachable. Keep the app open online to complete pending revocation before switching company.
- Revocation: server rejects revoked credentials immediately; an active phone checks connection state before each upload. No API secret, Firebase admin key or provider key is bundled.

## Verification boundaries

`../tests/` covers QR parsing, idempotent retries, enrollment recovery, offline privacy actions and capture/queue separation using explicit test transports. The server's `scripts/onboarding_smoke.py` covers browser QR generation, actual Firebase/Firestore, company/team permissions, labeled recording ingestion, charts and revocation. Android emulator acceptance uses the actual native application and local API. Recorded inputs establish transport semantics, not physical wearable compatibility.

Only standard BLE heart rate is implemented. Proprietary devices require a documented vendor adapter. No wearable, battery-duration or physical locked-screen test has been performed. iOS runtime behavior remains unvalidated until an Apple build/device is available.

## Acceptance commands

With the local build installed in a disposable Android emulator and the Docker stack running:

```bash
cd ../../neurasign_server_dashboard
.venv/bin/python scripts/native_phone_smoke.py
```

The script refuses physical phones and clears only the app installed in the emulator. It checks the real native UI, secure enrollment persistence after process death, Bluetooth permissions/discovery, an offline pause across restart, server acknowledgment and disconnect/revocation. It creates an isolated company and never generates physiological measurements. Run it alone; simultaneous UIAutomator sessions interfere with each other.

On WSL, if Java cannot resolve a download host while curl works, run the build with `JAVA_TOOL_OPTIONS=-Djava.net.preferIPv4Stack=true`.
