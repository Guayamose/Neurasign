"use client";

import { useEffect, useState } from "react";
import { CircleHelp, Clock3, Radio } from "lucide-react";
import { Chart } from "./monitoring-dashboard";

export type MetricDefinition = { id: string; name: string; unit: string; digits: number; meaning: string; freshness_seconds: number };
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
const periodLabel = (seconds: number | null) => !seconds ? "Point measurement" : seconds >= 3600 ? `${seconds / 3600}-hour period` : `${seconds}-second period`;

export function SignalTiles({ signals, catalog }: { signals: Signal[]; catalog: MetricDefinition[] }) {
  return <div className="co-signal-tiles">{signals.slice(0, 4).map(signal => {
    const definition = catalog.find(metric => metric.id === signal.metric);
    return <div key={signal.series_id} className={`co-signal-tile ${signal.status}`} title={`${definition?.meaning ?? signal.metric} Source: ${signal.source_name}`}>
      <small>{definition?.name ?? signal.metric}</small>
      <strong>{valueLabel(signal.latest?.value, definition?.digits ?? 1)}<em>{signal.unit}</em></strong>
      <span>{signal.status === "current" ? <Radio size={10} /> : <Clock3 size={10} />}{statusLabel[signal.status]}{signal.source === "recording" && " · Recording"}</span>
    </div>;
  })}{signals.length > 4 && <small className="co-more-signals">+{signals.length - 4} in signal detail</small>}</div>;
}

export function SignalExplorer({ personId, name, org, signals, catalog, revision, api }: {
  personId: string; name: string; org: string; signals: Signal[]; catalog: MetricDefinition[]; revision: number;
  api: <T>(path: string) => Promise<T>;
}) {
  const [selected, setSelected] = useState("");
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
  }, [api, org, personId, scope, signal?.series_id, visible, revision]);
  if (!signal) return null;
  const definition = catalog.find(metric => metric.id === signal.metric);
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
  return <section className="co-panel co-signal-panel" data-testid="canonical-signals">
    <div className="co-panel-head"><div><h2>Signal detail · {name}</h2><p>{signal.latest?.sample_count ? 'Raw samples and recent history.' : 'Measurements and recent history.'}</p></div><span className={`co-status ${signal.status === "current" ? "current" : "stale"}`}>{statusLabel[signal.status]}</span></div>
    <div className="co-metric-tabs">{signals.map(item => <button key={item.series_id} className={item.series_id === signal.series_id ? "active" : ""} aria-pressed={item.series_id === signal.series_id} onClick={() => setSelected(item.series_id)}>
      {catalog.find(metric => metric.id === item.metric)?.name ?? item.metric}<small>{item.source_name}{item.measurement_kind === "summary" ? " · Summary" : ""}</small>
    </button>)}</div>
    <div className="co-chart-value"><strong>{valueLabel(signal.latest?.value, definition?.digits ?? 1)}</strong><span>{signal.unit}</span><details><summary><CircleHelp size={14} />About this metric</summary><p>{definition?.meaning}<br />{periodLabel(signal.interval_seconds)} · {signal.method}</p></details></div>
    {history?.scope === scope && history.error && visible ? <p className="co-history-error" role="status">History is temporarily unavailable.</p> : <Chart live timeCaption="Measured time" unit={signal.unit} series={[{ label: definition?.name ?? signal.metric, color: "#789765", points }]} />}
    <footer className="co-panel-foot"><span>{signal.source === "recording" ? "DEMO RECORDING · " : ""}{signal.source_name} · {periodLabel(signal.interval_seconds)}</span><span>{signal.latest ? `Measured ${measuredTime(signal.latest.timestamp)}` : statusLabel[signal.status]}</span></footer>
  </section>;
}
