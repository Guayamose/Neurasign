"use client";

import { useState, type FormEvent } from "react";
import { ArrowRight, Check, ClipboardList, HandHeart, Users } from "lucide-react";
import { categoryLabels, eligibleRecipients, isCasePending, isTaskPending, parseSkills, type ApplicationId, type ApplicationsData, type OperationalPerson } from "@/lib/applications";
import { ApplicationDialog, InlineNotice, SavingLabel, SourceLabel } from "./applications-shared";

export type ApplicationMutation = <T>(path: string, body: unknown, method?: string) => Promise<T | null>;
type CreateProps = { app: Exclude<ApplicationId, "hub">; data: ApplicationsData; team: string; actorId?: string; initialEmployee?: string; busy: boolean; error: string; mutate: ApplicationMutation; onClose: () => void; onCreated: (id: string) => void };
const field = (form: FormData, name: string) => String(form.get(name) ?? "").trim();

function TeamField({ data, value, onChange }: { data: ApplicationsData; value: string; onChange: (value: string) => void }) {
  return <label>Team<select name="team_id" required value={value} onChange={event => onChange(event.target.value)}><option value="" disabled>Choose a team</option>{data.teams.map(team => <option key={team.id} value={team.id}>{team.name}</option>)}</select></label>;
}
function PriorityField() { return <label>Priority<select name="priority" defaultValue="normal"><option value="low">Low</option><option value="normal">Normal</option><option value="high">High</option><option value="urgent">Urgent</option></select></label>; }

