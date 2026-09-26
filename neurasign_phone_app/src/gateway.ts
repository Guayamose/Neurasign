import type { Measurement, Observation, ObservationBatch, SourceDescriptor } from "./contract.js";

/** Native implementation must encrypt at rest and persist before resolving.
 * Namespace every operation by enrollment, including after a company switch.
 * Acknowledge by ID, not queue position: capture may continue during an upload.
 */
export interface ObservationQueue {
  append(enrollment: string, row: Observation): Promise<void>;
  peek(enrollment: string, limit: number): Promise<Observation[]>;
  acknowledge(enrollment: string, ids: string[]): Promise<void>;
}

export class GatewayError extends Error {
  constructor(readonly status: number, message: string) { super(message); }
  get retryable() { return this.status === 429 || this.status >= 500; }
}

/** A session is permanently bound to one credential and queue namespace. */
export class GatewaySession {
  private stopped = false;
  private requests = new Set<AbortController>();
  close() { this.stopped = true; for (const controller of this.requests) controller.abort(); }
  private sourceIds = new Set<string>();
  private pendingFlush: Promise<number> | undefined;
  private base: string;
  constructor(private options: {
    apiOrigin: string;
    enrollmentId: string;
    credential: string;
    queue: ObservationQueue;
    newId: () => string;
    fetch?: typeof fetch;
    allowLocalHttp?: boolean;
  }) {
    const url = new URL(options.apiOrigin);
    if (url.username || url.password || url.pathname !== "/" || url.search || url.hash) throw new Error("Use an API origin without credentials, path or query.");
    const local = options.allowLocalHttp && url.protocol === "http:" && ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
    if (url.protocol !== "https:" && !local) throw new Error("Gateway uploads require HTTPS.");
    if (!options.enrollmentId || !/^nsd_[a-f0-9]{32}\.[A-Za-z0-9_-]{40,64}$/.test(options.credential)) throw new Error("A scoped gateway enrollment is required.");
    // Include the credential's non-secret gateway ID, so a caller reusing a label
    // for another company cannot pick up the previous gateway's queue.
    this.options = { ...options, enrollmentId: `${url.origin}:${options.credential.split('.')[0]}:${options.enrollmentId}` };
    this.base = url.origin;
  }
  private async request(path: string, body: unknown): Promise<Record<string, unknown>> {
    if (this.stopped) throw new Error("Gateway session has stopped.");
    const controller = new AbortController();
    this.requests.add(controller);
    const timer = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await (this.options.fetch ?? fetch)(`${this.base}/api/v1${path}`, {
        method: "POST", headers: { Authorization: `Bearer ${this.options.credential}`, "Content-Type": "application/json" },
        body: JSON.stringify(body), redirect: "error", signal: controller.signal,
      });
      const result = await response.json().catch(() => ({})) as Record<string, unknown>;
      if (!response.ok) throw new GatewayError(response.status, typeof result.detail === "string" ? result.detail : `Upload failed (${response.status}).`);
      return result;
    } finally { clearTimeout(timer); this.requests.delete(controller); }
  }
  async registerSource(descriptor: SourceDescriptor): Promise<string> {
    const result = await this.request("/gateway/sources", descriptor);
    const id = (result.source as { id?: unknown } | undefined)?.id;
    if (typeof id !== "string" || !/^[a-f0-9]{64}$/.test(id)) throw new Error("Invalid source registration response.");
    this.sourceIds.add(id);
    return id;
  }
  async capture(sourceId: string, measurement: Measurement): Promise<void> {
    if (this.stopped) return;
    if (!this.sourceIds.has(sourceId)) throw new Error("Register the source in this session before collecting measurements.");
    if (!Number.isFinite(measurement.value) || !Number.isFinite(Date.parse(measurement.measured_at))) throw new Error("Invalid measurement.");
    const id = this.options.newId();
    if (!/^[A-Za-z0-9_-]{8,80}$/.test(id)) throw new Error("Generate a stable UUID or equivalent observation ID.");
    await this.options.queue.append(this.options.enrollmentId, { ...measurement, source_id: sourceId, id });
  }
  flush(): Promise<number> {
    if (!this.pendingFlush) this.pendingFlush = this.flushBatch().finally(() => { this.pendingFlush = undefined; });
    return this.pendingFlush;
  }
  private async flushBatch(): Promise<number> {
    const rows = await this.options.queue.peek(this.options.enrollmentId, 60);
    if (!rows.length) return 0;
    const payload: ObservationBatch = { schema_version: 2, observations: rows };
    const result = await this.request("/observations", payload);
    if (!Number.isInteger(result.accepted) || !Number.isInteger(result.duplicates) ||
        Number(result.accepted) < 0 || Number(result.duplicates) < 0 || Number(result.accepted) + Number(result.duplicates) !== rows.length) {
      throw new Error("Invalid upload receipt; queued readings have been retained.");
    }
    await this.options.queue.acknowledge(this.options.enrollmentId, rows.map(row => row.id));
    return rows.length;
  }
}
