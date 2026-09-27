"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, ArrowRightLeft, Check, ChevronRight, ClipboardList, Clock3, HeartHandshake, LayoutGrid, List, LoaderCircle, Plus, Search, ShieldCheck, Smartphone, Users, WifiOff, X } from "lucide-react";
import type { Snapshot, Member } from "./company-workspace";
import type { ApplicationId, ApplicationsData, OperationalPerson } from "@/lib/applications";
import { availabilityLabels, isCasePending, isTaskPending, normalizeSearch } from "@/lib/applications";
import { rosterPage } from "@/lib/company-roster";
import { RosterPagination } from "./roster-pagination";
import "./company-command-center.css";

type Interpretation = { source: string; updated_at?: number; stress?: { level?: string; score?: number }; workload?: { level?: string; score?: number }; fatigue?: { level?: string; score?: number }; readiness?: { level?: string; score?: number } };
type Person = OperationalPerson & { interpretation?: Interpretation | null };
type View = "all" | "support" | "available" | "unconfirmed";
type Action = { id: string; app: ApplicationId; title: string; subtitle: string; action: string; kind: string; priority: number; time: number };
const unassignedTeam = "__unassigned__";
function matchesTeam(id: string | null | undefined, filter: string) { return !filter || (filter === unassignedTeam ? !id : id === filter); }
const order: Record<string, number> = { urgent: 4, high: 3, normal: 2, low: 1 };
const collator = new Intl.Collator("en", { sensitivity: "base", numeric: true });
function initials(name: string) { return name.trim().split(/\s+/).slice(0, 2).map(part => part[0]).join(""); }
function personState(person: Person) {
  if (person.open_case_count) return { label: "Support requested", kind: "support", Icon: HeartHandshake };
  if (person.max_active_tasks !== null && person.active_task_count >= person.max_active_tasks) return { label: "At task limit", kind: "busy", Icon: ClipboardList };
  if (person.availability === "available") return { label: "Available", kind: "available", Icon: Check };
  if (person.availability === "busy") return { label: "Busy", kind: "busy", Icon: Clock3 };
  return { label: availabilityLabels[person.availability], kind: "unknown", Icon: person.availability === "unavailable" ? Clock3 : Users };
}

