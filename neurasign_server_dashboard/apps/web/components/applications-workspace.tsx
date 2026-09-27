"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, CheckCircle2, ClipboardList, HandHeart, Layers3, LoaderCircle, Plus, RefreshCw, Search, Settings2, Users, Waypoints } from "lucide-react";
import { applicationInfo, availabilityLabels, displayTime, isCasePending, isTaskPending, matchesApplicationItem, normalizeSearch, type ApplicationApi, type ApplicationId, type ApplicationsData, type ApplicationTeam } from "@/lib/applications";
import { CreateApplicationItem, OperationalContextEditor, type ApplicationMutation } from "./applications-forms";
import { HandoverDetail, SupportCaseDetail, TaskDetail } from "./applications-details";
import { InlineNotice, SourceLabel, StatusLabel, WorkflowSteps } from "./applications-shared";
import "./applications.css";

export type ApplicationsWorkspaceProps = {
  org: string;
  snapshot: { me: { id?: string; role: string }; teams: ApplicationTeam[]; members: { id: string; name: string; team_id?: string | null }[] };
  api: ApplicationApi;
  data?: ApplicationsData | null;
  loading?: boolean;
  error?: string;
  onChanged?: () => void | Promise<void>;
  initialApp?: ApplicationId;
  target?: string;
  onNavigate?: (app: ApplicationId, target?: string) => void;
};
const moduleIcons = { tasks: ClipboardList, prevention: HandHeart, handover: Waypoints };
const moduleIds = ["tasks", "prevention", "handover"] as const;
const errorMessage = (error: unknown) => error instanceof Error ? error.message : "This action could not be saved. Please try again.";
const isCreationTarget = (target?: string) => target === "new" || target?.startsWith("new:");
const recordTarget = (target?: string) => isCreationTarget(target) || target?.startsWith("person:") ? null : target ?? null;

