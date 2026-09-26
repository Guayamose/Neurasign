# NEURASIGN Watch Link

A minimal **Wear OS → paired Android phone** sensor companion. Start/stop and optional spot measurements are the only watch controls. Company enrollment, the encrypted delivery queue and API credentials remain on the phone; team analytics remain on the dashboard.

## Build and install

Build the phone first using `../mobile/README.md`. With Java and the Android SDK configured:

```bash
export ANDROID_HOME=/path/to/Android/Sdk
node build.mjs
```

Output: `artifacts/neurasign-watch.apk`. Install this APK **on a Wear OS watch**, and `../mobile/artifacts/neurasign-link.apk` on its paired Android phone. Both use `com.neurasign.link` and the same generated development signing certificate. Configure the same company release certificate on both projects before distribution. This is not a store-signed release.

Open the watch app → **Start** → allow sensor permissions. Allow Nearby Devices on the phone so its connected-device foreground service can run. On the enrolled phone, **Find wearable** → select the paired watch. The watch must remain reachable. Stop on the watch or pause on the phone to stop capture. The watch does not resume automatically after process death.

## Collected channels

The base build discovers real Android `SensorManager` capabilities: heart rate, acceleration X/Y/Z, angular velocity X/Y/Z, magnetic field X/Y/Z, atmospheric pressure and ambient/sensor temperature. Missing sensors remain absent. There is no generated sensor feed. Ambient temperature is never labeled as skin temperature. Motion is requested at 50 Hz; delivery cadence is determined by hardware/OS and original event timing is retained to millisecond precision.

The optional Samsung binding discovers `HealthTrackerType` capabilities and implements:

- Continuous heart rate with optical beat intervals and quality codes.
- Green, red and infrared PPG with channel status.
- Skin conductance/EDA with measurement status.
- Skin and ambient temperature, kept separate.
- Explicitly triggered ECG with electrode-contact, saturation checks and sequence metadata, bounded to 30 seconds.
- Explicitly triggered SpO₂ with measurement status, bounded to 60 seconds.

EDA requires compatible hardware (Samsung documents Galaxy Watch8 series and later). Temperature requires Watch5 or later and applicable software. BIA/MF-BIA and post-workout sweat-loss are not implemented: these are separate measurement procedures requiring additional inputs, not unrestricted background raw streams.

## Samsung SDK build — external dependency outstanding

The Samsung adapter source is present, using the documented SDK API through an optional runtime binding. **The official SDK could not be downloaded here without a Samsung developer sign-in.** The base APK therefore does not contain that SDK and cannot read Samsung-only raw channels. No API binary, sample stub or fabricated measurement substitutes for it.

Download Samsung Health Sensor SDK 1.4.1 from the [official page](https://developer.samsung.com/health/sensor/overview.html), extract its AAR locally, then:

```bash
export SAMSUNG_SENSOR_AAR=/absolute/path/samsung-health-sensor-api.aar
node build.mjs --samsung
```

The Samsung build refuses to proceed without an AAR. Vendor binaries are ignored by Git. Development requires the watch's Health Sensor Service developer mode or an approved application policy; commercial distribution requires the [Samsung app process](https://developer.samsung.com/health/sensor/process.html). The Samsung variant has not been built or executed in this environment. The adapter rejects unrecognized timestamps rather than presenting receipt time as original capture time.

## Transport and lifecycle

Google's Wearable Data Layer enforces matching package names and signing certificates. The phone restricts discovery/sending to nearby nodes, and pins every stream to the selected node plus a fresh random session. Company tokens never travel to the watch. Data Layer normally uses Bluetooth nearby but can use Google's encrypted relay; proximity filtering is not a strict guarantee that no Google infrastructure is used. See the [Data Layer documentation](https://developer.android.com/training/wearables/data/overview).

The phone renews a 30-second watch lease. Expiry stops collection. The watch uses a visible foreground service and no persistent physiological storage. Bounded sample blocks preserve values and irregular timestamps (512 samples, ten seconds maximum). Acknowledgments follow the phone's encrypted append; retransmissions preserve the same sequence/payload. A full buffer or missing acknowledgment stops capture explicitly. No lossless delivery is promised across watch process death, user stop or an expired session.

Continuous Samsung trackers are flushed regularly to avoid treating delayed background batches as live data. Quality codes are kept separate; rejected optical/ECG samples are not converted to successful physiological values. On-demand measurements may interrupt continuous sensors according to vendor policy.

## Verification

`node build.mjs` runs JVM sample-block tests and produces the base APK. `npm test` in the parent directory tests watch declarations, sample validation, session/node isolation, retry conflicts and persistence-before-ACK semantics. Android phone lint/typecheck and its native build include the real Wear Link module. The server validates and plots the same raw-block contract.

No physical wearable, Wear OS runtime, Samsung SDK variant, background endurance or high-frequency sustained throughput has been validated. See the [coverage matrix](../docs/model-coverage.md) for exact boundaries.
