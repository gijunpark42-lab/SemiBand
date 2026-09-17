"""Round 40 switch (2026-09-17): TECHNICAL_RESIDUAL makes the technical agent's relative returns beta-adjusted residuals.
Off, the agent is unchanged. No network.

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_round40_flags
"""
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

import config
from agents import technical


def _frame(seed=3, n=260):
    """SOXX crashes 30% over the last 20 days; LOW has beta 0.3 (falls ~9%), HIGH has beta 1.5 (falls ~45%), both with small noise."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2025-01-02", periods=n)
    soxx_r = rng.normal(0.0004, 0.02, n)
    soxx_r[-20:] = -0.0175                                   # a steady 30% slide
    low_r = 0.3 * soxx_r + rng.normal(0, 0.004, n)
    high_r = 1.5 * soxx_r + rng.normal(0, 0.004, n)
    cols = {config.BENCHMARK: 100 * np.cumprod(1 + soxx_r), "LOW": 100 * np.cumprod(1 + low_r), "HIGH": 100 * np.cumprod(1 + high_r),
            "SPY": 100 * np.cumprod(1 + rng.normal(0.0003, 0.01, n))}
    return pd.DataFrame(cols, index=idx)


class ResidualMomentum(unittest.TestCase):
    def setUp(self):
        self.ctx = {"closes": _frame()}
        self.universe = {"LOW": "Low Beta Co", "HIGH": "High Beta Co"}

    def test_off_is_the_plain_relative_return(self):
        with patch.object(config, "TECHNICAL_RESIDUAL", False):
            sig = {s.ticker: s for s in technical.run(self.universe, self.ctx)}
        c = self.ctx["closes"]
        b20 = c[config.BENCHMARK].iloc[-1] / c[config.BENCHMARK].iloc[-21] - 1
        rel20_low = c["LOW"].iloc[-1] / c["LOW"].iloc[-21] - 1 - b20
        self.assertIn(f"rel20 {rel20_low*100:+.1f}%", sig["LOW"].reason)
        self.assertNotIn("beta", sig["LOW"].reason)
        self.assertGreater(sig["LOW"].direction, sig["HIGH"].direction)      # plain: the low-beta name "won" the crash

    def test_on_removes_the_beta_illusion(self):
        with patch.object(config, "TECHNICAL_RESIDUAL", False):
            plain = {s.ticker: s for s in technical.run(self.universe, self.ctx)}
        with patch.object(config, "TECHNICAL_RESIDUAL", True):
            resid = {s.ticker: s for s in technical.run(self.universe, self.ctx)}
        self.assertIn("beta 0.3", resid["LOW"].reason)
        self.assertIn("beta 1.5", resid["HIGH"].reason)
        self.assertLess(resid["LOW"].direction, plain["LOW"].direction)      # LOW's edge over SOXX was just low beta
        self.assertGreater(resid["HIGH"].direction, plain["HIGH"].direction)  # HIGH's loss was mostly beta
        self.assertLess(abs(resid["LOW"].direction - resid["HIGH"].direction), abs(plain["LOW"].direction - plain["HIGH"].direction))

    def test_beta_is_clipped_and_defaults_to_one_without_history(self):
        c = self.ctx["closes"].copy()
        c["FLAT"] = 100.0                                                    # zero variance name: beta from cov 0 -> 0.0 (clipped range)
        with patch.object(config, "TECHNICAL_RESIDUAL", True):
            sig = {s.ticker: s for s in technical.run({"FLAT": "Flat Co", "LOW": "Low"}, {"closes": c})}
        self.assertIn("beta 0.00", sig["FLAT"].reason)


if __name__ == "__main__":
    unittest.main()
