"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";
import { ArrowLeft, Check, Circle, FlaskConical, LoaderCircle, UserRound } from "lucide-react";
import { provenanceLabel, statusLabels } from "@/lib/applications";

export function ApplicationDialog({ title, subtitle, children, onClose, busy = false, wide = false }: { title: string; subtitle?: string; children: ReactNode; onClose: () => void; busy?: boolean; wide?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  const id = useId();
  useEffect(() => {
    const element = ref.current, trigger = document.activeElement as HTMLElement | null;
    if (element && !element.open) element.showModal();
    return () => { element?.close(); if (trigger?.isConnected) trigger.focus(); };
  }, []);
  return <dialog ref={ref} className={`apps-dialog apps-workspace ${wide ? "apps-dialog-wide" : ""}`} aria-labelledby={id} onCancel={event => { event.preventDefault(); if (!busy) onClose(); }} onClick={event => { if (event.target === event.currentTarget && !busy) onClose(); }}>
    <div className="apps-dialog-content"><header className="apps-dialog-header"><button type="button" className="apps-button apps-button-quiet" onClick={onClose} disabled={busy}><ArrowLeft size={17} />Back</button><div><h2 id={id}>{title}</h2>{subtitle && <p>{subtitle}</p>}</div></header>{children}</div>
  </dialog>;
}
export function SourceLabel({ value }: { value: string }) {
  const Icon = value === "demo" ? FlaskConical : UserRound;
  return <span className={`apps-source ${value === "demo" ? "apps-source-demo" : ""}`}><Icon size={13} aria-hidden="true" />{provenanceLabel(value)}</span>;
}
export function StatusLabel({ value }: { value: string }) { return <span className={`apps-status apps-status-${value}`}><i aria-hidden="true" />{statusLabels[value] ?? value}</span>; }
export function WorkflowSteps({ steps, current }: { steps: readonly string[]; current?: number }) {
  return <ol className="apps-steps" aria-label={current === undefined ? "How this application works" : "Workflow progress"}>{steps.map((step, index) => <li key={step} className={current !== undefined && index < current ? "is-done" : index === current ? "is-current" : ""} aria-current={index === current ? "step" : undefined}><span>{current !== undefined && index < current ? <Check size={14} /> : index + 1}</span><strong>{step}</strong></li>)}</ol>;
}
export function SavingLabel({ busy, children }: { busy: boolean; children: ReactNode }) { return <>{busy && <LoaderCircle className="apps-spin" size={16} />}{busy ? "Saving…" : children}</>; }
export function InlineNotice({ message, error = false }: { message: string; error?: boolean }) { return message ? <div className={`apps-notice ${error ? "apps-error" : ""}`} role={error ? "alert" : "status"}>{error ? <Circle size={17} /> : <Check size={17} />}<span>{message}</span></div> : null; }
