import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from neurasign_engine.fatigueset import absolute_answer_start,BASE_FEATURES


class FatigueSetTests(unittest.TestCase):
    def test_each_answer_uses_own_absolute_marker(self):
        answer={'fatigueSurveySubmissionTime':1037.,'physicalFatigueAnswerTime':1030.}
        self.assertEqual(absolute_answer_start(answer,1216000),1209.)
        shifted={k:v+180 for k,v in answer.items()}
        self.assertEqual(absolute_answer_start(shifted,1216000),1209.)

    def test_invalid_survey_timing_rejected(self):
        with self.assertRaises(ValueError):
            absolute_answer_start({'fatigueSurveySubmissionTime':3,'physicalFatigueAnswerTime':4},1000)

    def test_features_exclude_reference_and_nonwrist_signals(self):
        for name in BASE_FEATURES:
            self.assertFalse(any(v in name.lower() for v in ['fatigue','label','eeg','chest','task','session','participant']))


if __name__=='__main__':unittest.main()
