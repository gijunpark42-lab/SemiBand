"""Audit fixes (2026-09-17): drifted holdings, FRED inputs live-only, bounded best-quarter share, a trial-count floor for the
deflated Sharpe, an idempotent replay roster. No network.

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_audit_fixes
"""
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

import backtest
import config
import market
import robustness
from agents import macro


class DriftedHoldings(unittest.TestCase):
    def test_weights_grow_with_their_own_return_and_renormalise_to_the_grown_equity(self):
        w = {"A": 0.5, "B": 0.5}
        out = backtest.drifted(w, {"A": 0.10, "B": -0.10})          # equity unchanged: A is now 55% and B 45%
        self.assertAlmostEqual(out["A"], 0.55)
        self.assertAlmostEqual(out["B"], 0.45)
        out = backtest.drifted({"A": 1.0}, {"A": 0.10})               # a fully invested single name stays 100%
        self.assertAlmostEqual(out["A"], 1.0)
        out = backtest.drifted({"A": 0.5, "__SLEEVE__": 0.5}, {"A": None, "__SLEEVE__": 0.20})   # a missing price counts as 0
        self.assertAlmostEqual(out["A"], 0.5 / 1.10)
        self.assertAlmostEqual(out["__SLEEVE__"], 0.6 / 1.10)
        self.assertEqual(backtest.drifted({}, {}), {})
        out = backtest.drifted({"A": 0.5, "B": 0.5}, {"A": 0.10, "B": -0.10}, net_ret=-0.01)   # costs shrink the equity the weights are shares of
        self.assertAlmostEqual(out["A"], 0.55 / 0.99)
        self.assertEqual(backtest.drifted({"A": 1.0}, {"A": -1.0}), {})                  # a wiped-out book has no holdings


class FredLiveOnly(unittest.TestCase):
    def _closes(self):
        idx = pd.bdate_range("2025-01-02", periods=260)
        rng = np.random.default_rng(1)
        return pd.DataFrame({config.BENCHMARK: 100 * np.cumprod(1 + rng.normal(0.001, 0.02, 260)),
                             "SPY": 100 * np.cumprod(1 + rng.normal(0.0005, 0.01, 260)),
                             "^VIX": np.full(260, 15.0), "^TNX": np.full(260, 4.0)}, index=idx)

    def test_a_replay_never_reads_todays_fred_values(self):
        closes = self._closes()
        with patch.object(market, "fred_latest", return_value={"latest": -1.0, "date": "2026-09-11"}) as fred:
            r_live, why_live = macro.regime(closes, live=True)
            r_replay, why_replay = macro.regime(closes, live=False)
        self.assertIn("NFCI loose", why_live)
        self.assertNotIn("NFCI", why_replay)
        self.assertGreater(r_live, r_replay)
        with patch.object(market, "fred_latest", return_value={"latest": -1.0}) as fred:
            macro.run({"AAA": "A"}, {"closes": closes.assign(AAA=closes[config.BENCHMARK]), "asof": closes.index[-1].date()})
        fred.assert_not_called()


class RobustnessFixes(unittest.TestCase):
    def test_best_quarter_share_is_bounded_when_a_quarter_loses(self):
        curve = []
        eq = 1.0
        for d in pd.bdate_range("2025-01-02", periods=380):
            eq *= 1.004 if d.quarter != 2 else 0.997                    # Q2 loses, the rest gain
            curve.append({"date": d.date().isoformat(), "portfolio": eq, "soxx": 1.0})
        share = robustness.best_quarter_share(curve)
        self.assertIsNotNone(share)
        self.assertLessEqual(share, 1.0)

    def test_the_trial_count_never_falls_below_the_research_floor(self):
        rets = np.random.default_rng(2).normal(0.002, 0.02, 300)
        eq = np.cumprod(1 + rets)
        curve = [{"date": d.date().isoformat(), "portfolio": float(e), "soxx": 1.0} for d, e in zip(pd.bdate_range("2025-01-02", periods=300), eq)]
        with patch.object(robustness, "sweep_trials", return_value=(0, [])), patch.object(config, "RESEARCH_TRIALS", 330):
            out = robustness.summary(curve)
        self.assertEqual(out["deflated"]["n_trials"], 330)


class ReplayRoster(unittest.TestCase):
    def test_the_roster_is_rebuilt_from_the_live_list_every_run(self):
        with patch.object(backtest, "_run", return_value=None), patch.object(config, "AGENTS", list(config.AGENTS)):
            backtest.run(exec_mode="open", extra=("momentum",))
            backtest.run(exec_mode="open", extra=("momentum",))
        self.assertEqual(backtest.PIT_AGENTS.count("momentum"), 1)


if __name__ == "__main__":
    unittest.main()


class SimulatedRoster(unittest.TestCase):
    def test_every_simulated_agent_outside_the_fixed_set_has_a_module(self):
        import importlib
        for name in backtest.SIM_AGENTS:
            if name not in backtest.SPECIAL_AGENTS:
                mod = importlib.import_module(f"agents.{name}")
                self.assertEqual(mod.NAME, name)
                self.assertTrue(callable(mod.run))
        self.assertIn("customer_momentum", backtest.SIM_AGENTS)
