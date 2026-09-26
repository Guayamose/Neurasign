/** Paired-watch transport. Tenant credentials never leave the phone. */
import type { Capability, Measurement, SourceDescriptor } from './contract.js';
import type { WearableConnection, SourceIdentity } from './multisignal.js';

export interface WatchTransport {
  send(node: string, message: string): Promise<void>;
  listen(callback: (node: string, message: string) => void): () => void;
}
type Definition = { id: string; name: string; capabilities: Capability[] };
type Hello = { kind: 'hello'; session: string; version: 1; manufacturer: string; model: string; sources: Definition[]; warnings: string[] };
const units: Record<string, string> = {
  heart_rate: 'bpm', ppi_interval: 'ms', ppi_status: 'code', electrodermal_conductance: 'µS',
  skin_temperature: '°C', sensor_temperature: '°C', oxygen_saturation: '%', electrocardiogram: 'mV',
  barometric_pressure: 'hPa', heart_rate_status: 'code', eda_status: 'code', skin_temperature_status: 'code',
  ecg_contact: 'code', ecg_sequence: 'count', oxygen_status: 'code',
};
for (const axis of ['x', 'y', 'z']) { units[`acceleration_${axis}`] = 'm/s²'; units[`angular_velocity_${axis}`] = '°/s'; units[`magnetic_field_${axis}`] = 'gauss'; }
for (const color of ['green', 'red', 'ir']) { units[`ppg_${color}`] = 'a.u.'; units[`ppg_${color}_status`] = 'code'; }
const object = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value);

export function watchHello(value: unknown, session: string): Hello {
  if (!object(value) || value.version !== 1 || value.kind !== 'hello' || value.session !== session || !Array.isArray(value.sources) || !value.sources.length || value.sources.length > 3) throw new Error('Invalid watch capabilities.');
  const ids = new Set<string>();
  for (const source of value.sources) {
    if (!object(source) || typeof source.id !== 'string' || !/^[a-z][a-z0-9-]{2,40}$/.test(source.id) || ids.has(source.id) || typeof source.name !== 'string' || source.name.length > 80 || !Array.isArray(source.capabilities) || !source.capabilities.length || source.capabilities.length > 64) throw new Error('Invalid watch source.');
    ids.add(source.id);
    const metrics = new Set<string>();
    for (const cap of source.capabilities) {
      if (!object(cap) || typeof cap.metric !== 'string' || !units[cap.metric] || cap.unit !== units[cap.metric] || metrics.has(cap.metric) || cap.measurement_kind !== 'sample' || cap.delivery_mode !== 'stream' || cap.timestamp_basis !== 'device' || typeof cap.method !== 'string' || !cap.method || cap.method.length > 256 || cap.interval_seconds != null || cap.availability && cap.availability !== 'available') throw new Error('Invalid watch measurement definition.');
      metrics.add(cap.metric);
    }
  }
  for (const field of ['manufacturer', 'model']) if (typeof value[field] !== 'string' || (value[field] as string).length > 80) throw new Error('Invalid watch identity.');
  if (!Array.isArray(value.warnings) || value.warnings.length > 20 || value.warnings.some(item => typeof item !== 'string' || item.length > 300)) throw new Error('Invalid watch warnings.');
  return value as Hello;
}

export function watchMeasurements(value: unknown, definitions: Definition[], session: string): { source: number; sequence: number; measurements: Measurement[] } {
  if (!object(value) || value.version !== 1 || value.kind !== 'samples' || value.session !== session || !Number.isSafeInteger(value.sequence) || (value.sequence as number) < 0 || !Array.isArray(value.measurements) || !value.measurements.length || value.measurements.length > 64) throw new Error('Invalid watch sample message.');
  const source = definitions.findIndex(item => item.id === value.source);
  if (source < 0) throw new Error('Unknown watch source.');
  const metrics = new Set<string>();
  const measurements = value.measurements.map(row => {
    if (!object(row)) throw new Error('Invalid watch sample.');
    const cap = definitions[source]!.capabilities.find(cap => cap.metric === row.metric);
    if (!cap || row.unit !== cap.unit || typeof row.value !== 'number' || !Number.isFinite(row.value) || typeof row.measured_at !== 'string' || !row.measured_at.endsWith('Z') || !Number.isFinite(Date.parse(row.measured_at))) throw new Error('Watch sample does not match its capability.');
    if (metrics.has(cap.metric)) throw new Error('Repeated watch channel in one message.');
    metrics.add(cap.metric);
    const samples = row.samples, offsets = row.sample_offsets_ms;
    if (!Array.isArray(samples) || !samples.length || samples.length > 512 || samples.some(n => typeof n !== 'number' || !Number.isFinite(n)) || !Array.isArray(offsets) || samples.length !== offsets.length || samples.at(-1) !== row.value || offsets.at(-1) !== 0 || offsets[0] < -10000 || offsets.some((n, i) => typeof n !== 'number' || !Number.isFinite(n) || n > 0 || i > 0 && n < offsets[i - 1])) throw new Error('Invalid watch sample block.');
    // Copy approved fields only; a watch cannot inject a tenant, source ID or method.
    return { metric: cap.metric, unit: cap.unit, value: row.value, measured_at: row.measured_at, samples: samples as number[], sample_offsets_ms: offsets as number[] };
  });
  return { source, sequence: value.sequence as number, measurements };
}

