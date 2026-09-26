# Wearable connectivity — implementation status

NEURASIGN Link discovers all services on the selected BLE device and registers separate logical sources for each supported protocol. Multiple channels share one physical connection. A separate Wear OS route discovers sensors through a minimal companion installed on the paired watch; both routes enter the same phone queue and server contract. Company identity and permissions remain in the server; brand/model strings do not determine access.

**No physical model has been validated.** The entries below describe implemented decoders and software tests. A successful scan or SDK reference is not a supported-device certification.

| Connector | Measurements collected | Current boundary |
| --- | --- | --- |
| Bluetooth Heart Rate, `180D/2A37` | Heart rate, every supplied RR interval, contact status and cumulative energy expended | RR/contact/energy are optional; absence stays missing. Contact failure suppresses physiological measurements but retains contact status. |
| Bluetooth Health Thermometer, `1809/2A1C` | Body temperature, normalized to °C, and optional measurement-site code | Does not relabel thermometer data as skin/core temperature. Unzoned device date/time is not interpreted as UTC. |
| Bluetooth Pulse Oximeter, `1822/2A5F` or `2A5E` | Normal/fast/slow oxygen saturation and pulse rate, pulse-amplitude index, measurement and sensor status | Continuous preferred; otherwise spot. Optional fields are retained when supplied. Invalid, stored, demo and test measurements contribute quality fields only. |
| Polar Measurement Data, proprietary PMD service | ECG, optical PPG channels, optical pulse intervals/error/flags, acceleration, gyroscope, magnetometer, skin/sensor temperature, barometric pressure | Experimental direct protocol implementation, not the official SDK runtime. Starts only advertised PMD types and negotiates settings. Formats listed below; availability and simultaneous stream combinations depend on firmware. |
| Wear OS companion, paired Android phone | Available platform HR, acceleration, gyroscope, magnetometer, pressure and ambient/sensor temperature | Base watch and phone APKs compile with matching signing identity. Requires installation and permission on the watch. No hardware/runtime validation. |
| Optional Samsung Health Sensor SDK binding | Continuous HR/IBI, green/red/IR PPG, EDA, skin/ambient temperature; explicitly triggered ECG/SpO₂; quality codes | Adapter source implemented; official account-gated SDK absent. The base APK cannot collect Samsung-only channels. SDK variant and device access remain unvalidated. See [watch build guide](../watch_app/README.md). |
| UNIVERSE E4 recording, local acceptance script | HR, optical intervals, EDA, skin temperature, acceleration X/Y/Z | Uses actual local CSVs. Explicit recording credentials and label. This is not an Empatica live connector. BVP is not in the current local download and is not fabricated. |

## Polar formats

| PMD type | Implemented layouts |
| --- | --- |
| 0 · ECG | Raw frame 0 signed 24-bit µV; raw frames 1/2 masked µV plus status; raw frame 3 two unscaled ADC channels plus status (not labeled µV) |
| 1 · PPG | Frame 0, four signed 24-bit channels, raw or delta compressed; compressed frames 7/8/10/13 with 16/24/20/2 optical channels plus unscaled status |
| 2 · Accelerometer | Raw frames 0/1/2 (8/16/24-bit mg); compressed frame 0 (16-bit, scaled g) and frame 1 (32-bit, scaled mg) |
| 3 · PPI | Frame 0 interval, error and quality/contact flags, including zero/unavailable intervals; positive embedded heart-rate values retained separately |
| 5 · Gyroscope | Compressed frame 0, scaled 16-bit; frame 1 float32, raw or compressed |
| 6 · Magnetometer | Compressed frame 0, scaled 16-bit; compressed frame 1 with X/Y/Z and unscaled calibration status |
| 7 / 11 / 12 | Skin temperature / atmospheric pressure / sensor temperature, float32 frame 0, raw or compressed |

