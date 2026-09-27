"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { Activity, ArrowRight, Check, CheckCheck, ChevronDown, CircleAlert, Clock3, FileCheck2, FileText, GitBranch, LoaderCircle, Search, ShieldCheck, Sparkles, UserRound, X } from "lucide-react";
import type { Snapshot, SubTask, Worker } from "@/lib/types";
import type { useDashboard } from "@/lib/use-dashboard";
import "./incident-case.css";

const stages = [
  { title: "Find the cause", purpose: "AI drafts · a person reviews", ids: ["gather", "diagnose"], Icon: Search },
  { title: "Approve the plan", purpose: "A person makes the decision", ids: ["decide"], Icon: ShieldCheck },
  { title: "Check & report", purpose: "AI checks sample recovery data", ids: ["verify", "document"], Icon: FileCheck2 },
];
const stepLabels: Record<string, string> = {
  gather: "Collect evidence", diagnose: "Review diagnosis", decide: "Approve recovery plan",
  verify: "Check sample telemetry", document: "Write incident report",
};

function personFor(task: SubTask, state: Snapshot) {
  return state.workers.find(worker => worker.id === task.assignment.worker_id);
}
function assignee(task: SubTask, state: Snapshot) {
  const person = personFor(task, state)?.name ?? task.assignment.label;
  const ai = task.execution?.provider === "local_fallback" ? "Local fallback" : "Gemini";
  return task.assignment.kind === "AI" ? ai : task.assignment.kind === "HUMAN_AI" ? `${ai} + ${person}` : task.assignment.kind === "DELAY" ? "Waiting for an eligible owner" : person;
}
function familiar(label: string) {
  return label.replace(/AI Agent/g, "Gemini").replace(/\bAI\b/g, "Gemini");
}
function capacity(worker: Worker) {
  if (!worker.availability) return "Unavailable";
  if (worker.cognitive_state.confidence < .25) return "Low input quality";
  if (worker.cognitive_state.readiness < 40 || worker.cognitive_state.cognitive_load > 82) return "Limited · estimate";
  return "Available · estimate";
}
function routeContext(task: SubTask, state: Snapshot) {
  const person = personFor(task, state);
  if (task.assignment.kind === "DELAY") return "No person meets the example’s skill and experimental routing rules yet.";
  if (task.assignment.kind === "AI") return "AI handles the evidence work. People retain the diagnosis review and recovery decision.";
  if (!person) return "The assigned person retains responsibility for review.";
  if (task.id === "decide") return `${person.name} has the architecture expertise needed to judge the recovery risk.`;
  if (task.assignment.kind === "HUMAN_AI") return `${task.execution?.provider === "local_fallback" ? "Local fallback" : "Gemini"} prepares the evidence; ${person.name} reviews it using their backend expertise.`;
  return `${person.name} is assigned to review the diagnosis under this example’s skill and routing rules.`;
}
function stepStatus(task: SubTask) {
  if (task.status === "delayed") return "Waiting for an eligible owner";
  if (task.execution?.status === "failed") return "Output unavailable";
  if (task.status === "completed") return ({ gather: "Evidence ready", diagnose: "Reviewed", decide: "Approved", verify: "Checks complete", document: "Report ready" } as Record<string, string>)[task.id] ?? "Complete";
  if (task.execution?.status === "running") return "AI working";
  if (task.id === "diagnose" && task.execution?.status === "completed") return "Your review needed";
  if (task.id === "decide" && task.status === "active") return "Your approval needed";
  return task.status === "active" ? "Preparing" : "Next";
}
function excerpt(text: string) {
  const plain = text.split(/\n\nHuman review recorded/)[0].replace(/^#{1,6}\s+/gm, "").replace(/\*\*|`/g, "").replace(/\[([^\]]+)\]\([^)]*\)/g, "$1").replace(/\s+/g, " ").trim();
  return plain.length > 330 ? `${plain.slice(0, 327).trimEnd()}…` : plain;
}
function InlineText({ text }: { text: string }) {
  return <>{text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, index) => part.startsWith("**") && part.endsWith("**") ? <strong key={index}>{part.slice(2, -2)}</strong> : part.startsWith("`") && part.endsWith("`") ? <code key={index}>{part.slice(1, -1)}</code> : part)}</>;
}
function ModelResult({ text }: { text: string }) {
  return <div className="ic-result-text" data-testid="evidence-result">{text.split("\n").map((line, index) => /^#{1,6}\s/.test(line) ? <h3 key={index}><InlineText text={line.replace(/^#{1,6}\s*/, "")} /></h3> : /^\s*[-*]\s/.test(line) ? <div className="ic-result-bullet" key={index}><span aria-hidden="true">•</span><p><InlineText text={line.replace(/^\s*[-*]\s*/, "")} /></p></div> : line.trim() ? <p key={index}><InlineText text={line} /></p> : <div className="ic-result-break" key={index} />)}</div>;
}
function OutputDialog({ task, state, close }: { task: SubTask; state: Snapshot; close: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    ref.current?.querySelector<HTMLButtonElement>("button")?.focus();
    return () => { document.body.style.overflow = overflow; previous?.focus(); };
  }, []);
  const execution = task.execution;
  const provenance = execution?.provider === "local_fallback" ? "Local fallback · not a Gemini result" : execution?.provider === "human" ? "Recorded user approval" : execution?.status === "completed" ? "Generated by Gemini" : execution?.status === "running" ? "Gemini request in progress" : "No output yet";
  return <div className="ic-dialog-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) close(); }}>
    <div className="ic-dialog" ref={ref} role="dialog" aria-modal="true" aria-labelledby="ic-dialog-title" data-testid="output-dialog" onKeyDown={event => {
      if (event.key === "Escape") close();
      if (event.key === "Tab") {
        const items = ref.current?.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], summary, [tabindex="0"]');
        if (!items?.length) return;
        if (event.shiftKey && document.activeElement === items[0]) { event.preventDefault(); items[items.length - 1].focus(); }
        if (!event.shiftKey && document.activeElement === items[items.length - 1]) { event.preventDefault(); items[0].focus(); }
      }
    }}>
      <header className="ic-dialog-heading"><div><span className="ic-kicker">INCIDENT EVIDENCE</span><h2 id="ic-dialog-title">{stepLabels[task.id] ?? task.title}</h2></div><button className="ic-icon-button" aria-label="Close analysis" onClick={close}><X size={20} /></button></header>
      <div className="ic-output-meta"><span><UserRound size={14} />{assignee(task, state)}</span><span className={execution?.provider === "local_fallback" ? "ic-warning-text" : ""}>{execution?.status === "running" ? <LoaderCircle size={14} className="ic-spin" /> : <FileText size={14} />}{provenance}</span></div>
      {execution?.error && <p className="ic-inline-warning">{execution.error}</p>}
      {task.output ? <ModelResult text={task.output} /> : <div className="ic-output-empty"><Clock3 size={24} /><p>{task.id === "decide" ? "Approval has not been recorded. Review the diagnosis, then approve the recovery plan." : execution?.status === "running" ? "The analysis will appear when the current request completes." : "This step is waiting for its dependencies or an eligible owner."}</p></div>}
      <details className="ic-provenance"><summary>Assignment & execution details<ChevronDown size={14} /></summary><p>{routeContext(task, state)}</p><dl><div><dt>Routing</dt><dd>{task.assignment.provider === "jev" ? "Jev · validated against local eligibility rules" : "Local weighted router"}</dd></div><div><dt>Execution</dt><dd>{provenance}</dd></div>{execution?.model && <div><dt>Model</dt><dd>{execution.model}</dd></div>}{execution?.latency_ms != null && <div><dt>Request time</dt><dd>{(execution.latency_ms / 1000).toFixed(1)} seconds</dd></div>}</dl><p className="ic-policy-note">Assignment context describes local work policy, not the model’s internal reasoning.</p></details>
      <footer className="ic-dialog-foot">Sample incident evidence. No production system is changed.</footer>
    </div>
  </div>;
}

