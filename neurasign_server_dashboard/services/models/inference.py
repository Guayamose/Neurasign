"""Prediction-only adapters for our hash-pinned, locally trained research artifacts."""
from __future__ import annotations
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits


def columns_for(bundle):
    if 'models' in bundle:
        return list(dict.fromkeys(c for member in bundle['models'] for c in member['columns']))
    if 'members' in bundle:
        return list(dict.fromkeys(c for member in bundle['members'] for c in columns_for(member)))
    return list(bundle['columns'])


def score(bundle, features, model_id):
    """Accept trusted prepared rows internally; this function is never an HTTP input."""
    if bundle.get('production_enabled') is not False:
        raise ValueError('Artifact must remain research-only')
    frame = pd.DataFrame([features], dtype=float)
    def component(item, kind):
        if 'members' in item:
            return float(np.mean([component(member, kind) for member in item['members']]))
        model = item['model']; selected = frame[item['columns']]
        if kind == 'classification':
            classes = list(model.classes_)
            return float(model.predict_proba(selected)[0, classes.index(1)])
        return float(np.clip(model.predict(selected)[0], 0, 100))
    with threadpool_limits(limits=1):
        if model_id == 'stress':
            return float(bundle['model'].predict(frame[bundle['columns']])[0])
        if 'models' in bundle:
            return float(np.mean([component(item, bundle['kind']) for item in bundle['models']]))
        return component(bundle, 'regression')