The connector negotiates the highest offered rate/resolution/range for each implemented layout. It preserves the device conversion factor and encodes settings in source semantics. Unsupported channel counts, settings, formats and failed start commands produce errors/warnings. Other channels can start when one type is rejected during negotiation. It does not enable SDK mode, retrieve offline files or decode every firmware extension. Unknown frames during collection stop that connection and trigger the existing reconnect path; hardware testing must establish the usable stream combinations.

## Samples and time

- Raw blocks keep every decoded channel sample, with up to 512 samples over ten seconds per observation. `value` is the last sample for the compact dashboard card; it is not an average.
- Sample offsets retain within-packet cadence. BLE timestamps are explicitly anchored to phone receipt, so packet-to-packet latency/jitter remains. Original Polar nanosecond timestamps are retained as decimal strings without loss of integer precision; device clock synchronization/drift correction is not implemented.
- RR/PPI are raw intervals, not HRV. Without beat wall-clock timestamps, their ordering is retained with zero offsets at receipt. PPI quality flags and errors travel as separate aligned channels; zero/invalid intervals must not be treated as valid beats by future analysis.
- Watch sensor events retain original event cadence using the watch wall clock. Samsung timestamps must pass the documented adapter clock checks; this has not been confirmed on a real SDK/device. Samsung IBI lists retain order at their parent DataPoint time because individual beat wall-clock times are not supplied.
- The encrypted queue and server retain arrays and provenance. Uploads stay below count/byte limits, and stable IDs make retries idempotent. Queue retention is bounded, so this is not an unlimited offline waveform recorder.
- Server permissions and sharing checks cover the full block duration. The dashboard loads raw history independently per source/metric; no scores or interpretations were added.

## Remaining connectors and validation

The optional Samsung adapter contains an EDA acquisition path, gated by the missing official SDK and compatible hardware. It is not active in the base APK. Empatica retired E4 and its SDK/software on February 14, 2025; the UNIVERSE replay is not a live connector. Garmin Health SDK, Apple Watch/watchOS, HealthKit, Health Connect, and vendor cloud routes remain unimplemented. WHOOP's documented HR broadcast does not establish open access to its other raw sensors. See the [model/route coverage matrix](model-coverage.md) for manufacturer access requirements.

The current pilot allows 16 logical sources and 96 registered source/metric pairs per gateway; source semantics are immutable, and a changed negotiated configuration can consume a new source slot. High-frequency endurance, throughput, device clock mapping, battery use, background behavior and physical Android/iOS compatibility remain unvalidated. These must be checked before a production hardware-support claim.

Automated checks: `npm test` in the phone directory covers binary decoders, concurrent discovery/streaming, unsupported devices, queue retries/byte limits and watch protocol/session/persistence semantics. `node build.mjs` in the watch directory runs JVM raw-block tests and builds the base APK. `scripts/raw_signals_smoke.py` in the server directory verifies actual UNIVERSE samples through authenticated ingestion, Firestore and browser graphs. Neither requires an additional phone or pretends to certify hardware.

## Primary protocol references

- [Bluetooth Heart Rate Service](https://www.bluetooth.com/specifications/specs/heart-rate-service-1-0/)
- [Bluetooth Pulse Oximeter Service 1.0.1](https://www.bluetooth.com/wp-content/uploads/Files/Specification/HTML/PLXS_v1.0.1/out/en/index-en.html)
- [Bluetooth GATT Specification Supplement](https://btprodspecificationrefs.blob.core.windows.net/gatt-specification-supplement/GATT_Specification_Supplement.pdf)
- [Polar SDK and protocol reference](https://github.com/polarofficial/polar-ble-sdk), including `technical_documentation/online_measurement.pdf` and Android PMD model decoders
- [Garmin Health SDK](https://developer.garmin.com/health-sdk/)
- [WHOOP developer support: HR broadcast](https://developer.prod.whoop.com/docs/developing/support/)

- [Wear OS Data Layer](https://developer.android.com/training/wearables/data/overview)
- [Samsung Health Sensor specifications](https://developer.samsung.com/health/sensor/guide/data-specifications.html)
- [Empatica E4 retirement](https://www.empatica.com/research/e4-sunset)
