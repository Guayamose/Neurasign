from __future__ import annotations
import http.client
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

SERVICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE))
from runtime import ModelRuntime, RuntimeErrorResponse
from server import handler_for

BUNDLE = SERVICE.parents[1] / 'var/model-engine'


class MissingBundleTests(unittest.TestCase):
    def test_missing_bundle_is_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = ModelRuntime(folder)
            self.assertEqual(runtime.health()['status'], 'degraded')
            self.assertTrue(all(m['status'] == 'bundle_missing' for m in runtime.public_catalog()['models']))
            with self.assertRaises(RuntimeErrorResponse) as result:
                runtime.records('stress')
            self.assertEqual(result.exception.status, 503)

    def test_production_refuses_inference(self):
        for environment in [{'NEURASIGN_ENV': 'production'}, {'K_SERVICE': 'research-worker'}]:
            with patch.dict(os.environ, environment):
                with self.assertRaises(RuntimeError): ModelRuntime(BUNDLE)

    def test_exact_input_schema_even_without_bundle(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = ModelRuntime(folder)
            for body in [None, [], {}, {'record_id': 4}, {'record_id': 'stress-0001', 'features': {}},
                         {'record_id': 'stress-0001', 'employee_id': 'alex'},
                         {'record_id': 'stress-0001', 'organization_id': 'x'},
                         {'record_id': 'stress-0001', 'model_path': '/tmp/model'},
                         {'record_id': 'stress-0001', 'file': 'x'}]:
                with self.subTest(body=body), self.assertRaises(RuntimeErrorResponse) as result:
                    runtime.predict('stress', body)
                self.assertEqual(result.exception.status, 422)


@unittest.skipUnless((BUNDLE / 'manifest.json').exists(), 'Export verified research bundle before artifact integration tests')
class ArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.runtime = ModelRuntime(BUNDLE)

    def test_every_record_replays_original_saved_prediction(self):
        counts = {'stress': 86, 'readiness': 684, 'fatigue': 96, 'workload': 167}
        folds = set()
        for model_id, count in counts.items():
            records = self.runtime.records(model_id)['records']
            self.assertEqual(len(records), count)
            payload = json.loads((BUNDLE / f'{model_id}.json').read_text())
            expected = {row['id']: row for row in payload['records']}
            for row in records:
                response = self.runtime.predict(model_id, {'record_id': row['id']})
                original = expected[row['id']]
                value = int(original['expected'] >= .5) if model_id in ('stress', 'fatigue') else original['expected']
                self.assertAlmostEqual(response['prediction']['value'], value, places=5)
                self.assertEqual(response['reference']['value'], original['reference'])
                self.assertFalse(response['production_enabled'])
                self.assertIsNone(response['confidence'])
                if model_id == 'workload': folds.add(response['provenance']['fold'])
        self.assertEqual(folds, {0, 1, 2, 3})

    def test_responses_never_expose_people_or_features(self):
        response = self.runtime.predict('stress', {'record_id': 'stress-0001'})
        def keys(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    yield key; yield from keys(item)
            elif isinstance(value, list):
                for item in value: yield from keys(item)
        forbidden = {'participant', 'employee_id', 'organization_id', 'features', 'training_people', 'row_id', 'expected'}
        for payload in [response, self.runtime.public_catalog(), self.runtime.records('readiness')]:
            self.assertFalse(forbidden.intersection(keys(payload)))
        text = json.dumps(response)
        for raw_identifier in ['UN_101', 'par_13', 'S10']: self.assertNotIn(raw_identifier, text)

    def test_artifact_tamper_rejected_before_deserialization(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder)
            for name in ['stress.json', 'stress-selected.joblib']: shutil.copyfile(BUNDLE / name, destination / name)
            path = destination / 'stress-selected.joblib'; path.write_bytes(path.read_bytes() + b'tamper')
            runtime = ModelRuntime(destination)
            with patch('runtime.joblib.load', side_effect=AssertionError('Must not unpickle')) as loader:
                with self.assertRaises(RuntimeErrorResponse) as result:
                    runtime.predict('stress', {'record_id': 'stress-0001'})
                self.assertEqual((result.exception.status, result.exception.code), (503, 'invalid_hash'))
                loader.assert_not_called()

    def test_record_tamper_fails_and_cached_artifact_does_not_bypass_checks(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder)
            for name in ['stress.json', 'stress-selected.joblib']: shutil.copyfile(BUNDLE / name, destination / name)
            runtime = ModelRuntime(destination)
            runtime.predict('stress', {'record_id': 'stress-0001'})
            path = destination / 'stress.json'; path.write_bytes(path.read_bytes() + b' ')
            with self.assertRaises(RuntimeErrorResponse) as result:
                runtime.predict('stress', {'record_id': 'stress-0001'})
            self.assertEqual(result.exception.code, 'invalid_hash')

    def test_unknown_model_and_record(self):
        for model, record in [('employee_stress', 'stress-0001'), ('stress', '../readiness-0001'), ('stress', 'readiness-0001')]:
            with self.assertRaises(RuntimeErrorResponse) as result:
                self.runtime.predict(model, {'record_id': record})
            self.assertEqual(result.exception.status, 404)


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime = ModelRuntime(BUNDLE)
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(cls.runtime))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True); cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()
    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse(); data = json.loads(response.read()); status = response.status
        connection.close(); return status, data
    def test_catalog_and_health_http(self):
        self.assertEqual(self.request('GET', '/health')[0], 200)
        status, body = self.request('GET', '/catalog')
        self.assertEqual(status, 200); self.assertEqual(len(body['models']), 4)
    def test_malformed_and_arbitrary_payloads(self):
        cases = [('{', {'Content-Type':'application/json'}),
                 ('{"record_id":"stress-0001","features":{}}', {'Content-Type':'application/json'}),
                 ('{"record_id":"stress-0001","record_id":"stress-0002"}', {'Content-Type':'application/json'}),
                 ('{"record_id":NaN}', {'Content-Type':'application/json'}),
                 ('x'*2049, {'Content-Type':'application/json'}),
                 ('{"record_id":"stress-0001"}', {'Content-Type':'text/plain'})]
        for raw, headers in cases:
            with self.subTest(raw=raw[:80]):
                self.assertEqual(self.request('POST', '/models/stress/predict', raw, headers)[0], 422)
        self.assertEqual(self.request('GET', '/catalog?employee_id=alex')[0], 422)
        self.assertEqual(self.request('GET', '/models/../../etc/passwd')[0], 404)
    @unittest.skipUnless((BUNDLE/'manifest.json').exists(), 'Export bundle first')
    def test_actual_http_prediction(self):
        status, result = self.request('POST', '/models/stress/predict', '{"record_id":"stress-0001"}', {'Content-Type':'application/json'})
        self.assertEqual(status, 200); self.assertEqual(result['model_id'], 'stress')
        self.assertIn(result['prediction']['value'], (0, 1))


if __name__ == '__main__': unittest.main()
