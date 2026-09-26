"use client";

import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { CircleHelp, X, ChevronDown, BookOpen } from "lucide-react";

export const metricDefinitions = {
  heart_rate: { label: "Heart rate", kind: "Signal summary", unit: "bpm", short: "Beats per minute", meaning: "The average number of heartbeats per minute in the signal window.", calculation: "Recorded values are averages from the source window. The graph shows these recorded summaries, not an ECG or a heartbeat waveform.", limit: "A change has many possible causes. The color identifies this signal; it does not mark a healthy or unhealthy heart rate." },
  hrv: { label: "HRV · RMSSD", kind: "Signal summary", unit: "ms", short: "Beat-to-beat variation", meaning: "How much the time between successive pulse beats varies.", calculation: "RMSSD summarizes the differences between successive pulse intervals. This replay uses pulse-derived intervals and reports the result in milliseconds.", limit: "HRV is not a stress meter. Breathing, movement and other factors can affect it; compare the same person and context." },
  eda: { label: "EDA", kind: "Signal summary", unit: "µS", short: "Skin conductance", meaning: "How easily electricity passes through the skin, which changes with sweat-gland activity.", calculation: "This value is the mean skin conductance within the signal window, measured in microsiemens. It is not a separation of tonic and phasic activity.", limit: "EDA cannot identify a specific emotion or tell you why a signal changed." },
  temperature: { label: "Skin temperature", kind: "Signal summary", unit: "°C", short: "Temperature at the wrist", meaning: "The skin temperature measured where the wearable touches the wrist.", calculation: "The recorded signal is averaged across the window and shown in degrees Celsius.", limit: "This is not core body temperature. Contact, room temperature and circulation can affect the reading." },
  movement: { label: "Movement", kind: "Signal summary", unit: "g", short: "Motion variability", meaning: "How much acceleration changes during the signal window.", calculation: "This is the standard deviation of acceleration magnitude, expressed in g. A larger value means more variation in the window.", limit: "It is not a step count, distance or a judgment about productivity." },
  cognitive_load: { label: "Workload", kind: "Inferred index", unit: "0–100", short: "Estimated current demand", meaning: "An estimate of current cognitive demand relative to this person’s reference.", calculation: "The demo combines normalized physiological signal deviations using a heuristic. It uses several windows rather than one instantaneous reading.", limit: "This is not a clinical measurement or a percentage of brain use. A higher index means higher estimated demand in this model." },
  readiness: { label: "Readiness", kind: "Inferred index", unit: "0–100", short: "Estimated capacity for work", meaning: "An estimate of how much capacity is currently available for another task.", calculation: "The heuristic derives readiness from estimated workload and fatigue. Routing also considers expertise, availability and the task itself.", limit: "A score of 80 does not mean someone has 80% of their ability. It is an unvalidated relative index, not a performance rating." },
  fatigue: { label: "Fatigue", kind: "Inferred index", unit: "0–100", short: "Estimated accumulated strain", meaning: "A rough estimate of accumulated fatigue from signals and time on task.", calculation: "The demo combines signal deviations, recent history and staged work context in a heuristic index.", limit: "It does not directly measure tiredness and is not a diagnosis. It should support a conversation, not override what a person reports." },
  interruption_cost: { label: "Interruption cost", kind: "Work context", unit: "0–100", short: "Estimated cost of switching", meaning: "How disruptive it may be to pull this person away from their current task.", calculation: "The estimate considers task priority, time on task and current workload. Work context is simulated in this demo.", limit: "It is not a physiological measurement. A high value suggests protecting focus or considering an asynchronous update." },
  signal_quality: { label: "Signal quality", kind: "Data quality", unit: "%", short: "Usability of the input", meaning: "A source-supplied or imported score for signal coverage and reliability.", calculation: "It reflects how usable the available input is. Missing or stale readings are shown as gaps; they are not replaced with zero.", limit: "High signal quality does not prove that a cognitive estimate is accurate." },
  estimate_confidence: { label: "Estimate confidence", kind: "Model confidence", unit: "%", short: "Support for the estimate", meaning: "How much usable information supports the current cognitive estimate.", calculation: "The heuristic uses signal quality × the fraction of available features × 0.9, with a cap. Confidence uses a smoothed inference window; the visible quality score describes the latest source row. Manual indices are explicitly set.", limit: "This is not a validated probability that the estimate is correct. Low confidence can make an estimate unavailable for routing." },
  baseline: { label: "Personal reference", kind: "Comparison", unit: "Same units", short: "This person’s reference period", meaning: "A comparison with the mean from this recording’s individual reference period.", calculation: "Each signal is compared with the same person’s reference. The table shows the difference in the signal’s own units. Provisional live references are not treated as calibrated personal references.", limit: "The reference is not a healthy range or necessarily a resting state. Illustrative sources use scenario references." },
  window: { label: "Signal window", kind: "Time interval", unit: "seconds", short: "Time summarized by a point", meaning: "The period of signal data summarized in each chart point.", calculation: "UNIVERSE replay uses trailing 60-second summaries every 10 source seconds. Fixture windows are 10 seconds. Live current values summarize the latest 10 seconds; live history contains received readings.", limit: "Adjacent recorded windows overlap. The chart shows summaries, not a raw ECG or pulse waveform." },
  source: { label: "Signal source", kind: "Provenance", unit: "Origin", short: "Where the data comes from", meaning: "The source tells you whether the displayed input is recorded, illustrative, manual or live.", calculation: "UNIVERSE contains real recorded sessions with fictional work profiles. Illustrative replay is generated for the demo. Manual mode has no sensor values. Live mode displays actual received readings.", limit: "Recorded signals are not live measurements of the named employees. Physiological summaries and inferred cognitive indices are different kinds of information." },
  replay: { label: "Replay controls", kind: "Playback", unit: "1×–30×", short: "Recording time, played forward", meaning: "Replay advances through a recorded session as if its windows were arriving now.", calculation: "The clock is time inside the recording. At 10×, one real second advances ten recording seconds. Live timestamps come from the device instead.", limit: "Pausing stops signal playback. It does not cancel an AI request that is already running." },
  trend: { label: "Readiness trend", kind: "Change indicator", unit: "↑ · → · ↓", short: "Change from the last estimate", meaning: "The arrow shows whether the latest readiness estimate rose, stayed similar or fell.", calculation: "The demo compares the current readiness index with the preceding estimate: a change above 0.3 is up, below −0.3 is down, and otherwise it is stable.", limit: "This is not a forecast or a clinical trend. The chart recomputes earlier estimates from source windows using the current staged work context; it is not a log of past assessments." },
} as const;

