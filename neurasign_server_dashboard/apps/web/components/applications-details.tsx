"use client";

import { useEffect, useState, type FormEvent } from "react";
import { ArrowRight, Check, CheckCircle2, CircleHelp, ClipboardList, Clock3, HandHeart, LoaderCircle, Play, RefreshCw, Search, Settings2, UserRound } from "lucide-react";
import { actionLabels, availabilityLabels, categoryLabels, displayTime, isCasePending, isTaskPending, selectTaskCandidates, type ApplicationApi, type ApplicationsData, type ApplicationTask, type OperationalPerson, type ShiftHandover, type SupportCase, type TaskCandidates } from "@/lib/applications";
import { ApplicationDialog, InlineNotice, SavingLabel, SourceLabel, StatusLabel, WorkflowSteps } from "./applications-shared";
import type { ApplicationMutation } from "./applications-forms";

type DetailProps = { data: ApplicationsData; busy: boolean; error: string; mutate: ApplicationMutation; onClose: () => void };
const teamName = (data: ApplicationsData, id: string) => data.teams.find(team => team.id === id)?.name ?? "Team";

export function TaskDetail({ task, data, busy, error, mutate, onClose, api, base, onEditPerson }: DetailProps & { task: ApplicationTask; api: ApplicationApi; base: string; onEditPerson: (person: OperationalPerson) => void }) {
  const [candidates, setCandidates] = useState<TaskCandidates | null>(null);
  const [candidateError, setCandidateError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [chosen, setChosen] = useState("");
  const [canceling, setCanceling] = useState(false);
  const [candidateQuery, setCandidateQuery] = useState("");
  const [includeUnavailable, setIncludeUnavailable] = useState(false);
  const canManage = data.permissions.can_manage;
  const contextRevision = data.people.map(person => `${person.id}:${person.context_version}:${person.active_task_count}:${person.open_case_count}`).join("|");
  useEffect(() => {
    if (!canManage || task.status !== "open") return;
    let active = true;
    setCandidates(null); setCandidateError(""); setChosen("");
    api<TaskCandidates>(`${base}/tasks/${task.id}/candidates`).then(value => { if (active) setCandidates(value); }).catch(caught => { if (active) setCandidateError(caught instanceof Error ? caught.message : "Candidates could not be loaded."); });
    return () => { active = false; };
  }, [api, base, task.id, task.version, task.status, canManage, refresh, contextRevision]);
  const assigned = data.people.find(person => person.id === task.assignee_id);
  const selected = candidates?.candidates.find(person => person.employee_id === chosen && person.eligible);
  const filteredCandidates = selectTaskCandidates(candidates?.candidates ?? [], candidateQuery, includeUnavailable);
  const eligibleCount = candidates?.candidates.filter(person => person.eligible).length ?? 0;
  const unavailableCount = (candidates?.candidates.length ?? 0) - eligibleCount;
  const current = task.status === "completed" ? 4 : task.status === "in_progress" ? 2 : task.status === "assigned" ? 1 : 0;
  async function transition(action: "start" | "complete" | "cancel") {
    const result = await mutate(`/tasks/${task.id}/transition`, { version: task.version, action });
    if (result) setCanceling(false);
  }
  return <ApplicationDialog title={task.title} subtitle={`${teamName(data, task.team_id)} · ${task.priority.charAt(0).toUpperCase() + task.priority.slice(1)} priority`} onClose={onClose} busy={busy} wide>
    <div className="apps-detail" data-testid="apps-task-detail"><InlineNotice message={error} error /><div className="apps-detail-meta"><StatusLabel value={task.status} /><SourceLabel value={task.provenance} /></div>
      {task.status !== "canceled" && <WorkflowSteps steps={["Review candidates", "Assigned", "In progress", "Completed"]} current={current} />}
      {task.description && <details className="apps-task-notes"><summary>Task instructions</summary><p>{task.description}</p></details>}
      <dl className={`apps-facts ${task.status === "open" ? "apps-facts-open" : ""}`}><div><dt>{task.status === "open" ? "Required skills" : "Assigned to"}</dt><dd>{task.status === "open" ? task.required_skills.join(", ") || "No specific skills required" : assigned?.name ?? "Not assigned"}</dd></div><div><dt>Due</dt><dd>{displayTime(task.due_at)}</dd></div>{task.status !== "open" && <div><dt>Required skills</dt><dd>{task.required_skills.length ? task.required_skills.join(", ") : "No specific skills required"}</dd></div>}</dl>
      {isTaskPending(task) && canManage && <>
        {task.status === "assigned" && <div className="apps-next-action"><div><Play size={20} /><span><strong>Ready to begin</strong><small>{assigned?.name ?? "The assignee"} is assigned to this task.</small></span></div><button className="apps-button apps-button-primary" disabled={busy} onClick={() => void transition("start")}><SavingLabel busy={busy}>Start task<Play size={16} /></SavingLabel></button></div>}
        {task.status === "in_progress" && <div className="apps-next-action"><div><CheckCircle2 size={20} /><span><strong>Is the work finished?</strong><small>Confirm completion when the task is done.</small></span></div><button className="apps-button apps-button-primary" disabled={busy} onClick={() => void transition("complete")}><SavingLabel busy={busy}>Complete task<Check size={17} /></SavingLabel></button></div>}
        {task.status === "open" && <section className="apps-candidates" aria-labelledby="apps-candidate-title"><div className="apps-section-heading"><div><h3 id="apps-candidate-title">Choose who takes this task</h3><p>Based on recorded skills, availability and current commitments.</p></div></div>
          {candidateError ? <div className="apps-empty-compact" role="alert"><p>{candidateError}</p><button className="apps-button apps-button-secondary" onClick={() => setRefresh(value => value + 1)}><RefreshCw size={16} />Retry candidates</button></div> : !candidates ? <div className="apps-loading" role="status"><LoaderCircle className="apps-spin" size={21} />Reviewing operational inputs…</div> : !candidates.candidates.length ? <div className="apps-empty-compact"><UsersEmpty /><h4>No candidates in this team</h4><p>Add people to the team, then record their availability and skills.</p></div> : <>
            <div className="apps-candidate-tools"><label className="apps-search">Find a candidate<div><Search size={16} /><input type="search" value={candidateQuery} onChange={event => setCandidateQuery(event.target.value)} placeholder="Search name" /></div></label><div><span>{eligibleCount} eligible</span>{unavailableCount > 0 && <button className="apps-button apps-button-quiet" aria-pressed={includeUnavailable} onClick={() => setIncludeUnavailable(value => !value)}>{includeUnavailable ? "Hide unavailable" : `Review unavailable (${unavailableCount})`}</button>}</div></div>
            {!filteredCandidates.length && <div className="apps-empty-compact"><p>{candidateQuery ? "No matching candidates. Try another name." : "No eligible candidates yet. Review unavailable people and update their context, or resolve any open support cases."}</p>{!includeUnavailable && unavailableCount > 0 && <button className="apps-button apps-button-secondary" onClick={() => setIncludeUnavailable(true)}>Review unavailable people</button>}</div>}
            <fieldset className="apps-candidate-list" disabled={busy}><legend className="apps-visually-hidden">Candidate selection</legend>{filteredCandidates.map(candidate => {
              const person = data.people.find(value => value.id === candidate.employee_id);
              return <div className={`apps-candidate ${chosen === candidate.employee_id ? "is-selected" : ""} ${!candidate.eligible ? "is-ineligible" : ""}`} key={candidate.employee_id}>
                <label><input type="radio" name="candidate" value={candidate.employee_id} checked={chosen === candidate.employee_id} disabled={!candidate.eligible} onChange={() => setChosen(candidate.employee_id)} /><span className="apps-avatar" aria-hidden="true">{candidate.name.split(" ").map(part => part[0]).slice(0, 2).join("")}</span><span className="apps-candidate-person"><strong>{candidate.name}</strong><small>{candidate.active_task_count} active {candidate.active_task_count === 1 ? "task" : "tasks"}{person ? ` · ${availabilityLabels[person.availability]}` : ""}</small></span><span className={`apps-eligibility ${candidate.eligible ? "is-eligible" : ""}`}>{candidate.eligible ? <Check size={15} /> : <CircleHelp size={15} />}{candidate.eligible ? "Eligible" : "Not eligible"}</span></label>
                <div className="apps-candidate-reasons">{[...candidate.reasons, ...candidate.missing].filter((reason, index, all) => all.indexOf(reason) === index).map(reason => <p key={reason}>{reason}</p>)}<div>{person && <SourceLabel value={person.context_provenance} />}{person?.can_edit && <button type="button" data-testid={`apps-person-context-${person.id}`} className="apps-button apps-button-quiet" onClick={() => onEditPerson(person)}><Settings2 size={15} />Edit context</button>}</div></div>
              </div>;
            })}</fieldset>
            <div className="apps-confirm-assignment"><div><strong>{selected ? `Assign to ${selected.name}` : "Select an eligible person"}</strong><p>The server checks eligibility again when you confirm.</p></div><button className="apps-button apps-button-primary" data-testid="apps-confirm-assignment" disabled={!selected || busy} onClick={() => { if (selected) void mutate(`/tasks/${task.id}/assign`, { version: task.version, employee_id: selected.employee_id }); }}><SavingLabel busy={busy}>Confirm assignment<ArrowRight size={17} /></SavingLabel></button></div>
          </>}
        </section>}
        <div className="apps-secondary-action">{canceling ? <div className="apps-cancel-confirm"><p>Cancel this task? It will remain in the activity history.</p><button className="apps-button apps-button-secondary" disabled={busy} onClick={() => setCanceling(false)}>Keep task</button><button className="apps-button apps-button-danger" disabled={busy} onClick={() => void transition("cancel")}>Confirm cancellation</button></div> : <button className="apps-button apps-button-quiet" disabled={busy} onClick={() => setCanceling(true)}>Cancel task</button>}</div>
      </>}
      {!isTaskPending(task) && <div className="apps-complete-message"><CheckCircle2 size={23} /><div><strong>{task.status === "completed" ? "Work completed" : "Task canceled"}</strong><p>This task remains in the team’s history.</p></div></div>}
    </div>
  </ApplicationDialog>;
}

function UsersEmpty() { return <UserRound size={25} />; }

export function SupportCaseDetail({ item, data, busy, error, mutate, onClose }: DetailProps & { item: SupportCase }) {
  const [resolving, setResolving] = useState(false);
  const person = data.people.find(value => value.id === item.employee_id);
  const canAct = data.permissions.can_manage;
  async function recordAction(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget, values = new FormData(form);
    const result = await mutate(`/cases/${item.id}/actions`, { version: item.version, kind: String(values.get("kind")), note: String(values.get("note")).trim() });
    if (result) form.reset();
  }
  async function resolve(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const result = await mutate(`/cases/${item.id}/resolve`, { version: item.version, note: String(new FormData(event.currentTarget).get("resolution")).trim() });
    if (result) setResolving(false);
  }
  return <ApplicationDialog title={`Support · ${person?.name ?? "Employee"}`} subtitle={`${teamName(data, item.team_id)} · ${categoryLabels[item.category]}`} busy={busy} onClose={onClose} wide>
    <div className="apps-detail" data-testid="apps-case-detail"><InlineNotice message={error} error /><div className="apps-detail-meta"><StatusLabel value={item.status} /><SourceLabel value={item.provenance} /></div><WorkflowSteps steps={["Concern recorded", "Support in progress", "Resolved"]} current={item.status === "resolved" ? 3 : item.actions.length ? 1 : 0} />
      <section className="apps-concern"><HandHeart size={22} /><div><span>Reported concern</span><p>{item.summary}</p></div></section>
      <section className="apps-action-history"><h3>Follow-through</h3>{!item.actions.length ? <p className="apps-small">No action recorded yet. Agree on a next step with the person.</p> : <ol>{item.actions.map(action => <li key={action.id}><span className="apps-timeline-dot"><Check size={13} /></span><div><strong>{actionLabels[action.kind] ?? action.kind}</strong><p>{action.note}</p><small>{displayTime(action.created_at)}</small></div></li>)}</ol>}</section>
      {isCasePending(item) && canAct && <>{resolving ? <form className="apps-action-form" onSubmit={event => void resolve(event)}><h3>Confirm the outcome</h3><label>Resolution<textarea name="resolution" required minLength={3} maxLength={500} rows={3} placeholder="What was agreed, and what happens next?" autoFocus disabled={busy} /></label><div className="apps-form-footer"><button type="button" className="apps-button apps-button-secondary" disabled={busy} onClick={() => setResolving(false)}>Keep open</button><button className="apps-button apps-button-primary" disabled={busy}><SavingLabel busy={busy}>Confirm resolution<Check size={17} /></SavingLabel></button></div></form> : <>
        <form className="apps-action-form" onSubmit={event => void recordAction(event)}><h3>Record an action</h3><fieldset disabled={busy}><label>Action taken<select name="kind" defaultValue="check_in">{Object.entries(actionLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>What was agreed?<textarea name="note" required minLength={3} maxLength={500} rows={3} placeholder="e.g. Agreed a 15-minute break; Jordan is providing cover." /></label></fieldset><div className="apps-form-footer"><button className="apps-button apps-button-primary" disabled={busy}><SavingLabel busy={busy}>Record action<Check size={17} /></SavingLabel></button></div></form>
        <div className="apps-next-action"><div><CheckCircle2 size={20} /><span><strong>Ready to close this case?</strong><small>{item.actions.length ? "Confirm the agreed outcome before resolving." : "Record an action before resolving the case."}</small></span></div><button className="apps-button apps-button-secondary" disabled={busy || !item.actions.length} onClick={() => setResolving(true)}>Resolve case<ArrowRight size={16} /></button></div>
      </>}</>}
      {item.status === "resolved" && <div className="apps-complete-message"><CheckCircle2 size={23} /><div><strong>Case resolved</strong><p>{item.resolution}</p></div></div>}
    </div>
  </ApplicationDialog>;
}

export function HandoverDetail({ item, data, busy, error, mutate, onClose, actorId, actorRole }: DetailProps & { item: ShiftHandover; actorId?: string; actorRole?: string }) {
  const [canceling, setCanceling] = useState(false);
  const recipient = data.recipients.find(person => person.id === item.recipient_member_id);
  const sender = data.recipients.find(person => person.id === item.sender_member_id);
  const mayCancel = item.can_cancel ?? (data.permissions.can_manage && (actorRole === "owner" || actorId === item.sender_member_id));
  return <ApplicationDialog title={item.title} subtitle={teamName(data, item.team_id)} onClose={onClose} busy={busy} wide>
    <div className="apps-detail" data-testid="apps-handover-detail"><InlineNotice message={error} error /><div className="apps-detail-meta"><StatusLabel value={item.status} /><SourceLabel value={item.provenance} /></div>
      <div className="apps-handover-people"><div><span>From</span><strong>{sender?.name ?? "Team manager"}</strong></div><ArrowRight size={24} /><div><span>Taking over</span><strong>{recipient?.name ?? "Designated recipient"}{item.recipient_member_id === actorId && <small> (you)</small>}</strong></div></div>
      {item.note && <p className="apps-description">{item.note}</p>}
      <section className="apps-handover-work"><h3>Work included <span>{item.task_ids.length + item.case_ids.length}</span></h3><p className="apps-small">Acceptance transfers responsibility. Employee assignments and open items are preserved.</p>
        {item.task_ids.map(id => { const task = data.tasks.find(value => value.id === id); return <div className="apps-work-item" key={id}><ClipboardList size={19} /><div><strong>{task?.title ?? "Task outside current access"}</strong><small>Task{task?.assignee_id ? ` · ${data.people.find(person => person.id === task.assignee_id)?.name ?? "Assigned employee"}` : ""}</small></div>{task && <StatusLabel value={task.status} />}</div>; })}
        {item.case_ids.map(id => { const support = data.cases.find(value => value.id === id); return <div className="apps-work-item" key={id}><HandHeart size={19} /><div><strong>{support?.summary ?? "Support case outside current access"}</strong><small>Support case{support ? ` · ${data.people.find(person => person.id === support.employee_id)?.name ?? "Employee"}` : ""}</small></div>{support && <StatusLabel value={support.status} />}</div>; })}
      </section>
      {item.status === "pending" && <><div className="apps-next-action"><div><Clock3 size={22} /><span><strong>{item.can_accept ? "Your handover is ready" : `Waiting for ${recipient?.name ?? "the recipient"}`}</strong><small>{item.can_accept ? "Review the pending work, then accept responsibility." : "Only the designated recipient can accept."}</small></span></div>{item.can_accept && <button className="apps-button apps-button-primary" disabled={busy} onClick={() => void mutate(`/handovers/${item.id}/accept`, { version: item.version })}><SavingLabel busy={busy}>Accept handover<Check size={17} /></SavingLabel></button>}</div>
        {mayCancel && <div className="apps-secondary-action">{canceling ? <div className="apps-cancel-confirm"><p>Cancel this handover? The existing work and responsibility stay unchanged.</p><button className="apps-button apps-button-secondary" disabled={busy} onClick={() => setCanceling(false)}>Keep handover</button><button className="apps-button apps-button-danger" disabled={busy} onClick={() => void mutate(`/handovers/${item.id}/cancel`, { version: item.version })}>Confirm cancellation</button></div> : <button className="apps-button apps-button-quiet" disabled={busy} onClick={() => setCanceling(true)}>Cancel handover</button>}</div>}
      </>}
      {item.status === "accepted" && <div className="apps-complete-message"><CheckCircle2 size={23} /><div><strong>Accepted by {recipient?.name ?? "the recipient"}</strong><p>{displayTime(item.accepted_at)} · Pending work remains open.</p></div></div>}
    </div>
  </ApplicationDialog>;
}
