"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Activity, ArrowRight, Bluetooth, ChevronRight, CircleHelp, HeartPulse, History, Plus, Radio, Search, ShieldCheck, Smartphone, Users } from "lucide-react";
import { Chart } from "./monitoring-dashboard";
import { SignalExplorer, SignalTiles } from "./company-signals";
import { RosterPagination } from "./roster-pagination";
import { dataStatusLabels, hasCurrentWearable, lastReceived, legacyDataStatus, personDataStatus, personSource, rosterPage, selectRoster, type RosterSort } from "@/lib/company-roster";
import type { Features, Member, Reading, Snapshot } from "./company-workspace";

const metrics = {
  heart_rate: { name: "Heart rate", short: "HR", unit: "bpm", digits: 0, meaning: "Heartbeats per minute, summarized over the device’s measurement window.", color: "var(--accent)" },
  hrv: { name: "Heart rate variability", short: "HRV", unit: "ms", digits: 1, meaning: "Variation between successive beat intervals, reported as RMSSD. It requires interval data; heart rate alone is insufficient.", color: "var(--accent)" },
  eda: { name: "Skin conductance", short: "EDA", unit: "µS", digits: 2, meaning: "Skin conductance varies with sweat-gland activity. It cannot identify an emotion or its cause.", color: "var(--accent)" },
  temperature: { name: "Skin temperature", short: "Skin temp", unit: "°C", digits: 1, meaning: "Temperature at the sensor’s contact point, not core body temperature.", color: "var(--accent)" },
  movement: { name: "Movement", short: "Movement", unit: "g", digits: 3, meaning: "Variability of acceleration magnitude within the measurement window. This is not a step count.", color: "var(--accent)" },
};
const format = (value: number | null | undefined, digits = 0) => value == null ? "—" : value.toLocaleString("en-US", { maximumFractionDigits: digits });
const timeLabel = (value: number) => new Date(value * 1000).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
const stateLabel = (status: Member["status"]) => ({ paused: "Sharing paused", waiting: "Awaiting data", current: "Current", stale: "No recent data" }[status]);

