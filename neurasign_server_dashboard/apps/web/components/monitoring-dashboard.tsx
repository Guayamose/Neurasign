"use client";

import { useState, useRef, useEffect } from "react";
import { Activity, ArrowLeft, ArrowRight, CalendarClock, ChartNoAxesCombined, Check, ChevronDown, ChevronRight, Clock3, Coffee, Cpu, Download, HeartPulse, Layers3, LoaderCircle, LockKeyhole, Move, Pause, Play, Radio, RotateCcw, ShieldCheck, Sparkles, Thermometer, Users, Waves, Zap } from "lucide-react";
import IncidentStory from "./incident-story";
import { Brand } from "./brand";
import ManagerOverview from "./manager-overview";
import { toManagerView } from "@/lib/manager-preview";
import { MetricHelp, MetricHelpProvider, metricDefinitions } from "./metric-info";
import { useDashboard } from "@/lib/use-dashboard";
import type { Mode, MonitoringWorker, PhysiologicalFeature, Snapshot, StateField, Worker } from "@/lib/types";

type Tab = "monitoring" | "manager" | "wellbeing" | "focus" | "incidents";
type Point = { time: number; value: number | null };
type Series = { label: string; color: string; points: Point[] };
const featureInfo = {
  heart_rate: { label: "Heart rate", short: "HR", unit: "bpm", digits: 0, color: "var(--accent)", Icon: HeartPulse },
  hrv: { label: "HRV", short: "HRV", unit: "ms", digits: 1, color: "var(--accent)", Icon: Activity },
  eda: { label: "Skin conductance", short: "EDA", unit: "µS", digits: 2, color: "var(--accent)", Icon: Waves },
  temperature: { label: "Skin temp", short: "Skin temp", unit: "°C", digits: 1, color: "var(--accent)", Icon: Thermometer },
  movement: { label: "Motion variability", short: "Movement", unit: "g", digits: 3, color: "var(--accent)", Icon: Move },
};
const primaryFeatures: PhysiologicalFeature[] = ["heart_rate", "hrv", "eda", "temperature"];
const stateLabels: Record<StateField, string> = { cognitive_load: "Workload", readiness: "Readiness", fatigue: "Fatigue", interruption_cost: "Interruption cost" };
const workerColors: Record<string, string> = { alex: "var(--accent)", aoi: "var(--ink)" };
const number = (value: number | null | undefined, digits = 0) => {
  if (value == null || !Number.isFinite(value)) return "—";
  const rounded = Math.round(value * 10 ** digits) / 10 ** digits;
  return (Object.is(rounded, -0) ? 0 : rounded).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
};
const clock = (seconds: number, live = false) => live ? new Date(seconds * 1000).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : `${Math.floor(seconds / 60).toString().padStart(2, "0")}:${Math.floor(seconds % 60).toString().padStart(2, "0")}`;
const sourceLabel = (state: Snapshot) => state.mode === "manual" ? "Manual controls" : state.mode === "live" ? "Live device" : state.source.kind === "universe" ? "UNIVERSE · recorded" : "Illustrative signals";
const available = (worker: Worker, signal?: MonitoringWorker) => signal?.status === "manual" || !!signal && !["waiting", "stale"].includes(signal.status) && worker.cognitive_state.confidence >= .25;
const statusText = (_worker: Worker, signal?: MonitoringWorker) => !signal || signal.status === "waiting" ? "Waiting for data" : signal.status === "stale" ? "No recent data" : signal.status === "manual" ? "Manual indices" : signal.status === "recorded" ? "Recorded signals" : signal.status === "synthetic" ? "Illustrative signals" : "Receiving signals";
const roleName = (role: string) => role;

