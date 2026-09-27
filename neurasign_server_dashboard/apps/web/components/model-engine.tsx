"use client";

import { useEffect, useRef, useState, type CSSProperties } from "react";
import { Activity, ArrowLeft, ArrowRight, BatteryMedium, Check, ChevronDown, CircleHelp, CircleMinus, Clock3, Cpu, Database, Fingerprint, FlaskConical, HeartPulse, Layers3, LoaderCircle, Moon, Play, RotateCcw, ShieldCheck } from "lucide-react";
import { comparison, evidenceLabel, modelInputNotes, modelOrder, modelRequest, modelStatusLabels, modelTitles, valueLabel, type ModelCatalog, type ModelId, type ModelPrediction, type ModelRecords, type ResearchModel } from "@/lib/model-engine";
import "./model-engine.css";

const appearance = {
  stress: { Icon: HeartPulse, color: "#a76542", background: "#fbf0e9" },
  readiness: { Icon: BatteryMedium, color: "#107c68", background: "#eaf7f1" },
  fatigue: { Icon: Moon, color: "#7261ad", background: "#f1eefb" },
  workload: { Icon: Layers3, color: "#317c9d", background: "#eaf5fa" },
};

function ModelCard({ model, selected, select }: { model: ResearchModel; selected: boolean; select: () => void }) {
  const { Icon, color, background } = appearance[model.id];
  const ready = model.status === "ready";
  return <button className={`me-model-card ${selected ? "selected" : ""}`} style={{ "--model-color": color, "--model-tint": background } as CSSProperties} onClick={select} aria-pressed={selected} data-testid={`model-${model.id}`}>
    <span className="me-card-top"><span className="me-model-icon"><Icon size={21} /></span><span className={`me-status ${ready ? "ready" : "unavailable"}`}>{ready ? <Check size={11} /> : <CircleMinus size={11} />}{modelStatusLabels[model.status]}</span></span>
    <strong className="me-model-title">{modelTitles[model.id]}</strong>
    <span className="me-time"><Clock3 size={12} />{model.time_horizon}</span>
    <span className="me-evidence"><strong>{evidenceLabel({ ...model.evidence, unit: model.evidence.unit === "%" ? "%" : "" })}{model.evidence.unit !== "%" && <small>{model.evidence.unit}</small>}</strong><span>{model.evidence.metric}</span></span>
    <span className="me-card-foot"><span>{model.dataset}</span><ArrowRight size={16} /></span>
  </button>;
}

function Prediction({ result, model }: { result: ModelPrediction; model: ResearchModel }) {
  const classification = model.task === "classification";
  return <div className="me-result" data-testid="model-prediction" aria-live="polite">
    <div className="me-result-heading"><span><Check size={15} />Inference complete</span><small>Saved model · recorded input</small></div>
    <div className="me-values">
      <div className="me-predicted"><span>MODEL PREDICTION</span><strong>{valueLabel(result.prediction, model.task)}{!classification && <small>/ 100</small>}</strong></div>
      <div className="me-reference"><span>RECORDED REFERENCE</span><strong>{valueLabel(result.reference, model.task)}{!classification && <small>/ 100</small>}</strong></div>
    </div>
    <p className="me-comparison"><Activity size={15} />{comparison(result, model.task)}</p>
    <p className="me-result-note">One example shows the model in action. The evaluation above measures performance across the research cohort.</p>
    <details className="me-result-provenance"><summary><span><Fingerprint size={14} />Prediction provenance</span><ChevronDown size={15} /></summary><dl>
      <div><dt>Dataset</dt><dd>{result.provenance.dataset}</dd></div>
      <div><dt>Experiment</dt><dd>{result.provenance.experiment}</dd></div>
      <div><dt>Evaluation</dt><dd>{result.provenance.evaluation_scope}</dd></div>
      {result.provenance.fold != null && <div><dt>Evaluation fold</dt><dd>{result.provenance.fold}</dd></div>}
      <div><dt>Input period</dt><dd>{result.time_horizon}</dd></div>
      <div><dt>Observed features</dt><dd>{result.feature_coverage.observed} / {result.feature_coverage.total}</dd></div>
      <div><dt>Model fingerprint</dt><dd className="me-fingerprint">{result.provenance.artifact_sha256}</dd></div>
    </dl></details>
  </div>;
}

