"""Point-in-time equivalence (2026-09-16, from AQuA's "temporal footprint" lesson): nothing dated after the day may change
the day's signal. The replay's fast paths (full-history series sliced "as of" the day, the RSI precompute) must give
exactly the prefix computation, and the graph map must ignore statements dated after asof. No network.

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_point_in_time
"""
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

import config
from agents import graph_pit, indicators, macro, risk, supply_chain, technical, mean_reversion

T = 250          # the simulated day (row index) inside a 320-row history


def _closes(seed=7, n=320):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2025-01-02", periods=n)
    cols = {}
    for name, drift, vol in (("A", 0.0006, 0.03), ("B", -0.0002, 0.02), ("C", 0.0004, 0.05), (config.BENCHMARK, 0.0005, 0.025),
                             ("SPY", 0.0003, 0.012)):
        cols[name] = 100 * np.cumprod(1 + rng.normal(drift, vol, n))
    cols["^VIX"] = np.clip(20 + np.cumsum(rng.normal(0, 0.8, n)), 10, 60)
    cols["^TNX"] = np.clip(4.2 + np.cumsum(rng.normal(0, 0.03, n)), 2, 7)
    return pd.DataFrame(cols, index=idx)


def _hist(closes, tickers):
    """As backtest._run builds ctx["hist"]: full-history close / return series and (name, benchmark) return pairs."""
    bench = closes[config.BENCHMARK].pct_change()
    hist = {}
    for tk in list(tickers) + [config.BENCHMARK]:
        c_full = closes[tk].dropna()
        hist[tk] = {"close": c_full, "rets": c_full.pct_change().dropna()}
        if tk != config.BENCHMARK:
            hist[tk]["pair"] = pd.concat([closes[tk].pct_change(), bench], axis=1).dropna()
    return hist


def _sig(signals):
    return sorted((s.ticker, round(s.direction, 12), round(s.confidence, 12), s.horizon, s.reason) for s in signals)


class ReplayFastPathsEqualThePrefix(unittest.TestCase):
    def setUp(self):
        self.closes = _closes()
        self.universe = {"A": "A Corp", "B": "B Inc", "C": "C Ltd"}
        self.prefix = self.closes.iloc[: T + 1]
        self.slow = {"closes": self.prefix, "asof": self.prefix.index[-1].date(), "today": self.prefix.index[-1].date().isoformat()}
        self.fast = dict(self.slow, hist=_hist(self.closes, self.universe), asof_ts=self.closes.index[T])

    def test_risk_sliced_history_equals_the_prefix_computation(self):
        self.assertEqual(_sig(risk.run(self.universe, self.fast)), _sig(risk.run(self.universe, self.slow)))
        self.assertTrue(risk.run(self.universe, self.slow))

    def test_macro_sliced_pairs_equal_the_prefix_computation(self):
        self.assertEqual(_sig(macro.run(self.universe, self.fast)), _sig(macro.run(self.universe, self.slow)))
        self.assertTrue(macro.run(self.universe, self.slow))

    def test_future_rows_never_reach_a_prefix_agent(self):
        """The day loop hands each agent closes.iloc[:i+1]; a row after the day with an absurd move must not matter."""
        shocked = self.closes.copy()
        shocked.iloc[T + 1:, :5] *= 5.0
        for mod in (technical, mean_reversion, risk, macro):
            a = mod.run(self.universe, dict(self.slow, closes=shocked.iloc[: T + 1]))
            b = mod.run(self.universe, self.slow)
            self.assertEqual(_sig(a), _sig(b), mod.__name__)


class RsiPrecomputeIsCausal(unittest.TestCase):
    def test_full_history_rsi_matches_the_prefix_rsi_on_every_day(self):
        s = _closes()["A"]
        full = indicators.rsi_series(s)
        for t in (60, 120, T):
            pre = indicators.rsi_series(s.iloc[: t + 1])
            self.assertAlmostEqual(float(full.iloc[t]), float(pre.iloc[-1]), places=9)
        saved = indicators.PRECOMPUTED
        try:
            indicators.PRECOMPUTED = {"A": full}
            self.assertAlmostEqual(indicators.rsi(s.iloc[: T + 1]), float(indicators.rsi_series(s.iloc[: T + 1]).iloc[-1]), places=9)
        finally:
            indicators.PRECOMPUTED = saved


def _label(d, kind="Q"):
    return f"Alpha {kind} ({d.month:02d}-{d.day:02d}-{d.year})"


class GraphMapIgnoresStatementsAfterAsof(unittest.TestCase):
    def _graph(self, with_future):
        asof = self.asof
        alpha = [{"quarter": _label(asof - timedelta(days=30)), "signal": "capacity sold out, raised guidance", "chain": "hbm"}]
        beta = [{"quarter": _label(asof - timedelta(days=10)), "signal": "steady", "chain": "hbm"}]
        if with_future:
            alpha.append({"quarter": _label(asof + timedelta(days=3)), "signal": "demand exceeds supply, record backlog", "chain": "hbm"})
            beta.append({"quarter": _label(asof + timedelta(days=1)), "signal": "capacity constraints sold out", "chain": "hbm"})
        nodes = [{"id": "Alpha Corp", "chains": ["hbm"], "quarterly_data": alpha},
                 {"id": "Beta Inc", "chains": ["hbm"], "quarterly_data": beta}]
        return {"nodes": nodes, "edges": [{"source": "Alpha Corp", "target": "Beta Inc"}]}

    def _map(self, with_future):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        (root / "graph").mkdir()
        (root / "graph" / "merged_graph.json").write_text(json.dumps(self._graph(with_future)), encoding="utf-8")
        (root / "graph" / "exposure.json").write_text(json.dumps({"companies": {}}), encoding="utf-8")
        with patch.object(config, "EARNINGS_AI_DIR", root):
            supply_chain._load.cache_clear()
            pit = graph_pit.PointInTimeMap()
        supply_chain._load.cache_clear()
        tmp.cleanup()
        return pit

    def test_future_dated_rows_change_nothing_as_of_the_day(self):
        self.asof = date(2026, 6, 15)
        plain, future = self._map(False), self._map(True)
        for company, ticker in (("Alpha Corp", "ALP"), ("Beta Inc", "BET")):
            a, b = plain.supply_chain(ticker, company, self.asof), future.supply_chain(ticker, company, self.asof)
            self.assertEqual((a.direction, a.confidence, a.reason), (b.direction, b.confidence, b.reason))
            a, b = plain.neighbors(ticker, company, self.asof), future.neighbors(ticker, company, self.asof)
            self.assertEqual((a.direction, a.confidence, a.reason), (b.direction, b.confidence, b.reason))
        later = future.supply_chain("ALP", "Alpha Corp", self.asof + timedelta(days=5))
        self.assertGreater(later.direction, plain.supply_chain("ALP", "Alpha Corp", self.asof).direction)   # visible once dated


if __name__ == "__main__":
    unittest.main()
