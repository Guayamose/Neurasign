"""Behavior-level checks for inference boundaries, guardrails and the full demo."""

import asyncio
from datetime import datetime, timedelta, timezone
import json
from time import monotonic

import pytest

from neurasign.inference import InferenceEngine, normalize
from neurasign.models import CognitiveState
from neurasign.orchestration import WorkflowOrchestrator, incident, team
from neurasign.routing import DeterministicRoutingProvider, RoutingEngine
from neurasign.signals import DEFAULT_BASELINES, LiveWearableSource, SignalWindow, UniverseReplaySource


class FakeGemini:
    configured = True
    status = "Test model ready"
    model = "test-gemini"
    completed_calls = 0
    fallback_calls = 0

    async def execute_step(self, step, context):
        await asyncio.sleep(0)
        self.completed_calls += 1
        return {"text": f"Mock model artifact for {step['id']}; supplied sample incident evidence.", "provider": "gemini", "model": self.model, "latency_ms": 1, "error": None}


@pytest.fixture(autouse=True)
def isolate_external_services(monkeypatch):
    monkeypatch.setenv("ROUTING_PROVIDER", "deterministic")
    monkeypatch.setattr("neurasign.gemini.GeminiExecutor", FakeGemini)


async def settle(engine):
    """Drain actual background-job dependencies, without advancing fake time."""
    for _ in range(10):
        jobs = [job for job in [*engine.jobs.values(), engine.routing_job] if job and not job.done()]
        if not jobs:
            return
        await asyncio.gather(*jobs)
    raise AssertionError("Background work did not settle")


def test_normalization_is_personal_and_missing_features_are_neutral():
    alex = DEFAULT_BASELINES["alex"]
    aoi = DEFAULT_BASELINES["aoi"]
    features = {name: stats["mean"] for name, stats in alex.items()}
    assert normalize(features, alex)["heart_rate"] == 0
    assert normalize(features, aoi)["heart_rate"] == -.5
    assert normalize({}, alex) == {name: 0 for name in alex}
    assert normalize({"heart_rate": 9999}, alex)["heart_rate"] == 4


def test_state_response_and_confidence_are_bounded_and_monotonic():
    worker = team()[1]
    baseline = DEFAULT_BASELINES[worker.id]
    normal = {name: stats["mean"] for name, stats in baseline.items()}
    elevated = {name: stats["mean"]+stats["std"]*(-3 if name == "hrv" else 3) for name, stats in baseline.items()}
    inference = InferenceEngine()
    low = inference.infer(SignalWindow(worker.id, 0, normal, .9), baseline, worker)
    worker.cognitive_state = low
    high = inference.infer(SignalWindow(worker.id, 10, elevated, .9), baseline, worker)
    assert high.cognitive_load > low.cognitive_load
    assert high.readiness < low.readiness
    assert high.fatigue > low.fatigue
    assert high.trend == "down"
    assert 0 <= high.readiness <= 100
    incomplete = inference.infer(SignalWindow(worker.id, 20, {"heart_rate": 74}, .9), baseline, worker)
    assert incomplete.confidence < low.confidence


def test_live_uses_temporal_window_and_confidence_warmup_then_expiry():
    source = LiveWearableSource(window_seconds=10)
    start = datetime.now(timezone.utc)-timedelta(seconds=25)
    for index, value in enumerate((60, 80)):
        source.ingest({"worker_id": "aoi", "timestamp": (start+timedelta(seconds=index)).isoformat(), "ppg": {"heart_rate": value}, "quality": 1})
    window = source.get_next_window()[0]
    assert window.features["heart_rate"] == 70
    assert window.sample_count == 2
    assert 0 < window.quality < .1  # only 1 second of temporal coverage
    source.ingest({"worker_id": "aoi", "timestamp": (start+timedelta(seconds=20)).isoformat(), "ppg": {"heart_rate": 90}})
    assert source.get_next_window()[0].features["heart_rate"] == 90
    source.last_received["aoi"] = monotonic()-61
    assert source.get_next_window()[0].quality == 0


