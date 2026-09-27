import sys
import unittest
from pathlib import Path
import warnings
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from neurasign_engine import readiness_refinement as source
from neurasign_engine import readiness_refinement_training as train


def raw_fixture(days=5):
    sleeps=[];activities=[];hearts=[]
    for day in range(days):
        end=pd.Timestamp('2020-01-02 16:00Z').timestamp()*1000+day*86400000
        row={name:10. for name in source.old.SLEEP}
        row.update(date=pd.Timestamp(end,unit='ms').strftime('%Y-%m-%d'),bedtime_start_timestamp=end-8*3600000,
                   bedtime_end_timestamp=end,bedtime_start_midnight_delta=0.,bedtime_end_midnight_delta=8*3600,
                   hr_average=60+day,hr_lowest=50+day,rmssd=30+day,temperature_delta=.1,total=7*3600,duration=8*3600)
        sleeps.append(row)
        activities.append({'day_end_timestamp':end-8*3600000,**{c:float(100+day) for c in source.ACTIVITY}})
        for minute in range(0,480,10):
            hearts.append({'timestamp':end-8*3600000+minute*60000,'heart_rate':60+day+np.sin(minute/60),
                           'heart_rmssd':30+day+np.cos(minute/60)})
    return pd.DataFrame(sleeps),pd.DataFrame(activities),pd.DataFrame(hearts)


class ReadinessRefinementTests(unittest.TestCase):
    def test_future_signal_changes_cannot_change_earlier_features(self):
        s,a,h=raw_fixture()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',pd.errors.PerformanceWarning)
            reference=source.enhance(s,a,h)
            changed=s.copy();changed.loc[4,'rmssd']=999.;changed.loc[4,'total']=100.
            later_h=h.copy();later_h.loc[later_h.timestamp>=s.iloc[4].bedtime_start_timestamp,'heart_rate']=199.
            later_a=a.copy();later_a.loc[4,'steps']=999999
            altered=source.enhance(changed,later_a,later_h)
        pd.testing.assert_frame_equal(reference.iloc[:4],altered.iloc[:4])

    def test_vendor_scores_do_not_enter_features(self):
        s,a,h=raw_fixture(1)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',pd.errors.PerformanceWarning)
            reference=source.enhance(s,a,h)
            s['score']=99.;s['score_recovery_index']=1.;a['score']=0.;h['target']=100.
            changed=source.enhance(s,a,h)
        pd.testing.assert_frame_equal(reference,changed)
        self.assertFalse(any('score' in name or 'target' in name for name in changed.columns))

    def test_nested_people_are_disjoint_and_complete(self):
        frame=pd.DataFrame({'participant':np.repeat([f'p{x}' for x in range(14)],5)})
        folds=train.nested_folds(frame);seen=[]
        for fold in folds:
            training=set(fold['training_people']);valid=set(fold['validation_people'])
            self.assertFalse(training&valid);seen.extend(valid)
            for inner in fold['inner']:
                self.assertFalse(set(inner['training_people'])&set(inner['validation_people']))
                self.assertEqual(set(inner['training_people'])|set(inner['validation_people']),training)
        self.assertEqual(sorted(seen),sorted(frame.participant.unique()))

    def test_all_new_estimators_handle_missing_constant_signals(self):
        rng=np.random.default_rng(42)
        frame=pd.DataFrame({'participant':np.repeat(['a','b','c','d'],15),'x':rng.normal(size=60),'constant':1.,
                            'missing':np.nan,'target':rng.uniform(30,90,size=60)})
        for algorithm in train.ALGORITHMS:
            with self.subTest(algorithm=algorithm):
                model=train.train(frame,['x','constant','missing'],algorithm)
                p=train.output(model,frame,['x','constant','missing'])
                self.assertTrue(np.isfinite(p).all())
                altered=frame.copy();altered.target=-999;altered.participant='unseen'
                np.testing.assert_array_equal(p,train.output(model,altered,['x','constant','missing']))


if __name__=='__main__':unittest.main()
