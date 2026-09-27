"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, ChevronDown, LoaderCircle, RotateCcw } from "lucide-react";
import { Brand } from "./brand";
import { comparison, evidenceLabel, modelInputNotes, modelOrder, modelRequest, modelStatusLabels, modelTitles, valueLabel, type ModelCatalog, type ModelId, type ModelPrediction, type ModelRecords, type ResearchModel } from "@/lib/model-engine";
import "./model-engine.css";

function ModelSelector({ model, index, selected, select }: { model: ResearchModel; index: number; selected: boolean; select: () => void }) {
  return <button className={`me-model-option ${selected ? "selected" : ""}`} onClick={select} aria-pressed={selected} data-testid={`model-${model.id}`}>
    <span className="me-model-number">0{index + 1}</span>
    <span>{modelTitles[model.id]}</span>
    <span className="me-model-mark" aria-hidden="true">{selected ? "↗" : "+"}</span>
  </button>;
}

function Prediction({ result, model }: { result: ModelPrediction; model: ResearchModel }) {
  const classification = model.task === "classification";
  return <div className="me-result" data-testid="model-prediction" aria-live="polite">
    <div className="me-result-heading"><span><i />Inference complete</span><small>Recorded input / saved model</small></div>
    <div className="me-values">
      <div className="me-predicted"><span>Model prediction</span><strong>{valueLabel(result.prediction, model.task)}{!classification && <small>/ 100</small>}</strong></div>
      <div className="me-reference"><span>Recorded reference</span><strong>{valueLabel(result.reference, model.task)}{!classification && <small>/ 100</small>}</strong></div>
    </div>
    <p className="me-comparison">{comparison(result, model.task)}</p>
    <p className="me-result-note">One research record. Model performance is measured across the evaluation cohort above.</p>
    <details className="me-result-provenance"><summary><span>Prediction provenance</span><ChevronDown size={14} /></summary><dl>
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
    <header className="me-header"><a className="me-logo" href="/" aria-label="NEURASIGN home"><Brand /></a><span className="me-section-label">Model engine</span><div className="me-header-actions"><span className="me-local-badge"><i />Local research</span><a href="/demo"><ArrowLeft size={14} />Dashboard</a></div></header>
    <main className="me-main">
      <section className="me-heading" aria-labelledby="model-engine-title">
        <div><span className="me-eyebrow">NEURASIGN / RESEARCH ENGINE</span><h1 id="model-engine-title">Model engine</h1><p className="me-heading-description">Test trained models using anonymous research records.</p></div>
        <div className="me-heading-aside"><div className="me-runtime-status"><span>Models available</span><strong>{catalog ? String(readyCount).padStart(2, "0") : "—"}<small>/ {catalog ? String(catalog.models.length).padStart(2, "0") : "04"}</small></strong><span>Verified bundles</span></div></div>
      </section>
      <div className="me-process" aria-label="Model inference process"><span>01 — Recorded input</span><ArrowRight size={13} /><span>02 — Trained model</span><ArrowRight size={13} /><span>03 — Prediction + reference</span><small>Anonymous records only</small></div>

      {catalogError ? <section className="me-service-error" role="alert"><span className="me-error-label">Connection unavailable</span><div><h2>Model engine unavailable</h2><p>{catalogError}</p></div><button onClick={() => setRefresh(value => value + 1)}><RotateCcw size={14} />Retry connection</button></section> : !catalog ? <div className="me-loading" role="status"><LoaderCircle className="spin" size={19} /><span>Loading the model registry…</span></div> : <>
        <section className="me-model-selector" aria-label="Research models">{modelOrder.map((id, index) => { const item = catalog.models.find(item => item.id === id); return item ? <ModelSelector key={id} model={item} index={index} selected={selectedId === id} select={() => selectModel(id)} /> : null; })}</section>
        {model && <section className="me-experiment" aria-label={`${modelTitles[model.id]} model`} data-testid="model-experiment">
          <div className="me-model-overview">
            <div className="me-experiment-heading"><span className="me-eyebrow">0{modelOrder.indexOf(model.id) + 1} / SELECTED MODEL</span><h2>{modelTitles[model.id]}</h2><p>{model.target}</p><span className={`me-status ${model.status === "ready" ? "ready" : "unavailable"}`}><i />{modelStatusLabels[model.status]}</span></div>
            <dl className="me-source-details"><div><dt>Dataset</dt><dd>{model.dataset}</dd></div><div><dt>Input period</dt><dd>{model.time_horizon}</dd></div></dl>
            <div className="me-evidence"><span>{model.evidence.metric}</span><strong>{evidenceLabel({ ...model.evidence, unit: model.evidence.unit === "%" ? "%" : "" })}</strong>{model.evidence.unit !== "%" && <small>{model.evidence.unit}</small>}<p>{model.evaluation_scope}</p></div>
          </div>
          <div className="me-evaluation-context"><span>Reading the result</span><p>{model.evidence.description}</p></div>
          <div className="me-experiment-columns">
            <div className="me-input-panel">
              <div className="me-panel-title"><span>INPUT / 01</span><h3>Choose a record.</h3></div>
              <p className="me-input-description">{model.input_summary}</p>
              {model.status !== "ready" ? <div className="me-input-empty" role="status"><span className="me-error-label">Unavailable</span><h4>{modelStatusLabels[model.status]}</h4><p>{model.status === "bundle_missing" ? "The saved model and its matching recorded inputs need to be installed in this local engine." : model.status === "invalid_hash" ? "The saved bundle failed its integrity check. A verified bundle is required before inference." : "The local service could not load this saved model. Check the model runtime before trying again."}</p></div> : recordsError ? <div className="me-inline-error" role="alert"><p>{recordsError}</p><button onClick={() => setRefresh(value => value + 1)}><RotateCcw size={14} />Retry records</button></div> : !records ? <div className="me-records-loading" role="status"><LoaderCircle size={15} className="spin" />Loading recorded inputs…</div> : !activeRecords.length ? <div className="me-input-empty"><span className="me-error-label">No compatible records</span><p>This model has no matching research inputs available.</p></div> : <>
                <label className="me-record-select" htmlFor="model-record">Anonymous record<select id="model-record" value={recordId} onChange={event => selectRecord(event.target.value)}>{activeRecords.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
                {record && <div className="me-record-detail"><span>{record.feature_coverage.observed} / {record.feature_coverage.total} features observed</span><details><summary>About coverage <span aria-hidden="true">+</span></summary><p>These features were extracted from the recorded signals. Missing features use the preprocessing learned during training. Feature coverage is not prediction confidence.</p></details></div>}
              </>}
              <button className="me-run-button" onClick={() => void predict()} disabled={running || !record || model.status !== "ready"} data-testid="run-model">{running ? <><span>Running the saved model…</span><LoaderCircle size={16} className="spin" /></> : <><span>Run recorded example</span><ArrowRight size={17} /></>}</button>
              <div className="me-algorithm"><span>Method</span><p>{model.method}</p></div>
            </div>
            <div className="me-output-panel">
              <div className="me-panel-title"><span>OUTPUT / 02</span><h3>Compare the result.</h3><small>{model.task === "classification" ? "Classification" : "Score prediction"}</small></div>
              {predictionError ? <div className="me-inline-error" role="alert"><span className="me-error-label">Prediction unavailable</span><p>{predictionError}</p></div> : result ? <Prediction result={result} model={model} /> : <div className="me-output-empty" role="status"><span className="me-output-symbol" aria-hidden="true">{running ? <LoaderCircle className="spin" size={32} /> : "—"}</span><h3>{running ? "Calculating prediction" : "Awaiting inference"}</h3><p>{running ? "Applying the saved model to this recorded input." : "Select a record and run the model. Its prediction appears beside the recorded reference."}</p></div>}
            </div>
          </div>
          <div className="me-input-requirement"><span>Input requirements</span><p>{modelInputNotes[model.id]}</p></div>
          <details className="me-limitations"><summary><span>Scope & limitations</span><ChevronDown size={14} /></summary><div><ul>{model.limitations.map((limitation, index) => <li key={index}>{limitation}</li>)}</ul></div></details>
        </section>}
      </>}
      <footer className="me-footer"><span>NEURASIGN / ANONYMOUS RESEARCH</span><span>Local model engine</span><a href="/demo">Back to dashboard <ArrowRight size={13} /></a></footer>
    </main>
  </div>;
}