function Stage({ index, state, open }: { index: number; state: Snapshot; open: (id: string) => void }) {
  const stage = stages[index];
  const tasks = stage.ids.map(id => state.workflow?.subtasks.find(task => task.id === id));
  const done = tasks.every(task => task?.status === "completed");
  const active = tasks.some(task => task?.status === "active" || task?.status === "delayed");
  const Icon = stage.Icon;
  return <section className={`ic-stage ${done ? "is-complete" : active ? "is-current" : ""}`} aria-label={stage.title}>
    <header><span className="ic-stage-number">{done ? <Check size={14} /> : index + 1}</span><div><h2>{stage.title}</h2><p>{stage.purpose}</p></div><Icon className="ic-stage-icon" size={19} /></header>
    <div className="ic-stage-steps">{stage.ids.map((id, row) => {
      const task = tasks[row];
      return <div className="ic-step" key={id}>
        <div className="ic-step-heading"><span>{stepLabels[id]}</span>{task?.status === "completed" && <Check size={13} />}</div>
        {task ? <><div className="ic-step-owner">{task.assignment.kind === "AI" || task.assignment.kind === "HUMAN_AI" ? <Sparkles size={13} /> : <UserRound size={13} />}<strong>{assignee(task, state)}</strong></div><button data-testid={`workflow-step-${id}`} className={`ic-step-output ${task.execution?.provider === "local_fallback" ? "is-fallback" : ""}`} onClick={() => open(id)}>{task.execution?.status === "running" ? <LoaderCircle size={12} className="ic-spin" /> : null}<span>{stepStatus(task)}{task.execution?.provider === "local_fallback" ? " · fallback" : ""}</span><ArrowRight size={12} /></button></> : <p className="ic-step-preview">{id === "decide" ? "Qualified human approval" : id === "diagnose" ? "Human review of AI evidence" : "AI evidence work"}</p>}
      </div>;
    })}</div>
  </section>;
}

