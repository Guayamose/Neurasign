"""Allowlisted anonymous-record inference, isolated from employee telemetry."""
from __future__ import annotations
import hashlib
import io
import json
import math
import os
from pathlib import Path
import threading
import joblib
from inference import columns_for, score

CATALOG_PATH = Path(__file__).with_name('catalog.json')
PUBLIC_FIELDS = ('title', 'target', 'task', 'dataset', 'time_horizon', 'input_summary',
                 'method', 'experiment', 'evaluation_scope', 'evidence', 'limitations')


class RuntimeErrorResponse(Exception):
    def __init__(self, status, code):
        super().__init__(code)
        self.status = status; self.code = code


def ensure_research_environment():
    if os.getenv('NEURASIGN_ENV', '').lower() == 'production' or os.getenv('K_SERVICE'):
        raise RuntimeError('Anonymous research service is disabled in production')


class ModelRuntime:
    def __init__(self, bundle_dir=None):
        ensure_research_environment()
        self.directory = Path(bundle_dir or os.getenv('MODEL_BUNDLE_DIR',
                              Path(__file__).resolve().parents[2] / 'var/model-engine'))
        self.catalog = json.loads(CATALOG_PATH.read_text())
        self._records = {}; self._models = {}; self._errors = {}; self._lock = threading.RLock()

    def specification(self, model_id):
        if model_id not in self.catalog['models']:
            raise RuntimeErrorResponse(404, 'unknown_model')
        return self.catalog['models'][model_id]

    def _bytes(self, filename, expected):
        path = self.directory / filename
        try:
            # Filenames are source-controlled constants, never supplied by clients.
            if path.is_symlink() or not path.is_file():
                raise RuntimeErrorResponse(503, 'bundle_missing')
            raw = path.read_bytes()
        except OSError:
            raise RuntimeErrorResponse(503, 'bundle_missing') from None
        if hashlib.sha256(raw).hexdigest() != expected:
            raise RuntimeErrorResponse(503, 'invalid_hash')
        return raw

    def _verified(self, model_id):
        ensure_research_environment()
        specification = self.specification(model_id)
        rows = self._bytes(specification['records_file'], specification['records_sha256'])
        artifacts = {key: self._bytes(item['file'], item['sha256'])
                     for key, item in specification['artifacts'].items()}
        if model_id in self._errors:
            raise RuntimeErrorResponse(503, self._errors[model_id])
        if model_id not in self._records:
            try:
                payload = json.loads(rows)
                if payload['model_id'] != model_id or payload['schema_version'] != 1:
                    raise ValueError('Record schema')
                self._records[model_id] = {r['id']: r for r in payload['records']}
                if len(self._records[model_id]) != len(payload['records']):
                    raise ValueError('Duplicate records')
            except (KeyError, ValueError, TypeError):
                raise RuntimeErrorResponse(503, 'model_load_error') from None
        return specification, artifacts

    def status(self, model_id):
        try:
            with self._lock:
                self._verified(model_id)
            return 'ready'
        except RuntimeErrorResponse as error:
            return error.code

    def health(self):
        ready = [key for key in self.catalog['models'] if self.status(key) == 'ready']
        return {'status': 'ok' if len(ready) == len(self.catalog['models']) else 'degraded',
                'ready_models': ready, 'scope': 'anonymous_research'}

    def public_catalog(self):
        result = []
        for key, specification in self.catalog['models'].items():
            state = self.status(key)
            result.append({'id': key, **{field: specification[field] for field in PUBLIC_FIELDS},
                           'status': state, 'record_count': len(self._records.get(key, {})) if state == 'ready' else 0})
        return {'schema_version': 1, 'scope': 'anonymous_research', 'models': result}

    @staticmethod
    def coverage(record):
        values = record['features'].values(); total = len(record['features'])
        observed = sum(value is not None and math.isfinite(value) for value in values)
        return {'observed': observed, 'total': total, 'fraction': observed / total if total else 0.0}

    def records(self, model_id):
        with self._lock:
            self._verified(model_id)
            items = self._records[model_id].values()
            return {'model_id': model_id, 'records': [
                {'id': row['id'], 'label': f'Record {row["sequence"]:04d}',
                 'sequence': row['sequence'], 'feature_coverage': self.coverage(row)} for row in items]}

    def predict(self, model_id, body):
        # Exact schema: no feature values, employee/org identity, paths or uploads.
        self.specification(model_id)
        if type(body) is not dict or set(body) != {'record_id'} or type(body['record_id']) is not str:
            raise RuntimeErrorResponse(422, 'invalid_request')
        if not 1 <= len(body['record_id']) <= 64:
            raise RuntimeErrorResponse(422, 'invalid_request')
        with self._lock:
            specification, artifact_bytes = self._verified(model_id)
            record = self._records[model_id].get(body['record_id'])
            if record is None:
                raise RuntimeErrorResponse(404, 'unknown_record')
            key = record['artifact']; item = specification['artifacts'][key]
            cache_key = (model_id, key)
            try:
                if cache_key not in self._models:
                    # Verify exact bytes against source-controlled pins BEFORE unpickling.
                    bundle = joblib.load(io.BytesIO(artifact_bytes[key]))
                    if bundle.get('production_enabled') is not False or columns_for(bundle) != item['columns']:
                        raise ValueError('Artifact schema')
                    self._models[cache_key] = bundle
                value = score(self._models[cache_key], record['features'], model_id)
                if not math.isfinite(value) or not math.isclose(value, record['expected'], abs_tol=1e-9, rel_tol=1e-10):
                    raise ValueError('Original evaluation replay mismatch')
            except Exception:
                self._errors[model_id] = 'model_load_error'
                raise RuntimeErrorResponse(503, 'model_load_error') from None
            if specification['task'] == 'classification':
                decision = int(value >= .5); reference = int(record['reference'])
                prediction = {'value': decision, 'label': specification['classes'][decision], 'unit': 'class'}
                answer = {'value': reference, 'label': specification['classes'][reference], 'unit': 'class'}
            else:
                prediction = {'value': round(value, 6), 'label': f'{value:.1f} / 100', 'unit': 'points /100'}
                reference = record['reference']
                answer = {'value': reference, 'label': f'{reference:.1f} / 100', 'unit': 'points /100'}
            return {'model_id': model_id, 'record_id': record['id'], 'scope': 'anonymous_research',
                    'production_enabled': False, 'prediction': prediction, 'reference': answer,
                    'feature_coverage': self.coverage(record), 'time_horizon': specification['time_horizon'],
                    'provenance': {'dataset': specification['dataset'], 'experiment': specification['experiment'],
                                   'artifact_sha256': item['sha256'], 'evaluation_scope': specification['evaluation_scope'],
                                   'fold': int(key.removeprefix('fold')) if key.startswith('fold') else None},
                    'confidence': None}
