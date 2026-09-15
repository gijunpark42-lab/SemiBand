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
