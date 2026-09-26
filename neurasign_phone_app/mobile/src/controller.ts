import { AppState, Platform } from 'react-native';
import BackgroundService from 'react-native-background-actions';
import Constants from 'expo-constants';
import * as Crypto from 'expo-crypto';
import { GatewaySession, GatewayError } from '../../src/gateway';
import { AdapterRegistry, type Candidate } from '../../src/contract';
import { StandardHeartRateAdapter } from '../../src/heart-rate';
import { gatewayRequest, parseEnrollmentLink, type EnrollmentLink } from '../../src/enrollment';
import { EncryptedQueue, readSecret, writeSecret, removeSecret, secret } from './storage';
import { NativeBle } from './ble';

export const allowLocalHttp = Constants.expoConfig?.extra?.allowLocalHttp === true;
export type Preview = { company: string; employee: string; team: string | null; source: string };
type Receipt = { credential: string; gateway_id: string; organization_id: string; employee_id: string; company: string; employee: string };
type Enrollment = Receipt & { apiOrigin: string; candidate?: Candidate; intent?: 'pause' | 'disconnect'; paused?: boolean };
type Pending = EnrollmentLink & { installation_id: string; claim_secret: string; phone_name: string; consent: true };
export type LinkState = { ready: boolean; enrollment: Enrollment | null; pending: boolean; running: boolean; ble: 'connecting' | 'connected' | 'reconnecting'; offline: boolean; scanning: boolean; candidates: Candidate[]; status: string; error: string; queued: number; lastSent: number | null };
const delay = (ms: number, signal: AbortSignal) => new Promise<void>(resolve => { if (signal.aborted) return resolve(); const done = () => { clearTimeout(timer); signal.removeEventListener('abort', done); resolve(); }; const timer = setTimeout(done, ms); signal.addEventListener('abort', done); });
export class LinkController {
  state: LinkState = { ready: false, enrollment: null, pending: false, running: false, ble: 'connecting', offline: false, scanning: false, candidates: [], status: 'Starting…', error: '', queued: 0, lastSent: null };
  private listeners = new Set<() => void>();
  private queue!: EncryptedQueue;
  private ble = new NativeBle();
  private session?: GatewaySession;
  private abort?: AbortController;
  private task?: Promise<void>;
  private scanTimer?: ReturnType<typeof setTimeout>;
  private syncingIntent = false;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  snapshot = () => this.state;
  private update(patch: Partial<LinkState>) { this.state = { ...this.state, ...patch }; if (this.state.running) this.state.status = this.state.offline ? (this.state.ble === 'connected' ? 'Offline · saving on phone' : 'Offline · wearable disconnected') : ({ connecting: 'Connecting wearable…', connected: 'Wearable connected', reconnecting: 'Reconnecting wearable…' })[this.state.ble]; this.listeners.forEach(fn => fn()); }
  error = (e: unknown) => this.update({ error: e instanceof Error ? e.message : 'Connection failed. Please retry.' });
  async initialize() {
    try {
      this.queue = await EncryptedQueue.open();
      const enrollment = await readSecret<Enrollment>('enrollment');
      const pending = await readSecret<Pending>('pending-claim');
      this.update({ ready: true, enrollment, pending: Boolean(pending), queued: await this.queue.count(), status: enrollment ? (enrollment.paused ? 'Sharing paused' : 'Ready to connect') : 'Connect your company' });
      // No automatic capture after restart. Retry only a persisted privacy action.
      await this.syncIntent();
      setInterval(() => { if (AppState.currentState === 'active') void this.syncIntent().catch(this.error); }, 10000);
    } catch (e) { this.error(e); }
  }
  async preview(value: string): Promise<{ link: EnrollmentLink; preview: Preview }> {
    if (this.state.enrollment || this.state.pending) throw new Error('Disconnect the current company or finish the pending connection first.');
    const link = parseEnrollmentLink(value, allowLocalHttp);
    const preview = await gatewayRequest<Preview>(link.apiOrigin, '/enrollment/preview', { method: 'POST', body: { token: link.token } });
    if (preview.source !== 'wearable') throw new Error('This code is for a recording. Ask for a wearable connection code.');
    return { link, preview };
  }
  async enroll(link: EnrollmentLink) {
    if (this.state.enrollment || this.state.pending) throw new Error('A connection is already pending or active.');
    let installation_id = await readSecret<string>('installation-id');
    if (!installation_id) { installation_id = Crypto.randomUUID(); await writeSecret('installation-id', installation_id); }
    await writeSecret('pending-claim', { ...link, installation_id, claim_secret: secret(), phone_name: `${Platform.OS === 'android' ? 'Android' : 'iPhone'} gateway`, consent: true });
    this.update({ pending: true });
    await this.retryEnrollment();
  }
  async retryEnrollment() {
    const pending = await readSecret<Pending>('pending-claim');
    if (!pending) return;
    const { apiOrigin, ...body } = pending;
    try {
      const receipt = await gatewayRequest<Receipt>(apiOrigin, '/enrollment/claim', { method: 'POST', body });
      if (!/^nsd_[a-f0-9]{32}\.[A-Za-z0-9_-]{43}$/.test(receipt.credential) || receipt.credential.split('.')[1] !== pending.claim_secret) throw new Error('Invalid company connection response.');
      const enrollment = { ...receipt, apiOrigin };
      await writeSecret('enrollment', enrollment); await removeSecret('pending-claim');
      this.update({ enrollment, pending: false, status: 'Ready to connect', error: '' });
    } catch (e) {
      if (e instanceof GatewayError && [409, 410, 422].includes(e.status)) { await removeSecret('pending-claim'); this.update({ pending: false }); }
      throw e;
    }
  }
  async scan() {
    await this.stopScan(); this.update({ candidates: [], error: '' });
    await this.ble.scan(candidate => this.update({ candidates: [...this.state.candidates.filter(c => c.id !== candidate.id), candidate] }), e => { void this.stopScan(); this.error(e); });
    this.update({ scanning: true, status: 'Searching nearby…' });
    this.scanTimer = setTimeout(() => { void this.stopScan(); }, 12000);
  }
  async stopScan() { clearTimeout(this.scanTimer); await this.ble.stopScan(); this.update({ scanning: false, ...(this.state.scanning ? { status: 'Search complete' } : {}) }); }
  private async request<T>(path: string, method = 'GET', body?: unknown, signal?: AbortSignal): Promise<T> {
    const e = this.state.enrollment; if (!e) throw new Error('Connect your company first.');
    return gatewayRequest<T>(e.apiOrigin, path, { method, body, credential: e.credential, signal });
  }
  async start(candidate: Candidate) {
    if (this.state.running) return;
    if (AppState.currentState !== 'active') throw new Error('Open the app to start your wearable connection.');
    const e = this.state.enrollment; if (!e || e.intent === 'disconnect') throw new Error('Connect your company first.');
    await this.ble.permission(); await this.stopScan();
    if (this.syncingIntent) throw new Error('Finishing the previous sharing change. Please retry.');
    // Reserve the intent before resuming so the retry timer cannot pause a new session.
    const enrollment = { ...e, candidate, intent: undefined, paused: false };
    this.update({ enrollment });
    try { await this.request('/sharing', 'PATCH', { enabled: true }); }
    catch (error) { this.update({ enrollment: e }); throw error; }
    await writeSecret('enrollment', enrollment);
    this.update({ enrollment, running: true, ble: 'connecting', offline: false, status: 'Connecting wearable…', error: '' });
    const abort = new AbortController(); this.abort = abort;
    const session = new GatewaySession({ apiOrigin: e.apiOrigin, enrollmentId: e.gateway_id, credential: e.credential, queue: this.queue, newId: Crypto.randomUUID, allowLocalHttp }); this.session = session;
    const run = async () => { this.task = Promise.all([this.capture(candidate, session, abort.signal), this.upload(session, abort.signal)]).then(() => {}); await this.task; };
    try {
      if (Platform.OS === 'android') await BackgroundService.start(run, { taskName: 'NeurasignLink', taskTitle: 'NEURASIGN Link is active', taskDesc: 'Connecting your wearable. Tap to pause sharing.', taskIcon: { name: 'ic_launcher', type: 'mipmap' }, color: '#537941', linkingURI: 'neurasign://status', foregroundServiceType: ['connectedDevice'] });
      else void run().catch(this.error);
    } catch (error) { await this.stop(); throw error; }
  }
  private async capture(candidate: Candidate, session: GatewaySession, signal: AbortSignal) {
    const registry = new AdapterRegistry();
    // A stable one-way sensor ID prevents raw Bluetooth addresses reaching the server.
    const sourceId = await Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, `${this.state.enrollment!.gateway_id}:${candidate.id}`);
    registry.register(new StandardHeartRateAdapter(this.ble, () => sourceId));
    const adapter = registry.matching(candidate)[0];
    let backoff = 1000;
    while (!signal.aborted) {
      let connected;
      try {
        connected = await adapter.connect(candidate, signal);
        const id = await session.registerSource(connected.descriptor);
        this.update({ ble: 'connected', error: '' }); backoff = 1000;
        for await (const measurement of connected.measurements) {
          if (signal.aborted) break;
          await session.capture(id, measurement);
          this.update({ queued: await this.queue.count() });
        }
      } catch (e) { if (!signal.aborted) this.update({ ble: 'reconnecting', error: e instanceof Error ? e.message : 'Connection interrupted.' }); }
      finally { await connected?.close().catch(() => {}); }
      if (!signal.aborted) { await delay(backoff, signal); backoff = Math.min(backoff * 2, 30000); }
    }
  }
  private async upload(session: GatewaySession, signal: AbortSignal) {
    let backoff = 5000;
    while (!signal.aborted) {
      try {
        const status = await this.request<{ sharing: boolean }>('/status', 'GET', undefined, signal);
        if (!status.sharing) { void this.pause().catch(this.error); return; }
        const sent = await session.flush();
        this.update({ offline: false });
        if (sent) this.update({ lastSent: Date.now(), queued: await this.queue.count(), error: '' });
        backoff = sent === 60 ? 100 : 5000;
      } catch (e) {
        if (signal.aborted) return;
        if (e instanceof GatewayError && [401, 403, 410].includes(e.status)) { void this.revokeLocally().catch(this.error); return; }
        if (e instanceof GatewayError && e.status === 422) { void this.pause().catch(this.error); this.error(new Error('The server rejected queued measurements. Sharing paused; reconnect to retry.')); return; }
        this.update({ offline: true }); backoff = Math.min(backoff * 2, 60000);
      }
      await delay(backoff, signal);
    }
  }
  private async stop() {
    this.abort?.abort(); this.session?.close(); this.update({ running: false });
    await this.stopScan();
    await this.task?.catch(() => {}); this.task = undefined;
    if (Platform.OS === 'android' && BackgroundService.isRunning()) await BackgroundService.stop();
  }
  async pause() {
    const e = this.state.enrollment; if (!e) return;
    this.abort?.abort(); this.session?.close();
    const enrollment = { ...e, intent: 'pause' as const, paused: true };
    await writeSecret('enrollment', enrollment); this.update({ enrollment, status: 'Sharing paused' });
    await this.stop(); await this.queue.clear(); this.update({ queued: 0 });
    await this.syncIntent();
  }
  async disconnect() {
    const e = this.state.enrollment; if (!e) return;
    this.abort?.abort(); this.session?.close();
    const enrollment = { ...e, intent: 'disconnect' as const };
    await writeSecret('enrollment', enrollment); this.update({ enrollment, status: 'Disconnect pending' });
    await this.stop(); await this.queue.clear(); this.update({ queued: 0 });
    await this.syncIntent();
  }
  private async revokeLocally() {
    await this.stop(); await this.queue.clear(); await removeSecret('enrollment');
    this.update({ enrollment: null, running: false, queued: 0, status: 'Phone disconnected', error: 'Phone access has ended. Ask for a new connection code.' });
  }
  private async syncIntent() {
    const e = this.state.enrollment; if (!e?.intent || this.syncingIntent) return;
    this.syncingIntent = true;
    try {
      if (e.intent === 'disconnect') { await this.request('/connection', 'DELETE'); await removeSecret('enrollment'); this.update({ enrollment: null, status: 'Phone disconnected', error: '' }); }
      else { await this.request('/sharing', 'PATCH', { enabled: false }); const enrollment = { ...e, intent: undefined, paused: true }; await writeSecret('enrollment', enrollment); this.update({ enrollment, status: 'Sharing paused', error: '' }); }
    } catch (err) {
      if (err instanceof GatewayError && [401, 403, 410].includes(err.status)) await this.revokeLocally();
      else this.update({ status: e.intent === 'pause' ? 'Paused on phone · waiting for server' : 'Disconnected on phone · waiting for server' });
    } finally { this.syncingIntent = false; }
  }
}
