export type Mode = "replay" | "manual" | "live";
export type StateField = "cognitive_load" | "readiness" | "fatigue" | "interruption_cost";
export type CognitiveState = Record<StateField, number> & {
  confidence: number;
  trend: "up" | "down" | "stable";
};
export type Worker = {
  id: string; name: string; role: string; skills: Record<string, number>;
  current_task: string; current_task_priority: number; time_on_task: number;
  availability: boolean; cognitive_state: CognitiveState; history: number[];
};
export type SubTask = {
  id: string; title: string; description: string; required_skills: Record<string, number>;
  complexity: number; risk: number; urgency: number; human_judgment_requirement: number;
  ai_suitability: number; estimated_duration: number; dependencies: string[];
  status: "pending" | "active" | "completed" | "delayed";
  assignment: {
    provider?: "jev" | "deterministic";
    kind: "HUMAN" | "AI" | "HUMAN_AI" | "DELAY";
    worker_id: string | null; label: string; score: number; confidence: number;
    explanation: { summary: string; factors: string[] };
    previous_label: string | null; changed_at: string | null;
  };
  output: string | null;
  execution?: {
    provider: "gemini" | "human" | "local_fallback" | null;
    status: "idle" | "running" | "completed" | "failed";
    model: string | null;
    error: string | null;
    latency_ms: number | null;
  };
};
export type WorkItem = {
  id: string; title: string; description: string; urgency: number | string; risk: number | string;
  complexity: number | string; required_skills: Record<string, number>; estimated_duration: number;
  human_judgment_requirement: number; status: "active" | "resolved"; revision: number; subtasks: SubTask[];
};
export type TimelineEvent = {
  id: string; timestamp: string; type: "info" | "state" | "routing" | "reroute" | "success";
  title: string; description: string; worker_id?: string; from_label?: string; to_label?: string;
};
export type PhysiologicalFeature = "heart_rate" | "hrv" | "eda" | "temperature" | "movement";
export type PhysiologicalValues = Record<PhysiologicalFeature, number | null>;
export type MonitoringPoint = PhysiologicalValues & { time: number; cognitive_load: number; readiness: number; fatigue: number };
export type MonitoringWorker = {
  worker_id: string; quality: number; status: "recorded" | "synthetic" | "live" | "manual" | "waiting" | "stale";
  last_sample_at: string | null; features: PhysiologicalValues; reference: PhysiologicalValues;
  last_sample_seconds?: number | null;
  recording?: { participant?: string; session?: string; sensor?: string } | null;
  reference_status?: string; history: MonitoringPoint[];
};
export type Monitoring = {
  source_kind: "universe" | "fixture" | "manual" | "live";
  signal_seconds: number; window_seconds: number; workers: MonitoringWorker[];
  source_name?: string; source_description?: string;
  feature_method?: string; inference_method?: string;
};
export type Snapshot = {
  revision: number; mode: Mode; playing: boolean; speed: number; elapsed_seconds: number;
  duration_seconds: number; demo_running: boolean; demo_stage: string;
  source: { name: string; kind: "fixture" | "universe" | "manual" | "live"; description: string };
  provider: { selected: string; active: string; status: string; jev_configured: boolean; google_configured: boolean };
  workers: Worker[]; workflow: WorkItem | null; events: TimelineEvent[];
  metrics: { reroutes: number; protected_minutes: number; ai_steps: number }; research_enabled: boolean;
  monitoring?: Monitoring;
  ai?: {
    configured: boolean; provider: "gemini"; model: string; status: string;
    completed_calls: number; fallback_calls: number;
  };
};
export type Control = {
  action?: "play" | "pause" | "restart" | "run_demo" | "trigger_incident" | "advance" | "reset" | "stress_aoi" | "complete_diagnosis" | "approve_decision";
  speed?: number; mode?: Mode; provider?: "deterministic" | "jev";
};
