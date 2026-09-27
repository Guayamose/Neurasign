import importlib.util
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

PATH = Path(__file__).resolve().parents[1]/'scripts/audit_readiness_refinement.py'
SPEC = importlib.util.spec_from_file_location('readiness_independent_audit', PATH)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class ReadinessIndependentAuditTests(unittest.TestCase):
    def test_equal_person_metrics_do_not_weight_longer_records_more(self):
        frame = pd.DataFrame({'participant': ['A', 'A', 'B'], 'target': [0., 0., 100.], 'saved': [0., 0., 0.]})
        result = audit.metrics(frame, 'saved')
        self.assertEqual(result['mae'], 50.)
        self.assertAlmostEqual(result['rmse'], np.sqrt(5000))
        self.assertEqual(result['r2'], -1.)
        self.assertEqual(result['agreement_within_10'], .5)

    def test_source_timing_audit_flags_but_never_repairs_endpoints(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root/'data/external/ifh_readiness/extracted/A/oura/sleep.csv'
            path.parent.mkdir(parents=True)
            start = pd.Timestamp('2020-01-02T23:00Z').timestamp()*1000
            end = pd.Timestamp('2020-01-02T08:00Z').timestamp()*1000
            pd.DataFrame({'date': ['2020-01-02'], 'bedtime_start_timestamp': [start],
                          'bedtime_end_timestamp': [end], 'duration': [9*3600]}).to_csv(path, index=False)
            before = path.read_bytes()
            data = pd.DataFrame({'participant': ['A'], 'date': ['2020-01-02'], 'row_id': [7],
                                 'heart_rate_trajectory_q10': [np.nan], 'heart_rate_night_std': [np.nan]})
            result = audit.inspect_sources(root, {'people': ['A']}, data)
            self.assertEqual(result['invalid_raw_interval_count'], 1)
            self.assertEqual(result['invalid_prepared_interval_count'], 1)
            row = result['invalid_intervals'][0]
            self.assertEqual(row['duration_discrepancy_seconds'], -86400.)
            self.assertTrue(row['new_trajectory_all_missing'])
            self.assertEqual(result['affected_prepared_row_ids'], ['7'])
            self.assertEqual(path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
