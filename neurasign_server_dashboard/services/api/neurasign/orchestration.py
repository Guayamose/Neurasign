"""Real AI execution over staged incident evidence, with explicit human approvals."""

import asyncio
from datetime import datetime, timezone
import os

from .inference import InferenceEngine, normalize
from .monitoring import monitoring_snapshot
from .models import Event, StepExecution, SubTask, Worker, WorkItem
from .routing import RoutingEngine
from .signals import DEFAULT_BASELINES, LiveWearableSource, ManualSignalSource, UniverseReplaySource


def team() -> list[Worker]:
    return [Worker(id="alex", name="Alex", role="Staff Backend Engineer", skills={"backend": .95, "architecture": .98, "security": .8, "data": .6},
                   current_task="Architecture migration", current_task_priority=.85, time_on_task=1500),
            Worker(id="aoi", name="Sam", role="Backend Engineer", skills={"backend": .78, "architecture": .5, "security": .65, "data": .85},
                   current_task="Service health review", current_task_priority=.3, time_on_task=300)]


def incident() -> WorkItem:
    return WorkItem(id="inc-042", title="Production database incident", description="Checkout latency is rising. Diagnose the connection bottleneck and propose a safe recovery.",
                    urgency=.97, risk=.9, complexity=.84, required_skills={"backend": .8, "architecture": .9}, estimated_duration=18, human_judgment_requirement=.9,
                    subtasks=[
                        SubTask(id="gather", title="Gather logs & incident history", description="Collect telemetry and correlate recent changes.", required_skills={"backend": .4}, complexity=.3, risk=.15, urgency=.98, human_judgment_requirement=.05, ai_suitability=.98, estimated_duration=3),
                        SubTask(id="diagnose", title="Initial diagnosis", description="Identify the bottleneck and prepare a bounded recovery recommendation.", required_skills={"backend": .75}, complexity=.7, risk=.65, urgency=.95, human_judgment_requirement=.7, ai_suitability=.65, estimated_duration=6, dependencies=["gather"]),
                        SubTask(id="decide", title="Critical architecture decision", description="A qualified human reviews rollback risk and approves the recovery approach.", required_skills={"backend": .8, "architecture": .9}, complexity=.95, risk=.95, urgency=.98, human_judgment_requirement=.98, ai_suitability=.15, estimated_duration=4, dependencies=["diagnose"]),
                        SubTask(id="verify", title="Verify recovery", description="Check service health against the incident success criteria.", required_skills={"backend": .4}, complexity=.35, risk=.35, urgency=.9, human_judgment_requirement=.15, ai_suitability=.95, estimated_duration=3, dependencies=["decide"]),
                        SubTask(id="document", title="Document & close incident", description="Summarize evidence, decisions, recovery and follow-up actions.", required_skills={"backend": .2}, complexity=.2, risk=.1, urgency=.6, human_judgment_requirement=.1, ai_suitability=.99, estimated_duration=2, dependencies=["verify"]),
                    ])


SAMPLE_LOGS = [{"event": "connection_pool_timeout", "count": 147}, {"event": "slow_query", "count": 23}, {"event": "replica_lag", "count": 0}]


def local_fallback_output(step_id: str) -> str:
    """A visible continuity fallback only when the configured AI service fails."""
    if step_id == "gather":
        total = sum(row["count"] for row in SAMPLE_LOGS)
        top = max(SAMPLE_LOGS, key=lambda row: row["count"])
        return f"Local fallback analysis of sample evidence: {total} error events grouped; {top['count']} are connection pool timeouts. Onset correlates with deployment v2.8.1; no replica lag."
    return {
        "diagnose": "Local fallback draft: sample evidence suggests an expanded transaction scope in v2.8.1 holds pooled connections. Review a rollback recommendation; no human review or approval has occurred yet.",
        "verify": "Local fallback check of provided after-recovery sample telemetry: latency 182 ms (target <250 ms), zero connection timeouts, supplied integrity checks passed. This is not a live production verification.",
        "document": "Local fallback incident summary of the sample scenario: retain collected evidence and explicit user approvals; add pool saturation alerts and transaction-duration regression coverage. No production changes were executed.",
    }[step_id]


class _UnavailableExecutor:
    configured = False
    status = "Gemini executor unavailable; local fallback"
    model = None
    completed_calls = 0
    fallback_calls = 0

    async def execute_step(self, step: dict, context: dict) -> dict:
        self.fallback_calls += 1
        return {"text": local_fallback_output(step["id"]), "provider": "local_fallback", "model": None,
                "latency_ms": 0, "error": "Gemini executor unavailable"}


