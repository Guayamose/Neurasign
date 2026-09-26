# Coverage by wearable route

Status: 2026-09-26. **No physical model is certified by NEURASIGN.** Runtime discovery determines the channels, never a brand-name guess. “Implemented” below describes software; it does not mean every sensor inside the device is accessible.

| Family / route | NEURASIGN implementation | Boundary |
| --- | --- | --- |
| Any device exposing Bluetooth Heart Rate, Thermometer or Pulse Oximeter services | Native BLE discovery and decoders, including RR, contact/energy, fast/slow oxygen/pulse and quality fields | Only exposed services and optional fields; a BLE connection does not unlock other sensors. |
| Polar H10, OH1, Verity Sense, Polar 360/Loop, Ignite 3, Vantage V3/M3, Grit X2/X2 Pro | Experimental direct PMD negotiation/decoders plus standard HR; matches protocol capabilities | These are families documented by Polar's SDK, not tested NEURASIGN model integrations. Formats, SDK mode requirements and simultaneous stream support vary. See [Polar's product matrix](https://github.com/polarofficial/polar-ble-sdk#readme). |
| Wear OS watches paired to Android | Watch companion and phone bridge compile; discovers available Android sensor types | Includes eligible Wear OS variants of Galaxy Watch, Pixel Watch, TicWatch, OnePlus and Xiaomi watches; no brand-wide hardware claim. Requires installing the matching companion and granting permissions. |
| Galaxy Watch4 and later via Samsung Health Sensor SDK | Optional binding code for HR/IBI, three PPG colors, EDA, skin/ambient temperature and spot ECG/SpO₂ | SDK binary requires Samsung sign-in and is not bundled/tested here. Device/policy restrictions apply; EDA is Watch8+, temperature Watch5+ with required firmware. [Samsung specifications](https://developer.samsung.com/health/sensor/guide/data-specifications.html). |
| WHOOP | HR broadcast plus OAuth API v2 imports for HR, RMSSD, oxygen, skin temperature and respiratory summaries | Cloud route implemented/tested with provider fixtures; OAuth credentials and real account validation pending. No proprietary raw-sensor BLE decoder. [Setup and limits](vendor-integrations.md). |
| Garmin | Connect IQ watch source + real Android companion SDK: HR/SpO₂, temperature, pressure, intervals and motion where exposed | Public SDK route implemented, generic Monkey C and Android builds pass; target/device validation pending. Garmin Connect and our watch app required. Enterprise Health SDK remains separate. [Guide](../garmin_watch/README.md). |
| Empatica E4 | UNIVERSE CSV recording transport only | Empatica retired E4 and its SDK/software on February 14, 2025. Do not promise a live E4 integration by supplying an API key. [Official retirement](https://www.empatica.com/research/e4-sunset). |
| Empatica EmbracePlus / Corsano | Not implemented | Separate product/vendor integrations. Corsano requires its Connection Package and SDK license. [Corsano developer portal](https://developer.corsano.com/). |
| Apple Watch | Native iPhone HealthKit imports + foreground WatchConnectivity/CoreMotion companion | Source code and build configuration present. Xcode compilation/runtime pending; no unrestricted PPG/EDA or continuous passive HR. [Guide](../apple_watch/README.md). |
| Fitbit / Pixel wearable records | Google Health v4 OAuth import: HR, oxygen, core temperature and recorded ECG with provenance | API adapter tested with fixtures. Actual account/API authorization pending; no proprietary BLE protocol. HRV/daily summaries without original periods are currently excluded. [Guide](vendor-integrations.md). |
| Oura, Xiaomi Smart Band, Amazfit, Huawei | No dedicated vendor connector | A record exported to Apple Health can be imported if it contains supported measurements and wearable provenance. This does not establish direct Bluetooth support. |

## What is shared across routes

Every implemented route ends in source/capability registration, original values/units, timestamp/provenance, authenticated ingestion, company/team authorization and catalog-driven charts. Device/HealthKit routes use the encrypted phone queue; OAuth cloud imports persist directly on the server under the enrolled phone’s authorization. Adding an adapter does not change employee identity or tenant permissions.

Source counts are bounded at 16 per gateway and 96 registered source/metric pairs. Changed semantics use new source IDs. The existing 120-ingestion-requests/minute limit and bounded phone queue still apply. The prototype needs throughput testing and potentially a dedicated waveform store before high-rate collection across a large company.

The server's 82 definitions include raw channel axes, indexed optical channels and quality fields. This count is **not** a count of sensors accessible on every wearable. No inference formulas, workload or fatigue heuristics changed in this expansion.
