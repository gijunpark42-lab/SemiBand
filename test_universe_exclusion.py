"""User exclusions (config.EXCLUDED_TICKERS; SHEL from 2026-09-24) never enter the universe, whether it is built fresh or read
from a cache written before the exclusion.

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_universe_exclusion
"""
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import config
import universe


class Exclusion(unittest.TestCase):
    def test_a_cache_written_before_the_exclusion_is_filtered(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            cache = Path(tmp) / "universe.json"
            cache.write_text(json.dumps({"date": date.today().isoformat(), "tickers": {"SHEL": "Shell", "NVDA": "NVIDIA"}}),
                             encoding="utf-8")
            with patch.object(universe, "CACHE", cache), patch.object(config, "EXCLUDED_TICKERS", ("SHEL",)):
                self.assertEqual(universe.load(), {"NVDA": "NVIDIA"})

    def test_a_fresh_build_drops_it_and_records_it(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            cache = Path(tmp) / "universe.json"
            with patch.object(universe, "CACHE", cache), patch.object(config, "STATE_DIR", Path(tmp)), \
                    patch.object(config, "EXCLUDED_TICKERS", ("SHEL",)), patch.object(config, "MAX_MARKET_CAP", None), \
                    patch.object(universe, "_from_graph", return_value={"SHEL": "Shell", "NVDA": "NVIDIA"}), \
                    patch.object(universe.broker, "tradable", side_effect=lambda tickers: tickers), \
                    patch.object(universe, "_market_caps", side_effect=lambda tickers: {t: 1e9 for t in tickers}):
                self.assertEqual(universe.refresh(), {"NVDA": "NVIDIA"})
                self.assertEqual(json.loads(cache.read_text(encoding="utf-8"))["excluded"], ["SHEL"])

    def test_shel_is_excluded_live(self):
        self.assertIn("SHEL", config.EXCLUDED_TICKERS)


if __name__ == "__main__":
    unittest.main()
