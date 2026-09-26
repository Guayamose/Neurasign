# Garmin watch companion

A minimal Connect IQ watch app, paired through Garmin Connect and the real `com.garmin.connectiq:ciq-companion-app-sdk:2.2.0` in the Android phone module. No company token is stored on the watch. This public route does not require the enterprise Garmin Health SDK/license; it cannot unlock that SDK's additional features.

Install the official Connect IQ SDK Manager, log in to your developer account and install a target's device profile. Generate your signing key using Garmin's instructions and keep it outside the repository. Then:

```bash
CONNECT_IQ_SDK=/path/to/sdk GARMIN_DEVELOPER_KEY=/private/path/developer.der ./build.sh venu3
```

Install the resulting `build/neurasign.prg` using Garmin's development instructions for that exact watch. Install Garmin Connect on Android, pair the watch, and install the current NEURASIGN Link phone APK. The application ID in `manifest.xml` must match the phone module. Open the watch app, press Start/tap, then **Find wearable** on the phone.

The manifest lists candidate families for building, not certified models. Other compatible profiles can be added after checking APIs and memory requirements. Devices without Connect IQ watch-app support (including many basic bands) cannot run this app.

Software validation here: public SDK 9.2.0 compiled the source to a generic PRG without a target; the compiler warns that target profiles are absent and reports dynamic-type warnings. The Android companion SDK compiled in the APK. A target-specific build, simulator messaging and physical capture remain unvalidated. The generic compile is not a deployable compatibility certification.

Channels are selected from onboard sensor availability and supported high-rate sensor types. Registration failures warn explicitly. Temperature is **sensor temperature**, and pressure is Garmin's barometric pressure, never skin temperature/blood pressure. ECG, raw PPG and EDA are not exposed by this adapter.

Timing uses the watch callback's UTC clock (second resolution). SDK timestamp arrays retain their relative offsets when available (newer firmware); otherwise all values in a block share callback time with zero offsets. Beat interval lists also share callback time. This preserves ordered values without inventing individual beat times or a sampling rate. It is not clock synchronization between the phone and watch.

The app requires remaining open, stops on exit/inactivity or after a 30-second phone lease, and retains at most 12 unacknowledged messages. Raw blocks cap at 128 values/channel, with requested rates at most 25 Hz. A reconnect creates a new session; unacknowledged samples still on the watch are not a durable offline recorder.