export function Chart({ series, compact = false, baseline, live = false, unit = "", fixedRange, height = 195, timeCaption }: { timeCaption?: string; series: Series[]; compact?: boolean; baseline?: number | null; live?: boolean; unit?: string; fixedRange?: [number, number]; height?: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const [chartWidth, setChartWidth] = useState(740);
  const chartRef = useRef<HTMLDivElement>(null);
  const all = series.flatMap(s => s.points.filter(p => p.value != null && Number.isFinite(p.value)));
  const hasData = all.length > 0;
  useEffect(() => {
    const node = chartRef.current;
    if (!node || compact) return;
    const observer = new ResizeObserver(entries => setChartWidth(Math.max(250, entries[0].contentRect.width)));
    observer.observe(node);
    return () => observer.disconnect();
  }, [compact, hasData]);
  if (!all.length) return <div className={`chart-empty ${compact ? "" : "large"}`}>{compact ? "No signal" : <><Activity size={23} /><span>No samples yet.<br />Missing readings stay as gaps.</span></>}</div>;
  const width = compact ? 160 : chartWidth;
  const viewHeight = compact ? 42 : height;
  const left = compact ? 0 : 43, right = compact ? 0 : 12, top = compact ? 4 : 11, bottom = compact ? 3 : 29;
  const times = series.flatMap(s => s.points.map(p => p.time)), values = all.map(p => p.value as number);
  if (baseline != null) values.push(baseline);
  const minTime = Math.min(...times), maxTime = Math.max(...times);
  const ticks = minTime === maxTime ? [minTime] : width < 460 ? [minTime, maxTime] : [minTime, (minTime + maxTime) / 2, maxTime];
  const padding = Math.max((Math.max(...values) - Math.min(...values)) * .18, Math.max(Math.abs(values[0]) * .01, .01));
  const low = fixedRange?.[0] ?? Math.min(...values) - padding, high = fixedRange?.[1] ?? Math.max(...values) + padding;
  const x = (t: number) => left + (t - minTime) / Math.max(maxTime - minTime, 1) * (width - left - right);
  const y = (v: number) => top + (high - v) / (high - low) * (viewHeight - top - bottom);
  const digits = high - low < 1 ? 2 : high - low < 10 ? 1 : 0;
  const focused = hover == null ? null : all.reduce((closest, p) => Math.abs(p.time - hover) < Math.abs(closest.time - hover) ? p : closest, all[0]).time;
  const paths = (points: Point[]) => { const result: string[] = []; let current = ""; for (const p of points) { if (p.value == null || !Number.isFinite(p.value)) { if (current) result.push(current); current = ""; } else current += `${current ? "L" : "M"}${x(p.time).toFixed(2)},${y(p.value).toFixed(2)} `; } if (current) result.push(current); return result; };
  return <div className="data-chart" ref={chartRef}><svg viewBox={`0 0 ${width} ${viewHeight}`} role="img" aria-label={`${series.map(s => s.label).join(" and ")}. ${all.length} samples. ${clock(minTime, live) } to ${clock(maxTime, live)}.`} onPointerMove={compact ? undefined : e => { const box = e.currentTarget.getBoundingClientRect(); const position = (e.clientX - box.left) / box.width * width; setHover(minTime + (position - left) / (width - left - right) * (maxTime - minTime)); }} onPointerLeave={() => setHover(null)}>
    <title>{series.map(s => `${s.label}: ${number(s.points.filter(p => p.value != null).at(-1)?.value, digits)} ${unit}`).join(". ")}</title>
    {!compact && [0, .5, 1].map(fraction => { const value = low + (high - low) * fraction; return <g key={fraction}><line x1={left} x2={width - right} y1={y(value)} y2={y(value)} stroke="var(--line)" strokeDasharray="3 4" /><text x={left - 9} y={y(value) + 4} textAnchor="end">{number(value, digits)}</text></g>; })}
    {baseline != null && <line x1={left} x2={width - right} y1={y(baseline)} y2={y(baseline)} stroke="#B0BCD0" strokeDasharray="5 5" strokeWidth="1.2" />}
    {series.map(s => <g key={s.label}>{paths(s.points).map((path, i) => <path key={i} d={path} stroke={s.color} strokeWidth={compact ? 1.6 : 2} fill="none" strokeLinejoin="round" />)}{s.points.map((point, index) => point.value != null && (index === 0 || s.points[index - 1].value == null) && (index === s.points.length - 1 || s.points[index + 1].value == null) ? <circle key={index} cx={x(point.time)} cy={y(point.value)} r="3" fill={s.color} /> : null)}</g>)}
    {!compact && ticks.map((t, i) => <text key={i} x={x(t)} y={viewHeight - 6} textAnchor={i === 0 ? "start" : i === ticks.length - 1 ? "end" : "middle"}>{clock(t, live)}</text>)}
    {!compact && focused != null && <g><line x1={x(focused)} x2={x(focused)} y1={top} y2={viewHeight - bottom} stroke="#B0BCD0" strokeDasharray="3 3" />{series.map(s => { const p = s.points.find(p => p.time === focused); return p?.value != null ? <circle key={s.label} cx={x(focused)} cy={y(p.value)} r="4" fill={s.color} stroke="var(--bg)" strokeWidth="2" /> : null; })}</g>}
  </svg>{!compact && <div className="chart-caption"><div className="chart-legend">{series.map(s => <span key={s.label}><i style={{ background: s.color }} />{s.label}</span>)}{baseline != null && <span><i style={{ background: "#B0BCD0" }} />Personal reference</span>}</div><span className="chart-hover">{focused != null ? `${clock(focused, live)} · ${series.map(s => number(s.points.find(p => p.time === focused)?.value, digits)).join(" / ")} ${unit}` : timeCaption ?? (live ? "Device time" : "Recording time")}</span></div>}</div>;
}

function MonitorWorker({ worker, signal, selected, select, live }: { worker: Worker; signal?: MonitoringWorker; selected: boolean; select: () => void; live: boolean }) {
  const valid = available(worker, signal);
  const missing = !signal || ["waiting", "stale", "manual"].includes(signal.status);
  return <article className={`monitor-worker-card ${selected ? "selected" : ""}`} data-testid={`monitor-worker-${worker.id}`}>
    <div className="monitor-worker-header">
      <div className={`monitor-person-icon ${worker.id}`}>{worker.name[0]}</div>
      <div><h3>{worker.name}</h3><p>{roleName(worker.role)} <span className="profile-context">· Demo profile</span></p></div>
      <span className={`monitor-label ${missing ? "neutral" : ""}`}><span className={`quality-dot ${missing ? "low" : ""}`} />{statusText(worker, signal)}</span>
    </div>
    <div className="physiology-tiles">{primaryFeatures.map(key => {
      const info = featureInfo[key], Icon = info.Icon;
      return <div className="physiology-tile" key={key}>
        <span className="physiology-label"><Icon size={14} />{key === "heart_rate" ? "Heart rate" : key === "eda" ? "EDA" : info.short}<MetricHelp metric={key} suffix={worker.id === "alex" ? undefined : worker.id} /></span>
        <span className="metric-meaning">{metricDefinitions[key].short}</span>
        <div className="physiology-value">{number(signal?.features[key], info.digits)}<small>{info.unit}</small></div>
        <Chart compact live={live} series={[{ label: `${worker.name} · ${info.label}`, color: info.color, points: signal?.history.map(p => ({ time: p.time, value: p[key] })) ?? [] }]} />
      </div>;
    })}</div>
    <details className="worker-estimates"><summary><span>{signal?.status === "manual" ? "Manual values" : "Formula estimates"}<small>Unvalidated · 0–100</small></span><ChevronDown size={13} /></summary>
    <div className="inferred-state-row">{(["cognitive_load", "readiness", "fatigue"] as StateField[]).map(key => <div className="inferred-metric" key={key}>
      <div><span>{stateLabels[key]}<MetricHelp metric={key} suffix={worker.id === "alex" ? undefined : worker.id} /></span><strong>{valid ? Math.round(worker.cognitive_state[key]) : "—"}</strong></div>
      <div className="index-track"><i style={{ width: valid ? `${worker.cognitive_state[key]}%` : "0%" }} /></div>
    </div>)}</div></details>
    <div className="monitor-worker-foot"><span><span className={`quality-dot ${(signal?.quality ?? 0) < .6 ? "low" : ""}`} />Signal quality <strong>{signal ? `${number(signal.quality * 100)}%` : "—"}</strong><MetricHelp metric="signal_quality" suffix={worker.id === "alex" ? undefined : worker.id} /></span><button onClick={select} aria-pressed={selected} aria-label={`View details for ${worker.name}`}>{selected ? "Viewing signals" : "Explore signals"}<ChevronRight size={15} /></button></div>
  </article>;
}

function ManualSlider({ worker, field, update }: { worker: Worker; field: StateField; update: (id: string, values: Partial<Record<StateField, number>>) => Promise<void> }) {
  const [value, setValue] = useState(worker.cognitive_state[field]); const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => { if (!timer.current) setValue(worker.cognitive_state[field]); }, [worker.cognitive_state, field]);
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);
  return <label className="slider-label" htmlFor={`monitor-${worker.id}-${field}`}><span>{stateLabels[field]}<b>{number(value)}</b></span><input id={`monitor-${worker.id}-${field}`} type="range" min="0" max="100" value={value} onChange={e => { const next = Number(e.target.value); setValue(next); if (timer.current) clearTimeout(timer.current); timer.current = setTimeout(() => { timer.current = null; void update(worker.id, { [field]: next }); }, 150); }} /></label>;
}