def test_live_rejects_duplicate_out_of_order_and_stale_timestamps():
    source = LiveWearableSource()
    now = datetime.now(timezone.utc)
    payload = {"worker_id": "aoi", "timestamp": now.isoformat(), "ppg": {"heart_rate": 75}}
    source.ingest(payload)
    for timestamp in (now, now-timedelta(seconds=1), now-timedelta(days=1), now+timedelta(minutes=1)):
        with pytest.raises(ValueError):
            source.ingest({**payload, "timestamp": timestamp.isoformat()})
    assert source.get_next_window()[0].quality == 0


def test_live_high_coverage_requires_time_span_and_keeps_provisional_discount():
    now = datetime.now(timezone.utc)
    fast, covered = LiveWearableSource(), LiveWearableSource()
    for index in range(5):
        for source, spacing in ((fast, .01), (covered, 2)):
            source.ingest({"worker_id": "aoi", "timestamp": (now-timedelta(seconds=9-index*spacing)).isoformat(), "ppg": {"heart_rate": 75}, "quality": 1})
    assert fast.get_next_window()[0].quality < .01
    assert covered.get_next_window()[0].quality == .6


@pytest.mark.asyncio
async def test_live_reference_is_independent_of_preceding_replay_source():
    real, fixture = WorkflowOrchestrator(), WorkflowOrchestrator()
    await fixture.run_demo()
    payload = {"worker_id": "aoi", "timestamp": datetime.now(timezone.utc).isoformat(), "ppg": {"heart_rate": 75, "hrv": 60}, "eda": {"tonic": 1.8}, "temperature": 33, "movement": {"magnitude": .1}}
    for engine in (real, fixture):
        await engine.ingest_live(payload)
    assert real.workers[1].cognitive_state.model_dump(exclude={"trend"}) == fixture.workers[1].cognitive_state.model_dump(exclude={"trend"})
    assert real.research()["workers"]["aoi"]["baseline"] == DEFAULT_BASELINES["aoi"]
    assert "provisional" in real.research()["baseline_status"]


def test_malformed_import_falls_back_to_labeled_fixture(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"windows": [{"worker_id": "alex"}, {"worker_id": "aoi"}], "baselines": {"alex": {}, "aoi": {}}}))
    replay = UniverseReplaySource(path=path)
    assert replay.metadata["kind"] == "fixture"
    assert len(replay.get_next_window(0)) == 2


def test_router_retains_human_judgment_and_supports_delay():
    router = DeterministicRoutingProvider()
    workers = team()
    tasks = incident().subtasks
    assert router.choose(tasks[0], workers).assignment.kind == "AI"
    decision = router.choose(tasks[2], workers).assignment
    assert decision.kind == "HUMAN"
    assert decision.worker_id == "alex"
    assert all(candidate.kind not in ("AI", "HUMAN_AI") for candidate in router.candidates(tasks[2], workers))
    for worker in workers:
        worker.availability = False
    assert router.choose(tasks[2], workers).assignment.kind == "DELAY"
    assert all(candidate.worker_id is None for candidate in router.candidates(tasks[1], workers))


def test_skills_cannot_be_compensated_by_high_readiness():
    router = DeterministicRoutingProvider()
    workers = team()
    workers[0].availability = False
    workers[1].cognitive_state = CognitiveState(readiness=100, cognitive_load=0, fatigue=0, interruption_cost=0)
    assert router.choose(incident().subtasks[2], workers).assignment.kind == "DELAY"


def test_ai_capabilities_are_hard_constraints():
    router = DeterministicRoutingProvider()
    task = incident().subtasks[0]
    task.required_skills = {"specialist_unknown_domain": .9}
    assert router.choose(task, team()).assignment.kind == "DELAY"


