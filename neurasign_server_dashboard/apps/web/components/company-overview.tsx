"use client";

import { useEffect, useState } from "react";
import { Activity, ArrowRight, Bluetooth, ChevronRight, CircleHelp, HeartPulse, History, Plus, Radio, Search, ShieldCheck, Smartphone, Users } from "lucide-react";
import { Chart } from "./monitoring-dashboard";
import { SignalExplorer, SignalTiles } from "./company-signals";
import type { Features, Member, Reading, Snapshot } from "./company-workspace";

const metrics = {
  heart_rate: { name: "Heart rate", short: "HR", unit: "bpm", digits: 0, meaning: "Heartbeats per minute, summarized over the device’s measurement window.", color: "#107c68" },
  hrv: { name: "Heart rate variability", short: "HRV", unit: "ms", digits: 1, meaning: "Variation between successive beat intervals, reported as RMSSD. It requires interval data; heart rate alone is insufficient.", color: "#7b61b7" },
  eda: { name: "Skin conductance", short: "EDA", unit: "µS", digits: 2, meaning: "Skin conductance varies with sweat-gland activity. It cannot identify an emotion or its cause.", color: "#287ea4" },
  temperature: { name: "Skin temperature", short: "Skin temp", unit: "°C", digits: 1, meaning: "Temperature at the sensor’s contact point, not core body temperature.", color: "#b87929" },
  movement: { name: "Movement", short: "Movement", unit: "g", digits: 3, meaning: "Variability of acceleration magnitude within the measurement window. This is not a step count.", color: "#566d9c" },
};
const format = (value: number | null | undefined, digits = 0) => value == null ? "—" : value.toLocaleString("en-US", { maximumFractionDigits: digits });
const timeLabel = (value: number) => new Date(value * 1000).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
const stateLabel = (status: Member["status"]) => ({ paused: "Sharing paused", waiting: "Awaiting data", current: "Current", stale: "No recent data" }[status]);
const isCurrentWearable = (person: Member) => (person.status === "current" && person.latest?.source === "wearable") || person.signals?.some(signal => signal.status === "current" && signal.source === "wearable");

