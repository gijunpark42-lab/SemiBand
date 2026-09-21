"""Round 48 live wiring: close mode — same-close labels from a switch date, market-on-close orders with the day-order fallback,
the close-refresh time, the wait/cutoff helper. Inert unless config.EXEC_MODE == "close".

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_close_exec
"""
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd

import broker
import config
import cycle
import ledger
import learner
import score
from agents.base import Signal
from alpaca.trading.enums import OrderSide, TimeInForce


class SameCloseLabels(unittest.TestCase):
    def _score(self, same_close_from):
        idx = pd.bdate_range("2024-01-01", periods=100)
        closes = pd.DataFrame({"SOXX": np.linspace(100, 160, 100), "AAA": np.linspace(50, 120, 100)}, index=idx)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(config, "STATE_DIR", root), patch.object(ledger, "DB", root / "ledger.sqlite"), \
                    patch.object(config, "AGENTS", ["technical"]), patch.object(config, "HORIZONS", (10,)), \
                    patch.object(config, "LABEL_SAME_CLOSE_FROM", same_close_from), \
                    patch.object(learner, "fit", return_value={"effective_weights": {}, "horizons": {}}):
                ledger.add_predictions(str(idx[60].date()), [Signal("technical", "AAA", 1.0, 0.5, 10, "")], {"AAA": 1.0}, {"AAA": 1.0})
                score.run(closes, str(idx[90].date()))
                with ledger.connect() as con:
                    return con.execute("SELECT ret, bench_ret FROM scores").fetchone(), closes

    def test_open_mode_labels_start_at_the_close_before_the_prediction_date(self):
        (ret, bench_ret), closes = self._score(None)
        self.assertAlmostEqual(ret, closes.AAA.iloc[69] / closes.AAA.iloc[59] - 1)

    def test_close_mode_labels_start_at_the_prediction_days_own_close_from_the_switch_date(self):
        (ret, bench_ret), closes = self._score("2024-01-01")
        self.assertAlmostEqual(ret, closes.AAA.iloc[70] / closes.AAA.iloc[60] - 1)
        self.assertAlmostEqual(bench_ret, closes.SOXX.iloc[70] / closes.SOXX.iloc[60] - 1)
        (ret_before, _), closes = self._score("2030-01-01")                  # a switch date after the prediction: the old label
        self.assertAlmostEqual(ret_before, closes.AAA.iloc[69] / closes.AAA.iloc[59] - 1)


class MarketOnClose(unittest.TestCase):
    def test_whole_share_moc_then_day_fallback(self):
        sent = []

        def submit(req):
            sent.append(req)
            if req.time_in_force == TimeInForce.CLS and sum(1 for r in sent if r.time_in_force == TimeInForce.CLS) > 1:
                raise RuntimeError("cls refused")                          # the second MOC is refused; day orders go through
            return SimpleNamespace(id=f"o{len(sent)}")

        with patch.object(broker, "_dry", return_value=False), patch.object(broker, "quote", return_value=(99.0, 101.0, 200.0)), \
                patch.object(broker, "_client", SimpleNamespace(submit_order=submit)):
            broker.moc("NVDA", 1005.0, OrderSide.BUY, "sb2-x")
            self.assertEqual((sent[0].qty, sent[0].time_in_force, sent[0].side), (10, TimeInForce.CLS, OrderSide.BUY))   # $1005 / 100 -> 10 shares
            broker.moc("NVDA", 1005.0, OrderSide.SELL, "sb2-y")               # the MOC is refused: a day order follows
            self.assertEqual(len(sent), 3)
            self.assertEqual(sent[2].time_in_force, TimeInForce.DAY)
        with patch.object(broker, "_dry", return_value=False), patch.object(broker, "quote", return_value=(99.0, 101.0, 200.0)), \
                patch.object(broker, "_client", SimpleNamespace(submit_order=lambda req: (sent.append(req) or SimpleNamespace(id="d")))):
            sent.clear()
            broker.moc("NVDA", 50.0, OrderSide.BUY, "sb2-z")                  # under one share: a day order, notional
            self.assertEqual(sent[0].time_in_force, TimeInForce.DAY)

    def test_close_moc_splits_whole_shares_and_the_fraction(self):
        sent = []
        client = SimpleNamespace(submit_order=lambda req: (sent.append(req) or SimpleNamespace(id=f"o{len(sent)}")),
                                 get_open_position=lambda s: SimpleNamespace(qty="284.8044"))
        with patch.object(broker, "_dry", return_value=False), patch.object(broker, "_client", client):
            broker.close_moc("VST", "sb2-c")
        self.assertEqual((sent[0].qty, sent[0].time_in_force, sent[0].side), (284, TimeInForce.CLS, OrderSide.SELL))
        self.assertEqual(sent[1].time_in_force, TimeInForce.DAY)
        self.assertAlmostEqual(sent[1].qty, 0.8044, places=4)
        self.assertEqual(sent[1].client_order_id, "sb2-c-frac")

    def test_dry_run_sends_nothing(self):
        with patch.object(broker, "_dry", return_value=True), patch.object(broker, "_client", SimpleNamespace()):
            self.assertIsNone(broker.moc("NVDA", 1000.0, OrderSide.BUY, "x"))
            self.assertIsNone(broker.close_moc("NVDA", "x"))


class CloseModeCycle(unittest.TestCase):
    def test_wait_until_et_refuses_past_the_cutoff(self):
        with patch.object(cycle.pd.Timestamp, "now", staticmethod(lambda tz=None: pd.Timestamp("2026-09-22 15:49", tz="America/New_York"))):
            self.assertFalse(cycle.wait_until_et("15:45", "15:48", "2026-09-22"))
        with patch.object(cycle.pd.Timestamp, "now", staticmethod(lambda tz=None: pd.Timestamp("2026-09-22 15:46", tz="America/New_York"))), \
                patch.object(cycle.time, "sleep") as sleep:
            self.assertTrue(cycle.wait_until_et("15:45", "15:48", "2026-09-22"))
            sleep.assert_not_called()                                      # already inside the window

    def test_the_refresh_prefers_prints_after_the_given_time(self):
        seen = {}

        def live_prices(symbols, prefer_after=None, **kw):
            seen["after"] = prefer_after
            return {}

        with patch.object(cycle.market, "live_prices", live_prices), patch.object(config, "OPEN_REFRESH_AGENTS", ("technical",)):
            cycle.open_refresh({"NVDA": "NVIDIA"}, [], "2026-09-22", {}, [], at="15:30")
        self.assertEqual(seen["after"], pd.Timestamp("2026-09-22 15:30", tz="America/New_York").tz_convert("UTC"))

    def test_the_live_execution_mode_and_its_label_date_agree(self):
        """Close execution scores its predictions from their own day's close, so the two settings move together
        (adopted 2026-09-21). An open-mode config must not carry a label date, and a close-mode config must."""
        self.assertIn(config.EXEC_MODE, ("open", "close"))
        if config.EXEC_MODE == "close":
            self.assertIsNotNone(config.LABEL_SAME_CLOSE_FROM)
            date.fromisoformat(config.LABEL_SAME_CLOSE_FROM)          # a real ISO date
            self.assertTrue(config.CLOSE_REFRESH_TIME < config.MOC_CUTOFF)
            self.assertTrue(config.LLM_STAGE_DEADLINE_CLOSE < config.CLOSE_REFRESH_TIME)
        else:
            self.assertIsNone(config.LABEL_SAME_CLOSE_FROM)


if __name__ == "__main__":
    unittest.main()
