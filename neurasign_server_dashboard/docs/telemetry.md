# Wearable-independent telemetry

Implemented: capability registration, independent observations, raw sample blocks, server-side unit normalization, persistent history, per-signal freshness and a catalog-driven dashboard. The phone directory contains a portable TypeScript gateway core with concurrent standard BLE and experimental Polar PMD connectors. The native app implements BLE bindings, QR enrollment, secure credentials and encrypted queue storage. See the [connector matrix](../../neurasign_phone_app/docs/wearable-connectivity.md). Physical-device validation remains outstanding.

The server owns metric definitions, conversion, validation, storage and presentation metadata. The phone decodes the device protocol, labels quantities accurately, preserves timestamps and sends original values/units. Neither tenant authorization nor analytical decisions depend on manufacturer/model strings.

## API

All paths below start with `/api/v1`. The observation payload uses `schema_version: 2`; this is an additive contract alongside the unchanged `/readings` window endpoint.

| Method | Path | Access |
| --- | --- | --- |
| GET | `/metrics` | Public metric definitions, accepted units and freshness policies; no company data |
| GET | `/gateway/sources` | Gateway credential; only sources belonging to that credential |
| POST | `/gateway/sources` | Gateway credential with sharing enabled; register source capabilities |
| POST | `/observations` | Gateway credential with sharing enabled; upload independent readings |
| GET | `/organizations/{org}/members/{member}/observations?series_id={series}` | Verified company user with permission to view that person; latest 90 observations in the selected series |

The existing company dashboard includes `metric_catalog` and a `signals` list for each visible person. Each signal has its own status, source, definition and latest measurement. Legacy window readings remain supported and have their own detail view when present.

An existing revocable device credential acts as the gateway credential. The server derives company, employee and gateway identity from it, then verifies each source belongs to that same gateway. The payload cannot assign company/employee identity. Pausing, removal, revocation and deletion apply to the new observation path. Managers are restricted to granted teams, including capture-time history; QR enrollment binds employee phones without dashboard accounts. See [phone onboarding](phone-onboarding.md).

## Register capabilities

Send `Authorization: Bearer DEVICE_CREDENTIAL` and JSON:

```json
{
  "client_source_id": "persistent-local-source-id",
  "name": "Wrist sensor",
  "adapter": {"id": "ble-heart-rate", "version": "1.0.0"},
  "transport": "ble",
  "capabilities": [{
    "metric": "heart_rate",
    "unit": "bpm",
    "delivery_mode": "stream",
    "measurement_kind": "sample",
    "method": "device-reported",
    "timestamp_basis": "phone_receipt",
    "availability": "available"
  }]
}
```

Use the returned `source.id` in uploads. Repeating the same registration returns the same ID. Re-registration can update `availability` between `available`, `unsupported` and `permission_required`. Metric semantics, units, method, adapter version and source metadata are immutable; changed semantics require a new `client_source_id` so incompatible data never share a series. A gateway supports up to 16 logical sources and 96 registered source/metric pairs in this pilot. Different methods/periods for the same metric use different logical sources. The same device may therefore have separate live and overnight-summary sources.

`sample` means a point measurement with no aggregation interval; a raw block groups several point samples without averaging them. `window` requires `interval_seconds` from 1–300; `summary` accepts periods up to seven days. A variable-length summary declares `interval_variable: true` and omits capability-level `interval_seconds`; every observation must then supply its original `interval_seconds`. Fixed sources reject observation-level periods. Full periods are checked against sharing pauses and team changes. HRV, movement variability and steps require a period. The catalog now contains 82 definitions: physiological measurements, individually indexed optical channels, sensor quantities and quality/status codes. See `/metrics` for the authoritative list. Entries with `category: quality` remain available in signal detail but do not occupy the main physiological tiles. Integer status/counter samples reject fractional values. Catalog support does not establish that a live connector exists for every quantity or device. Model and manufacturer are optional metadata.

`timestamp_basis` records whether the timestamp came from the device, phone receipt, or a source record. Standard BLE heart-rate notifications use phone receipt time because that payload has no measurement timestamp. The adapter must not present a synchronization receipt time as the original measurement time for historical records.

## Upload readings

The IDs and timestamp below are illustrative. Use the returned 64-character source ID and actual observation time.

```json
{
  "schema_version": 2,
  "observations": [{
    "id": "persistent-observation-id",
    "source_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "metric": "heart_rate",
    "value": 74,
    "unit": "bpm",
    "measured_at": "2026-09-26T10:00:00Z"
  }]
}
```