export default function IncidentStory({ dashboard }: { dashboard: ReturnType<typeof useDashboard> }) {
  const { state, connection, error, pending, control, clearError } = dashboard;
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const work = state?.workflow;
  const diagnosis = work?.subtasks.find(task => task.id === "diagnose");
  const decision = work?.subtasks.find(task => task.id === "decide");
  const working = work?.subtasks.find(task => task.execution?.status === "running");
  const current = work?.subtasks.find(task => task.status === "active" || task.status === "delayed");
  const failed = work?.subtasks.find(task => task.execution?.status === "failed");
  const finished = work?.status === "resolved";
  const review = diagnosis?.status === "active" && diagnosis.execution?.status === "completed";
  const approval = decision?.status === "active";
  const evaluating = /evaluating/i.test(state?.provider.status ?? "");
  const disabled = pending || connection === "offline" || evaluating;
  const selected = work?.subtasks.find(task => task.id === selectedId);
  const artifact = finished ? work?.subtasks.find(task => task.id === "document") : diagnosis?.output ? diagnosis : undefined;
  const changed = diagnosis?.assignment.previous_label ? diagnosis : undefined;
  const reviewer = diagnosis && state ? personFor(diagnosis, state)?.name ?? "the assigned reviewer" : "the assigned reviewer";
  const decider = decision && state ? personFor(decision, state)?.name ?? "the assigned owner" : "the assigned owner";
  const completedSteps = work?.subtasks.filter(task => task.status === "completed").length ?? 0;
  const totalSteps = work?.subtasks.length ?? 5;

  let actionTitle = "Let AI prepare the investigation";
  let actionDescription = "Start the sample case. AI gathers evidence and a team member reviews the diagnosis.";
  let action: ReactNode = <button data-testid="start-incident" className="ic-primary" disabled={!state || pending || connection === "offline"} onClick={() => void control({ action: "trigger_incident" })}>{pending ? <LoaderCircle size={16} className="ic-spin" /> : <Search size={16} />}Start investigation<ArrowRight size={16} /></button>;
  if (finished) {
    actionTitle = "Case complete";
    actionDescription = "The reviewed plan has been checked against sample recovery data. The incident report is ready.";
    action = <button className="ic-primary" onClick={() => setSelectedId("document")}><FileText size={16} />Read incident report<ArrowRight size={16} /></button>;
  } else if (approval) {
    actionTitle = "Approve the recovery plan";
    actionDescription = `${decider} owns this decision. Read the diagnosis before approving sample recovery checks.`;
    action = <button data-testid="approve-decision" className="ic-primary" disabled={disabled} onClick={() => void control({ action: "approve_decision" })}>{pending ? <LoaderCircle size={16} className="ic-spin" /> : <ShieldCheck size={16} />}Approve recovery plan</button>;
  } else if (review) {
    actionTitle = "The diagnosis needs a human review";
    actionDescription = `${reviewer} is the assigned reviewer. Read the analysis, then confirm the diagnosis.`;
    action = <button data-testid="complete-diagnosis" className="ic-primary" disabled={disabled} onClick={() => void control({ action: "complete_diagnosis" })}>{pending ? <LoaderCircle size={16} className="ic-spin" /> : <Check size={16} />}Confirm diagnosis<ArrowRight size={16} /></button>;
  } else if (work) {
    actionTitle = failed ? "Analysis needs attention" : evaluating ? "Finding an eligible reviewer" : working?.id === "gather" ? "Gemini is collecting evidence" : working?.id === "diagnose" ? "Gemini is drafting the diagnosis" : working?.id === "verify" ? "Checking sample recovery data" : working?.id === "document" ? "Writing the incident report" : current?.status === "delayed" ? "Waiting for an eligible owner" : "Preparing the next step";
    actionDescription = failed ? "Open the step details to see what happened." : evaluating ? "The example checks skills, availability, and experimental signal estimates." : current?.status === "delayed" ? "No person meets the example’s routing rules. The assignment updates as the demo plays." : working?.id === "verify" || working?.id === "document" ? "Your approval is recorded. The result will appear when the AI request completes." : "You will review the diagnosis before anyone approves a recovery plan.";
    action = failed || current?.status === "delayed" ? <button className="ic-secondary" onClick={() => setSelectedId((failed ?? current)?.id ?? null)}>View assignment<ArrowRight size={15} /></button> : <span className="ic-running"><LoaderCircle size={17} className="ic-spin" />{evaluating ? "Routing in progress" : "Work in progress"}</span>;
  }

  return <div className="incident-case">
    <header className="ic-heading"><div><span className="ic-example-badge"><Sparkles size={12} />Example workflow</span><h1>Incident response</h1><p>See how team signals could support an AI-assisted response.</p></div>{finished && <button className="ic-text-button" data-testid="start-incident" disabled={pending || connection === "offline"} onClick={() => { setSelectedId(null); void control({ action: "trigger_incident" }); }}>Start another case<ArrowRight size={14} /></button>}</header>
    <section className="ic-scenario" aria-label="Example scenario">
      <div className="ic-scenario-problem"><span className="ic-scenario-icon"><CircleAlert size={21} /></span><div><span className="ic-kicker">WHAT HAPPENED</span><h2>Checkout is slow</h2><p>Requests time out after a deployment.</p></div></div>
      <div className="ic-scenario-input"><Activity size={18} /><div><span className="ic-kicker">INPUT</span><strong>Sample logs + team signals</strong><span>Experimental routing estimates</span></div></div>
      <div className="ic-scenario-outcome"><FileCheck2 size={18} /><div><span className="ic-kicker">GOAL</span><strong>A reviewed recovery plan</strong><span>Every decision stays with a person</span></div></div>
    </section>
    {error && <div className="ic-notice" role="alert"><span>{error}</span><button className="ic-icon-button" aria-label="Dismiss error" onClick={clearError}><X size={17} /></button></div>}
    {connection === "offline" && <div className="ic-notice" role="status">Connection lost. Showing the last received state; reconnecting automatically.</div>}
    {!state ? <div className="ic-loading"><LoaderCircle className="ic-spin" size={23} /><span>Loading the example…</span></div> : <>
      <section className={`ic-next-action ${finished ? "is-complete" : approval || review ? "needs-review" : ""}`} aria-label="Current action" data-testid="incident-current-action">
        <div className="ic-action-main"><span className="ic-action-icon">{finished ? <CheckCheck size={23} /> : approval ? <ShieldCheck size={23} /> : review ? <UserRound size={23} /> : <Search size={23} />}</span><div><span className="ic-kicker">{finished ? "OUTCOME" : !work ? "START HERE" : approval || review ? "YOUR NEXT ACTION" : "HAPPENING NOW"}</span><h2>{actionTitle}</h2><p>{actionDescription}</p></div><div className="ic-action-control">{action}{evaluating && (approval || review) && <small>Updating the assignment…</small>}</div></div>
        {artifact?.output && <div className="ic-artifact-preview"><div><span className="ic-artifact-label">{artifact.execution?.provider === "local_fallback" ? <><Clock3 size={13} />Local fallback output</> : <><Sparkles size={13} />{finished ? "Incident report" : "Diagnosis draft"} · Gemini</>}</span><p>{excerpt(artifact.output)}</p></div><button className="ic-text-button" onClick={() => setSelectedId(artifact.id)}>{finished ? "Read full report" : "Read full analysis"}<ArrowRight size={14} /></button></div>}
        {!work && <div className="ic-capacity-preview"><span>Demo team</span>{state.workers.map(worker => <span key={worker.id}><UserRound size={12} /><strong>{worker.name}</strong>{capacity(worker)}</span>)}<small>Estimates are not validated measures of capacity.</small></div>}
        {work && current && !finished && <div className="ic-owner-context"><UserRound size={14} /><span>{routeContext(approval && decision ? decision : diagnosis?.status === "active" ? diagnosis : current, state)}</span></div>}
      </section>
      {changed && <div className="ic-route-change" data-testid="capacity-change"><GitBranch size={16} /><span>Diagnosis review reassigned: <strong>{familiar(changed.assignment.previous_label ?? "")}</strong><ArrowRight size={13} /><strong>{assignee(changed, state)}</strong></span><small>Collected evidence is kept.</small></div>}
      <div className="ic-workflow-heading"><h2>The response, step by step</h2><span>{work ? `${completedSteps} of ${totalSteps} steps complete` : "Starts when you’re ready"}</span></div>
      <div className="ic-stages" aria-label="Incident response stages">{stages.map((stage, index) => <Stage key={stage.title} index={index} state={state} open={setSelectedId} />)}</div>
      <details className="ic-how-it-works"><summary><span><Sparkles size={15} />What do Jev and Gemini do here?</span><ChevronDown size={15} /></summary><div className="ic-service-roles"><div><GitBranch size={18} /><strong>Jev · choose a reviewer</strong><p>Matches the sample task to eligible people. Local rules check every assignment.</p><span>{state.provider.active === "jev" ? "Jev routing active" : "Local routing active"}</span></div><div><Sparkles size={18} /><strong>Gemini · prepare evidence</strong><p>Drafts the diagnosis, checks sample recovery data, and writes a report.</p><span>{state.ai?.configured || state.provider.google_configured ? "Gemini configured" : "Local fallback available"}</span></div><div><ShieldCheck size={18} /><strong>People · review & approve</strong><p>A person confirms the diagnosis and approves the recovery plan.</p><span>Human approval required</span></div></div><p className="ic-method-note">Signal-based routing is experimental. This example does not establish an employee’s capacity or fitness for work. Each output shows whether it came from Gemini or a local fallback.</p></details>
      <footer className="ic-footer"><span><ShieldCheck size={13} />Sample scenario · no production changes</span><span>Signal estimates are experimental.</span></footer>
    </>}
    {selected && state && <OutputDialog task={selected} state={state} close={() => setSelectedId(null)} />}
  </div>;
}
