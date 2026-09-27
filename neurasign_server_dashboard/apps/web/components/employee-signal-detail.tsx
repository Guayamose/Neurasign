"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, CircleHelp, HeartPulse, ShieldCheck, X } from "lucide-react";
import { Chart } from "./monitoring-dashboard";
import { SignalExplorer, SignalTiles } from "./company-signals";
import { dataStatusLabels, legacyDataStatus, personDataStatus, personSource } from "@/lib/company-roster";
import { classifyAttention } from "@/lib/team-attention";
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

export function EmployeeSignalDetail({ person, snapshot, org, canManage, openPeople, api, onClose }: {
  person: Member; snapshot: Snapshot; org: string; canManage: boolean;
  openPeople: (id?: string) => void; onClose: () => void;
  api: <T>(path: string) => Promise<T>;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [metric, setMetric] = useState<keyof Features>("heart_rate");
  const [history, setHistory] = useState<{ scope: string; rows: Reading[]; error: boolean } | null>(null);
  const status = personDataStatus(person);
  const attention = classifyAttention(person, snapshot.server_time);
  const scope = `${org}/${person.id}`;
  const legacyHistory = Boolean(person.latest) && status !== "paused";
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    element?.focus();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { element?.close(); document.body.style.overflow = overflow; };
  }, []);
  useEffect(() => {
    let active = true;
    if (!legacyHistory) return;
    api<{ readings: Reading[] }>(`/organizations/${org}/members/${person.id}/history`)
      .then(value => { if (active) setHistory({ scope, rows: value.readings, error: false }); })
      .catch(() => { if (active) setHistory({ scope, rows: [], error: true }); });
    return () => { active = false; };
  }, [api, org, person.id, legacyHistory, scope, snapshot.server_time]);
  const rows = legacyHistory && history?.scope === scope ? history.rows : [];
  const meta = metrics[metric];
  return <dialog className="co-person-dialog" ref={dialog} tabIndex={-1} aria-labelledby="employee-detail-name" data-testid="company-selected-signals" onCancel={event => { event.preventDefault(); onClose(); }} onClick={event => {
    if (event.target !== event.currentTarget) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) onClose();
  }}>
    <header className="ov-detail-header"><button className="co-secondary" onClick={onClose}><ArrowLeft size={16} />Back to list</button><button className="co-icon" onClick={onClose} aria-label="Close employee details"><X size={21} /></button></header>
    <div className="ov-detail-title"><span>Employee measurements</span><h2 id="employee-detail-name">{person.name}</h2><p>{snapshot.teams.find(item => item.id === person.team_id)?.name ?? "Unassigned team"} · {dataStatusLabels[status]}</p><small>{personSource(person)}</small></div>
    {status === "paused" ? <div className="ov-detail-notice"><ShieldCheck size={24} /><h3>Sharing is paused</h3><p>Measurements stay hidden. The employee decides when to resume sharing from their phone.</p></div> : <>
      {attention.kind && <div className="ov-detail-notice"><h3>{attention.label}</h3><p>{attention.nextStep}</p>{canManage && attention.kind === "setup" && !person.signals?.length && !person.latest && <button className="co-secondary" onClick={() => { onClose(); openPeople(person.id); }}>Open phone setup<ArrowRight size={16} /></button>}</div>}
      {person.signals?.length ? <SignalTiles signals={person.signals} catalog={snapshot.metric_catalog ?? []} /> : person.latest ? <div className="co-readings">{(["heart_rate", "hrv", "eda", "temperature"] as (keyof Features)[]).map(key => <div key={key}><small>{metrics[key].name}</small><strong>{format(person.features[key], metrics[key].digits)}<em>{metrics[key].unit}</em></strong></div>)}</div> : !attention.kind ? <div className="ov-detail-notice"><h3>No measurements yet</h3><p>Connect a phone and enable sharing to receive measurements.</p></div> : null}
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
    <p className="ov-detail-foot">Measurements and connection status do not establish how someone feels.</p>
  </dialog>;
}
