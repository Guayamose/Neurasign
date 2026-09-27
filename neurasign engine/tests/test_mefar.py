"""Protect causal extraction, group weighting and exclusion of label metadata."""
import unittest
from pathlib import Path
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from neurasign_engine import mefar_data as data
from neurasign_engine import mefar_benchmark as bench


class MefarTests(unittest.TestCase):
    def test_future_signal_cannot_change_window(self):
        values = np.sin(np.arange(200)*.1)[:,None]+60
        channel = {'hr':{'start':0.,'rate':1.,'values':values.copy()}}
        original = data.features(channel,120.,60.)
        channel['hr']['values'][:60] = 150
        channel['hr']['values'][120:] = 200
        changed = data.features(channel,120.,60.)
        for key in original:
            np.testing.assert_allclose(original[key],changed[key],equal_nan=True)

    def test_missing_channel_preserves_nan(self):
        extracted = data.features({},100.,60.)
        self.assertEqual(set(extracted),set(data.FEATURES))
        self.assertTrue(all(np.isnan(value) for value in extracted.values()))

    def test_partial_channel_rejected(self):
        values = np.full((30,1),60.)
        extracted = data.features({'hr':{'start':0.,'rate':1.,'values':values}},60.,60.)
        self.assertTrue(np.isnan(extracted['hr_mean']))

    def test_profile_whitelist(self):
        for config in bench.CONFIGS:
            columns = bench.columns(config)
            self.assertTrue(all(name.startswith(f"w{config['width']}__") for name in columns))
            self.assertFalse(any(any(word in name for word in ['cfs','session','participant','outcome','eeg']) for name in columns))
        with self.assertRaises(ValueError):
            bench.columns({'width':60,'profile':'participant','algorithm':'logit1'})

    def test_balancing_people_and_sessions(self):
        frame = pd.DataFrame({'participant':['a']*100+['b']*2,'unit_id':['a1']*100+['b1','b2'],
                              'outcome':[0]*100+[0,1]})
        values = bench.metric(frame,np.ones(len(frame)))
        self.assertAlmostEqual(values['accuracy'],.25)
        self.assertAlmostEqual(values['balanced_accuracy'],.5)

    def test_label_metadata_never_enters_fit(self):
        config = {'width':60,'profile':'cardiac','algorithm':'logit1'}
        random = np.random.default_rng(4)
        frame = pd.DataFrame(random.normal(size=(40,len(bench.columns(config)))),columns=bench.columns(config))
        frame['participant'] = np.repeat(['a','b','c','d'],10)
        frame['unit_id'] = frame.participant+'_'+np.tile(np.repeat(['low','high'],5),4)
        frame['outcome'] = np.tile([0]*5+[1]*5,4);frame['row_id'] = np.arange(40)
        artifact = bench.fit(frame,config);first = bench.predict(artifact,frame)
        frame['outcome'] = 1-frame.outcome;frame['participant'] = 'different';frame['cfs'] = 999
        np.testing.assert_allclose(first,bench.predict(artifact,frame))
        self.assertFalse(artifact['production_enabled'])


if __name__ == '__main__':
    unittest.main()
