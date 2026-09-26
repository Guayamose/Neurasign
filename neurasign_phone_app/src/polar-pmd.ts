/** Polar Measurement Data protocol. See docs/wearable-connectivity.md for the
 * exact supported frame types. Unknown formats fail explicitly, never become HR.
 */
import type { Capability, Measurement } from './contract.js';
import { Bytes, block, capability, type GattConnection, type Packet } from './ble-protocol.js';

export const PMD_SERVICE = 'fb005c80-02e7-f387-1cad-8acd2d8df0c8';
export const PMD_CONTROL = 'fb005c81-02e7-f387-1cad-8acd2d8df0c8';
export const PMD_DATA = 'fb005c82-02e7-f387-1cad-8acd2d8df0c8';
export type PmdSettings = Map<number, number[]>;
const widths: Record<number, number> = { 0: 2, 1: 2, 2: 2, 3: 4, 4: 1, 5: 4 };
export const pmdChannels: Record<number, [string, string][]> = {
  0: [['electrocardiogram', 'µV']],
  1: ['1', '2', '3', 'ambient'].map(channel => [`ppg_${channel}`, 'a.u.']),
  2: ['x', 'y', 'z'].map(axis => [`acceleration_${axis}`, 'g']),
  3: [['ppi_interval', 'ms'], ['ppi_error', 'ms'], ['ppi_flags', 'bitmask']],
  5: ['x', 'y', 'z'].map(axis => [`angular_velocity_${axis}`, '°/s']),
  6: ['x', 'y', 'z'].map(axis => [`magnetic_field_${axis}`, 'gauss']),
  7: [['skin_temperature', '°C']],
  11: [['barometric_pressure', 'hPa']],
  12: [['sensor_temperature', '°C']],
};

export function parseSettings(bytes: Uint8Array): PmdSettings {
  const reader = new Bytes(bytes), settings: PmdSettings = new Map();
  while (reader.offset < bytes.length) {
    const type = reader.uint(1), count = reader.uint(1), width = widths[type];
    if (!width || !count || settings.has(type)) throw new Error(`Unsupported Polar stream setting ${type}.`);
    const values = Array.from({ length: count }, () => type === 5 ? reader.float() : reader.uint(width));
    if (values.some(value => !Number.isFinite(value) || value <= 0)) throw new Error('Invalid Polar stream settings.');
    settings.set(type, values);
  }
  return settings;
}

export function chooseSettings(type: number, offered: PmdSettings): PmdSettings {
  const selected: PmdSettings = new Map();
  for (const [key, options] of offered) {
    if (key === 5) { selected.set(key, [options[0]!]); continue; }
    let choice = Math.max(...options);
    if (key === 4) {
      const channels = pmdChannels[type]!.length;
      if (!options.includes(channels)) throw new Error(`Polar channel layout ${options.join('/')} requires another decoder.`);
      choice = channels;
    }
    selected.set(key, [choice]);
  }
  if (!selected.get(0)?.[0]) throw new Error('Polar did not provide a sampling frequency.');
  return selected;
}

export function serializeSettings(settings: PmdSettings): Uint8Array {
  const output: number[] = [];
  for (const [type, values] of settings) {
    if (type === 5) continue; // The conversion factor is returned by the device.
    output.push(type, 1);
    const value = values[0]!, width = widths[type]!;
    for (let n = 0; n < width; n++) output.push(Math.floor(value / 2 ** (8 * n)) & 255);
  }
  return Uint8Array.from(output);
}

/** Signed delta blocks, LSB first. Float blocks encode deltas of IEEE754 bit patterns. */
export function decodeDelta(bytes: Uint8Array, channels: number, resolution: number): number[][] {
  if (![8, 16, 24, 32].includes(resolution) || channels < 1 || channels > 4) throw new Error('Unsupported Polar delta format.');
  const reader = new Bytes(bytes), values = Array.from({ length: channels }, () => reader.int(resolution / 8));
  const rows = [[...values]];
  while (reader.offset < bytes.length) {
    const bits = reader.uint(1), count = reader.uint(1);
    if (bits < 1 || bits > 32 || count < 1 || rows.length + count > 512) throw new Error('Invalid Polar delta block.');
    const bitCount = bits * count * channels, start = reader.take(Math.ceil(bitCount / 8));
    let bit = 0;
    for (let sample = 0; sample < count; sample++) {
      for (let channel = 0; channel < channels; channel++) {
        let delta = 0;
        for (let n = 0; n < bits; n++, bit++) delta += ((bytes[start + Math.floor(bit / 8)]! >> (bit % 8)) & 1) * 2 ** n;
        if (delta >= 2 ** (bits - 1)) delta -= 2 ** bits;
        values[channel] = (values[channel]! + delta) | 0;
      }
      rows.push([...values]);
    }
  }
  return rows;
}

