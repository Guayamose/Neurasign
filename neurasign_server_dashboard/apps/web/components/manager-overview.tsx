"use client";

import { useId, useRef, useState, type CSSProperties } from "react";
import { Activity, ArrowLeft, ArrowRight, BatteryMedium, ChevronDown, CircleHelp, CircleMinus, EyeOff, Info, LoaderCircle, MessageCircle, Moon, Radio, Search, Users } from "lucide-react";
import type { ManagerPerson, ManagerView } from "@/lib/manager-preview";
import "./manager-overview.css";

const statuses = {
  review: { label: "Review suggested", Icon: MessageCircle },
  no_flag: { label: "No flag", Icon: Activity },
  unavailable: { label: "Unavailable", Icon: CircleMinus },
} as const;

const indices = [
  { key: "workload", label: "Workload", description: "Estimated demand", color: "var(--ink)", Icon: Activity },
  { key: "fatigue", label: "Fatigue", description: "Estimated tiredness", color: "var(--accent)", Icon: Moon },
  { key: "readiness", label: "Readiness", description: "Experimental capacity", color: "var(--muted)", Icon: BatteryMedium },
] as const;

function StatusBadge({ status }: { status: ManagerPerson["status"] }) {
  const { label, Icon } = statuses[status];
  return <span className={`manager-status ${status}`}><Icon size={13} />{label}</span>;
}

function EstimateTiles({ person }: { person: ManagerPerson }) {
  if (!person.indices) return <div className="manager-estimates-missing"><CircleMinus size={17} /><span>Current estimates are unavailable.</span></div>;
  return <div className="manager-estimates" data-testid={`manager-estimates-${person.id}`}>
    {indices.map(({ key, label, color, Icon }) => {
      const value = Math.round(person.indices![key]);
      return <div key={key} style={{ "--index-color": color } as CSSProperties}>
        <span><Icon size={13} />{label}</span>
        <strong>{value}<small>/100</small></strong>
        <div className="manager-index-track" aria-hidden="true"><i style={{ width: `${Math.max(0, Math.min(100, value))}%` }} /></div>
      </div>;
    })}
  </div>;
}

function timeLabel(seconds: number, live: boolean) {
  if (live) return new Date(seconds * 1000).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  const rounded = Math.max(0, Math.round(seconds));
  return `${Math.floor(rounded / 60)}:${String(rounded % 60).padStart(2, "0")}`;
}

function IndividualTrend({ person, live }: { person: ManagerPerson; live: boolean }) {
  const chartId = useId().replace(/:/g, "");
  const points = person.history;
  if (!points.length || !person.indices) return <div className="manager-chart-empty"><Activity size={25} /><strong>No interpreted trend available</strong><span>A current, usable estimate is needed to show this view.</span></div>;
  const left = 52, right = 680, top = 16, bottom = 190;
  const first = points[0].time, last = points[points.length - 1].time, span = last - first;
  const x = (time: number) => span > 0 ? left + (time - first) / span * (right - left) : (left + right) / 2;
  const y = (value: number) => bottom - Math.max(0, Math.min(100, value)) / 100 * (bottom - top);
  return <div className="manager-trend">
    <svg data-testid="manager-trend" viewBox="0 0 708 255" role="img" aria-labelledby={`${chartId}-title ${chartId}-description`}>
      <title id={`${chartId}-title`}>{person.name} · experimental interpretation history</title>
      <desc id={`${chartId}-description`}>Workload, fatigue and readiness indices from 0 to 100 over the visible window. These are experimental estimates, not probabilities or a fitness-for-duty assessment.</desc>
      {[0, 25, 50, 75, 100].map(value => <g key={value}><line x1={left} x2={right} y1={y(value)} y2={y(value)} stroke="#38465F" strokeDasharray="3 5" /><text x={left - 10} y={y(value) + 4} textAnchor="end">{value}</text></g>)}
      {indices.map(({ key, color }) => <g key={key}>
        <path d={points.map((point, index) => `${index ? "L" : "M"}${x(point.time)},${y(point[key])}`).join(" ")} fill="none" stroke={color} strokeWidth="2.6" strokeLinejoin="round" strokeLinecap="round" />
        <circle cx={x(last)} cy={y(points[points.length - 1][key])} r="4.2" fill={color} stroke="#131A2A" strokeWidth="2" />
      </g>)}
      <text x={left} y="239" textAnchor="start">{timeLabel(first, live)}</text>
      <text x={right} y="239" textAnchor="end">{timeLabel(last, live)}</text>
    </svg>
    <div className="manager-chart-legend">{indices.map(({ key, label, color }) => <span key={key}><i style={{ background: color }} />{label}</span>)}<small>{live ? "Device time" : "Recording time"} · indices 0–100</small></div>
  </div>;
}

