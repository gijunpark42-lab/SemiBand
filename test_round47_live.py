"""Round 47 live wiring: portfolio.apply_beta_floor (the trend-gated beta floor on the live targets).

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_round47_live
"""
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

import config
import portfolio


class ApplyBetaFloor(unittest.TestCase):
    def setUp(self):
        idx = pd.bdate_range("2025-01-01", periods=260)
        self.up = pd.DataFrame({config.IDLE_SLEEVE: np.linspace(100.0, 130.0, 260)}, index=idx)      # above its 200-day average
        self.down = pd.DataFrame({config.IDLE_SLEEVE: np.linspace(130.0, 100.0, 260)}, index=idx)    # below it
        self.equity = 1_000_000.0
        self.targets = {"ETR": 0.70 * self.equity, "XEL": 0.72 * self.equity}                       # gross 1.42, the live shape
        self.betas = {"ETR": 0.20, "XEL": 0.16, "NVDA": None}

    def test_off_when_unset_or_below_the_trend(self):
        with patch.object(config, "BETA_FLOOR", None):
            self.assertEqual(portfolio.apply_beta_floor(self.targets, self.betas, self.equity, self.up), (self.targets, 0.0, ""))
        with patch.object(config, "BETA_FLOOR", 0.5), patch.object(config, "IDLE_SLEEVE_TREND", 200):
            new, sleeve, why = portfolio.apply_beta_floor(self.targets, self.betas, self.equity, self.down)
            self.assertEqual((new, sleeve), (self.targets, 0.0))
            self.assertIn("off", why)

    def test_past_the_gross_ceiling_the_stocks_shrink_and_the_sleeve_brings_beta_to_the_floor(self):
        with patch.object(config, "BETA_FLOOR", 0.5), patch.object(config, "IDLE_SLEEVE_TREND", 200), patch.object(config, "GROSS_TARGET", 1.5):
            new, sleeve, why = portfolio.apply_beta_floor(self.targets, self.betas, self.equity, self.up)
        beta = 0.70 * 0.20 + 0.72 * 0.16                              # 0.2552
        k = (1.5 - 0.5) / (1.42 - beta)
        self.assertAlmostEqual(new["ETR"] / self.equity, 0.70 * k, places=6)
        self.assertAlmostEqual(new["XEL"] / self.equity, 0.72 * k, places=6)
        self.assertAlmostEqual(sleeve / self.equity, 0.5 - k * beta, places=6)
        self.assertAlmostEqual(sum(new.values()) / self.equity + sleeve / self.equity, 1.5, places=6)   # gross == the ceiling
        self.assertAlmostEqual(sum(v / self.equity * self.betas[t] for t, v in new.items()) + sleeve / self.equity, 0.5, places=6)
        self.assertIn("stocks scaled x", why)

    def test_with_room_under_the_ceiling_only_the_sleeve_is_added(self):
        small = {"ETR": 0.30 * self.equity}
        with patch.object(config, "BETA_FLOOR", 0.5), patch.object(config, "IDLE_SLEEVE_TREND", 200), patch.object(config, "GROSS_TARGET", 1.5):
            new, sleeve, why = portfolio.apply_beta_floor(small, self.betas, self.equity, self.up)
        self.assertEqual(new, {"ETR": 300000.0})
        self.assertAlmostEqual(sleeve / self.equity, 0.5 - 0.30 * 0.20, places=6)
        self.assertNotIn("scaled", why)

    def test_a_book_already_at_the_floor_is_left_alone(self):
        hot = {"NVDA": 0.6 * self.equity}                                # beta missing -> 1.0
        with patch.object(config, "BETA_FLOOR", 0.5), patch.object(config, "IDLE_SLEEVE_TREND", 200):
            new, sleeve, why = portfolio.apply_beta_floor(hot, self.betas, self.equity, self.up)
        self.assertEqual((new, sleeve), (hot, 0.0))
        self.assertIn("nothing to add", why)


if __name__ == "__main__":
    unittest.main()
