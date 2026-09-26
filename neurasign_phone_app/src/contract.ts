/** The server owns the metric catalog, unit conversion and interpretation. */
export type Capability = {
  metric: string;
  unit: string;
  delivery_mode: "stream" | "sync";
  measurement_kind: "sample" | "window" | "summary";
  method: string;
  timestamp_basis?: "device" | "phone_receipt" | "source_record";
  interval_seconds?: number | null;
  availability?: "available" | "unsupported" | "permission_required";
};

export type SourceDescriptor = {
  client_source_id: string;
  name: string;
  adapter: { id: string; version: string };
  transport: "ble" | "vendor_sdk" | "health_store" | "cloud_api" | "recording";
  manufacturer?: string | null;
  model?: string | null;
  firmware?: string | null;
  capabilities: Capability[];
};

export type Measurement = {
  metric: string;
  value: number;
  unit: string;
  measured_at: string;
  source_record_id?: string | null;
};

export type Observation = Measurement & { id: string; source_id: string };
export type ObservationBatch = { schema_version: 2; observations: Observation[] };

export type Candidate = { id: string; name: string; services: string[] };
export type ConnectedSource = {
  descriptor: SourceDescriptor;
  measurements: AsyncIterable<Measurement>;
  close(): Promise<void>;
};

export interface WearableAdapter {
  readonly id: string;
  supports(candidate: Candidate): boolean;
  connect(candidate: Candidate, signal: AbortSignal): Promise<ConnectedSource>;
}

/** The native shell supplies discovery; adapters match capabilities, not names. */
export class AdapterRegistry {
  private adapters = new Map<string, WearableAdapter>();
  register(adapter: WearableAdapter): void {
    if (this.adapters.has(adapter.id)) throw new Error(`Duplicate adapter: ${adapter.id}`);
    this.adapters.set(adapter.id, adapter);
  }
  matching(candidate: Candidate): WearableAdapter[] {
    return [...this.adapters.values()].filter(adapter => adapter.supports(candidate));
  }
}