export default function ManagerOverview({ view }: { view: ManagerView | null }) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | ManagerPerson["status"]>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const detailRef = useRef<HTMLElement>(null);
  const personButtons = useRef(new Map<string, HTMLButtonElement>());
  const people = view?.people ?? [];
  const normalizedQuery = query.trim().toLowerCase();
  const filtered = people.filter(person => (filter === "all" || person.status === filter) && `${person.name} ${person.role}`.toLowerCase().includes(normalizedQuery));
  const selected = filtered.find(person => person.id === selectedId);
  const selectPerson = (id: string) => {
    setSelectedId(id);
    requestAnimationFrame(() => {
      detailRef.current?.focus({ preventScroll: true });
      detailRef.current?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "start" });
    });
  };
  const closeDetails = () => {
    const button = selectedId ? personButtons.current.get(selectedId) : null;
    setSelectedId(null);
    requestAnimationFrame(() => button?.focus());
  };
  const setStatusFilter = (next: typeof filter) => {
    setFilter(next);
    setSelectedId(null);
  };

  return <main className="manager-overview" data-testid="manager-overview">
    <div className="manager-heading"><div><h1>Manager overview</h1><p>See each person’s demo conclusion, with their measurements hidden.</p></div></div>
    <div className="manager-preview-bar"><span><Info size={16} /><span><strong>Experimental interpretations.</strong> Demo rules, not a fitness-for-duty assessment.</span></span></div>

    {!view ? <div className="manager-loading" role="status"><LoaderCircle size={26} className="spin" /><h2>Loading the team</h2><p>The demo profiles will appear here.</p></div> : <>
      {view.connection === "offline" && <div className="manager-connection-notice" role="status"><Radio size={17} /><span>Connection lost. Estimates will return when the service reconnects.</span></div>}
      <section className="manager-summary" aria-label="Team interpretation summary">
        <button aria-pressed={filter === "all"} onClick={() => setStatusFilter("all")}><Users size={18} /><span>All members</span><strong>{people.length}</strong></button>
        <button className="review" aria-pressed={filter === "review"} onClick={() => setStatusFilter("review")}><MessageCircle size={18} /><span>Review suggested</span><strong>{people.filter(person => person.status === "review").length}</strong></button>
        <button aria-pressed={filter === "unavailable"} onClick={() => setStatusFilter("unavailable")}><CircleMinus size={18} /><span>Unavailable</span><strong>{people.filter(person => person.status === "unavailable").length}</strong></button>
      </section>

      <div className="manager-section-heading"><h2>Team members <span>{filtered.length} of {people.length}</span></h2><div className="manager-filters"><label className="manager-search"><Search size={17} /><input aria-label="Search employees" placeholder="Search name or role" value={query} onChange={event => { setQuery(event.target.value); setSelectedId(null); }} /></label><label className="manager-filter"><span className="sr-only">Filter by status</span><select aria-label="Filter by status" value={filter} onChange={event => setStatusFilter(event.target.value as typeof filter)}><option value="all">All statuses</option><option value="review">Review suggested</option><option value="no_flag">No flag</option><option value="unavailable">Unavailable</option></select></label></div></div>

      {filtered.length > 0 && <section className="manager-people-list" aria-label="Individual team interpretations">
        <div className="manager-list-head" aria-hidden="true"><span>Person</span><span>Demo result</span><span>Details</span></div>
        {filtered.map(person => <article key={person.id} className={`manager-person ${person.status} ${selected?.id === person.id ? "selected" : ""}`} data-testid={`manager-person-${person.id}`}>
          <div className="manager-person-identity"><span className="manager-person-avatar" aria-hidden="true">{person.name.split(" ").map(part => part[0]).slice(0, 2).join("")}</span><div><h3>{person.name}</h3><p>{person.role}</p></div></div>
          <div className="manager-person-conclusion"><StatusBadge status={person.status} /><p>{person.summary}</p></div>
          <button className="manager-person-open" ref={button => { if (button) personButtons.current.set(person.id, button); else personButtons.current.delete(person.id); }} onClick={() => selectPerson(person.id)} aria-label={`View details for ${person.name}`} aria-controls="manager-detail" aria-expanded={selected?.id === person.id}>View details<ArrowRight size={16} /></button>
        </article>)}
      </section>}

      {!filtered.length && <div className="manager-empty" data-testid="manager-empty"><Users size={26} /><h3>{people.length ? "No matching team members" : "No team members available"}</h3><p>{people.length ? "Try another name or status." : "Profiles will appear when the demo connects."}</p>{people.length > 0 && <button onClick={() => { setQuery(""); setStatusFilter("all"); }}>Clear filters</button>}</div>}

      {selected && <section className="manager-detail" id="manager-detail" data-testid="manager-detail" ref={detailRef} tabIndex={-1} aria-label={`Interpretation details for ${selected.name}`}>
        <header className="manager-detail-heading"><div><span className="manager-eyebrow">DEMO DETAILS</span><h2>{selected.name}</h2><p>{selected.role} · {selected.updatedLabel}</p></div><button className="manager-back" onClick={closeDetails}><ArrowLeft size={16} />Back to team</button></header>
        <div className="manager-detail-body"><div className="manager-detail-context"><StatusBadge status={selected.status} /><h3>{selected.summary}</h3><p>{selected.reason}</p><div className="manager-human-context"><MessageCircle size={18} /><span>{selected.status === "review" ? "Start with a conversation. Confirm with the person before acting." : selected.status === "unavailable" ? "Missing data cannot tell us how someone is feeling." : "No flag means no demo rule was triggered. It does not confirm how the person feels."}</span></div></div>
          <div className="manager-detail-chart"><h3>Experimental estimates <span>0–100 indices</span></h3><EstimateTiles person={selected} /><div className="manager-chart-heading"><h3>Change over time</h3><span><EyeOff size={13} />Measurements hidden</span></div><IndividualTrend person={selected} live={view.sourceKind === "live"} /></div>
        </div>
      </section>}

      <details className="manager-metric-explainer"><summary><span><CircleHelp size={17} />How are these demo results calculated?</span><ChevronDown size={16} /></summary><div className="manager-explainer-grid">{indices.map(({ key, label, description, Icon }) => <div key={key}><Icon size={18} /><h3>{label}</h3><p>{description}. A relative 0–100 demo index, not a validated assessment.</p></div>)}</div><p>Review suggested: workload ≥ 70, fatigue ≥ 60, or readiness &lt; 45. These experimental demo rules need validation. Scores are not probabilities, diagnoses, or permission to perform safety-critical work.</p></details>
    </>}

    <details className="manager-about"><summary><span><Info size={17} />About this preview and privacy</span><ChevronDown size={16} /></summary><div><p><strong>Same people, less detail.</strong> This preview uses the same demo profiles and experimental indices as Team signals. It shows individual interpretations without displaying underlying measurements.</p><p><strong>Preview, not a permission boundary.</strong> This tab filters data in the browser. Production access must also be restricted on the server. Named health-related inferences remain personal data and require a privacy and legal assessment.</p></div></details>
  </main>;
}