export function CompanyOverview({ snapshot, org, canManage, openPeople, demoAvailable, api }: {
  snapshot: Snapshot; org: string; canManage: boolean; openPeople: () => void; demoAvailable: boolean;
  api: <T>(path: string) => Promise<T>;
}) {
  const [selected, setSelected] = useState("");
  const [query, setQuery] = useState("");
  const [team, setTeam] = useState("");
  const [dataStatus, setDataStatus] = useState("");
  const [sort, setSort] = useState<RosterSort>("name");
  const [pageIndex, setPageIndex] = useState(0);
  const [pageSize, setPageSize] = useState(25);
  const detailRef = useRef<HTMLElement>(null);
  const rosterRef = useRef<HTMLElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const selectionTrigger = useRef<HTMLButtonElement | null>(null);
  const [metric, setMetric] = useState<keyof Features>("heart_rate");
  const [history, setHistory] = useState<{ scope: string; rows: Reading[]; error: boolean } | null>(null);
  const members = useMemo(() => {
    const arrivals = new Map<string, number>();
    for (const device of snapshot.devices) if (device.last_received_at && Number.isFinite(device.last_received_at)) arrivals.set(device.member_id, Math.max(arrivals.get(device.member_id) ?? 0, device.last_received_at));
    return snapshot.members.map(member => ({ ...member, last_received_at: arrivals.get(member.id) ?? null }));
  }, [snapshot.members, snapshot.devices]);
  const visible = useMemo(() => selectRoster(members, snapshot.teams, { query, team, status: dataStatus, sort }), [members, snapshot.teams, query, team, dataStatus, sort]);
  const page = rosterPage(visible, pageIndex, pageSize);
  const person = visible.find(member => member.id === selected);
  useEffect(() => { if (selected && !person) setSelected(""); }, [selected, person]);
  useEffect(() => { if (pageIndex !== page.page) setPageIndex(page.page); }, [page.page, pageIndex]);
  function changeFilters(update: () => void) { update(); setPageIndex(0); setSelected(""); }
  function changePage(next: number) { setPageIndex(next); setSelected(""); if (scrollRef.current) scrollRef.current.scrollTop = 0; }
  function choosePerson(id: string, trigger: HTMLButtonElement) {
    selectionTrigger.current = trigger; setSelected(id);
    requestAnimationFrame(() => {
      detailRef.current?.focus({ preventScroll: true });
      const bounds = detailRef.current?.getBoundingClientRect();
      if (bounds && (bounds.top < 0 || bounds.top > window.innerHeight - 150)) detailRef.current?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "start" });
    });
  }
  function backToRoster() {
    const target = selectionTrigger.current?.isConnected ? selectionTrigger.current : rosterRef.current;
    target?.focus({ preventScroll: true }); target?.scrollIntoView({ behavior: "instant", block: "nearest" });
  }
  const scope = `${org}/${person?.id}`;
  const legacyHistory = Boolean(person?.latest) && person?.status !== "paused";
  useEffect(() => {
    let active = true;
    if (!person || !legacyHistory) return;
    api<{ readings: Reading[] }>(`/organizations/${org}/members/${person.id}/history`)
      .then(value => { if (active) setHistory({ scope, rows: value.readings, error: false }); })
      .catch(() => { if (active) setHistory({ scope, rows: [], error: true }); });
    return () => { active = false; };
  }, [api, org, person?.id, legacyHistory, scope, snapshot.server_time]);
  const rows = legacyHistory && history?.scope === scope ? history.rows : [];
  const current = snapshot.members.filter(member => hasCurrentWearable(member, snapshot.server_time)).length;
  const connected = snapshot.devices.filter(device => !device.revoked).length;
  const awaiting = snapshot.members.filter(member => member.sharing && member.status !== "current" && !member.signals?.some(signal => signal.status === "current")).length;
  const hasReadings = snapshot.members.some(member => member.latest || member.signals?.some(signal => signal.latest));
  const meta = metrics[metric];
  return <>
    <div className="co-stat-grid" aria-label="Workspace summary">
      <div className="co-stat-card"><span><Users size={17} />People</span><strong>{snapshot.members.length}<small>in this workspace</small></strong><div>{snapshot.teams.length} {snapshot.teams.length === 1 ? "team" : "teams"}</div></div>
      <div className="co-stat-card co-stat-live"><span><Radio size={17} />Receiving signals</span><strong>{current}<small>of {snapshot.members.length} {snapshot.members.length === 1 ? "person" : "people"}</small></strong><div>{current > 0 && <i />}{current ? "Recent measurements" : "No recent wearable data"}</div></div>
      <div className="co-stat-card"><span><Smartphone size={17} />Connections</span><strong>{connected}<small>{connected === 1 ? "gateway" : "gateways"}</small></strong><div>Phone and device access</div></div>
      <div className="co-stat-card"><span><History size={17} />Awaiting data</span><strong>{awaiting}<small>sharing enabled</small></strong><div>{snapshot.organization.retention_days}-day history retention</div></div>
    </div>
    {!hasReadings && <section className="co-onboarding co-panel">
      <div className="co-onboarding-intro"><span className="co-onboarding-icon"><Bluetooth size={25} /></span><div><span className="co-eyebrow">LET’S GET CONNECTED</span><h2>{snapshot.members.length ? "Ready for your first signal." : "Start with your people."}</h2><p>Add your team. Connect a phone. See the signals arrive.</p></div></div>
      <div className="co-setup-steps"><div><span>1</span><strong>Create a team</strong><small>Organize your people</small></div><ChevronRight size={17} /><div><span>2</span><strong>Add an employee</strong><small>No employee account needed</small></div><ChevronRight size={17} /><div><span>3</span><strong>Connect their phone</strong><small>Scan the code in NEURASIGN Link</small></div></div>
      <div className="co-onboarding-actions">{canManage && <button className="co-primary" onClick={openPeople}><Plus size={16} />Set up your team</button>}{demoAvailable && <a className="co-text" href="/demo">Preview with recorded data<ArrowRight size={15} /></a>}</div>
    </section>}
    {snapshot.members.length > 0 && <div className="co-team-browser">
      <section className="co-roster-browser" ref={rosterRef} tabIndex={-1} aria-labelledby="co-roster-title">
        <div className="co-roster-heading"><div><h2 id="co-roster-title">Team members <span>{snapshot.members.length}</span></h2><p>Find a person, then choose View signals.</p></div></div>
        <div className="co-roster-filters">
          <label className="co-filter-search">Find a person or team<input type="search" aria-label="Search team members" value={query} onChange={event => changeFilters(() => setQuery(event.target.value))} placeholder="Name or team" /></label>
          <label>Team<select aria-label="Filter by team" value={team} onChange={event => changeFilters(() => setTeam(event.target.value))}><option value="">All teams</option><option value="unassigned">Unassigned</option>{snapshot.teams.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          <label>Data status<select aria-label="Filter by data status" value={dataStatus} onChange={event => changeFilters(() => setDataStatus(event.target.value))}><option value="">All data statuses</option>{Object.entries(dataStatusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label>Sort by<select aria-label="Sort team members" value={sort} onChange={event => changeFilters(() => setSort(event.target.value as RosterSort))}><option value="name">Name A–Z</option><option value="name_desc">Name Z–A</option><option value="recent">Most recently received</option><option value="oldest">Least recently received</option></select></label>
          {(query || team || dataStatus) && <button className="co-secondary co-clear-filters" onClick={() => changeFilters(() => { setQuery(""); setTeam(""); setDataStatus(""); })}>Clear filters</button>}
        </div>
        {!visible.length ? <div className="co-panel co-no-results"><h3>No matching team members</h3><p>Try another name, team or data status.</p></div> : <div className="co-roster-scroll" ref={scrollRef}>
          <table className="co-team-table"><caption className="co-sr-only">Team members and received data. Data status describes measurements, not a person’s condition.</caption><thead><tr><th scope="col">Person</th><th scope="col">Team</th><th scope="col">Data status</th><th scope="col">Last received</th><th scope="col"><span className="co-sr-only">Actions</span></th></tr></thead><tbody>
            {page.items.map(member => {
              const status = personDataStatus(member), received = lastReceived(member);
              return <tr key={member.id} className={`co-roster-row${person?.id === member.id ? " selected" : ""}`} data-testid={`company-person-${member.id}`}>
                <th scope="row"><strong>{member.name}</strong><small>{personSource(member)}</small></th>
                <td data-label="Team">{snapshot.teams.find(item => item.id === member.team_id)?.name ?? "Unassigned"}</td>
                <td data-label="Data status"><span className={`co-data-status ${status}`}><i />{dataStatusLabels[status]}</span></td>
                <td data-label="Last received">{received ? <time dateTime={new Date(received * 1000).toISOString()} title={new Date(received * 1000).toLocaleString("en-US")}>{new Date(received * 1000).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</time> : status === "paused" ? "Hidden while paused" : "No data received"}</td>
                <td className="co-roster-action"><button className="co-secondary" aria-label={`View signals for ${member.name}`} aria-pressed={person?.id === member.id} onClick={event => choosePerson(member.id, event.currentTarget)}>View signals<ArrowRight size={16} /></button></td>
              </tr>;
            })}
          </tbody></table>
        </div>}
        <RosterPagination {...page} label="Team members" onPage={changePage} onSize={size => { setPageSize(size); changePage(0); }} />
        <p className="co-roster-explanation">Data status shows whether measurements are current. It does not describe how a person feels.</p>
      </section>
      <section className="co-selected-detail" ref={detailRef} tabIndex={-1} aria-label={person ? `Signals for ${person.name}` : "Selected person signals"} data-testid="company-selected-signals">
        {!person ? <div className="co-detail-placeholder"><h2>View one person’s signals</h2><p>Choose <strong>View signals</strong> beside a name. Measurements and their source appear here.</p></div> : <>
          <div className="co-selected-heading"><div><span>SELECTED PERSON</span><h2>{person.name}</h2><p>{snapshot.teams.find(item => item.id === person.team_id)?.name ?? "Unassigned team"} · {dataStatusLabels[personDataStatus(person)]}</p></div><button className="co-secondary" onClick={backToRoster}>Back to list</button></div>
          {personDataStatus(person) === "paused" ? <div className="co-detail-placeholder"><h3>Sharing is paused</h3><p>Measurements stay hidden until this person enables sharing from their phone.</p></div> : <>
            {person.signals?.length ? <SignalTiles signals={person.signals} catalog={snapshot.metric_catalog ?? []} /> : person.latest ? <div className="co-readings">{(["heart_rate", "hrv", "eda", "temperature"] as (keyof Features)[]).map(key => <div key={key}><small>{metrics[key].name}</small><strong>{format(person.features[key], metrics[key].digits)}<em>{metrics[key].unit}</em></strong></div>)}</div> : <div className="co-detail-placeholder"><h3>No measurements yet</h3><p>Connect this person’s phone and enable sharing to receive data.</p>{canManage && <button className="co-secondary" onClick={openPeople}>Open People &amp; teams<ArrowRight size={16} /></button>}</div>}
    {person?.signals?.length ? <SignalExplorer key={`${org}:${person.id}`} personId={person.id} name={person.name} org={org} signals={person.signals} catalog={snapshot.metric_catalog ?? []} revision={snapshot.server_time} api={api} /> : null}
    {person?.latest && <section className="co-panel">
      <div className="co-panel-head"><div><h2>Signal detail · {person.name}</h2><p>{person.latest.source === "recording" ? "Demo recording" : "Device measurements"} · {person.latest.window_seconds}-second window</p></div><span className={`co-status ${legacyDataStatus(person, snapshot.server_time)}`}>{dataStatusLabels[legacyDataStatus(person, snapshot.server_time)]}</span></div>
      <div className="co-metric-tabs">{(Object.keys(metrics) as (keyof Features)[]).map(key => <button key={key} className={metric === key ? "active" : ""} aria-pressed={metric === key} onClick={() => setMetric(key)}>{metrics[key].short}</button>)}</div>
      <div className="co-chart-value"><HeartPulse size={21} /><strong>{format(person.features[metric], meta.digits)}</strong><span>{meta.unit}</span><details><summary><CircleHelp size={15} />{meta.name}</summary><p>{meta.meaning}</p></details></div>
      {history?.scope === scope && history.error ? <p className="co-history-error" role="status">History is temporarily unavailable.</p> : <Chart live unit={meta.unit} series={[{ label: person.name, color: meta.color, points: rows.flatMap((row, index) => {
        const previous = rows[index - 1];
        const point = { time: row.timestamp, value: row.features[metric] };
        return previous && row.timestamp - previous.timestamp > Math.max(row.window_seconds, previous.window_seconds) * 2 ? [{ time: previous.timestamp + 1, value: null }, point] : [point];
      }) }]} />}
      <footer className="co-panel-foot"><span>Measured time · gaps mean missing readings</span><span>{person.latest.quality == null ? "Quality not reported" : `Reported quality ${format(person.latest.quality * 100)}%`}</span></footer>
    </section>}
          </>}
        </>}
      </section>
    </div>}
    <div className="co-note"><ShieldCheck size={16} /><span>Received measurements only. Source and freshness stay visible.</span></div>
  </>;
}
