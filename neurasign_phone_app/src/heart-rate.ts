import type { Candidate, ConnectedSource, Measurement, WearableAdapter } from "./contract.js";

export const HEART_RATE_SERVICE = "0000180d-0000-1000-8000-00805f9b34fb";
export const HEART_RATE_MEASUREMENT = "00002a37-0000-1000-8000-00805f9b34fb";
const serviceId = (id: string) => id.length === 4 ? `0000${id.toLowerCase()}-0000-1000-8000-00805f9b34fb` : id.toLowerCase();

/** Decode Bluetooth SIG Heart Rate Measurement (0x2A37), little-endian.
 * RR intervals are exposed as intervals, never mislabeled as computed HRV.
 * https://www.bluetooth.com/specifications/specs/heart-rate-service-1-0/
 */
export function decodeHeartRate(bytes: Uint8Array) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let offset = 0;
  function read(size: 1 | 2): number {
    if (offset + size > view.byteLength) throw new Error("Truncated heart-rate measurement.");
    const result = size === 1 ? view.getUint8(offset) : view.getUint16(offset, true);
    offset += size;
    return result;
  }
  const flags = read(1);
  if (flags & 0xe0) throw new Error("Unknown heart-rate flags.");
  const heartRate = read(flags & 1 ? 2 : 1);
  const contact = flags & 4 ? Boolean(flags & 2) : null;
  const energyKj = flags & 8 ? read(2) : null;
  const rrIntervalsMs: number[] = [];
  if (flags & 16) while (offset < view.byteLength) rrIntervalsMs.push(read(2) * 1000 / 1024);
  if (offset !== view.byteLength) throw new Error("Unexpected heart-rate payload bytes.");
  return { heartRate, contact, energyKj, rrIntervalsMs };
}

export interface BleConnection {
  notifications(service: string, characteristic: string, signal: AbortSignal): AsyncIterable<{ bytes: Uint8Array; receivedAt: string }>;
  close(): Promise<void>;
}
/** Implement using native Android/iOS BLE. No browser or vendor dependency. */
export interface BleTransport {
  connect(candidate: Candidate, signal: AbortSignal): Promise<BleConnection>;
}

export class StandardHeartRateAdapter implements WearableAdapter {
  readonly id = "ble-heart-rate";
  constructor(private transport: BleTransport, private sourceId: (candidate: Candidate) => string) {}
  supports(candidate: Candidate): boolean {
    return candidate.services.some(id => serviceId(id) === HEART_RATE_SERVICE);
  }
  async connect(candidate: Candidate, signal: AbortSignal): Promise<ConnectedSource> {
    if (!this.supports(candidate)) throw new Error("Heart Rate Service is not available.");
    const connection = await this.transport.connect(candidate, signal);
    let closed = false;
    async function close() {
      if (!closed) { closed = true; await connection.close(); }
    }
    async function* measurements(): AsyncIterable<Measurement> {
      try {
        for await (const packet of connection.notifications(HEART_RATE_SERVICE, HEART_RATE_MEASUREMENT, signal)) {
          if (signal.aborted) return;
          const reading = decodeHeartRate(packet.bytes);
          // A supported contact sensor reporting no contact must not produce a reading.
          if (reading.contact === false || reading.heartRate <= 0) continue;
          yield { metric: "heart_rate", value: reading.heartRate, unit: "bpm", measured_at: packet.receivedAt };
        }
      } finally {
        await close();
      }
    }
    return {
      descriptor: {
        client_source_id: this.sourceId(candidate), name: candidate.name || "Heart rate sensor",
        adapter: { id: this.id, version: "1.0.0" }, transport: "ble",
        capabilities: [{ metric: "heart_rate", unit: "bpm", delivery_mode: "stream", measurement_kind: "sample",
          method: "device-reported", timestamp_basis: "phone_receipt" }],
      },
      measurements: measurements(),
      close,
    };
  }
}
