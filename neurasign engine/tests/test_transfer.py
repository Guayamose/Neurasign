import unittest
import numpy as np
import pandas as pd
from neurasign_engine.external_labeled import native_intervals,resistance_to_conductance
from neurasign_engine.transfer_features import FEATURES,add_history,extract
from neurasign_engine.transfer_training import grouped_folds,fit_weights,metrics,columns
from neurasign_engine.causal import Trace


class TransferTests(unittest.TestCase):
    def test_reference_does_not_use_future_or_other_people(self):
        rows=[]
        for person in ['a','b']:
            for end in [60,120,180,240,300]:
                rows.append({**{f:float(end) for f in FEATURES},'participant':person,'session':'one','source_end':end})
        d=pd.DataFrame(rows);a=add_history(d)
        altered=d.copy();altered.loc[4,FEATURES]=99999.;altered.loc[5:,FEATURES]=-99999.
        b=add_history(altered)
        self.assertTrue(np.isnan(a.loc[2,'eda_mean__delta']))
        self.assertEqual(a.loc[3,'eda_mean__delta'],120)
        self.assertEqual(a.loc[3,'eda_mean__delta'],b.loc[3,'eda_mean__delta'])

    def test_missing_channels_remain_missing(self):
        trace=Trace(np.arange(60,dtype=float),np.full(60,70.),1,'bpm')
        d=extract({'heart_rate':trace},60.)
        self.assertEqual(d['heart_rate_mean'],70)
        self.assertTrue(np.isnan(d['eda_mean']))
        self.assertTrue(np.isnan(d['pulse_interval_rmssd_ms']))

    def test_resistance_units_and_invalid_values(self):
        a=resistance_to_conductance([1000,500,0,-2,np.nan])
        np.testing.assert_allclose(a[:2],[1,2]);self.assertTrue(np.isnan(a[2:]).all())

    def test_native_rr_does_not_difference_across_gap(self):
        t=np.r_[np.arange(1,29.),np.arange(33,59.)];rr=np.ones(len(t))
        d=native_intervals(t,rr,60.)
        self.assertEqual(d['native_rmssd_ms'],0)
        self.assertLess(d['native_coverage'],1)
        bad=native_intervals(np.r_[np.arange(1,20.),np.arange(45,59.)],np.ones(33),60.)
        self.assertTrue(np.isnan(bad['native_rmssd_ms']))

    def test_person_splits_and_equal_dataset_weights(self):
        d=pd.DataFrame({'participant':['a','a','b','c'],'unit_id':['u','u','v','w'],'dataset':['x','x','x','y']})
        folds=grouped_folds(d);all_ids=[v for f in folds for v in f]
        self.assertEqual(len(all_ids),len(set(all_ids)))
        w=fit_weights(d);self.assertAlmostEqual(w[:3].sum(),w[3])
        self.assertAlmostEqual(w[:2].sum(),w[2])

    def test_metrics_weight_people_and_blocks_not_windows(self):
        d=pd.DataFrame({'participant':['a','a','b'],'unit_id':['x','x','y'],'mental_demand':[0,0,100]})
        m=metrics(d,'mental_demand',[0,0,0])
        self.assertEqual(m['mae'],50);self.assertEqual(m['within_tolerance'],.5)

    def test_predictor_allowlist(self):
        d=pd.DataFrame(columns=FEATURES+[f+'__delta' for f in FEATURES])
        self.assertNotIn('mental_demand',columns('all_history',d))
        self.assertEqual(len(columns('all_history',d)),56)


if __name__=='__main__':unittest.main()
