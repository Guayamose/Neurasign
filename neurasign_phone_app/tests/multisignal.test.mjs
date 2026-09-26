import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { Bytes, decimalFloat } from '../dist/ble-protocol.js';
import { heartMeasurements, temperatureMeasurements, oxygenMeasurements, THERMOMETER_SERVICE, TEMPERATURE_MEASUREMENT, OXIMETER_SERVICE, OXIMETER_CONTINUOUS } from '../dist/standard-signals.js';
import { HEART_RATE_SERVICE, HEART_RATE_MEASUREMENT } from '../dist/heart-rate.js';
import { decodeDelta, decodePmd, parseSettings, chooseSettings, PMD_SERVICE, PMD_CONTROL, PMD_DATA } from '../dist/polar-pmd.js';
import { connectWearable, mergeWearable, UnsupportedWearableError } from '../dist/multisignal.js';

const time = '2026-09-26T10:00:00.000Z';
const packet = bytes => ({ bytes: Uint8Array.from(bytes), receivedAt: time });
const pmd = (type, frame, bytes) => packet([type, 1, 0, 0, 0, 0, 0, 0, 0, frame, ...bytes]);
const settings = new Map([[0, [100]], [1, [16]], [4, [3]], [5, [.001]]]);

test('HR notifications preserve every RR interval without creating HRV or invented beat times', () => {
  const rows = heartMeasurements(packet([16, 72, 0, 4, 0, 2]));
  assert.deepEqual(rows.map(row => row.metric), ['heart_rate', 'rr_interval']);
  assert.deepEqual(rows[1].samples, [1000, 500]);
  assert.deepEqual(rows[1].sample_offsets_ms, [0, 0]);
  assert.equal(rows[1].measured_at, time);
  assert.deepEqual(heartMeasurements(packet([4, 70])).map(row => [row.metric, row.value]), [['heart_rate_contact', 0]]);
});

test('11073 reserved values, signed decimal exponents and thermometer measurement site are handled', () => {
  for (const raw of [0x07fe, 0x07ff, 0x0800, 0x0801, 0x0802]) assert.equal(decimalFloat(new Bytes(Uint8Array.of(raw & 255, raw >> 8)), 2), null);
  assert.equal(decimalFloat(new Bytes(Uint8Array.of(0x62, 0xf2)), 2), 61);
  // 365 * 10^-1 = 36.5 C, site 6 = mouth, NOT skin.
  const temperature = temperatureMeasurements(packet([4, 0x6d, 1, 0, 255, 6]));
  assert.equal(temperature[0].metric, 'body_temperature');
  assert.equal(temperature[0].value, 36.5);
  assert.throws(() => temperatureMeasurements(packet([2, 1, 0, 0, 0])), /Truncated/);
});

test('oximeter preserves oxygen and pulse and distinguishes validated from invalid flags', () => {
  assert.deepEqual(oxygenMeasurements(packet([0, 98, 0, 72, 0])).map(row => [row.metric, row.value]), [['oxygen_saturation', 98], ['heart_rate', 72]]);
  assert.equal(oxygenMeasurements(packet([4, 98, 0, 72, 0, 128, 1])).length, 3); // validated + qualified + raw flags
  assert.deepEqual(oxygenMeasurements(packet([4, 98, 0, 72, 0, 0, 128])).map(row => row.metric), ['oximeter_measurement_status']); // invalid
  assert.deepEqual(oxygenMeasurements(packet([4, 98, 0, 72, 0, 0, 4])).map(row => row.metric), ['oximeter_measurement_status']); // demonstration
  assert.equal(oxygenMeasurements(packet([0, 255, 7, 72, 0])).length, 1); // unavailable oxygen
  assert.throws(() => oxygenMeasurements(packet([1, 98, 0, 72, 0])), /Truncated/);
});

test('Polar raw ECG and accelerometer blocks preserve signed samples and timing', () => {
  const ecg = decodePmd(pmd(0, 0, [255, 255, 255, 2, 0, 0]), settings)[0];
  assert.deepEqual(ecg.samples, [-1, 2]);
  assert.deepEqual(ecg.sample_offsets_ms, [-10, 0]);
  assert.equal(ecg.device_timestamp_ns, '1');
  const acc = decodePmd(pmd(2, 1, [232, 3, 24, 252, 0, 0]), settings);
  assert.deepEqual(acc.map(row => [row.metric, row.value]), [['acceleration_x', 1], ['acceleration_y', -1], ['acceleration_z', 0]]);
});

