import { NativeModule, requireOptionalNativeModule } from 'expo';
import type { Candidate } from '../../src/contract';
import { connectWatch, type WatchTransport } from '../../src/watch-link';
import type { SourceIdentity } from '../../src/multisignal';

declare class WearModule extends NativeModule<{ message: (event: { node: string; message: string }) => void }> {
  peers(): Promise<{ id: string; name: string }[]>;
  send(node: string, message: string): Promise<void>;
}
const modules = {
  wear_os: requireOptionalNativeModule<WearModule>('WearLink'),
  garmin: requireOptionalNativeModule<WearModule>('GarminLink'),
  apple_watch: requireOptionalNativeModule<WearModule>('AppleWatchLink'),
};
export async function pairedWatches(): Promise<Candidate[]> {
  const results = await Promise.allSettled(Object.entries(modules).map(async ([route, native]) =>
    native ? (await native.peers()).map(peer => ({ id: peer.id, name: peer.name, services: [], route: route as Candidate['route'] })) : []));
  return results.flatMap(result => result.status === 'fulfilled' ? result.value : []);
}
export function connectPairedWatch(candidate: Candidate, session: string, signal: AbortSignal, identity: SourceIdentity) {
  const native = modules[candidate.route as keyof typeof modules];
  if (!native) throw new Error('This watch connector is unavailable on this phone.');
  const transport: WatchTransport = { send: (node, value) => native.send(node, value), listen: callback => {
    const subscription = native.addListener('message', event => callback(event.node, event.message));
    return () => subscription.remove();
  } };
  return connectWatch(transport, candidate.id, session, signal, identity);
}
