"use client";

import { useState, useRef, useEffect } from "react";
import { Activity, ArrowLeft, ArrowRight, CalendarClock, Check, ChevronDown, Coffee, Download, HeartPulse, LoaderCircle, LockKeyhole, Move, Pause, Play, Radio, RotateCcw, Thermometer, Waves } from "lucide-react";
import IncidentStory from "./incident-story";
import { Brand } from "./brand";
import ManagerOverview from "./manager-overview";
import { toManagerView } from "@/lib/manager-preview";
import { MetricHelp, MetricHelpProvider, metricDefinitions } from "./metric-info";
import { useDashboard } from "@/lib/use-dashboard";
import "./demo-workspace.css";
import type { Mode, MonitoringWorker, PhysiologicalFeature, Snapshot, StateField, Worker } from "@/lib/types";

type Tab = "monitoring" | "manager" | "examples" | "wellbeing" | "focus" | "incidents";
type Point = { time: number; value: number | null };
type Series = { label: string; color: string; points: Point[] };
const featureInfo = {
  heart_rate: { label: "Heart rate", short: "HR", unit: "bpm", digits: 0, color: "var(--accent)", Icon: HeartPulse },
  hrv: { label: "Heart rate variability", short: "HRV", unit: "ms", digits: 1, color: "var(--accent)", Icon: Activity },
  eda: { label: "Skin conductance", short: "EDA", unit: "µS", digits: 2, color: "var(--accent)", Icon: Waves },
  temperature: { label: "Skin temperature", short: "Skin temp", unit: "°C", digits: 1, color: "var(--accent)", Icon: Thermometer },
  movement: { label: "Movement", short: "Movement", unit: "g", digits: 3, color: "var(--accent)", Icon: Move },
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

function MonitorWorker({ worker, signal, selected, select }: { worker: Worker; signal?: MonitoringWorker; selected: boolean; select: () => void }) {
  return <article className={`demo-person-row ${selected ? "selected" : ""}`} data-testid={`monitor-worker-${worker.id}`}>
    <div className="demo-person-name"><span className="demo-avatar" aria-hidden="true">{worker.name[0]}</span><div><h3>{worker.name}</h3><span>{statusText(worker, signal)}</span></div></div>
    <dl className="demo-person-values">{primaryFeatures.map(key => { const info = featureInfo[key]; return <div key={key}>
      <dt>{info.label}<MetricHelp metric={key} suffix={`row-${worker.id}`} /></dt>
      <dd>{number(signal?.features[key], info.digits)}<small>{info.unit}</small></dd>
    </div>; })}</dl>
    <button className="demo-person-open" onClick={select} aria-pressed={selected} aria-label={`View details for ${worker.name}`}>View details<ArrowRight size={16} /></button>
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
  return <main className="example-page"><div className="example-heading"><div><h1>{kind === "wellbeing" ? "Break suggestions" : "Team check-ins"}</h1><p>{kind === "wellbeing" ? "See a demo suggestion, then prepare a message for the person to review." : "See a demo suggestion, then prepare a check-in agenda."}</p></div></div><p className="demo-example-context">Experimental rules · Local drafts only. Nothing is sent or scheduled.</p><div className="example-cards">{state.workers.map(worker => {
    const signal = state.monitoring?.workers.find(m => m.worker_id === worker.id), valid = available(worker, signal), cognitive = worker.cognitive_state;
    const pause = cognitive.fatigue >= 60 || cognitive.cognitive_load >= 70 || cognitive.readiness < 45;
    const protect = cognitive.interruption_cost >= 60 || cognitive.readiness < 45;
    const recommendation = !valid ? "Wait for a reliable signal" : kind === "wellbeing" ? pause ? "Consider a 10-minute break" : "Keep the current rhythm" : protect ? "Consider an asynchronous update" : "Consider a brief check-in";
    const explanation = !valid ? "A reliable current estimate is needed first." : kind === "wellbeing" ? pause ? "The demo rule suggests offering a voluntary pause." : "The demo’s break rule is not triggered." : protect ? "The demo rule suggests an asynchronous update." : "The demo rule suggests a short conversation.";
    const action = kind === "wellbeing" ? "Draft suggestion" : "Draft agenda";
    return <article className="example-card" key={worker.id}><div className="example-card-header"><span className="demo-avatar" aria-hidden="true">{worker.name[0]}</span><div><h2>{worker.name}</h2><p>{roleName(worker.role)}</p></div></div><div className="example-recommendation"><h3>{recommendation}</h3></div><button className="secondary-button" disabled={!valid} onClick={() => setDrafts(previous => ({ ...previous, [worker.id]: `${kind === "wellbeing" ? "Break suggestion" : "Agenda proposal"} for ${worker.name}\n\n${recommendation}.\n${explanation}\n\nRelative readiness: ${number(cognitive.readiness)}/100. Source: ${sourceLabel(state)}.\nLocal example draft. Awaiting the person’s review.` }))}>{kind === "wellbeing" ? <Coffee size={15} /> : <CalendarClock size={15} />}{action}</button>{drafts[worker.id] && <div className="example-action-result" role="status"><strong><Check size={13} /> Draft ready · not sent</strong><p>{drafts[worker.id].split("\n")[2]}</p><a href={`data:text/plain;charset=utf-8,${encodeURIComponent(drafts[worker.id])}`} download={`neurasign-${kind}-${worker.id}.txt`}><Download size={13} />Download draft</a></div>}<details><summary>Why this suggestion?</summary><p>{explanation}</p><p>{kind === "wellbeing" ? "Demo rule: offer a break when workload ≥ 70, fatigue ≥ 60, or readiness < 45. The person decides." : "Demo rule: consider an asynchronous update when interruption cost ≥ 60 or readiness < 45."}</p><div className="example-factors"><span>Readiness: {valid ? number(cognitive.readiness) : "—"} / 100</span><span>{kind === "wellbeing" ? `Fatigue: ${valid ? number(cognitive.fatigue) : "—"}` : `Interruption cost: ${valid ? number(cognitive.interruption_cost) : "—"}`} / 100</span><span>{sourceLabel(state)}</span></div></details></article>;
  })}</div></main>;
}

function UseCases({ select }: { select: (tab: Tab) => void }) {
  return <main className="demo-use-cases"><div className="demo-page-heading"><h1>Use cases</h1><p>Choose an example to explore what the platform could help with.</p></div><div className="demo-case-list">
    {([
      { id: "wellbeing", title: "Break suggestions", description: "Explore a voluntary break suggestion and prepare a local draft.", Icon: Coffee },
      { id: "focus", title: "Team check-ins", description: "Explore a check-in suggestion and prepare a local agenda.", Icon: CalendarClock },
      { id: "incidents", title: "Incident walkthrough", description: "Investigate a sample incident, review the plan, and approve the next step.", Icon: Activity },
    ] as const).map(({ id, title, description, Icon }) => <button key={id} data-testid={`tab-${id}`} onClick={() => select(id)}><span className="demo-case-icon"><Icon size={23} /></span><span><strong>{title}</strong><span>{description}</span></span><ArrowRight size={20} /></button>)}
  </div><p className="demo-small-note">Demo scenarios use experimental interpretations. You stay in control of each action.</p></main>;
}

export default function MonitoringDashboard() {
  const dashboard = useDashboard();
  const { state, connection, pending, control, updateWorker, error } = dashboard;
  const [tab, setTab] = useState<Tab>("monitoring"), [selected, setSelected] = useState("alex"), [feature, setFeature] = useState<PhysiologicalFeature>("heart_rate");
  const [showReference, setShowReference] = useState(false);
  useEffect(() => {
    const hash = window.location.hash.slice(1);
    if (["manager", "examples", "wellbeing", "focus", "incidents"].includes(hash)) setTab(hash as Tab);
  }, []);
  const selectTab = (next: Tab) => {
    setTab(next);
    window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}${next === "monitoring" ? "" : `#${next}`}`);
    window.scrollTo({ top: 0, behavior: "instant" });
  };
  const selectedWorker = state?.workers.find(w => w.id === selected) ?? state?.workers[0];
  const selectedSignal = state?.monitoring?.workers.find(m => m.worker_id === selectedWorker?.id);
  const personalReference = !/provisional|not_personally_calibrated/i.test(selectedSignal?.reference_status ?? "");
  const live = state?.monitoring?.source_kind === "live";
  const info = featureInfo[feature];
  const selectedSeries = selectedSignal?.history.map(p => ({ time: p.time, value: p[feature] })) ?? [];
  const exampleActive = ["examples", "wellbeing", "focus", "incidents"].includes(tab);
  const valid = selectedWorker ? available(selectedWorker, selectedSignal) : false;
  const sourceTitle = !state ? "Connecting to demo" : state.mode === "manual" ? "Manual scenario" : state.mode === "live" ? "Live device input · demo" : state.source.kind === "universe" ? "Recorded wearable data" : "Illustrative data";
  const sourceDetail = !state ? "Loading the sample profiles." : state.mode === "manual" ? "Values set by you · no sensor measurements" : state.mode === "live" ? "Received readings only · missing data stays empty" : state.source.kind === "universe" ? `UNIVERSE recordings · ${state.workers.length} sample profiles · not live employees` : "Generated sample signals · not recorded measurements";

  return <MetricHelpProvider><div className="monitoring-app demo-workspace">
    <header className="demo-header"><a className="demo-brand" href="/demo" onClick={event => { event.preventDefault(); selectTab("monitoring"); }}><Brand /><span>Interactive demo</span></a><div className="demo-header-actions"><a className="demo-login-link" href="/?login=1"><ArrowLeft size={15} />Back to login</a></div></header>
    <nav className="demo-tabs" aria-label="Demo sections">
      {([{ id: "monitoring", label: "Team signals" }, { id: "manager", label: "Manager preview" }, { id: "examples", label: "Use cases" }] as const).map(({ id, label }) => {
        const active = id === "examples" ? exampleActive : tab === id;
        return <button key={id} data-testid={`tab-${id}`} className={active ? "active" : ""} aria-current={active ? "page" : undefined} onClick={() => selectTab(id)}>{label}</button>;
      })}
    </nav>
    <section className="demo-source-context" data-testid="demo-source-context" aria-label="Demo data source"><div><Radio size={18} aria-hidden="true" /><div><strong>{sourceTitle}</strong><span>{sourceDetail}</span></div></div>{state?.mode === "replay" && <div className="demo-playback"><span>{clock(state.monitoring?.signal_seconds ?? 0)} <small>{state.playing ? "Playing" : "Paused"}</small></span><button data-testid="monitoring-play" disabled={pending} onClick={() => void control({ action: state.playing ? "pause" : "play" })}>{state.playing ? <Pause size={15} /> : <Play size={15} />}{state.playing ? "Pause recording" : "Resume recording"}</button></div>}</section>
    {error && <div className="demo-global-notice monitor-error" role="alert">{error}</div>}
    {connection === "offline" && <div className="demo-global-notice monitor-error" role="status">Connection lost. Showing the last received data; reconnecting automatically.</div>}

    {tab === "monitoring" && <main className="demo-signals" data-testid="monitoring-dashboard"><div className="demo-page-heading"><div><h1>Team signals</h1><p>See the readings at a glance. Select a person or signal to explore.</p></div><MetricHelp metric="heart_rate" guide /></div>
      {!state ? <div className="monitor-loading" role="status"><LoaderCircle size={27} className="spin" /><h2>Loading team signals</h2><p>The sample profiles will appear here.</p></div> : <>
        <section className="demo-people-list" aria-label="Current signals for each person">{state.workers.map(worker => <MonitorWorker key={worker.id} worker={worker} signal={state.monitoring?.workers.find(m => m.worker_id === worker.id)} selected={worker.id === selectedWorker?.id} select={() => { setSelected(worker.id); const details = document.querySelector<HTMLElement>('[data-testid="selected-physiology-chart"]'); details?.focus({ preventScroll: true }); details?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "start" }); }} />)}</section>
        <section className="demo-signal-detail" data-testid="selected-physiology-chart" tabIndex={-1} aria-label="Physiological signal details">
          <div className="demo-detail-heading"><h2>Signal detail · {selectedWorker?.name}</h2><div className="monitor-person-switch" aria-label="Selected person">{state.workers.map(worker => <button key={worker.id} data-testid={`select-person-${worker.id}`} className={selectedWorker?.id === worker.id ? "active" : ""} aria-pressed={selectedWorker?.id === worker.id} onClick={() => setSelected(worker.id)}>{worker.name}</button>)}</div></div>
          <div className="demo-metric-tabs" aria-label="Chart signal">{(Object.keys(featureInfo) as PhysiologicalFeature[]).map(key => { const Icon = featureInfo[key].Icon; return <button key={key} data-testid={`metric-${key}`} className={feature === key ? "active" : ""} aria-pressed={feature === key} onClick={() => setFeature(key)}><Icon size={16} />{featureInfo[key].label}</button>; })}</div>
          <div className="demo-chart-heading"><div><span>{info.label}<MetricHelp metric={feature} suffix="detail" /></span><p>{metricDefinitions[feature].short}</p></div><strong>{number(selectedSignal?.features[feature], info.digits)}<small>{info.unit}</small></strong></div>
          <Chart series={[{ label: selectedWorker?.name ?? "Signal", color: info.color, points: selectedSeries }]} baseline={showReference && personalReference ? selectedSignal?.reference[feature] : null} live={!!live} unit={info.unit} />
          <p className="demo-chart-note">{state.mode === "manual" ? "Manual mode has no sensor measurements." : "Gaps mean missing readings."}</p>
          <details className="baseline-detail demo-disclosure" onToggle={event => setShowReference(event.currentTarget.open)}><summary>Compare with personal reference<ChevronDown size={16} /></summary><div className="baseline-table"><table><caption>{personalReference ? "Personal reference · no clinical thresholds" : "Reference not calibrated"}<MetricHelp metric="baseline" /></caption><thead><tr><th>Signal</th><th>Current</th><th>Reference</th><th>Change</th></tr></thead><tbody>{(Object.keys(featureInfo) as PhysiologicalFeature[]).map(key => { const meta = featureInfo[key], value = selectedSignal?.features[key], reference = personalReference ? selectedSignal?.reference[key] : null, delta = value != null && reference != null ? value - reference : null; return <tr key={key}><td>{meta.label}</td><td>{number(value, meta.digits)} {meta.unit}</td><td>{number(reference, meta.digits)} {meta.unit}</td><td>{delta != null && delta > 0 ? "+" : ""}{number(delta, Math.max(1, meta.digits))} {meta.unit}</td></tr>; })}</tbody></table></div></details>
          <details className="demo-disclosure worker-estimates" data-testid="demo-estimates"><summary><span>Experimental estimates<small>Formula indices · unvalidated</small></span><ChevronDown size={16} /></summary><div className="demo-estimate-values">{(["cognitive_load", "readiness", "fatigue"] as StateField[]).map(key => <div key={key}><span>{stateLabels[key]}<MetricHelp metric={key} /></span><strong>{valid ? number(selectedWorker?.cognitive_state[key]) : "—"}<small>/ 100</small></strong></div>)}</div><p>These {state.mode === "manual" ? "manually set values" : "experimental formulas"} power the demo examples. They are not probabilities or validated assessments.</p></details>
          <details className="demo-disclosure"><summary>Recording & signal details<ChevronDown size={16} /></summary><dl className="demo-recording-details"><div><dt>Source</dt><dd>{sourceLabel(state)}</dd></div><div><dt>Signal window<MetricHelp metric="window" /></dt><dd>{state.monitoring?.window_seconds ?? "—"} seconds</dd></div><div><dt>Signal quality<MetricHelp metric="signal_quality" /></dt><dd>{selectedSignal ? `${number(selectedSignal.quality * 100)}%` : "—"}</dd></div><div><dt>Visible windows</dt><dd>{selectedSignal?.history.length ?? 0}</dd></div>{selectedSignal?.recording && <div><dt>Recording</dt><dd>{[selectedSignal.recording.participant, selectedSignal.recording.session, selectedSignal.recording.sensor].filter(Boolean).join(" · ")}</dd></div>}</dl></details>
        </section>
        <details className="demo-disclosure demo-comparison" data-testid="demo-comparison"><summary>Compare heart rates<ChevronDown size={16} /></summary><Chart height={195} unit="bpm" live={!!live} series={state.workers.map(worker => ({ label: worker.name, color: workerColors[worker.id] ?? "var(--accent)", points: state.monitoring?.workers.find(m => m.worker_id === worker.id)?.history.map(p => ({ time: p.time, value: p.heart_rate })) ?? [] }))} /></details>
        <details className="demo-disclosure demo-presenter" data-testid="presenter-controls"><summary>Presenter controls<ChevronDown size={16} /></summary><div className="demo-presenter-fields"><label><span>Signal source</span><select data-testid="monitoring-source" value={state.mode} disabled={pending} onChange={e => void control({ mode: e.target.value as Mode })}><option value="replay">Recorded playback</option><option value="manual">Manual scenario</option><option value="live">Live input</option></select></label><label><span>Playback speed</span><select value={state.speed} disabled={pending || state.mode !== "replay"} onChange={e => void control({ speed: Number(e.target.value) })}>{[1, 5, 10, 30].map(speed => <option key={speed} value={speed}>{speed}×</option>)}</select></label><button disabled={pending} onClick={() => void control({ action: "restart" })}><RotateCcw size={16} />Restart demo</button></div><p>Restart resets the recording and all example progress.</p>{state.mode === "manual" && <section className="monitor-manual-panel" aria-label="Manual capacity controls">{state.workers.map(worker => <div key={worker.id}><h3>{worker.name} · manual indices · no sensor data</h3><div className="monitor-manual-fields">{(Object.keys(stateLabels) as StateField[]).map(field => <ManualSlider key={field} worker={worker} field={field} update={updateWorker} />)}</div></div>)}</section>}</details>
      </>}
    </main>}
    {tab === "manager" && <ManagerOverview view={toManagerView(state, connection)} />}
    {tab === "examples" && <UseCases select={selectTab} />}
    {["wellbeing", "focus", "incidents"].includes(tab) && <div className="demo-example-back"><button onClick={() => selectTab("examples")}><ArrowLeft size={16} />Back to examples</button></div>}
    {(tab === "wellbeing" || tab === "focus") && (state ? <Examples key={tab} kind={tab} state={state} /> : <main className="demo-signals" role="status">Loading example data…</main>)}
    {tab === "incidents" && <div className="incident-embed"><IncidentStory dashboard={dashboard} /></div>}
    <footer className="demo-footer"><LockKeyhole size={14} /><span>Demo profiles and examples · <a href="/?login=1">Open company workspace</a> · <a href="/models">Model engine</a></span></footer>
  </div></MetricHelpProvider>;
}