test('Polar signed deltas cross byte boundaries and apply the device conversion factor', () => {
  // Three 16-bit seeds; two delta rows with 4 bits/value: [1,-1,2],[-2,0,-1].
  const bytes = Uint8Array.from([100, 0, 200, 0, 44, 1, 4, 2, 0xf1, 0xe2, 0xf0]);
  assert.deepEqual(decodeDelta(bytes, 3, 16), [[100, 200, 300], [101, 199, 302], [99, 199, 301]]);
  const rows = decodePmd(pmd(2, 128, bytes), settings);
  assert.deepEqual(rows[0].samples, [.1, .101, .099]);
  assert.deepEqual(rows[0].sample_offsets_ms, [-20, -10, 0]);
  assert.throws(() => decodeDelta(bytes.slice(0, -1), 3, 16), /Truncated/);
  assert.throws(() => decodePmd(pmd(1, 7, [1, 2, 3]), settings), /Unsupported/);
});

test('Polar PPG, skin temperature and PPI are transported independently', () => {
  const ppg = decodePmd(pmd(1, 0, [1, 0, 0, 2, 0, 0, 3, 0, 0, 4, 0, 0]), new Map([...settings, [4, [4]]]));
  assert.deepEqual(ppg.map(row => row.metric), ['ppg_1', 'ppg_2', 'ppg_3', 'ppg_ambient']);
  const temperature = new Uint8Array(4); new DataView(temperature.buffer).setFloat32(0, 32.5, true);
  assert.equal(decodePmd(pmd(7, 0, temperature), settings)[0].value, 32.5);
  const ppi = decodePmd(pmd(3, 0, [72, 0x20, 3, 5, 0, 2, 0, 0, 0, 50, 0, 1]), new Map());
  assert.deepEqual(ppi[0].samples, [800, 0]);
  assert.deepEqual(ppi[1].samples, [5, 50]);
  assert.deepEqual(ppi[2].samples, [2, 1]);
});

test('Polar settings reject unknown layouts and preserve device-supported frequencies', () => {
  const offered = parseSettings(Uint8Array.from([0, 2, 50, 0, 200, 0, 1, 1, 16, 0, 4, 1, 3]));
  assert.equal(chooseSettings(2, offered).get(0)[0], 200);
  assert.equal(chooseSettings(1, offered).get(4)[0], 3);
  assert.throws(() => chooseSettings(1, new Map([[0, [100]], [4, [7]]])), /layout/);
  assert.throws(() => parseSettings(Uint8Array.from([20, 1, 0])), /Unsupported/);
  assert.throws(() => parseSettings(Uint8Array.from([0, 2, 50])), /Truncated/);
});

test('optional BLE energy, contact, fast/slow oximeter and amplitude channels survive decoding', () => {
  const heart = heartMeasurements(packet([14, 72, 234, 0]));
  assert.deepEqual(heart.map(row => [row.metric, row.value]), [['heart_rate_contact', 1], ['energy_expended', 234], ['heart_rate', 72]]);
  const oxygen = oxygenMeasurements(packet([19, 98, 0, 72, 0, 97, 0, 73, 0, 99, 0, 71, 0, 15, 0]));
  assert.deepEqual(oxygen.map(row => [row.metric, row.value]), [['oxygen_saturation', 98], ['heart_rate', 72], ['oxygen_saturation_fast', 97], ['pulse_rate_fast', 73], ['oxygen_saturation_slow', 99], ['pulse_rate_slow', 71], ['pulse_amplitude_index', 15]]);
});

test('Polar 24-channel optical frames retain signed ADC values and unsigned status without scaling flags', () => {
  const bytes = Array.from({ length: 25 }, (_, i) => i === 24 ? [255, 255, 255] : [i, 0, 0]).flat();
  const rows = decodePmd(pmd(1, 136, bytes), new Map([[0, [50]], [4, [25]], [5, [2]]]));
  assert.equal(rows.length, 25);
  assert.equal(rows[23].metric, 'ppg_24'); assert.equal(rows[23].value, 46);
  assert.equal(rows[24].metric, 'ppg_raw_flags'); assert.equal(rows[24].value, 16777215);
  assert.throws(() => decodePmd(pmd(1, 136, bytes), new Map([[0, [50]], [4, [4]]])), /layout changed/);
  assert.throws(() => decodePmd(pmd(1, 0, Array(12).fill(0)), new Map([[0, [50]], [4, [25]]])), /layout changed/);
});

test('Polar alternate electrical and magnetometer frames preserve their distinct units and metadata', () => {
  const electrical = decodePmd(pmd(0, 3, [255, 255, 255, 2, 0, 0, 128]), settings);
  assert.deepEqual(electrical.map(row => [row.metric, row.value]), [['ecg_adc_1', -1], ['ecg_adc_2', 2], ['ecg_raw_flags', 128]]);
  const magnetic = decodePmd(pmd(6, 129, [232, 3, 24, 252, 0, 0, 3, 0]), new Map([[0, [50]], [5, [2]]]));
  assert.deepEqual(magnetic.map(row => row.value), [2, -2, 0, 3]);
});

