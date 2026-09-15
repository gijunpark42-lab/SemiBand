"""Cross-asset factor agents: loadings recover a known exposure, the direction follows exposure x factor trend, and a replay
never downloads. No network.

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_factors
"""
import unittest

import numpy as np
import pandas as pd

from agents import factors
from agents import factor_oil


def synthetic(days=330, names=30, oil_up=True, seed=7):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2025-06-02", periods=days)
    m = rng.normal(0.0005, 0.012, days)
    f = rng.normal(0.0, 0.015, days)
    if oil_up:
        f[-60:] += 0.004                                  # a clear recent uptrend in oil
    exposures = np.linspace(-2.0, 2.0, names)
    data = {"SOXX": 100 * np.cumprod(1 + m), "CL=F": 70 * np.cumprod(1 + f)}
    for j, b in enumerate(exposures):
        data[f"S{j:02d}"] = 50 * np.cumprod(1 + 1.0 * m + b * f + rng.normal(0, 0.004, days))
    return pd.DataFrame(data, index=idx), dict(zip([f"S{j:02d}" for j in range(names)], exposures))


class Factors(unittest.TestCase):
    def test_loadings_recover_the_exposure_net_of_soxx(self):
        closes, exposures = synthetic()
        loads = factors.loadings("oil", closes, list(exposures))
        self.assertEqual(len(loads), len(exposures))
        for ticker, b in exposures.items():
            self.assertAlmostEqual(loads[ticker], b, delta=0.15)

    def test_direction_follows_exposure_times_trend(self):
        closes, exposures = synthetic(oil_up=True)
        universe = {t: t for t in exposures}
        sig = factors.signal(factors.level("oil", closes), "price")
        self.assertGreater(sig, 0)
        out = {s.ticker: s for s in factor_oil.run(universe, {"closes": closes, "asof": closes.index[-1]})}
        self.assertEqual(len(out), len(exposures))
        self.assertGreater(out["S29"].direction, 0.5)      # most oil-exposed stock leans long while oil rises
        self.assertLess(out["S00"].direction, -0.5)        # the most negatively exposed leans short
        self.assertTrue(all(s.agent == "factor_oil" and s.horizon == 20 for s in out.values()))

    def test_replay_without_the_symbol_returns_nothing_instead_of_downloading(self):
        closes, exposures = synthetic()
        closes = closes.drop(columns=["CL=F"])
        self.assertEqual(factor_oil.run({t: t for t in exposures}, {"closes": closes, "asof": closes.index[-1]}), [])

    def test_rate_factor_uses_level_changes(self):
        closes, _ = synthetic()
        closes["ZQ=F"] = 96.0 - np.linspace(0, 0.5, len(closes))   # implied rate 4.0 -> 4.5: hawkish repricing
        lvl = factors.level("fed", closes)
        self.assertAlmostEqual(float(lvl.iloc[-1]), 4.5, places=6)
        self.assertGreater(factors.signal(lvl, "rate"), 0)


if __name__ == "__main__":
    unittest.main()