export type MetricKey = keyof typeof metricDefinitions;
const MetricHelpContext = createContext<(metric: MetricKey) => void>(() => {});

export function MetricHelp({ metric, suffix, label, guide = false }: { metric: MetricKey; suffix?: string; label?: string; guide?: boolean }) {
  const open = useContext(MetricHelpContext);
  return <button type="button" className={guide ? "metric-guide-button" : "metric-help-button"} data-testid={guide ? "metric-guide" : `metric-help-${metric}${suffix ? `-${suffix}` : ""}`} aria-label={label ?? `About ${metricDefinitions[metric].label}`} title={label ?? `About ${metricDefinitions[metric].label}`} onClick={() => open(metric)}>{guide ? <><BookOpen size={16} /><span>Metric guide</span></> : <CircleHelp size={13} />}</button>;
}

export function MetricHelpProvider({ children }: { children: ReactNode }) {
  const [metric, setMetric] = useState<MetricKey | null>(null);
  const dialog = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!metric) return;
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog.current?.querySelector<HTMLButtonElement>("button")?.focus();
    return () => { document.body.style.overflow = overflow; previous?.focus(); };
  }, [!!metric]);
  const item = metric ? metricDefinitions[metric] : null;
  return <MetricHelpContext.Provider value={setMetric}>{children}{item && metric && <div className="metric-help-overlay" onMouseDown={event => { if (event.target === event.currentTarget) setMetric(null); }}><div className="metric-help-dialog" data-testid="metric-help-dialog" ref={dialog} role="dialog" aria-modal="true" aria-labelledby="metric-help-title" onKeyDown={event => {
    if (event.key === "Escape") setMetric(null);
    if (event.key === "Tab") {
      const focusable = Array.from(dialog.current?.querySelectorAll<HTMLElement>('button, summary, a[href], [tabindex="0"]') ?? []).filter(element => {
        const closedDetails = element.closest("details:not([open])");
        if (closedDetails && !closedDetails.querySelector(":scope > summary")?.contains(element)) return false;
        return element.getClientRects().length > 0;
      });
      if (!focusable?.length) return;
      const first = focusable[0], last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
  }}><div className="metric-help-heading"><div><span>{item.kind}</span><h2 id="metric-help-title">{item.label}</h2></div><button className="icon-button" aria-label="Close metric help" onClick={() => setMetric(null)}><X size={20} /></button></div><div className="metric-help-meaning"><span className="metric-unit">{item.unit}</span><p>{item.meaning}</p></div><details className="metric-help-details" key={metric}><summary>How it works & limitations<ChevronDown size={15} /></summary><p>{item.calculation}</p><p>{item.limit}</p></details><details className="metric-help-directory"><summary>Explore all metrics<ChevronDown size={15} /></summary><div>{(Object.keys(metricDefinitions) as MetricKey[]).map(key => <button key={key} aria-pressed={key === metric} onClick={() => setMetric(key)}>{metricDefinitions[key].label}</button>)}</div></details></div></div>}</MetricHelpContext.Provider>;
}
