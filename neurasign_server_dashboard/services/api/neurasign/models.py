"""Team physiology summaries, derived capacity, and explainable incident work."""

from typing import Literal
from pydantic import BaseModel, Field


class CognitiveState(BaseModel):
    """Personal-baseline-relative heuristic indices, never clinical percentages."""

    cognitive_load: float = Field(30, ge=0, le=100)
    readiness: float = Field(82, ge=0, le=100)
    fatigue: float = Field(20, ge=0, le=100)
    interruption_cost: float = Field(20, ge=0, le=100)
    confidence: float = Field(0.8, ge=0, le=1)
    trend: Literal["up", "down", "stable"] = "stable"


class Worker(BaseModel):
    id: str
    name: str
    role: str
    skills: dict[str, float]
    current_task: str
    current_task_priority: float
    time_on_task: float
    availability: bool = True
    cognitive_state: CognitiveState = Field(default_factory=CognitiveState)
    history: list[float] = Field(default_factory=list)


class AIAgent(BaseModel):
    id: str = "incident-assistant"
    name: str = "AI Agent"
    capabilities: dict[str, float] = Field(default_factory=lambda: {
        "log_analysis": .95, "backend": .70, "documentation": .98,
        "verification": .95, "architecture": .25,
    })
    available: bool = True


class RoutingExplanation(BaseModel):
    summary: str
    factors: list[str]


class Assignment(BaseModel):
    kind: Literal["HUMAN", "AI", "HUMAN_AI", "DELAY"]
    worker_id: str | None = None
    label: str
    score: float
    confidence: float
    explanation: RoutingExplanation
    previous_label: str | None = None
    changed_at: str | None = None
    provider: Literal["jev", "deterministic"] = "deterministic"


class RoutingDecision(BaseModel):
    subtask_id: str
    assignment: Assignment
    considered_candidates: int


class StepExecution(BaseModel):
    provider: Literal["gemini", "human", "local_fallback"] | None = None
    status: Literal["idle", "running", "completed", "failed"] = "idle"
    model: str | None = None
    error: str | None = None
    latency_ms: int | None = None


class SubTask(BaseModel):
    id: str
    title: str
    description: str
    required_skills: dict[str, float]
    complexity: float
    risk: float
    urgency: float
    human_judgment_requirement: float
    ai_suitability: float
    estimated_duration: float
    dependencies: list[str] = Field(default_factory=list)
    status: Literal["pending", "active", "completed", "delayed"] = "pending"
    assignment: Assignment | None = None
    output: str | None = None
    execution: StepExecution = Field(default_factory=StepExecution)


class WorkItem(BaseModel):
    id: str
    title: str
    description: str
    urgency: float
    risk: float
    complexity: float
    required_skills: dict[str, float]
    estimated_duration: float
    human_judgment_requirement: float
    status: Literal["active", "resolved"] = "active"
    revision: int = 1
    subtasks: list[SubTask]


class Event(BaseModel):
    id: str
    timestamp: str
    type: Literal["info", "state", "routing", "reroute", "success"]
    title: str
    description: str
    worker_id: str | None = None
    from_label: str | None = None
    to_label: str | None = None


class MonitoringFeatures(BaseModel):
    heart_rate: float | None = None
    hrv: float | None = None
    eda: float | None = None
    temperature: float | None = None
    movement: float | None = None


class MonitoringPoint(MonitoringFeatures):
    time: float
    cognitive_load: float
    readiness: float
    fatigue: float


class MonitoringWorker(BaseModel):
    worker_id: str
    quality: float = Field(ge=0, le=1)
    status: Literal["recorded", "synthetic", "live", "manual", "waiting", "stale"]
    last_sample_at: str | None = None
    last_sample_seconds: float | None = None
    features: MonitoringFeatures = Field(default_factory=MonitoringFeatures)
    reference: MonitoringFeatures = Field(default_factory=MonitoringFeatures)
    reference_status: str
    recording: dict[str, str] | None = None
    history: list[MonitoringPoint] = Field(default_factory=list)
