"""Data guards from the 2026-09-15 audit: events reads the last valid closes over the stock's own dates, a failed download is
never cached, and the guardian remembers three previous check days. No network.

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_data_guards
"""
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

import config
import market
from agents import events


class EventsLastValidClose(unittest.TestCase):
    def test_a_trailing_row_filled_only_by_an_index_does_not_hide_the_reaction(self):
        idx = pd.bdate_range("2026-08-03", periods=31)
        closes = pd.DataFrame({"SOXX": np.linspace(500, 510, 31), "NVDA": np.linspace(100, 130, 31)}, index=idx)
        closes.loc[pd.Timestamp("2026-09-15")] = [np.nan, np.nan]          # the day's partial row (only ^VIX had a value)
        report = str(idx[-5].date())
        earnings = {"NVDA": [{"date": report, "eps_estimate": 1.0, "reported_eps": 1.2, "surprise_pct": 20.0}]}
        out = events.run({"NVDA": "NVIDIA"}, {"closes": closes, "earnings": earnings, "asof": idx[-1].date()})
        self.assertEqual(len(out), 1)
        self.assertIn("confirms", out[0].reason)                            # the price reaction was measured
        self.assertAlmostEqual(out[0].confidence, 0.6)


class ClosesCache(unittest.TestCase):
    def test_a_symbol_whose_download_failed_is_not_cached_and_is_retried(self):
        idx = pd.bdate_range("2026-09-01", periods=10)
        first = pd.concat({"Close": pd.DataFrame({"NVDA": np.arange(10.0) + 100, "SOXX": np.nan}, index=idx)}, axis=1)
        second = pd.concat({"Close": pd.DataFrame({"SOXX": np.arange(10.0) + 500}, index=idx)}, axis=1)
        with tempfile.TemporaryDirectory() as tmp, patch.object(config, "STATE_DIR", Path(tmp)), \
                patch.object(market.yf, "download", side_effect=[first, second]) as download:
            a = market.closes(["NVDA", "SOXX"])
            self.assertTrue(a["SOXX"].isna().all())
            b = market.closes(["NVDA", "SOXX"])
            self.assertEqual(download.call_count, 2)                       # the empty SOXX column was fetched again
            self.assertEqual(download.call_args_list[1].args[0], ["SOXX"])
            self.assertEqual(float(b["SOXX"].iloc[-1]), 509.0)
            self.assertEqual(float(b["NVDA"].iloc[-1]), 109.0)


class EventsBenchmarkDates(unittest.TestCase):
    def test_the_benchmark_is_measured_over_the_stock_own_dates(self):
        idx = pd.bdate_range("2026-08-03", periods=31)
        soxx = np.linspace(500, 510, 31)
        soxx[-3:] = [600, 700, 800]                                           # the benchmark rallies after the stock stops trading
        nvda = np.linspace(100, 130, 31)
        nvda[-3:] = np.nan
        closes = pd.DataFrame({"SOXX": soxx, "NVDA": nvda}, index=idx)
        earnings = {"NVDA": [{"date": str(idx[-10].date()), "eps_estimate": 1.0, "reported_eps": 1.2, "surprise_pct": 20.0}]}
        out = events.run({"NVDA": "NVIDIA"}, {"closes": closes, "earnings": earnings, "asof": idx[-1].date()})
        self.assertEqual(len(out), 1)
        self.assertIn("confirms", out[0].reason)                            # +5.8% vs SOXX's +0.5% to the same date, not -52%


class GuardianSeenMemory(unittest.TestCase):
    def test_the_second_check_of_a_day_still_remembers_three_previous_days(self):
        import guardian
        # the file after the first check of 09-15: today plus the three previous check days
        seen_by = {"2026-09-11": ["b"], "2026-09-12": ["c"], "2026-09-14": ["d"], "2026-09-15": ["e"]}
        seen, older = guardian.seen_titles(seen_by, "2026-09-15")
        self.assertEqual(older, {"b", "c", "d"})
        self.assertEqual(seen, {"b", "c", "d", "e"})


class ModelSaveRetry(unittest.TestCase):
    def test_a_momentarily_locked_model_file_is_still_replaced(self):
        import json
        import learner
        real, calls = Path.replace, []

        def flaky(self, target):
            calls.append(target)
            if len(calls) < 3:
                raise PermissionError(5, "Access is denied")            # a scanner holds the old file for a moment
            return real(self, target)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.json"
            path.write_text("{}", encoding="utf-8")
            with patch.object(Path, "replace", flaky), patch("time.sleep"):
                learner.save_model({"weights": {"risk": 0.2}}, path)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"weights": {"risk": 0.2}})
            self.assertEqual(len(calls), 3)
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ["model.json"])

    def test_a_file_that_stays_locked_raises_and_leaves_no_temp_file(self):
        import learner

        def locked(self, target):
            raise PermissionError(5, "Access is denied")

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.json"
            path.write_text("{}", encoding="utf-8")
            with patch.object(Path, "replace", locked), patch("time.sleep") as sleep, self.assertRaises(PermissionError):
                learner.save_model({"weights": {}}, path)
            self.assertEqual(sleep.call_count, 19)
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ["model.json"])
            self.assertEqual(path.read_text(encoding="utf-8"), "{}")          # the previous model is still readable


if __name__ == "__main__":
    unittest.main()
