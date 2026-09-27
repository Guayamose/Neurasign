"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { ArrowRight, Building2, Check, ChevronDown, Copy, LockKeyhole, Pause, Plus, QrCode, Search, ShieldCheck, Smartphone, Trash2, UserPlus, Users, X } from "lucide-react";
import { RosterPagination } from "./roster-pagination";
import { rosterPage, selectRoster, type RosterSort } from "@/lib/company-roster";
import "./company-details.css";

export type Team = { id: string; name: string };
type Person = { id: string; name: string; team_id?: string | null; sharing: boolean };
export type DashboardAccount = { id: string; name: string; email: string; role: string; team_ids?: string[] };
type Api = <T>(path: string, method?: string, body?: unknown) => Promise<T>;
type ConnectionCode = { link: string; name: string; personId: string; expires: number };

export function CompanyPeople({ org, teams, people, accounts, owner, canManage, focusPersonId, startSetup = false, api, reload }: {
  org: string; teams: Team[]; people: Person[]; accounts: DashboardAccount[]; owner: boolean;
  canManage: boolean; focusPersonId?: string; startSetup?: boolean; api: Api; reload: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [invite, setInvite] = useState(""), [copied, setCopied] = useState("");
  const [query, setQuery] = useState("");
  const [teamFilter, setTeamFilter] = useState("");
  const [sharingFilter, setSharingFilter] = useState("");
  const [sort, setSort] = useState<RosterSort>("name");
  const [pageIndex, setPageIndex] = useState(0);
  const [pageSize, setPageSize] = useState(25);
  const [setupOpen, setSetupOpen] = useState(startSetup || !people.length);
  const [focusedPersonId, setFocusedPersonId] = useState<string>();
  const listRef = useRef<HTMLDivElement>(null);
  const focusRow = useRef<HTMLDivElement>(null);
  const [code, setCode] = useState<ConnectionCode | null>(null);
  const [now, setNow] = useState(Date.now());
  const dialog = useRef<HTMLElement>(null);
  const connectionTrigger = useRef<HTMLElement | null>(null);
  const dialogOpen = code !== null;
  const targetName = people.find(person => person.id === focusPersonId)?.name;

  useEffect(() => {
    if (!focusPersonId || !targetName) return;
    setFocusedPersonId(focusPersonId); setQuery(targetName); setTeamFilter(""); setSharingFilter(""); setPageIndex(0); setSetupOpen(false);
  }, [focusPersonId, targetName]);
  useEffect(() => {
    if (!focusedPersonId) return;
    const frame = requestAnimationFrame(() => {
      focusRow.current?.querySelector<HTMLButtonElement>("button")?.focus({ preventScroll: true });
      focusRow.current?.scrollIntoView({ block: "center" });
    });
    return () => cancelAnimationFrame(frame);
  }, [focusedPersonId]);

  useEffect(() => {
    if (!dialogOpen) return;
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), 1000);
    const previousFocus = connectionTrigger.current ?? document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog.current?.querySelector<HTMLButtonElement>("button")?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); setCode(null); }
      if (event.key !== "Tab") return;
      const elements = Array.from(dialog.current?.querySelectorAll<HTMLElement>("button:not(:disabled), input:not(:disabled), summary, [tabindex='0']") ?? []).filter(element => {
        const closedDetails = element.closest("details:not([open])");
        if (closedDetails && !closedDetails.querySelector(":scope > summary")?.contains(element)) return false;
        return element.getClientRects().length > 0;
      });
      const first = elements[0], last = elements.at(-1);
      if (!first || !last) { event.preventDefault(); return; }
      if (!dialog.current?.contains(document.activeElement)) { event.preventDefault(); (event.shiftKey ? last : first).focus(); return; }
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      clearInterval(timer);
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previousOverflow;
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, [dialogOpen]);

  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(""), 2500);
    return () => clearTimeout(timer);
  }, [copied]);

  async function act(fn: () => Promise<void>) {
    setBusy(true); setError("");
    try { await fn(); await reload(); }
    catch (e) { setError(e instanceof Error ? e.message : "Something went wrong. Please try again."); }
    finally { setBusy(false); }
  }
  async function copy(value: string, kind: string) {
    setError("");
    try { await navigator.clipboard.writeText(value); setCopied(kind); }
    catch { setError("Could not copy automatically. Select the link and copy it manually."); }
  }
  async function createCode(person: { id: string; name: string }) {
    const result = await api<{ token: string; expires_at: number }>(`${path}/employees/${person.id}/enrollments`, "POST", { source: "wearable" });
    const params = new URLSearchParams({ server: window.location.origin, token: result.token });
    setNow(Date.now()); setCopied("");
    setCode({ link: `neurasign://enroll#${params}`, name: person.name, personId: person.id, expires: result.expires_at });
  }
  const canManagePerson = (person: Person) => canManage && (owner || teams.some(team => team.id === person.team_id));
  const path = `/organizations/${org}`;
  const seconds = code ? Math.min(300, Math.max(0, Math.ceil(code.expires - now / 1000))) : 0;
  const filteredPeople = useMemo(() => selectRoster(people, teams, { query, team: teamFilter, sharing: sharingFilter, sort }).filter(person => !focusedPersonId || person.id === focusedPersonId), [people, teams, query, teamFilter, sharingFilter, sort, focusedPersonId]);
  const page = rosterPage(filteredPeople, pageIndex, pageSize);
  useEffect(() => { if (page.page !== pageIndex) setPageIndex(page.page); }, [page.page, pageIndex]);
  function changeFilter(update: () => void) { update(); setFocusedPersonId(undefined); setPageIndex(0); }
  function changePage(next: number) { setPageIndex(next); if (listRef.current) listRef.current.scrollTop = 0; }

  return <div className="co-people-admin">
    {error && !code && <div className="co-message error" role="alert">{error}<button aria-label="Dismiss error" onClick={() => setError("")}><X size={16} /></button></div>}
    {canManage && <details className="co-people-setup-disclosure" open={setupOpen} onToggle={event => setSetupOpen(event.currentTarget.open)}><summary><UserPlus size={19} /><span><strong>Add people or teams</strong><small>Create a profile, then connect their phone.</small></span><ChevronDown size={18} /></summary><div className="co-setup-disclosure-body"><ol className="co-setup-path" aria-label="Employee setup steps">
      <li className={teams.length ? "complete" : ""}><span>{teams.length ? <Check size={16} /> : "1"}</span><div><strong>Create a team</strong><small>Group your people</small></div><ArrowRight size={16} /></li>
      <li className={people.length ? "complete" : ""}><span>{people.length ? <Check size={16} /> : "2"}</span><div><strong>Add an employee</strong><small>No employee account needed</small></div><ArrowRight size={16} /></li>
      <li><span><Smartphone size={16} /></span><div><strong>Connect their phone</strong><small>Scan the code below</small></div></li>
    </ol>

    <div className="co-people-setup">
      <section className="co-panel co-form-panel co-team-setup">
        <div className="co-detail-section-head"><span className="co-detail-icon"><Building2 size={19} /></span><div><h2>Teams</h2><p>Keep everyone in the right group.</p></div><span className="co-chip">{teams.length}</span></div>
        <div className="co-team-tags">{teams.map(team => <span className="co-team-tag" key={team.id}>{team.name}<b>{people.filter(person => person.team_id === team.id).length}</b></span>)}</div>
        {!teams.length && <p className="co-setup-hint">{owner ? "Start with a name for your first team." : "Your owner needs to assign you a team."}</p>}
        {owner && <form className="co-team-create-form" onSubmit={e => {
          e.preventDefault(); const form = e.currentTarget; const data = new FormData(form);
          void act(async () => { await api(`${path}/teams`, "POST", { name: data.get("name") }); form.reset(); });
        }}><label>New team<input name="name" placeholder="e.g. Operations" minLength={2} maxLength={80} required /></label><button className="co-secondary" disabled={busy}><Plus size={15} />Create team</button></form>}
      </section>

      {canManage && <section className="co-panel co-form-panel co-employee-setup">
        <div className="co-detail-section-head"><span className="co-detail-icon"><UserPlus size={19} /></span><div><h2>Add an employee</h2><p>Their phone links readings to this profile.</p></div></div>
        <form onSubmit={e => {
          e.preventDefault(); const form = e.currentTarget; const data = new FormData(form);
          void act(async () => { await api(`${path}/employees`, "POST", { name: data.get("name"), team_id: data.get("team") }); form.reset(); });
        }}><fieldset disabled={busy || !teams.length} className="co-employee-fields"><label>Employee name<input name="name" placeholder="Alex Morgan" minLength={2} maxLength={80} required /></label><label>Team<select name="team" aria-label="Employee team" required defaultValue=""><option value="" disabled>Select a team</option>{teams.map(team => <option key={team.id} value={team.id}>{team.name}</option>)}</select></label></fieldset><div className="co-form-action"><span>{!teams.length ? "Create a team first." : "You can connect their phone next."}</span><button className="co-primary" disabled={busy || !teams.length}><Plus size={15} />Add employee</button></div></form>
      </section>}
    </div></div></details>}

    <section className="co-panel co-roster">
      <div className="co-panel-head"><div><h2>Employees <span className="co-inline-count">{people.length}</span></h2><p>Connect a phone or change an employee’s team.</p></div>{canManage && !setupOpen && <button className="co-secondary" onClick={() => { setSetupOpen(true); requestAnimationFrame(() => document.querySelector<HTMLInputElement>('.co-employee-setup input[name="name"]')?.focus()); }}><UserPlus size={17} />Add employee</button>}</div>
      {people.length > 0 && <div className="co-roster-filters co-admin-filters">
        <label className="co-filter-search">Find a person or team<input type="search" aria-label="Search employees or teams" placeholder="Name or team" value={query} onChange={event => changeFilter(() => setQuery(event.target.value))} /></label>
        <label>Team<select aria-label="Filter employee team" value={teamFilter} onChange={event => changeFilter(() => setTeamFilter(event.target.value))}><option value="">All teams</option><option value="unassigned">Unassigned</option>{teams.map(team => <option key={team.id} value={team.id}>{team.name}</option>)}</select></label>
        <label>Sharing<select aria-label="Filter employee sharing" value={sharingFilter} onChange={event => changeFilter(() => setSharingFilter(event.target.value))}><option value="">All sharing states</option><option value="enabled">Sharing enabled</option><option value="paused">Sharing paused</option></select></label>
        <label>Sort by<select aria-label="Sort employees" value={sort} onChange={event => changeFilter(() => setSort(event.target.value as RosterSort))}><option value="name">Name A–Z</option><option value="name_desc">Name Z–A</option></select></label>
        {(query || teamFilter || sharingFilter) && <button className="co-secondary" onClick={() => changeFilter(() => { setQuery(""); setTeamFilter(""); setSharingFilter(""); })}>Clear filters</button>}
      </div>}
      {focusedPersonId && <div className="co-focused-person-note" role="status"><span>Connect this person’s phone using the button below.</span><button className="co-text" onClick={() => changeFilter(() => setQuery(""))}>Show all employees</button></div>}
      {!people.length ? <div className="co-empty"><span className="co-empty-detail-icon"><Users size={26} /></span><h3>Your team starts here</h3><p>{canManage ? <>Add your first employee above. Then select <strong>Connect phone</strong>.</> : "Your manager will add people to this workspace."}</p></div> : !filteredPeople.length ? <div className="co-empty"><Search size={24} /><h3>No matching people</h3><button className="co-text" onClick={() => changeFilter(() => { setQuery(""); setTeamFilter(""); setSharingFilter(""); })}>Clear filters</button></div> : <div ref={listRef} className="co-admin-list" role="list" aria-label="Employees">{page.items.map(person => <div className={`co-list-row co-employee-row${person.id === focusedPersonId ? " targeted" : ""}`} role="listitem" key={person.id} data-person-id={person.id} ref={person.id === focusedPersonId ? focusRow : undefined}>
        <span className="co-avatar">{person.name.split(" ").map(part => part[0]).slice(0, 2).join("")}</span>
        <div className="co-employee-identity"><strong>{person.name}</strong><small className={person.sharing ? "co-sharing-on" : ""}>{person.sharing ? <><span className="co-tiny-dot" />Sharing enabled</> : <><Pause size={10} />Sharing paused</>}</small></div>
        {canManagePerson(person) ? <select aria-label={`Team for ${person.name}`} value={person.team_id ?? ""} disabled={busy} onChange={e => { const teamId = e.target.value; void act(async () => { await api(`${path}/employees/${person.id}`, "PATCH", { name: person.name, team_id: teamId }); }); }}><option value="" disabled>Unassigned</option>{teams.map(team => <option key={team.id} value={team.id}>{team.name}</option>)}</select> : <span className="co-employee-team">{teams.find(team => team.id === person.team_id)?.name ?? "Unassigned"}</span>}
        {canManagePerson(person) && <div className="co-employee-actions"><button className="co-secondary" disabled={busy} onClick={e => { connectionTrigger.current = e.currentTarget; void act(() => createCode(person)); }}><QrCode size={15} />Connect phone</button><button className="co-icon co-remove-person" aria-label={`Remove ${person.name}`} disabled={busy} onClick={() => { if (window.confirm(`Remove ${person.name}? All their phones will lose access.`)) void act(async () => { await api(`${path}/employees/${person.id}`, "DELETE"); }); }}><Trash2 size={15} /></button></div>}
      </div>)}</div>}
      {people.length > 0 && <RosterPagination {...page} label="Employees" onPage={changePage} onSize={size => { setPageSize(size); changePage(0); }} />}
      <footer className="co-panel-foot"><span><LockKeyhole size={13} />Employees control sharing from their phone.</span><span>Sharing enabled does not mean a device is connected.</span></footer>
    </section>

    {owner && <details className="co-panel co-access-details"><summary><span className="co-detail-icon"><ShieldCheck size={19} /></span><span><strong>Dashboard access</strong><small>Invite managers and choose the teams they can see.</small></span><span className="co-chip">{accounts.length} {accounts.length === 1 ? "account" : "accounts"}</span><ChevronDown size={17} /></summary><div className="co-access-body">
      <div className="co-access-accounts">{accounts.map(account => <div className="co-list-row" key={account.id}><div><strong>{account.name}<span className="co-account-role">{account.role}</span></strong><small>{account.email}</small></div>{account.role === "manager" && <><div className="co-team-tags">{teams.map(team => <label className="co-check" key={team.id}><input type="checkbox" checked={account.team_ids?.includes(team.id) ?? false} disabled={busy} onChange={e => { const checked = e.target.checked; void act(async () => { const ids = new Set(account.team_ids); checked ? ids.add(team.id) : ids.delete(team.id); await api(`${path}/members/${account.id}/teams`, "PATCH", { team_ids: [...ids] }); }); }} />{team.name}</label>)}</div><button className="co-icon co-remove-person" aria-label={`Remove access for ${account.name}`} disabled={busy} onClick={() => { if (window.confirm(`Remove dashboard access for ${account.name}?`)) void act(async () => { await api(`${path}/members/${account.id}`, "DELETE"); }); }}><Trash2 size={15} /></button></>}</div>)}</div>
      <form className="co-manager-form" onSubmit={e => {
        e.preventDefault(); const data = new FormData(e.currentTarget);
        void act(async () => { const result = await api<{ token: string }>(`${path}/invitations`, "POST", { email: data.get("email"), role: "manager", team_ids: data.getAll("teams") }); setInvite(`${window.location.origin}/#invite=${encodeURIComponent(result.token)}`); setCopied(""); });
      }}><h3>Invite a manager</h3><label>Manager email<input name="email" type="email" placeholder="name@company.com" required /></label><fieldset><legend>Teams they can view</legend><div className="co-team-tags">{teams.map(team => <label className="co-check" key={team.id}><input name="teams" type="checkbox" value={team.id} />{team.name}</label>)}</div>{!teams.length && <p>Create a team before inviting a manager.</p>}</fieldset><button className="co-secondary" disabled={busy || !teams.length}>Create manager invitation<ArrowRight size={14} /></button></form>
      {invite && <div className="co-secret"><strong>Invitation ready</strong><p>Send this link to your manager. It expires in 72 hours.</p><input aria-label="Invitation link" readOnly value={invite} onFocus={e => e.currentTarget.select()} /><button className="co-secondary" onClick={() => void copy(invite, "invite")}>{copied === "invite" ? <Check size={14} /> : <Copy size={14} />}{copied === "invite" ? "Copied" : "Copy invitation"}</button><span role="status" className="co-copy-status">{copied === "invite" ? "Invitation copied to clipboard." : ""}</span></div>}
    </div></details>}

    {code && <div className="co-modal-backdrop" onClick={event => { if (event.target === event.currentTarget) setCode(null); }}><section ref={dialog} className="co-modal co-connection-modal" role="dialog" aria-modal="true" aria-label="Connect employee phone" aria-describedby="co-connect-description">
      <button className="co-icon co-modal-close" aria-label="Close connection code" onClick={() => setCode(null)}><X size={20} /></button>
      <span className="co-connection-icon"><Smartphone size={23} /></span><span className="co-eyebrow">Phone connection</span><h2 id="co-connect-title">Connect {code.name}’s phone</h2><p id="co-connect-description">Open <strong>NEURASIGN Link</strong> on their phone and scan this code.</p>
      {error && <div className="co-message error" role="alert">{error}</div>}
      {seconds > 0 ? <><div className="co-qr"><QRCodeSVG value={code.link} size={216} marginSize={3} level="M" title={`Connection code for ${code.name}`} /></div><span className={`co-code-time ${seconds < 60 ? "expiring" : ""}`}>One use<span>·</span>Expires in {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, "0")}</span><div className="co-phone-confirm"><ShieldCheck size={16} /><p>Confirm the company and name on the phone, then choose what to share.</p></div><details className="co-connection-link"><summary>Use a connection link<ChevronDown size={14} /></summary><input aria-label="Phone connection link" readOnly value={code.link} onFocus={e => e.currentTarget.select()} /><button className="co-secondary" onClick={() => void copy(code.link, "phone")}>{copied === "phone" ? <Check size={14} /> : <Copy size={14} />}{copied === "phone" ? "Copied" : "Copy link"}</button><span role="status" className="co-copy-status">{copied === "phone" ? "Connection link copied to clipboard." : ""}</span></details></> : <div className="co-code-expired"><QrCode size={36} /><h3>This code has expired</h3><p role="status">Generate a new code to connect this phone.</p><button className="co-primary" disabled={busy} onClick={() => void act(() => createCode({ id: code.personId, name: code.name }))}>Create new code</button></div>}
    </section></div>}
  </div>;
}
