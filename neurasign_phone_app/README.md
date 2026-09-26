# NEURASIGN Phone App

**NEURASIGN Link** is a minimal wearable gateway: scan a company QR, confirm the employee, connect a wearable, send its measurements and pause/disconnect. Team analytics stay in the web dashboard. All UI is English.

```text
Wearable → native adapter → encrypted phone queue → authenticated API → company dashboard
```

- [`mobile/`](mobile/README.md): React Native / Expo native application for Android and iOS, camera QR scanning, BLE discovery/notifications, secure credentials, SQLCipher queue and connection controls.
- [`watch_app/`](watch_app/README.md): minimal Wear OS sensor companion, Android sensor discovery and optional Samsung Health Sensor binding; no employee analytics or company credentials on the watch.
- `src/`: portable measurement contract, standard BLE and Polar PMD decoders, concurrent stream collection, enrollment parser and authenticated upload client.
- `contracts/`: schemas generated from the server; `npm test` checks protocol and native-controller behavior with injected OS transports.

**Implemented connectors:** standard Bluetooth heart rate plus every supplied RR interval, Health Thermometer, Pulse Oximeter, and experimental Polar PMD streams (ECG, PPG, PPI, acceleration, gyroscope, magnetometer, temperature and pressure where exposed in supported formats). Discovery inspects actual GATT services and runs available channels concurrently. Raw sample arrays and timing survive the queue, API and history. No HRV or other interpretation is computed by these connectors.

Read the [connectivity matrix](docs/wearable-connectivity.md) and [model coverage](docs/model-coverage.md) for exact formats, time semantics and gaps. Protocol tests have passed; no physical model has been validated. Samsung EDA binding code is present, but its vendor SDK build remains blocked by the account-gated SDK download. Garmin, Apple and other vendor paths remain unimplemented. UNIVERSE recording replay validates data transport, not Empatica Bluetooth compatibility; Empatica retired the E4 software suite in February 2025.

The server stores employees independently of dashboard accounts. Owners create teams and assign managers; managers only access their granted teams. A five-minute, single-use QR connects a phone to one employee/company. No Firebase login is needed on the phone. See the [onboarding API](../neurasign_server_dashboard/docs/phone-onboarding.md).

Credentials are stored with Expo SecureStore; observations are stored in SQLCipher, with a separate random key in SecureStore. Queue namespaces include company server and gateway identity. At most 20,000 observations / seven days are retained; older records are removed. Original IDs/timestamps survive retries. Pause stops capture and discards unsent data. Offline pause/disconnect remains persisted until the server acknowledges it. Restart requires explicit resume; the app does not silently restart collection.

Android uses a foreground service with a persistent notification. iOS has Bluetooth central background mode configured, but its scheduling and termination rules still apply. Neither platform is claimed to provide uninterrupted collection. Physical background, lock-screen, Bluetooth reconnect and battery behavior require hardware validation.

Start with the [native build and test instructions](mobile/README.md). The shared core can be checked independently with `npm ci && npm test`. The [architecture](ARCHITECTURE.md) explains how additional wearable adapters join the same contract without changing tenancy or dashboard code.
