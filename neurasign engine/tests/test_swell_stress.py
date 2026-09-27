"""Stress benchmark uses actual ratings and excludes identity/labels at inference."""
from pathlib import Path
import sys
import unittest
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from neurasign_engine import swell_stress as experiment


def examples():
    return pd.DataFrame([{'participant':f'p{p}','unit_id':f'p{p}/b{block}','row_id':p*10+block*2+minute,
                         'outcome':block%2,'stress':0 if block==0 else 10,
                         'HR':60+10*block+minute,'RMSSD':40-10*block,'SCL':1+block}
                        for p in range(6) for block in range(2) for minute in range(2)])


class SwellStressTests(unittest.TestCase):
    def test_predictor_contract_and_label_invariance(self):
        frame=examples();artifact=experiment.fit(frame,'logit1')
        expected=experiment.learning.predict(artifact,frame)
        frame['outcome']=1-frame.outcome;frame['stress']=999;frame['participant']='unrelated'
        frame['unit_id']='unrelated';frame['Condition']='high';frame['timestamp']=123
        np.testing.assert_array_equal(expected,experiment.learning.predict(artifact,frame))
        self.assertEqual(artifact['columns'],['HR','RMSSD','SCL'])
        self.assertFalse(artifact['production_enabled'])

    def test_folds_keep_each_person_in_one_partition(self):
        people=list('abcdefg');parts=experiment.folds(people,5)
        self.assertEqual(sorted(p for group in parts for p in group),people)
        for i,group in enumerate(parts):
            self.assertFalse(set(group)&set(p for j,other in enumerate(parts) if i!=j for p in other))

    def test_majority_accuracy_does_not_replace_balanced_accuracy(self):
        frame=examples();frame['score']=1.
        measured=experiment.metrics(frame,'score')
        self.assertAlmostEqual(measured['balanced_accuracy'],.5)
        self.assertAlmostEqual(measured['low_recall'],0)
        self.assertAlmostEqual(measured['high_recall'],1)
        self.assertAlmostEqual(measured['macro_f1'],1/3)

    def test_single_class_is_explicit_constant(self):
        frame=examples();frame=frame[frame.outcome==0]
        artifact=experiment.fit(frame,'extra')
        self.assertEqual(artifact['constant'],0)
        self.assertNotIn('model',artifact)

if __name__=='__main__':
    unittest.main()
