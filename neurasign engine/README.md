# NEURASIGN Engine

Research workspace for turning wearable signal windows into reproducible, testable interpretations. The product remains a general team monitoring platform; experiments define individual outputs and their evidence requirements.

Start with the [model evidence card](MODEL_CARD.md) for stress, readiness, fatigue and workload. Each output has its own target, time scale and evaluation; there is no shared 80% accuracy claim. The research models remain separate from the dashboard's experimental formulas.

## Latest improvement round

Experiments 019–021 compare new models with fixed prior methods on identical, participant-disjoint outer folds. Inner folds select configurations without seeing the outer people; the previously scored test cohorts remain excluded. Experiment 022 uses a new external wrist dataset and reserves three people before model selection.

- [019: readiness refinement](experiments/019-readiness-refinement-results.md): richer overnight trajectories and strictly preceding physiological context reduce MAE from **4.274 to 4.207/100** on the same nested folds, a small 1.6% change below the research gate. The older 3.98-point held-out result remains separate.
- [020: fatigue refinement](experiments/020-fatigue-nested-results.md): 36 configurations across daily classification and regression. The new classifier scores **63.7% balanced accuracy**, below the fixed prior's **66.7%** on the same development folds. No established improvement.
- [021: overall workload](experiments/021-workload-improvement-results.md): MAE falls from **16.04 to 13.02/100**, but a post-hoc rest/activity-only baseline reaches **13.22**. The gain attributable to physiology is not established. This uses the overall NASA-TLX target and complete tasks, not the previous mental-demand component or live windows.
- [022: WESAD wrist condition recognition](experiments/022-wesad-stress-results.md): the development-selected ExtraTrees reaches **94.2% accuracy / 92.2% balanced accuracy** on three unseen people, using 60-second wrist windows. The prespecified fixed logistic reference performs better at 96.5% / 95.7%; no test-driven model switch was made. These are laboratory baseline-versus-TSST condition labels, not instantaneous employee stress, and the source license is scientific non-commercial.

Install this round's dependencies with `.venv/bin/python -m pip install -r requirements-improvement.txt`. Follow each report's preparation, training and verification stages. Original evaluations and source fingerprints remain unchanged; completed runs refuse replacement.

All **134 implementation tests** passed. Independent checks reproduce model predictions, participant exclusions, training-only preprocessing, inner selections and aggregate metrics. [Artifact fingerprints](experiments/improvement-round-artifacts.json) identify 33 saved artifact files, including fold models and constant references. Raw recordings, individual predictions and weights remain ignored. `scripts/plot_improvement_results.py` exports the [aggregate comparison](experiments/figures/019-022-results.png), with PDF/CSV copies under ignored `results/improvement-round/`.

## New fatigue and daily readiness training

[MEFAR](experiments/014-mefar-results.md), [FatigueSet](experiments/015-fatigueset-results.md), [IFH Affect/Oura](experiments/016-readiness-oura-results.md), [the Luo daily wearable study](experiments/017-fatigue-daily-results.md) and [DailySense](experiments/018-dailysense-results.md) now have reproducible preparation, grouped model selection, reserved-person evaluation and saved trained artifacts. Data and individual predictions remain local and ignored.

Install the additional experiment dependencies with `.venv/bin/python -m pip install -r requirements-fatigue.txt`. Download scripts need `requests`; use a Python environment with `requirements-download.txt` installed. Run each experiment's `prepare`, `run` and `verify` commands as described in its report. Completed evaluations refuse replacement.

The strongest new result is **daily Oura readiness approximation: 3.98-point mean absolute error on a 100-point scale**, compared with 8.71 for a constant, in four reserved people and 684 days. Predictions fall within ±10 points of Oura on 93.4% of person-weighted days; this is tolerance agreement, not 93.4% classification accuracy. It requires overnight/daily inputs and is not a one-second live readiness model.