export default function ModelEngine() {
  const [catalog, setCatalog] = useState<ModelCatalog | null>(null);
  const [catalogError, setCatalogError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [selectedId, setSelectedId] = useState<ModelId>("stress");
  const [records, setRecords] = useState<ModelRecords | null>(null);
  const [recordsError, setRecordsError] = useState("");
  const [recordId, setRecordId] = useState("");
  const [result, setResult] = useState<ModelPrediction | null>(null);
  const [predictionError, setPredictionError] = useState("");
  const [running, setRunning] = useState(false);
  const predictionRequest = useRef<AbortController | null>(null);
  const model = catalog?.models.find(item => item.id === selectedId);
  const activeRecords = records?.model_id === selectedId ? records.records : [];
  const record = activeRecords.find(item => item.id === recordId);
  const readyCount = catalog?.models.filter(item => item.status === "ready").length ?? 0;

  useEffect(() => {
    const controller = new AbortController();
    setCatalogError("");
    modelRequest<ModelCatalog>("catalog", controller.signal)
      .then(value => { if (!controller.signal.aborted) setCatalog(value); })
      .catch(error => { if (!controller.signal.aborted) setCatalogError(error instanceof Error ? error.message : "Unable to load the model catalog."); });
    return () => controller.abort();
  }, [refresh]);

  useEffect(() => {
    const controller = new AbortController();
    predictionRequest.current?.abort();
    setRecords(null); setRecordId(""); setRecordsError(""); setResult(null); setPredictionError(""); setRunning(false);
    if (model?.status === "ready") {
      modelRequest<ModelRecords>(`models/${selectedId}/records`, controller.signal)
        .then(value => { if (!controller.signal.aborted) { setRecords(value); setRecordId(value.records[0]?.id ?? ""); } })
        .catch(error => { if (!controller.signal.aborted) setRecordsError(error instanceof Error ? error.message : "Unable to load recorded examples."); });
    }
    return () => { controller.abort(); predictionRequest.current?.abort(); };
  }, [selectedId, model?.status, refresh]);

  function selectModel(id: ModelId) {
    predictionRequest.current?.abort();
    setResult(null); setPredictionError(""); setRunning(false); setSelectedId(id);
  }

  function selectRecord(id: string) {
    predictionRequest.current?.abort();
    setResult(null); setPredictionError(""); setRunning(false); setRecordId(id);
  }

  async function predict() {
    if (!record || model?.status !== "ready") return;
    predictionRequest.current?.abort();
    const controller = new AbortController();
    predictionRequest.current = controller;
    setResult(null); setPredictionError(""); setRunning(true);
    try {
      const next = await modelRequest<ModelPrediction>(`models/${selectedId}/predict`, controller.signal, { record_id: record.id });
      if (!controller.signal.aborted) {
        if (next.model_id !== selectedId || next.record_id !== record.id || next.scope !== "anonymous_research" || next.production_enabled !== false) throw new Error("The model response does not match this research record.");
        setResult(next);
      }
    } catch (error) {
      if (!controller.signal.aborted) setPredictionError(error instanceof Error ? error.message : "The prediction could not be completed.");
    } finally {
      if (!controller.signal.aborted) setRunning(false);
    }
  }

  return <div className="model-engine-app">
    <header className="me-header"><a className="me-logo" href="/"><span><Activity size={24} /></span>NEURASIGN<small>Model engine</small></a><div><span className="me-local-badge"><FlaskConical size={14} />Local research</span><a href="/demo"><ArrowLeft size={15} />Dashboard</a></div></header>
    <main className="me-main">
      <div className="me-heading"><div><span className="me-eyebrow">TRAINED MODELS · REAL INFERENCE</span><h1>From signals to a prediction.</h1><p>Explore four saved models using their original research inputs.</p></div><div className="me-runtime-status"><Cpu size={23} /><div><strong>{catalog ? `${readyCount} / ${catalog.models.length}` : "—"}</strong><span>verified model bundles</span></div></div></div>
      <div className="me-process" aria-label="Model inference process"><span><Database size={17} /><strong>Recorded research input</strong></span><ArrowRight size={16} /><span><Cpu size={17} /><strong>Trained model</strong></span><ArrowRight size={16} /><span><Activity size={17} /><strong>Prediction + reference</strong></span><small><ShieldCheck size={13} />Anonymous records</small></div>

      {catalogError ? <section className="me-service-error" role="alert"><CircleMinus size={27} /><div><h2>Model engine unavailable</h2><p>{catalogError}</p></div><button onClick={() => setRefresh(value => value + 1)}><RotateCcw size={15} />Retry connection</button></section> : !catalog ? <div className="me-loading" role="status"><LoaderCircle className="spin" size={24} /><span>Loading the model registry…</span></div> : <>
        <section className="me-model-grid" aria-label="Research models">{modelOrder.map(id => { const item = catalog.models.find(item => item.id === id); return item ? <ModelCard key={id} model={item} selected={selectedId === id} select={() => selectModel(id)} /> : null; })}</section>
        {model && <section className="me-experiment" aria-label={`${modelTitles[model.id]} model`} data-testid="model-experiment">
          <div className="me-experiment-heading"><div><span className="me-eyebrow">EXPLORE THE MODEL</span><h2>{modelTitles[model.id]}</h2><p>{model.target}</p></div><span className="me-dataset-badge"><Database size={14} />{model.dataset}<span>·</span>{model.time_horizon}</span></div>
          <div className="me-evaluation-context"><FlaskConical size={16} /><div><strong>{model.evidence.description}</strong><p>{model.evaluation_scope}</p></div></div>
          <div className="me-experiment-columns">
            <div className="me-input-panel">
              <div className="me-panel-title"><span>01</span><h3>Choose a research record</h3></div>
              <p className="me-input-description">{model.input_summary}</p>
              {model.status !== "ready" ? <div className="me-input-empty" role="status"><CircleMinus size={25} /><h4>{modelStatusLabels[model.status]}</h4><p>{model.status === "bundle_missing" ? "The saved model and its matching recorded inputs need to be installed in this local engine." : model.status === "invalid_hash" ? "The saved bundle failed its integrity check. A verified bundle is required before inference." : "The local service could not load this saved model. Check the model runtime before trying again."}</p></div> : recordsError ? <div className="me-inline-error" role="alert"><p>{recordsError}</p><button onClick={() => setRefresh(value => value + 1)}><RotateCcw size={14} />Retry records</button></div> : !records ? <div className="me-records-loading" role="status"><LoaderCircle size={17} className="spin" />Loading recorded inputs…</div> : !activeRecords.length ? <div className="me-input-empty"><Database size={24} /><h4>No compatible records</h4><p>This model has no matching research inputs available.</p></div> : <>
                <label className="me-record-select" htmlFor="model-record">Anonymous record<select id="model-record" value={recordId} onChange={event => selectRecord(event.target.value)}>{activeRecords.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
                {record && <div className="me-record-detail"><span><Database size={14} />{record.feature_coverage.observed} of {record.feature_coverage.total} features observed</span><details><summary><CircleHelp size={13} />What does this mean?</summary><p>These features were extracted from the recorded signals. Missing features use the preprocessing learned during training. Feature coverage is not prediction confidence.</p></details></div>}
              </>}
              <button className="me-run-button" onClick={() => void predict()} disabled={running || !record || model.status !== "ready"} data-testid="run-model">{running ? <><LoaderCircle size={17} className="spin" />Running the saved model…</> : <><Play size={16} />Run recorded example<ArrowRight size={16} /></>}</button>
              <div className="me-algorithm"><Cpu size={15} /><span><small>METHOD</small>{model.method}</span></div>
            </div>
            <div className="me-output-panel">
              <div className="me-panel-title"><span>02</span><h3>Compare the output</h3><span className="me-output-tag">{model.task === "classification" ? "Classification" : "Score prediction"}</span></div>
              {predictionError ? <div className="me-inline-error" role="alert"><CircleMinus size={22} /><h4>Prediction unavailable</h4><p>{predictionError}</p></div> : result ? <Prediction result={result} model={model} /> : <div className="me-output-empty" role="status"><span className={`me-output-symbol ${running ? "running" : ""}`}>{running ? <LoaderCircle className="spin" size={30} /> : <Cpu size={30} />}</span><h3>{running ? "Calculating the prediction" : "Your model output appears here"}</h3><p>{running ? "The server is applying the saved model to this recorded input." : "Choose a record, then run the model to compare its prediction with the recorded reference."}</p></div>}
            </div>
          </div>
          <div className="me-input-requirement"><Clock3 size={18} /><div><strong>Input requirements</strong><p>{modelInputNotes[model.id]}</p></div><span>Recorded inputs</span></div>
          <details className="me-limitations"><summary><span><CircleHelp size={15} />How to interpret this model</span><ChevronDown size={16} /></summary><div><ul>{model.limitations.map((limitation, index) => <li key={index}>{limitation}</li>)}</ul></div></details>
        </section>}
      </>}
      <footer className="me-footer"><span><FlaskConical size={14} />Anonymous research · Local model engine</span><a href="/demo">Back to the dashboard<ArrowRight size={14} /></a></footer>
    </main>
  </div>;
}