function Examples({ kind, state }: { kind: "wellbeing" | "focus"; state: Snapshot }) {
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  return <main className="example-page"><div className="example-heading"><div><h1>{kind === "wellbeing" ? "Breaks & wellbeing" : "Team check-ins"}</h1><p>{kind === "wellbeing" ? "Explore a voluntary break suggestion using experimental demo indices." : "Explore a check-in suggestion using experimental indices and demo work context."}</p></div><span className="monitor-label"><Sparkles size={12} />Example · unvalidated rules</span></div><div className="example-cards">{state.workers.map(worker => {
    const signal = state.monitoring?.workers.find(m => m.worker_id === worker.id), valid = available(worker, signal), cognitive = worker.cognitive_state;
    const pause = cognitive.fatigue >= 60 || cognitive.cognitive_load >= 70 || cognitive.readiness < 45;
    const protect = cognitive.interruption_cost >= 60 || cognitive.readiness < 45;
    const recommendation = !valid ? "Wait for a reliable signal" : kind === "wellbeing" ? pause ? "Consider a 10-minute break" : "Keep the current rhythm" : protect ? "Consider an asynchronous update" : "Consider a brief check-in";
    const explanation = !valid ? "A reliable current estimate is needed first." : kind === "wellbeing" ? pause ? "The demo rule suggests offering a voluntary pause." : "The demo’s break rule is not triggered." : protect ? "The demo rule suggests an asynchronous update." : "The demo rule suggests a short conversation.";
    const action = kind === "wellbeing" ? "Draft suggestion" : "Draft agenda";
    return <article className="example-card" key={worker.id}><div className="example-card-header"><span className={`monitor-person-icon ${worker.id}`}>{worker.name[0]}</span><div><h2>{worker.name}</h2><p>{roleName(worker.role)}</p></div></div><div className="example-recommendation"><h3>{recommendation}</h3><p>{explanation}</p></div><div className="example-factors"><span>Readiness: {valid ? number(cognitive.readiness) : "—"} / 100</span><span>{kind === "wellbeing" ? `Fatigue: ${valid ? number(cognitive.fatigue) : "—"}` : `Interruption cost: ${valid ? number(cognitive.interruption_cost) : "—"}`} / 100</span><span>{sourceLabel(state)}</span></div><details><summary>Why this suggestion?</summary><p>{kind === "wellbeing" ? "Demo rule: offer a break when workload ≥ 70, fatigue ≥ 60, or readiness < 45. The person decides; this is not medical advice." : "Demo rule: consider an asynchronous update when interruption cost ≥ 60 or readiness < 45. No calendar is read or changed."}</p></details><button className="secondary-button" disabled={!valid} onClick={() => setDrafts(previous => ({ ...previous, [worker.id]: `${kind === "wellbeing" ? "Break suggestion" : "Agenda proposal"} for ${worker.name}\n\n${recommendation}.\n${explanation}\n\nRelative readiness: ${number(cognitive.readiness)}/100. Source: ${sourceLabel(state)}.\nLocal example draft. Awaiting the person’s review.` }))}>{kind === "wellbeing" ? <Coffee size={15} /> : <CalendarClock size={15} />}{action}</button>{drafts[worker.id] && <div className="example-action-result"><strong><Check size={13} /> Draft ready · not sent</strong><p>{drafts[worker.id].split("\n")[2]}</p><a href={`data:text/plain;charset=utf-8,${encodeURIComponent(drafts[worker.id])}`} download={`neurasign-${kind}-${worker.id}.txt`}><Download size={13} />Download draft</a></div>}</article>;
  })}</div><p className="example-note"><LockKeyhole size={15} />Local drafts only. Nothing is sent or scheduled.</p></main>;
}