Fatigue remains unresolved. MEFAR scores 46.7% balanced accuracy. FatigueSet physical fatigue reaches 82.7% balanced accuracy, but the test has only one high-fatigue answer and nine false alerts; ordinary accuracy is 66.7%. Its mental-fatigue result is 43.8% balanced accuracy. The independent daily-fatigue study gives less than 1% MAE improvement. DailySense adds 453 fatigue ratings from 36 people: its selected classifier obtains 54.8% person-weighted and 60.6% balanced accuracy on eight reserved people, with only 43.0% high-fatigue recall. Its intensity regressor has 20.89-point error versus 20.14 for a constant. All fatigue research gates fail. The [model card](MODEL_CARD.md) keeps target definitions, baselines and limitations together. Across these five datasets, 468 profile/algorithm configurations were evaluated. [Artifact fingerprints](experiments/fatigue-readiness-artifacts.json) record 19 actual saved model files. None of these artifacts is loaded by the dashboard.

Historical UNIVERSE acquisition status: research inputs downloaded and verified: 26,361 files, 5.33 GB extracted, covering available wrist records from all 24 participants. Initial offline experiments did not establish consistent predictive benefit. The [causal streaming interface](experiments/003-streaming-interface.md) processes raw sensor blocks with a 60-second trailing window and 10-second updates; the [third experiment](experiments/003-causal-results.md) evaluates those windows against questionnaire ratings. There is no production integration. The legacy demo's heuristic scores are not ground truth.

The preceding [experiment 011](experiments/011-short-window-results.md) retrains classifiers on **one second of raw signal evidence**, compared with sixty seconds at identical recording endpoints. Both matched profiles use the same 23 features, without HRV, device HR or preceding history. On mental demand in 17 people, the Lab1-selected general/personal/hybrid arms score **48.9% / 52.5% / 47.8%** within-person balanced accuracy with one second, versus **53.1% / 55.3% / 55.1%** with sixty seconds. Constant predictions score 50%. The one-second models do not establish useful interpretation; active-task results remain near that reference. Mental effort has only two paired people. Original models, data and reports remain unchanged; no product integration was added.

This is a controlled duration comparison using a smaller, common feature and algorithm search than experiment 010, so its sixty-second selected results are not replacements for the earlier 60.1% hybrid figure. Predictions use the original ten-second-spaced endpoints and task-level labels: the experiment does not validate every-second delivery, first-second startup accuracy or instantaneous ground truth. [The protocol](experiments/011-short-window-protocol.json) fixes the comparison before new outcomes. Saved verification passed 720 metric checks, 72 paired interval checks and 342 artifact replays; 95 prior files retained their hashes.

Run `.venv/bin/python scripts/run_short_window.py` with the separate `prepare`, `select`, `evaluate`, `report` and `verify` stages. Completed evaluation refuses replacement; use `report` and `verify` to inspect the saved run. New data, detailed predictions and artifacts live in ignored `data/prepared/short-window-v1/`, `results/short-window-v1/` and `models/short-window-v1/`.

The preceding [experiment 010](experiments/010-personalization-results.md) compares general, personalized and hybrid classifiers trained and selected on Lab1, then evaluated on Lab2. For low/high self-reported mental demand in 17 development participants, within-person balanced accuracy is 57.1%, 58.6% and 60.1%, respectively. Paired improvements over the general model are inconclusive; the hybrid scores 54.3% during active tasks in the 13 people retaining both classes. The separate mental-effort target has only two paired people because most first-session source files lack that question. The [protocol](experiments/010-personalization-protocol.json) and [source-data note](experiments/010-data-audit-note.md) preserve the planned comparison and coverage limits. No arm met the prespecified research criterion or supports production interpretation scores.

Use `scripts/run_personalization.py` with the separate `prepare`, `select`, `evaluate`, `report` and `verify` stages. Selection reads only Lab1; whole tasks or people define its inner folds. Evaluation predictions, calibration histories, individual model artifacts and verification records remain in ignored directories. The experiment does not reopen the original test sets.