const bitsToFloat = (bits: number) => { const data = new DataView(new ArrayBuffer(4)); data.setInt32(0, bits, true); return data.getFloat32(0, true); };

export function decodePmd(packet: Packet, settings: PmdSettings): Measurement[] {
  const reader = new Bytes(packet.bytes), type = reader.uint(1);
  if (!pmdChannels[type]) throw new Error(`Unsupported Polar measurement type ${type}.`);
  const low = reader.uint(4), high = reader.uint(4), deviceTime = (BigInt(high) * 4294967296n + BigInt(low)).toString();
  const frame = reader.uint(1), format = frame & 127, compressed = Boolean(frame & 128);
  const payload = packet.bytes.slice(reader.offset);
  if (type === 3) {
    if (format || compressed || !payload.length || payload.length % 6) throw new Error('Unsupported Polar PPI frame.');
    const body = new Bytes(payload), values: number[][] = [[], [], []];
    while (body.offset < payload.length) {
      body.uint(1); // HR is delivered separately by the Heart Rate Service.
      values[0]!.push(body.uint(2)); values[1]!.push(body.uint(2)); values[2]!.push(body.uint(1));
    }
    // Retain interval, error and flags together, including zero/unavailable intervals.
    return pmdChannels[type]!.map(([metric, unit], index) => block(metric, unit, values[index]!, packet.receivedAt, undefined, deviceTime));
  }
  const rate = settings.get(0)?.[0], factor = settings.get(5)?.[0] ?? 1;
  if (!rate || !Number.isFinite(rate) || rate <= 0) throw new Error('Missing Polar sample rate.');
  const channels = pmdChannels[type]!.length;
  const floating = [7, 11, 12].includes(type) || type === 5 && format === 1;
  let width: number;
  if (type === 0 && format === 0 && !compressed || type === 1 && format === 0) width = 3;
  else if (type === 2 && format <= 2) width = compressed ? format === 0 ? 2 : format === 1 ? 4 : 0 : format + 1;
  else if ((type === 5 || type === 6) && format === 0 && compressed) width = 2;
  else if (floating && (format === 0 || type === 5 && format === 1)) width = 4;
  else throw new Error(`Unsupported Polar frame ${type}/${frame}.`);
  if (!width || !payload.length) throw new Error('Unsupported Polar sample layout.');
  let samples: number[][];
  if (compressed) {
    samples = decodeDelta(payload, channels, width * 8);
    if (floating) samples = samples.map(row => row.map(bitsToFloat));
  } else {
    if (payload.length % (width * channels)) throw new Error('Truncated Polar sample.');
    const body = new Bytes(payload); samples = [];
    while (body.offset < payload.length) samples.push(Array.from({ length: channels }, () => floating ? body.float() : body.int(width)));
  }
  // Polar compressed ACC type 0 is in g; raw ACC and compressed type 1 are mg.
  const scale = type === 2 && !(compressed && format === 0) ? .001 : 1;
  const conversion = (compressed ? factor : 1) * scale;
  const offsets = samples.map((_, index) => (index - samples.length + 1) * 1000 / rate);
  return pmdChannels[type]!.map(([metric, unit], channel) => block(metric, unit, samples.map(row => row[channel]! * conversion), packet.receivedAt, offsets, deviceTime));
}

