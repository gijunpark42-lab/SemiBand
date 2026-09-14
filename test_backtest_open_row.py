"""The open-refresh backtest row: day t+1's open is appended, day t+1's close is never read. No network.

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_backtest_open_row
"""
import unittest

import numpy as np
import pandas as pd

import backtest


class OpenRowWindow(unittest.TestCase):
    def test_appends_the_next_open_and_never_the_next_close(self):
        idx = pd.to_datetime(["2026-09-09", "2026-09-10", "2026-09-11"])
        closes = pd.DataFrame({"NVDA": [100.0, 102.0, 150.0], "AMD": [50.0, np.nan, 99.0],
                               "SOXX": [500.0, 510.0, 900.0], "^VIX": [15.0, 16.0, 40.0]}, index=idx)
        opens = pd.DataFrame({"NVDA": [99.0, 101.0, 97.0], "AMD": [49.0, 51.0, np.nan],
                              "SOXX": [498.0, 505.0, 480.0]}, index=idx)
        w = backtest.open_row_window(closes, opens, 1)
        self.assertEqual(list(w.index), list(idx))
        self.assertEqual(w.loc["2026-09-11", "NVDA"], 97.0)       # the next open
        self.assertEqual(w.loc["2026-09-11", "SOXX"], 480.0)
        self.assertEqual(w.loc["2026-09-11", "AMD"], 50.0)        # no open that day: last known close
        self.assertEqual(w.loc["2026-09-11", "^VIX"], 16.0)       # not traded: last close
        pd.testing.assert_frame_equal(w.iloc[:2], closes.iloc[:2])
        self.assertNotIn(150.0, w["NVDA"].tolist())               # day t+1 closes never appear
        self.assertNotIn(900.0, w["SOXX"].tolist())

    def test_refresh_requires_open_execution(self):
        with self.assertRaises(ValueError):
            backtest.run(days=5, exec_mode="close", open_refresh=True)

    def test_only_one_label_start(self):
        with self.assertRaises(ValueError):
            backtest.run(days=5, exec_mode="open", open_refresh=True, label_open=True, label_next_close=True)


if __name__ == "__main__":
    unittest.main()