The preceding [experiment 009](experiments/009-papagei-results.md) evaluates the frozen PaPaGei-S raw-pulse encoder, signal fusion and three-minute temporal context. Across 90 comparisons on the same 35,425 windows from 19 development participants, it does not establish a reliable advantage over engineered features or constant predictions. Its [protocol](experiments/009-papagei-protocol.json), per-window predictions and verification retain the full comparison.

The preceding [experiment 008](experiments/008-transfer-results.md) evaluates stronger models, joint UNIVERSE/Microsoft Band training, external unlabeled pretraining, native beat intervals and coarse classification. Its [frozen selection](experiments/008-final-selection.json) separates development search from the reserved Mobile CogLoad evaluation. Those test results remain unchanged.

To reproduce experiment 009, install `requirements-transfer.txt` and its documented CPU PyTorch build, then follow its report. `scripts/download_papagei.py` checks the published checkpoint before loading; `scripts/run_papagei.py` exposes extraction, training, reporting and verification stages. `scripts/audit_papagei.py` independently checks balanced accuracy, paired intervals and preserved experiment 008 code, and writes PNG/PDF comparison figures. Research data, weights and generated results remain ignored by Git.

The [wrist-only acquisition inventory](experiments/000-data-acquisition.md) measures original Empatica files plus questionnaire tables at 141.9 MB compressed, including BVP, across the 24 participants. This is not an aligned training dataset: inspected questionnaire tables lack task timestamps. The paper reports 159.70 hours for Empatica; its approximately 315-hour headline sums Empatica and Muse recordings. The expanded acquisition includes the labeled and processed representations and timing records described below; check `data/universe/verification.json` for the completed-run verification result.

## Useful-information audit

The [fourth experiment](experiments/004-information-results.md) measures actual recording duration without double-counting overlapping windows, audits the pulse-quality gates against raw signals, and compares fixed models with individual signal groups removed. It also tests fitting every available window against the earlier maximum of 20 fitting windows per task. Every window already inherits its task's questionnaire rating; the audit does not invent instantaneous reference labels.

Run `.venv/bin/python scripts/audit_information.py` from this directory. The [frozen diagnostic protocol](experiments/004-information-protocol.json) excludes the original test participants and reports every planned variant. Relaxed gates are experimental comparisons; they do not change the streaming engine. Full reports, per-window predictions and source checks remain in ignored `results/information-v4/`.

## Separate SWELL workbook benchmark

The user-provided SWELL-KW workbook has been evaluated in [experiment 005](experiments/005-swell-results.md), using only HR, RMSSD and SCL. It contains 25 participants and 3,139 minute rows; 2,197 labeled minutes have at least one usable physiological feature. Models using native measurements or deviations from preceding relaxation periods were selected on 20 people and evaluated once on five reserved people. The six-output results do not establish a consistent advantage over constant predictions.

These features originate from chest ECG and finger electrodes, so this is a separate physiological research experiment, not wrist-device validation. The source is listed under CC-BY-NC-SA-4.0 and is not a production data source. The workbook, predictions and model artifact are ignored by Git. Use `.venv/bin/python scripts/verify_swell.py` to recalculate the saved metrics and verify the locally trained artifact without repeating the test evaluation.

## Download and verify the research inputs

Run from this directory:

```bash
python3 -m pip install -r requirements-download.txt
python3 scripts/download_universe.py
python3 scripts/download_universe.py --verify-only
```

The expanded selection includes all original Empatica files, synchronized Empatica tables, labeled wrist segments, processed BVP/EDA/temperature, HRV/EDA/temperature features, task questionnaires, PsychoPy timing records and study notes. It excludes Muse recordings and EEG features. These representations support different experiments and must not be counted as independent recordings.

The downloader uses cached archive indexes and multipart HTTP ranges. It saves each completed file atomically after checking its byte length and source ZIP CRC32, and records a SHA-256 digest. Rerunning verifies existing files and retrieves only missing or corrupted members. It never deserializes downloaded pickle files. The full-archive MD5 cannot be checked for a subset download.

