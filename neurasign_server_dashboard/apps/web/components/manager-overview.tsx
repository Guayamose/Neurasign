"use client";

import { useId, useRef, useState, type CSSProperties } from "react";
import { Activity, ArrowRight, BatteryMedium, ChevronDown, CircleHelp, CircleMinus, Clock3, EyeOff, Info, LoaderCircle, MessageCircle, Moon, Radio, Search, ShieldCheck, Users } from "lucide-react";
import type { ManagerPerson, ManagerView } from "@/lib/manager-preview";
import "./manager-overview.css";

const statuses = {
  review: { label: "Review suggested", Icon: MessageCircle },
  no_flag: { label: "No flag", Icon: Activity },
  unavailable: { label: "Unavailable", Icon: CircleMinus },
} as const;

const indices = [
  { key: "workload", label: "Workload", description: "Estimated demand", color: "#7b61b7", Icon: Activity },
  { key: "fatigue", label: "Fatigue", description: "Estimated tiredness", color: "#b98232", Icon: Moon },
  { key: "readiness", label: "Readiness", description: "Experimental capacity", color: "#107c68", Icon: BatteryMedium },
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
        <strong>{value}<small>/ 100</small></strong>
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
  const left = 38, right = 680, top = 16, bottom = 190;
  const first = points[0].time, last = points[points.length - 1].time, span = last - first;
  const x = (time: number) => span > 0 ? left + (time - first) / span * (right - left) : (left + right) / 2;
  const y = (value: number) => bottom - Math.max(0, Math.min(100, value)) / 100 * (bottom - top);
  return <div className="manager-trend">
    <svg data-testid="manager-trend" viewBox="0 0 708 227" role="img" aria-labelledby={`${chartId}-title ${chartId}-description`}>
      <title id={`${chartId}-title`}>{person.name} · experimental interpretation history</title>
      <desc id={`${chartId}-description`}>Workload, fatigue and readiness indices from 0 to 100 over the visible window. These are experimental estimates, not probabilities or a fitness-for-duty assessment.</desc>
      {[0, 25, 50, 75, 100].map(value => <g key={value}><line x1={left} x2={right} y1={y(value)} y2={y(value)} stroke="#e4ecef" strokeDasharray="3 5" /><text x={left - 10} y={y(value) + 4} textAnchor="end">{value}</text></g>)}
      {indices.map(({ key, color }) => <g key={key}>
        <path d={points.map((point, index) => `${index ? "L" : "M"}${x(point.time)},${y(point[key])}`).join(" ")} fill="none" stroke={color} strokeWidth="2.6" strokeLinejoin="round" strokeLinecap="round" />
        <circle cx={x(last)} cy={y(points[points.length - 1][key])} r="4.2" fill={color} stroke="#fff" strokeWidth="2" />
      </g>)}
      <text x={left} y="215" textAnchor="start">{timeLabel(first, live)}</text>
      <text x={right} y="215" textAnchor="end">{timeLabel(last, live)}</text>
    </svg>
    <div className="manager-chart-legend">{indices.map(({ key, label, color }) => <span key={key}><i style={{ background: color }} />{label}</span>)}<small>{live ? "Device time" : "Recording time"} · indices 0–100</small></div>
  </div>;
}