An observation must match an available registered metric and its declared input unit. Values must be finite and inside the catalog's transport bounds. These bounds are not medical alarm thresholds. The server stores canonical value/unit alongside original input value/unit, method, period, adapter, source record ID when supplied, measurement time and server receipt time.

Limits: 60 observations per batch, 128 KiB request body, and a shared limit of 120 ingestion batches/minute per gateway across `/readings` and `/observations`. Original timestamps must include a timezone and fall within the past seven days with at most five seconds of future clock tolerance. Responses contain `accepted`, `duplicates` and `received_at`.

Generate each observation ID once and persist the exact payload before sending. Identical retries are idempotent; reusing an ID for different content returns 409 and rolls back the batch. Late arrivals enter history without moving the latest value backward. A separate series is maintained for every source/metric. Cross-source measurements are not summed or automatically merged; source record IDs are provenance, not a cross-source deduplication guarantee.

Current initial metric freshness is 60 seconds from **measurement time**. Summaries always display `Summary`; arrival time never promotes them to current sensor data. Old samples/windows display `Delayed`. Missing/unsupported/permission states do not create readings. A source without a temperature capability cannot erase temperature arriving from another source.

Recording credentials label all their observations as recorded input. A recording transport is rejected for a wearable credential. As with the existing API, a source label is not physical hardware attestation.

## Raw sample blocks

An observation may additionally contain `samples`, `sample_offsets_ms` and an optional decimal-string `device_timestamp_ns`. The existing scalar fields remain required: `value` equals the final sample and `measured_at` is its time anchor. Offsets are ordered, finite milliseconds relative to that anchor, end at zero, and cover at most ten seconds. A block holds 1–512 samples; samples and offsets must have identical lengths. Every value is validated and normalized, with the input array retained in history. Only `sample` capabilities accept raw blocks.

The clock basis belongs to the capability. Current BLE connectors use phone receipt time; Polar retains the original 64-bit device timestamp separately and reconstructs within-packet offsets from the negotiated sample rate. This is not device/phone clock synchronization. BLE RR and Polar PPI preserve interval order at receipt time where individual beat wall-clock timestamps are unavailable.

The complete block must fall within allowed capture periods; a block crossing a team assignment must be split. The latest dashboard snapshot contains the last scalar, count and duration, while the history endpoint returns the arrays for waveform plotting. Retrying old scalar v2 observations preserves their existing content hashes. The gateway batches by both count and UTF-8 byte size (100,000 bytes, below the API limit); loss of an acknowledgment never changes IDs or samples.

## Storage, lifecycle and verification

New documents live under the existing organization boundary: `sources/{source}`, `signal_state/{member}` and `members/{member}/observations/{observation}`. Measurements expire after 30 days and disappear from responses immediately after expiry. The prepared cloud deployment adds TTL policies for observations/state and the `observations` composite index on `series_id` ascending + `timestamp` descending. Confirm the index is ready when deploying to the future project. No cloud resources were created for this work.

Deleting measurements first blocks ingestion transactionally, then removes legacy windows and observations and clears both latest caches. Paused sharing hides values/history. Revoked gateway sources disappear from current signal cards; their retained history remains accessible to authorized company users while the employee is sharing, until deletion/expiry.

Export/check portable contracts from the server directory:

```bash
PYTHONPATH=services/api .venv/bin/python scripts/export_gateway_contract.py
PYTHONPATH=services/api .venv/bin/python scripts/export_gateway_contract.py --check
.venv/bin/python -m pytest -q
```

Phone core checks, from `neurasign_phone_app`:

```bash
npm ci
npm test
```

With the local Docker stack running and phone core built, run `.venv/bin/python scripts/telemetry_smoke.py` from the server directory. It exercises the TypeScript gateway, actual Auth/Firestore emulators, API and desktop/mobile browser. It creates its own test workspace and explicitly labeled recorded fixtures; it does not establish physical wearable compatibility.

Run `.venv/bin/python scripts/raw_signals_smoke.py` with the local UNIVERSE download present to exercise actual HR, optical beat intervals, EDA, skin temperature and three acceleration axes through that same path. Values/cadence are preserved, historical times are explicitly remapped for the local recording test, and source timestamps remain in provenance. It checks exact arrays, duplicate retries, tenant isolation, sample counts in browser charts, pause and deletion. It never substitutes generated physiology when files are missing.