Inputs are stored under `data/universe/extracted/UNIVERSE/`. The ignored `acquisition-plan.json`, `manifest.json`, `verified-files.jsonl` and `verification.json` record selection, source provenance and completion status. Use `--max-download-mb` to adjust the transfer budget for a run if repeated interrupted requests exhaust it.

## Candidates

| Candidate | Proposed experiment | Main question |
| --- | --- | --- |
| Explicit formulas and rules | Calculate features, personal deviations and a documented rule-based classifier. | Do the rules predict the chosen labels beyond a trivial baseline? |
| Model trained on UNIVERSE | Compare regularized regression, support-vector and tree models against constant predictions. | Does it generalize to participants excluded from training? |
| Jev interpreter | Submit feature summaries, units, recent trends and reference context to a fixed Choice prompt. | Does it classify held-out windows reliably at acceptable latency and cost? |
| Personal change detection | Detect sustained departures from a person's previous reference distribution. | Can it identify measurable changes consistently, without assigning an unsupported cause? |

The working hypothesis is a hybrid: deterministic signal processing and quality checks, followed by whichever interpreter performs well for a specific output and signal profile. Personal change detection is a complementary output, not a substitute for labeled state prediction. Ensembles are evaluated per target and are not an assumed improvement.

## First multi-output experiment

The first bundle estimates six questionnaire ratings: mental effort (five levels), mental demand, physical demand, time pressure, perceived performance and effort (0–100). Missing labels are masked per output; the model does not fabricate absent answers or turn every target into a high/low category. The heads share a physiological input schema but are fitted separately.

Stress, frustration, PANAS and affective-slider outputs are excluded from workplace biometric inference. The weighted NASA-TLX composite is also excluded from that product path because it contains frustration. Separate anonymous research experiments evaluate published stress labels and the overall NASA-TLX score; these research artifacts remain production-disabled and are not loaded by the employee application. No fatigue, recovery or productivity label is invented.

The prepared table has 43,062 overlapping windows from 598 labeled intervals. An immutable participant split uses 19 people for development and five for final scoring. Five-fold grouped validation compares ridge regression and histogram gradient boosting against a mean baseline. [Read the measured results and limitations](experiments/001-multioutput-results.md).