export function CreateApplicationItem({ app, data, team, actorId, initialEmployee, busy, error, mutate, onClose, onCreated }: CreateProps) {
  const initialPerson = data.people.find(person => person.id === initialEmployee);
  const [selectedTeam, setTeam] = useState(initialPerson?.team_id || team || (data.teams.length === 1 ? data.teams[0].id : ""));
  const [employee, setEmployee] = useState(initialPerson?.id ?? "");
  const [taskIds, setTaskIds] = useState<string[]>([]);
  const [caseIds, setCaseIds] = useState<string[]>([]);
  const [recipient, setRecipient] = useState("");
  const pendingHandovers = data.handovers.filter(item => item.status === "pending");
  const reservedTasks = new Set(pendingHandovers.flatMap(item => item.task_ids));
  const reservedCases = new Set(pendingHandovers.flatMap(item => item.case_ids));
  const tasks = data.tasks.filter(task => task.team_id === selectedTeam && isTaskPending(task) && !reservedTasks.has(task.id));
  const cases = data.cases.filter(item => item.team_id === selectedTeam && isCasePending(item) && !reservedCases.has(item.id));
  const recipients = eligibleRecipients(data.recipients, selectedTeam);
  const people = data.people.filter(person => !selectedTeam || person.team_id === selectedTeam);
  const changeTeam = (next: string) => { setTeam(next); setEmployee(""); setTaskIds([]); setCaseIds([]); setRecipient(""); };
  const toggle = (id: string, values: string[], set: (values: string[]) => void) => set(values.includes(id) ? values.filter(value => value !== id) : values.length < 30 ? [...values, id] : values);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    let body: unknown;
    if (app === "tasks") {
      const due = field(values, "due_at");
      body = { title: field(values, "title"), team_id: selectedTeam, description: field(values, "description"), required_skills: parseSkills(field(values, "required_skills")), priority: field(values, "priority"), due_at: due ? new Date(due).toISOString() : null };
    } else if (app === "prevention") body = { employee_id: employee, category: field(values, "category"), summary: field(values, "summary"), priority: field(values, "priority") };
    else body = { title: field(values, "title"), team_id: selectedTeam, recipient_member_id: recipient, task_ids: taskIds, case_ids: caseIds, note: field(values, "note") };
    const result = await mutate<{ id: string }>(app === "tasks" ? "/tasks" : app === "prevention" ? "/cases" : "/handovers", body);
    if (result) onCreated(result.id);
  }
  const title = app === "tasks" ? "Create a task" : app === "prevention" ? "Open a support case" : "Prepare a handover";
  const subtitle = app === "tasks" ? "Define the work. You’ll review candidates before assigning it." : app === "prevention" ? "Record a reported concern and agree on a next step." : "The recipient must accept before responsibility changes.";
  return <ApplicationDialog title={title} subtitle={subtitle} onClose={onClose} busy={busy} wide={app === "handover"}>
    <form className="apps-form" onSubmit={event => void submit(event)} data-testid={`apps-create-${app}`}>
      <InlineNotice message={error} error />
      <fieldset disabled={busy}>
        {app !== "prevention" && <label>{app === "tasks" ? "What needs to be done?" : "Handover title"}<input name="title" autoFocus required minLength={3} maxLength={120} placeholder={app === "tasks" ? "e.g. Cover the afternoon reception desk" : "e.g. Evening shift · North team"} /></label>}
        <div className="apps-form-columns"><TeamField data={data} value={selectedTeam} onChange={changeTeam} />{app !== "handover" && <PriorityField />}</div>
        {app === "tasks" && <>
          <label>Required skills<input name="required_skills" maxLength={400} placeholder="e.g. first aid, equipment handling" /><small>Separate skills with commas. Leave empty if none are required.</small></label>
          <details className="apps-form-more"><summary>Add instructions or a due time</summary><label>Instructions<textarea name="description" maxLength={1000} rows={3} placeholder="A clear, practical description of the work." /></label><label>Due time <span className="apps-optional">Optional · your local time</span><input name="due_at" type="datetime-local" /></label></details>
          <div className="apps-form-note"><Users size={18} /><p>Suggestions use recorded skills, availability and active tasks. You make the assignment.</p></div>
        </>}
        {app === "prevention" && <>
          <label>Employee<select value={employee} required onChange={event => setEmployee(event.target.value)}><option value="" disabled>Choose a person</option>{people.map(person => <option key={person.id} value={person.id}>{person.name}</option>)}</select></label>
          <label>Type of concern<select name="category" defaultValue="workload">{Object.entries(categoryLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label>What needs attention?<textarea name="summary" required minLength={3} maxLength={500} rows={4} placeholder="e.g. Sam requested help covering two overlapping tasks." /><small>Record operational context. Avoid medical or sensitive personal details.</small></label>
          <div className="apps-form-note"><HandHeart size={18} /><p>This is a human-reported concern. It is not an automatic assessment of someone’s health.</p></div>
        </>}
        {app === "handover" && <>
          <label>Who is taking over?<select value={recipient} required onChange={event => setRecipient(event.target.value)}><option value="" disabled>Choose a recipient</option>{recipients.map(person => <option value={person.id} key={person.id}>{person.name}{person.id === actorId ? " (you)" : ""}</option>)}</select>{recipient === actorId && <small>You are the recipient. This lets you complete a self-handover, including in a demo.</small>}</label>
          <section className="apps-work-picker" aria-label="Pending work to hand over"><div><h3>Pending work</h3><span>{taskIds.length + caseIds.length} selected</span></div>{!selectedTeam ? <p>Choose a team to see its pending work.</p> : !tasks.length && !cases.length ? <p>No eligible pending work. Items already in a pending handover are excluded.</p> : <>
            {tasks.map(task => <label className="apps-check-row" key={task.id}><input type="checkbox" checked={taskIds.includes(task.id)} onChange={() => toggle(task.id, taskIds, setTaskIds)} /><ClipboardList size={18} /><span><strong>{task.title}</strong><small>Task · {data.people.find(person => person.id === task.assignee_id)?.name ?? "Unassigned"}</small></span></label>)}
            {cases.map(item => <label className="apps-check-row" key={item.id}><input type="checkbox" checked={caseIds.includes(item.id)} onChange={() => toggle(item.id, caseIds, setCaseIds)} /><HandHeart size={18} /><span><strong>{item.summary}</strong><small>Support case · {data.people.find(person => person.id === item.employee_id)?.name ?? "Employee"}</small></span></label>)}
          </>}</section><p className="apps-small">Up to 30 tasks and 30 cases. Work already included in a pending handover is excluded.</p>
          <label>Note for the next shift <span className="apps-optional">Optional</span><textarea name="note" maxLength={1000} rows={3} placeholder="What does the next person need to know?" /></label>
          <div className="apps-form-note"><Check size={18} /><p>Pending items stay open. Employee assignments stay the same; only responsibility transfers on acceptance.</p></div>
        </>}
      </fieldset>
      <footer className="apps-form-footer"><button type="button" className="apps-button apps-button-secondary" onClick={onClose} disabled={busy}>Cancel</button><button className="apps-button apps-button-primary" disabled={busy || !selectedTeam || (app === "prevention" && !employee) || (app === "handover" && (!recipient || !taskIds.length && !caseIds.length))}><SavingLabel busy={busy}>{app === "tasks" ? "Create task" : app === "prevention" ? "Open support case" : "Send handover"}<ArrowRight size={17} /></SavingLabel></button></footer>
    </form>
  </ApplicationDialog>;
}

export function OperationalContextEditor({ person, busy, error, mutate, onClose }: { person: OperationalPerson; busy: boolean; error: string; mutate: ApplicationMutation; onClose: () => void }) {
  // Keep the version shown when editing began: polling must not silently rebase
  // an older form onto another manager's newly saved operational context.
  const [openedContext] = useState(person);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    const result = await mutate(`/people/${person.id}/context`, { version: openedContext.context_version, skills: parseSkills(field(values, "skills")), availability: field(values, "availability"), max_active_tasks: Number(field(values, "max_active_tasks")), context_note: field(values, "context_note") }, "PATCH");
    if (result) onClose();
  }
  return <ApplicationDialog title={`Operational context · ${person.name}`} subtitle="Confirm these details with the person before saving." onClose={onClose} busy={busy}>
    <form className="apps-form" onSubmit={event => void submit(event)} data-testid="apps-context-form"><InlineNotice message={error} error />{person.context_version !== openedContext.context_version && <InlineNotice message="This context changed while you were editing. Close and reopen it to review the latest details before saving." error />}<SourceLabel value={openedContext.context_provenance} />
      <fieldset disabled={busy}>
        <label>Skills and qualifications<input name="skills" defaultValue={person.skills.join(", ")} maxLength={400} placeholder="e.g. first aid, reception" /><small>Comma-separated. Use the same names in task requirements.</small></label>
        <div className="apps-form-columns"><label>Availability<select name="availability" defaultValue={person.availability} required><option value="unknown">Not confirmed</option><option value="available">Available</option><option value="busy">Busy</option><option value="unavailable">Unavailable</option></select></label><label>Agreed active task limit<input name="max_active_tasks" type="number" required min={1} max={20} step={1} defaultValue={person.max_active_tasks ?? ""} placeholder="1–20" /></label></div>
        <label>Operational note <span className="apps-optional">Optional</span><textarea name="context_note" defaultValue={person.context_note} maxLength={500} rows={3} placeholder="e.g. Available until 17:00; confirmed at shift briefing." /></label>
        <p className="apps-small">These are human-provided inputs, not wearable measurements or a fitness-for-work assessment.</p>
      </fieldset>
      <footer className="apps-form-footer"><button type="button" className="apps-button apps-button-secondary" onClick={onClose} disabled={busy}>Cancel</button><button className="apps-button apps-button-primary" disabled={busy || person.context_version !== openedContext.context_version}><SavingLabel busy={busy}>Save context<Check size={17} /></SavingLabel></button></footer>
    </form>
  </ApplicationDialog>;
}