class WorkflowOrchestrator:
    def __init__(self, ai_executor=None):
        self.inference = InferenceEngine()
        self.router = RoutingEngine()
        if ai_executor is not None:
            self.ai = ai_executor
        else:
            try:
                from .gemini import GeminiExecutor
                self.ai = GeminiExecutor()
            except ImportError:
                self.ai = _UnavailableExecutor()
        self.lock = asyncio.Lock()
        self.on_change = None
        self.jobs: dict[str, asyncio.Task] = {}
        self.routing_job = None
        self.generation = 0
        self.routing_generation = 0
        self.revision = 0
        self.reset()

    def _cancel_jobs(self):
        for job in [*self.jobs.values(), self.routing_job]:
            if job and not job.done():
                job.cancel()
        self.jobs = {}
        self.routing_job = None

    async def close(self):
        jobs = [job for job in [*self.jobs.values(), self.routing_job] if job]
        self.generation += 1
        self._cancel_jobs()
        await asyncio.gather(*jobs, return_exceptions=True)

    def reset(self, fixture_only: bool = False):
        self.generation += 1
        self.routing_generation += 1
        self._cancel_jobs()
        self.workers = team()
        self.replay = UniverseReplaySource(fixture_only=fixture_only)
        self.manual = ManualSignalSource()
        self.live = LiveWearableSource()
        self.mode = "replay"
        self.playing = True
        self.speed = 10
        self.elapsed_seconds = 0.
        self.signal_seconds = 0. if fixture_only else min(120., self.replay.duration_seconds)
        self.duration_seconds = 180
        self.demo_running = False
        self.demo_stage = "Start an incident to see the team coordinate"
        self.workflow = None
        self.events: list[Event] = []
        self.metrics = {"reroutes": 0, "protected_minutes": 0, "ai_steps": 0}
        self.ai_counts = {"completed_calls": 0, "fallback_calls": 0}
        self.step_progress = {}
        self.last_windows = {}
        self.last_announced = {}
        self.last_history_time = -10.
        self.last_routing_signature = None
        self.last_routing_states = {}
        self.routing_pending = False
        self.waiting_for_human = False
        self._event_counter = 0
        self._update_signals()
        self.add_event("info", "Team capacity ready", "Personal baselines inform relative estimates. Raw sensor inputs remain in the private inference layer.")
        self.touch()

    def touch(self):
        self.revision += 1

    def timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def add_event(self, kind: str, title: str, description: str, **extra):
        self._event_counter += 1
        self.events.append(Event(id=f"event-{self.generation}-{self._event_counter}", timestamp=self.timestamp(), type=kind, title=title, description=description, **extra))
        self.events = self.events[-100:]

    def source_description(self) -> dict:
        if self.mode == "manual":
            return {"kind": "manual", "name": "Manual scenario controls", "description": "Explicit demo settings for relative cognitive indices; no physiological measurements."}
        if self.mode == "live":
            waiting = "Awaiting device readings; existing indices are held with zero input confidence. " if not self.live.buffers else "Private feature readings aggregated over a trailing 10-second window. "
            return {"kind": "live", "name": "Live wearable gateway", "description": waiting + "Uses a provisional synthetic reference until personal device calibration. Five readings spanning eight seconds establish temporal coverage; confidence decays when readings stop."}
        return {key: self.replay.metadata.get(key, "") for key in ("kind", "name", "description")}

    def snapshot(self) -> dict:
        jev = self.router.jev
        duration = max(self.duration_seconds, self.elapsed_seconds)
        if self.mode == "replay" and not self.demo_running and self.workflow is None:
            duration = max(1, round(self.elapsed_seconds + max(0, self.replay.duration_seconds-self.signal_seconds)/self.speed, 1))
        provider_status = "Jev is evaluating eligible routes" if self.routing_pending else ((jev.status if jev else "Jev adapter unavailable") if self.router.selected == "jev" else "Deterministic routing selected")
        return {"revision": self.revision, "mode": self.mode, "playing": self.playing, "speed": self.speed,
                "elapsed_seconds": round(self.elapsed_seconds, 1), "duration_seconds": duration,
                "demo_running": self.demo_running, "demo_stage": self.demo_stage, "source": self.source_description(),
                "waiting_for_human": self.waiting_for_human,
                "provider": {"selected": self.router.selected, "active": self.router.active, "status": provider_status,
                             "jev_configured": bool(jev and jev.configured), "google_configured": bool(self.ai.configured)},
                "ai": {"configured": self.ai.configured, "provider": "gemini", "model": self.ai.model, "status": self.ai.status,
                       **self.ai_counts},
                "workers": [worker.model_dump() for worker in self.workers], "workflow": self.workflow.model_dump() if self.workflow else None,
                "monitoring": monitoring_snapshot(self),
                "events": [event.model_dump(exclude_none=True) for event in reversed(self.events)], "metrics": self.metrics.copy(),
                "research_enabled": os.getenv("RESEARCH_ENABLED", "false").lower() == "true"}

    async def _publish(self):
        if self.on_change:
            await self.on_change(self.snapshot())

    def _update_signals(self):
        source = {"replay": self.replay, "manual": self.manual, "live": self.live}[self.mode]
        for window in source.get_next_window(self.signal_seconds):
            worker = next((w for w in self.workers if w.id == window.worker_id), None)
            if worker is None:
                continue
            old_window = self.last_windows.get(worker.id)
            if self.mode != "manual" and old_window and old_window.timestamp == window.timestamp and old_window.features == window.features and old_window.sample_count == window.sample_count and old_window.quality == window.quality:
                continue
            worker.cognitive_state = self.inference.infer(window, self._baselines()[worker.id], worker)
            self.last_windows[worker.id] = window
            state = worker.cognitive_state
            old = self.last_announced.get(worker.id)
            if old and (abs(old[0]-state.readiness) >= 9 or abs(old[1]-state.cognitive_load) >= 12):
                self.add_event("state", f"{worker.name} {'needs more capacity' if state.readiness < old[0] else 'readiness recovered'}",
                               f"Readiness {old[0]:g} → {state.readiness:g}; load {old[1]:g} → {state.cognitive_load:g}. Relative estimates trigger a work review.", worker_id=worker.id)
                self.last_announced[worker.id] = (state.readiness, state.cognitive_load)
            elif old is None:
                self.last_announced[worker.id] = (state.readiness, state.cognitive_load)
        if self.elapsed_seconds-self.last_history_time >= 3:
            for worker in self.workers:
                worker.history = (worker.history + [worker.cognitive_state.readiness])[-45:]
            self.last_history_time = self.elapsed_seconds

    async def set_manual(self, worker_id: str, patch: dict):
        if self.mode != "manual":
            for worker in self.workers:
                self.manual.set_state(worker.id, worker.cognitive_state.model_dump())
        self.mode = "manual"
        worker = next(worker for worker in self.workers if worker.id == worker_id)
        state = worker.cognitive_state.model_dump()
        state.update(patch)
        self.manual.set_state(worker_id, state)
        self._update_signals()
        await self.reconsider(force=True)
        self.touch()

    async def stress_aoi(self):
        if self.mode != "manual":
            for worker in self.workers:
                self.manual.set_state(worker.id, worker.cognitive_state.model_dump())
        self.mode = "manual"
        self.manual.set_state("aoi", {"readiness": 24, "cognitive_load": 91, "fatigue": 65, "interruption_cost": 84})
        self.manual.set_state("alex", {"readiness": 82, "cognitive_load": 30, "fatigue": 20, "interruption_cost": 65})
        self._update_signals()
        self.add_event("state", "Sam capacity change introduced", "Manual presentation control reduces Sam's available capacity. The same routing policy reconsiders unfinished work.", worker_id="aoi")
        await self.reconsider(force=True)
        self.touch()

    async def set_mode(self, mode: str):
        if mode == self.mode:
            return
        if mode == "manual":
            for worker in self.workers:
                self.manual.set_state(worker.id, worker.cognitive_state.model_dump())
        if mode == "live":
            for worker in self.workers:
                worker.cognitive_state.confidence = 0
        self.mode = mode
        self.last_windows = {}
        self._update_signals()
        await self.reconsider(force=True)
        self.add_event("info", f"{mode.capitalize()} source selected", self.source_description()["description"])
        self.touch()

    async def ingest_live(self, payload: dict):
        self.live.ingest(payload)
        if self.mode != "live":
            self.last_windows = {}
            for worker in self.workers:
                worker.cognitive_state.confidence = 0
        self.mode = "live"
        self._update_signals()
        await self.reconsider()
        self.touch()

    async def trigger_incident(self):
        if self.workflow and self.workflow.status == "active":
            return
        self.generation += 1
        self._cancel_jobs()
        self.workflow = incident()
        self.ai_counts = {"completed_calls": 0, "fallback_calls": 0}
        self.step_progress = {task.id: 0 for task in self.workflow.subtasks}
        self.last_routing_signature = None
        self.demo_stage = "Incident opened · gathering evidence"
        self.add_event("info", "Production database incident", "Staged checkout incident evidence is ready. Gemini performs the analysis; human review and approval are explicit actions.")
        await self.reconsider(force=True)
        if self.demo_running:
            self.playing = True
        self.touch()

    async def run_demo(self):
        self.reset(fixture_only=True)
        default = "jev" if self.router.jev and self.router.jev.configured else "deterministic"
        self.router.selected = os.getenv("ROUTING_PROVIDER", default)
        self.demo_running = True
        self.playing = True
        self.speed = 30
        self.add_event("info", "Guided incident started", "Synthetic state replay runs at 30×. Gemini analyzes staged incident evidence; the workflow waits for your diagnosis review and decision approval.")
        await self.trigger_incident()

    async def reconsider(self, force: bool = False):
        if not self.workflow or self.workflow.status == "resolved":
            return
        signature = (self.router.selected, tuple((w.id, w.availability, w.cognitive_state.confidence >= .25) for w in self.workers))
        states = {w.id: tuple(getattr(w.cognitive_state, key) for key in ("readiness", "cognitive_load", "fatigue", "interruption_cost")) for w in self.workers}
        meaningful = any(wid not in self.last_routing_states or any(abs(a-b) >= 6 for a, b in zip(values, self.last_routing_states[wid])) for wid, values in states.items())
        if not force and signature == self.last_routing_signature and not meaningful:
            return
        self.last_routing_signature, self.last_routing_states = signature, states
        self.routing_generation += 1
        if self.routing_job and not self.routing_job.done():
            self.routing_job.cancel()
        self.routing_pending = self.router.selected == "jev"
        # Local eligibility and immediate capacity protection never wait on a network.
        for task in self.workflow.subtasks:
            if task.status != "completed":
                proposed = self.router.deterministic.choose(task, self.workers).assignment
                self._apply_assignment(task, proposed, force=force)
        if self.routing_pending:
            generation, routing_generation = self.generation, self.routing_generation
            tasks = [task.model_copy(deep=True) for task in self.workflow.subtasks if task.status != "completed"]
            workers = [worker.model_copy(deep=True) for worker in self.workers]
            self.routing_job = asyncio.create_task(self._run_routing(generation, routing_generation, tasks, workers))
        else:
            self.router.active = "deterministic"
        self._activate_ready()

    async def _run_routing(self, generation: int, routing_generation: int, tasks: list, workers: list):
        try:
            decisions = await asyncio.gather(*(self.router.choose(task, workers) for task in tasks))
        except asyncio.CancelledError:
            return
        async with self.lock:
            if generation != self.generation or routing_generation != self.routing_generation or not self.workflow or self.workflow.status == "resolved":
                return
            self.routing_pending = False
            for original, proposed in zip(tasks, decisions):
                task = next(task for task in self.workflow.subtasks if task.id == original.id)
                if task.status == "completed":
                    continue
                valid = any((candidate.kind, candidate.worker_id) == (proposed.kind, proposed.worker_id) for candidate in self.router.deterministic.candidates(task, self.workers))
                if valid:
                    self._apply_assignment(task, proposed, force=True)
            self.add_event("routing", "Jev routing evaluated" if self.router.active == "jev" else "Local routing fallback active", "Eligible assignments are ready. Human approvals remain required.")
            self._activate_ready()
            self.touch()
        await self._publish()

    def _apply_assignment(self, task, proposed, force=False):
        previous = task.assignment
        changed = previous and (previous.kind, previous.worker_id) != (proposed.kind, proposed.worker_id)
        if changed and not force:
            current = next((candidate for candidate in self.router.deterministic.candidates(task, self.workers) if (candidate.kind, candidate.worker_id) == (previous.kind, previous.worker_id)), None)
            if current and proposed.score-current.score < 7:
                return
        if changed:
            proposed.previous_label, proposed.changed_at = previous.label, self.timestamp()
            old_worker = next((w for w in self.workers if w.id == previous.worker_id), None)
            reason = (f"{old_worker.name}'s readiness is {old_worker.cognitive_state.readiness:g} and load is {old_worker.cognitive_state.cognitive_load:g}. " if old_worker else "Current routing requirements changed. ")
            proposed.explanation.summary = reason+proposed.explanation.summary
            self.metrics["reroutes"] += 1
            if previous.worker_id and previous.worker_id != proposed.worker_id:
                self.metrics["protected_minutes"] += task.estimated_duration
            self.workflow.revision += 1
            self.demo_stage = "Workflow adapted · human attention protected"
            self.add_event("reroute", f"{task.title} reassigned", reason+f"{previous.label} → {proposed.label}. Completed evidence and draft outputs are preserved.", worker_id=previous.worker_id, from_label=previous.label, to_label=proposed.label)
        elif previous:
            proposed.previous_label, proposed.changed_at = previous.previous_label, previous.changed_at
        else:
            self.add_event("routing", f"{task.title} → {proposed.label}", proposed.explanation.summary, worker_id=proposed.worker_id)
        task.assignment = proposed
        if proposed.kind == "DELAY":
            task.status = "delayed"
        elif task.status == "delayed":
            task.status = "pending"

    def _activate_ready(self):
        if not self.workflow:
            return
        self.waiting_for_human = False
        completed = {task.id for task in self.workflow.subtasks if task.status == "completed"}
        for task in self.workflow.subtasks:
            if task.status == "pending" and task.assignment and task.assignment.kind != "DELAY" and all(dep in completed for dep in task.dependencies):
                task.status = "active"
            if task.status != "active":
                continue
            if task.id not in ("diagnose", "decide") and task.execution.status == "completed":
                # A completed artifact remains useful if capacity temporarily delayed its step.
                task.status = "completed"
                completed.add(task.id)
                continue
            if task.id == "decide":
                task.execution.provider = "human"
                self.waiting_for_human = True
                self.demo_stage = "Your approval is required for the architecture decision"
            elif task.execution.status == "idle" and not self.routing_pending:
                self._start_execution(task)
            elif task.id == "diagnose" and task.execution.status == "completed":
                self.demo_stage = "Diagnosis draft ready · review it or change team capacity"
        self._check_resolved()

    def _execution_context(self) -> dict:
        # The executor owns the reviewed operational fixture and allow-lists keys.
        return {"prior_outputs": {task.id: task.output for task in self.workflow.subtasks if task.output},
                "human_approval": next((task.output for task in self.workflow.subtasks if task.id == "decide" and task.status == "completed"), None)}

    def _start_execution(self, task):
        task.execution = StepExecution(provider="gemini", status="running", model=self.ai.model)
        self.demo_stage = f"Gemini is working · {task.title.lower()}"
        self.add_event("info", f"Gemini started: {task.title}", "Sending staged incident evidence and preceding work outputs to the configured model. No wearable signals are included.")
        self.jobs[task.id] = asyncio.create_task(self._run_execution(self.generation, task.id, task.model_dump(), self._execution_context()))

    async def _run_execution(self, generation, task_id, step, context):
        try:
            result = await self.ai.execute_step(step, context)
        except asyncio.CancelledError:
            return
        except Exception:
            result = {"text": local_fallback_output(task_id), "provider": "local_fallback", "model": None, "error": "AI request failed; local fallback used", "latency_ms": 0}
        async with self.lock:
            if generation != self.generation or not self.workflow:
                return
            task = next(task for task in self.workflow.subtasks if task.id == task_id)
            if task.execution.status != "running":
                return
            task.output = result["text"]
            task.execution = StepExecution(provider=result["provider"], status="completed", model=result.get("model"), error=result.get("error"), latency_ms=result.get("latency_ms"))
            self.metrics["ai_steps"] += 1
            self.ai_counts["completed_calls" if result["provider"] == "gemini" else "fallback_calls"] += 1
            label = "Gemini" if result["provider"] == "gemini" else "Local fallback"
            self.add_event("success", f"{label} output ready: {task.title}", task.output[:350])
            if task_id != "diagnose" and task.status == "active":
                task.status = "completed"
            self._activate_ready()
            self._check_resolved()
            self.touch()
        await self._publish()

    async def complete_diagnosis(self):
        if not self.workflow:
            raise ValueError("Start an incident first")
        if self.mode == "live":
            self._update_signals()
            await self.reconsider()
        task = next(task for task in self.workflow.subtasks if task.id == "diagnose")
        if task.status != "active" or task.execution.status != "completed" or not task.output:
            raise ValueError("Diagnosis review requires a completed draft and an eligible active owner")
        if self.routing_pending:
            raise ValueError("Wait for the current routing evaluation before confirming review")
        task.status = "completed"
        task.output += f"\n\nHuman review recorded at {self.timestamp()}: the user confirmed this diagnosis for {task.assignment.label}. Architecture approval is still required."
        self.add_event("success", "Diagnosis reviewed by the user", f"Review confirmed for {task.assignment.label}; the architecture recommendation now awaits explicit approval.")
        self._activate_ready()
        self.touch()

    async def approve_decision(self):
        if not self.workflow:
            raise ValueError("Start an incident first")
        if self.mode == "live":
            self._update_signals()
            await self.reconsider()
        task = next(task for task in self.workflow.subtasks if task.id == "decide")
        if task.status != "active" or not task.assignment or task.assignment.kind != "HUMAN":
            raise ValueError("The architecture decision must be active and assigned to a qualified human")
        if self.routing_pending:
            raise ValueError("Wait for the current routing evaluation before approving")
        task.status = "completed"
        task.execution = StepExecution(provider="human", status="completed")
        task.output = f"Explicit user approval recorded at {self.timestamp()} for {task.assignment.label}'s assigned architecture decision. Approve the reviewed recovery recommendation for the staged incident. No production change was executed."
        self.waiting_for_human = False
        if self.demo_running:
            self.playing = True
        self.add_event("success", "Human approval recorded", task.output)
        self._activate_ready()
        self.touch()

    def _check_resolved(self):
        if self.workflow and self.workflow.status != "resolved" and all(task.status == "completed" for task in self.workflow.subtasks):
            self.workflow.status = "resolved"
            self.demo_stage = "Incident workflow complete · evidence, approval and report ready"
            if self.demo_running:
                self.playing = False
            self.demo_running = False
            self.waiting_for_human = False
            self.routing_pending = False
            self.add_event("success", "Incident workflow complete", "Gemini work and explicit human review/approval are complete. Recovery verification used supplied sample telemetry; no production system was changed.")

    async def tick(self, seconds: float = 1, force: bool = False):
        if not self.playing and not force:
            return
        remaining = seconds
        while remaining > 0:
            delta = min(1., remaining)
            remaining -= delta
            # Approval is a real user dependency; the presentation clock waits here.
            if self.waiting_for_human and self.demo_running:
                if self.mode == "live":
                    self._update_signals()
                    await self.reconsider()
                if self.waiting_for_human:
                    break
            self.elapsed_seconds += delta
            self.signal_seconds = min(self.replay.duration_seconds, self.signal_seconds+delta*self.speed)
            for worker in self.workers:
                worker.time_on_task += delta
            self._update_signals()
            await self.reconsider()
            for task in self.workflow.subtasks if self.workflow else []:
                if task.status == "active":
                    self.step_progress[task.id] += delta
            if self.mode == "replay" and self.signal_seconds >= self.replay.duration_seconds and not self.demo_running:
                self.playing = False
                if not self.workflow:
                    self.demo_stage = "Replay complete · restart or use manual controls"
                break
        self.touch()

    def research(self) -> dict:
        return {"source": self.source_description(), "signal_seconds": self.signal_seconds,
                "baseline_status": self.live.baseline_status if self.mode == "live" else ("manual_indices_no_sensor_inference" if self.mode == "manual" else "source_personal_reference"),
                "caveats": ["Developer-only private input inspection; not part of the manager API.",
                            "Load, readiness and fatigue are unvalidated relative heuristic indices, not clinical measurements.",
                            "Movement, environment and non-work factors can confound physiological associations.",
                            "Interruption cost incorporates staged work context. Confidence indicates input completeness and quality, not validated model accuracy."],
                "workers": {worker.id: {"window": self.last_windows[worker.id].__dict__ if worker.id in self.last_windows else None,
                                        "baseline": self._baselines()[worker.id],
                                        "normalized_features": normalize(self.last_windows[worker.id].features, self._baselines()[worker.id]) if worker.id in self.last_windows and self.last_windows[worker.id].features else {},
                                        "inference": worker.cognitive_state.model_dump()} for worker in self.workers}}

    def _baselines(self) -> dict:
        return self.live.baselines if self.mode == "live" else self.replay.baselines
