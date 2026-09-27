"use client";

import { useEffect, useState } from "react";
import { Activity, ArrowDownToLine, CircleHelp, Clock3, HeartPulse, LoaderCircle, Pause, Radio, RotateCcw, ShieldAlert, Thermometer, Waves } from "lucide-react";
import { Chart } from "./monitoring-dashboard";
import "./company-details.css";

export type MetricDefinition = { id: string; name: string; unit: string; digits: number; meaning: string; freshness_seconds: number; category?: "quality" };
type Observation = { id: string; value: number; timestamp: number; received_at: number; method: string; interval_seconds: number | null; samples?: number[]; sample_offsets_ms?: number[]; sample_count?: number; sample_duration_ms?: number };
export type Signal = {
  series_id: string; metric: string; source_id: string; source_name: string; source: "wearable" | "recording";
  unit: string; measurement_kind: "sample" | "window" | "summary"; delivery_mode: "stream" | "sync";
  interval_seconds: number | null; method: string;
  status: "current" | "delayed" | "summary" | "waiting" | "unsupported" | "permission_required" | "paused";
  latest: Observation | null;
};
const statusLabel = { current: "Current", delayed: "Delayed", summary: "Summary", waiting: "Waiting", unsupported: "Unavailable", permission_required: "Permission needed", paused: "Paused" };
const valueLabel = (value: number | undefined, digits: number) => value === undefined ? "—" : value.toLocaleString("en-US", { maximumFractionDigits: digits });
const measuredTime = (value: number) => new Date(value * 1000).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" });
const periodLabel = (seconds: number | null) => !seconds ? "Point measurement" : seconds >= 3600 ? `${Number((seconds / 3600).toFixed(2))}-hour period` : `${seconds}-second period`;
const metricIcon = (metric: string) => metric === "heart_rate" ? HeartPulse : metric.includes("temperature") ? Thermometer : metric.includes("hrv") || metric.includes("acceleration") ? Activity : Waves;
const statusIcon = (status: Signal["status"]) => status === "current" ? Radio : status === "paused" ? Pause : status === "permission_required" ? ShieldAlert : Clock3;
const emptyDescription: Partial<Record<Signal["status"], { title: string; body: string }>> = {
  paused: { title: "Sharing is paused", body: "Measurements are hidden until the employee enables sharing on their phone." },
  waiting: { title: "Waiting for measurements", body: "This signal is supported. Its chart will appear when the connected device sends a reading." },
  unsupported: { title: "This signal is unavailable", body: "The connected source does not provide this measurement." },
  permission_required: { title: "Permission is needed", body: "The employee needs to allow access to this signal on their phone." },
};

export function SignalTiles({ signals, catalog }: { signals: Signal[]; catalog: MetricDefinition[] }) {
  const primary = signals.filter(signal => catalog.find(metric => metric.id === signal.metric)?.category !== "quality").slice(0, 4);
  return <div className="co-signal-tiles">{primary.map(signal => {
    const definition = catalog.find(metric => metric.id === signal.metric);
    const Icon = metricIcon(signal.metric), StatusIcon = statusIcon(signal.status);
    return <div key={signal.series_id} className={`co-signal-tile ${signal.status}`} title={`${definition?.meaning ?? signal.metric} Source: ${signal.source_name}`}>
      <small><Icon size={12} />{definition?.name ?? signal.metric}</small>
      <strong>{valueLabel(signal.status === "paused" ? undefined : signal.latest?.value, definition?.digits ?? 1)}<em>{signal.unit}</em></strong>
      <span><StatusIcon size={10} />{statusLabel[signal.status]}{signal.delivery_mode === "sync" && " · Synced"}{signal.source === "recording" && " · Recording"}</span>
    </div>;
  })}{signals.length > primary.length && <small className="co-more-signals">+{signals.length - primary.length} in signal detail</small>}</div>;
}