Run from this directory:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-engine.txt
.venv/bin/python scripts/train_multioutput.py
.venv/bin/python scripts/predict_multioutput.py --input results/multioutput-v1/example-input.json
.venv/bin/python -m unittest discover -s tests -v
```

The model is stored in ignored `models/multioutput-v1.joblib`, and reports in `results/multioutput-v1/`. Prediction accepts only the ten published wrist features and the matching pipeline identifier; it returns `insufficient_data` when fewer than eight features or an entire modality are missing. It does not accept questionnaire answers, task identifiers or employee identities as predictors.

This first run uses the authors' offline feature tables (60-second windows with a 12-second step). Their source preprocessing can use future samples through interpolation/backfill and whole-segment processing. Live integration requires a causal feature pipeline and a new evaluation; these offline results must not be marketed as live validation. The fixed five-person test is already evaluated and must not be reused for iterative model tuning.

## Improving the model

The current direction is [causal raw-signal processing](experiments/003-streaming-interface.md). It includes motion and quality checks and measures errors before averaging predictions across a task. The complete-interval experiment below is retained as historical research and is not a live inference implementation.

The [second experiment](experiments/002-tuning-results.md) compares 18 fixed configurations across two interval representations, using only the original 19 development participants. Five outer participant folds evaluate model selection; three inner folds choose the model without seeing the outer participants. The original window-model selection procedure is repeated on the same nested folds for comparison. Mean and median constants are eligible to win, so choosing a more complex model is not mandatory.

The representations summarize a complete questionnaire interval using either ten feature means or 50 distribution statistics. This tests whether matching the unit of prediction to the unit of labeling helps. It requires the interval to end and is explicitly offline; its artifact is separate from the single-window v1 API. Missing answers remain masked per target, and labels and identifying fields never enter the predictor matrix.

```bash
.venv/bin/python scripts/tune_multioutput.py
```

The run records its protocol before fitting, saves detailed fold scores and predictions under ignored `results/multioutput-v2/`, and writes a separate `models/multioutput-v2-interval-research.joblib`. The five original test participants are filtered out before analysis and never scored again by this command. Final fitted heads are selected with all-development cross-validation; nested validation estimates the selection procedure, not independent performance of that exact final artifact.

Subsequent improvements should test a specific hypothesis: causal feature extraction and signal-quality rejection, reference labels with finer timing, or preceding personal calibration where a real reference recording is available. Use learning curves to assess whether additional participants help. More hyperparameter trials cannot guarantee useful predictions when the signals do not contain enough information about a label. New live or cross-device claims require new corresponding evaluation data.

Start with wrist signals, without depending on EEG. Evaluate separate input profiles according to actual available channels, sampling rates and window definitions. A successful Empatica-based experiment does not demonstrate transfer to another manufacturer's device. Overnight HRV summaries cannot replace live beat intervals, and RMSSD and SDNN must retain their distinct definitions.

Candidate windows of 60 seconds, updated every 10 seconds, are a starting configuration to evaluate. Adjacent overlapping windows are not independent observations. End-to-end response time includes the evidence window as well as computation and network latency.

## Evaluation protocol

1. Define the target, label source, units, required signals, reference period and expected output before fitting or prompting anything. Include `insufficient_data` as an explicit outcome.
2. Version a shared feature pipeline and input manifest. Record timestamps, source, freshness, quality and missing channels. Never replace absent physiological observations with invented measurements.
3. Reserve participants for final evaluation before development. Tune models, thresholds, prompts and any score calibration only on development participants, using participant-grouped validation. Keep every overlapping window and session from one participant in the same partition.
4. Fit population preprocessing on training data only. If an experiment uses a personal reference period, declare it separately, use only preceding samples and exclude it from scored evaluation. Report cold-start behavior and never normalize with future recordings.
5. Give each candidate the same available evidence and target definitions. Keep labels, task names and participant identifiers out of predictor inputs. Any Jev examples must come from development participants; hold-out labels are for scoring only.
6. For rating prediction, compare against participant-weighted mean and median constants and report MAE in the original scale. For classification, compare against a majority-class baseline and report balanced accuracy, macro F1, per-class precision/recall and confusion counts. Report variation and uncertainty across participants rather than treating overlapping windows as independent.
7. Report abstention coverage alongside accuracy, false alerts per evaluable hour, prediction changes over time, inference/network latency and cost per monitored employee-hour. For transition timing, state the resolution of the available reference labels.
8. Evaluate probability calibration separately from classification accuracy. Jev's confidence describes concentration across candidate answers; it is not established physiological accuracy. An arbitrary 0–100 score is not an observed severity scale.
9. Test missing channels, delayed data, motion and reduced sampling as separate conditions. Report controlled and uncontrolled sessions separately. Simulated channel removal tests robustness to missingness, not cross-device compatibility.
10. Record model/provider version, prompt, features, split, configuration, seed, failures and limitations. Check repeated identical Jev inputs for consistency. Freeze the selected candidate before final evaluation; further tuning requires a fresh evaluation plan.

## Layout and records

- `experiments/`: versioned plans and reviewed aggregate conclusions. Start with [TEMPLATE.md](experiments/TEMPLATE.md).
- `data/`: local datasets and derived windows, ignored by Git; create when importing data.
- `results/`: local predictions, provider responses and detailed run output, ignored by Git; create when running experiments.
- `models/`: local trained artifacts, ignored by Git; create when fitting models.

Keep credentials in ignored environment files. Review reports before committing; include aggregate evidence, configuration and provenance rather than participant-level recordings or provider payloads. The research code is in `src/neurasign_engine/`; executable preparation, training and prediction commands are in `scripts/`.

## Completed Jev benchmark

[Experiment 006](experiments/006-jev-results.md) records 1,806 real calls to pinned `jev-1.13.0`: zero-shot and eight-example prompts on 472 UNIVERSE causal windows and all 431 SWELL held-out minutes. Examples exclude the evaluated people, prompts are frozen, and local comparators are scored on exactly the same observations. No API failures occurred; no local fallback predictions were used.

Both Jev variants lose to constant predictions on mean absolute error for all six UNIVERSE outputs. SWELL physical demand improves in the eight-example run; the remaining results are mixed and do not validate a general live interpreter. The report contains percentage agreement, MAE, all earlier experiment comparisons and every information-audit variant. API confidence is kept separate from measured correctness. No application model was replaced.

```bash
.venv/bin/python scripts/benchmark_jev.py --prepare-only
.venv/bin/python scripts/benchmark_jev.py
.venv/bin/python scripts/report_jev.py
.venv/bin/python scripts/verify_jev.py
```

The runner resumes saved responses without making duplicate calls. Detailed requests, replies and comparison CSVs are in ignored `results/jev-v1/`. Credentials are read from the existing server environment and are never written to experiment artifacts.

## Reproducing the multi-dataset experiment

Install `requirements-transfer.txt` into the engine virtual environment, then install the pinned CPU build with `pip install torch==2.14.0+cpu --index-url https://download.pytorch.org/whl/cpu`. This extends the earlier engine environment without CUDA dependencies.

