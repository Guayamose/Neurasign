"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { getApp, getApps, initializeApp } from "firebase/app";
import { browserSessionPersistence, connectAuthEmulator, createUserWithEmailAndPassword, getAuth, onIdTokenChanged, sendEmailVerification, sendPasswordResetEmail, setPersistence, signInWithEmailAndPassword, signOut, updateProfile, type Auth, type User } from "firebase/auth";
import { Activity, ArrowRight, Building2, Copy, Cpu, FlaskConical, History, LayoutGrid, LoaderCircle, LogOut, Pause, Play, Plus, Radio, ShieldCheck, Smartphone, Trash2, Users } from "lucide-react";
import { CompanyOverview } from "./company-overview";
import { CompanyCommandCenter } from "./company-command-center";
import { ApplicationsWorkspace } from "./applications-workspace";
import type { ApplicationsData, ApplicationId } from "@/lib/applications";
import { CompanyLogin } from "./company-login";
import { CompanyConnections, type Connection } from "./company-connections";
import { Brand } from "./brand";
import { type Signal, type MetricDefinition } from "./company-signals";
import { CompanyPeople, type Team, type DashboardAccount } from "./company-people";
import "./company-workspace.css";
import "./company-design.css";

type Config = { enabled: boolean; firebase: { apiKey: string; projectId: string; authDomain: string }; emulator_url: string | null; demo_available: boolean; test_account?: { email: string; password: string } | null };
type Company = { id: string; name: string; role?: string; retention_days: number; is_demo?: boolean; demo_label?: string };
export type Features = { heart_rate: number | null; hrv: number | null; eda: number | null; temperature: number | null; movement: number | null };
export type Reading = { id: string; timestamp: number; received_at: number; window_seconds: number; features: Features; source: "wearable" | "recording"; quality: number | null };
export type Member = { team_id?: string | null; id: string; name: string; email: string; role: "owner" | "manager" | "employee"; sharing: boolean; status: "paused" | "waiting" | "current" | "stale"; latest: Reading | null; features: Features; signals?: Signal[]; measurements_access?: boolean; can_view_measurements?: boolean; connection?: { status: string; current_count: number; issue_count: number; last_received_at: number | null; issue_kind?: string | null; next_step?: string } };
type Device = Connection;
export type Snapshot = { teams: Team[]; accounts: DashboardAccount[]; metric_catalog?: MetricDefinition[]; organization: Company; me: Member; members: Member[]; devices: Device[]; server_time: number; audit: { id: string; action: string; time: number }[] };
type Account = { name: string; email: string; organizations: Company[] };
type Tab = "overview" | "people" | "applications" | "devices" | "sharing";

