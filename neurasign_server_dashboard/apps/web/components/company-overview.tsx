"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, Check, ChevronRight, CircleHelp, Clock3, Pause, Radio, Search, Smartphone, Users, WifiOff, X } from "lucide-react";
import { EmployeeSignalDetail } from "./employee-signal-detail";
import { RosterPagination } from "./roster-pagination";
import { dataStatusLabels, lastReceived, personDataStatus, personSource, rosterPage, selectRoster, type RosterSort } from "@/lib/company-roster";
import { classifyAttention, groupTeams, summarizeTeam, hasCurrentWearableData } from "@/lib/team-attention";
import type { Snapshot } from "./company-workspace";
import "./company-overview.css";

type View = "all" | "attention" | "teams" | "paused" | "current";
type Issue = "" | "permission" | "stale" | "setup";
const issueLabels = { permission: "Permission needed", stale: "No recent data", setup: "Waiting for data" };
const viewLabels: Record<View, string> = { all: "All employees", attention: "Connection help", teams: "By team", paused: "Sharing paused", current: "Recent wearable data" };
const collator = new Intl.Collator("en", { sensitivity: "base", numeric: true });
function receivedLabel(timestamp: number | null, now: number) {
  if (!timestamp) return "Not received yet";
  const seconds = Math.max(0, now - timestamp);
  if (seconds < 60) return "Just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} hr ago`;
  return `${Math.floor(seconds / 86400)} days ago`;
}