export default function MonitoringDashboard() {
  const dashboard = useDashboard(); const { state, connection, pending, control, updateWorker, error } = dashboard;
  const [tab, setTab] = useState<Tab>("monitoring"), [selected, setSelected] = useState("alex"), [feature, setFeature] = useState<PhysiologicalFeature>("heart_rate");
  useEffect(() => {
    if (window.location.hash === "#manager") setTab("manager");
  }, []);
  const selectTab = (next: Tab) => {
    setTab(next);
    window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}${next === "manager" ? "#manager" : ""}`);
  };
  const selectedWorker = state?.workers.find(w => w.id === selected) ?? state?.workers[0];
  const selectedSignal = state?.monitoring?.workers.find(m => m.worker_id === selectedWorker?.id);
  const personalReference = !/provisional|not_personally_calibrated/i.test(selectedSignal?.reference_status ?? "");
  const live = state?.monitoring?.source_kind === "live";
  const liveSampleSeconds = Math.max(0, ...(state?.monitoring?.workers.map(worker => worker.last_sample_seconds ?? 0) ?? []));
  const info = featureInfo[feature];
  const selectedSeries = selectedSignal?.history.map(p => ({ time: p.time, value: p[feature] })) ?? [];
  const featureValue = selectedSignal?.features[feature];
  const historyCount = selectedSignal?.history.length ?? 0;
  return <MetricHelpProvider><div className="monitoring-app"><header className="monitor-header"><a className="monitor-logo" href="#" onClick={event => { event.preventDefault(); selectTab("monitoring"); }}><Brand /><span className="monitor-header-title">Demo workspace</span></a><div className="monitor-header-right"><a className="monitor-back-login" href="/?login=1"><ArrowLeft size={15} />Back to login</a><span className={`monitor-connection ${connection === "offline" ? "offline" : ""}`}><i />{connection === "connected" ? "Service connected" : connection === "offline" ? "Offline" : "Reconnecting"}</span>{tab !== "manager" && <MetricHelp metric="heart_rate" guide />}</div></header><nav className="monitor-tabs" aria-label="Team sections">
      {([{ id: "monitoring", label: "Team overview" }, { id: "manager", label: "Manager overview" }] as const).map(({ id, label }) => <button key={id} data-testid={`tab-${id}`} className={tab === id ? "active" : ""} aria-current={tab === id ? "page" : undefined} onClick={() => selectTab(id)}>{label}</button>)}
      <a className="monitor-model-link" href="/models">Model engine<ArrowRight size={13} /></a>
      <details className="monitor-examples-nav" onKeyDown={event => { if (event.key === "Escape") { event.currentTarget.open = false; event.currentTarget.querySelector("summary")?.focus(); } }}><summary className={["wellbeing", "focus", "incidents"].includes(tab) ? "active" : ""}>Use cases<ChevronDown size={13} /></summary><div>{([{ id: "wellbeing", label: "Breaks & wellbeing" }, { id: "focus", label: "Team check-ins" }, { id: "incidents", label: "Incident response" }] as const).map(({ id, label }) => <button key={id} data-testid={`tab-${id}`} aria-current={tab === id ? "page" : undefined} onClick={event => { selectTab(id); event.currentTarget.closest("details")?.removeAttribute("open"); }}>{label}<ArrowRight size={13} /></button>)}</div></details>
    </nav>
    {tab === "monitoring" && <main className="monitor-content" data-testid="monitoring-dashboard"><div className="monitor-heading"><div><span className="monitor-eyebrow">01 / TEAM SIGNALS</span><h1>Team overview</h1><p>View each person’s signals, data quality and recent changes.</p></div></div>{error && <div className="monitor-error" role="alert">{error}</div>}{connection === "offline" && <div className="monitor-error" role="status">Connection lost. Showing the last received data; reconnecting automatically.</div>}
      {!state ? <div className="monitor-loading"><LoaderCircle size={27} className="spin" /><h2>Connecting to team signals</h2><p>Waiting for the monitoring service.</p></div> : <>
        <section className="monitor-summary" aria-label="Monitoring summary">
          <div><span className="summary-icon"><Users size={20} /></span><div><span>People in this view</span><strong>{state.workers.length}<small>demo profiles</small></strong></div></div>
          <div><span className="summary-icon"><Waves size={20} /></span><div><span>Available signal types</span><strong>{(Object.keys(featureInfo) as PhysiologicalFeature[]).filter(key => state.monitoring?.workers.some(worker => worker.features[key] != null)).length}<small>of {Object.keys(featureInfo).length} channels</small></strong></div></div>
          <div><span className="summary-icon"><Radio size={20} /></span><div><span>Data source</span><strong className="summary-source">{sourceLabel(state)}<small>{state.mode === "manual" ? "No sensor measurements" : state.mode === "live" ? "Received device measurements" : "Playback · not live employees"}</small></strong></div></div>
        </section>
        <section className="monitor-controls" aria-label="Source and playback"><label className="monitor-source-select"><Radio size={15} /><span className="sr-only">Signal source</span><select data-testid="monitoring-source" value={state.mode} disabled={pending} onChange={e => void control({ mode: e.target.value as Mode })}><option value="replay">Replay</option><option value="manual">Manual</option><option value="live">Live</option></select></label><div className="monitor-source-name"><span title={state.source.description}>{sourceLabel(state)}</span><MetricHelp metric="source" /><small>{state.source.kind === "universe" ? "RECORDED" : state.source.kind === "fixture" ? "ILLUSTRATIVE" : state.mode === "manual" ? "NO SENSORS" : "DEVICE"}</small></div><div className="monitor-playback"><button className="monitor-play" data-testid="monitoring-play" aria-label={state.playing ? "Pause signals" : "Play signals"} disabled={pending || state.mode !== "replay"} onClick={() => void control({ action: state.playing ? "pause" : "play" })}>{state.playing ? <Pause size={13} /> : <Play size={13} />}{state.playing ? "Pause" : "Play"}</button><button className="icon-button" disabled={pending} aria-label="Restart replay" title="Restart replay" onClick={() => void control({ action: "restart" })}><RotateCcw size={15} /></button><span className="monitor-time">{live ? liveSampleSeconds ? clock(liveSampleSeconds, true) : "—" : clock(state.monitoring?.signal_seconds ?? 0)}<small> · {live ? "device" : "recording"}</small></span><label className="monitor-speed"><span className="sr-only">Playback speed</span><select value={state.speed} disabled={pending || state.mode !== "replay"} onChange={e => void control({ speed: Number(e.target.value) })}>{[1, 5, 10, 30].map(speed => <option key={speed} value={speed}>{speed}×</option>)}</select></label><MetricHelp metric="replay" /></div></section>
        {state.mode === "manual" && <section className="monitor-manual-panel" aria-label="Manual capacity controls">{state.workers.map(worker => <div key={worker.id}><h3>{worker.name} · manual indices · no sensor data</h3><div className="monitor-manual-fields">{(Object.keys(stateLabels) as StateField[]).map(field => <ManualSlider key={field} worker={worker} field={field} update={updateWorker} />)}</div></div>)}</section>}
        <div className="monitor-section-title"><h2>People & signals<span>{state.workers.length} people</span></h2><span><Clock3 size={12} />Signal window: {state.monitoring?.window_seconds ?? "—"} s<MetricHelp metric="window" /></span></div><section className="monitor-worker-grid" aria-label="Current signals for each person">{state.workers.map(worker => <MonitorWorker key={worker.id} worker={worker} signal={state.monitoring?.workers.find(m => m.worker_id === worker.id)} selected={worker.id === selected} select={() => { setSelected(worker.id); const details = document.querySelector<HTMLElement>('[data-testid="selected-physiology-chart"]'); details?.focus({ preventScroll: true }); details?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "start" }); }} live={!!live} />)}</section>
        <div className="monitor-analysis-grid"><section className="monitor-panel" data-testid="selected-physiology-chart" tabIndex={-1} aria-label="Physiological signal details"><div className="monitor-panel-heading"><div><h2>Signal detail · {selectedWorker?.name}</h2><p>{state.source.kind === "fixture" ? "Illustrative windows · scenario reference" : state.mode === "manual" ? "Manual indices · no sensor data" : live ? "Readings received from the device" : "Recorded windows · personal reference"}</p></div><div className="monitor-person-switch" aria-label="Selected person">{state.workers.map(worker => <button key={worker.id} data-testid={`select-person-${worker.id}`} className={selected === worker.id ? "active" : ""} aria-pressed={selected === worker.id} onClick={() => setSelected(worker.id)}>{worker.name}</button>)}</div></div><div className="metric-tabs" aria-label="Chart signal">{(Object.keys(featureInfo) as PhysiologicalFeature[]).map(key => { const Icon = featureInfo[key].Icon; return <button key={key} data-testid={`metric-${key}`} className={feature === key ? "active" : ""} aria-pressed={feature === key} onClick={() => setFeature(key)}><Icon size={13} />{featureInfo[key].short}</button>; })}</div><div className="selected-chart-wrap"><div className="chart-heading"><div><strong>{number(featureValue, info.digits)}</strong><small>{info.unit}</small></div><span>{historyCount} windows · {info.label}<MetricHelp metric={feature} suffix="detail" /></span></div><Chart series={[{ label: selectedWorker?.name ?? "Signal", color: info.color, points: selectedSeries }]} baseline={personalReference ? selectedSignal?.reference[feature] : null} live={!!live} unit={info.unit} /></div><details className="baseline-detail"><summary>Compare with reference<ChevronDown size={14} /></summary><div className="baseline-table"><table><caption>{personalReference ? "Personal reference" : "Reference not calibrated"}<MetricHelp metric="baseline" /></caption><thead><tr><th>Signal</th><th>Current</th><th>Reference</th><th>Change</th></tr></thead><tbody>{(Object.keys(featureInfo) as PhysiologicalFeature[]).map(key => { const meta = featureInfo[key], value = selectedSignal?.features[key], reference = personalReference ? selectedSignal?.reference[key] : null, delta = value != null && reference != null ? value - reference : null; return <tr key={key}><td>{meta.short}<MetricHelp metric={key} suffix={key === "movement" ? undefined : "reference"} /></td><td>{number(value, meta.digits)} {meta.unit}</td><td>{number(reference, meta.digits)} {meta.unit}</td><td className="reference-change">{delta != null && Math.round(delta * 10 ** Math.max(1, meta.digits)) > 0 ? "+" : ""}{number(delta, Math.max(1, meta.digits))} {meta.unit}</td></tr>; })}</tbody></table></div></details><div className="baseline-note"><ShieldCheck size={12} /><span>{personalReference ? "Personal reference · no clinical thresholds" : "Uncalibrated · comparisons hidden"}</span><span className="baseline-gap-note">Gaps = missing readings</span></div></section>
          <div className="monitor-side-column"><section className="monitor-panel"><div className="monitor-panel-heading"><div><h2>Heart rate comparison<MetricHelp metric="heart_rate" suffix="comparison" /></h2><p>{live ? "Received device readings" : state.mode === "manual" ? "No sensor data in manual mode" : state.source.kind === "fixture" ? "Illustrative signals" : "Recorded measurements"} · bpm</p></div><ChartNoAxesCombined size={18} /></div><div className="team-chart-wrap"><Chart height={210} unit="bpm" live={!!live} series={state.workers.map(worker => ({ label: worker.name, color: workerColors[worker.id] ?? "var(--accent)", points: state.monitoring?.workers.find(m => m.worker_id === worker.id)?.history.map(p => ({ time: p.time, value: p.heart_rate })) ?? [] }))} /></div><div className="team-state-summary">{state.workers.map(worker => { const signal = state.monitoring?.workers.find(m => m.worker_id === worker.id); return <div key={worker.id}><span><i className="quality-dot" style={{ background: workerColors[worker.id] }} />{worker.name}</span><strong>{number(signal?.features.heart_rate)}<small>bpm</small></strong></div>; })}</div></section>
          <details className="monitor-panel monitor-context"><summary>Source & changes<ChevronDown size={14} /></summary><div className="change-summary-list">{state.workers.map(worker => { const signal = state.monitoring?.workers.find(m => m.worker_id === worker.id), current = signal?.features.heart_rate, baseline = /provisional|not_personally_calibrated/i.test(signal?.reference_status ?? "") ? null : signal?.reference.heart_rate, delta = current != null && baseline != null ? current - baseline : null; return <div className="change-summary" key={worker.id}><span className="change-summary-icon"><HeartPulse size={15} /></span><div><strong>{worker.name} · {statusText(worker, signal)}</strong><p>{delta == null ? "No current heart-rate comparison." : `Heart rate ${number(Math.abs(delta), 1)} bpm ${delta >= 0 ? "above" : "below"} personal reference.`}</p></div></div>; })}<div className="change-summary"><span className="change-summary-icon"><Layers3 size={15} /></span><div><strong>{sourceLabel(state)}</strong><p>{state.source.kind === "universe" ? "Recorded sessions · demo work profiles." : state.mode === "manual" ? "Manual indices · no sensor readings." : state.mode === "live" ? "Received readings only · stale data is marked unavailable." : "Illustrative scenario · generated signals."}</p></div></div></div><div className="monitor-provenance"><ShieldCheck size={15} /><span>{selectedSignal?.recording ? `${selectedSignal.recording.participant ?? "Participant"} · ${selectedSignal.recording.session ?? "Session"} · ${selectedSignal.recording.sensor ?? "Sensor"}. ` : ""}Measured signals come first. Capacity indices use experimental formulas.</span></div></details></div>
        </div><footer className="monitor-footer"><span><LockKeyhole size={13} />Demo profiles · physiological monitoring</span><span><Activity size={13} />{state.mode === "manual" ? "Manual values" : state.source.kind === "fixture" ? "Illustrative summaries" : state.mode === "live" ? "Received signal summaries" : "Recorded signal summaries"} · {state.mode === "manual" ? "Manual indices" : "Formula estimates"} / 100</span></footer>
      </>}
    </main>}
    {tab === "manager" && <ManagerOverview view={toManagerView(state, connection)} />}
    {state && (tab === "wellbeing" || tab === "focus") && <Examples key={tab} kind={tab} state={state} />}
    {tab === "incidents" && <div className="incident-embed"><div className="incident-example-toolbar"><span>Example workflow · demo profiles + experimental indices</span><button className="quiet-button" onClick={() => selectTab("monitoring")}><ArrowRight size={13} />Back to overview</button></div><IncidentStory dashboard={dashboard} /></div>}
  </div></MetricHelpProvider>;
}
