"""Insider shadow agent (2026-09-17): point-in-time by filing date, 60-day window, derivative and routine buys ignored.
No network; a temp state folder.

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_insider
"""
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import config
from agents import insider


def _row(name, filed, traded, shares, price, code="P", derivative=False):
    return {"name": name, "filingDate": filed, "transactionDate": traded, "change": shares, "transactionPrice": price,
            "transactionCode": code, "isDerivative": derivative, "symbol": "X"}


class InsiderAgent(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        state = Path(self.tmp.name)
        (state / "insider").mkdir()
        self.patch = patch.object(config, "STATE_DIR", state)
        self.patch.start()
        insider._purchases.cache_clear()
        self.universe = {"AAA": "A Corp", "BBB": "B Inc", "CCC": "C Ltd"}

    def tearDown(self):
        self.patch.stop()
        insider._purchases.cache_clear()
        self.tmp.cleanup()

    def _write(self, ticker, rows):
        (Path(self.tmp.name) / "insider" / f"{ticker}.json").write_text(json.dumps({"fetched": "2026-09-17", "data": {"data": rows}}),
                                                                        encoding="utf-8")
        insider._purchases.cache_clear()

    def test_a_purchase_counts_from_its_filing_date_for_sixty_days(self):
        self._write("AAA", [_row("Jane Doe", "2026-06-10", "2026-06-08", 1000, 50.0)])
        before = insider.run(self.universe, {"asof": date(2026, 6, 9)})        # traded but not yet filed: unknown to the market
        filing_day = insider.run(self.universe, {"asof": date(2026, 6, 10)})  # filed during that day: not in a pre-open signal
        on = insider.run(self.universe, {"asof": date(2026, 6, 11)})
        late = insider.run(self.universe, {"asof": date(2026, 8, 20)})         # 71 days after the filing
        self.assertEqual(before, [])
        self.assertEqual(filing_day, [])
        self.assertEqual([s.ticker for s in on], ["AAA"])
        self.assertGreater(on[0].direction, 0)
        self.assertEqual(on[0].horizon, 20)
        self.assertEqual(late, [])

    def test_sales_derivatives_and_small_buys_are_ignored(self):
        self._write("BBB", [_row("A", "2026-06-10", "2026-06-09", 1000, 50.0, code="S"),
                            _row("B", "2026-06-10", "2026-06-09", 1000, 50.0, derivative=True),
                            _row("C", "2026-06-10", "2026-06-09", 10, 50.0)])       # $500
        self.assertEqual(insider.run(self.universe, {"asof": date(2026, 6, 15)}), [])

    def test_a_routine_buyer_is_not_a_signal_but_a_first_time_buyer_is(self):
        self._write("CCC", [_row("Routine Rob", "2025-06-05", "2025-06-03", 500, 40.0),
                            _row("Routine Rob", "2026-06-04", "2026-06-02", 500, 40.0),      # same month, a year later: on a schedule
                            _row("New Nora", "2026-06-06", "2026-06-05", 5000, 40.0)])
        sig = insider.run(self.universe, {"asof": date(2026, 6, 12)})
        self.assertEqual(len(sig), 1)
        self.assertIn("1 insider(s)", sig[0].reason)
        self.assertIn("$200,000", sig[0].reason)
        first_year = insider.run(self.universe, {"asof": date(2025, 6, 12)})          # in 2025 Rob had no history: he counted then
        self.assertEqual(len(first_year), 1)

    def test_more_buyers_and_more_dollars_mean_a_stronger_signal(self):
        self._write("AAA", [_row("One", "2026-06-10", "2026-06-09", 1000, 20.0)])
        self._write("BBB", [_row("One", "2026-06-10", "2026-06-09", 50000, 20.0), _row("Two", "2026-06-11", "2026-06-10", 50000, 20.0)])
        sig = {s.ticker: s for s in insider.run(self.universe, {"asof": date(2026, 6, 12)})}
        self.assertGreater(sig["BBB"].direction, sig["AAA"].direction)
        self.assertGreater(sig["BBB"].confidence, sig["AAA"].confidence)

    def test_no_key_means_no_fetch(self):
        with patch.dict("os.environ", {}, clear=False), patch("os.getenv", return_value=None), patch.object(insider.requests, "get") as get:
            self.assertEqual(insider.refresh(self.universe, date(2026, 6, 12)), 0)
        get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
