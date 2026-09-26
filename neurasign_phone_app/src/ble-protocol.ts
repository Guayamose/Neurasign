import type { Capability, Measurement, SourceDescriptor } from './contract.js';
import type { BleConnection, BleTransport } from './heart-rate.js';

export const uuid = (id: string) => id.length === 4 ? `0000${id.toLowerCase()}-0000-1000-8000-00805f9b34fb` : id.toLowerCase();
export type Packet = { bytes: Uint8Array; receivedAt: string };
export type GattCharacteristic = { service: string; uuid: string; notify: boolean; indicate: boolean; read: boolean; write: boolean };
export interface GattConnection extends BleConnection {
  characteristics(): Promise<GattCharacteristic[]>;
  read(service: string, characteristic: string): Promise<Uint8Array>;
  write(service: string, characteristic: string, bytes: Uint8Array): Promise<void>;
}
export interface GattTransport extends BleTransport {
  connect(...args: Parameters<BleTransport['connect']>): Promise<GattConnection>;
}
export type SensorStream = { descriptor: SourceDescriptor; measurements: AsyncIterable<Measurement> };
export const capability = (metric: string, unit: string, method: string): Capability => ({ metric, unit, method,
  delivery_mode: 'stream', measurement_kind: 'sample', timestamp_basis: 'phone_receipt' });

/** Retain every sample; the anchor is explicitly phone receipt, not a synchronized device clock. */
export function block(metric: string, unit: string, values: number[], receivedAt: string, offsets?: number[], deviceTime?: string): Measurement {
  if (!values.length || values.length > 512 || values.some(value => !Number.isFinite(value))) throw new Error('Invalid raw sample block.');
  const times = offsets ?? values.map(() => 0);
  if (times.length !== values.length || times.at(-1) !== 0 || times[0]! < -10000 || times.some((t, i) => !Number.isFinite(t) || t > 0 || i > 0 && t < times[i - 1]!)) throw new Error('Invalid sample timing.');
  return { metric, unit, value: values.at(-1)!, measured_at: receivedAt, samples: values, sample_offsets_ms: times,
    ...(deviceTime ? { device_timestamp_ns: deviceTime } : {}) };
}

/** Merge subscriptions concurrently. Consumers must abort their shared signal before closing. */
export async function* merge<T>(streams: AsyncIterable<T>[]): AsyncIterable<T> {
  const iterators = streams.map(stream => stream[Symbol.asyncIterator]());
  const pending = new Map(iterators.map((iterator, index) => [index, iterator.next().then(result => ({ index, result }))]));
  // Attach handlers immediately so an error in another channel cannot become unhandled.
  for (const promise of pending.values()) void promise.catch(() => {});
  try {
    while (pending.size) {
      const { index, result } = await Promise.race(pending.values());
      if (result.done) { pending.delete(index); continue; }
      yield result.value;
      const next = iterators[index]!.next().then(result => ({ index, result }));
      void next.catch(() => {}); pending.set(index, next);
    }
  } finally {
    // Native notifications settle on the shared abort signal / connection close.
    for (const iterator of iterators) void iterator.return?.().catch(() => {});
  }
}

export class Bytes {
  offset = 0;
  view: DataView;
  constructor(readonly data: Uint8Array) { this.view = new DataView(data.buffer, data.byteOffset, data.byteLength); }
  take(size: number) { if (this.offset + size > this.data.length) throw new Error('Truncated Bluetooth payload.'); const start = this.offset; this.offset += size; return start; }
  uint(size: number): number { const start = this.take(size); let value = 0; for (let n = 0; n < size; n++) value += this.data[start + n]! * 2 ** (n * 8); return value; }
  int(size: number): number { const value = this.uint(size); return value >= 2 ** (size * 8 - 1) ? value - 2 ** (size * 8) : value; }
  float() { return this.view.getFloat32(this.take(4), true); }
  end() { if (this.offset !== this.data.length) throw new Error('Unexpected Bluetooth payload bytes.'); }
}

/** IEEE 11073 decimal FLOAT/SFLOAT, with all reserved values excluded. */
export function decimalFloat(reader: Bytes, size: 2 | 4): number | null {
  const mantissaBits = size === 2 ? 12 : 24, exponentBits = size === 2 ? 4 : 8;
  const raw = reader.uint(size), mask = 2 ** mantissaBits - 1;
  let mantissa = raw & mask, exponent = Math.floor(raw / 2 ** mantissaBits);
  const midpoint = 2 ** (mantissaBits - 1);
  if ([midpoint - 2, midpoint - 1, midpoint, midpoint + 1, midpoint + 2].includes(mantissa)) return null;
  if (mantissa >= midpoint) mantissa -= 2 ** mantissaBits;
  if (exponent >= 2 ** (exponentBits - 1)) exponent -= 2 ** exponentBits;
  const value = mantissa * 10 ** exponent;
  return Number.isFinite(value) ? value : null;
}
