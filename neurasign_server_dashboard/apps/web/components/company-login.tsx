"use client";

import type { FormEvent } from "react";
import { ArrowRight, Eye, EyeOff, LoaderCircle } from "lucide-react";
import { useState } from "react";
import { SignalOrb } from "./brand";

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
      <span className="co-story-label"><span /> HUMAN SIGNALS / CONNECTED</span>
      <h2>Human signals.<br />One clear<br /><em>view.</em></h2>
      <p>Wearable measurements for your whole team.<br />See signals, connections and changes in one place.</p>
      <SignalOrb className="co-login-orb" />
      <div className="co-login-story-bottom">
        <div className="co-device-path" aria-label="Wearable connects to phone, which sends measurements to the team dashboard"><span>Wearable</span><ArrowRight size={13} /><span>Phone</span><ArrowRight size={13} /><span>Workspace</span></div>
        {demoAvailable && <a className="co-story-demo" href="/demo"><span>Explore the recorded demo</span><ArrowRight size={20} /></a>}
        <div className="co-story-foot"><span>Employee-controlled sharing.</span><span>Separate company workspaces.</span></div>
      </div>
    </section>
    <section className="co-login-form co-auth" id="workspace-access" tabIndex={-1}>
      <span className="co-eyebrow">WORKSPACE ACCESS</span>
      <h1>{signup ? "Start here." : "Sign in."}</h1>
      <p>{signup ? "Create your company account." : "Your team. Your workspace."}</p>
      <form onSubmit={onSubmit}>
        {signup && <label>Full name<input name="name" autoComplete="name" placeholder="Alex Morgan" required minLength={2} maxLength={80} /></label>}
        <label>Work email<input name="email" type="email" autoComplete="email" placeholder="you@company.com" required /></label>
        <label>Password<span className="co-password-input"><input name="password" type={showPassword ? "text" : "password"} autoComplete={signup ? "new-password" : "current-password"} required minLength={signup ? 12 : 1} maxLength={128} placeholder={signup ? "At least 12 characters" : "Enter your password"} /><button type="button" className="co-icon" aria-label={showPassword ? "Hide password" : "Show password"} aria-pressed={showPassword} onClick={() => setShowPassword(value => !value)}>{showPassword ? <EyeOff size={17} /> : <Eye size={17} />}</button></span></label>
        {!signup && <button type="button" className="co-text co-forgot" disabled={busy} onClick={onReset}>Reset password</button>}
        <button className="co-primary" disabled={busy || !ready}>{busy ? <LoaderCircle className="co-spin" size={17} /> : <ArrowRight size={17} />}{signup ? "Create account" : "Sign in"}</button>
      </form>
      <button className="co-text co-signup-toggle" onClick={onToggle}>{signup ? "Already have an account? Sign in" : "New here? Create an account"}</button>
      {!signup && testAccount && <aside className="co-test-account" aria-label="Local test account"><div><strong>Explore the workspace</strong><span className="co-chip">LOCAL</span></div><button className="co-secondary" disabled={busy || !ready} onClick={onTestLogin}>Sign in with test account<ArrowRight size={15} /></button><details><summary>Test credentials</summary><dl><div><dt>Email</dt><dd>{testAccount.email}</dd></div><div><dt>Password</dt><dd>{testAccount.password}</dd></div></dl></details></aside>}
      <footer>Your company’s data stays in its own workspace.</footer>
    </section>
  </main>;
}
