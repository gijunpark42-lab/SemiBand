"""Round 31 replay flags are refused when they cannot mean anything, and parallel replays share one price download.
No data, no network: the flag checks run before loading (a missing check fails on a patched _run instead of downloading),
and the download is mocked.

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_backtest_flags
"""
import os
import pickle
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import backtest


class RefreshFlags(unittest.TestCase):
    def setUp(self):
        # a missing guard must fail here, not go on to rebuild the universe, download prices or write progress files
        for name in ("_run", "publish_progress"):
            p = patch.object(backtest, name, side_effect=AssertionError(f"run() got past its checks into {name}"))
            p.start()
            self.addCleanup(p.stop)

    def test_hybrid_and_agent_list_need_the_refresh(self):
        with self.assertRaises(ValueError):
            backtest.run(exec_mode="open", learn_preopen=True)
        with self.assertRaises(ValueError):
            backtest.run(exec_mode="open", refresh_agents=("technical",))

    def test_open_labels_need_open_execution(self):
        with self.assertRaises(ValueError):
            backtest.run(exec_mode="close", label_open=True)

    def test_a_mistyped_refresh_agent_is_refused(self):
        with self.assertRaises(ValueError):
            backtest.run(exec_mode="open", open_refresh=True, refresh_agents=("technical", "mean_reverson"))

    def test_an_empty_refresh_agent_list_is_refused(self):
        with self.assertRaises(ValueError):
            backtest.run(exec_mode="open", open_refresh=True, refresh_agents=())


class LongShortWeights(unittest.TestCase):
    def test_top_long_bottom_short_beta_matched_within_the_gross(self):
        conv = {"A": 0.3, "B": 0.1, "C": -0.1, "D": -0.4}
        betas = {"A": 1.5, "B": 1.5, "C": 1.0, "D": 1.0}
        w = backtest.long_short_weights(conv, betas, 1, 1.5)
        self.assertEqual(sorted(w), ["A", "D"])
        self.assertAlmostEqual(w["A"], 0.6)                               # gross / (1 + r) with r = 1.5
        self.assertAlmostEqual(w["D"], -0.9)                              # the low-beta short leg is the larger one
        self.assertAlmostEqual(sum(abs(x) for x in w.values()), 1.5)      # gross never exceeds the target
        self.assertAlmostEqual(sum(x * betas[t] for t, x in w.items()), 0.0)

    def test_the_beta_ratio_is_bounded_and_bad_or_tiny_inputs_are_handled(self):
        w = backtest.long_short_weights({"A": 0.2, "B": -0.2}, {"A": 5.0, "B": 0.5}, 1, 1.0)
        self.assertAlmostEqual(w["A"], 1 / 3)                             # r capped at 2
        self.assertAlmostEqual(w["B"], -2 / 3)
        self.assertEqual(backtest.long_short_weights({"A": 0.2}, {}, 3, 1.0), {})
        w = backtest.long_short_weights({"A": 0.2, "B": float("nan"), "C": -0.2}, {}, 1, 1.0)
        self.assertEqual(sorted(w), ["A", "C"])                           # a non-finite conviction is ignored


class PriceCacheRace(unittest.TestCase):
    def test_a_run_that_loses_the_race_trades_on_the_winners_prices(self):
        idx = pd.bdate_range("2026-09-01", periods=3)
        winner = pd.DataFrame({"NVDA": [1.0, 2.0, 3.0]}, index=idx)
        mine = pd.DataFrame({"NVDA": [9.0, 9.0, 9.0]}, index=idx)
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"BACKTEST_PRICE_CACHE": tmp}):
            path = Path(tmp) / f"closes_{date.today().isoformat()}_10_1.pkl"

            def download(*args, **kwargs):
                path.write_bytes(pickle.dumps(winner))      # a parallel run lands its file while this one downloads
                return mine

            with patch.object(backtest.market, "closes", side_effect=download):
                out = backtest._prices("closes", ["NVDA"], 10)
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), [path.name])   # no temp file left behind
        pd.testing.assert_frame_equal(out, winner)

    def test_the_first_run_writes_the_cache_and_returns_its_download(self):
        idx = pd.bdate_range("2026-09-01", periods=3)
        mine = pd.DataFrame({"NVDA": [9.0, 9.0, 9.0]}, index=idx)
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"BACKTEST_PRICE_CACHE": tmp}):
            with patch.object(backtest.market, "closes", return_value=mine):
                out = backtest._prices("closes", ["NVDA"], 10)
            cached = pickle.loads((Path(tmp) / f"closes_{date.today().isoformat()}_10_1.pkl").read_bytes())
        pd.testing.assert_frame_equal(out, mine)
        pd.testing.assert_frame_equal(cached, mine)


if __name__ == "__main__":
    unittest.main()
