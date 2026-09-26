"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { getApp, getApps, initializeApp } from "firebase/app";
import { browserSessionPersistence, connectAuthEmulator, createUserWithEmailAndPassword, getAuth, onIdTokenChanged, sendEmailVerification, sendPasswordResetEmail, setPersistence, signInWithEmailAndPassword, signOut, updateProfile, type Auth, type User } from "firebase/auth";
import { Activity, ArrowRight, Building2, Check, ChevronRight, CircleHelp, Copy, HeartPulse, History, LoaderCircle, LogOut, Pause, Play, Plus, Radio, RefreshCw, ShieldCheck, Smartphone, Trash2, UserRound, Users, Waves } from "lucide-react";
import { Chart } from "./monitoring-dashboard";
import { SignalTiles, SignalExplorer, type Signal, type MetricDefinition } from "./company-signals";
import { CompanyPeople, type Team, type DashboardAccount } from "./company-people";
import "./company-workspace.css";

type Config = { enabled: boolean; firebase: { apiKey: string; projectId: string; authDomain: string }; emulator_url: string | null; demo_available: boolean; test_account?: { email: string; password: string } | null };
type Company = { id: string; name: string; role?: string; retention_days: number };
type Features = { heart_rate: number | null; hrv: number | null; eda: number | null; temperature: number | null; movement: number | null };
type Reading = { id: string; timestamp: number; received_at: number; window_seconds: number; features: Features; source: "wearable" | "recording"; quality: number | null };
type Member = { team_id?: string | null; id: string; name: string; email: string; role: "owner" | "manager" | "employee"; sharing: boolean; status: "paused" | "waiting" | "current" | "stale"; latest: Reading | null; features: Features; signals?: Signal[] };
type Device = { id: string; name: string; member_id: string; source: "wearable" | "recording"; revoked: boolean; last_received_at: number | null };
type Snapshot = { teams: Team[]; accounts: DashboardAccount[]; metric_catalog?: MetricDefinition[]; organization: Company; me: Member; members: Member[]; devices: Device[]; server_time: number; audit: { id: string; action: string; time: number }[] };
type Account = { name: string; email: string; organizations: Company[] };
type Tab = "overview" | "people" | "devices" | "sharing";

const metrics = {
  heart_rate: { name: "Heart rate", short: "HR", unit: "bpm", digits: 0, meaning: "Heartbeats per minute, summarized over the device’s measurement window.", color: "#83a567" },
  hrv: { name: "HRV · RMSSD", short: "HRV", unit: "ms", digits: 1, meaning: "Variation between successive beat intervals, reported as RMSSD. It requires interval data; heart rate alone is insufficient.", color: "#a396b9" },
  eda: { name: "Skin conductance", short: "EDA", unit: "µS", digits: 2, meaning: "Skin conductance varies with sweat-gland activity. It cannot identify an emotion or its cause.", color: "#74a397" },
  temperature: { name: "Skin temperature", short: "Skin temp", unit: "°C", digits: 1, meaning: "Temperature at the sensor’s contact point, not core body temperature.", color: "#bd9a6d" },
  movement: { name: "Movement", short: "Movement", unit: "g", digits: 3, meaning: "Variability of acceleration magnitude within the measurement window. This is not a step count.", color: "#91a873" },
};
const format = (value: number | null | undefined, digits = 0) => value == null ? "—" : value.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
const timeLabel = (value: number | null | undefined) => value ? new Date(value * 1000).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "No readings yet";
const stateLabel = (status: Member["status"]) => ({ paused: "Sharing paused", waiting: "Waiting for device", current: "Current", stale: "No recent readings" }[status]);
const errorText = (error: unknown) => {
  const code = (error as { code?: string })?.code;
  if (code === "auth/invalid-credential") return "The email or password is incorrect.";
  if (code === "auth/email-already-in-use") return "An account already uses this email. Sign in instead.";
  if (code === "auth/weak-password") return "Choose a stronger password with at least 12 characters.";
  if (code === "auth/too-many-requests") return "Too many attempts. Please try again later.";
  if (code === "auth/operation-not-allowed") return "Email sign-in is not enabled for this deployment.";
  return error instanceof Error ? error.message : "Something went wrong. Please retry.";
};

