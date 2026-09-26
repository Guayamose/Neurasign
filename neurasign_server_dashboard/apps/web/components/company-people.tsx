"use client";

import { useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { Building2, Copy, Plus, QrCode, ShieldCheck, Smartphone, Trash2, X } from "lucide-react";

export type Team = { id: string; name: string };
type Person = { id: string; name: string; team_id?: string | null; sharing: boolean };
export type DashboardAccount = { id: string; name: string; email: string; role: string; team_ids?: string[] };
type Api = <T>(path: string, method?: string, body?: unknown) => Promise<T>;
export function CompanyPeople({ org, teams, people, accounts, owner, canManage, api, reload }: {
  org: string; teams: Team[]; people: Person[]; accounts: DashboardAccount[]; owner: boolean;
  canManage: boolean; api: Api; reload: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [invite, setInvite] = useState("");
  const [code, setCode] = useState<{ link: string; name: string; expires: number } | null>(null);
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, []);
  async function act(fn: () => Promise<void>) { setBusy(true); setError(""); try { await fn(); await reload(); } catch (e) { setError(e instanceof Error ? e.message : "Please retry."); } finally { setBusy(false); } }
  const canManagePerson = (person: Person) => canManage && (owner || teams.some(team => team.id === person.team_id));
  const path = `/organizations/${org}`;
  const seconds = code ? Math.min(300, Math.max(0, Math.ceil(code.expires - now / 1000))) : 0;
  return <>
    {error && <div className="co-message error" role="alert">{error}</div>}
    <div className="co-two-columns">
      <section className="co-panel co-form-panel"><div className="co-panel-head"><h2><Building2 size={18} /> Teams</h2><span className="co-chip">{teams.length}</span></div>
        <div className="co-team-tags">{teams.map(team => <span className="co-chip" key={team.id}>{team.name} · {people.filter(p => p.team_id === team.id).length}</span>)}</div>
        {!teams.length && <p>{owner ? "Create a team to add employees." : "Your owner needs to assign you a team."}</p>}
        {owner && <form onSubmit={e => { e.preventDefault(); const form = e.currentTarget; const data = new FormData(form); void act(async () => { await api(`${path}/teams`, "POST", { name: data.get("name") }); form.reset(); }); }}><label>New team<input name="name" placeholder="Operations" minLength={2} maxLength={80} required /></label><button className="co-secondary" disabled={busy}><Plus size={15} />Create team</button></form>}
      </section>
      {canManage && <section className="co-panel co-form-panel"><h2>Add an employee</h2><p>One profile per person. No employee account needed.</p><form onSubmit={e => { e.preventDefault(); const form = e.currentTarget; const data = new FormData(form); void act(async () => { await api(`${path}/employees`, "POST", { name: data.get("name"), team_id: data.get("team") }); form.reset(); }); }}><label>Employee name<input name="name" placeholder="Alex Morgan" minLength={2} maxLength={80} required /></label><label>Team<select name="team" aria-label="Employee team" required defaultValue=""><option value="" disabled>Select a team</option>{teams.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}</select></label><button className="co-primary" disabled={busy || !teams.length}><Plus size={15} />Add employee</button></form></section>}
    </div>
    <section className="co-panel"><div className="co-panel-head"><h2>Employees</h2><span className="co-chip">{people.length} people</span></div>
      {!people.length && <div className="co-empty"><Smartphone size={30} /><h3>Ready for your first connection</h3><p>Add an employee, then connect their phone.</p></div>}
      {people.map(person => <div className="co-list-row co-employee-row" key={person.id}><span className="co-avatar">{person.name[0]}</span><div><strong>{person.name}</strong><small>{person.sharing ? "Sharing enabled" : "Sharing paused"}</small></div>
        {canManagePerson(person) ? <select aria-label={`Team for ${person.name}`} value={person.team_id ?? ""} disabled={busy} onChange={e => void act(async () => { await api(`${path}/employees/${person.id}`, "PATCH", { name: person.name, team_id: e.target.value }); })}><option value="" disabled>Unassigned</option>{teams.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}</select> : <span>{teams.find(t => t.id === person.team_id)?.name}</span>}
        {canManagePerson(person) && <><button className="co-secondary" disabled={busy} onClick={() => void act(async () => { const result = await api<{ token: string; expires_at: number }>(`${path}/employees/${person.id}/enrollments`, "POST", { source: "wearable" }); const params = new URLSearchParams({ server: window.location.origin, token: result.token }); setCode({ link: `neurasign://enroll#${params}`, name: person.name, expires: result.expires_at }); })}><QrCode size={15} />Connect phone</button><button className="co-icon" aria-label={`Remove ${person.name}`} disabled={busy} onClick={() => { if (window.confirm(`Remove ${person.name}? All their phones will lose access.`)) void act(async () => { await api(`${path}/employees/${person.id}`, "DELETE"); }); }}><Trash2 size={15} /></button></>}
      </div>)}
    </section>
    {owner && <section className="co-panel co-form-panel"><h2><ShieldCheck size={18} /> Dashboard access</h2><p>Managers can only see their assigned teams.</p>
      {accounts.map(account => <div className="co-list-row" key={account.id}><div><strong>{account.name}</strong><small>{account.email} · {account.role}</small></div>{account.role === "manager" && <><div className="co-team-tags">{teams.map(team => <label className="co-check" key={team.id}><input type="checkbox" checked={account.team_ids?.includes(team.id) ?? false} disabled={busy} onChange={e => void act(async () => { const ids = new Set(account.team_ids); e.target.checked ? ids.add(team.id) : ids.delete(team.id); await api(`${path}/members/${account.id}/teams`, "PATCH", { team_ids: [...ids] }); })} />{team.name}</label>)}</div><button className="co-icon" aria-label={`Remove access for ${account.name}`} disabled={busy} onClick={() => { if (window.confirm(`Remove dashboard access for ${account.name}?`)) void act(async () => { await api(`${path}/members/${account.id}`, "DELETE"); }); }}><Trash2 size={15} /></button></>}</div>)}
      <form onSubmit={e => { e.preventDefault(); const data = new FormData(e.currentTarget); void act(async () => { const result = await api<{ token: string }>(`${path}/invitations`, "POST", { email: data.get("email"), role: "manager", team_ids: data.getAll("teams") }); setInvite(`${window.location.origin}/#invite=${encodeURIComponent(result.token)}`); }); }}><label>Manager email<input name="email" type="email" required /></label><div className="co-team-tags">{teams.map(team => <label className="co-check" key={team.id}><input name="teams" type="checkbox" value={team.id} />{team.name}</label>)}</div><button className="co-secondary" disabled={busy || !teams.length}>Create manager invitation</button></form>
      {invite && <div className="co-secret"><strong>Share this invitation · valid for 72 hours</strong><input aria-label="Invitation link" readOnly value={invite} /><button className="co-secondary" onClick={() => void act(() => navigator.clipboard.writeText(invite))}><Copy size={14} />Copy invitation</button></div>}
    </section>}
    {code && <div className="co-modal-backdrop"><section className="co-modal" role="dialog" aria-modal="true" aria-label="Connect employee phone"><button className="co-icon co-modal-close" aria-label="Close connection code" onClick={() => setCode(null)}><X size={20} /></button><QrCode size={28} /><h2>Connect {code.name}’s phone</h2><p>Open NEURASIGN Link on the phone and scan.</p>{seconds > 0 ? <><div className="co-qr"><QRCodeSVG value={code.link} size={240} marginSize={3} level="M" /></div><span className="co-chip">One use · {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, "0")} left</span><p>Confirm the company and name on the phone.</p><details><summary>Use a connection link</summary><input aria-label="Phone connection link" readOnly value={code.link} /><button className="co-secondary" onClick={() => void act(() => navigator.clipboard.writeText(code.link))}><Copy size={14} />Copy link</button></details></> : <p role="status">Code expired. Close this window and create a new one.</p>}</section></div>}
  </>;
}