export function CompanyCommandCenter({ snapshot, data, error, openApplication, openPeople, openConnections, onRetry, onDemo }: {
  snapshot: Snapshot; data: ApplicationsData | null; error: string;
  openApplication: (app: ApplicationId, target?: string) => void;
  openPeople: (id?: string) => void; openConnections: () => void; onRetry: () => void; onDemo?: () => void;
}) {
  const [query, setQuery] = useState("");
  const [team, setTeam] = useState("");
  const [view, setView] = useState<View>("all");
  const [grouped, setGrouped] = useState(false);
  const [selected, setSelected] = useState("");
  const [pageIndex, setPageIndex] = useState(0);
  const [pageSize, setPageSize] = useState(25);
  const rosterRef = useRef<HTMLElement>(null);
  const trigger = useRef<HTMLElement | null>(null);
  const [showAllActions, setShowAllActions] = useState(false);
  const [actionLimit, setActionLimit] = useState(10);
  const teams = data?.teams ?? snapshot.teams;
  const teamNames = useMemo(() => new Map(teams.map(item => [item.id, item.name])), [teams]);
  const people = useMemo(() => (data?.people ?? []) as Person[], [data?.people]);
  const scoped = useMemo(() => people.filter(person => matchesTeam(person.team_id, team)), [people, team]);
  const tasks = (data?.tasks ?? []).filter(item => matchesTeam(item.team_id, team));
  const cases = (data?.cases ?? []).filter(item => matchesTeam(item.team_id, team));
  const handovers = (data?.handovers ?? []).filter(item => matchesTeam(item.team_id, team));
  const needsSupport = scoped.filter(person => person.open_case_count > 0).length;
  const openTasks = tasks.filter(item => item.status === "open");
  const pendingHandovers = handovers.filter(item => item.status === "pending");
  const names = new Map(people.map(person => [person.id, person.name]));
  const recipients = new Map((data?.recipients ?? []).map(person => [person.id, person.name]));
  const actions: Action[] = [
    ...cases.filter(isCasePending).map(item => ({ id: item.id, app: "prevention" as const, title: item.summary, subtitle: `${names.get(item.employee_id) ?? "Team member"} · ${teamNames.get(item.team_id) ?? "Team"}`, action: item.status === "open" ? "Review case" : "Follow up", kind: "Support", priority: (order[item.priority] ?? 2) * 10 + 3, time: item.created_at })),
    ...openTasks.map(item => ({ id: item.id, app: "tasks" as const, title: item.title, subtitle: `${teamNames.get(item.team_id) ?? "Team"} · ${item.priority === "urgent" ? "Urgent" : item.priority === "high" ? "High priority" : "Not assigned yet"}`, action: "Find a person", kind: "Task", priority: (order[item.priority] ?? 2) * 10 + 1, time: item.created_at })),
    ...pendingHandovers.map(item => ({ id: item.id, app: "handover" as const, title: item.title, subtitle: `${teamNames.get(item.team_id) ?? "Team"} · ${item.can_accept ? "Waiting for your acceptance" : `Waiting for ${recipients.get(item.recipient_member_id) ?? "recipient"}`}`, action: item.can_accept ? "Review handover" : "View handover", kind: "Handover", priority: item.can_accept ? 22 : 0, time: item.created_at })),
  ].sort((a, b) => b.priority - a.priority || a.time - b.time);
  const filtered = useMemo(() => {
    const words = normalizeSearch(query).split(/\s+/).filter(Boolean);
    return scoped.filter(person => words.every(word => normalizeSearch(`${person.name} ${teamNames.get(person.team_id ?? "") ?? "Unassigned"}`).includes(word))
      && (view !== "support" || person.open_case_count > 0)
      && (view !== "available" || personState(person).kind === "available")
      && (view !== "unconfirmed" || person.availability === "unknown"))
      .sort((a, b) => Number(b.open_case_count > 0) - Number(a.open_case_count > 0) || collator.compare(a.name, b.name));
  }, [query, scoped, teamNames, view]);
  const page = rosterPage(filtered, pageIndex, pageSize);
  const person = people.find(item => item.id === selected);
  const connections = snapshot.members.filter(member => matchesTeam(member.team_id, team) && (member.connection?.issue_count ?? 0) > 0).length;
  useEffect(() => { if (pageIndex !== page.page) setPageIndex(page.page); }, [page.page, pageIndex]);
  useEffect(() => { if (selected && !person) setSelected(""); }, [person, selected]);
  function change(operation: () => void) { operation(); setPageIndex(0); setSelected(""); }
  function focusRoster() { requestAnimationFrame(() => { rosterRef.current?.scrollIntoView({ block: "start", behavior: "instant" }); rosterRef.current?.focus({ preventScroll: true }); }); }
  function closePerson() { setSelected(""); requestAnimationFrame(() => (trigger.current?.isConnected ? trigger.current : rosterRef.current)?.focus({ preventScroll: true })); }
  function clear() { change(() => { setQuery(""); setTeam(""); setView("all"); }); }

  if (!data) return <section className="ops-loading" aria-live="polite">{error ? <><WifiOff size={28} /><h2>Team context is unavailable</h2><p>Your data has not been replaced with empty results.</p><button className="co-secondary" onClick={onRetry}>Try again<ArrowRight size={16} /></button></> : <><LoaderCircle className="co-spin" size={25} /><h2>Loading your team</h2><p>Preparing people, tasks and handovers.</p></>}</section>;
  if (!people.length) return <div className="ops-empty-workspace">
    <div className="ops-welcome"><span className="ops-welcome-symbol"><Users size={34} /></span><h2>Bring your team into view.</h2><p>Start with a team and its people. Connect wearables when you are ready.</p><button className="co-primary" onClick={() => openPeople()}><Plus size={18} />Set up your team</button>{onDemo && <button className="co-secondary" onClick={onDemo}><LayoutGrid size={18} />Try a sample workspace</button>}</div>
    <div className="ops-start-steps">{[{ title: "Create a team", text: "A department, location or working group.", Icon: Users }, { title: "Add your people", text: "Employee profiles need no login account.", Icon: Plus }, { title: "Connect their phones", text: "A QR code links each phone to its employee.", Icon: Smartphone }].map(({ title, text, Icon }, index) => <div key={title}><span>{index + 1}</span><Icon size={23} /><h3>{title}</h3><p>{text}</p></div>)}</div>
  </div>;
  return <div className="ops-center" data-testid="command-center">
    <div className="ops-scope"><label>Team<select aria-label="Filter by team" value={team} onChange={event => change(() => setTeam(event.target.value))}><option value="">All teams</option>{teams.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}{people.some(person => !person.team_id) && <option value={unassignedTeam}>Unassigned</option>}</select></label><span><ShieldCheck size={15} />Manager view · measurements protected</span></div>
    <section className="ops-stats" aria-label="Team summary">
      {[{ id: "people", label: "People", value: scoped.length, detail: team ? (team === unassignedTeam ? "Unassigned" : teamNames.get(team)) : `${teams.length} teams`, Icon: Users, onClick: () => { change(() => setView("all")); focusRoster(); } },
        { id: "support", label: "Need support", value: needsSupport, detail: "Open support cases", Icon: HeartHandshake, onClick: () => { change(() => setView("support")); focusRoster(); } },
        { id: "tasks", label: "Tasks to assign", value: openTasks.length, detail: "Waiting for a person", Icon: ClipboardList, onClick: () => openApplication("tasks") },
        { id: "handover", label: "Pending handovers", value: pendingHandovers.length, detail: "Waiting for acceptance", Icon: ArrowRightLeft, onClick: () => openApplication("handover") }].map(({ id, label, value, detail, Icon, onClick }) => <button key={id} className={`ops-stat ${id === "support" && value ? "ops-stat-attention" : ""}`} data-testid={`ops-summary-${id}`} onClick={onClick} aria-label={`${label}: ${value}. View details`}><span><Icon size={18} />{label}</span><strong>{value}<ArrowRight size={18} /></strong><small>{detail}</small></button>)}
    </section>
    <section className="ops-priorities" aria-labelledby="ops-priorities-title">
      <div className="ops-section-heading"><div><h2 id="ops-priorities-title">What needs attention<span>{actions.length}</span></h2><p>Open situations and the next step.</p></div><button className="co-text" onClick={() => openApplication("hub")}>All applications<ArrowRight size={15} /></button></div>
      {actions.length ? <div className="ops-actions">{(showAllActions ? actions.slice(0, actionLimit) : actions.slice(0, 3)).map(item => {
        const Icon = item.app === "prevention" ? HeartHandshake : item.app === "tasks" ? ClipboardList : ArrowRightLeft;
        return <div className={`ops-action ops-action-${item.app}`} key={item.id}><span className="ops-action-icon"><Icon size={21} /></span><div className="ops-action-copy"><span>{item.kind}</span><strong>{item.title}</strong><small>{item.subtitle}</small></div><button className="co-secondary" onClick={() => openApplication(item.app, item.id)} aria-label={`${item.action}: ${item.title}`}>{item.action}<ArrowRight size={15} /></button></div>;
      })}</div> : <div className="ops-clear"><Check size={24} /><div><strong>No open items to review</strong><span>Tasks and support requests will appear here.</span></div></div>}
      {showAllActions && actions.length > actionLimit && <button className="ops-more" onClick={() => setActionLimit(value => value + 10)}>Show next {Math.min(10, actions.length - actionLimit)}<ChevronRight size={14} /></button>}
      {actions.length > 3 && <button className="ops-more" onClick={() => setShowAllActions(value => !value)}>{showAllActions ? "Show fewer" : `Show more (${actions.length - 3})`}<ChevronRight size={14} /></button>}
    </section>
    <section className="ops-roster" ref={rosterRef} tabIndex={-1} aria-labelledby="ops-roster-title">
      <div className="ops-section-heading"><div><h2 id="ops-roster-title">Your team</h2><p>Support requests first. Select a person for context.</p></div><div className="ops-layout-switch" role="group" aria-label="Team display"><button aria-pressed={!grouped} onClick={() => setGrouped(false)}><List size={16} />People</button><button aria-pressed={grouped} onClick={() => setGrouped(true)}><LayoutGrid size={16} />Teams</button></div></div>
      <div className="ops-filters"><label className="ops-search"><span className="sr-only">Find a person or team</span><Search size={18} /><input type="search" aria-label="Search team members" placeholder="Search people or teams" value={query} onChange={event => change(() => setQuery(event.target.value))} />{query && <button className="co-icon" aria-label="Clear search" onClick={() => change(() => setQuery(""))}><X size={17} /></button>}</label><label className="ops-status-filter"><span className="sr-only">Show people by status</span><select aria-label="Filter by team status" value={view} onChange={event => change(() => setView(event.target.value as View))}><option value="all">All people</option><option value="support">Support requested</option><option value="available">Available</option><option value="unconfirmed">Availability not confirmed</option></select></label><span className="ops-results" aria-live="polite">{filtered.length} {filtered.length === 1 ? "person" : "people"}</span>{(query || team || view !== "all") && <button className="co-text" onClick={clear}>Clear filters<X size={14} /></button>}</div>
      {!filtered.length ? <div className="ops-no-results"><Search size={28} /><h3>No people match these filters</h3><p>Try a different name, team or status.</p><button className="co-secondary" onClick={clear}>Show all people</button></div> : grouped ? <div className="ops-team-cards">{[...teams, { id: "", name: "Unassigned" }].map(group => {
        const members = filtered.filter(person => (person.team_id ?? "") === group.id);
        if (!members.length) return null;
        const support = members.filter(person => person.open_case_count).length;
        return <button key={group.id} onClick={() => { change(() => setTeam(group.id || unassignedTeam)); setGrouped(false); }}><span className="ops-team-symbol"><Users size={22} /></span><h3>{group.name}</h3><span>{members.length} people</span><div><span className={support ? "ops-team-support" : ""}>{support ? `${support} need support` : "No open support cases"}</span><ArrowRight size={18} /></div></button>;
      })}</div> : <div className="ops-table-wrap"><div className="ops-table-scroll"><table className="ops-people-table"><caption className="sr-only">Team members, reported status and task count. Status is operational context, not a health clearance.</caption><thead><tr><th>Person</th><th>Current status</th><th>Active tasks</th><th>Connection</th><th><span className="sr-only">Actions</span></th></tr></thead><tbody>{page.items.map(item => {
        const status = personState(item), member = snapshot.members.find(member => member.id === item.id);
        return <tr key={item.id} data-testid={`ops-person-${item.id}`}><th scope="row"><div className="ops-person-name"><span className="ops-avatar">{initials(item.name)}</span><div><strong>{item.name}</strong><small>{teamNames.get(item.team_id ?? "") ?? "Unassigned"}</small></div></div></th><td data-label="Current status"><span className={`ops-badge ${status.kind}`}><status.Icon size={14} />{status.label}</span></td><td data-label="Active tasks"><span className="ops-task-count">{item.active_task_count}<span>{item.max_active_tasks !== null ? ` / ${item.max_active_tasks}` : " assigned"}</span></span></td><td data-label="Connection"><ConnectionLabel member={member} demo={data.organization.is_demo} /></td><td><button className="ops-view-person" onClick={event => { trigger.current = event.currentTarget; setSelected(item.id); }} aria-label={`View ${item.name}`}>View person<ChevronRight size={16} /></button></td></tr>;
      })}</tbody></table></div><RosterPagination {...page} label="Team members" onPage={setPageIndex} onSize={value => { setPageSize(value); setPageIndex(0); }} /></div>}
    </section>
    {!data.organization.is_demo && <button className="ops-connection-link" onClick={openConnections}><Smartphone size={20} /><span><strong>{connections ? `${connections} connections need a check` : "Phone connections"}</strong><small>Manage phone access and data availability</small></span><ArrowRight size={18} /></button>}
    {person && <PersonDialog key={person.id} person={person} member={snapshot.members.find(item => item.id === person.id)} data={data} teamName={teamNames.get(person.team_id ?? "") ?? "Unassigned"} onClose={closePerson} onOpen={openApplication} />}
  </div>;
}