def test_ready_humans_are_protected_from_automatable_routine_work():
    router = DeterministicRoutingProvider()
    workers = team()
    for worker in workers:
        worker.cognitive_state = CognitiveState(cognitive_load=0, readiness=100, fatigue=0, interruption_cost=0, confidence=1)
        worker.skills = {key: 1 for key in worker.skills}
        worker.current_task_priority = 0
    tasks = incident().subtasks
    assert all(router.choose(tasks[index], workers).assignment.kind == "AI" for index in (0, 3, 4))
    assert router.choose(tasks[2], workers).assignment.kind == "HUMAN"


def test_uncertain_retained_indices_cannot_authorize_human_assignment():
    router = DeterministicRoutingProvider()
    workers = team()
    for worker in workers:
        worker.cognitive_state.confidence = .1
    decision = router.choose(incident().subtasks[2], workers).assignment
    assert decision.kind == "DELAY"
    assert "reliable" in decision.explanation.summary
    assert router.choose(incident().subtasks[0], workers).assignment.kind == "AI"


@pytest.mark.asyncio
async def test_confidence_loss_triggers_reconsideration_without_score_change():
    engine = WorkflowOrchestrator()
    await engine.run_demo()
    await engine.tick(6)
    assert engine.workflow.subtasks[2].assignment.kind == "HUMAN"
    engine.workers[0].cognitive_state.confidence = .1
    await engine.reconsider()
    assert engine.workflow.subtasks[2].assignment.kind == "DELAY"
    assert engine.workflow.subtasks[2].status == "delayed"


@pytest.mark.asyncio
async def test_ordinary_replay_stops_when_recording_ends():
    engine = WorkflowOrchestrator()
    engine.speed = 30
    engine.playing = True
    await engine.tick(180)
    assert not engine.playing
    assert engine.signal_seconds == engine.replay.duration_seconds
    assert engine.snapshot()["elapsed_seconds"] == engine.snapshot()["duration_seconds"]


@pytest.mark.asyncio
async def test_manual_change_immediately_reroutes_and_preserves_completed_work():
    engine = WorkflowOrchestrator()
    await engine.run_demo()
    await settle(engine)
    await engine.tick(2)
    gather, diagnosis = engine.workflow.subtasks[:2]
    assert gather.status == "completed"
    output = gather.output
    assignment = gather.assignment.model_dump()
    assert diagnosis.assignment.worker_id == "aoi"
    progress = engine.step_progress["diagnose"]
    await engine.set_manual("aoi", {"readiness": 22, "cognitive_load": 92, "fatigue": 70, "interruption_cost": 80})
    assert engine.mode == "manual"
    assert diagnosis.assignment.kind == "HUMAN_AI"
    assert diagnosis.assignment.worker_id == "alex"
    assert diagnosis.assignment.previous_label == "Sam"
    assert gather.status == "completed"
    assert gather.output == output
    assert gather.assignment.model_dump() == assignment
    assert engine.step_progress["diagnose"] == progress
    assert engine.events[-1].type == "reroute"


