import sys
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from neurasign_engine.reference_benchmark import weights,metrics,split_people,fit,predict
from neurasign_engine.readiness_oura import enrich_sleep,SLEEP,ACTIVITY


class ReferenceBenchmarkTests(unittest.TestCase):
    def test_people_have_equal_metric_weight(self):
        frame=pd.DataFrame({'participant':['a']*9+['b'],'target':[0]*9+[1]})
        self.assertAlmostEqual(weights(frame)[:9].sum(),weights(frame)[9:].sum())
        result=metrics(frame,np.zeros(10),'classification')
        self.assertAlmostEqual(result['accuracy'],.5)
        self.assertAlmostEqual(result['balanced_accuracy'],.5)
        self.assertEqual(result['high_recall'],0.)

    def test_regression_tolerance_is_not_accuracy(self):
        frame=pd.DataFrame({'participant':['a','a','b','b'],'target':[10,20,30,40]})
        result=metrics(frame,np.array([15,25,45,55]),'regression')
        self.assertAlmostEqual(result['mae'],10.)
        self.assertEqual(result['agreement_within_10'],.5)
        self.assertNotIn('accuracy',result)

    def test_split_independent_of_input_order(self):
        people=[str(i) for i in range(18)]
        a=split_people(people);b=split_people(people[::-1])
        self.assertEqual(a,b)
        self.assertFalse(set(a['development']) & set(a['test']))

    def test_labels_and_ids_are_not_model_inputs(self):
        frame=pd.DataFrame({'participant':['a']*5+['b']*5,'target':[0]*5+[1]*5,'signal':range(10)})
        model=fit(frame,['signal'],'classification','linear1');p=predict(model,frame,['signal'],'classification')
        altered=frame.copy();altered.target=1-frame.target;altered.participant='unknown'
        np.testing.assert_array_equal(p,predict(model,altered,['signal'],'classification'))

    def test_oura_future_data_cannot_change_earlier_features(self):
        end=pd.Timestamp('2020-01-02 16:00:00Z').timestamp()*1000
        row={c:1. for c in SLEEP};row.update(date='2020-01-02',bedtime_start_timestamp=end-8*3600*1000,bedtime_end_timestamp=end)
        activity=pd.DataFrame([{**{c:2. for c in ACTIVITY},'day_end_timestamp':end-3600000}])
        heart=pd.DataFrame({'timestamp':[end-300000,end-200000,end-100000],'heart_rate':[60.,62.,61.],'heart_rmssd':[30.,35.,32.]})
        before=enrich_sleep(pd.DataFrame([row]),activity,heart)
        future={**row,'date':'2020-01-03','bedtime_start_timestamp':end+16*3600*1000,'bedtime_end_timestamp':end+24*3600*1000,'rmssd':999.}
        extra_activity={**{c:999. for c in ACTIVITY},'day_end_timestamp':end+3600000}
        after=enrich_sleep(pd.DataFrame([row,future]),pd.concat([activity,pd.DataFrame([extra_activity])]),heart)
        pd.testing.assert_frame_equal(before,after.iloc[[0]].reset_index(drop=True))


if __name__=='__main__':unittest.main()