The finished run is best inspected with `scripts/verify_transfer.py` and `scripts/report_transfer.py`. Both read saved evidence; neither tunes on the test set. The report includes every development configuration, the separate MAUS protocol probe and the frozen held-out results. Inputs, predictions and experimental weights are ignored by Git.

For a clean reproduction, with the existing UNIVERSE causal-v3 preparation and participant split available, the acquisition commands are:

```bash
.venv/bin/python scripts/download_external.py clacir
.venv/bin/python scripts/download_external.py cogwear
.venv/bin/python scripts/download_external.py mobile
.venv/bin/python scripts/download_external.py maus
.venv/bin/python scripts/download_external.py cognitive
```

The experiment sequence is:

```bash
.venv/bin/python scripts/prepare_external_features.py universe
.venv/bin/python scripts/prepare_external_features.py clacir
.venv/bin/python scripts/prepare_external_features.py cogwear
.venv/bin/python scripts/prepare_mobile.py
.venv/bin/python scripts/prepare_native_ibi.py
.venv/bin/python scripts/pretrain_transfer.py
.venv/bin/python scripts/train_transfer.py universe
.venv/bin/python scripts/train_transfer.py pooled
.venv/bin/python scripts/train_transfer.py latent
.venv/bin/python scripts/train_transfer.py native
.venv/bin/python scripts/train_multitask_transfer.py
.venv/bin/python scripts/train_coarse_transfer.py
.venv/bin/python scripts/benchmark_maus.py
.venv/bin/python scripts/finalize_transfer.py freeze
.venv/bin/python scripts/finalize_transfer.py fit
.venv/bin/python scripts/finalize_transfer.py evaluate
.venv/bin/python scripts/verify_transfer.py
.venv/bin/python scripts/report_transfer.py
```

Use `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1` when running process-parallel experiments. The completed selection and held-out report refuse overwrite through the finalization commands. Preserve the frozen artifacts; further model selection needs a new experiment and fresh evaluation data. Public-source licenses and any access restrictions are source-specific. No restricted-source access requests are sent automatically.

## References

- [UNIVERSE dataset and label description](https://zenodo.org/records/10371068), CC BY 4.0; cite the authors when using its data.
- [UNIVERSE authors' processing and machine-learning examples](https://github.com/HPI-CH/UNIVERSE).
- [TypeSafe Jev Choice API and confidence definition](https://docs.typesafe.ai/primitives/choice).