export default function ManagerOverview({ view }: { view: ManagerView | null }) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | ManagerPerson["status"]>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const detailRef = useRef<HTMLElement>(null);
  const people = view?.people ?? [];
  const normalizedQuery = query.trim().toLowerCase();
  const filtered = people.filter(person => (filter === "all" || person.status === filter) && `${person.name} ${person.role}`.toLowerCase().includes(normalizedQuery));
  const selected = filtered.find(person => person.id === selectedId) ?? filtered[0];
  const selectPerson = (id: string) => {
    setSelectedId(id);
    requestAnimationFrame(() => {
      detailRef.current?.focus({ preventScroll: true });
      detailRef.current?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "start" });
    });
  };

  return <main className="manager-overview" data-testid="manager-overview">
    <div className="manager-heading"><div><span className="manager-eyebrow">THE MANAGER PERSPECTIVE</span><h1>Every person. A clearer picture.</h1><p>Individual interpretations, with underlying measurements hidden.</p></div><span className="manager-view-badge"><ShieldCheck size={15} />Manager overview<span>Preview</span></span></div>
    <div className="manager-preview-bar"><span><Info size={16} /><strong>Experimental interpretations</strong><span>· not fitness-for-duty clearance</span></span><span className="manager-source"><Radio size={13} />{view?.sourceLabel ?? "Connecting to demo"}</span></div>

    {!view ? <div className="manager-loading" role="status"><LoaderCircle size={26} className="spin" /><h2>Connecting to the team</h2><p>Waiting for the current demo profiles.</p></div> : <>
      {view.connection === "offline" && <div className="manager-connection-notice" role="status"><Radio size={16} /><span>Connection lost. Current interpretations are unavailable until the service reconnects.</span></div>}
      <section className="manager-summary" aria-label="Team interpretation summary">
        <div><span className="manager-summary-icon"><Users size={20} /></span><div><span>Team members</span><strong>{people.length}<small>individual profiles</small></strong></div></div>
        <div className="review"><span className="manager-summary-icon"><MessageCircle size={20} /></span><div><span>Review suggested</span><strong>{people.filter(person => person.status === "review").length}<small>experimental flags</small></strong></div></div>
        <div><span className="manager-summary-icon"><CircleMinus size={20} /></span><div><span>Unavailable</span><strong>{people.filter(person => person.status === "unavailable").length}<small>no current estimate</small></strong></div></div>
      </section>

      <div className="manager-section-heading"><div><h2>Your team<span>{filtered.length} of {people.length}</span></h2><p>Select a person to understand their current interpretation.</p></div><div className="manager-filters"><label className="manager-search"><Search size={15} /><input aria-label="Search employees" placeholder="Find a team member" value={query} onChange={event => setQuery(event.target.value)} /></label><label className="manager-filter"><span className="sr-only">Filter by status</span><select aria-label="Filter by status" value={filter} onChange={event => setFilter(event.target.value as typeof filter)}><option value="all">All statuses</option><option value="review">Review suggested</option><option value="no_flag">No flag</option><option value="unavailable">Unavailable</option></select></label></div></div>

      <section className="manager-people-grid" aria-label="Individual team interpretations">
        {filtered.map(person => <article key={person.id} className={`manager-person ${person.status} ${selected?.id === person.id ? "selected" : ""}`} data-testid={`manager-person-${person.id}`}>
          <header><span className="manager-person-avatar" aria-hidden="true">{person.name.split(" ").map(part => part[0]).slice(0, 2).join("")}</span><div><h3>{person.name}</h3><p>{person.role}</p></div><StatusBadge status={person.status} /></header>
          <div className="manager-person-conclusion"><span className="manager-eyebrow">CURRENT INTERPRETATION</span><h4>{person.summary}</h4></div>
          <EstimateTiles person={person} />
          {person.indices && <span className="manager-estimate-caption">Experimental indices · 0–100</span>}
          <div className="manager-person-source"><span><Clock3 size={12} />{person.updatedLabel}</span></div>
          <button className="manager-person-open" onClick={() => selectPerson(person.id)} aria-label={`View interpretation for ${person.name}`} aria-controls="manager-detail" aria-pressed={selected?.id === person.id}>{selected?.id === person.id ? "Viewing interpretation" : "View interpretation"}<ArrowRight size={15} /></button>
        </article>)}
      </section>

      {!filtered.length && <div className="manager-empty" data-testid="manager-empty"><Users size={26} /><h3>{people.length ? "No matching team members" : "No team members available"}</h3><p>{people.length ? "Try another name or status." : "Individual profiles will appear when the demo service provides them."}</p>{people.length > 0 && <button onClick={() => { setQuery(""); setFilter("all"); }}>Clear filters</button>}</div>}

      {selected && <section className="manager-detail" id="manager-detail" data-testid="manager-detail" ref={detailRef} tabIndex={-1} aria-label={`Interpretation details for ${selected.name}`}>
        <div className="manager-detail-context"><span className="manager-eyebrow">INDIVIDUAL VIEW</span><h2>{selected.name}<span>Interpretation history</span></h2><StatusBadge status={selected.status} /><p>{selected.reason}</p><div className="manager-human-context"><MessageCircle size={17} /><span>{selected.status === "review" ? "Use this as a prompt for a conversation. Confirm with the person before acting." : selected.status === "unavailable" ? "Missing data cannot tell us how someone is feeling." : "No flag means no demo rule was triggered. It does not confirm how the person feels."}</span></div></div>
        <div className="manager-detail-chart"><div className="manager-chart-heading"><h3>How the estimates change</h3><span><EyeOff size={12} />Measurements hidden</span></div><IndividualTrend person={selected} live={view.sourceKind === "live"} /></div>
      </section>}

      <details className="manager-metric-explainer"><summary><span><CircleHelp size={15} />What do these estimates mean?</span><ChevronDown size={15} /></summary><div className="manager-explainer-grid">{indices.map(({ key, label, description, Icon }) => <div key={key}><Icon size={17} /><h3>{label}</h3><p>{description}. A relative 0–100 demo index, not a validated assessment.</p></div>)}</div><p>Review suggested: workload ≥ 70, fatigue ≥ 60, or readiness &lt; 45. These experimental demo rules need validation. Scores are not probabilities, diagnoses, or permission to perform safety-critical work.</p></details>
    </>}

    <details className="manager-about"><summary><span><Info size={15} />About this view and privacy</span><ChevronDown size={15} /></summary><div><p><strong>Same people, less detail.</strong> This preview uses the same demo profiles and experimental indices as Team overview. It shows individual interpretations without displaying underlying measurements.</p><p><strong>Preview, not a permission boundary.</strong> This tab filters data in the browser. Production access must also be restricted on the server. Named health-related inferences remain personal data and require a privacy and legal assessment.</p></div></details>
    <footer className="manager-footer"><span><EyeOff size={13} />Individual conclusions · measurements hidden</span><span>Demo profiles · experimental interpretations</span></footer>
  </main>;
}
