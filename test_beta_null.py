"""Round 57: the shrunk 250-day beta (point-in-time, shrinks noisy betas toward the cross-section, off by default) and the
constrained-random null of the replay.

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_beta_null
"""
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

import backtest
import config
import learning_targets as lt
from agents import macro


def prices(n=400, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2024-01-01", periods=n)
    m = rng.normal(0.0005, 0.02, n)
    cols = {"SOXX": 100 * np.cumprod(1 + m)}
    for k, beta in enumerate((0.3, 0.8, 1.2, 1.6, 2.0)):
        cols[f"S{k}"] = 50 * np.cumprod(1 + beta * m + rng.normal(0, 0.02 + 0.01 * k, n))
    return pd.DataFrame(cols, index=idx)


class Vasicek(unittest.TestCase):
    def test_default_is_unchanged(self):
        c = prices()
        self.assertEqual(config.BETA_ESTIMATOR, "ols60")
        pd.testing.assert_frame_equal(lt.rolling_beta(c), lt.rolling_beta(c, estimator="ols60"))

    def test_point_in_time(self):
        c = prices()
        full = lt.rolling_beta(c, estimator="vasicek250")
        cut = lt.rolling_beta(c.iloc[:300], estimator="vasicek250")
        pd.testing.assert_series_equal(full.iloc[299], cut.iloc[299])     # later prices never move an earlier beta

    def test_shrinks_toward_the_cross_section_and_keeps_order(self):
        c = prices()
        raw = lt.rolling_beta(c, window=250, estimator="ols60")            # unshrunk reference on the same window length
        raw = (c.pct_change().rolling(250, min_periods=120).cov(c.pct_change()["SOXX"])
               .div(c.pct_change()["SOXX"].rolling(250, min_periods=120).var(), axis=0)).iloc[-1]
        vas = lt.rolling_beta(c, estimator="vasicek250").iloc[-1]
        stocks = [f"S{k}" for k in range(5)]
        mean = raw[stocks].mean()
        for s in stocks:
            self.assertLessEqual(abs(vas[s] - mean), abs(raw[s] - mean) + 1e-12)
        self.assertEqual(list(vas[stocks].sort_values().index), list(raw[stocks].sort_values().index))
        self.assertEqual(vas["SOXX"], 1.0)

    def test_macro_reads_the_shared_beta(self):
        c = prices()
        betas = lt.rolling_beta(c, estimator="vasicek250")
        with patch.object(config, "BETA_ESTIMATOR", "vasicek250"), patch.object(macro, "regime", return_value=(0.5, "test")):
            out = macro.run({"S0": "a", "S4": "b"}, {"closes": c, "asof": c.index[-1].date(), "asof_ts": c.index[-1], "betas": betas})
        by = {s.ticker: s for s in out}
        self.assertIn("shrunk 250-day", by["S0"].reason)
        self.assertGreater(by["S4"].direction, by["S0"].direction)        # risk-on: the higher beta gets the higher vote


class Null(unittest.TestCase):
    def test_same_distribution_random_ranking_and_reproducible(self):
        traded = {f"T{k}": v for k, v in enumerate(np.linspace(-0.3, 0.4, 50))}
        a = backtest.null_scores(traded, np.random.default_rng(7), {}, 0.9)
        b = backtest.null_scores(traded, np.random.default_rng(7), {}, 0.9)
        self.assertEqual(a, b)
        vals, real = np.array(list(a.values())), np.array(list(traded.values()))
        self.assertAlmostEqual(vals.mean(), real.mean(), places=9)
        self.assertAlmostEqual(vals.std(), real.std(), places=9)
        self.assertLess(abs(np.corrcoef(vals, real)[0, 1]), 0.5)

    def test_persistence(self):
        traded = {f"T{k}": v for k, v in enumerate(np.linspace(-0.3, 0.4, 200))}
        rng, state = np.random.default_rng(1), {}
        d1 = backtest.null_scores(traded, rng, state, 0.9)
        d2 = backtest.null_scores(traded, rng, state, 0.9)
        self.assertGreater(np.corrcoef(list(d1.values()), list(d2.values()))[0, 1], 0.7)


if __name__ == "__main__":
    unittest.main()
