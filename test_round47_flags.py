"""Round 47 (2026-09-18): the events pre-earnings switch, the constant customer-momentum confidence, the chain cap, the replay flags.

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_round47_flags
"""
import inspect
import unittest
from datetime import date
from unittest.mock import patch

import numpy as np
import pandas as pd

import config
import portfolio
from agents import customer_momentum, events
from test_link_momentum import LinkMomentum


class EventsPreLeg(unittest.TestCase):
    def setUp(self):
        idx = pd.bdate_range("2026-01-02", periods=60)
        self.closes = pd.DataFrame({config.BENCHMARK: np.full(60, 100.0), "NVDA": np.full(60, 100.0)}, index=idx)
        self.ctx = {"closes": self.closes, "asof": date(2026, 3, 2), "earnings": {"NVDA": [{"date": "2026-03-05", "surprise_pct": 5.0}]}}

    def test_the_pre_earnings_vote_can_be_switched_off(self):
        with patch.object(config, "EVENTS_PRE_LEG", True):
            sig = events.run({"NVDA": "Nvidia"}, self.ctx)
            self.assertEqual([(s.ticker, s.direction) for s in sig], [("NVDA", -0.25)])
        with patch.object(config, "EVENTS_PRE_LEG", False):
            self.assertEqual(events.run({"NVDA": "Nvidia"}, self.ctx), [])
        with patch.object(config, "EVENTS_PRE_LEG", False):                     # the drift leg is untouched by the switch
            ctx = dict(self.ctx, asof=date(2026, 3, 9))
            sig = events.run({"NVDA": "Nvidia"}, ctx)
            self.assertEqual(len(sig), 1)
            self.assertGreater(sig[0].direction, 0)


class ConstantConfidence(LinkMomentum):
    def test_momentum_conf_replaces_the_customer_count(self):
        with patch.object(config, "MOMENTUM_CONF", 0.5):
            sig = {s.ticker: s for s in customer_momentum.run(self.universe, {"closes": self.closes})}
        self.assertEqual({s.confidence for s in sig.values()}, {0.5})
        with patch.object(config, "MOMENTUM_CONF", None):
            plain = {s.ticker: s for s in customer_momentum.run(self.universe, {"closes": self.closes})}
        self.assertEqual(plain["CHIP"].confidence, 0.35)                                   # 0.3 + 0.05 x 1 customer
        self.assertAlmostEqual(sig["CHIP"].direction, plain["CHIP"].direction, places=12)  # the direction is unchanged


class ChainCap(unittest.TestCase):
    def test_the_power_group_is_scaled_to_the_cap_and_nothing_else_moves(self):
        groups = {"ETR": "power", "XEL": "power", "NVDA": "chip"}
        w = {"ETR": 0.20, "XEL": 0.20, "NVDA": 0.10, "__SLEEVE__": 0.05}
        out = portfolio.chain_cap(w, groups, "power", 0.30)
        self.assertAlmostEqual(out["ETR"], 0.15)
        self.assertAlmostEqual(out["XEL"], 0.15)
        self.assertEqual((out["NVDA"], out["__SLEEVE__"]), (0.10, 0.05))
        self.assertEqual(portfolio.chain_cap(w, groups, "power", 0.50), w)                 # under the cap: unchanged
        self.assertEqual(portfolio.chain_cap({"NVDA": 0.3}, groups, "power", 0.1), {"NVDA": 0.3})   # no members: unchanged


class ReplayFlags(unittest.TestCase):
    def test_run_takes_the_round_47_parameters(self):
        import backtest
        params = inspect.signature(backtest.run).parameters
        for name in ("events_pre_leg", "momentum_conf", "chain_cap", "exclude_group"):
            self.assertIn(name, params)


if __name__ == "__main__":
    unittest.main()
