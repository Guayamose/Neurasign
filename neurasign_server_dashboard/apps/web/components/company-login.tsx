"use client";

import type { FormEvent } from "react";
import { Activity, ArrowRight, Bluetooth, Eye, EyeOff, HeartPulse, LayoutDashboard, LoaderCircle, ShieldCheck, Smartphone, Waves } from "lucide-react";
import { useState } from "react";

type Props = {
  signup: boolean;
  busy: boolean;
  ready: boolean;
  testAccount?: { email: string; password: string } | null;
  demoAvailable: boolean;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onToggle: () => void;
  onTestLogin: () => void;
  onReset: () => void;
};

export function CompanyLogin({ signup, busy, ready, testAccount, demoAvailable, onSubmit, onToggle, onTestLogin, onReset }: Props) {
  const [showPassword, setShowPassword] = useState(false);
  return <main className="co-login-layout">
    <section className="co-login-story" aria-label="About NEURASIGN">
      <span className="co-story-label"><span /> WEARABLE SIGNALS. ONE WORKSPACE.</span>
      <h2>A clearer picture<br />of your <em>team.</em></h2>
      <p>Bring your team’s physiological signals together.<br className="co-desktop-break" /> See measurements, connections and trends at a glance.</p>
      <div className="co-connection-visual" aria-label="Wearable connects to phone, which sends measurements to the team dashboard">
        <div className="co-visual-caption"><Activity size={15} /> FROM SENSOR TO SCREEN</div>
        <div className="co-device-path">
          <div><span className="co-path-icon"><HeartPulse size={27} strokeWidth={1.6} /></span><strong>Wearable</strong><small>Collect signals</small></div>
          <span className="co-path-link"><Bluetooth size={15} /><i /></span>
          <div><span className="co-path-icon"><Smartphone size={27} strokeWidth={1.6} /></span><strong>Phone</strong><small>Sync securely</small></div>
          <span className="co-path-link"><Waves size={15} /><i /></span>
          <div><span className="co-path-icon accent"><LayoutDashboard size={27} strokeWidth={1.6} /></span><strong>Dashboard</strong><small>See your team</small></div>
        </div>
        <div className="co-signal-labels"><span>Heart rate</span><span>HRV</span><span>Skin signals</span><span>Movement</span></div>
        <small className="co-visual-note">Available signals depend on the wearable and its permissions.</small>
      </div>
      {demoAvailable && <a className="co-story-demo" href="/demo"><span className="co-demo-play"><ArrowRight size={21} /></span><span><strong>Take a look around</strong><small>Explore the dashboard with recorded data</small></span><ArrowRight size={18} /></a>}
      <div className="co-story-foot"><ShieldCheck size={16} /><span>Separate company workspaces. Employee-controlled sharing.</span></div>
    </section>
    <section className="co-login-form co-auth">
      <span className="co-eyebrow">YOUR COMPANY WORKSPACE</span>
      <h1>{signup ? "Create your account" : "Welcome to NEURASIGN"}</h1>
      <p>{signup ? "Your team’s connected workspace starts here." : "Sign in to see your team’s signals."}</p>
      <form onSubmit={onSubmit}>
        {signup && <label>Full name<input name="name" autoComplete="name" placeholder="Alex Morgan" required minLength={2} maxLength={80} /></label>}
        <label>Work email<input name="email" type="email" autoComplete="email" placeholder="you@company.com" required /></label>
        <label>Password<span className="co-password-input"><input name="password" type={showPassword ? "text" : "password"} autoComplete={signup ? "new-password" : "current-password"} required minLength={signup ? 12 : 1} maxLength={128} placeholder={signup ? "At least 12 characters" : "Enter your password"} /><button type="button" className="co-icon" aria-label={showPassword ? "Hide password" : "Show password"} aria-pressed={showPassword} onClick={() => setShowPassword(value => !value)}>{showPassword ? <EyeOff size={17} /> : <Eye size={17} />}</button></span></label>
        {!signup && <button type="button" className="co-text co-forgot" disabled={busy} onClick={onReset}>Reset password</button>}
        <button className="co-primary" disabled={busy || !ready}>{busy ? <LoaderCircle className="co-spin" size={17} /> : <ArrowRight size={17} />}{signup ? "Create account" : "Sign in"}</button>
      </form>
      <button className="co-text co-signup-toggle" onClick={onToggle}>{signup ? "Already have an account? Sign in" : "New here? Create an account"}</button>
      {!signup && testAccount && <aside className="co-test-account" aria-label="Local test account"><div><strong>Just exploring?</strong><span className="co-chip">Local test account</span></div><button className="co-secondary" disabled={busy || !ready} onClick={onTestLogin}><ArrowRight size={15} />Sign in with test account</button><dl><div><dt>Email</dt><dd>{testAccount.email}</dd></div><div><dt>Password</dt><dd>{testAccount.password}</dd></div></dl></aside>}
      <footer><ShieldCheck size={15} />Your company’s data stays in its own workspace.</footer>
    </section>
  </main>;
}