@pytest.mark.asyncio
async def test_complete_guided_demo_requires_real_job_results_and_two_human_actions():
    results = []
    for _ in range(2):
        engine = WorkflowOrchestrator()
        engine.router.selected = "jev"
        await engine.run_demo()
        assert engine.router.selected == "deterministic"
        assert engine.snapshot()["source"]["kind"] == "fixture"
        assert [s.assignment.label for s in engine.workflow.subtasks] == ["AI Agent", "Sam", "Alex", "AI Agent", "AI Agent"]
        await settle(engine)
        assert engine.workflow.subtasks[1].execution.status == "completed"
        assert engine.workflow.subtasks[1].status == "active"
        await engine.tick(30)
        assert engine.workflow.subtasks[0].status == "completed"
        assert engine.workflow.subtasks[1].assignment.label == "Alex"
        assert engine.workflow.subtasks[2].status == "pending"
        with pytest.raises(ValueError):
            await engine.approve_decision()
        await engine.complete_diagnosis()
        before = engine.elapsed_seconds
        await engine.tick(180)
        assert engine.elapsed_seconds == before
        assert engine.workflow.subtasks[2].status == "active"
        assert engine.workflow.subtasks[3].execution.status == "idle"
        await engine.approve_decision()
        await settle(engine)
        assert engine.workflow.status == "resolved"
        assert not engine.playing and not engine.demo_running
        assert all(s.status == "completed" and s.output for s in engine.workflow.subtasks)
        assert engine.metrics == {"reroutes": 1, "protected_minutes": 6, "ai_steps": 4}
        assert engine.snapshot()["ai"]["completed_calls"] == 4
        assert engine.workflow.subtasks[2].execution.provider == "human"
        completions = [e.title for e in engine.events if e.type == "success"]
        assert completions[-1] == "Incident workflow complete"
        assert [e.title for e in engine.events if e.type == "reroute"] == ["Initial diagnosis reassigned"]
        results.append(([s.assignment.label for s in engine.workflow.subtasks], engine.metrics, completions))
    assert results[0] == results[1]


@pytest.mark.asyncio
async def test_slow_ai_leaves_state_responsive_and_reset_rejects_late_result():
    started, release = asyncio.Event(), asyncio.Event()
    class Slow(FakeGemini):
        async def execute_step(self, step, context):
            started.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                await release.wait()  # emulate a third-party client ignoring cancellation
            return await super().execute_step(step, context)
    engine = WorkflowOrchestrator(ai_executor=Slow())
    await asyncio.wait_for(engine.run_demo(), timeout=.2)
    await started.wait()
    job = engine.jobs["gather"]
    async with asyncio.timeout(.2):
        async with engine.lock:
            assert engine.snapshot()["workflow"]["subtasks"][0]["execution"]["status"] == "running"
            engine.reset()
    release.set()
    await job
    assert engine.workflow is None
    assert engine.snapshot()["ai"]["completed_calls"] == 0
    assert not any("output ready" in event.title for event in engine.events)


@pytest.mark.asyncio
async def test_pause_only_pauses_signals_and_model_outputs_still_arrive():
    release = asyncio.Event()
    class Slow(FakeGemini):
        async def execute_step(self, step, context):
            await release.wait()
            return await super().execute_step(step, context)
    engine = WorkflowOrchestrator(ai_executor=Slow())
    await engine.run_demo()
    engine.playing = False
    release.set()
    await settle(engine)
    assert engine.elapsed_seconds == 0
    assert engine.workflow.subtasks[0].status == "completed"
    assert engine.workflow.subtasks[1].execution.status == "completed"
    assert engine.workflow.subtasks[1].status == "active"


@pytest.mark.asyncio
async def test_jev_runs_outside_state_lock_and_records_per_assignment_provenance(monkeypatch):
    release = asyncio.Event()
    class SlowJev:
        configured = True
        status = "Test Jev pending"
        async def choose_assignment(self, subtask, workers, candidates):
            await release.wait()
            return candidates[0]
    monkeypatch.setenv("ROUTING_PROVIDER", "jev")
    engine = WorkflowOrchestrator()
    engine.router.jev = SlowJev()
    await asyncio.wait_for(engine.run_demo(), .2)
    assert engine.routing_pending
    async with asyncio.timeout(.2):
        async with engine.lock:
            assert engine.snapshot()["provider"]["selected"] == "jev"
    release.set()
    await settle(engine)
    assert engine.workflow.subtasks[0].assignment.provider == "jev"
    assert engine.workflow.subtasks[1].execution.status == "completed"


