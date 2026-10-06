"""2026-10-06 live scorecard statistics.

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_live_scorecard
"""
import unittest

import numpy as np

import live_scorecard as ls


class Scorecard(unittest.TestCase):
    def test_regression_recovers_beta_and_alpha(self):
        rng = np.random.default_rng(0)
        b = rng.normal(0.001, 0.02, 2000)
        r = 0.0004 + 0.3 * b + rng.normal(0, 0.005, 2000)
        reg = ls.regression(r, b)
        self.assertAlmostEqual(reg["beta"], 0.3, delta=0.02)
        self.assertAlmostEqual(reg["alpha_annual"], 0.0004 * 252, delta=0.03)
        self.assertGreater(reg["alpha_t"], 2)

    def test_stats(self):
        s = ls.stats([0.10, -0.10, 0.05])
        self.assertAlmostEqual(s["return"], 1.1 * 0.9 * 1.05 - 1)
        self.assertAlmostEqual(s["max_drawdown"], 0.10)
        self.assertIsNotNone(s["sortino"])


if __name__ == "__main__":
    unittest.main()
