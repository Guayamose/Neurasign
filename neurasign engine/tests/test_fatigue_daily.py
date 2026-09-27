from pathlib import Path
import sys
import unittest
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from neurasign_engine import fatigue_daily_data as data
from neurasign_engine import fatigue_daily_benchmark as bench


class DailyFatigueTests(unittest.TestCase):
    def test_conflicting_simultaneous_labels_excluded(self):
        frame=pd.DataFrame([{'SubjectID':1,'DateTime':'01.01.20 20:00','PROquestion':'Describe fatigue','PROanswer_value':v,'PROanswer_choice':None} for v in [2,5]])
        frame=pd.concat([frame,pd.DataFrame([{'SubjectID':2,'DateTime':'01.01.20 20:00','PROquestion':'Describe fatigue','PROanswer_value':3,'PROanswer_choice':None}])])
        result,audit=data.labels(frame)
        self.assertEqual(result.participant.tolist(),['S2'])
        self.assertEqual(audit['conflicting_person_time_target_answers_excluded'],1)

    def test_history_excludes_current_and_future(self):
        rows=pd.DataFrame({f:np.arange(6,dtype=float) for f in data.BASE_FEATURES})
        rows['participant']='S1';rows['day']=pd.date_range('2020-01-01',periods=6)
        first=data.history_features(rows)
        changed=rows.copy();changed.loc[4:,data.BASE_FEATURES]=999
        second=data.history_features(changed)
        np.testing.assert_allclose(first.loc[3,[f+'__delta' for f in data.BASE_FEATURES]].to_numpy(float),
                                   second.loc[3,[f+'__delta' for f in data.BASE_FEATURES]].to_numpy(float))
        self.assertAlmostEqual(first.loc[3,data.BASE_FEATURES[0]+'__delta'],2.)

    def test_person_weighted_metrics(self):
        frame=pd.DataFrame({'participant':['a']*100+['b'],'vas':[1]*100+[10]})
        metric=bench.metrics(frame,'vas',np.ones(len(frame)))
        self.assertAlmostEqual(metric['mae'],4.5)
        self.assertAlmostEqual(metric['within_tolerance'],.5)

    def test_labels_and_metadata_excluded_from_models(self):
        rng=np.random.default_rng(4)
        frame=pd.DataFrame(rng.normal(size=(40,len(data.BASE_FEATURES))),columns=data.BASE_FEATURES)
        frame['participant']=np.repeat(['a','b','c','d'],10);frame['row_id']=np.arange(40);frame['vas']=rng.integers(1,11,40)
        artifact=bench.fit(frame,'vas',bench.FIXED);original=bench.predict(artifact,frame)
        frame['vas']=-999;frame['physical']=999;frame['participant']='changed';frame['day']='changed'
        np.testing.assert_allclose(original,bench.predict(artifact,frame))
        self.assertFalse(artifact['production_enabled'])

    def test_sensor_summary_does_not_impute_empty_channel(self):
        frame=pd.DataFrame({name:[np.nan]*40 for name in data.CHANNELS});frame['HR']=60.
        features=data.aggregate_day(frame)
        self.assertEqual(features['HR__mean'],60.)
        self.assertTrue(np.isnan(features['HRV__mean']))


if __name__=='__main__':
    unittest.main()
