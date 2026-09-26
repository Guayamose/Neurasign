import type { Candidate, Capability, Measurement, SourceDescriptor } from './contract.js';
import { capability, merge, uuid, type GattTransport, type Packet, type SensorStream } from './ble-protocol.js';
import { HEART_RATE_MEASUREMENT, HEART_RATE_SERVICE } from './heart-rate.js';
import { heartMeasurements, temperatureMeasurements, oxygenMeasurements, THERMOMETER_SERVICE, TEMPERATURE_MEASUREMENT, OXIMETER_SERVICE, OXIMETER_CONTINUOUS, OXIMETER_SPOT } from './standard-signals.js';
import { PMD_SERVICE, PMD_CONTROL, PMD_DATA, startPolar } from './polar-pmd.js';

export class UnsupportedWearableError extends Error {}
type Identity = Pick<SourceDescriptor, 'manufacturer' | 'model' | 'firmware'>;
export type WearableConnection = { sources: SensorStream[]; warnings: string[]; close(): Promise<void> };
export type SourceIdentity = (profile: string, capabilities: Capability[]) => Promise<string>;

/** A physical connection can expose several protocols simultaneously. Advertisement
 * UUIDs are hints only; all decisions use discovered GATT characteristics.
 */
export async function connectWearable(transport: GattTransport, candidate: Candidate, signal: AbortSignal, sourceIdentity: SourceIdentity): Promise<WearableConnection> {
  const lifetime = new AbortController();
  const abort = () => lifetime.abort(); signal.addEventListener('abort', abort, { once: true });
  if (signal.aborted) lifetime.abort();
  const connection = await transport.connect(candidate, lifetime.signal).catch(error => { signal.removeEventListener('abort', abort); throw error; });
  let closed = false;
  const close = async () => { if (closed) return; closed = true; lifetime.abort(); signal.removeEventListener('abort', abort); await connection.close(); };
  try {
    const characteristics = await connection.characteristics();
    const has = (service: string, characteristic: string, stream = true) => characteristics.some(item => uuid(item.service) === service && uuid(item.uuid) === characteristic && (!stream || item.notify || item.indicate));
    const identity: Identity = {};
    for (const [key, characteristic] of [['manufacturer', '2a29'], ['model', '2a24'], ['firmware', '2a26']] as const) {
      if (!has(uuid('180a'), uuid(characteristic), false)) continue;
      try { identity[key] = String.fromCharCode(...await connection.read(uuid('180a'), uuid(characteristic))).replace(/\0/g, '').slice(0, 80); } catch { /* Optional device information must not disable acquisition. */ }
    }
    const sources: SensorStream[] = [], warnings: string[] = [];
    async function add(id: string, label: string, capabilities: Capability[], measurements: AsyncIterable<Measurement>) {
      sources.push({ descriptor: { client_source_id: await sourceIdentity(id, capabilities), name: `${candidate.name || 'Wearable'} · ${label}`.slice(0, 80),
        adapter: { id, version: '2.0.0' }, transport: 'ble', ...identity, capabilities }, measurements });
    }
    async function* read(service: string, characteristic: string, decode: (packet: Packet) => Measurement[]) {
      for await (const packet of connection.notifications(service, characteristic, lifetime.signal)) {
        for (const row of decode(packet)) yield row;
      }
    }
    if (has(HEART_RATE_SERVICE, HEART_RATE_MEASUREMENT)) {
      await add('ble-heart-rate', 'Heart & beat intervals', [capability('heart_rate', 'bpm', 'ble-heart-rate'), capability('rr_interval', 'ms', 'ble-heart-rate-rr'), capability('heart_rate_contact', 'code', 'ble-heart-rate-contact'), capability('energy_expended', 'kJ', 'ble-heart-rate-energy-counter')], read(HEART_RATE_SERVICE, HEART_RATE_MEASUREMENT, heartMeasurements));
    }
    if (has(THERMOMETER_SERVICE, TEMPERATURE_MEASUREMENT)) {
      await add('ble-thermometer', 'Temperature', [capability('body_temperature', '°C', 'ble-health-thermometer'), capability('body_temperature_site', 'code', 'ble-health-thermometer-site')], read(THERMOMETER_SERVICE, TEMPERATURE_MEASUREMENT, temperatureMeasurements));
    }
    if (has(OXIMETER_SERVICE, OXIMETER_CONTINUOUS) || has(OXIMETER_SERVICE, OXIMETER_SPOT)) {
      const spot = !has(OXIMETER_SERVICE, OXIMETER_CONTINUOUS), characteristic = spot ? OXIMETER_SPOT : OXIMETER_CONTINUOUS;
      const method = spot ? 'ble-oximeter-spot' : 'ble-oximeter-continuous';
      const channels = [capability('oxygen_saturation', '%', method), capability('heart_rate', 'bpm', method), capability('pulse_amplitude_index', '%', method), capability('oximeter_measurement_status', 'bitmask', method), capability('oximeter_sensor_status', 'bitmask', method)];
      if (!spot) for (const speed of ['fast', 'slow']) channels.push(capability(`oxygen_saturation_${speed}`, '%', method), capability(`pulse_rate_${speed}`, 'bpm', method));
      await add('ble-oximeter', 'Oxygen & pulse', channels, read(OXIMETER_SERVICE, characteristic, packet => oxygenMeasurements(packet, spot)));
    }
    if (has(PMD_SERVICE, PMD_CONTROL) && has(PMD_SERVICE, PMD_DATA)) {
      const polarLife = new AbortController(), stopPolar = () => polarLife.abort();
      lifetime.signal.addEventListener('abort', stopPolar, { once: true });
      try {
        const polar = await startPolar(connection, polarLife.signal, warnings);
        await add('polar-pmd', 'Raw sensor streams', polar.capabilities, polar.measurements);
      } catch (error) { polarLife.abort(); warnings.push(error instanceof Error ? error.message : 'Polar streaming unavailable.'); }
    }
    if (!sources.length) throw new UnsupportedWearableError(warnings.join(' ') || 'This device exposes no supported measurement channels. It needs a manufacturer connector.');
    return { sources, warnings, close };
  } catch (error) { await close().catch(() => {}); throw error; }
}

export async function* mergeWearable(sources: SensorStream[]): AsyncIterable<{ source: number; measurement: Measurement }> {
  const streams = sources.map((source, index) => (async function* () {
    for await (const measurement of source.measurements) yield { source: index, measurement };
  })());
  yield* merge(streams);
}
