#!/usr/bin/env python3
"""Export verified anonymous research records and exact fitted models; never retrain.

Run with the engine virtual environment. Fails closed if any pinned source,
artifact, selected prediction, held-out membership or output fingerprint changes.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import joblib
import numpy as np
import pandas as pd

ENGINE = Path(__file__).resolve().parents[1]
SERVICE = ENGINE.parent / 'neurasign_server_dashboard/services/models'
sys.path.insert(0, str(SERVICE))
from inference import columns_for, score


def sha_bytes(value):
    return hashlib.sha256(value).hexdigest()


def checked(root, name, expected):
    data = (root / name).read_bytes()
    if sha_bytes(data) != expected:
        raise ValueError(f'Pinned input changed: {name}')
    return data


def verify_original_evidence(root):
    """Cross-check prepared data against hashes frozen by the original experiments."""
    def read(name):
        return json.loads((root / name).read_text())
    for directory in ['readiness-oura-v1', 'dailysense-classification-v1']:
        start = read(f'results/{directory}/run-start.json')
        evaluation = read(f'results/{directory}/evaluation.json')
        checked(root, start['data'], start['data_sha256'])
        checked(root, start['protocol'], start['protocol_sha256'])
        checked(root, 'src/neurasign_engine/reference_benchmark.py', start['code_sha256'])
        for name, digest in start['dependencies'].items():
            checked(root, name, digest)
        checked(root, f'results/{directory}/test-predictions.csv.gz', evaluation['predictions_sha256'])
        checked(root, evaluation['model'], evaluation['model_sha256'])
    start = read('results/wesad-stress-022/run-start.json')
    evaluation = read('results/wesad-stress-022/evaluation.json')
    checked(root, 'data/prepared/wesad-stress-022/windows.csv.gz', start['prepared_sha256'])
    checked(root, 'experiments/022-wesad-stress-protocol.json', start['protocol_sha256'])
    checked(root, 'src/neurasign_engine/wesad_stress_022.py', start['code_sha256'])
    checked(root, 'results/wesad-stress-022/heldout-predictions.csv.gz', evaluation['predictions_sha256'])
    start = read('results/workload-improvement-v1/run-freeze.json')
    evaluation = read('results/workload-improvement-v1/evaluation.json')
    checked(root, 'data/prepared/workload-improvement-v1/tasks.csv.gz', start['data_sha256'])
    checked(root, 'experiments/021-workload-improvement-protocol.json', start['protocol_sha256'])
    checked(root, 'src/neurasign_engine/workload_improvement.py', start['code_sha256'])
    for job in evaluation['jobs']:
        checked(root, job['predictions'], job['predictions_sha256'])
        checked(root, job['selection'], job['selection_sha256'])
        for artifact in job['artifacts']:
            checked(root, artifact['file'], artifact['sha256'])


def build_records(root, catalog):
    verify_original_evidence(root)
    for name, digest in catalog['source_sha256'].items():
        checked(root, name, digest)
    output = {}; artifact_bytes = {}; counts = {}
    for model_id, specification in catalog['models'].items():
        bundles = {}
        for key, item in specification['artifacts'].items():
            raw = checked(root, item['source'], item['sha256'])
            bundle = joblib.load(io.BytesIO(raw))
            if bundle.get('production_enabled') is not False or columns_for(bundle) != item['columns']:
                raise ValueError('Artifact schema or research scope differs')
            bundles[key] = bundle; artifact_bytes[item['file']] = raw
        data = pd.read_csv(root / specification['data'])
        saved = pd.read_csv(root / specification['pred'])
        if data.row_id.duplicated().any() or saved.row_id.duplicated().any():
            raise ValueError('Duplicate research rows')
        data = data.set_index('row_id')
        # Preserve every scored row. Stable source order; no selection by labels/errors.
        saved = saved.sort_values('row_id', kind='stable')
        records = []
        for sequence, (_, observed) in enumerate(saved.iterrows(), 1):
            row = data.loc[observed.row_id]
            key = f'fold{int(observed.fold)}' if model_id == 'workload' else 'selected'
            bundle = bundles[key]
            person = str(row.participant)
            if person in set(map(str, bundle['training_people'])):
                raise ValueError('Replay person occurred in artifact training')
            if str(observed.participant) != person:
                raise ValueError('Saved prediction maps to another participant')
            target = float(row[specification['target_column']])
            if target != float(observed[specification['target_column']]):
                raise ValueError('Reference differs from saved evaluation')
            features = {name: (float(row[name]) if pd.notna(row[name]) else None)
                        for name in specification['artifacts'][key]['columns']}
            if any(value is not None and not np.isfinite(value) for value in features.values()):
                raise ValueError('Nonfinite feature')
            prediction = score(bundle, features, model_id)
            if not np.isclose(prediction, float(observed.selected), atol=1e-9, rtol=1e-10):
                raise ValueError('Actual model output differs from original evaluation')
            records.append({'id': f'{model_id}-{sequence:04d}', 'sequence': sequence,
                            'artifact': key, 'features': features, 'reference': target,
                            'expected': float(observed.selected)})
        payload = {'schema_version': 1, 'model_id': model_id, 'records': records}
        raw = (json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()
        output[specification['records_file']] = raw; counts[model_id] = len(records)
    return output, artifact_bytes, counts


def export(destination):
    catalog = json.loads((SERVICE / 'catalog.json').read_text())
    rows, artifacts, counts = build_records(ENGINE, catalog)
    for specification in catalog['models'].values():
        if sha_bytes(rows[specification['records_file']]) != specification['records_sha256']:
            raise ValueError('Export differs from reviewed record fingerprint')
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError('Export destination exists; verify it or use a new destination')
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.model-engine-', dir=destination.parent))
    try:
        for name, raw in {**rows, **artifacts}.items():
            (temporary / name).write_bytes(raw)
        (temporary / 'manifest.json').write_text(json.dumps({
            'scope': 'anonymous_research', 'production_enabled': False, 'records': counts,
            'catalog_sha256': sha_bytes((SERVICE / 'catalog.json').read_bytes()),
            'files': {name: sha_bytes(raw) for name, raw in {**rows, **artifacts}.items()},
            'selection': 'All previously scored rows; no sampling by label or error.',
            'validation': 'Exact fitted predictions match original saved evaluation; all people excluded from their artifact training.'
        }, indent=2)+'\n')
        temporary.chmod(0o755)
        for file in temporary.iterdir():
            file.chmod(0o644)
        temporary.rename(destination)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {'destination': str(destination), 'records': counts, 'artifacts': len(artifacts)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ENGINE.parent/'neurasign_server_dashboard/var/model-engine')
    args = parser.parse_args()
    print(json.dumps(export(args.output)))