export function CompanyOverview({ snapshot, org, canManage, openPeople, demoAvailable, api }: {
  snapshot: Snapshot; org: string; canManage: boolean; openPeople: (id?: string) => void; demoAvailable: boolean;
  api: <T>(path: string) => Promise<T>;
}) {
  const [selected, setSelected] = useState("");
  const [query, setQuery] = useState("");
  const [team, setTeam] = useState("");
  const [view, setView] = useState<View>("all");
  const [issue, setIssue] = useState<Issue>("");
  const [dataStatus, setDataStatus] = useState("");
  const [sort, setSort] = useState<RosterSort | "attention">("attention");
  const [pageIndex, setPageIndex] = useState(0);
  const [pageSize, setPageSize] = useState(25);
  const rosterRef = useRef<HTMLElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement | null>(null);
  const members = useMemo(() => {
    const arrivals = new Map<string, number>();
    for (const device of snapshot.devices) if (device.last_received_at && Number.isFinite(device.last_received_at)) arrivals.set(device.member_id, Math.max(arrivals.get(device.member_id) ?? 0, device.last_received_at));
    return snapshot.members.map(member => ({ ...member, last_received_at: arrivals.get(member.id) ?? null }));
  }, [snapshot.members, snapshot.devices]);
  const teamNames = useMemo(() => new Map(snapshot.teams.map(item => [item.id, item.name])), [snapshot.teams]);
  const scoped = useMemo(() => selectRoster(members, snapshot.teams, { team }), [members, snapshot.teams, team]);
  const summary = useMemo(() => summarizeTeam(scoped, snapshot.server_time), [scoped, snapshot.server_time]);
  const attention = useMemo(() => new Map(members.map(member => [member.id, classifyAttention(member, snapshot.server_time)])), [members, snapshot.server_time]);
  const categories = (Object.keys(issueLabels) as Exclude<Issue, "">[]).map(kind => ({ kind, count: scoped.filter(member => attention.get(member.id)?.kind === kind).length }));
  const filtered = useMemo(() => {
    const result = selectRoster(scoped, snapshot.teams, { query, status: dataStatus, sort: sort === "attention" ? "name" : sort }).filter(member => {
      const item = attention.get(member.id)!;
      if (view === "attention" && item.priority <= 0) return false;
      if (view === "paused" && personDataStatus(member) !== "paused") return false;
      if (view === "current" && !hasCurrentWearableData(member, snapshot.server_time)) return false;
      return !issue || item.kind === issue;
    });
    return sort === "attention" ? result.sort((a, b) => attention.get(b.id)!.priority - attention.get(a.id)!.priority || collator.compare(a.name, b.name) || collator.compare(a.id, b.id)) : result;
  }, [scoped, snapshot.teams, snapshot.server_time, query, dataStatus, sort, view, issue, attention]);
  const groups = useMemo(() => groupTeams(filtered, snapshot.teams, snapshot.server_time).filter(group => group.people.length), [filtered, snapshot.teams, snapshot.server_time]);
  const page = rosterPage(filtered, pageIndex, pageSize);
  const teamPage = rosterPage(groups, pageIndex, pageSize);
  const activePage = view === "teams" ? teamPage : page;
  const person = filtered.find(member => member.id === selected);
  useEffect(() => { if (selected && !person) closeDetails(); }, [selected, person]);
  useEffect(() => { if (pageIndex !== activePage.page) setPageIndex(activePage.page); }, [activePage.page, pageIndex]);
  function change(update: () => void) { update(); setPageIndex(0); setSelected(""); if (scrollRef.current) scrollRef.current.scrollTop = 0; }
  function showView(next: View) { change(() => { setView(next); setIssue(""); setDataStatus(""); setQuery(""); }); }
  function resetFilters() { change(() => { setQuery(""); setTeam(""); setDataStatus(""); setIssue(""); setView("all"); }); }
  function jumpToResults() { requestAnimationFrame(() => { rosterRef.current?.focus({ preventScroll: true }); rosterRef.current?.scrollIntoView({ block: "start", behavior: "instant" }); }); }
  function closeDetails() { setSelected(""); requestAnimationFrame(() => { (trigger.current?.isConnected ? trigger.current : rosterRef.current)?.focus({ preventScroll: true }); }); }
  const hasFilters = Boolean(query || team || dataStatus || issue || view !== "all");
  const teamName = team === "unassigned" ? "Unassigned" : teamNames.get(team) ?? "All teams";
  const emptyWorkspace = members.length === 0;
  return <div className="co-overview">
    <div className="ov-scope"><label>Team<select aria-label="Filter by team" value={team} onChange={event => change(() => setTeam(event.target.value))}><option value="">All teams</option>{snapshot.teams.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}<option value="unassigned">Unassigned</option></select></label><span><Radio size={14} />Counts update with received data</span></div>
    <section className="ov-summary" aria-label="Workspace summary">
      {([
        { id: "all", label: "Employees", value: summary.total, note: team ? teamName : `${snapshot.teams.length} ${snapshot.teams.length === 1 ? "team" : "teams"} in this workspace`, Icon: Users },
        { id: "current", label: "Recent wearable data", value: summary.currentWearable, note: "People sending recent measurements", Icon: Radio },
        { id: "attention", label: "Need connection help", value: summary.attention, note: "Missing data or permissions", Icon: WifiOff },
        { id: "paused", label: "Sharing paused", value: summary.paused, note: "Employee-controlled · no action needed", Icon: Pause },
      ] as const).map(({ id, label, value, note, Icon }) => <button key={id} className={`ov-summary-item ${id === "attention" && value ? "has-issues" : ""}`} data-testid={`summary-${id}`} aria-label={`${label}: ${value}. View employees`} onClick={() => { showView(id); jumpToResults(); }}><span><Icon size={18} />{label}</span><strong>{value}<ArrowRight size={18} /></strong><small>{note}</small></button>)}
    </section>
    {emptyWorkspace ? <section className="ov-welcome"><div><span className="ov-welcome-icon"><Users size={28} /></span><h2>Start with your people.</h2><p>Create a team, add employees and connect their phones.</p></div><ol><li><b>1</b><span>Create a team<small>Group employees by department or location.</small></span></li><li><b>2</b><span>Add employees<small>They do not need a dashboard account.</small></span></li><li><b>3</b><span>Connect their phones<small>Scan a code using NEURASIGN Link.</small></span></li></ol><div>{canManage && <button className="co-primary" onClick={() => openPeople()}>Set up your team<ArrowRight size={16} /></button>}{demoAvailable && <a className="co-secondary" href="/demo">Explore recorded demo<ArrowRight size={16} /></a>}</div></section> : <>
      <section className={`ov-attention ${summary.attention ? "has-issues" : ""}`} aria-label="Connection attention">
        <div>{summary.attention ? <WifiOff size={22} /> : <Check size={22} />}<div><h2>{summary.attention ? `${summary.attention} ${summary.attention === 1 ? "person needs" : "people need"} connection help` : "No connection issues to review"}</h2><p>{summary.attention ? "Review these connections to restore missing measurements." : "Paused sharing and device capabilities are shown separately."}</p></div></div>
        <div className="ov-issue-shortcuts">{categories.filter(item => item.count).map(({ kind, count }) => <button key={kind} className="co-secondary" aria-pressed={view === "attention" && issue === kind} onClick={() => { change(() => { setView("attention"); setIssue(kind); setQuery(""); setDataStatus(""); }); jumpToResults(); }}><span>{count}</span>{issueLabels[kind]}<ChevronRight size={15} /></button>)}{!summary.attention && summary.summary > 0 && <span className="ov-summary-note"><Clock3 size={16} />{summary.summary} with period summaries</span>}</div>
      </section>
      <section className="ov-directory" ref={rosterRef} tabIndex={-1} aria-labelledby="ov-directory-title">
        <div className="ov-directory-heading"><h2 id="ov-directory-title">Your workforce</h2><span>{teamName} · {summary.total} {summary.total === 1 ? "employee" : "employees"}</span></div>
        <div className="ov-views" role="group" aria-label="Workforce views">{(["all", "attention", "teams", "paused"] as const).map(item => <button key={item} data-testid={`view-${item}`} aria-pressed={view === item} onClick={() => showView(item)}>{viewLabels[item]}<span>{item === "all" ? summary.total : item === "attention" ? summary.attention : item === "paused" ? summary.paused : groupTeams(scoped, snapshot.teams, snapshot.server_time).filter(group => group.people.length).length}</span></button>)}</div>
        <div className="ov-tools"><label className="ov-search"><span>Find a person or team</span><div><Search size={17} /><input type="search" aria-label="Search team members" placeholder="Search by name or team" value={query} onChange={event => change(() => setQuery(event.target.value))} />{query && <button className="co-icon" aria-label="Clear search" onClick={() => change(() => setQuery(""))}><X size={16} /></button>}</div></label><label>Data status<select aria-label="Filter by data status" value={dataStatus} onChange={event => change(() => setDataStatus(event.target.value))}><option value="">All data statuses</option>{Object.entries(dataStatusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>{view !== "teams" && <label>Sort by<select aria-label="Sort team members" value={sort} onChange={event => change(() => setSort(event.target.value as typeof sort))}><option value="attention">Connection issues first</option><option value="name">Name A–Z</option><option value="name_desc">Name Z–A</option><option value="recent">Most recently received</option><option value="oldest">Least recently received</option></select></label>}</div>
        <div className="ov-results-context"><span aria-live="polite">{view === "teams" ? `${groups.length} teams` : `${filtered.length} ${filtered.length === 1 ? "employee" : "employees"}`}{view !== "all" && <> · {viewLabels[view]}</>}{issue && <> · {issueLabels[issue]}</>}{query && <> · “{query}”</>}{dataStatus && <> · {dataStatusLabels[dataStatus as keyof typeof dataStatusLabels]}</>}</span>{hasFilters && <button className="co-text" onClick={resetFilters}><X size={14} />Clear filters</button>}</div>
        {!filtered.length ? <div className="ov-empty"><Search size={26} /><h3>{view === "attention" && !query && !dataStatus && !issue ? "No connections need help" : "No matching employees"}</h3><p>{view === "attention" ? "Choose All employees to see the rest of your team." : "Change the search or clear your filters to see more people."}</p><button className="co-secondary" onClick={resetFilters}>Show all employees<ArrowRight size={16} /></button></div> : view === "teams" ? <div className="ov-table-scroll" ref={scrollRef}><table className="ov-team-table"><caption className="sr-only">Team connection coverage. Counts refer to the employees matching your filters.</caption><thead><tr><th>Team</th><th>Employees</th><th>Recent wearable data</th><th>Connection help</th><th>Sharing paused</th><th><span className="sr-only">Actions</span></th></tr></thead><tbody>{teamPage.items.map(group => <tr key={group.id} data-testid={`team-summary-${group.id}`}><th scope="row"><strong>{group.name}</strong><small>{group.summary.summary} with period summaries</small></th><td data-label="Employees">{group.summary.total}</td><td data-label="Recent wearable data"><span>{group.summary.currentWearable} / {group.summary.total}</span><div className="ov-coverage" aria-hidden="true"><i style={{ width: `${group.summary.total ? group.summary.currentWearable / group.summary.total * 100 : 0}%` }} /></div></td><td data-label="Connection help"><span className={group.summary.attention ? "ov-issue-count" : ""}>{group.summary.attention}</span></td><td data-label="Sharing paused">{group.summary.paused}</td><td><button className="co-secondary" aria-label={`View team ${group.name}`} onClick={() => change(() => { setTeam(group.id || "unassigned"); setView("all"); setIssue(""); setQuery(""); setDataStatus(""); })}>View team<ArrowRight size={15} /></button></td></tr>)}</tbody></table></div> : <div className="ov-table-scroll" ref={scrollRef}><table className="ov-people-table"><caption className="sr-only">Employees, connection issues and next steps. These are data availability indicators, not health assessments.</caption><thead><tr><th scope="col">Employee</th><th scope="col">Data status</th><th scope="col">Next step</th><th scope="col">Last received</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead><tbody>{page.items.map(member => {
          const status = personDataStatus(member), received = lastReceived(member), item = attention.get(member.id)!;
          return <tr key={member.id} className={`co-roster-row ${item.priority > 0 ? "ov-row-attention" : ""}`} data-testid={`company-person-${member.id}`}><th scope="row"><strong>{member.name}</strong><small>{teamNames.get(member.team_id ?? "") ?? "Unassigned"}</small>{personSource(member).includes("RECORDING") && <span className="ov-recording">DEMO RECORDING</span>}</th><td data-label="Data status"><span className={`ov-status ${status}`}>{status === "paused" ? <Pause size={14} /> : status === "current" ? <Radio size={14} /> : <Clock3 size={14} />}{dataStatusLabels[status]}</span>{item.priority > 0 && <small className="ov-issue-text">{item.label}</small>}{item.issueCount > 1 && item.priority > 0 && <small>{item.issueCount} data issues</small>}</td><td data-label="Next step" className="ov-next-step">{status === "paused" ? "No action. Sharing is the employee’s choice." : item.kind ? item.nextStep : status === "summary" ? "No action. This device sends period summaries." : "No connection action needed."}</td><td data-label="Last received">{received ? <time dateTime={new Date(received * 1000).toISOString()} title={new Date(received * 1000).toLocaleString("en-US")}>{receivedLabel(received, snapshot.server_time)}</time> : status === "paused" ? "Hidden while paused" : "Not received yet"}</td><td className="ov-row-actions"><button className="co-secondary" aria-label={`View signals for ${member.name}`} onClick={event => { trigger.current = event.currentTarget; setSelected(member.id); }}>View signals<ArrowRight size={15} /></button>{canManage && item.kind === "setup" && !member.signals?.length && !member.latest && <button className="co-text" aria-label={`Set up phone for ${member.name}`} onClick={() => openPeople(member.id)}><Smartphone size={14} />Set up phone</button>}</td></tr>;
        })}</tbody></table></div>}
        <RosterPagination {...activePage} label={view === "teams" ? "Teams" : "Team members"} itemLabel={view === "teams" ? "teams" : "people"} onPage={next => { setPageIndex(next); setSelected(""); if (scrollRef.current) scrollRef.current.scrollTop = 0; }} onSize={size => change(() => setPageSize(size))} />
        <details className="ov-data-guide"><summary><CircleHelp size={16} />What do these statuses mean?</summary><div><p><strong>Current:</strong> at least one recent measurement. Other signals may still need attention.</p><p><strong>Period summary:</strong> a daily or periodic report, rather than a live reading.</p><p><strong>Sharing paused:</strong> the employee has chosen not to share. Measurements are hidden.</p><p><strong>Connection help:</strong> a signal stopped arriving, a permission is missing, or setup is incomplete. It does not describe a person’s health.</p></div></details>
      </section>
    </>}
    {person && <EmployeeSignalDetail key={person.id} person={person} snapshot={snapshot} org={org} canManage={canManage} openPeople={openPeople} api={api} onClose={closeDetails} />}
  </div>;
}
