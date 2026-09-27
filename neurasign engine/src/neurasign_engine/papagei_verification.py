"""Independent verification of saved 009 predictions, allowing CSV float32 rounding."""
import json

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from . import papagei_training
from .schema import TARGETS
from .transfer_training import sha, write_json


def verify(root):
    out = root/'results/papagei-v1'
    document = json.loads((out/'report.json').read_text())
    run = document['run']
    assert sha(papagei_training.__file__) == run['training_code_sha256']
    assert sha(root/'experiments/008-final-selection.json') == run['previous_final_selection_sha256']
    assert sha(root/'results/transfer-v1/final/test-report.json') == run['previous_test_report_sha256']
    frame, embeddings = papagei_training.load_inputs(root)
    maximum_mae_difference = 0.
    count = 0
    for result in document['results']:
        target = result['target']
        path = out/(target+'__'+result['name']+'.csv.gz')
        assert sha(path) == result['predictions_sha256']
        pred = pd.read_csv(path)
        assert not pred.original_row.duplicated().any()
        expected = frame.loc[frame[target].notna()].sort_values('original_row')
        assert pred.original_row.tolist() == expected.original_row.tolist()
        np.testing.assert_allclose(pred[target], expected[target], rtol=0, atol=0)
        for fold, ids in enumerate(run['folds']):
            assert set(pred.loc[pred.fold == fold, 'participant']) == set(ids)
        # Ridge emits float32 and CSV records its short decimal representation.
        # Reading that text as float64 can differ by a few parts in 10^8. This
        # does not warrant changing predictions, rerunning fits or rounding labels.
        pred['error'] = abs(pred[target]-pred.prediction)
        mae = pred.groupby(['participant', 'unit_id']).error.mean().groupby('participant').mean().mean()
        difference = abs(mae-result['metrics']['mae'])
        maximum_mae_difference = max(maximum_mae_difference, difference)
        np.testing.assert_allclose(mae, result['metrics']['mae'], rtol=0, atol=1e-6)
        tol = 1 if target == 'mental_effort' else 10
        pred['agreement'] = pred.error <= tol
        agreement = pred.groupby(['participant', 'unit_id']).agreement.mean().groupby('participant').mean().mean()
        np.testing.assert_allclose(agreement, result['metrics']['within_tolerance'], rtol=0, atol=1e-12)
        if target == 'mental_effort':
            pred['exact'] = np.floor(pred.prediction+.5) == pred[target]
        else:
            pred['exact'] = np.minimum((pred.prediction/(100/3)).astype(int), 2) == np.minimum((pred[target]/(100/3)).astype(int), 2)
        exact = pred.groupby(['participant', 'unit_id']).exact.mean().groupby('participant').mean().mean()
        np.testing.assert_allclose(exact, result['metrics']['exact_or_three_level_accuracy'], rtol=0, atol=1e-12)
        count += 3
    assert len(document['results']) == 90
    artifacts = []
    with threadpool_limits(limits=1):
        for target in TARGETS:
            path = root/'models/papagei-v1'/(target+'.joblib')
            artifact = joblib.load(path)  # Locally generated artifacts only.
            assert artifact['production_enabled'] is False
            x, _ = papagei_training.design(frame.iloc[:5], embeddings[:5], [], artifact['profile'], artifact['algorithm'], artifact['projections'])
            assert np.isfinite(artifact['model'].predict(x)).all()
            artifacts.append({'target': target, 'sha256': sha(path)})
    write_json(out/'verification.json', {'status': 'passed', 'comparisons': 90, 'independent_metrics': count,
               'old_test_report_unchanged': True, 'artifact_checks': artifacts,
               'float32_csv_mae_absolute_tolerance': 1e-6, 'maximum_mae_roundtrip_difference': maximum_mae_difference,
               'verification_code_sha256': sha(__file__)})
    print(f'Verified 90 comparisons, {count} independent metrics and six research artifacts. Maximum CSV MAE difference: {maximum_mae_difference:.3g}', flush=True)
