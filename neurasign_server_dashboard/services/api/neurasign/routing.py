"""Deterministic, explainable candidate scoring with hard judgment safeguards."""

import os

from .models import AIAgent, Assignment, RoutingDecision, RoutingExplanation, SubTask, Worker


class DeterministicRoutingProvider:
    def __init__(self):
        self.ai_agent = AIAgent()

    def candidates(self, task: SubTask, workers: list[Worker]) -> list[Assignment]:
        candidates = []
        ai_has_skills = all(self.ai_agent.capabilities.get(skill, 0) >= requirement*.75 for skill, requirement in task.required_skills.items())
        # Abundant human capacity is not a reason to hand them automatable chores.
        attention_cost = 24*task.ai_suitability*(1-task.human_judgment_requirement) if self.ai_agent.available and ai_has_skills else 0
        for worker in workers:
            state = worker.cognitive_state
            # Required expertise is a guardrail, not something a high state score can buy.
            if not worker.availability or state.confidence < .25 or any(worker.skills.get(skill, 0) < requirement*.75 for skill, requirement in task.required_skills.items()):
                continue
            weights = sum(task.required_skills.values()) or 1
            expertise = sum(worker.skills.get(skill, 0)*weight for skill, weight in task.required_skills.items())/weights
            base_factors = [f"Required expertise match: {round(expertise*100)} / 100",
                            f"Readiness {state.readiness:g}, relative to personal baseline",
                            f"Interruption cost {state.interruption_cost:g}; demo estimate from task priority, time on task and workload",
                            f"Task complexity {round(task.complexity*100)} and risk {round(task.risk*100)} inform the match"]
            if task.ai_suitability >= .65 and task.human_judgment_requirement <= .4:
                base_factors.append("Human attention carries a cost for repeatable work that AI can handle")
            human_score = expertise*42 + state.readiness*.42 - state.cognitive_load*.12 - state.fatigue*.10 - state.interruption_cost*.28 - worker.current_task_priority*3 - task.complexity*(1-expertise)*8 - attention_cost
            if state.readiness >= 40 and state.cognitive_load <= 82 and state.fatigue < 85:
                candidates.append(Assignment(kind="HUMAN", worker_id=worker.id, label=worker.name,
                    score=round(human_score, 2), confidence=state.confidence,
                    explanation=RoutingExplanation(summary=f"{worker.name} brings the required expertise and enough present capacity for human judgment.", factors=base_factors)))
            # High-consequence decisions retain a named human decision-maker, without AI delegation.
            if self.ai_agent.available and ai_has_skills and task.ai_suitability >= .35 and task.human_judgment_requirement < .85 and state.readiness >= 35 and state.cognitive_load <= 90 and state.fatigue < 85:
                hybrid_score = expertise*40 + state.readiness*.32 - state.cognitive_load*.08 - state.fatigue*.08 - state.interruption_cost*.13 - worker.current_task_priority*1.5 + task.ai_suitability*14 - 10 - task.complexity*(1-expertise)*6 - attention_cost
                candidates.append(Assignment(kind="HUMAN_AI", worker_id=worker.id, label=f"AI + {worker.name}",
                    score=round(hybrid_score, 2), confidence=round(state.confidence*.95, 2),
                    explanation=RoutingExplanation(summary=f"AI preprocesses the evidence; {worker.name} supplies focused human judgment with less interruption.",
                        factors=base_factors+["AI handles repetitive analysis; a human owns the interpretation"])))
        if self.ai_agent.available and ai_has_skills and task.ai_suitability >= .65 and task.human_judgment_requirement <= .4 and task.risk <= .55:
            ai_score = 45 + task.ai_suitability*40 - task.risk*20 - task.human_judgment_requirement*35 - task.complexity*6
            candidates.append(Assignment(kind="AI", label="AI Agent", score=round(ai_score, 2), confidence=.90,
                explanation=RoutingExplanation(summary="A bounded, repeatable step is suitable for AI execution and preserves human attention.",
                    factors=[f"AI suitability: {round(task.ai_suitability*100)} / 100", "Low human judgment requirement", "Human approval remains mandatory for the critical architecture decision", "Gemini processes staged incident evidence; production infrastructure is not connected"])))
        uncertain = any(worker.cognitive_state.confidence < .25 for worker in workers)
        candidates.append(Assignment(kind="DELAY", label="Wait for capacity", score=0, confidence=.9,
            explanation=RoutingExplanation(summary=("A sufficiently reliable, qualified assignment is unavailable. Await fresh calibrated input or use manual capacity controls." if uncertain else "No safe, qualified assignment is available; keep this step queued."),
                factors=["Availability, expertise and minimum input confidence are hard constraints", "Low-confidence retained indices cannot authorize a new human assignment", "Escalate rather than force a depleted worker into critical work"])))
        return sorted(candidates, key=lambda c: c.score, reverse=True)

    def choose(self, task: SubTask, workers: list[Worker]) -> RoutingDecision:
        candidates = self.candidates(task, workers)
        return RoutingDecision(subtask_id=task.id, assignment=candidates[0], considered_candidates=len(candidates))


class RoutingEngine:
    """Jev may rank only candidates that passed the same deterministic guardrails."""

    def __init__(self):
        self.deterministic = DeterministicRoutingProvider()
        try:
            from .jev import JevRoutingProvider
            self.jev = JevRoutingProvider()
        except ImportError:
            self.jev = None
        configured_default = "jev" if self.jev is not None and self.jev.configured else "deterministic"
        self.selected = os.getenv("ROUTING_PROVIDER", configured_default).lower()
        if self.selected not in ("jev", "deterministic"):
            self.selected = configured_default
        self.active = "deterministic"

    async def choose(self, task: SubTask, workers: list[Worker]) -> Assignment:
        candidates = self.deterministic.candidates(task, workers)
        self.active = "deterministic"
        if self.selected == "jev" and self.jev is not None:
            try:
                picked = await self.jev.choose_assignment(task.model_dump(exclude={"assignment", "output"}), [w.model_dump(exclude={"history"}) for w in workers], [c.model_dump() for c in candidates])
                if picked:
                    # Never accept a provider invention or an altered score/explanation.
                    original = next((c for c in candidates if c.kind == picked.get("kind") and c.worker_id == picked.get("worker_id")), None)
                    if original is not None:
                        self.active = "jev"
                        result = original.model_copy(deep=True)
                        result.provider = "jev"
                        result.confidence = min(original.confidence, float(picked.get("confidence", original.confidence)))
                        result.explanation.summary = "Jev selected this locally validated route. " + result.explanation.summary
                        result.explanation.factors.append("Jev ranks eligible options; explanation factors come from local routing policy")
                        return result
            except Exception:
                # Network/model/schema failures must not interrupt the demo.
                pass
        return candidates[0].model_copy(deep=True)