function ConnectionLabel({ member, demo }: { member?: Member; demo: boolean }) {
  if (demo) return <span className="ops-connection example">Example profile</span>;
  if (!member?.sharing || member.connection?.status === "paused") return <span className="ops-connection"><ShieldCheck size={13} />Sharing paused</span>;
  if (member.connection?.status === "summary") return <span className="ops-connection">Periodic updates</span>;
  if (member.connection?.status === "unsupported") return <span className="ops-connection">No supported signals</span>;
  if (member.connection?.status === "permission_required") return <span className="ops-connection">Permission needed</span>;
  if (member.connection?.current_count || member.connection?.status === "current") return <span className="ops-connection connected"><span />Data received</span>;
  return <span className="ops-connection"><WifiOff size={13} />{member.connection?.last_received_at ? "Check connection" : "Not connected"}</span>;
}

function PersonDialog({ person, member, teamName, data, onClose, onOpen }: { person: Person; member?: Member; teamName: string; data: ApplicationsData; onClose: () => void; onOpen: (app: ApplicationId, target?: string) => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const state = personState(person);
  const tasks = data.tasks.filter(item => item.assignee_id === person.id && isTaskPending(item));
  const cases = data.cases.filter(item => item.employee_id === person.id && isCasePending(item));
  useEffect(() => { const el = dialog.current; el?.showModal(); const previous = document.body.style.overflow; document.body.style.overflow = "hidden"; return () => { el?.close(); document.body.style.overflow = previous; }; }, []);
  function go(app: ApplicationId, target?: string) { onClose(); onOpen(app, target); }
  return <dialog className="ops-person-dialog" ref={dialog} aria-labelledby="ops-person-title" onCancel={event => { event.preventDefault(); onClose(); }} onClick={event => { if (event.target === event.currentTarget) { const rect = event.currentTarget.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) onClose(); } }}>
    <header><button className="co-text" onClick={onClose}><ArrowLeft size={16} />Back to team</button><button className="co-icon" aria-label="Close person details" onClick={onClose}><X size={21} /></button></header>
    <div className="ops-person-hero"><span className="ops-avatar">{initials(person.name)}</span><div><h2 id="ops-person-title">{person.name}</h2><p>{teamName}</p></div><span className={`ops-badge ${state.kind}`}><state.Icon size={15} />{state.label}</span></div>
    <div className="ops-person-facts"><div><span>Availability</span><strong>{availabilityLabels[person.availability]}</strong></div><div><span>Active tasks</span><strong>{person.active_task_count}{person.max_active_tasks !== null && <small> / {person.max_active_tasks} limit</small>}</strong></div><div><span>Open support cases</span><strong>{person.open_case_count}</strong></div></div>
    {data.organization.is_demo && person.interpretation ? <section className="ops-estimates"><div><h3>Team status</h3><span>Illustrative estimates</span></div><div className="ops-estimate-grid">{(["stress", "workload", "fatigue", "readiness"] as const).map(key => {
      const value = person.interpretation?.[key];
      const level = value?.level ?? "Unavailable";
      const score = typeof value?.score === "number" ? Math.max(0, Math.min(100, value.score)) : null;
      return <div key={key}><span>{key[0].toUpperCase() + key.slice(1)}</span><strong>{level}</strong>{score !== null && <div className={`ops-estimate-track ${key}`} aria-hidden="true"><i style={{ width: `${score}%` }} /></div>}</div>;
    })}</div><p>Scripted for this example. Underlying measurements are not shared.</p></section> : <div className="ops-context-note"><ShieldCheck size={18} /><span>Availability and support are human-reported. Physiological measurements are protected.</span></div>}
    <section className="ops-person-section"><div><h3>Qualifications</h3>{person.can_edit && <button className="co-text" onClick={() => go("tasks", `person:${person.id}`)}>Edit work context<ArrowRight size={14} /></button>}</div>{person.skills.length ? <div className="ops-skill-list">{person.skills.map(skill => <span key={skill}>{skill}</span>)}</div> : <p>Qualifications have not been added.</p>}{person.context_note && <p>{person.context_note}</p>}</section>
    <section className="ops-person-section"><div><h3>Support & follow-up</h3><span>{cases.length}</span></div>{cases.length ? cases.map(item => <button className="ops-person-item" key={item.id} onClick={() => go("prevention", item.id)}><HeartHandshake size={18} /><span>{item.summary}<small>{item.status === "in_progress" ? "Action taken · follow-up pending" : "Needs review"}</small></span><ChevronRight size={17} /></button>) : <p>No open support cases.</p>}<button className="co-secondary" onClick={() => go("prevention", `new:${person.id}`)}><Plus size={16} />Open support case</button></section>
    <section className="ops-person-section"><div><h3>Current tasks</h3><span>{tasks.length}</span></div>{tasks.length ? tasks.map(task => <button className="ops-person-item" key={task.id} onClick={() => go("tasks", task.id)}><ClipboardList size={18} /><span>{task.title}<small>{task.status === "in_progress" ? "In progress" : "Assigned"}</small></span><ChevronRight size={17} /></button>) : <p>No active assignments.</p>}</section>
    <footer><ShieldCheck size={15} />Manager view<ConnectionLabel member={member} demo={data.organization.is_demo} /></footer>
  </dialog>;
}