export function CompanyOverview({ snapshot, org, canManage, openPeople, demoAvailable, api }: {
  snapshot: Snapshot; org: string; canManage: boolean; openPeople: () => void; demoAvailable: boolean;
  api: <T>(path: string) => Promise<T>;
}) {
  const [selected, setSelected] = useState("");
  const [query, setQuery] = useState("");
  const [team, setTeam] = useState("");
  const [metric, setMetric] = useState<keyof Features>("heart_rate");
  const [history, setHistory] = useState<{ scope: string; rows: Reading[]; error: boolean } | null>(null);
  const visible = snapshot.members.filter(member => (!team || member.team_id === team) && member.name.toLowerCase().includes(query.toLowerCase().trim()));
  const person = visible.find(member => member.id === selected) ?? visible[0];
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
  const current = snapshot.members.filter(isCurrentWearable).length;
  const connected = snapshot.devices.filter(device => !device.revoked).length;
  const awaiting = snapshot.members.filter(member => member.sharing && member.status !== "current" && !member.signals?.some(signal => signal.status === "current")).length;
  const hasReadings = snapshot.members.some(member => member.latest || member.signals?.some(signal => signal.latest));
  const meta = metrics[metric];
  return <>
    <div className="co-stat-grid" aria-label="Workspace summary">
      <div className="co-stat-card"><span><Users size={17} />Team members</span><strong>{snapshot.members.length}<small>in this workspace</small></strong><div>{snapshot.teams.length} {snapshot.teams.length === 1 ? "team" : "teams"}</div></div>
      <div className="co-stat-card co-stat-live"><span><Radio size={17} />Receiving wearable data</span><strong>{current}<small>of {snapshot.members.length} {snapshot.members.length === 1 ? "person" : "people"}</small></strong><div>{current > 0 && <i />}{current ? "Recent measurements" : "No recent wearable data"}</div></div>
      <div className="co-stat-card"><span><Smartphone size={17} />Authorized connections</span><strong>{connected}<small>{connected === 1 ? "gateway" : "gateways"}</small></strong><div>Phone and device access</div></div>
      <div className="co-stat-card"><span><History size={17} />Awaiting readings</span><strong>{awaiting}<small>sharing enabled</small></strong><div>{snapshot.organization.retention_days}-day history retention</div></div>
    </div>
    {!hasReadings && <section className="co-onboarding co-panel">
      <div className="co-onboarding-intro"><span className="co-onboarding-icon"><Bluetooth size={25} /></span><div><span className="co-eyebrow">LET’S GET CONNECTED</span><h2>{snapshot.members.length ? "Your workspace is ready for its first signals" : "Connect your first employee"}</h2><p>Connect a wearable through the phone app to start seeing measurements here.</p></div></div>
      <div className="co-setup-steps"><div><span>1</span><strong>Create a team</strong><small>Organize your people</small></div><ChevronRight size={17} /><div><span>2</span><strong>Add an employee</strong><small>No employee account needed</small></div><ChevronRight size={17} /><div><span>3</span><strong>Connect their phone</strong><small>Scan the code in NEURASIGN Link</small></div></div>
      <div className="co-onboarding-actions">{canManage && <button className="co-primary" onClick={openPeople}><Plus size={16} />Set up your team</button>}{demoAvailable && <a className="co-text" href="/demo">Preview with recorded data<ArrowRight size={15} /></a>}</div>
    </section>}
    {snapshot.members.length > 0 && <>
      <div className="co-roster-heading"><div><h2>Team members <span>{visible.length}</span></h2><p>Select a person to explore their signals.</p></div><div className="co-roster-tools"><label className="co-search"><Search size={16} /><input aria-label="Search team members" value={query} onChange={event => setQuery(event.target.value)} placeholder="Find a person…" /></label>{snapshot.teams.length > 0 && <select aria-label="Filter by team" value={team} onChange={event => setTeam(event.target.value)}><option value="">All teams</option>{snapshot.teams.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select>}</div></div>
      {!visible.length && <div className="co-panel co-no-results"><Search size={25} /><h3>No matching team members</h3><p>Try another name or team.</p><button className="co-secondary" onClick={() => { setQuery(""); setTeam(""); }}>Clear filters</button></div>}
      <div className="co-people-grid">{visible.map(member => <button key={member.id} className={`co-person ${person?.id === member.id ? "selected" : ""}`} aria-pressed={person?.id === member.id} data-testid={`company-person-${member.id}`} onClick={() => setSelected(member.id)}>
        <div className="co-person-head"><span className="co-avatar">{member.name.split(" ").map(part => part[0]).slice(0, 2).join("")}</span><div><h2>{member.name}</h2><small>{snapshot.teams.find(item => item.id === member.team_id)?.name ?? "Unassigned team"}</small></div><span className={`co-status ${member.status}`}><i />{stateLabel(member.status)}</span></div>
        {member.signals?.length ? <SignalTiles signals={member.signals} catalog={snapshot.metric_catalog ?? []} /> : member.latest ? <div className="co-readings">{(["heart_rate", "hrv", "eda", "temperature"] as (keyof Features)[]).map(key => <div key={key}><small>{metrics[key].short}</small><strong style={{ color: metrics[key].color }}>{format(member.features[key], metrics[key].digits)}<em>{metrics[key].unit}</em></strong></div>)}</div> : <div className="co-person-waiting"><Activity size={20} /><span>{member.sharing ? "Ready for a first measurement" : "No signals shared yet"}<small>{member.sharing ? "Connect their phone to begin." : "Sharing is controlled from their phone."}</small></span></div>}
        <footer><span>{member.latest?.source === "recording" ? "DEMO RECORDING · " : ""}{member.signals?.length ? "View signal details" : member.latest ? `Measured ${timeLabel(member.latest.timestamp)}` : member.sharing ? "Waiting for an authorized device" : "Employee controls sharing"}</span><span>{person?.id === member.id ? "Selected" : "View"}<ChevronRight size={14} /></span></footer>
      </button>)}</div>
    </>}
    {person?.signals?.length ? <SignalExplorer key={`${org}:${person.id}`} personId={person.id} name={person.name} org={org} signals={person.signals} catalog={snapshot.metric_catalog ?? []} revision={snapshot.server_time} api={api} /> : null}
    {person?.latest && <section className="co-panel">
      <div className="co-panel-head"><div><h2>Signal detail · {person.name}</h2><p>{person.latest.source === "recording" ? "Demo recording" : "Device measurements"} · {person.latest.window_seconds}-second window</p></div><span className={`co-status ${person.status}`}>{stateLabel(person.status)}</span></div>
      <div className="co-metric-tabs">{(Object.keys(metrics) as (keyof Features)[]).map(key => <button key={key} className={metric === key ? "active" : ""} aria-pressed={metric === key} onClick={() => setMetric(key)}>{metrics[key].short}</button>)}</div>
      <div className="co-chart-value"><HeartPulse size={21} /><strong>{format(person.features[metric], meta.digits)}</strong><span>{meta.unit}</span><details><summary><CircleHelp size={15} />{meta.name}</summary><p>{meta.meaning}</p></details></div>
      {history?.scope === scope && history.error ? <p className="co-history-error" role="status">History is temporarily unavailable.</p> : <Chart live unit={meta.unit} series={[{ label: person.name, color: meta.color, points: rows.flatMap((row, index) => {
        const previous = rows[index - 1];
        const point = { time: row.timestamp, value: row.features[metric] };
        return previous && row.timestamp - previous.timestamp > Math.max(row.window_seconds, previous.window_seconds) * 2 ? [{ time: previous.timestamp + 1, value: null }, point] : [point];
      }) }]} />}
      <footer className="co-panel-foot"><span>Measured time · gaps mean missing readings</span><span>{person.latest.quality == null ? "Quality not reported" : `Reported quality ${format(person.latest.quality * 100)}%`}</span></footer>
    </section>}
    <div className="co-note"><ShieldCheck size={16} /><span>Wearable measurements, with source and freshness. Mental-state estimates remain experimental.</span></div>
  </>;
}