export default function CompanyWorkspace() {
  const [config, setConfig] = useState<Config | null>(null);
  const [auth, setAuth] = useState<Auth | null>(null);
  const [session, setSession] = useState<{ user: User | null }>({ user: null });
  const user = session.user;
  const [account, setAccount] = useState<Account | null>(null);
  const [org, setOrg] = useState("");
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [selected, setSelected] = useState("");
  const [rows, setRows] = useState<Reading[]>([]);
  const [metric, setMetric] = useState<keyof Features>("heart_rate");
  const [tab, setTab] = useState<Tab>("overview");
  const [signup, setSignup] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [offline, setOffline] = useState(false);
  const [invite, setInvite] = useState("");
  const [inviteToken, setInviteToken] = useState("");
  const [credential, setCredential] = useState("");
  const [confirmation, setConfirmation] = useState<"" | "DELETE">("");
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    let alive = true, unsubscribe: (() => void) | undefined;
    async function start() {
      try {
        const response = await fetch("/api/v1/config", { cache: "no-store" });
        if (!response.ok) throw new Error("The workspace service is unavailable.");
        const settings: Config = await response.json();
        if (!alive) return;
        setConfig(settings);
        const incoming = new URLSearchParams(window.location.hash.slice(1)).get("invite");
        if (incoming) { setInviteToken(incoming); window.history.replaceState(null, "", window.location.pathname); }
        if (!settings.enabled) return;
        const app = getApps().some(app => app.name === "neurasign-workspace") ? getApp("neurasign-workspace") : initializeApp(settings.firebase, "neurasign-workspace");
        const instance = getAuth(app);
        if (settings.emulator_url && !instance.emulatorConfig) connectAuthEmulator(instance, settings.emulator_url, { disableWarnings: true });
        await setPersistence(instance, browserSessionPersistence);
        if (new URLSearchParams(window.location.search).get("login") === "1") {
          await signOut(instance);
          window.history.replaceState(null, "", window.location.pathname);
        }
        if (!alive) return;
        setAuth(instance);
        unsubscribe = onIdTokenChanged(instance, next => { if (alive) setSession({ user: next }); });
      } catch (error) { if (alive) setError(errorText(error)); }
    }
    void start();
    return () => { alive = false; unsubscribe?.(); };
  }, []);

  const api = useCallback(async <T,>(path: string, method = "GET", body?: unknown): Promise<T> => {
    if (!user) throw new Error("Please sign in.");
    const token = await user.getIdToken();
    const response = await fetch(`/api/v1${path}`, { method, headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body), cache: "no-store", signal: AbortSignal.timeout(20000) });
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : `Request failed (${response.status}).`);
    return result;
  }, [user]);

  const act = async (operation: () => Promise<void>) => {
    setBusy(true); setError(""); setNotice("");
    try { await operation(); setRefresh(value => value + 1); }
    catch (error) { setError(errorText(error)); }
    finally { setBusy(false); }
  };

  useEffect(() => {
    let active = true;
    if (!user?.emailVerified) { setAccount(null); setSnapshot(null); setOrg(""); return; }
    api<Account>("/me").then(value => { if (active) { setAccount(value); setOrg(previous => value.organizations.some(item => item.id === previous) ? previous : value.organizations[0]?.id ?? ""); } }).catch(error => { if (active) setError(errorText(error)); });
    return () => { active = false; };
  }, [api, user?.emailVerified, refresh]);

  useEffect(() => {
    let active = true, running = false;
    setSnapshot(null); setRows([]); setCredential(""); setInvite("");
    if (!org || !user?.emailVerified) return;
    async function poll() {
      if (running) return;
      running = true;
      try {
        const value = await api<Snapshot>(`/organizations/${org}/dashboard`);
        if (active) { setSnapshot(value); setSelected(previous => value.members.some(person => person.id === previous) ? previous : value.members[0]?.id ?? ""); setOffline(false); }
      } catch (error) { if (active) { setOffline(true); setSnapshot(null); setRows([]); setError(errorText(error)); } }
      finally { running = false; }
    }
    void poll();
    const timer = setInterval(poll, 4000);
    return () => { active = false; clearInterval(timer); };
  }, [api, org, user?.emailVerified]);

  useEffect(() => {
    let active = true;
    if (!org || !selected) { setRows([]); return; }
    api<{ readings: Reading[] }>(`/organizations/${org}/members/${selected}/history`).then(value => { if (active) setRows(value.readings); }).catch(() => { if (active) setRows([]); });
    return () => { active = false; };
  }, [api, org, selected, snapshot?.server_time]);

  const reload = async () => {
    if (org) setSnapshot(await api<Snapshot>(`/organizations/${org}/dashboard`));
  };
  const own = snapshot?.me;
  const canManage = own?.role === "owner" || own?.role === "manager";
  const person = snapshot?.members.find(member => member.id === selected);
  const meta = metrics[metric];
  const signIn = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    void act(async () => {
      if (!auth) throw new Error("Sign-in is still loading.");
      const email = String(fields.get("email")).trim(), password = String(fields.get("password"));
      if (signup) {
        const result = await createUserWithEmailAndPassword(auth, email, password);
        await updateProfile(result.user, { displayName: String(fields.get("name")).trim() });
        await sendEmailVerification(result.user);
        setNotice("Verification email sent. Open its link, then continue here.");
      } else await signInWithEmailAndPassword(auth, email, password);
    });
  };

  return <div className="company-app"><header className="co-header"><a href="/" className="co-logo"><span><Activity size={23} /></span>NEURASIGN<small>Team workspace</small></a><div>{config?.emulator_url && <span className="co-chip">Local development</span>}{config?.demo_available && <a className="co-demo-link" href="/demo">Explore demo<ArrowRight size={14} /></a>}{user && <button className="co-icon" aria-label="Sign out" onClick={() => void act(async () => { if (auth) await signOut(auth); setSignup(false); setCredential(""); setInvite(""); })}><LogOut size={17} /></button>}</div></header>
    {error && <div className="co-message error" role="alert">{error}<button aria-label="Dismiss error" onClick={() => setError("")}>×</button></div>}{notice && <div className="co-message" role="status">{notice}</div>}
    {!config ? <div className="co-loading"><LoaderCircle className="co-spin" />Connecting to NEURASIGN…</div> : !config.enabled ? <main className="co-auth"><Building2 size={30} /><h1>Your company workspace</h1><p>Company sign-in has not been configured for this deployment.</p>{config.demo_available && <a className="co-primary" href="/demo">Explore the recorded demo<ArrowRight size={16} /></a>}</main> : !user ? <main className="co-auth"><span className="co-eyebrow">YOUR TEAM. CONNECTED.</span><h1>{signup ? "Create your account" : "Welcome to NEURASIGN"}</h1><p>Connect your team’s wearables in one workspace.</p><form onSubmit={signIn}>{signup && <label>Full name<input name="name" autoComplete="name" required minLength={2} maxLength={80} /></label>}<label>Work email<input name="email" type="email" autoComplete="email" required /></label><label>Password<input name="password" type="password" autoComplete={signup ? "new-password" : "current-password"} required minLength={signup ? 12 : 1} maxLength={128} /></label><button className="co-primary" disabled={busy || !auth}>{busy ? <LoaderCircle className="co-spin" size={16} /> : <ArrowRight size={16} />}{signup ? "Create account" : "Sign in"}</button></form>{!signup && config.test_account && <aside className="co-test-account" aria-label="Local test account"><strong>Local test account</strong><dl><div><dt>Email</dt><dd>{config.test_account.email}</dd></div><div><dt>Password</dt><dd>{config.test_account.password}</dd></div></dl><button className="co-secondary" disabled={busy || !auth} onClick={() => void act(async () => { if (auth && config.test_account) await signInWithEmailAndPassword(auth, config.test_account.email, config.test_account.password); })}><ArrowRight size={15} />Sign in with test account</button></aside>}<button className="co-text" onClick={() => setSignup(value => !value)}>{signup ? "Already have an account? Sign in" : "New here? Create an account"}</button>{!signup && <button className="co-text" onClick={() => void act(async () => { const input = document.querySelector<HTMLInputElement>('input[name="email"]'); if (!auth || !input?.value) throw new Error("Enter your email address first."); await sendPasswordResetEmail(auth, input.value.trim()); setNotice("If an account exists, a reset link will arrive by email."); })}>Reset password</button>}<footer><ShieldCheck size={14} />Your company’s data stays in its own workspace.</footer></main> : !user.emailVerified ? <main className="co-auth"><ShieldCheck size={32} /><h1>Verify your email</h1><p>Open the verification link sent to <strong>{user.email}</strong>.</p><button className="co-primary" disabled={busy} onClick={() => void act(async () => { await user.reload(); await user.getIdToken(true); setSession({ user }); if (!user.emailVerified) throw new Error("Your email has not been verified yet."); })}>I have verified my email<ArrowRight size={16} /></button><button className="co-text" disabled={busy} onClick={() => void act(async () => { await sendEmailVerification(user); setNotice("Verification email sent."); })}>Resend verification email</button></main> : !account ? <div className="co-loading"><LoaderCircle className="co-spin" />Loading your account…</div> : !org || inviteToken ? <main className="co-auth"><Building2 size={30} /><h1>{inviteToken ? "Join your team" : "Set up your workspace"}</h1><p>{inviteToken ? "Accept the invitation using your verified work email." : "Create your company or enter an invitation code."}</p>{!inviteToken && <form onSubmit={event => { event.preventDefault(); const data = new FormData(event.currentTarget); void act(async () => { const value = await api<Company>("/organizations", "POST", { name: data.get("company") }); setOrg(value.id); }); }}><label>Company name<input name="company" required minLength={2} maxLength={80} placeholder="Your company" /></label><button className="co-primary" disabled={busy}>Create workspace<ArrowRight size={16} /></button></form>}<form onSubmit={event => { event.preventDefault(); void act(async () => { const value = await api<{ organization_id: string }>("/invitations/accept", "POST", { token: inviteToken.trim() }); setOrg(value.organization_id); setInviteToken(""); }); }}><label>Invitation code<input value={inviteToken} onChange={event => setInviteToken(event.target.value)} required minLength={32} maxLength={128} autoComplete="off" /></label><button className="co-secondary" disabled={busy}>Join workspace<ArrowRight size={16} /></button></form>{org && <button className="co-text" onClick={() => setInviteToken("")}>Return to my workspace</button>}</main> : <>
      <nav className="co-nav"><label className="co-company-select"><Building2 size={15} /><select aria-label="Company workspace" value={org} onChange={event => setOrg(event.target.value)}>{account.organizations.map(company => <option key={company.id} value={company.id}>{company.name}</option>)}</select></label>{([{ id: "overview", label: "Team overview", Icon: Activity }, { id: "people", label: "People", Icon: Users }, { id: "devices", label: "Wearables", Icon: Smartphone }, { id: "sharing", label: "My sharing", Icon: ShieldCheck }] as const).map(({ id, label, Icon }) => <button key={id} data-testid={`company-tab-${id}`} className={tab === id ? "active" : ""} onClick={() => { setTab(id); setCredential(""); }}><Icon size={16} />{label}</button>)}</nav>
      {!snapshot ? <div className="co-loading">{offline ? "Workspace unavailable. Reconnecting…" : <><LoaderCircle className="co-spin" />Loading your workspace…</>}</div> : <main className="co-content" data-testid="company-workspace">
        <div className="co-heading"><div><span className="co-eyebrow">{snapshot.organization.name}</span><h1>{({ overview: "Your team at a glance.", people: "People in your workspace.", devices: "Connected wearables.", sharing: "Your data. Your choice." })[tab]}</h1><p>{({ overview: "Current measurements and recent trends.", people: "Teams, employee phones and manager access.", devices: "Device access, signal sources and last contact.", sharing: "Choose when your team can see your measurements." })[tab]}</p></div><span className="co-chip"><i />Connected</span></div>
        {tab === "overview" && <>{!snapshot.members.length && <section className="co-panel co-empty"><Users size={32} /><h2>Connect your first employee</h2><p>Create a team, add an employee and scan their phone’s connection code.</p>{canManage && <button className="co-primary" onClick={() => setTab("people")}><Plus size={16} />Set up your team</button>}</section>}<div className="co-stats"><span><Users size={16} /><strong>{snapshot.members.length}</strong> people</span><span><Radio size={16} /><strong>{snapshot.members.filter(person => (person.status === "current" && person.latest?.source === "wearable") || person.signals?.some(signal => signal.status === "current" && signal.source === "wearable")).length}</strong> current wearable signals</span><span><History size={16} />{snapshot.organization.retention_days}-day retention</span></div><div className="co-people-grid">{snapshot.members.map(member => <button key={member.id} className={`co-person ${selected === member.id ? "selected" : ""}`} data-testid={`company-person-${member.id}`} onClick={() => setSelected(member.id)}><div className="co-person-head"><span className="co-avatar">{member.name[0]}</span><div><h2>{member.name}</h2><small>{snapshot.teams?.find(team => team.id === member.team_id)?.name ?? "Unassigned team"}</small></div><span className={`co-status ${member.status}`}><i />{stateLabel(member.status)}</span></div>{member.signals?.length ? <SignalTiles signals={member.signals} catalog={snapshot.metric_catalog ?? []} /> : <div className="co-readings">{(["heart_rate", "hrv", "eda", "temperature"] as (keyof Features)[]).map(key => <div key={key}><small>{metrics[key].short}</small><strong style={{ color: metrics[key].color }}>{format(member.features[key], metrics[key].digits)}<em>{metrics[key].unit}</em></strong></div>)}</div>}<footer><span>{member.latest?.source === "recording" ? "DEMO RECORDING · " : ""}{member.signals?.length ? "View signal details" : member.latest ? timeLabel(member.latest.timestamp) : member.sharing ? "Waiting for an authorized device" : "Employee controls sharing"}</span><ChevronRight size={14} /></footer></button>)}</div>{person?.signals?.length ? <SignalExplorer key={`${org}:${person.id}`} personId={person.id} name={person.name} org={org} signals={person.signals} catalog={snapshot.metric_catalog ?? []} revision={snapshot.server_time} api={api} /> : null}{person && (person.latest || !person.signals?.length) && <section className="co-panel"><div className="co-panel-head"><div><h2>Signal detail · {person.name}</h2><p>{person.latest ? `${person.latest.source === "recording" ? "Demo recording" : "Device measurements"} · ${person.latest.window_seconds}-second window` : "Measurements will appear after the employee connects a device."}</p></div><span className={`co-status ${person.status}`}>{stateLabel(person.status)}</span></div><div className="co-metric-tabs">{(Object.keys(metrics) as (keyof Features)[]).map(key => <button key={key} className={metric === key ? "active" : ""} aria-pressed={metric === key} onClick={() => setMetric(key)}>{metrics[key].short}</button>)}</div><div className="co-chart-value"><strong>{format(person.features[metric], meta.digits)}</strong><span>{meta.unit}</span><details><summary><CircleHelp size={14} />{meta.name}</summary><p>{meta.meaning}</p></details></div><Chart live unit={meta.unit} series={[{ label: person.name, color: meta.color, points: rows.map(row => ({ time: row.timestamp, value: row.features[metric] })) }]} /><footer className="co-panel-foot"><span>Time measured · missing readings stay as gaps</span><span>{person.latest?.quality == null ? "Quality not reported" : `Reported quality ${format(person.latest.quality * 100)}%`}</span></footer></section>}<div className="co-note"><ShieldCheck size={16} /><span>Physiological measurements only. Workload and fatigue estimates are not inferred for uncalibrated company devices.</span></div></>}
        {tab === "people" && <CompanyPeople key={org} org={org} teams={snapshot.teams ?? []} people={snapshot.members} accounts={snapshot.accounts ?? []} owner={own?.role === "owner"} canManage={canManage} api={api} reload={reload} />}
        {tab === "devices" && <div className="co-two-columns"><section className="co-panel"><div className="co-panel-head"><h2>Device access</h2><span className="co-chip">{snapshot.devices.filter(device => !device.revoked).length} authorized</span></div>{!snapshot.devices.length && <div className="co-empty"><Smartphone size={32} /><h3>No devices connected yet</h3><p>Connect a phone from the People tab.</p></div>}{snapshot.devices.map(device => <div className="co-list-row" key={device.id}><Smartphone size={19} /><div><strong>{device.name}</strong><small>{device.source === "recording" ? "Demo recording" : "Wearable gateway"} · {snapshot.members.find(member => member.id === device.member_id)?.name ?? "Member"}</small><small>{device.revoked ? "Access revoked" : device.last_received_at ? `Last contact ${timeLabel(device.last_received_at)}` : "Waiting for first upload"}</small></div>{!device.revoked && <button className="co-icon" aria-label={`Revoke ${device.name}`} disabled={busy} onClick={() => void act(async () => { await api(`/organizations/${org}/devices/${device.id}`, "DELETE"); setCredential(""); await reload(); })}><Trash2 size={15} /></button>}</div>)}</section><section className="co-panel co-form-panel"><h2>Connect an employee’s phone</h2><p>Go to People, choose an employee and select Connect phone.</p><button className="co-primary" onClick={() => setTab("people")}><Smartphone size={16} />Open People</button><details><summary>Advanced · personal gateway credential</summary><h2>Authorize your device</h2><p>Access is tied to your account. Enable sharing first.</p><form onSubmit={event => { event.preventDefault(); const data = new FormData(event.currentTarget); void act(async () => { const result = await api<{ credential: string }>(`/organizations/${org}/devices`, "POST", { name: data.get("name"), source: data.get("source") }); setCredential(result.credential); await reload(); }); }}><label>Device name<input name="name" placeholder="My wearable" minLength={2} maxLength={80} required /></label><label>Signal source<select name="source"><option value="wearable">Wearable measurements</option><option value="recording">Demo recording</option></select></label><button className="co-primary" disabled={busy || !own?.sharing}><Plus size={15} />Authorize device</button>{!own?.sharing && <button type="button" className="co-text" onClick={() => setTab("sharing")}>Open My sharing<ArrowRight size={14} /></button>}</form>{credential && <div className="co-secret"><strong>Device credential · shown once</strong><p>Keep this credential private. Revoking the device stops uploads.</p><input readOnly aria-label="Device credential" value={credential} /><button className="co-secondary" onClick={() => void act(async () => { await navigator.clipboard.writeText(credential); setNotice("Device credential copied."); })}><Copy size={14} />Copy credential</button><details><summary>Gateway connection details</summary><p>Custom gateways can submit measurements to this endpoint.</p><code>POST {typeof window !== "undefined" ? window.location.origin : ""}/api/v1/readings</code><p>Send the credential as a Bearer token in the Authorization header.</p></details></div>}</details></section></div>}
        {tab === "sharing" && <div className="co-two-columns"><section className="co-panel co-form-panel"><ShieldCheck size={28} /><h2>{own?.sharing ? "You are sharing with your team" : "Your sharing is paused"}</h2><p>{own?.sharing ? "Authorized managers can view your received measurements and recent history." : "New uploads are blocked and your readings are hidden from the team view."}</p><button className="co-primary" disabled={busy} onClick={() => void act(async () => { await api(`/organizations/${org}/me/sharing`, "PATCH", { enabled: !own?.sharing }); await reload(); })}>{own?.sharing ? <Pause size={16} /> : <Play size={16} />}{own?.sharing ? "Pause sharing" : "Enable sharing"}</button><div className="co-note"><History size={15} />Measurements are retained for up to {snapshot.organization.retention_days} days in the active history.</div></section><section className="co-panel co-form-panel"><h2>Delete your measurements</h2><p>Pause sharing and delete your stored physiological history from this workspace. This cannot be undone.</p><label>Type DELETE to confirm<input aria-label="Deletion confirmation" value={confirmation} onChange={event => setConfirmation(event.target.value as "" | "DELETE")} autoComplete="off" /></label><button className="co-secondary danger" disabled={busy || confirmation !== "DELETE"} onClick={() => void act(async () => { await api(`/organizations/${org}/me/readings`, "DELETE"); setConfirmation(""); setRows([]); await reload(); setNotice("Your measurements were deleted. Sharing is paused."); })}><Trash2 size={15} />Delete my measurements</button></section></div>}
        <footer className="co-footer"><span><ShieldCheck size={13} />{account.email} · {own?.role}</span><span>Updated {timeLabel(snapshot.server_time)}</span></footer>
      </main>}
    </>}
  </div>;
}
