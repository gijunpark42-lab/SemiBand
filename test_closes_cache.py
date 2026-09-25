"""2026-09-25: today's closes cache is refetched when it does not cover the requested lookback (a shorter call wrote it
first), and a long cache still serves a shorter request.

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_closes_cache
"""
import pickle
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import config
import market


def frame(start, end, cols):
    idx = pd.bdate_range(start, end)
    return pd.DataFrame({c: [float(i) for i in range(len(idx))] for c in cols}, index=idx)


class ClosesCache(unittest.TestCase):
    def _closes(self, cached_from_days_ago, lookback):
        today = date.today()
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp, patch.object(config, "STATE_DIR", Path(tmp)):
            cache = Path(tmp) / f"closes_{today.isoformat()}.pkl"
            cache.write_bytes(pickle.dumps(frame(today - timedelta(days=cached_from_days_ago), today - timedelta(days=1), ["AAA", "SOXX"])))
            full = frame(today - timedelta(days=lookback), today - timedelta(days=1), ["AAA", "SOXX"])
            calls = []

            def download(symbols, start=None, **kwargs):
                calls.append((tuple(symbols), start))
                return pd.concat({"Close": full[list(symbols)]}, axis=1)

            with patch.object(market.yf, "download", download):
                out = market.closes(["AAA", "SOXX"], lookback_days=lookback)
        return out, calls

    def test_a_short_cache_is_refetched(self):
        out, calls = self._closes(200, 420)
        self.assertEqual(len(calls), 1)
        self.assertLessEqual(out.index[0], pd.Timestamp(date.today() - timedelta(days=410)))

    def test_a_long_cache_serves_a_shorter_request(self):
        out, calls = self._closes(420, 200)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