const timeLabel = (value: number | null | undefined) => value ? new Date(value * 1000).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "No readings yet";
class WorkspaceRequestError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}
const accessRejected = (error: unknown) => error instanceof WorkspaceRequestError
  ? error.status >= 400 && error.status < 500 && error.status !== 408 && error.status !== 429
  : Boolean((error as { code?: string })?.code?.startsWith("auth/"));
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
  const [tab, setTab] = useState<Tab>("overview");
  const [application, setApplication] = useState<ApplicationId>("hub");
  const [applicationTarget, setApplicationTarget] = useState<string>();
  const [applications, setApplications] = useState<ApplicationsData | null>(null);
  const [applicationsError, setApplicationsError] = useState("");
  const [demoRequested, setDemoRequested] = useState(false);
  const [demoOpening, setDemoOpening] = useState(false);
  const demoInFlight = useRef(false);
  const demoAutoStarted = useRef(false);
  const workspaceRequest = useRef(0);
  const accountOwner = useRef<string | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [peopleFocusId, setPeopleFocusId] = useState<string>();
  const [peopleStartSetup, setPeopleStartSetup] = useState(false);
  const [signup, setSignup] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [offline, setOffline] = useState(false);
  const [refreshError, setRefreshError] = useState("");
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
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new WorkspaceRequestError(typeof result.detail === "string" ? result.detail : `Request failed (${response.status}).`, response.status);
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
    if (!user?.emailVerified) { accountOwner.current = null; setAccount(null); setSnapshot(null); setApplications(null); setOrg(""); return; }
    if (accountOwner.current !== user.uid) {
      accountOwner.current = user.uid;
      setAccount(null); setSnapshot(null); setApplications(null); setOrg(""); setError("");
    }
    api<Account>("/me").then(value => {
      if (!active) return;
      setAccount(value);
      let saved = "";
      try { saved = sessionStorage.getItem(`neurasign-workspace:${user.uid}`) ?? ""; } catch { /* Storage may be disabled. */ }
      setOrg(previous => value.organizations.some(item => item.id === previous) ? previous : value.organizations.some(item => item.id === saved) ? saved : value.organizations[0]?.id ?? "");
    }).catch(error => { if (active) setError(errorText(error)); });
    return () => { active = false; };
  }, [api, user?.emailVerified, refresh]);

  useEffect(() => {
    if (user && org && accountOwner.current === user.uid && account?.organizations.some(company => company.id === org)) {
      try { sessionStorage.setItem(`neurasign-workspace:${user.uid}`, org); } catch { /* Optional navigation memory. */ }
    }
  }, [org, user, account]);

  const fetchWorkspace = useCallback(async () => {
    if (!org) return;
    const request = ++workspaceRequest.current;
    const [workspaceResult, appsResult] = await Promise.allSettled([
      api<Snapshot>(`/organizations/${org}/dashboard`),
      api<ApplicationsData>(`/organizations/${org}/applications`),
    ]);
    if (request !== workspaceRequest.current) return;
    if (workspaceResult.status === "rejected") {
      if (accessRejected(workspaceResult.reason)) { setSnapshot(null); setApplications(null); setCredential(""); }
      setOffline(true); setRefreshError(errorText(workspaceResult.reason));
      throw workspaceResult.reason;
    }
    setSnapshot(workspaceResult.value);
    if (appsResult.status === "fulfilled") {
      setApplications(appsResult.value); setApplicationsError(""); setOffline(false); setRefreshError("");
    } else if (workspaceResult.value.me.role === "employee") {
      setApplications(null); setApplicationsError(""); setOffline(false); setRefreshError("");
    } else {
      if (accessRejected(appsResult.reason)) setApplications(null);
      setApplicationsError(errorText(appsResult.reason)); setOffline(true); setRefreshError(errorText(appsResult.reason));
    }
  }, [api, org]);

  useEffect(() => {
    let active = true, running = false;
    ++workspaceRequest.current;
    setSnapshot(null); setApplications(null); setApplicationsError(""); setRefreshError(""); setOffline(false); setCredential(""); setInvite("");
    if (!org || !user?.emailVerified) return;
    async function poll() {
      if (running) return;
      running = true;
      try { await fetchWorkspace(); }
      catch { /* Refresh errors are shown without discarding unsaved work on a temporary outage. */ }
      finally { running = false; }
    }
    void poll();
    const timer = setInterval(poll, 4000);
    return () => { active = false; ++workspaceRequest.current; clearInterval(timer); };
  }, [fetchWorkspace, org, user?.emailVerified]);

  const reload = fetchWorkspace;
  const navigateTab = (next: Tab) => {
    setTab(next); setCredential("");
    if (next !== "applications") { setApplication("hub"); setApplicationTarget(undefined); }
    window.history.pushState(null, "", `#${next}`);
    window.scrollTo({ top: 0, left: 0, behavior: "instant" });
    requestAnimationFrame(() => headingRef.current?.focus({ preventScroll: true }));
  };
  const openApplication = (next: ApplicationId, target?: string) => {
    setTab("applications"); setApplication(next); setApplicationTarget(target); setCredential("");
    window.history.pushState(null, "", `#applications/${next}${target ? `/${encodeURIComponent(target)}` : ""}`);
    window.scrollTo({ top: 0, left: 0, behavior: "instant" });
  };
  const openPeople = (memberId?: string) => { setPeopleFocusId(memberId); setPeopleStartSetup(false); navigateTab("people"); };

  useEffect(() => {
    const restore = () => {
      const [section, app, target] = window.location.hash.slice(1).split("/");
      if (["overview", "people", "applications", "devices", "sharing"].includes(section)) {
        setTab(section as Tab);
        setApplication(["tasks", "prevention", "handover"].includes(app) ? app as ApplicationId : "hub");
        try { setApplicationTarget(target ? decodeURIComponent(target) : undefined); }
        catch { setApplicationTarget(undefined); }
      }
    };
    restore(); window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, []);

  const openDemo = useCallback(async () => {
    if (!auth || !config?.demo_available || !config.test_account) return;
    setError(""); setDemoOpening(true);
    try {
      if (auth.currentUser?.email !== config.test_account.email) await signInWithEmailAndPassword(auth, config.test_account.email, config.test_account.password);
      setDemoRequested(true);
    } catch (error) { setError(errorText(error)); setDemoOpening(false); }
  }, [auth, config]);

  useEffect(() => {
    if (auth && config?.demo_available && !demoAutoStarted.current && new URLSearchParams(window.location.search).get("demo") === "1") {
      demoAutoStarted.current = true; void openDemo();
      window.history.replaceState(null, "", window.location.pathname + window.location.hash);
    }
  }, [auth, config, openDemo]);

  useEffect(() => {
    if (!demoRequested || !user?.emailVerified || demoInFlight.current) return;
    demoInFlight.current = true;
    void (async () => {
      try {
        const result = await api<{ organization: Company; created: boolean }>("/applications/demo", "POST", {});
        const refreshed = await api<Account>("/me");
        setAccount(refreshed); setOrg(result.organization.id); setTab("overview"); setApplication("hub"); setApplicationTarget(undefined);
        window.history.replaceState(null, "", "#overview");
      } catch (error) { setError(errorText(error)); }
      finally { setDemoRequested(false); setDemoOpening(false); demoInFlight.current = false; }
    })();
  }, [demoRequested, user?.emailVerified, api]);
  const own = snapshot?.me;
  const canManage = own?.role === "owner" || own?.role === "manager";
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

  return <div className="company-app"><a className="co-skip-link" href="#main-workspace">Skip to workspace</a><header className={`co-header${!user && config?.enabled ? " co-header-guest" : ""}`}><a href="/" className="co-logo" aria-label="NEURASIGN home"><Brand theme="light" /><small>TEAM WORKSPACE</small></a><div>{config?.emulator_url && <span className="co-chip">Local workspace</span>}{config?.demo_available && !user && <button className="co-demo-link" disabled={demoOpening || !auth} onClick={() => void openDemo()}>Explore demo<ArrowRight size={14} /></button>}{config?.enabled && !user && <a className="co-header-access" href="#workspace-access">{signup ? "Account access" : "Sign in"}<ArrowRight size={14} /></a>}{user && <button className="co-icon co-signout" aria-label="Sign out" onClick={() => void act(async () => { if (auth) await signOut(auth); setSignup(false); setCredential(""); setInvite(""); })}><LogOut size={17} /><span>Sign out</span></button>}</div></header>
    {error && <div className="co-message error" role="alert">{error}<button aria-label="Dismiss error" onClick={() => setError("")}>×</button></div>}{notice && <div className="co-message" role="status">{notice}</div>}{refreshError && <div className="co-message error" role="alert"><span><strong>Updates interrupted.</strong> {snapshot ? "Showing the last received information. Your unsaved work is kept." : refreshError}</span><button className="co-text" onClick={() => void fetchWorkspace().catch(() => {})}>Retry now</button></div>}
    {!config ? <div className="co-loading"><LoaderCircle className="co-spin" />Connecting to NEURASIGN…</div> : !config.enabled ? <main className="co-auth"><Building2 size={30} /><h1>Your company workspace</h1><p>Company sign-in has not been configured for this deployment.</p>{config.demo_available && <a className="co-primary" href="/signals">Explore sample signals<ArrowRight size={16} /></a>}</main> : !user ? <CompanyLogin signup={signup} busy={busy} ready={Boolean(auth)} testAccount={config.test_account} demoAvailable={config.demo_available} onDemo={() => void openDemo()} demoOpening={demoOpening} onSubmit={signIn} onToggle={() => { setSignup(value => !value); setError(""); setNotice(""); }} onTestLogin={() => void act(async () => { if (auth && config.test_account) await signInWithEmailAndPassword(auth, config.test_account.email, config.test_account.password); })} onReset={() => void act(async () => { const input = document.querySelector<HTMLInputElement>('input[name="email"]'); if (!auth || !input?.value) throw new Error("Enter your email address first."); await sendPasswordResetEmail(auth, input.value.trim()); setNotice("If an account exists, a reset link will arrive by email."); })} /> : !user.emailVerified ? <main className="co-auth"><ShieldCheck size={32} /><h1>Verify your email</h1><p>Open the verification link sent to <strong>{user.email}</strong>.</p><button className="co-primary" disabled={busy} onClick={() => void act(async () => { await user.reload(); await user.getIdToken(true); setSession({ user }); if (!user.emailVerified) throw new Error("Your email has not been verified yet."); })}>I have verified my email<ArrowRight size={16} /></button><button className="co-text" disabled={busy} onClick={() => void act(async () => { await sendEmailVerification(user); setNotice("Verification email sent."); })}>Resend verification email</button></main> : !account ? <div className="co-loading"><LoaderCircle className="co-spin" />Loading your account…</div> : !org || inviteToken ? <main className="co-auth"><Building2 size={30} /><h1>{inviteToken ? "Join your team" : "Set up your workspace"}</h1><p>{inviteToken ? "Accept the invitation using your verified work email." : "Create your company or enter an invitation code."}</p>{!inviteToken && <form onSubmit={event => { event.preventDefault(); const data = new FormData(event.currentTarget); void act(async () => { const value = await api<Company>("/organizations", "POST", { name: data.get("company") }); setOrg(value.id); }); }}><label>Company name<input name="company" required minLength={2} maxLength={80} placeholder="Your company" /></label><button className="co-primary" disabled={busy}>Create workspace<ArrowRight size={16} /></button></form>}<form onSubmit={event => { event.preventDefault(); void act(async () => { const value = await api<{ organization_id: string }>("/invitations/accept", "POST", { token: inviteToken.trim() }); setOrg(value.organization_id); setInviteToken(""); }); }}><label>Invitation code<input value={inviteToken} onChange={event => setInviteToken(event.target.value)} required minLength={32} maxLength={128} autoComplete="off" /></label><button className="co-secondary" disabled={busy}>Join workspace<ArrowRight size={16} /></button></form>{org && <button className="co-text" onClick={() => setInviteToken("")}>Return to my workspace</button>}</main> : <div className="co-workspace-layout">
      <nav className="co-nav" aria-label="Workspace navigation">
        <span className="co-nav-label">Your workspace</span><label className="co-company-select"><Building2 size={17} /><select aria-label="Company workspace" value={org} onChange={event => { setOrg(event.target.value); setApplications(null); setApplicationTarget(undefined); setPeopleFocusId(undefined); setPeopleStartSetup(false); }}>{account.organizations.map(company => <option key={company.id} value={company.id}>{company.name}</option>)}</select></label>
        <div className="co-primary-nav">{([{ id: "overview", label: "Overview", Icon: Activity }, { id: "people", label: "People & teams", Icon: Users }, ...(canManage ? [{ id: "applications" as const, label: "Applications", Icon: LayoutGrid }] : []), { id: "devices", label: "Connections", Icon: Smartphone }] as const).map(({ id, label, Icon }) => <button key={id} data-testid={`company-tab-${id}`} className={tab === id ? "active" : ""} aria-current={tab === id ? "page" : undefined} onClick={() => { navigateTab(id); setPeopleFocusId(undefined); setPeopleStartSetup(false); }}><Icon size={19} />{label}</button>)}</div>

        <div className="co-secondary-nav"><button data-testid="company-tab-sharing" className={tab === "sharing" ? "active" : ""} aria-current={tab === "sharing" ? "page" : undefined} onClick={() => navigateTab("sharing")}><ShieldCheck size={18} />My privacy</button></div>
        {config.demo_available && <details className="co-research-nav"><summary>Demo & research<ArrowRight size={15} /></summary><button className="co-nav-demo" disabled={demoOpening} onClick={() => void openDemo()}><Play size={16} />{demoOpening ? "Opening sample…" : "Open sample workspace"}</button><a href="/signals"><Activity size={16} />Signal explorer</a><a href="/models"><Cpu size={16} />Model engine</a><p>Separate examples and research tools.</p></details>}
        <div className="co-nav-bottom"><span><ShieldCheck size={16} />Private workspace</span><p>{snapshot?.me.role === "owner" ? "Company administration · private by default." : "Only your assigned teams are visible here."}</p><div><span className="co-avatar">{account.name?.[0] ?? "N"}</span><span><strong>{account.name}</strong><small>{snapshot?.me.role ?? "Member"}</small></span></div></div>
      </nav>
      {!snapshot || snapshot.organization.id !== org ? <div className="co-loading">{offline ? "Workspace unavailable. Reconnecting…" : <><LoaderCircle className="co-spin" />Loading your workspace…</>}</div> : <main className="co-content" id="main-workspace" data-testid="company-workspace">
        {snapshot.organization.is_demo && <aside className="co-example-banner" aria-label="Sample workspace"><FlaskConical size={18} /><div><strong>Sample workspace</strong><span>Fictional people and situations. Your changes stay in this example.</span></div><a href="/?login=1">Back to sign in<ArrowRight size={15} /></a></aside>}
        <div className={`co-heading${tab === "applications" && application !== "hub" ? " co-heading-compact" : ""}`}><div><span className="co-eyebrow">{snapshot.organization.name}</span><h1 ref={headingRef} tabIndex={-1}>{({ overview: "Team overview", people: "People & teams", applications: "Applications", devices: "Connections", sharing: "My privacy" })[tab]}</h1><p>{({ overview: "Your people, their situation and the next step.", applications: "Turn team context into clear, coordinated action.", people: "Find employees, organize teams and connect their phones.", devices: "Manage which phones can send measurements to your workspace.", sharing: "Control access to your own measurements." })[tab]}</p></div><div className="co-heading-actions">{tab === "overview" && canManage && <button className="co-primary" onClick={() => snapshot.members.length ? openApplication("tasks", "new") : openPeople()}><Plus size={18} />{snapshot.members.length ? "Create task" : "Add people"}</button>}<span className={`co-refresh-status${offline ? " offline" : ""}`}><i />{offline ? "Reconnecting" : "Workspace up to date"}<small>{offline ? "Waiting for the server" : "Updates automatically"}</small></span></div></div>
        {tab === "overview" && (canManage ? <CompanyCommandCenter key={org} snapshot={snapshot} data={applications} error={applicationsError} openApplication={openApplication} openPeople={openPeople} openConnections={() => navigateTab("devices")} onRetry={() => void reload()} onDemo={config.demo_available ? () => void openDemo() : undefined} /> : <CompanyOverview key={org} snapshot={snapshot} org={org} canManage={canManage} openPeople={openPeople} demoAvailable={config.demo_available} api={api} />)}
        {tab === "applications" && canManage && <ApplicationsWorkspace key={org} org={org} snapshot={snapshot} api={api} data={applications} loading={!applications && !applicationsError} error={applicationsError} onChanged={reload} initialApp={application} target={applicationTarget} onNavigate={openApplication} />}
        {tab === "applications" && !canManage && <div className="co-panel co-form-panel"><ShieldCheck size={28} /><h2>Manager access required</h2><p>Applications are available to your company’s authorised team managers.</p><button className="co-secondary" onClick={() => navigateTab("overview")}>Back to overview</button></div>}
        {tab === "people" && <CompanyPeople key={org} org={org} teams={snapshot.teams ?? []} people={snapshot.members} accounts={snapshot.accounts ?? []} owner={own?.role === "owner"} canManage={canManage} focusPersonId={peopleFocusId} startSetup={peopleStartSetup} api={api} reload={reload} />}
        {tab === "devices" && <div className="co-connections-workspace"><CompanyConnections devices={snapshot.devices} people={snapshot.members} busy={busy} canManage={canManage} openPeople={openPeople} onRevoke={device => void act(async () => { await api(`/organizations/${org}/devices/${device.id}`, "DELETE"); setCredential(""); await reload(); })} /><details className="co-personal-connection"><summary>Advanced · personal gateway credential</summary><h2>Authorize your device</h2><p>Access is tied to your account. Enable sharing first.</p><form onSubmit={event => { event.preventDefault(); const data = new FormData(event.currentTarget); void act(async () => { const result = await api<{ credential: string }>(`/organizations/${org}/devices`, "POST", { name: data.get("name"), source: data.get("source") }); setCredential(result.credential); await reload(); }); }}><label>Device name<input name="name" placeholder="My wearable" minLength={2} maxLength={80} required /></label><label>Signal source<select name="source"><option value="wearable">Wearable measurements</option><option value="recording">Demo recording</option></select></label><button className="co-primary" disabled={busy || !own?.sharing}><Plus size={15} />Authorize device</button>{!own?.sharing && <button type="button" className="co-text" onClick={() => navigateTab("sharing")}>Open My privacy<ArrowRight size={14} /></button>}</form>{credential && <div className="co-secret"><strong>Device credential · shown once</strong><p>Keep this credential private. Revoking the device stops uploads.</p><input readOnly aria-label="Device credential" value={credential} /><button className="co-secondary" onClick={() => void act(async () => { await navigator.clipboard.writeText(credential); setNotice("Device credential copied."); })}><Copy size={14} />Copy credential</button><details><summary>Gateway connection details</summary><p>Custom gateways can submit measurements to this endpoint.</p><code>POST {typeof window !== "undefined" ? window.location.origin : ""}/api/v1/readings</code><p>Send the credential as a Bearer token in the Authorization header.</p></details></div>}</details></div>}
        {tab === "sharing" && <div className="co-two-columns"><section className="co-panel co-form-panel"><ShieldCheck size={28} /><h2>{own?.sharing ? "You are sharing with your team" : "Your sharing is paused"}</h2><p>{own?.sharing ? "Your phone can send measurements. Team managers see only permitted team information; physiological access is restricted separately." : "New uploads are blocked and your readings are hidden from the team view."}</p><button className="co-primary" disabled={busy} onClick={() => void act(async () => { await api(`/organizations/${org}/me/sharing`, "PATCH", { enabled: !own?.sharing }); await reload(); })}>{own?.sharing ? <Pause size={16} /> : <Play size={16} />}{own?.sharing ? "Pause sharing" : "Enable sharing"}</button><div className="co-note"><History size={15} />Measurements are retained for up to {snapshot.organization.retention_days} days in the active history.</div></section><section className="co-panel co-form-panel"><h2>Delete your measurements</h2><p>Pause sharing and delete your stored physiological history from this workspace. This cannot be undone.</p><label>Type DELETE to confirm<input aria-label="Deletion confirmation" value={confirmation} onChange={event => setConfirmation(event.target.value as "" | "DELETE")} autoComplete="off" /></label><button className="co-secondary danger" disabled={busy || confirmation !== "DELETE"} onClick={() => void act(async () => { await api(`/organizations/${org}/me/readings`, "DELETE"); setConfirmation(""); await reload(); setNotice("Your measurements were deleted. Sharing is paused."); })}><Trash2 size={15} />Delete my measurements</button></section></div>}
        <footer className="co-footer"><span><ShieldCheck size={13} />{account.email} · {own?.role}</span><span>Updated {timeLabel(snapshot.server_time)}</span></footer>
      </main>}
    </div>}
  </div>;
}
