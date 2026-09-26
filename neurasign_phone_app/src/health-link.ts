import type { Measurement } from './contract.js';
export const healthCapabilities: Record<string, string> = { heart_rate: 'bpm', hrv_sdnn: 'ms', oxygen_saturation: '%', respiratory_rate: 'breaths/min', body_temperature: '°C', skin_temperature: '°C', steps: 'count', electrocardiogram: 'mV' };
export type ImportPolicy = { paused_intervals: { from: number; until: number | null }[]; team_boundaries: number[] };
/** Conservative client filter; server repeats authorization atomically on upload. */
export function importAllowed(row: Measurement, policy: ImportPolicy, now = Date.now()/1000) {
  const end = Date.parse(row.measured_at)/1000;
  const duration = -(row.sample_offsets_ms?.[0] ?? 0)/1000 || row.interval_seconds || 0;
  const start = end-duration;
  return Number.isFinite(end) && end <= now+5 && end >= now-7*86400 &&
    !policy.paused_intervals.some(period => end >= period.from && (period.until === null || start < period.until)) &&
    !policy.team_boundaries.some(boundary => start < boundary && boundary <= end);
}
