# NEURASIGN Phone App

**NEURASIGN Link** is a minimal wearable gateway: scan a company QR, confirm the employee, connect a wearable, send its measurements and pause/disconnect. Team analytics stay in the web dashboard. All UI is English.

```text
Wearable → native adapter → encrypted phone queue → authenticated API → company dashboard
```

- [`mobile/`](mobile/README.md): React Native / Expo native application for Android and iOS, camera QR scanning, BLE discovery/notifications, secure credentials, SQLCipher queue and connection controls.
- `src/`: portable adapter/measurement contract, standard Heart Rate Service parser, enrollment parser and authenticated upload client.
- `contracts/`: schemas generated from the server; `npm test` checks protocol and native-controller behavior with injected OS transports.

**Implemented connection:** Bluetooth Heart Rate Service (`0x180D`), independent of brand names. It sends heart rate in bpm with the phone's receipt timestamp. It parses optional RR intervals but does not invent or upload HRV. No physical wearable has been tested. Manufacturer SDKs, HealthKit, Health Connect and proprietary Bluetooth protocols are not implemented.

The server stores employees independently of dashboard accounts. Owners create teams and assign managers; managers only access their granted teams. A five-minute, single-use QR connects a phone to one employee/company. No Firebase login is needed on the phone. See the [onboarding API](../neurasign_server_dashboard/docs/phone-onboarding.md).

Credentials are stored with Expo SecureStore; observations are stored in SQLCipher, with a separate random key in SecureStore. Queue namespaces include company server and gateway identity. At most 20,000 observations / seven days are retained; older records are removed. Original IDs/timestamps survive retries. Pause stops capture and discards unsent data. Offline pause/disconnect remains persisted until the server acknowledges it. Restart requires explicit resume; the app does not silently restart collection.

Android uses a foreground service with a persistent notification. iOS has Bluetooth central background mode configured, but its scheduling and termination rules still apply. Neither platform is claimed to provide uninterrupted collection. Physical background, lock-screen, Bluetooth reconnect and battery behavior require hardware validation.

Start with the [native build and test instructions](mobile/README.md). The shared core can be checked independently with `npm ci && npm test`. The [architecture](ARCHITECTURE.md) explains how additional wearable adapters join the same contract without changing tenancy or dashboard code.
