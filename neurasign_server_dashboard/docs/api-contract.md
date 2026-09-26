> This is the legacy local demo contract. Production mobile clients must use the [authenticated company API](company-workspace.md). Legacy endpoints are disabled in production.

# NEURASIGN API contract

Python entry point: `services/api/neurasign/main.py`; package imports use `PYTHONPATH=services/api`. The API listens on port 8000. Next.js uses `NEXT_PUBLIC_API_URL`, defaulting to `http://localhost:8000`, and subscribes to `/ws`.

## Endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /api/state` | Current team-monitoring and workflow snapshot |
| `GET /api/health` | Service health |
| `POST /api/control` | Workflow, playback, mode, and provider controls |
| `PATCH /api/workers/{id}/state` | Partial manual state update; switches to Manual |
| `POST /api/live/readings` | Private gateway feature ingestion; switches to Live |
| `GET /api/research` | Optional private source/feature/baseline inspection |
| `WS /ws` | Initial and subsequent `{type:"snapshot",data:Snapshot}` messages |

Ordinary snapshots intentionally include selected physiological summary features, reference means, timestamped history, and inferred cognitive state. They exclude full raw sensor waveforms, detailed research diagnostics, and provider credentials. Research requires `RESEARCH_ENABLED=true` plus loopback access or the configured `X-Research-Token`.

## Control requests

```ts
{
  action?: "play" | "pause" | "restart" | "reset" | "run_demo"
         | "trigger_incident" | "advance" | "stress_aoi"
         | "complete_diagnosis" | "approve_decision";
  speed?: 1 | 5 | 10 | 30;
  mode?: "replay" | "manual" | "live";
  provider?: "deterministic" | "jev";
  seconds?: number; // advance only: default 10, greater than 0, at most 180
}
```

Mutations return a snapshot. Remote routing and AI execution may still be pending; the client continues receiving WebSocket updates and must use actual returned state rather than assuming a command completed a model call.

| Action | Behavior |
| --- | --- |
| `run_demo` | Starts the guided sample incident immediately with synthetic signal replay at 30×; configured Jev/Gemini remain enabled |
| `trigger_incident` | Introduces the secondary incident example, preserving the monitoring source and playback choice |
| `stress_aoi` | Applies the explicit low-capacity Sam scenario and invokes the same routing provider; it does not directly overwrite the assignment |
| `complete_diagnosis` | Records the user's diagnosis review after its artifact is ready and the task is active; unlocks the critical decision |
| `approve_decision` | Records explicit approval only when the critical decision is active; unlocks verification |
| `restart` / `reset` | Resets the workspace, invalidates older background jobs, and reloads the preferred recording |
| `advance` | Advances the signal/workflow clock; does not invent remote results or bypass human review |

Incident controls start work, change the example capacity state, record diagnosis review, and approve the recovery plan. Human gates do not complete on a timer. The guided workflow therefore has no fixed wall-clock completion time. `pause` pauses monitoring playback; running and subsequent eligible AI jobs can finish independently. Starting, reviewing, approving, or resolving an ordinary example preserves that playback choice.

The English incident interface maps **Start investigation** to `trigger_incident`, **Confirm diagnosis** to `complete_diagnosis`, and **Approve recovery plan** to `approve_decision`. `run_demo` and `stress_aoi` remain developer API controls and are not exposed in that simplified tab. Provider selection and optional research inspection also remain available through their API/configuration surfaces.

Manual state patches accept any nonempty subset of `{cognitive_load,readiness,fatigue,interruption_cost}`, each finite and 0–100. Worker IDs are `alex` and `aoi`.

## Snapshot

```ts
type Snapshot = {
  revision: number;
  mode: "replay" | "manual" | "live";
  playing: boolean;
  speed: number;
  elapsed_seconds: number;
  duration_seconds: number;
  demo_running: boolean;
  demo_stage: string;
  waiting_for_human: boolean;
  source: {
    name: string;
    kind: "fixture" | "universe" | "manual" | "live";
    description: string;
  };
  provider: {
    selected: string;
    active: string;
    status: string;
    jev_configured: boolean;
    google_configured: boolean;
  };
  ai: {
    configured: boolean;
    provider: "gemini";
    model: string;
    status: string;
    completed_calls: number;
    fallback_calls: number;
  };
  monitoring: Monitoring;
  workers: Worker[];
  workflow: WorkItem | null;
  events: Event[];
  metrics: {reroutes: number; protected_minutes: number; ai_steps: number};
  research_enabled: boolean;
};
```

