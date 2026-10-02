"""2026-10-01: a cycle whose PC slept through the close window must not send orders on waking (09-30: orders went out at
00:14 ET), and the clean-up re-sends exactly the unfilled shares.

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_sleep_guard
"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

import broker
import cycle
from alpaca.trading.enums import OrderSide


class SleptThroughTheWindow(unittest.TestCase):
    def test_waking_after_the_cutoff_returns_false(self):
        clock = [pd.Timestamp("2026-09-30 14:29:31", tz="America/New_York")]

        def sleep(seconds):                                  # the PC suspends inside the first sleep and wakes at 00:14
            clock[0] = pd.Timestamp("2026-10-01 00:14:18", tz="America/New_York")

        with patch.object(cycle.pd.Timestamp, "now", staticmethod(lambda tz=None: clock[0])), patch.object(cycle.time, "sleep", sleep):
            self.assertFalse(cycle.wait_until_et("15:45", "15:55", "2026-09-30"))

    def test_a_normal_wait_reaches_the_refresh(self):
        clock = [pd.Timestamp("2026-09-30 15:43:30", tz="America/New_York")]
        slept = []

        def sleep(seconds):
            slept.append(seconds)
            clock[0] += pd.Timedelta(seconds=seconds)

        with patch.object(cycle.pd.Timestamp, "now", staticmethod(lambda tz=None: clock[0])), patch.object(cycle.time, "sleep", sleep):
            self.assertTrue(cycle.wait_until_et("15:45", "15:55", "2026-09-30"))
        self.assertEqual(slept, [60.0, 30.0])                 # steps of at most a minute

    def test_the_last_check_before_the_orders(self):
        end = pd.Timestamp("2026-09-30 15:55", tz="America/New_York")
        with patch.object(cycle.pd.Timestamp, "now", staticmethod(lambda tz=None: pd.Timestamp("2026-09-30 15:46", tz="America/New_York"))):
            self.assertTrue(cycle.window_still_open(end))
        with patch.object(cycle.pd.Timestamp, "now", staticmethod(lambda tz=None: pd.Timestamp("2026-10-01 00:14", tz="America/New_York"))):
            self.assertFalse(cycle.window_still_open(end))
        with patch.object(cycle.broker, "clock", return_value=SimpleNamespace(is_open=False)):
            self.assertFalse(cycle.window_still_open(None))  # open mode: the market itself must be open


class CleanupQuantity(unittest.TestCase):
    def test_the_remainder_is_exact(self):
        sent = []
        order = SimpleNamespace(id="o1", client_order_id="sb2-2026-09-30-VST-sell-1", symbol="VST", side=OrderSide.SELL,
                                qty="567.101695397", filled_qty="0")
        client = SimpleNamespace(get_orders=lambda req: [order], cancel_order_by_id=lambda oid: None,
                                 submit_order=lambda req: sent.append(req))
        with patch.object(broker, "_dry", return_value=False), patch.object(broker, "_client", client):
            self.assertEqual(broker.cleanup_open_orders("sb2-"), 1)
        self.assertEqual(sent[0].qty, 567.101695397)          # not 567.1017, which the account does not hold


if __name__ == "__main__":
    unittest.main()
