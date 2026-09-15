"""Open refresh and signal reuse: cycle.open_refresh, ledger.predictions_on / replace_predictions. No network.

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_open_refresh
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import cycle
import ledger
from agents.base import Signal


class Ledger(unittest.TestCase):
    def test_replace_swaps_only_the_named_agents_and_reuse_reads_them_back(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(ledger, "DB", Path(tmp) / "ledger.sqlite"):
            ledger.add_predictions("2026-09-14", [Signal("technical", "NVDA", 0.2, 0.5, 10, "pre-open"),
                                                  Signal("llm_news", "NVDA", 0.4, 0.6, 20, "claude")],
                                   {"NVDA": 100.0}, {"NVDA": 1.2})
            ledger.replace_predictions("2026-09-14", ["technical"], [Signal("technical", "NVDA", -0.3, 0.5, 10, "open")],
                                       {"NVDA": 95.0}, {"NVDA": 1.2})
            rows = {(r["agent"], r["ticker"]): r for r in ledger.predictions_on("2026-09-14")}
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[("technical", "NVDA")]["reason"], "open")
            self.assertEqual(rows[("llm_news", "NVDA")]["reason"], "claude")
            self.assertEqual(ledger.predictions_on("2026-09-11"), [])


class OpenRefresh(unittest.TestCase):
    def setUp(self):
        idx = pd.to_datetime(["2026-09-10", "2026-09-11"])
        self.closes = pd.DataFrame({"NVDA": [100.0, 102.0], "AMD": [50.0, 51.0], "SOXX": [500.0, 527.0],
                                    "SPY": [760.0, 764.0], "^VIX": [15.0, 16.0], "^TNX": [4.0, 4.1]}, index=idx)
        self.universe = {"NVDA": "NVIDIA", "AMD": "AMD"}
        self.pre = [Signal("technical", "NVDA", 0.5, 0.5, 10, "pre"), Signal("llm_news", "NVDA", 0.3, 0.6, 20, "claude"),
                    Signal("macro", "AMD", 0.1, 0.4, 10, "pre"), Signal("risk", "AMD", -0.2, 0.5, 10, "pre")]

    def test_price_agents_rerun_on_a_live_row_and_everything_else_is_kept(self):
        seen = {}

        def fake_run(name, universe, ctx):
            seen[name] = ctx["closes"]
            return [] if name == "risk" else [Signal(name, "NVDA", -0.4, 0.5, 10, "open")]

        notes = []
        with patch.object(cycle.market, "live_prices", return_value={"NVDA": 97.0, "SOXX": 502.0}), \
                patch.object(cycle.market, "closes", return_value=self.closes), \
                patch.object(cycle, "_run_agent", side_effect=fake_run), \
                patch.object(cycle.ledger, "replace_predictions") as replace, \
                patch.object(cycle.config, "OPEN_REFRESH_AGENTS", ("technical", "risk", "macro")):
            signals, live = cycle.open_refresh(self.universe, self.pre, "2026-09-14", {"NVDA": 1.2}, notes)
        frame = seen["technical"]
        self.assertEqual(frame.index[-1], pd.Timestamp("2026-09-14"))
        self.assertEqual(frame.loc["2026-09-14", "NVDA"], 97.0)       # today's print
        self.assertEqual(frame.loc["2026-09-14", "AMD"], 51.0)        # no print today: last close
        self.assertEqual(frame.loc["2026-09-14", "^VIX"], 16.0)
        by = {(s.agent, s.ticker): s for s in signals}
        self.assertEqual(by[("technical", "NVDA")].reason, "open")
        self.assertEqual(by[("llm_news", "NVDA")].reason, "claude")
        self.assertNotIn(("macro", "AMD"), by)                        # macro re-ran: its fresh output replaces the old
        self.assertEqual(by[("risk", "AMD")].reason, "pre")           # risk returned nothing: pre-open signal kept
        self.assertEqual(replace.call_args.args[1], ["technical", "macro"])
        self.assertEqual(live, {"NVDA": 97.0, "SOXX": 502.0})
        self.assertIn("SOXX -4.7% vs last close", notes[0])

    def test_no_live_prices_keeps_the_pre_open_signals(self):
        with patch.object(cycle.market, "live_prices", return_value={}), patch.object(cycle, "_run_agent") as run:
            signals, live = cycle.open_refresh(self.universe, self.pre, "2026-09-14", {}, [])
        self.assertEqual(signals, self.pre)
        self.assertEqual(live, {})
        run.assert_not_called()


class Fundamentals(unittest.TestCase):
    def test_live_price_reprices_the_valuation_ratios_without_touching_the_cache(self):
        from agents import fundamentals
        info = {"NVDA": {"currentPrice": 100.0, "targetMeanPrice": 122.0, "numberOfAnalystOpinions": 10,
                         "forwardPE": 62.0, "priceToSalesTrailing12Months": 16.0}}
        with patch.object(fundamentals.market, "fundamentals", return_value=info):
            before = fundamentals.run({"NVDA": "NVIDIA"}, {})[0]
            after = fundamentals.run({"NVDA": "NVIDIA"}, {"live_prices": {"NVDA": 95.0}})[0]
        self.assertLess(before.direction, 0)                   # fwd PE 62 and P/S 16 penalised, target only +22%
        self.assertGreater(after.direction, 0)                 # at 95: fwd PE 59 (no penalty), target +28%
        self.assertIn("target +28%", after.reason)
        self.assertEqual(info["NVDA"]["currentPrice"], 100.0)   # the day's cache is not modified


class LiveLabels(unittest.TestCase):
    def test_label_starts_at_the_close_before_the_prediction_date(self):
        import numpy as np
        import config
        import learner
        import score
        idx = pd.bdate_range("2024-01-01", periods=100)
        closes = pd.DataFrame({"SOXX": np.linspace(100, 160, 100), "AAA": np.linspace(50, 120, 100)}, index=idx)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(config, "STATE_DIR", root), patch.object(ledger, "DB", root / "ledger.sqlite"), \
                    patch.object(config, "AGENTS", ["technical"]), patch.object(config, "HORIZONS", (10,)), \
                    patch.object(learner, "fit", return_value={"effective_weights": {}, "horizons": {}}):
                ledger.add_predictions(str(idx[60].date()), [Signal("technical", "AAA", 1.0, 0.5, 10, "")], {"AAA": 1.0}, {"AAA": 1.0})
                score.run(closes, str(idx[90].date()))
                with ledger.connect() as con:
                    ret, bench_ret = con.execute("SELECT ret, bench_ret FROM scores").fetchone()
        self.assertAlmostEqual(ret, closes.AAA.iloc[69] / closes.AAA.iloc[59] - 1)
        self.assertAlmostEqual(bench_ret, closes.SOXX.iloc[69] / closes.SOXX.iloc[59] - 1)


if __name__ == "__main__":
    unittest.main()