The configured provider is not proof of a successful call. `provider.active` identifies overall routing activity, each `assignment.provider` records that route's provenance, and each task's `execution` identifies its artifact's provenance. `waiting_for_human` indicates the critical approval gate; a diagnosis draft also requires review when its task remains active with a completed execution. Events are newest-first and use actual UTC wall-clock timestamps. In-process reset preserves increasing snapshot revisions so clients can discard older responses; AI call counters apply to the current incident.

```ts
type CognitiveState = {
  cognitive_load: number; readiness: number; fatigue: number;
  interruption_cost: number; confidence: number;
  trend: "up" | "down" | "stable";
};
type Worker = {
  id: "alex" | "aoi"; name: string; role: string;
  skills: Record<string, number>; current_task: string;
  current_task_priority: number; time_on_task: number;
  availability: boolean;
  cognitive_state: CognitiveState; history: number[];
};
type Assignment = {
  kind: "HUMAN" | "AI" | "HUMAN_AI" | "DELAY";
  worker_id: string | null; label: string;
  score: number; confidence: number;
  explanation: {summary: string; factors: string[]};
  previous_label: string | null; changed_at: string | null;
  provider: "jev" | "deterministic";
};
type StepExecution = {
  provider: "gemini" | "human" | "local_fallback" | null;
  status: "idle" | "running" | "completed" | "failed";
  model: string | null; error: string | null; latency_ms: number | null;
};
type SubTask = {
  id: string; title: string; description: string;
  required_skills: Record<string, number>;
  complexity: number; risk: number; urgency: number;
  human_judgment_requirement: number; ai_suitability: number;
  estimated_duration: number; dependencies: string[];
  status: "pending" | "active" | "completed" | "delayed";
  assignment: Assignment | null;
  output: string | null;
  execution: StepExecution;
};
type WorkItem = {
  id: string; title: string; description: string;
  urgency: number; risk: number; complexity: number;
  required_skills: Record<string, number>; estimated_duration: number;
  human_judgment_requirement: number;
  status: "active" | "resolved"; revision: number; subtasks: SubTask[];
};
type Event = {
  id: string; timestamp: string;
  type: "info" | "state" | "routing" | "reroute" | "success";
  title: string; description: string;
  worker_id?: string; from_label?: string; to_label?: string;
};
```

`execution.status="completed"` means an artifact or human action completed; it does not always mean the task completed. In particular, a completed Gemini diagnosis artifact leaves the diagnosis task active until `complete_diagnosis`. `local_fallback` identifies locally generated example output, never a successful Gemini result. Error fields contain safe status summaries without credentials or raw provider requests.

## Monitoring

```ts
type PhysiologicalFeatures = {
  heart_rate: number | null;
  hrv: number | null;
  eda: number | null;
  temperature: number | null;
  movement: number | null;
};
type MonitoringPoint = PhysiologicalFeatures & {
  time: number;
  cognitive_load: number;
  readiness: number;
  fatigue: number;
};
type MonitoringWorker = {
  worker_id: "alex" | "aoi";
  quality: number;
  status: "recorded" | "synthetic" | "live" | "manual" | "waiting" | "stale";
  last_sample_at: string | null;
  last_sample_seconds: number | null;
  features: PhysiologicalFeatures;
  reference: PhysiologicalFeatures;
  reference_status: string;
  recording: {participant?: string; session?: string; sensor?: string} | null;
  history: MonitoringPoint[];
};
type Monitoring = {
  source_kind: "universe" | "fixture" | "manual" | "live";
  source_name: string;
  description: string;
  feature_method: string;
  inference_method: string;
  signal_seconds: number; // engine replay cursor; not a Live device timestamp
  window_seconds: number;
  units: {heart_rate: "bpm"; hrv: "ms"; eda: "µS"; temperature: "°C"; movement: "g"};
  workers: MonitoringWorker[];
};
```

