import { NativeModule, requireOptionalNativeModule } from 'expo';
import type { Candidate } from '../../src/contract';
import { connectWatch, type WatchTransport } from '../../src/watch-link';
import type { SourceIdentity } from '../../src/multisignal';

declare class WearModule extends NativeModule<{ message: (event: { node: string; message: string }) => void }> {
  peers(): Promise<{ id: string; name: string }[]>;
  send(node: string, message: string): Promise<void>;
}
const native = requireOptionalNativeModule<WearModule>('WearLink');
export async function pairedWatches(): Promise<Candidate[]> {
  if (!native) return [];
  return (await native.peers()).map(peer => ({ id: peer.id, name: peer.name, services: [], route: 'wear_os' }));
}
export function connectPairedWatch(candidate: Candidate, session: string, signal: AbortSignal, identity: SourceIdentity) {
  if (!native) throw new Error('Paired-watch collection requires the Android build.');
  const transport: WatchTransport = { send: (node, value) => native.send(node, value), listen: callback => {
    const subscription = native.addListener('message', event => callback(event.node, event.message));
    return () => subscription.remove();
  } };
  return connectWatch(transport, candidate.id, session, signal, identity);
}