@pytest.mark.asyncio
async def test_continuous_stable_live_samples_do_not_cancel_pending_jev_work():
    release = asyncio.Event()
    class SlowJev:
        configured = True
        status = "Waiting on test response"
        calls = 0
        canceled = 0
        async def choose_assignment(self, subtask, workers, candidates):
            self.calls += 1
            try:
                await release.wait()
            except asyncio.CancelledError:
                self.canceled += 1
                raise
            return candidates[0]
    engine = WorkflowOrchestrator()
    now = datetime.now(timezone.utc)
    def reading(worker_id, offset):
        baseline = DEFAULT_BASELINES[worker_id]
        return {"worker_id": worker_id, "timestamp": (now+timedelta(seconds=offset)).isoformat(),
                "ppg": {"heart_rate": baseline["heart_rate"]["mean"], "hrv": baseline["hrv"]["mean"]},
                "eda": {"tonic": baseline["eda"]["mean"]}, "temperature": baseline["temperature"]["mean"],
                "movement": {"magnitude": baseline["movement"]["mean"]}}
    for index in range(5):
        for worker_id in ("alex", "aoi"):
            await engine.ingest_live(reading(worker_id, -9+index*2))
    provider = SlowJev()
    engine.router.jev = provider
    engine.router.selected = "jev"
    await engine.trigger_incident()
    for index in range(10):
        for worker_id in ("alex", "aoi"):
            await engine.ingest_live(reading(worker_id, -.9+index*.05))
        await asyncio.sleep(0)
    assert engine.routing_pending
    assert provider.calls == 5
    assert provider.canceled == 0
    release.set()
    await settle(engine)
    assert engine.workflow.subtasks[0].execution.status == "completed"
    assert engine.workflow.subtasks[0].assignment.provider == "jev"


@pytest.mark.asyncio
async def test_visible_ai_fallback_is_never_labeled_gemini():
    class Offline(FakeGemini):
        async def execute_step(self, step, context):
            return {"text": "Local fallback checklist only", "provider": "local_fallback", "model": None, "latency_ms": 3, "error": "AI unavailable"}
    engine = WorkflowOrchestrator(ai_executor=Offline())
    await engine.run_demo()
    await settle(engine)
    assert engine.workflow.subtasks[0].execution.provider == "local_fallback"
    assert engine.workflow.subtasks[0].execution.error == "AI unavailable"
    assert engine.snapshot()["ai"]["completed_calls"] == 0
    assert engine.snapshot()["ai"]["fallback_calls"] == 2


@pytest.mark.asyncio
async def test_completed_ai_artifact_survives_delay_and_unlocks_dependency_on_recovery():
    release = asyncio.Event()
    class Slow(FakeGemini):
        async def execute_step(self, step, context):
            await release.wait()
            return await super().execute_step(step, context)
    engine = WorkflowOrchestrator(ai_executor=Slow())
    await engine.run_demo()
    engine.router.deterministic.ai_agent.available = False
    for worker in engine.workers:
        worker.availability = False
    await engine.reconsider(force=True)
    assert engine.workflow.subtasks[0].status == "delayed"
    release.set()
    await settle(engine)
    gather = engine.workflow.subtasks[0]
    assert gather.execution.status == "completed" and gather.status == "delayed"
    preserved = gather.output
    engine.router.deterministic.ai_agent.available = True
    for worker in engine.workers:
        worker.availability = True
    await engine.reconsider(force=True)
    await settle(engine)
    assert gather.status == "completed" and gather.output == preserved
    assert engine.workflow.subtasks[1].execution.status == "completed"
    assert engine.snapshot()["ai"]["completed_calls"] == 2


@pytest.mark.asyncio
async def test_live_confidence_expires_while_waiting_for_approval():
    engine = WorkflowOrchestrator()
    await engine.run_demo()
    await settle(engine)
    now = datetime.now(timezone.utc)
    for index in range(5):
        for worker_id in ("alex", "aoi"):
            baseline = DEFAULT_BASELINES[worker_id]
            await engine.ingest_live({"worker_id": worker_id, "timestamp": (now-timedelta(seconds=9-index*2)).isoformat(),
                "ppg": {"heart_rate": baseline["heart_rate"]["mean"], "hrv": baseline["hrv"]["mean"]},
                "eda": {"tonic": baseline["eda"]["mean"]}, "temperature": baseline["temperature"]["mean"], "movement": {"magnitude": baseline["movement"]["mean"]}})
    await engine.complete_diagnosis()
    assert engine.waiting_for_human
    engine.live.last_received["alex"] = monotonic()-61
    engine.live.last_received["aoi"] = monotonic()-61
    await engine.tick(1)
    assert not engine.waiting_for_human
    assert engine.workflow.subtasks[2].status == "delayed"
    with pytest.raises(ValueError):
        await engine.approve_decision()


