"""Round 38 learner research flags (intercept, dropped direction terms) are inert by default and do what they say when set.
No ledger, no network.

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_learner_flags
"""
import unittest
from unittest.mock import patch

import numpy as np

import learner
from agents.base import Signal


class Ridge(unittest.TestCase):
    def test_a_free_last_column_recovers_the_level_while_a_penalised_one_shrinks_it(self):
        rng = np.random.default_rng(0)
        y = 0.3 + 0.01 * rng.standard_normal(200)
        X = np.ones((200, 1))
        d = np.ones(200)
        free = learner.ridge(X, y, d, 150.0, np.zeros(1), free_last=True)
        shrunk = learner.ridge(X, y, d, 150.0, np.zeros(1))
        self.assertAlmostEqual(float(free[0]), float(y.mean()), places=6)
        self.assertAlmostEqual(float(shrunk[0]), float(y.sum() / (200 + 150)), places=6)

    def test_the_flags_off_leave_the_design_matrix_and_prior_untouched(self):
        X = np.arange(12, dtype=float).reshape(3, 4)
        X_aug, w0 = learner._augment(X, ["a", "b"])
        self.assertIs(X_aug, X)
        self.assertEqual(list(w0), [0.5, 0.5, 0.0, 0.0])

    def test_augment_zeroes_dropped_direction_columns_and_appends_a_constant(self):
        X = np.arange(12, dtype=float).reshape(3, 4)
        before = X.copy()
        with patch.object(learner, "INTERCEPT", "in"), patch.object(learner, "DROP_DIR", ("a",)):
            X_aug, w0 = learner._augment(X, ["a", "b"])
        np.testing.assert_array_equal(X, before)                                  # a copy was augmented
        self.assertEqual(X_aug.shape, (3, 5))
        self.assertEqual(list(X_aug[:, 2]), [0.0, 0.0, 0.0])                       # a's direction-only column (index n + 0)
        self.assertEqual(list(X_aug[:, 3]), [3.0, 7.0, 11.0])                      # b's stays
        self.assertEqual(list(X_aug[:, 4]), [1.0, 1.0, 1.0])
        self.assertEqual(list(w0), [0.5, 0.5, 0.0, 0.0, 0.0])


class Predict(unittest.TestCase):
    def _model(self, mode):
        m = {"agents": ["a", "b"], "horizons": {"10": {"reliability": 1.0, "w_conf": {"a": 0.5, "b": 0.5}, "w_dir": {"a": 0.0, "b": 0.0},
                                                       "intercept": -0.2}}}
        if mode:
            m["intercept_mode"] = mode
        return m

    def test_the_intercept_moves_convictions_only_when_it_is_in(self):
        with patch.object(learner.config, "AGENTS", ["a", "b"]), patch.object(learner.config, "HORIZONS", (10,)):
            signals = [Signal("a", "X", 1.0, 1.0, 10, ""), Signal("b", "X", 1.0, 1.0, 10, "")]
            base, _ = learner.predict(signals, self._model(None))
            fit_only, _ = learner.predict(signals, self._model("fit_only"))
            added, _ = learner.predict(signals, self._model("in"))
        self.assertAlmostEqual(base["X"], 1.0)                                     # 0.5 + 0.5, no intercept
        self.assertAlmostEqual(fit_only["X"], 1.0)
        self.assertAlmostEqual(added["X"], 0.8)


if __name__ == "__main__":
    unittest.main()
