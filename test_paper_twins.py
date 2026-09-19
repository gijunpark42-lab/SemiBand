"""Paper twins: the marking arithmetic (drifted holdings, cost), the two-session lag, the open-mode books, the alternative
confidence rule, the book construction with and without the floor.

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_paper_twins
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

import config
import paper_twins
from agents.base import Signal


class Marking(unittest.TestCase):
    def test_one_period_with_cost_and_drift(self):
        with patch.object(config, "COST_BPS", 5):
            ret, drifted = paper_twins.mark_book({}, {"A": 0.5, "B": 0.5}, {"A": 100.0, "B": 100.0}, {"A": 110.0, "B": 90.0})
        self.assertAlmostEqual(ret, 0.0 - 1.0 * 0.0005, places=9)             # +5% -5% gross, one unit of turnover at 5 bps
        self.assertGreater(drifted["A"], drifted["B"])
        self.assertAlmostEqual(drifted["A"] + drifted["B"], 1.0 / (1 + ret), places=9)
        ret2, _ = paper_twins.mark_book({"A": 0.5, "B": 0.5}, {"A": 0.5, "B": 0.5}, {"A": 100.0, "B": 100.0}, {"A": 100.0, "B": 100.0})
        self.assertEqual(ret2, 0.0)                                             # unchanged book, flat prices: no turnover, no cost

    def test_books_are_marked_two_sessions_later_and_open_books_from_opens(self):
        idx = pd.bdate_range("2026-09-21", periods=4)                          # Mon..Thu
        closes = pd.DataFrame({"SOXX": [100.0, 102.0, 101.0, 105.0], "A": [50.0, 55.0, 52.0, 60.0]}, index=idx)
        opens = {"2026-09-22": {"A": 51.0, "SOXX": 101.0}, "2026-09-23": {"A": 54.0, "SOXX": 100.0}}
        with tempfile.TemporaryDirectory() as tmp, patch.object(config, "STATE_DIR", Path(tmp)), patch.object(config, "COST_BPS", 0):
            paper_twins.record("2026-09-21", {"live_model": {"A": 1.0}, "open_exec": {"A": 1.0}}, "close")
            self.assertEqual(paper_twins.mark("2026-09-22", closes.iloc[:2], lambda days: {}), 1)   # the close book: close Mon -> close Tue
            s = paper_twins.summary()
            self.assertAlmostEqual(s["live_model"]["return"], 55.0 / 50.0 - 1, places=6)
            self.assertNotIn("open_exec", s)                                    # needs the Tue and Wed opens
            self.assertEqual(paper_twins.mark("2026-09-23", closes.iloc[:3], lambda days: opens), 1)
            s = paper_twins.summary()
            self.assertAlmostEqual(s["open_exec"]["return"], 54.0 / 51.0 - 1, places=3)   # open Tue -> open Wed (summary rounds to 4 places)
            self.assertEqual(paper_twins.mark("2026-09-24", closes, lambda days: opens), 0)   # nothing left unmarked
            self.assertIn("live_model +10.00% (1 d)", paper_twins.note(s))


class Books(unittest.TestCase):
    def test_alt_conf_flips_the_customer_momentum_rule_only(self):
        sig = [Signal("customer_momentum", "NVDA", 0.4, 0.5, 20, "3 customers, 21d return +4.0% vs SOXX"),
               Signal("technical", "NVDA", 0.2, 0.6, 10, "x")]
        with patch.object(config, "MOMENTUM_CONF", 0.5):
            out = paper_twins.alt_conf_signals(sig)
        self.assertAlmostEqual(out[0].confidence, 0.45)                        # the count rule: 0.3 + 0.05 x 3
        self.assertEqual(out[1].confidence, 0.6)
        with patch.object(config, "MOMENTUM_CONF", None):
            out = paper_twins.alt_conf_signals(sig)
        self.assertEqual(out[0].confidence, 0.5)                               # the constant rule

    def test_book_with_and_without_the_floor(self):
        idx = pd.bdate_range("2025-01-01", periods=260)
        closes = pd.DataFrame({config.IDLE_SLEEVE: np.linspace(100.0, 130.0, 260)}, index=idx)
        conv = {"ETR": 0.25, "XEL": 0.24}
        with patch.object(config, "BETA_FLOOR", 0.5), patch.object(config, "IDLE_SLEEVE_TREND", 200), patch.object(config, "GROSS_TARGET", 1.5), \
                patch.object(config, "VOL_TARGET", None):
            with_floor = paper_twins.book(conv, 1_000_000.0, None, closes, {"ETR": 0.1, "XEL": 0.1})
            without = paper_twins.book(conv, 1_000_000.0, None, closes, {"ETR": 0.1, "XEL": 0.1}, floor=False)
        self.assertGreater(with_floor.get(config.IDLE_SLEEVE, 0.0), 0.3)          # the floor puts SOXX in
        self.assertLess(with_floor["ETR"], without["ETR"] + 1e-12)              # and never enlarges a stock


if __name__ == "__main__":
    unittest.main()