Physical feature definitions are mean heart rate, pulse-derived RMSSD variability, mean EDA conductance, skin temperature, and standard deviation of acceleration magnitude. Values are not percentages and are not raw PPG/ECG waveforms. `reference` contains individual reference means, with provenance in `reference_status`; it is not a clinical normal range.

For Replay, `features` is the most recent direct source row and `history` includes only actual rows at or before the cursor, capped at 90 per worker. Recorded UNIVERSE rows summarize 60 seconds and arrive every 10 source seconds. Both `time` and `last_sample_seconds` use relative recording time; `last_sample_at` is null because no live sample timestamp is asserted. Missing measurements remain null, including the known Sam HRV gap at source second 420.

For Live, history contains received feature readings; current `features` are trailing ten-second means. `time` and `last_sample_seconds` are Unix seconds, and `last_sample_at` is UTC ISO time. After 15 seconds without fresh readings, status becomes `stale`, quality becomes zero, and current features become null; earlier history remains. For Manual, current physiological features/reference are null and history is empty.

History's cognitive indices are recomputed using the existing inference heuristic and current staged work context. Replay inference smooths three overlapping source windows; the physical history preserves each original row. These inferred trajectories are not recorded mental-state labels. The older untimestamped `Worker.history` contains readiness values only and must not be used as a physical-signal time axis.

An ordinary reset starts Replay at the earlier of source second 120 or the recording end, with playback on at 10×. The developer `run_demo` API action instead starts its synthetic fixture at zero and 30×. Source status and history must be updated together rather than drawing an invented line between unrelated sources.

## Replay schema

The preferred file is `data/universe/replay.json`; the fallback is `data/fixtures/replay.json`.

```json
{
  "metadata": {
    "kind": "fixture",
    "name": "Synthetic scenario replay",
    "description": "Illustrative signals, not recorded participant measurements",
    "window_seconds": 10
  },
  "baselines": {
    "alex": {"heart_rate": {"mean": 72, "std": 8}},
    "aoi": {"heart_rate": {"mean": 67, "std": 8}}
  },
  "windows": [
    {"worker_id": "alex", "timestamp": 0, "features": {"heart_rate": 72}, "quality": 0.9}
  ]
}
```

This abbreviated illustration omits required baseline entries for `hrv`, `eda`, `temperature`, and `movement`, and the second worker's windows. Full files require baselines and windows for both workers. Missing measured features can be omitted with reduced quality; baseline entries remain required.

The deterministic fixture covers 0–1,800 source seconds. Sam's rising load and Alex's recovery are synthetic trajectories, not UNIVERSE observations. At 30×, the same signal change arrives sooner than in ordinary 10× replay; workflow completion still depends on actual provider responses and human actions. Ordinary replay stops at the last common worker window, with displayed duration adjusted for speed. See [dataset processing](dataset.md) for units, real recordings, and provenance.

## Live readings

```json
{
  "worker_id": "alex",
  "timestamp": "2026-09-20T12:00:00Z",
  "ppg": {"heart_rate": 72, "hrv": 44},
  "eda": {"tonic": 2.1},
  "movement": {"magnitude": 0.1},
  "temperature": 33,
  "quality": 0.9
}
```

Replace the example timestamp with the current UTC time. Units are bpm, RMSSD milliseconds, EDA microsiemens, acceleration-magnitude standard deviation in g, and temperature °C. At least one finite feature is required. Readings must increase strictly per worker and fall within the accepted freshness interval. The source aggregates a trailing temporal window and uses its own provisional reference; it never borrows a recorded participant's baseline. See the README for exact live validation and confidence rules.

## Provider boundaries

`JevRoutingProvider.choose_assignment(subtask, workers, candidates)` returns an eligible candidate or `None`. The deterministic policy supplies candidate eligibility and fallback behavior. Jev receives allow-listed derived work context; raw features and baselines stay private.

The Gemini executor receives sample incident evidence and prior artifacts. It produces text for gather, diagnosis support, verification, and documentation. Provider credentials use the existing `JEV_API_key` and `Google_AI_API_key` variables on the server. Neither provider can bypass human approval or execute a production change.