class ControlPoint {
  private pending?: { op: number; type: number; values: number[]; resolve: (data: Uint8Array) => void; reject: (error: Error) => void };
  private failure?: Error;
  constructor(private connection: GattConnection, private signal: AbortSignal) {
    void this.read().catch(error => { this.failure = error; this.pending?.reject(error); });
  }
  private async read() {
    try {
      for await (const { bytes } of this.connection.notifications(PMD_SERVICE, PMD_CONTROL, this.signal)) {
        if (bytes[0] !== 0xf0) continue;
        const pending = this.pending;
        if (!pending || bytes[1] !== pending.op || bytes[2] !== pending.type) continue;
        if (bytes.length < 4) { pending.reject(new Error('Truncated Polar control response.')); continue; }
        if (bytes[3] !== 0) { pending.reject(new Error(`Polar rejected stream ${pending.type} (status ${bytes[3]}).`)); continue; }
        if (bytes.length < 5 || (bytes[4] !== 0 && bytes[4] !== 1)) { pending.reject(new Error('Invalid Polar response continuation.')); continue; }
        pending.values.push(...bytes.slice(5));
        if (pending.values.length > 8192) { pending.reject(new Error('Polar settings response too large.')); continue; }
        if (!bytes[4]) pending.resolve(Uint8Array.from(pending.values));
      }
    } finally { this.pending?.reject(new Error('Polar control connection ended.')); }
  }
  async command(op: number, type: number, settings: Uint8Array = new Uint8Array()): Promise<Uint8Array> {
    if (this.signal.aborted) throw new Error('Connection cancelled.');
    if (this.failure) throw this.failure;
    if (this.pending) throw new Error('Concurrent Polar control command.');
    let timeout: ReturnType<typeof setTimeout> | undefined;
    const abort = () => this.pending?.reject(new Error('Connection cancelled.'));
    try {
      return await new Promise<Uint8Array>((resolve, reject) => {
        this.pending = { op, type, values: [], resolve, reject };
        this.signal.addEventListener('abort', abort, { once: true });
        timeout = setTimeout(() => reject(new Error('Polar stream negotiation timed out.')), 8000);
        void this.connection.write(PMD_SERVICE, PMD_CONTROL, Uint8Array.from([op, type, ...settings])).catch(reject);
      });
    } finally { clearTimeout(timeout); this.signal.removeEventListener('abort', abort); this.pending = undefined; }
  }
}

export async function startPolar(connection: GattConnection, signal: AbortSignal, warnings: string[]) {
  const control = new ControlPoint(connection, signal);
  const feature = await connection.read(PMD_SERVICE, PMD_CONTROL);
  if (feature.length < 3 || feature[0] !== 0x0f) throw new Error('Unsupported Polar feature response.');
  // Activate notifications before any start command. Keep the first packet for the consumer.
  const iterator = connection.notifications(PMD_SERVICE, PMD_DATA, signal)[Symbol.asyncIterator]();
  let pending = iterator.next(); void pending.catch(() => {});
  const active = new Map<number, PmdSettings>(), capabilities: Capability[] = [];
  for (const [typeString, channels] of Object.entries(pmdChannels)) {
    const type = Number(typeString);
    if (!(feature[1 + Math.floor(type / 8)]! & (1 << (type % 8)))) continue;
    try {
      const settings = type === 3 ? new Map<number, number[]>() : chooseSettings(type, parseSettings(await control.command(1, type)));
      const result = parseSettings(await control.command(2, type, serializeSettings(settings)));
      if (result.has(5)) settings.set(5, result.get(5)!);
      active.set(type, settings);
      for (const [metric, unit] of channels) capabilities.push(capability(metric, unit, `polar-pmd-v1:${type}:${JSON.stringify([...settings])}`));
    } catch (error) { warnings.push(error instanceof Error ? error.message : `Polar stream ${type} unavailable.`); }
  }
  if (!active.size) throw new Error(warnings.join(' ') || 'No supported Polar streams were available.');
  async function* measurements(): AsyncIterable<Measurement> {
    try {
      while (!signal.aborted) {
        const result = await pending;
        if (result.done) return;
        pending = iterator.next(); void pending.catch(() => {});
        const type = result.value.bytes[0]!, settings = active.get(type);
        if (!settings) continue;
        for (const row of decodePmd(result.value, settings)) yield row;
      }
    } finally { void iterator.return?.().catch(() => {}); }
  }
  return { capabilities, measurements: measurements() };
}
