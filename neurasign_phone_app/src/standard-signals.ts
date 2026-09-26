import type { Measurement } from './contract.js';
import { Bytes, decimalFloat, block, type Packet } from './ble-protocol.js';
import { decodeHeartRate } from './heart-rate.js';

export const THERMOMETER_SERVICE = '00001809-0000-1000-8000-00805f9b34fb';
export const TEMPERATURE_MEASUREMENT = '00002a1c-0000-1000-8000-00805f9b34fb';
export const OXIMETER_SERVICE = '00001822-0000-1000-8000-00805f9b34fb';
export const OXIMETER_CONTINUOUS = '00002a5f-0000-1000-8000-00805f9b34fb';
export const OXIMETER_SPOT = '00002a5e-0000-1000-8000-00805f9b34fb';

export function heartMeasurements(packet: Packet): Measurement[] {
  const reading = decodeHeartRate(packet.bytes);
  const rows: Measurement[] = [];
  if (reading.contact !== null) rows.push({ metric: 'heart_rate_contact', value: reading.contact ? 1 : 0, unit: 'code', measured_at: packet.receivedAt });
  if (reading.energyKj !== null) rows.push({ metric: 'energy_expended', value: reading.energyKj, unit: 'kJ', measured_at: packet.receivedAt });
  if (reading.contact === false) return rows;
  if (reading.heartRate > 0) rows.push({ metric: 'heart_rate', value: reading.heartRate, unit: 'bpm', measured_at: packet.receivedAt });
  if (reading.rrIntervalsMs.length) {
    if (reading.rrIntervalsMs.some(value => value <= 0)) throw new Error('Invalid beat interval.');
    // BLE HR carries no beat timestamps. Preserve ordered intervals at receipt time;
    // do not manufacture wall-clock beat times or label intervals as HRV.
    rows.push(block('rr_interval', 'ms', reading.rrIntervalsMs, packet.receivedAt));
  }
  return rows;
}

/** Health Thermometer sites do not establish a skin-temperature measurement.
 * A BLE Date Time has no timezone, so it is
 * never silently interpreted as UTC; the declared timestamp basis is receipt.
 */
export function temperatureMeasurements(packet: Packet): Measurement[] {
  const data = new Bytes(packet.bytes), flags = data.uint(1);
  if (flags & 0xf8) throw new Error('Unknown thermometer flags.');
  const value = decimalFloat(data, 4);
  if (flags & 2) data.take(7);
  const site = flags & 4 ? data.uint(1) : null;
  if (site !== null && (site < 1 || site > 9)) throw new Error('Unknown thermometer measurement site.');
  data.end();
  if (value === null) return [];
  const celsius = flags & 1 ? (value - 32) * 5 / 9 : value;
  const rows: Measurement[] = [{ metric: 'body_temperature', value: celsius, unit: '°C', measured_at: packet.receivedAt }];
  if (site !== null) rows.push({ metric: 'body_temperature_site', value: site, unit: 'code', measured_at: packet.receivedAt });
  return rows;
}

/** Keep oximeter pulse independent of the Heart Rate Service logical source.
 * Invalid/in-progress measurements are not represented as valid oxygen values.
 */
export function oxygenMeasurements(packet: Packet, spot = false): Measurement[] {
  const data = new Bytes(packet.bytes), flags = data.uint(1);
  if (flags & 0xe0) throw new Error('Unknown oximeter flags.');
  const oxygen = decimalFloat(data, 2), pulse = decimalFloat(data, 2);
  const extra: [string, string, number | null][] = [];
  if (spot && flags & 1) data.take(7);
  if (!spot) {
    for (const [flag, speed] of [[1, 'fast'], [2, 'slow']] as const) if (flags & flag) {
      extra.push([`oxygen_saturation_${speed}`, '%', decimalFloat(data, 2)], [`pulse_rate_${speed}`, 'bpm', decimalFloat(data, 2)]);
    }
  }
  const measurementStatus = flags & (spot ? 2 : 4) ? data.uint(2) : 0;
  const deviceStatus = flags & (spot ? 4 : 8) ? data.uint(3) : 0;
  if (flags & (spot ? 8 : 16)) extra.push(['pulse_amplitude_index', '%', decimalFloat(data, 2)]);
  data.end();
  // Stored / demonstration / testing values must never masquerade as live readings.
  // Bits 7 and 8 indicate validated / qualified data and are NOT error flags.
  const rows: Measurement[] = [];
  if (flags & (spot ? 2 : 4)) rows.push({ metric: 'oximeter_measurement_status', value: measurementStatus, unit: 'bitmask', measured_at: packet.receivedAt });
  if (flags & (spot ? 4 : 8)) rows.push({ metric: 'oximeter_sensor_status', value: deviceStatus, unit: 'bitmask', measured_at: packet.receivedAt });
  if (measurementStatus & 0xfe60 || deviceStatus & 0xfffe) return rows;
  if (oxygen !== null && oxygen >= 0 && oxygen <= 100) rows.push({ metric: 'oxygen_saturation', unit: '%', value: oxygen, measured_at: packet.receivedAt });
  if (pulse !== null && pulse > 0 && pulse <= 300) rows.push({ metric: 'heart_rate', unit: 'bpm', value: pulse, measured_at: packet.receivedAt });
  for (const [metric, unit, value] of extra) if (value !== null && value >= 0 && (metric === 'pulse_amplitude_index' || value <= (unit === '%' ? 100 : 300))) rows.push({ metric, unit, value, measured_at: packet.receivedAt });
  return rows;
}
