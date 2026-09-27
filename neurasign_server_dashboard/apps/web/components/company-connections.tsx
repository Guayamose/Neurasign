"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, Search, Smartphone, Trash2 } from "lucide-react";
import { rosterPage } from "@/lib/company-roster";
import { RosterPagination } from "./roster-pagination";
import "./company-connections.css";

export type Connection = { id: string; name: string; member_id: string; source: "wearable" | "recording"; revoked: boolean; last_received_at: number | null };

export function CompanyConnections({ devices, people, busy, canManage, openPeople, onRevoke }: {
  devices: Connection[]; people: { id: string; name: string; sharing: boolean }[]; busy: boolean; canManage: boolean;
  openPeople: (memberId?: string) => void; onRevoke: (device: Connection) => void;
}) {
  const [query, setQuery] = useState("");
  const [access, setAccess] = useState("allowed");
  const [pageIndex, setPageIndex] = useState(0);
  const [pageSize, setPageSize] = useState(25);
  const list = useRef<HTMLDivElement>(null);
  const names = useMemo(() => new Map(people.map(person => [person.id, person])), [people]);
  const allowed = devices.filter(device => !device.revoked).length;
  const normalize = (value: string) => value.normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  const words = normalize(query).trim().split(/\s+/).filter(Boolean);
  const filtered = devices.filter(device => (access === "all" || (access === "revoked") === device.revoked) && words.every(word => normalize(`${device.name} ${names.get(device.member_id)?.name ?? ""}`).includes(word)))
    .sort((a, b) => (names.get(a.member_id)?.name ?? "").localeCompare(names.get(b.member_id)?.name ?? "", "en", { sensitivity: "base", numeric: true }) || a.name.localeCompare(b.name, "en", { numeric: true }) || a.id.localeCompare(b.id));
  const page = rosterPage(filtered, pageIndex, pageSize);
  useEffect(() => { if (page.page !== pageIndex) setPageIndex(page.page); }, [page.page, pageIndex]);
  const changePage = (next: number) => { setPageIndex(next); if (list.current) list.current.scrollTop = 0; };

  return <section className="co-panel co-connections" aria-labelledby="co-connections-title">
    <div className="co-panel-head"><div><h2 id="co-connections-title">Phone connections</h2><p>{allowed} allowed · {devices.length - allowed} revoked. Allowed access does not mean a phone is online.</p></div>{canManage && <button className="co-primary" onClick={() => openPeople()}><Smartphone size={17} />Connect a phone</button>}</div>
    {devices.length > 0 && <div className="co-connection-filters">
      <label>Find a person or phone<input type="search" aria-label="Search connections" placeholder="Person or phone name" value={query} onChange={event => { setQuery(event.target.value); changePage(0); }} /></label>
      <label>Access<select aria-label="Filter connection access" value={access} onChange={event => { setAccess(event.target.value); changePage(0); }}><option value="allowed">Allowed ({allowed})</option><option value="revoked">Revoked ({devices.length - allowed})</option><option value="all">All connections ({devices.length})</option></select></label>
      {(query || access !== "allowed") && <button className="co-secondary" onClick={() => { setQuery(""); setAccess("allowed"); changePage(0); }}>Reset filters</button>}
    </div>}
    {!devices.length ? <div className="co-empty"><Smartphone size={28} /><h3>No phone connections yet</h3><p>{canManage ? "Add an employee, then select Connect phone to create their connection code." : "Your manager can create a connection code for your phone."}</p>{canManage && <button className="co-secondary" onClick={() => openPeople()}>Open People & teams<ArrowRight size={16} /></button>}</div> : !filtered.length ? <div className="co-empty"><Search size={24} /><h3>No matching connections</h3><p>Try another name or include revoked access.</p><button className="co-secondary" onClick={() => { setQuery(""); setAccess("all"); changePage(0); }}>Show all connections</button></div> : <div className="co-connections-scroll" ref={list}>
      <table className="co-connections-table"><caption className="co-sr-only">Phones authorized to send measurements, with their latest upload and access controls.</caption><thead><tr><th scope="col">Person / phone</th><th scope="col">Access</th><th scope="col">Last upload</th><th scope="col">Actions</th></tr></thead><tbody>{page.items.map(device => {
        const person = names.get(device.member_id);
        const paused = person && !person.sharing;
        return <tr key={device.id} data-testid={`connection-${device.id}`}><th scope="row"><strong>{person?.name ?? "Person unavailable"}</strong><span>{device.name}</span><small>{device.source === "recording" ? "Demo recording" : "Wearable via phone"}</small></th><td data-label="Access"><span className={`co-access-badge${device.revoked ? " revoked" : ""}`}>{device.revoked ? "Revoked" : "Allowed"}</span>{paused && <small>Sharing paused</small>}</td><td data-label="Last upload">{paused ? "Hidden while sharing is paused" : device.last_received_at ? <time dateTime={new Date(device.last_received_at * 1000).toISOString()}>{new Date(device.last_received_at * 1000).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</time> : "No uploads yet"}</td><td className="co-connection-actions">{!device.revoked && <button className="co-secondary" aria-label={`Revoke ${device.name}`} disabled={busy} onClick={() => onRevoke(device)}><Trash2 size={15} />Revoke access</button>}{device.revoked && canManage && person && <button className="co-secondary" onClick={() => openPeople(person.id)}>Reconnect phone<ArrowRight size={15} /></button>}{device.revoked && !canManage && <span>Uploads blocked</span>}</td></tr>;
      })}</tbody></table>
    </div>}
    {devices.length > 0 && <RosterPagination {...page} label="Connections" itemLabel="connections" onPage={changePage} onSize={size => { setPageSize(size); changePage(0); }} />}
    <footer className="co-panel-foot">Revoke access to stop a phone from sending measurements. Employees control sharing from their phone.</footer>
  </section>;
}
