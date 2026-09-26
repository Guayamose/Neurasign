import { NativeModule, requireOptionalNativeModule } from 'expo';
import * as Crypto from 'expo-crypto';
import type { Capability, Measurement } from '../../src/contract';
import type { GatewaySession } from '../../src/gateway';
import { readSecret, writeSecret } from './storage';
import { importAllowed, healthCapabilities, type ImportPolicy } from '../../src/health-link';

type Record = { identity: string; name: string; manufacturer: string; model: string; kind: 'sample' | 'summary'; measurement: Measurement };
declare class HealthModule extends NativeModule {
  authorize(): Promise<boolean>;
  page(metric: string, anchor: string | null, since: number): Promise<{ records: Record[]; anchor: string; deleted: number }>;
}
const native = requireOptionalNativeModule<HealthModule>('AppleHealthLink');
export const healthKitAvailable = Boolean(native);
const digest = (value: unknown) => Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, JSON.stringify(value));
export async function syncHealthKit(session: GatewaySession, gateway: string, signal: AbortSignal, policy: ImportPolicy) {
  if (!native) throw new Error('Apple Health requires the iPhone build.');
  if (!await native.authorize()) throw new Error('Apple Health authorization was not completed.');
  const channels = new Set<string>(); const sources = new Map<string, string>(); let deleted = 0, skipped = 0;
  for (const metric of Object.keys(healthCapabilities)) {
    if (signal.aborted) break;
    const key = 'health-'+await digest([gateway, metric]);
    const cursor = await readSecret<{ anchor: string; since: number }>(key);
    const since = cursor?.since ?? Date.now()/1000-6*86400;
    const page = await native.page(metric, cursor?.anchor ?? null, since);
    if (signal.aborted) break;
    for (const record of page.records) {
      if (signal.aborted) break;
      if (!importAllowed(record.measurement, policy)) { skipped++; continue; }
      const sourceKey = await digest([gateway, record.identity]);
      let id = sources.get(sourceKey);
      if (!id) {
        const capabilities: Capability[] = Object.entries(healthCapabilities).filter(([name]) => record.kind === 'summary' ? name !== 'electrocardiogram' : !['hrv_sdnn', 'steps'].includes(name)).map(([metric, unit]) => ({ metric, unit, delivery_mode: 'sync', measurement_kind: record.kind, method: 'healthkit-wearable-record', timestamp_basis: 'source_record', ...(record.kind === 'summary' ? { interval_variable: true } : {}) }));
        id = await session.registerSource({ client_source_id: sourceKey, name: record.name.slice(0, 80), manufacturer: record.manufacturer.slice(0, 80), model: record.model.slice(0, 80), adapter: { id: 'apple-health', version: '1.0.0' }, transport: 'health_store', capabilities });
        sources.set(sourceKey, id);
      }
      // Same HealthKit record/block and contents retain their ID across retries/restarts.
      await session.capture(id, record.measurement, await digest([id, record.measurement]));
      channels.add(record.measurement.metric);
    }
    if (!signal.aborted) await writeSecret(key, { since, anchor: page.anchor });
    deleted += page.deleted;
  }
  return { channels: [...channels], warnings: [
    'Apple Health records are synced, not live. Empty channels may mean no data or read permission denied.',
    ...(skipped ? [`${skipped} records excluded by time, sharing or team boundaries.`] : []),
    ...(deleted ? ['Apple Health reports removed records. Previously uploaded company records use the dashboard deletion controls.'] : []),
  ] };
}