export async function connectWatch(transport: WatchTransport, node: string, session: string, signal: AbortSignal, identity: SourceIdentity): Promise<WearableConnection> {
  let hello: Hello | undefined, failure: Error | undefined, closed = false, wake: (() => void) | undefined, lastSeen = Date.now();
  let retiredThrough = -1;
  let announce: ((value: Hello) => void) | undefined, rejectHello: ((error: Error) => void) | undefined;
  const rows: { source: number; measurement: Measurement }[] = [], seen = new Map<number, string>(), persisted = new Set<number>();
  const send = (kind: string, extra = {}) => transport.send(node, JSON.stringify({ version: 1, kind, session, ...extra }));
  const fail = (error: Error) => { failure = error; rejectHello?.(error); wake?.(); };
  const remove = transport.listen((sender, message) => {
    if (closed || sender !== node) return;
    try {
      if (message.length > 100000) throw new Error('Watch message exceeds the limit.');
      const body: unknown = JSON.parse(message);
      if (!object(body) || body.version !== 1 || body.session !== session) return; // Delayed frames from previous enrollment/session.
      lastSeen = Date.now();
      if (body.kind === 'hello') {
        if (!hello) { hello = watchHello(body, session); announce?.(hello); }
      } else if (body.kind === 'warning' && hello && typeof body.message === 'string') {
        const warning = body.message.slice(0, 300);
        if (!hello.warnings.includes(warning) && hello.warnings.length < 20) hello.warnings.push(warning);
      } else if (body.kind === 'error') fail(new Error(typeof body.message === 'string' ? body.message.slice(0, 300) : 'Watch collection stopped.'));
      else if (body.kind === 'samples') {
        if (!hello) throw new Error('Watch sent samples before capabilities.');
        const decoded = watchMeasurements(body, hello.sources, session), previous = seen.get(decoded.sequence);
        if (previous) { if (previous !== message) throw new Error('Watch reused a sequence with different samples.'); if (persisted.has(decoded.sequence)) void send('ack', { sequence: decoded.sequence }).catch(fail); return; }
        if (decoded.sequence <= retiredThrough) throw new Error('Watch retry is outside the deduplication window. Reconnect to continue.');
        if (rows.length + decoded.measurements.length > 2048) throw new Error('Watch stream exceeded the phone buffer.');
        // ACK only after the consumer persists this message's last measurement.
        seen.set(decoded.sequence, message);
        for (const measurement of decoded.measurements) rows.push({ source: decoded.source, measurement: { ...measurement, source_record_id: `${session}:${decoded.sequence}:${measurement.metric}` } });
        wake?.();
      }
    } catch (error) { fail(error instanceof Error ? error : new Error('Invalid watch data.')); }
  });
  const abort = () => { closed = true; rejectHello?.(new Error('Watch connection cancelled.')); wake?.(); };
  signal.addEventListener('abort', abort, { once: true });
  let heartbeat: ReturnType<typeof setInterval> | undefined;
  const close = async () => { closed = true; clearInterval(heartbeat); signal.removeEventListener('abort', abort); remove(); wake?.(); await send('stop').catch(() => {}); };
  try {
    if (signal.aborted) throw new Error('Watch connection cancelled.');
    const announced = new Promise<Hello>((resolve, reject) => { announce = resolve; rejectHello = reject; });
    void announced.catch(() => {});
    heartbeat = setInterval(() => {
      if (Date.now() - lastSeen > 30000) { fail(new Error('Watch stopped responding. Open NEURASIGN on the watch to reconnect.')); return; }
      void send('lease').catch(fail);
    }, 10000);
    const timeout = setTimeout(() => fail(new Error('Open NEURASIGN on your paired watch and tap Start, then retry.')), 20000);
    try { await send('start'); hello = await announced; } finally { clearTimeout(timeout); }
    const descriptorSources: SourceDescriptor[] = [];
    for (const definition of hello.sources) descriptorSources.push({ client_source_id: await identity(definition.id, definition.capabilities),
      name: `${hello.model} · ${definition.name}`.slice(0, 80), manufacturer: hello.manufacturer, model: hello.model,
      adapter: { id: definition.id, version: '1.0.0' }, transport: 'vendor_sdk', capabilities: definition.capabilities });
    // Each stream consumes only its own queue; all share the transport lifecycle.
    const waiters = new Set<() => void>(); wake = () => { for (const fn of waiters) fn(); waiters.clear(); };
    const remaining = new Map<number, number>();
    async function* measurements(source: number): AsyncIterable<Measurement> {
      while (!closed && !signal.aborted) {
        if (failure) throw failure;
        const index = rows.findIndex(row => row.source === source);
        if (index < 0) { await new Promise<void>(resolve => waiters.add(resolve)); continue; }
        const row = rows.splice(index, 1)[0]!.measurement;
        const sequence = Number(row.source_record_id!.split(':')[1]);
        if (!remaining.has(sequence)) remaining.set(sequence, 1 + rows.filter(item => item.measurement.source_record_id!.split(':')[1] === String(sequence)).length);
        yield row;
        // The next() request follows the gateway's successful encrypted append.
        const count = remaining.get(sequence)! - 1;
        if (count) remaining.set(sequence, count);
        else { remaining.delete(sequence); persisted.add(sequence); await send('ack', { sequence }); if (seen.size > 128) { const oldest = persisted.values().next().value!; persisted.delete(oldest); seen.delete(oldest); retiredThrough = Math.max(retiredThrough, oldest); } }
      }
      if (failure) throw failure;
    }
    return { sources: descriptorSources.map((descriptor, index) => ({ descriptor, measurements: measurements(index) })), warnings: hello.warnings, close };
  } catch (error) { await close(); throw error; }
}