export function SignalExplorer({ personId, name, org, signals, catalog, revision, api }: {
  personId: string; name: string; org: string; signals: Signal[]; catalog: MetricDefinition[]; revision: number;
  api: <T>(path: string) => Promise<T>;
}) {
  const [selected, setSelected] = useState("");
  const [retry, setRetry] = useState(0);
  const [history, setHistory] = useState<{ scope: string; rows: Observation[]; error: boolean } | null>(null);
  const signal = signals.find(item => item.series_id === selected) ?? signals[0];
  const scope = `${org}/${personId}/${signal?.series_id ?? ""}`;
  const visible = Boolean(signal?.latest) && signal?.status !== "paused";
  useEffect(() => {
    let active = true;
    if (!signal || !visible) return;
    api<{ observations: Observation[] }>(`/organizations/${org}/members/${personId}/observations?series_id=${signal.series_id}`)
      .then(value => { if (active) setHistory({ scope, rows: value.observations, error: false }); })
      .catch(() => { if (active) setHistory({ scope, rows: [], error: true }); });
    return () => { active = false; };
  }, [api, org, personId, scope, signal?.series_id, visible, revision, retry]);
  if (!signal) return null;
  const definition = catalog.find(metric => metric.id === signal.metric);
  const Icon = metricIcon(signal.metric), StatusIcon = statusIcon(signal.status);
  const loading = visible && history?.scope !== scope;
  const empty = emptyDescription[signal.status];
  const rows = visible && history?.scope === scope ? history.rows : [];
  const points: { time: number; value: number | null }[] = [];
  rows.forEach((row, index) => {
    const previous = rows[index - 1];
    if (previous && row.timestamp - previous.timestamp > (signal.interval_seconds ?? definition?.freshness_seconds ?? 60) * 2) {
      points.push({ time: previous.timestamp + 1, value: null });
    }
    if (row.samples && row.sample_offsets_ms) {
      row.samples.forEach((value, index) => points.push({ time: row.timestamp + row.sample_offsets_ms![index] / 1000, value }));
    } else points.push({ time: row.timestamp, value: row.value });
  });
  return <section className="co-panel co-signal-panel co-signal-explorer" data-testid="canonical-signals">
    <div className="co-panel-head"><div><h2>Signal detail · {name}</h2><p>Explore each measurement and where it came from.</p></div><span className={`co-status ${signal.status === "current" ? "current" : signal.status === "delayed" ? "stale" : ""}`}><StatusIcon size={12} />{statusLabel[signal.status]}</span></div>
    <div className="co-metric-tabs" aria-label="Signals">{signals.map(item => {
      const ItemIcon = metricIcon(item.metric);
      return <button key={item.series_id} className={item.series_id === signal.series_id ? "active" : ""} aria-pressed={item.series_id === signal.series_id} onClick={() => setSelected(item.series_id)}><ItemIcon size={16} /><span>{catalog.find(metric => metric.id === item.metric)?.name ?? item.metric}<small>{item.source_name}{item.measurement_kind === "summary" ? " · Summary" : ""}</small></span></button>;
    })}</div>
    <div className="co-signal-intro"><span className="co-signal-symbol"><Icon size={22} /></span><div><h3>{definition?.name ?? signal.metric}</h3><p>{definition?.meaning ?? "A measurement reported by this source."}</p></div><div className="co-chart-value"><strong>{valueLabel(visible ? signal.latest?.value : undefined, definition?.digits ?? 1)}</strong><span>{signal.unit}</span>{signal.status === "delayed" && <small>Last reading</small>}</div></div>
    <div className="co-signal-meta"><span>{signal.delivery_mode === "stream" ? <Radio size={11} /> : <ArrowDownToLine size={11} />}{signal.delivery_mode === "stream" ? "Streaming source" : "Synced source"}</span><span><Clock3 size={11} />{periodLabel(signal.latest?.interval_seconds ?? signal.interval_seconds)}</span>{signal.source === "recording" && <span className="co-recording-badge">DEMO RECORDING</span>}</div>
    {empty && !visible ? <div className="co-signal-chart-empty"><StatusIcon size={26} /><h3>{empty.title}</h3><p>{empty.body}</p></div> : loading ? <div className="co-signal-loading" role="status"><LoaderCircle className="co-spin" size={17} />Loading measurements…</div> : history?.scope === scope && history.error && visible ? <div className="co-signal-chart-empty" role="status"><Clock3 size={25} /><h3>History is temporarily unavailable</h3><p>Your latest reading is shown above. Try loading the chart again.</p><button className="co-secondary" onClick={() => setRetry(value => value + 1)}><RotateCcw size={14} />Retry history</button></div> : !points.length ? <div className="co-signal-chart-empty"><Activity size={26} /><h3>No recent history</h3><p>Readings will appear here as this source sends measurements.</p></div> : <Chart live timeCaption="Measured time" unit={signal.unit} series={[{ label: definition?.name ?? signal.metric, color: "#6C8BFF", points }]} />}
    <details className="co-signal-technical"><summary><CircleHelp size={13} />Measurement details</summary><dl><div><dt>Method</dt><dd>{signal.method}</dd></div><div><dt>Measurement type</dt><dd>{signal.measurement_kind === "sample" ? "Individual samples" : signal.measurement_kind === "window" ? "Calculated over a time window" : "Summary over a period"}</dd></div><div><dt>Freshness</dt><dd>{signal.measurement_kind === "summary" ? "Period summaries are not live readings." : `Current for ${definition?.freshness_seconds ?? 60} seconds after measurement.`}</dd></div></dl></details>
    <footer className="co-panel-foot"><span><Radio size={12} />{signal.source_name}</span><span>{visible && signal.latest ? `Measured ${measuredTime(signal.latest.timestamp)}` : statusLabel[signal.status]}</span></footer>
  </section>;
}
