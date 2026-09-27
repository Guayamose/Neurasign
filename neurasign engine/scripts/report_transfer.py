#!/usr/bin/env python3
"""Render reviewed aggregate results from frozen development and test records."""
from pathlib import Path
import json,sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1]
NAMES={'mental_effort':'Mental effort (1–5)','mental_demand':'Mental demand','physical_demand':'Physical demand',
       'temporal_demand':'Time pressure','effort':'Effort','perceived_performance':'Self-rated performance'}


def main():
    base=ROOT/'results/transfer-v1';frozen=json.loads((ROOT/'experiments/008-final-selection.json').read_text())
    test=json.loads((base/'final/test-report.json').read_text());verification=json.loads((base/'verification.json').read_text())
    pretrain=json.loads((base/'pretraining/report.json').read_text());native=json.loads((ROOT/'data/prepared/transfer-v1/universe-native-audit.json').read_text())
    maus=json.loads((base/'maus/report.json').read_text());comparison=pd.read_csv(base/'final/development-comparison.csv')
    lines=['# Experiment 008: multi-dataset transfer and stronger models','',
      '**Decision: no output met the registered MVP research gate. No interpretation model was enabled in the product.**','',
      'This round trained conventional regressors, CatBoost, a masked multi-output neural network, and an external-signal feature autoencoder. It tested native beat intervals, modality subsets, strictly preceding personal references, joint training across two wrist-device studies, and direct three-level classification. All results below come from actual local fits and saved predictions. Jev was already tested in [experiment 006](006-jev-results.md); this round makes no new Jev calls.','',
      f'The sweep contains **{frozen["selection_records"]} target/configuration comparisons** ({len(comparison)} source-specific rows), including repeated control configurations across experiments. There are eight conventional regression configurations, two constant controls, ten multi-output network configurations, 72 coarse-classification comparisons, and a separate nested MAUS probe. Counts of configurations are not counts of independent models or people.','',
      '## Fresh held-out wrist study','',
      f'Ten Mobile CogLoad user codes were reserved before modeling. One has no released questionnaire, leaving **{test["scored_codes"]} scored codes, {test["blocks"]} tasks and {test["windows"]} windows**. The 26 development codes were used for model selection. Final choices and model files were frozen before the reserved labels were scored. No tuning followed this test.','',
      'Agreement means a prediction within **±10 points** of a questionnaire rating on a 0–100 scale. It is not the probability that a live physiological interpretation is correct. Each person contributes equally, and each task within a person contributes equally.','',
      '| Output | Learned agreement ±10 | Constant agreement ±10 | Learned MAE /100 | Constant MAE /100 | MAE improvement, paired 95% CI | Pass |',
      '|---|---:|---:|---:|---:|---:|---|']
    for target,r in test['targets'].items():
        a,b=r['learned'],r['constant'];ci=r['paired_comparison']['paired_person_bootstrap_95_ci'];improvement=b['mae']-a['mae']
        lines.append(f'| {NAMES[target]} | {100*a["within_tolerance"]:.1f}% | {100*b["within_tolerance"]:.1f}% | {a["mae"]:.2f} | {b["mae"]:.2f} | {improvement:+.2f} [{ci[0]:+.2f}, {ci[1]:+.2f}] | {"Yes" if r["passes_gate"] else "No"} |')
    lines += ['', 'Positive MAE improvement favors the learned model. Confidence intervals resample whole user codes 10,000 times; they do not treat overlapping windows as independent. They are descriptive per output and not adjusted for multiple comparisons. Constants are selected using development data only. A constant can have high agreement when ratings cluster, without reading physiological signals.','',
      '| Output | Selected continuous candidate | Separate low/middle/high balanced accuracy |', '|---|---|---:|']
    for t,r in test['targets'].items():
        c=frozen['targets'][t]['learned'];lines.append(f'| {NAMES[t]} | `{c["name"]}` | {100*r["coarse_classifier"]["balanced_accuracy"]:.1f}% |')
    lines += ['', 'The coarse classifier is selected separately. Its fixed cut points are 33⅓ and 66⅔; balanced accuracy averages recall across true classes. A three-class chance reference is 33⅓%. This experiment does not change the continuous-rating acceptance criterion after seeing results.','',
      f'Signal-window coverage among recordings with questionnaire files was {100*test["eligible_signal_coverage"]:.1f}%. The missing questionnaire is not counted as a successful interpretation or silently assigned a target.','',
      '## Development results on UNIVERSE','',
      'These are the best **development selection scores after a broad search**, not a new independent accuracy claim. The original five test participants remained excluded throughout. Mental effort uses exact rounded-level agreement on its separate 1–5 scale. Other rows use ±10-point agreement.','',
      '| Output | Best learned MAE | Best constant MAE | Learned agreement | Constant agreement | Selected learned comparison |',
      '|---|---:|---:|---:|---:|---|']
    for t,r in frozen['development_summary']['universe'].items():
        a,b=r['learned']['development_metrics'],r['constant']['development_metrics']
        metric='exact_or_three_level_accuracy' if t=='mental_effort' else 'within_tolerance'
        lines.append(f'| {NAMES[t]} | {a["mae"]:.3f} | {b["mae"]:.3f} | {100*a[metric]:.1f}% | {100*b[metric]:.1f}% | `{r["learned"]["experiment"]}/{r["learned"]["name"]}` |')
    lines += ['', '## What the added data contributed','',
      '| Source | Actual use | Limitation |', '|---|---|---|',
      '| UNIVERSE | 19 development people; 41,069 causal windows, 472 labeled tasks; six questionnaire targets | Ratings describe tasks/intervals, not momentary truth; original five test people untouched |',
      '| Mobile CogLoad / Snake | 26 development user codes, 78 tasks, 722 windows; joint training of four demand/effort dimensions; nine labeled reserved codes | Export has 36 codes while paper reports 23 people; source identity reconciliation unresolved; one reserved code has no labels |',
      '| CLACIR | 5,727 nonoverlapping minute windows from 142 wrist recording groups, unlabeled pretraining | 140 metadata people plus two unmatched recording IDs (experiment 1/050 and experiment 2/140); no duplicate raw BVP hashes; no NASA-TLX ratings pooled |',
      '| CogWear | 336 nonoverlapping minute windows from 24 participant namespaces; unlabeled pretraining | No compatible questionnaire targets pooled; published CSV checksums verified |',
      '| MAUS | Author-public wrist PPG table: 342 rows, 13 features, 19 subject groups | Raw files require IEEE login; protocol classification only |',
      '| CognitiveLoad_Wearables | All 60 raw/timing archive files acquired for 15 people; withheld from fitting | Timing spreadsheets contain no task NASA-TLX answers; demographics file does not supply them |',
      '| WAUC | Source/access reviewed | Direct raw and rating downloads return HTTP 403; available author GitHub sample covers one person |',
      '| MOCAS | Source/access reviewed | Publisher confirms signed EULA and approved researcher access are required; no request sent |',
      '| SWELL | Prior benchmark retained in experiment 005 | Chest ECG/finger EDA; native units and target scales were not silently merged into wrist training |','',
      'Primary sources: [Mobile repository](https://gitlab.fri.uni-lj.si/lrk/mobile-cogload-dataset), [original Mobile thesis](https://repozitorij.uni-lj.si/IzpisGradiva.php?id=110571), [CLACIR](https://github.com/unl-cchil/clacir_dataset), [CogWear](https://physionet.org/content/consumer-grade-wearables/1.0.0/), [MAUS author code](https://github.com/rickwu11/MAUS_dataset_baseline_system), [CognitiveLoad release](https://zenodo.org/records/20815030), [WAUC](https://musaelab.ca/wauc-dataset/), [MOCAS access terms](https://zenodo.org/records/7023242).','',
      'An additional [n-back/music release](https://physionet.org/content/multimodal-nback-music/1.0.0/) was screened. It explicitly lacks subject cognitive-state scores and only includes five usable participants. It was not downloaded as another supposedly labeled training source.','',
      '## Methods and findings','',
      '- Trailing 60-second evidence windows, normally updated every 10 seconds. No participant, task, condition, game score, taps, EEG, personality, affect or frustration predictors. Missing channels remain missing and are imputed within training folds only; labels are never fabricated.',
      '- Equal source weighting for pooled fits, then equal people and tasks. At most 20 training windows per task; all eligible validation windows are scored. Five disjoint user folds per source. No random splitting of neighboring windows.',
      '- Ridge (two regularization strengths), SVR, squared/absolute histogram boosting, CatBoost (depth 4/6), and Extra Trees. Profiles cover pulse, EDA, summary measurements, all signals and preceding personal differences. The reference is initial physiology, not assumed resting physiology.',
      '- A 64→32→6 neural regressor learns all available targets jointly with masked missing labels; fixed 80 epochs, two losses, source-specific training. It uses engineered causal features, not raw waveform deep learning.',
      f'- The denoising feature autoencoder learned a 16-dimensional representation from {pretrain["training_windows"]} external training windows; {pretrain["validation_windows"]} separate recording-group windows checked reconstruction. The source pool spans {pretrain["source_hours_nonoverlap"]:.2f} nonoverlapping hours. It sees no supervised/test labels. Better signal reconstruction did not establish better questionnaire interpretation.',
      f'- Native E4 beat intervals were joined only after matching three distant raw BVP blocks. {native["waveform_aligned_windows"]:,} of {native["windows"]:,} windows were aligned; {native["usable_native_variability_windows"]:,} ({100*native["usable_native_variability_windows"]/native["windows"]:.1f}%) passed native-interval quality checks. Gaps remain gaps; differences never bridge missing beats. These are manufacturer PPG intervals, not ECG ground truth.',
      '- Microsoft Band resistance in kΩ is converted to conductance in µS using 1000/R. Native event RR files are used, never the repeated last-value RR column. Four NASA-TLX sliders are linearly mapped 0–20→0–100 using the source instrument/export; measurement equivalence remains an assumption. Self-rated performance stays source-specific.',
      '- Direct low/middle/high classifiers use class-balanced training and fixed thresholds. They are evaluated separately from numeric ratings.','',
      f'The MAUS nested probe achieved **{100*maus["selected"]["accuracy"]:.1f}% ordinary accuracy and {100*maus["selected"]["balanced_accuracy"]:.1f}% balanced accuracy**; its majority constant achieved {100*maus["constant"]["accuracy"]:.1f}% and {100*maus["constant"]["balanced_accuracy"]:.1f}%, respectively. Outer evaluation leaves one subject out; three inner person folds select among seven configurations. The authors’ future-aware whole-subject normalization was not reused. These labels encode experimental N-back conditions, not a real-time mental-state diagnosis or an MVP pass.','',
      '## Acceptance, limits and next evidence','',
      'The gate was specified before new outcome scoring: at least 15% MAE reduction over the selected constant, a positive lower paired-bootstrap improvement bound, at least 60% three-level balanced accuracy, at least 60% ±10-point agreement, at least 80% coverage, and at least ten held-out people. No output passed. Nine labeled held-out codes also fail the minimum evaluation-size criterion independently of performance. The criterion was not lowered after testing.','',
      'The evidence does not show that physiological inference is impossible or that every possible architecture has been exhausted. It shows that this completed battery, the accessible labels and these generalization tests do not justify a dependable general-purpose live interpreter. More unlabeled hours do not supply missing target truth. Access to restricted compatible sources and a genuinely independent target-domain dataset are the next material dependencies; repeated tuning on this test would not provide new validation.','',
      'The product can continue displaying measured signals and explicitly observed trends. These research models should not supply authoritative fatigue, productivity, concentration or employee-ranking claims. Physical demand is not fatigue; subjective performance is not productivity. No dashboard or phone behavior was changed in this round.','',
      '## Artifacts and verification','',
      f'All 41 engine tests passed. Independent verification recalculated {verification["independently_recalculated_development_metrics"]} development metrics across {verification["development_prediction_files"]} prediction files, plus all held-out rating scores and paired confidence intervals. Model, prediction, split and input hashes passed. The verification command does not refit models or choose new winners.','',
      '- Plan: [008-transfer-protocol.json](008-transfer-protocol.json); [acquisition amendment](008-protocol-amendment.md); [frozen selection](008-final-selection.json).',
      '- Full local results and predictions: `results/transfer-v1/`; complete comparison: `final/development-comparison.csv`; final test: `final/test-report.json`; independent audit: `verification.json`.',
      '- Frozen experimental weights: `models/transfer-v1/`. They are research artifacts with `production_enabled=False`, not a deployed model service.',
      '- Data, credentials, logs, weights and participant-level predictions remain ignored by Git. Source licenses/access conditions remain attached to each dataset; public availability is not a blanket production-use clearance.','',
      'From the engine directory, the completed run can be inspected without rerunning its held-out evaluation:','',
      '```bash','.venv/bin/python scripts/verify_transfer.py','.venv/bin/python scripts/report_transfer.py','```','',
      'Research preparation/training commands and dependencies are listed in the engine README. Do not overwrite the frozen run or reuse the final holdout to tune another configuration.','']
    path=ROOT/'experiments/008-transfer-results.md';path.write_text('\n'.join(lines))
    targets=list(test['targets']);x=np.arange(len(targets));a=[test['targets'][t]['learned']['within_tolerance']*100 for t in targets]
    b=[test['targets'][t]['constant']['within_tolerance']*100 for t in targets]
    c=[test['targets'][t]['coarse_classifier']['balanced_accuracy']*100 for t in targets]
    fig,axes=plt.subplots(1,2,figsize=(12,4.8),layout='constrained');labels=[NAMES[t].replace(' ','\n',1) for t in targets]
    axes[0].bar(x-.18,a,.36,label='Learned',color='#3366cc');axes[0].bar(x+.18,b,.36,label='Constant',color='#98a2b3')
    axes[0].set_title('Rating agreement within ±10 /100');axes[0].legend(frameon=False)
    axes[1].bar(x,c,.6,color='#7357b8');axes[1].axhline(100/3,color='#667085',linestyle='--',label='Three-class chance reference');axes[1].set_title('Separate low / middle / high classifiers');axes[1].legend(frameon=False)
    for ax in axes:
        ax.set_xticks(x,labels,fontsize=8);ax.set_ylim(0,100);ax.set_ylabel('Percent');ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
    fig.suptitle('NEURASIGN • Frozen held-out test: 9 user codes, 27 tasks\nNo output met the registered MVP research gate',fontsize=12)
    fig.savefig(base/'final/heldout-results.png',dpi=180);fig.savefig(base/'final/heldout-results.pdf');plt.close(fig)
    print(path,flush=True)


if __name__=='__main__':main()
