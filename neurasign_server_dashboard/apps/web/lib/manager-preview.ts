import type { MonitoringWorker, Snapshot } from "./types";

export type ManagerStatus = "review" | "no_flag" | "unavailable";
export type ManagerIndices = { workload: number; readiness: number; fatigue: number };
export type ManagerPerson = {
  id: string;
  name: string;
  role: string;
  status: ManagerStatus;
  summary: string;
  reason: string;
  sourceLabel: string;
  updatedLabel: string;
  indices: ManagerIndices | null;
  history: Array<ManagerIndices & { time: number }>;
};
export type ManagerView = {
  sourceLabel: string;
  sourceKind: "recorded" | "illustrative" | "manual" | "live";
  connection: "connected" | "polling" | "connecting" | "offline";
  people: ManagerPerson[];
};

const validIndex = (value: number) => Number.isFinite(value) && value >= 0 && value <= 100;
const sessionTime = (seconds: number) => `${Math.floor(seconds / 60).toString().padStart(2, "0")}:${Math.floor(seconds % 60).toString().padStart(2, "0")}`;

function unavailableReason(signal: MonitoringWorker | undefined, connection: ManagerView["connection"], manual: boolean, nowSeconds: number) {
  if (connection === "offline" || connection === "connecting") return "The service is disconnected or reconnecting. A current interpretation is unavailable.";
  if (manual) return null;
  if (!signal || signal.status === "waiting") return "Waiting for enough signal data to form an experimental interpretation.";
  if (signal.status === "stale") return "The source has stopped sending recent data. The last estimate is not shown as current.";
  if (signal.status === "live") {
    const last = signal.last_sample_seconds ?? (signal.last_sample_at ? Date.parse(signal.last_sample_at) / 1000 : NaN);
    if (!Number.isFinite(last) || nowSeconds - last > 60 || last - nowSeconds > 60) return "A recent device reading is unavailable. No current interpretation is shown.";
    if (!signal.reference_status || /provisional|not_personally_calibrated/i.test(signal.reference_status)) return "A personal reference is not established for this device. Interpretation is unavailable.";
  }
  return null;
}

/**
 * Demo presentation projection, NOT an authorization boundary.
 * Copies explicitly allowed interpretation fields; never spreads a worker or signal.
 * The enclosing demo still receives the full snapshot. A real manager API must
 * apply its own permitted-field contract and deny access to raw measurements.
 */
export function toManagerView(snapshot: Snapshot | null, connection: ManagerView["connection"], nowSeconds = Date.now() / 1000): ManagerView | null {
  if (!snapshot) return null;
  const manual = snapshot.mode === "manual";
  const sourceKind: ManagerView["sourceKind"] = manual ? "manual" : snapshot.mode === "live" ? "live" : snapshot.source.kind === "universe" ? "recorded" : "illustrative";
  const sourceLabel = sourceKind === "recorded" ? "UNIVERSE replay · experimental estimates" : sourceKind === "manual" ? "Manual scenario · values set by the presenter" : sourceKind === "live" ? "Device input · experimental estimates" : "Illustrative signals · experimental estimates";
  return {
    sourceKind,
    sourceLabel,
    connection,
    people: snapshot.workers.map(worker => {
      const signal = snapshot.monitoring?.workers.find(item => item.worker_id === worker.id);
      const state = worker.cognitive_state;
      const indices: ManagerIndices = { workload: state.cognitive_load, readiness: state.readiness, fatigue: state.fatigue };
      let unavailable = unavailableReason(signal, connection, manual, nowSeconds);
      if (!unavailable && !Object.values(indices).every(validIndex)) unavailable = "The interpretation is incomplete. No current estimate is shown.";
      if (!unavailable && !manual && (!Number.isFinite(state.confidence) || state.confidence < .25)) unavailable = "Signal support is too limited to show an experimental interpretation.";
      const flags = [
        indices.fatigue >= 60 ? "Fatigue estimate reaches the demo review threshold." : "",
        indices.workload >= 70 ? "Workload estimate reaches the demo review threshold." : "",
        indices.readiness < 45 ? "Readiness estimate is below the demo review threshold." : "",
      ].filter(Boolean);
      const history = !unavailable && !manual ? (signal?.history ?? []).filter(point => Number.isFinite(point.time) && [point.cognitive_load, point.readiness, point.fatigue].every(validIndex)).map(point => ({ time: point.time, workload: point.cognitive_load, readiness: point.readiness, fatigue: point.fatigue })) : [];
      const lastTime = signal?.history.at(-1)?.time;
      const updatedLabel = manual ? "Presenter-set values" : sourceKind === "live" ? signal?.last_sample_at ? `Last input ${new Date(signal.last_sample_at).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}` : "Awaiting device input" : lastTime != null && Number.isFinite(lastTime) ? `Recording position ${sessionTime(lastTime)}` : "No recent window";
      return {
        id: worker.id,
        name: worker.name,
        role: worker.role,
        status: unavailable ? "unavailable" : flags.length ? "review" : "no_flag",
        summary: unavailable ? "Interpretation unavailable" : flags.length ? "Check-in suggested by the demo rules." : "Within the demo review thresholds.",
        reason: unavailable ?? (flags.length ? flags.join(" ") : "The current experimental indices do not trigger a review. This is not a confirmation of fitness for duty."),
        sourceLabel,
        updatedLabel,
        indices: unavailable ? null : indices,
        history,
      };
    }),
  };
}
