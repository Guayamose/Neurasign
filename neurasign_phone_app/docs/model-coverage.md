# Coverage by wearable route

Status: 2026-09-26. **No physical model is certified by NEURASIGN.** Runtime discovery determines the channels, never a brand-name guess. “Implemented” below describes software; it does not mean every sensor inside the device is accessible.

| Family / route | NEURASIGN implementation | Boundary |
| --- | --- | --- |
| Any device exposing Bluetooth Heart Rate, Thermometer or Pulse Oximeter services | Native BLE discovery and decoders, including RR, contact/energy, fast/slow oxygen/pulse and quality fields | Only exposed services and optional fields; a BLE connection does not unlock other sensors. |
| Polar H10, OH1, Verity Sense, Polar 360/Loop, Ignite 3, Vantage V3/M3, Grit X2/X2 Pro | Experimental direct PMD negotiation/decoders plus standard HR; matches protocol capabilities | These are families documented by Polar's SDK, not tested NEURASIGN model integrations. Formats, SDK mode requirements and simultaneous stream support vary. See [Polar's product matrix](https://github.com/polarofficial/polar-ble-sdk#readme). |
| Wear OS watches paired to Android | Watch companion and phone bridge compile; discovers available Android sensor types | Includes eligible Wear OS variants of Galaxy Watch, Pixel Watch, TicWatch, OnePlus and Xiaomi watches; no brand-wide hardware claim. Requires installing the matching companion and granting permissions. |
| Galaxy Watch4 and later via Samsung Health Sensor SDK | Optional binding code for HR/IBI, three PPG colors, EDA, skin/ambient temperature and spot ECG/SpO₂ | SDK binary requires Samsung sign-in and is not bundled/tested here. Device/policy restrictions apply; EDA is Watch8+, temperature Watch5+ with required firmware. [Samsung specifications](https://developer.samsung.com/health/sensor/guide/data-specifications.html). |
| WHOOP | Standard HR broadcast route can be decoded when enabled | No WHOOP proprietary raw-sensor decoder. Official documentation establishes HR broadcast, not unrestricted PPG/EDA/temperature streams. [WHOOP support](https://developer.prod.whoop.com/docs/developing/support/). |
| Garmin | Standard BLE services only when a device exposes them | Broader live data requires the Garmin Health SDK and partner access/license; that SDK integration is not implemented. [Garmin Health SDK](https://developer.garmin.com/health-sdk/). |
| Empatica E4 | UNIVERSE CSV recording transport only | Empatica retired E4 and its SDK/software on February 14, 2025. Do not promise a live E4 integration by supplying an API key. [Official retirement](https://www.empatica.com/research/e4-sunset). |
| Empatica EmbracePlus / Corsano | Not implemented | Separate product/vendor integrations. Corsano requires its Connection Package and SDK license. [Corsano developer portal](https://developer.corsano.com/). |
| Apple Watch | iPhone direct-BLE gateway exists for external sensors; Apple Watch integration does not | HealthKit stored samples, watch-side APIs and research-gated SensorKit are different routes. They do not amount to universal live raw-sensor BLE access. [HealthKit ECG](https://developer.apple.com/documentation/healthkit/hkelectrocardiogram), [SensorKit](https://developer.apple.com/documentation/sensorkit). |
| Fitbit/Pixel non-Wear-OS devices, Oura, Xiaomi Smart Band, Amazfit, Huawei | No dedicated vendor connector | They are not covered merely by the Wear OS companion. Implementing each requires a documented data route, required access and model-specific verification. Unknown GATT data are not relabeled as physiology. |

## What is shared across routes

Every implemented route ends in source/capability registration, original samples and units, timestamp/provenance, an enrollment-scoped encrypted queue, authenticated ingestion, company/team authorization and catalog-driven charts. Adding an adapter does not change employee identity or tenant permissions.

Source counts are bounded at 16 per gateway and 96 registered source/metric pairs. Changed semantics use new source IDs. The existing 120-ingestion-requests/minute limit and bounded phone queue still apply. The prototype needs throughput testing and potentially a dedicated waveform store before high-rate collection across a large company.

The server's 81 definitions include raw channel axes, indexed optical channels and quality fields. This count is **not** a count of sensors accessible on every wearable. No inference formulas, workload or fatigue heuristics changed in this expansion.
