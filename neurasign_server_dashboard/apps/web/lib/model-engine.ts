export type ModelId = "stress" | "readiness" | "fatigue" | "workload";
export type FeatureCoverage = { observed: number; total: number; fraction: number };
export type ResearchModel = {
  id: ModelId;
  title: string;
  target: string;
  task: "classification" | "regression";
  dataset: string;
  time_horizon: string;
  input_summary: string;
  method: string;
  status: "ready" | "bundle_missing" | "invalid_hash" | "model_load_error";
  record_count: number;
  evidence: { metric: string; value: number; unit: string; description: string };
  evaluation_scope: string;
  limitations: string[];
};
export type ModelCatalog = { schema_version: number; scope: "anonymous_research"; models: ResearchModel[] };
export type ResearchRecord = { id: string; label: string; sequence: number; feature_coverage: FeatureCoverage };
export type ModelRecords = { model_id: ModelId; records: ResearchRecord[] };
export type ModelValue = { value: number; label: string; unit: string };
export type ModelPrediction = {
  model_id: ModelId;
  record_id: string;
  scope: "anonymous_research";
  production_enabled: false;
  prediction: ModelValue;
  reference: ModelValue;
  feature_coverage: FeatureCoverage;
  time_horizon: string;
  provenance: { dataset: string; experiment: string; artifact_sha256: string; evaluation_scope: string; fold: number | null };
  confidence: null;
};

export const modelOrder: ModelId[] = ["stress", "readiness", "fatigue", "workload"];
export const modelTitles: Record<ModelId, string> = {
  stress: "Stress condition", readiness: "Daily readiness", fatigue: "Daily fatigue", workload: "Task workload",
};
export const modelStatusLabels: Record<ResearchModel["status"], string> = {
  ready: "Bundle verified", bundle_missing: "Bundle missing", invalid_hash: "Verification failed", model_load_error: "Model unavailable",
};
export const modelInputNotes: Record<ModelId, string> = {
  stress: "Requires a complete 60-second wrist recording. A heart-rate summary alone cannot supply this model.",
  readiness: "Requires completed sleep, prior activity and physiological history. A live minute cannot supply a daily readiness estimate.",
  fatigue: "Requires a daily recording with cardiac summaries. A live minute cannot supply a daily fatigue estimate.",
  workload: "Requires summaries of a completed task and its preceding context. A live minute cannot supply a task-level workload estimate.",
};

export function evidenceLabel(evidence: ResearchModel["evidence"]) {
  const value = Number.isFinite(evidence.value) ? evidence.value.toLocaleString("en-US", { maximumFractionDigits: evidence.unit === "%" ? 1 : 2 }) : "—";
  return `${value}${evidence.unit === "%" ? "%" : evidence.unit ? ` ${evidence.unit}` : ""}`;
}

export function valueLabel(value: ModelValue, task: ResearchModel["task"]) {
  if (task === "classification") return value.label;
  return Number.isFinite(value.value) ? value.value.toLocaleString("en-US", { maximumFractionDigits: 1 }) : "—";
}

export function comparison(prediction: ModelPrediction, task: ResearchModel["task"]) {
  if (task === "classification") return prediction.prediction.value === prediction.reference.value ? "Matches this recorded reference" : "Differs from this recorded reference";
  const distance = Math.abs(prediction.prediction.value - prediction.reference.value);
  return Number.isFinite(distance) ? `${distance.toLocaleString("en-US", { maximumFractionDigits: 1 })}-point difference on this record` : "Comparison unavailable";
}

export async function modelRequest<T>(path: string, signal: AbortSignal, body?: { record_id: string }): Promise<T> {
  const response = await fetch(`/api/model-engine/${path}`, {
    method: body ? "POST" : "GET",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.any([signal, AbortSignal.timeout(60000)]),
    cache: "no-store",
  });
  if (!response.ok) {
    let message = "The model engine is unavailable. Try again.";
    try {
      const error = await response.json();
      if (typeof error.detail === "string") message = error.detail;
    } catch { /* Keep a readable error for proxy or network failures. */ }
    throw new Error(message);
  }
  return response.json();
}
