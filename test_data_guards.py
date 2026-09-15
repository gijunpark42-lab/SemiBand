"""Data guards from the 2026-09-15 audit: events reads the last valid closes, and a failed download is never cached. No network.

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


if __name__ == "__main__":
    unittest.main()
