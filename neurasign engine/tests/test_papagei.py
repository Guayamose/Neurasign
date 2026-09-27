"""Leakage, missingness and train-only projection checks for experiment 009."""
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from neurasign_engine.papagei import prepare_chunk, aggregate_embeddings, load_encoder
from neurasign_engine.papagei_training import design, ENGINEERED


class PaPaGeiTests(unittest.TestCase):
    def test_frozen_checkpoint_is_independent_of_other_batch_members(self):
        root = Path(__file__).resolve().parents[1]
        if not (root/'data/external/papagei/papagei_s.pt').exists():
            self.skipTest('Published checkpoint has not been downloaded')
        import torch
        torch.set_num_threads(1)
        model = load_encoder(root)
        self.assertFalse(model.training)
        self.assertFalse(any(p.requires_grad for p in model.parameters()))
        times = np.arange(1280)/64
        wave = prepare_chunk(times, np.sin(times*7), 20)
        batch = torch.from_numpy(np.stack([wave, wave*20])).unsqueeze(1)
        with torch.inference_mode():
            together = model(batch)[0].numpy()[0]
            alone = model(batch[:1])[0].numpy()[0]
        self.assertEqual(alone.shape, (512,))
        np.testing.assert_allclose(together, alone, rtol=1e-4, atol=1e-6)

    def test_future_waveform_cannot_change_completed_chunk(self):
        times = np.arange(64*40)/64
        x = np.sin(times*2*np.pi*1.1)+.2*np.sin(times*2*np.pi*2.2)
        expected = prepare_chunk(times, x, 20)
        x[times >= 20] = 1e8
        np.testing.assert_array_equal(prepare_chunk(times, x, 20), expected)
        self.assertEqual(expected.shape, (1250,))
        self.assertTrue(np.isfinite(expected).all())

    def test_missing_gap_and_flat_inputs_are_rejected(self):
        times = np.arange(1280)/64
        self.assertIsNone(prepare_chunk(times, np.zeros(1280), 20))
        x = np.sin(times*7)
        self.assertIsNone(prepare_chunk(np.delete(times, slice(100, 110)), np.delete(x, slice(100, 110)), 20))
        x[700] = np.nan
        self.assertIsNone(prepare_chunk(times, x, 20))

    def test_aggregation_is_past_only_and_needs_real_history(self):
        rng = np.random.default_rng(4)
        x = rng.normal(size=(30, 512)).astype(np.float32)
        expected = aggregate_embeddings(x, 180)
        x[18:] = 1e8
        np.testing.assert_array_equal(aggregate_embeddings(x, 180), expected)
        self.assertIsNone(aggregate_embeddings(x, 170))
        x[15] = np.nan
        self.assertIsNone(aggregate_embeddings(x, 180))

    def test_pca_does_not_fit_validation_rows(self):
        rng = np.random.default_rng(4)
        embeddings = rng.normal(size=(55, 3, 512)).astype(np.float32)
        frame = pd.DataFrame(rng.normal(size=(55, len(ENGINEERED))), columns=ENGINEERED)
        frame['mental_demand'] = 99
        first, p1 = design(frame, embeddings, np.arange(45), 'fused60', 'cat4')
        embeddings[45:] += 1e5
        frame.loc[45:, ENGINEERED] += 1e5
        second, p2 = design(frame, embeddings, np.arange(45), 'fused60', 'cat4')
        np.testing.assert_allclose(first[:45], second[:45], rtol=1e-5, atol=1e-5)
        np.testing.assert_array_equal(p1[0][0].mean_, p2[0][0].mean_)
        self.assertEqual(first.shape[1], 32+len(ENGINEERED))


if __name__ == '__main__':
    unittest.main()