export function ApplicationsWorkspace({ org, snapshot, api, data: controlledData, loading: controlledLoading, error: controlledError, onChanged, initialApp = "hub", target, onNavigate }: ApplicationsWorkspaceProps) {
  const [remote, setRemote] = useState<ApplicationsData | null>(null);
  const [fetchError, setFetchError] = useState("");
  const [loading, setLoading] = useState(true);
  const [app, setApp] = useState<ApplicationId>(initialApp);
  const [selectedId, setSelectedId] = useState<string | null>(recordTarget(target));
  const [editingId, setEditingId] = useState<string | null>(target?.startsWith("person:") ? target.slice(7) : null);
  const [creating, setCreating] = useState(Boolean(isCreationTarget(target)));
  const [contextOpen, setContextOpen] = useState(false);
  const [team, setTeam] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("active");
  const [page, setPage] = useState(0);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  const [notice, setNotice] = useState("");
  const inFlight = useRef(false);
  const requests = useRef(new Map<string, string>());
  const mounted = useRef(true);
  const base = `/organizations/${org}/applications`;
  const controlled = controlledData !== undefined;
  const data = controlled ? controlledData : remote;
  const initialLoading = controlled ? controlledLoading ?? !data : loading;
  const serviceError = controlled ? controlledError ?? "" : fetchError;
  const headingRef = useRef<HTMLHeadingElement>(null);
  const reload = useCallback(async () => {
    if (controlled) { await onChanged?.(); return; }
    const result = await api<ApplicationsData>(base);
    if (mounted.current) { setRemote(result); setFetchError(""); setLoading(false); }
    await onChanged?.();
  }, [api, base, controlled, onChanged]);

  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    setApp(initialApp); setSelectedId(recordTarget(target)); setEditingId(target?.startsWith("person:") ? target.slice(7) : null); setCreating(Boolean(isCreationTarget(target)));
  }, [initialApp, target]);
  useEffect(() => {
    if (controlled) return;
    let active = true, running = false;
    setRemote(null); setLoading(true);
    const load = async () => {
      if (running) return;
      running = true;
      try { const value = await api<ApplicationsData>(base); if (active) { setRemote(value); setFetchError(""); } }
      catch (error) { if (active) setFetchError(errorMessage(error)); }
      finally { running = false; if (active) setLoading(false); }
    };
    void load(); const timer = setInterval(load, 5000);
    return () => { active = false; clearInterval(timer); };
  }, [api, base, controlled]);
  useEffect(() => { setPage(0); }, [team, query, status, app]);

  const mutate: ApplicationMutation = async <T,>(path: string, body: unknown, method = "POST"): Promise<T | null> => {
    if (inFlight.current) return null;
    inFlight.current = true; setBusy(true); setActionError(""); setNotice("");
    const key = `${base}${path}:${method}:${JSON.stringify(body)}`;
    const requestId = requests.current.get(key) ?? crypto.randomUUID();
    requests.current.set(key, requestId);
    try {
      const payload = method === "POST" ? { ...(body as Record<string, unknown>), request_id: requestId } : body;
      const result = await api<T>(`${base}${path}`, method, payload);
      requests.current.delete(key);
      let refreshed = true;
      try { await reload(); } catch { refreshed = false; if (mounted.current) setFetchError("Saved successfully. Refresh to see the latest data."); }
      if (mounted.current) setNotice(refreshed ? "Saved. Your team’s workspace is up to date." : "Saved successfully. The latest view could not be loaded.");
      return result;
    } catch (error) {
      if (mounted.current) setActionError(errorMessage(error));
      // Refresh versions after a conflict; a transport retry retains its idempotency key.
      try { await reload(); } catch { /* Keep the original actionable error visible. */ }
      return null;
    } finally { inFlight.current = false; if (mounted.current) setBusy(false); }
  };

  function navigate(next: ApplicationId, id?: string) {
    setApp(next); setSelectedId(id ?? null); setCreating(false); setEditingId(null); setActionError(""); setNotice("");
    if (next !== app) { setQuery(""); setStatus("active"); setContextOpen(false); }
    onNavigate?.(next, id);
  }
  const openItem = (id: string) => { setActionError(""); setSelectedId(id); onNavigate?.(app, id); };
  const openCreate = () => { setActionError(""); setCreating(true); onNavigate?.(app, "new"); };
  const closeDetail = () => { setSelectedId(null); setActionError(""); onNavigate?.(app); };
  function retry() { void reload().catch(error => setFetchError(errorMessage(error))); }

  if (!data) return <section className="apps-workspace"><div className="apps-loading-panel" role={serviceError ? "alert" : "status"}>{initialLoading && !serviceError ? <><LoaderCircle size={28} className="apps-spin" /><h2>Loading your applications</h2><p>Preparing your team’s tasks, support cases and handovers.</p></> : <><Layers3 size={30} /><h2>Applications are unavailable</h2><p>{serviceError || "Your workspace could not be loaded."}</p><button className="apps-button apps-button-primary" onClick={retry}><RefreshCw size={16} />Try again</button></>}</div></section>;

  const teamNames = new Map(data.teams.map(value => [value.id, value.name]));
  const names = new Map(data.people.map(person => [person.id, person.name]));
  const counts = { tasks: data.tasks.filter(isTaskPending).length, prevention: data.cases.filter(isCasePending).length, handover: data.handovers.filter(item => item.status === "pending").length };
  const records = app === "tasks" ? data.tasks.map(task => ({ ...task, label: task.title, detail: names.get(task.assignee_id ?? "") ?? "Unassigned", meta: task.due_at ? `Due ${displayTime(task.due_at)}` : "No due time" })) : app === "prevention" ? data.cases.map(item => ({ ...item, label: names.get(item.employee_id) ?? "Employee", detail: item.summary, meta: `${item.actions.length} ${item.actions.length === 1 ? "action" : "actions"} recorded` })) : app === "handover" ? data.handovers.map(item => ({ ...item, label: item.title, detail: `To ${data.recipients.find(person => person.id === item.recipient_member_id)?.name ?? "recipient"}`, meta: `${item.task_ids.length + item.case_ids.length} pending items` })) : [];
  const filtered = records.filter(item => matchesApplicationItem(item, query, team, status, `${item.label} ${item.detail} ${teamNames.get(item.team_id) ?? ""}`)).sort((a, b) => b.updated_at - a.updated_at || a.id.localeCompare(b.id));
  const pageSize = 15, pages = Math.max(1, Math.ceil(filtered.length / pageSize)), currentPage = Math.min(page, pages - 1);
  const visible = filtered.slice(currentPage * pageSize, (currentPage + 1) * pageSize);
  const info = app === "hub" ? null : applicationInfo[app];
  const canCreate = app === "prevention" ? data.permissions.can_create_cases : data.permissions.can_manage;
  const selectedTask = app === "tasks" ? data.tasks.find(item => item.id === selectedId) : undefined;
  const selectedCase = app === "prevention" ? data.cases.find(item => item.id === selectedId) : undefined;
  const selectedHandover = app === "handover" ? data.handovers.find(item => item.id === selectedId) : undefined;
  const editingPerson = data.people.find(person => person.id === editingId && person.can_edit);
  const filteredPeople = data.people.filter(person => (!team || person.team_id === team) && normalizeSearch(`${person.name} ${person.skills.join(" ")}`).includes(normalizeSearch(query)));

  return <section className="apps-workspace" data-testid={app === "hub" ? "apps-hub" : `apps-module-${app}`}>
    {(serviceError || fetchError) && <div className="apps-service-warning" role="alert"><span>{serviceError || fetchError}</span><button className="apps-button apps-button-quiet" onClick={retry}><RefreshCw size={16} />Refresh</button></div>}
    {data.organization.is_demo && !controlled && <div className="apps-demo-label"><SourceLabel value="demo" /><span>{data.organization.demo_label || "Fictional operational inputs. Actions are saved only in this demo workspace."}</span></div>}
    {app !== "hub" && <button className="apps-button apps-back" onClick={() => navigate("hub")}><ArrowLeft size={17} />All applications</button>}
    {info ? <header className="apps-page-header"><div><h2 ref={headingRef} tabIndex={-1}>{info.title}</h2><p>{info.description}</p></div>{canCreate && <button className="apps-button apps-button-primary" data-testid="apps-create" disabled={!data.teams.length} onClick={openCreate}><Plus size={18} />{info.action}</button>}</header> : <p className="apps-hub-intro">Choose a workflow. Keep your team’s next steps in one place.</p>}
    {app === "hub" ? <>
      <div className="apps-hub-summary"><span><strong>{counts.tasks}</strong> active tasks</span><span><strong>{counts.prevention}</strong> open support cases</span><span><strong>{counts.handover}</strong> pending handovers</span></div>
      <div className="apps-catalog">{moduleIds.map(id => { const Icon = moduleIcons[id], module = applicationInfo[id]; return <button key={id} className={`apps-module-entry apps-entry-${id}`} data-testid={`apps-open-${id}`} onClick={() => navigate(id)}><div className="apps-module-symbol"><Icon size={25} strokeWidth={1.6} /></div><div className="apps-module-copy"><h3>{module.title}</h3><p>{module.description}</p><div className="apps-module-journey">{module.steps.map((step, position) => <span key={step}>{position > 0 && <ArrowRight size={13} aria-hidden="true" />}{step}</span>)}</div></div><span className="apps-module-open"><span>{counts[id]} {id === "tasks" ? "active" : id === "prevention" ? "open" : "pending"}</span><span>Open application<ArrowRight size={18} /></span></span></button>; })}</div>
    </> : <>
      <nav className="apps-module-tabs" aria-label="Applications">{moduleIds.map(id => { const Icon = moduleIcons[id]; return <button key={id} onClick={() => navigate(id)} aria-current={app === id ? "page" : undefined}><Icon size={17} />{applicationInfo[id].short}<span>{counts[id]}</span></button>; })}</nav>
      <WorkflowSteps steps={info!.steps} />
      {!data.teams.length && <div className="apps-empty-compact"><Users size={23} /><h3>Start with a team</h3><p>Create a team and add employees in People & teams. They’ll be available here.</p></div>}
      {!selectedId && !creating && !editingId && <InlineNotice message={notice} />}
      <div className="apps-toolbar"><label className="apps-search">Search<div><Search size={17} /><input type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder={app === "tasks" ? "Task, person or team" : app === "prevention" ? "Person, concern or team" : "Handover, recipient or team"} /></div></label><label>Team<select value={team} onChange={event => setTeam(event.target.value)}><option value="">All teams</option>{data.teams.map(value => <option value={value.id} key={value.id}>{value.name}</option>)}</select></label><label>Show<select value={status} onChange={event => setStatus(event.target.value)}><option value="active">{app === "handover" ? "Awaiting acceptance" : "Active work"}</option><option value="closed">{app === "prevention" ? "Resolved" : "Completed / closed"}</option><option value="all">All activity</option></select></label></div>
      <div className="apps-results-heading"><span>{filtered.length} {app === "tasks" ? "tasks" : app === "prevention" ? "support cases" : "handovers"}{team ? ` · ${teamNames.get(team)}` : ""}</span>{app === "tasks" && <button className="apps-button apps-button-quiet" aria-expanded={contextOpen} onClick={() => setContextOpen(value => !value)}><Settings2 size={16} />Team context</button>}</div>
      {contextOpen && app === "tasks" && <section className="apps-context-panel"><div className="apps-section-heading"><div><h3>Operational context</h3><p>Skills, availability and agreed task limits. Provided by people, not inferred from wearables.</p></div></div>{!filteredPeople.length ? <p className="apps-small">No matching employees. Add people in People & teams or adjust your filters.</p> : <div className="apps-context-list">{filteredPeople.map(person => <div key={person.id}><span className="apps-avatar" aria-hidden="true">{person.name[0]}</span><div><strong>{person.name}</strong><small>{availabilityLabels[person.availability]} · {person.skills.length ? person.skills.join(", ") : "Skills not provided"}</small><SourceLabel value={person.context_provenance} /></div>{person.can_edit && <button className="apps-button apps-button-secondary" data-testid={`apps-person-context-${person.id}`} onClick={() => { setActionError(""); setEditingId(person.id); }}><Settings2 size={15} />Edit context</button>}</div>)}</div>}</section>}
      {!visible.length ? <div className="apps-list-empty"><span className="apps-empty-symbol">{app === "tasks" ? <ClipboardList size={28} /> : app === "prevention" ? <HandHeart size={28} /> : <Waypoints size={28} />}</span><h3>{query || team || status !== "active" ? "No matching activity" : app === "tasks" ? "Give the next task a clear owner." : app === "prevention" ? "A clear place to follow through." : "Make the next shift a smooth one."}</h3><p>{query || team || status !== "active" ? "Adjust your search or filters to find the work you need." : app === "tasks" ? "Create a task, review available people and confirm the assignment." : app === "prevention" ? "Open a case when someone reports a concern. Record the support and its outcome." : "Choose pending tasks and cases, then ask the next person to accept."}</p>{query || team || status !== "active" ? <button className="apps-button apps-button-secondary" onClick={() => { setQuery(""); setTeam(""); setStatus("all"); }}>Clear filters</button> : canCreate && <button className="apps-button apps-button-secondary" disabled={!data.teams.length} onClick={() => { setActionError(""); setCreating(true); }}><Plus size={17} />{info!.action}</button>}</div> : <div className="apps-record-list" aria-label={info!.title}>{visible.map(item => <button key={item.id} className="apps-record-row" data-testid={`apps-row-${item.id}`} onClick={() => openItem(item.id)}><div className="apps-record-main"><strong>{item.label}</strong><span>{item.detail}</span><div><span>{teamNames.get(item.team_id) ?? "Team"}</span><span aria-hidden="true">·</span><SourceLabel value={item.provenance} /></div></div><div className="apps-record-state"><StatusLabel value={item.status} /><small>{item.meta}</small></div><span className="apps-row-open">View<ArrowRight size={17} /></span></button>)}</div>}
      {filtered.length > pageSize && <nav className="apps-pagination" aria-label="Activity pages"><span>{currentPage * pageSize + 1}–{Math.min((currentPage + 1) * pageSize, filtered.length)} of {filtered.length}</span><div><button className="apps-button apps-button-secondary" disabled={!currentPage} onClick={() => setPage(currentPage - 1)}><ArrowLeft size={16} />Previous</button><button className="apps-button apps-button-secondary" disabled={currentPage >= pages - 1} onClick={() => setPage(currentPage + 1)}>Next<ArrowRight size={16} /></button></div></nav>}
      {selectedId && !selectedTask && !selectedCase && !selectedHandover && <InlineNotice message="This item is no longer available in your current team access. Refresh the list to continue." error />}
    </>}
    {creating && app !== "hub" && <CreateApplicationItem app={app} data={data} team={team} actorId={snapshot.me.id} initialEmployee={target?.startsWith("new:") ? target.slice(4) : undefined} busy={busy} error={actionError} mutate={mutate} onClose={() => { setCreating(false); setActionError(""); onNavigate?.(app); }} onCreated={id => { setCreating(false); setStatus("active"); openItem(id); }} />}
    {selectedTask && <TaskDetail task={selectedTask} data={data} api={api} base={base} busy={busy} error={editingId ? "" : actionError} mutate={mutate} onClose={closeDetail} onEditPerson={person => { setActionError(""); setEditingId(person.id); }} />}
    {selectedCase && <SupportCaseDetail item={selectedCase} data={data} busy={busy} error={actionError} mutate={mutate} onClose={closeDetail} />}
    {selectedHandover && <HandoverDetail item={selectedHandover} data={data} busy={busy} error={actionError} mutate={mutate} onClose={closeDetail} actorId={snapshot.me.id} actorRole={snapshot.me.role} />}
    {editingPerson && <OperationalContextEditor person={editingPerson} busy={busy} error={actionError} mutate={mutate} onClose={() => { setEditingId(null); setActionError(""); if (target?.startsWith("person:")) onNavigate?.(app); }} />}
  </section>;
}

export default ApplicationsWorkspace;
