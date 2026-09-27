"""Check data separation, label masking, feature boundaries and safe ingestion."""
from collections import Counter
import io
from pathlib import Path
import pickle
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))

from neurasign_engine.data import FeatureUnpickler, parse_labels, verified_bytes
from neurasign_engine.model import MultiOutputEngine
from neurasign_engine.schema import FEATURES, TARGETS, PIPELINE_ID, normalize_likert
from neurasign_engine.training import metrics, participant_split, weights


class UntrustedPayload:
    def __reduce__(self):
        return eval,("1+1",)


class ConstantModel:
    def predict(self, frame):
        assert list(frame.columns)==FEATURES
        return np.full(len(frame),2.5)


class EngineTests(unittest.TestCase):
    def test_disjoint_split_is_stable_and_complete(self):
        people=[f"UN_{i}" for i in range(101,125)]
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            first=participant_split(root,people)
            second=participant_split(root,list(reversed(people)))
            self.assertEqual(first,second)
            self.assertFalse(set(first['development'])&set(first['test']))
            self.assertEqual(len(first['development']),19)
            self.assertEqual(len(first['test']),5)
            with self.assertRaises(ValueError):
                participant_split(root,people[:-1])

    def test_missing_target_does_not_erase_other_targets(self):
        data=b'Task,Mental Demand,Physical Demand,Temporal Demand,Performance,Effort,Mental effort level\nstroop_easy,20,5,10,80,25,\nstroop_hard,90,0,75,30,95,high\n'
        audit=Counter()
        labels=parse_labels(Path('UN_101/Lab1/Task_Labels.csv'),data,audit)
        self.assertIsNone(labels['stroop_easy']['targets']['mental_effort'])
        self.assertEqual(labels['stroop_easy']['targets']['mental_demand'],20)
        self.assertEqual(labels['stroop_hard']['targets']['mental_effort'],4)
        self.assertEqual(set(labels['stroop_hard']['targets']),set(TARGETS))

    def test_ambiguous_or_shifted_labels_are_excluded(self):
        data=b'Task,Mental Demand,Mental effort level\nstroop_easy,20,low\nstroop_easy,80,high\nstroop_hard,20,Performance\n'
        audit=Counter()
        self.assertEqual(parse_labels(Path('UN_101/Lab1/Task_Labels.csv'),data,audit),{})
        self.assertEqual(audit['conflicting_questionnaire_segments'],1)
        self.assertEqual(audit['malformed_questionnaire_rows'],1)
        self.assertIsNone(normalize_likert('Performance'))

    def test_source_digest_and_pickle_globals_are_checked(self):
        with self.assertRaises(ValueError):
            FeatureUnpickler(io.BytesIO(pickle.dumps(UntrustedPayload()))).load()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            path=root/'changed.pickle'
            path.write_bytes(b'changed')
            with self.assertRaises(ValueError):
                verified_bytes(path,root,{'changed.pickle':{'sha256':'0'*64}})

    def test_weighting_does_not_favor_longer_or_more_numerous_intervals(self):
        frame=pd.DataFrame({'participant':['A']*10+['A']+['B']*2,
                            'unit_id':['a1']*10+['a2']+['b1']*2})
        frame['weight']=weights(frame)
        total=frame.groupby('participant').weight.sum()
        self.assertAlmostEqual(total['A'],total['B'])
        units=frame.groupby('unit_id').weight.sum()
        self.assertAlmostEqual(units['a1'],units['a2'])

    def test_evaluation_counts_label_intervals_not_overlapping_windows(self):
        frame=pd.DataFrame({'participant':['A']*10+['B'],'session':['Lab1']*11,
                            'unit_id':['a1']*10+['b1'],'mental_demand':[10]*10+[90]})
        result=metrics(frame,'mental_demand',np.zeros(11))
        self.assertEqual(result['label_units'],2)
        self.assertEqual(result['participant_macro_mae'],50)

    def test_prediction_contract_cannot_accept_targets_or_missing_modalities(self):
        metadata={'targets':{name:{'test':{'participant_macro_mae':1},'beat_baseline_on_holdout':False} for name in TARGETS}}
        engine=MultiOutputEngine({name:ConstantModel() for name in TARGETS},metadata)
        inputs={name:1.0 for name in FEATURES}
        result=engine.predict(inputs,PIPELINE_ID)
        self.assertEqual(set(result['estimates']),set(TARGETS))
        self.assertNotIn('Frustration',result['estimates'])
        with self.assertRaises(ValueError):
            engine.predict({**inputs,'mental_demand':80},PIPELINE_ID)
        with self.assertRaises(ValueError):
            engine.predict(inputs,'unknown-live-pipeline')
        empty=engine.predict({},PIPELINE_ID)
        self.assertEqual(empty['status'],'insufficient_data')
        missing_eda={name:value for name,value in inputs.items() if not name.startswith('SCR_')}
        self.assertEqual(engine.predict(missing_eda,PIPELINE_ID)['status'],'insufficient_data')


if __name__=='__main__':
    unittest.main()