function fixture(characteristics, feature = [15, 0, 0]) {
  const pending = new Map(), buffered = new Map(), writes = [];
  let connections = 0, closed = 0;
  function emit(id, bytes) { const item = packet(bytes); if (pending.has(id)) { pending.get(id)(item); pending.delete(id); } else buffered.set(id, [...(buffered.get(id) ?? []), item]); }
  const connection = {
    characteristics: async () => characteristics.map(([service, uuid]) => ({ service, uuid, notify: true, indicate: false, read: true, write: true })),
    read: async () => Uint8Array.from(feature),
    write: async (_service, id, data) => {
      assert.equal(id, PMD_CONTROL); writes.push([...data]);
      const [op, type] = data;
      emit(PMD_CONTROL, [240, op, type, 0, 0, ...(op === 1 ? [0, 1, 100, 0, 1, 1, 16, 0, 4, 1, 3] : [])]);
    },
    async *notifications(_service, id, signal) {
      while (!signal.aborted) {
        const queue = buffered.get(id) ?? [];
        if (queue.length) { yield queue.shift(); buffered.set(id, queue); continue; }
        let abort;
        const value = await new Promise(resolve => { pending.set(id, resolve); abort = () => { pending.delete(id); resolve(null); }; signal.addEventListener('abort', abort, { once: true }); });
        signal.removeEventListener('abort', abort);
        if (value) yield value;
      }
    },
    close: async () => { closed++; },
  };
  return { transport: { connect: async () => { connections++; return connection; } }, emit, writes, get connections() { return connections; }, get closed() { return closed; } };
}
const identity = async (profile, capabilities) => createHash('sha256').update(profile + JSON.stringify(capabilities)).digest('hex');

test('one BLE connection discovers unadvertised services and carries simultaneous HR, RR, oxygen and temperature', async () => {
  const f = fixture([[HEART_RATE_SERVICE, HEART_RATE_MEASUREMENT], [THERMOMETER_SERVICE, TEMPERATURE_MEASUREMENT], [OXIMETER_SERVICE, OXIMETER_CONTINUOUS]]);
  const abort = new AbortController();
  const wearable = await connectWearable(f.transport, { id: 'address', name: 'Unknown brand', services: [] }, abort.signal, identity);
  assert.equal(f.connections, 1); assert.equal(wearable.sources.length, 3);
  f.emit(HEART_RATE_MEASUREMENT, [16, 72, 0, 4]);
  f.emit(TEMPERATURE_MEASUREMENT, [0, 0x6d, 1, 0, 255]);
  f.emit(OXIMETER_CONTINUOUS, [0, 98, 0, 72, 0]);
  const rows = [];
  try { for await (const row of mergeWearable(wearable.sources)) { rows.push(row); if (rows.length === 5) { await wearable.close(); break; } } }
  finally { await wearable.close(); }
  assert.equal(new Set(rows.map(row => row.source)).size, 3);
  assert.ok(rows.some(row => row.measurement.metric === 'rr_interval'));
  assert.equal(f.closed, 1);
});

test('Polar negotiates ACC alongside the standard HR service on the same connection', async () => {
  const f = fixture([[HEART_RATE_SERVICE, HEART_RATE_MEASUREMENT], [PMD_SERVICE, PMD_CONTROL], [PMD_SERVICE, PMD_DATA]], [15, 4, 0]);
  const wearable = await connectWearable(f.transport, { id: 'polar', name: 'Sensor', services: [] }, new AbortController().signal, identity);
  assert.equal(wearable.sources.length, 2);
  assert.deepEqual(f.writes.map(row => row.slice(0, 2)), [[1, 2], [2, 2]]);
  assert.ok(wearable.sources.flatMap(row => row.descriptor.capabilities).some(row => row.metric === 'acceleration_x'));
  f.emit(HEART_RATE_MEASUREMENT, [0, 70]);
  f.emit(PMD_DATA, [...pmd(2, 1, [232, 3, 0, 0, 0, 0]).bytes]);
  const rows = [];
  try { for await (const row of mergeWearable(wearable.sources)) { rows.push(row); if (rows.length === 4) { await wearable.close(); break; } } }
  finally { await wearable.close(); }
  assert.deepEqual(rows.filter(row => row.source === 1).map(row => row.measurement.value), [1, 0, 0]);
});

test('unknown devices fail explicitly instead of being presented as supported heart-rate wearables', async () => {
  const f = fixture([['custom', 'custom']]);
  await assert.rejects(connectWearable(f.transport, { id: 'unknown', name: 'Wearable', services: [] }, new AbortController().signal, identity), UnsupportedWearableError);
  assert.equal(f.closed, 1);
});