@pytest.mark.asyncio
async def test_advanced_incident_keeps_selected_recorded_source():
    engine = WorkflowOrchestrator()
    source = engine.replay
    await engine.trigger_incident()
    assert engine.replay is source
    await settle(engine)


@pytest.mark.asyncio
async def test_unsafe_state_delays_critical_work_and_recovery_resumes():
    engine = WorkflowOrchestrator()
    await engine.run_demo()
    await engine.tick(6)
    await engine.set_manual("alex", {"readiness": 10, "cognitive_load": 98})
    critical = engine.workflow.subtasks[2]
    assert critical.status == "delayed"
    assert critical.assignment.kind == "DELAY"
    await engine.set_manual("alex", {"readiness": 85, "cognitive_load": 30})
    assert critical.status == "pending"
    assert critical.assignment.kind == "HUMAN"


@pytest.mark.asyncio
async def test_external_provider_failures_fall_back_without_stopping_work():
    class Unavailable:
        async def choose_assignment(self, *args):
            raise ConnectionError("offline")
    engine = RoutingEngine()
    engine.jev = Unavailable()
    engine.selected = "jev"
    choice = await engine.choose(incident().subtasks[0], team())
    assert choice.kind == "AI"
    assert engine.active == "deterministic"


@pytest.mark.asyncio
async def test_empty_live_mode_clearly_marks_unknown_confidence():
    engine = WorkflowOrchestrator()
    await engine.set_mode("live")
    assert all(worker.cognitive_state.confidence == 0 for worker in engine.workers)
    assert "Awaiting" in engine.snapshot()["source"]["description"]


def test_snapshot_has_authorized_summaries_but_no_private_research_or_credentials():
    engine = WorkflowOrchestrator()
    previous = engine.revision
    engine.reset()
    assert engine.revision > previous
    snapshot = engine.snapshot()
    assert all("deep_work" not in worker for worker in snapshot["workers"])
    assert "heart_rate" in snapshot["monitoring"]["workers"][0]["features"]
    assert "heart_rate" not in json.dumps(snapshot["workers"])
    encoded = json.dumps(snapshot)
    for sensitive in ('"baselines"', '"normalized_features"', '"raw_signal"', "JEV_API_key", "Google_AI_API_key"):
        assert sensitive not in encoded


@pytest.mark.asyncio
async def test_ordinary_monitoring_advances_through_approval_and_pause_survives_case_actions():
    engine = WorkflowOrchestrator()
    engine.reset(fixture_only=True)
    engine.playing = False
    await engine.trigger_incident()
    assert not engine.playing
    await settle(engine)
    await engine.complete_diagnosis()
    assert engine.waiting_for_human
    engine.playing = True
    before = engine.signal_seconds
    await engine.tick(2)
    assert engine.signal_seconds > before
    engine.playing = False
    await engine.approve_decision()
    assert not engine.playing
    await settle(engine)
    assert engine.workflow.status == "resolved"
    assert not engine.playing


@pytest.mark.asyncio
async def test_normal_incident_completion_does_not_stop_monitoring_playback():
    engine = WorkflowOrchestrator()
    engine.reset(fixture_only=True)
    await engine.trigger_incident()
    await settle(engine)
    await engine.complete_diagnosis()
    await engine.approve_decision()
    await settle(engine)
    assert engine.workflow.status == "resolved"
    assert engine.playing
    before = engine.signal_seconds
    await engine.tick(1)
    assert engine.signal_seconds > before
