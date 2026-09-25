"""2026-09-24: close mode follows Alpaca's calendar (no orders on holidays, the close window before a half day's 13:00
close) and a cycle that starts too late for the close window catches up in the extended session with whole-share limits.

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_close_calendar
"""
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

import broker
import config
import cycle
from alpaca.trading.enums import OrderSide, TimeInForce


def at(hhmm, day="2026-09-24"):
    return staticmethod(lambda tz=None: pd.Timestamp(f"{day} {hhmm}", tz="America/New_York"))


class CloseWindow(unittest.TestCase):
    def test_the_window_sits_before_the_sessions_close(self):
        with patch.object(config, "CLOSE_ORDER_TYPE", "market"):
            self.assertEqual(cycle.close_times(datetime(2026, 9, 24, 16, 0)), ("15:45", "15:55", "15:30"))
            self.assertEqual(cycle.close_times(datetime(2026, 11, 27, 13, 0)), ("12:45", "12:55", "12:30"))   # half day
        with patch.object(config, "CLOSE_ORDER_TYPE", "moc"):
            self.assertEqual(cycle.close_times(datetime(2026, 9, 24, 16, 0))[1], "15:48")

    def test_the_catch_up_runs_until_half_an_hour_before_the_extended_session_ends(self):
        normal, half = datetime(2026, 9, 24, 16, 0), datetime(2026, 11, 27, 13, 0)
        with patch.object(config, "AFTER_HOURS_CATCHUP", True):
            with patch.object(cycle.pd.Timestamp, "now", at("17:00")):
                self.assertTrue(cycle.extended_session_open(normal))
            with patch.object(cycle.pd.Timestamp, "now", at("19:45")):
                self.assertFalse(cycle.extended_session_open(normal))
            with patch.object(cycle.pd.Timestamp, "now", at("16:00", "2026-11-27")):
                self.assertTrue(cycle.extended_session_open(half))
            with patch.object(cycle.pd.Timestamp, "now", at("16:45", "2026-11-27")):
                self.assertFalse(cycle.extended_session_open(half))
        with patch.object(config, "AFTER_HOURS_CATCHUP", False), patch.object(cycle.pd.Timestamp, "now", at("17:00")):
            self.assertFalse(cycle.extended_session_open(normal))


class Calendar(unittest.TestCase):
    def test_a_holiday_has_no_close(self):
        close = datetime(2026, 11, 27, 13, 0)
        cal = {"2026-11-26": [], "2026-11-27": [SimpleNamespace(close=close)]}
        client = SimpleNamespace(get_calendar=lambda req: cal[req.start.isoformat()])
        with patch.object(broker, "_client", client):
            self.assertIsNone(broker.session_close("2026-11-26"))
            self.assertEqual(broker.session_close("2026-11-27"), close)


class ExtendedLimit(unittest.TestCase):
    def _send(self, *args, last=100.0, **kwargs):
        sent = []
        client = SimpleNamespace(submit_order=lambda req: (sent.append(req) or SimpleNamespace(id="o1")))
        with patch.object(broker, "_dry", return_value=False), patch.object(broker, "latest_trade", return_value=last), \
                patch.object(broker, "_client", client):
            return broker.extended_limit(*args, **kwargs), sent

    def test_whole_shares_marketable_against_the_latest_trade(self):
        order, sent = self._send("NVDA", OrderSide.BUY, notional=1005.0, client_order_id="sb2-x-ah")
        req = sent[0]
        self.assertEqual((req.qty, req.limit_price, req.time_in_force, req.extended_hours), (9, 102.0, TimeInForce.DAY, True))
        order, sent = self._send("NVDA", OrderSide.SELL, qty=10.7)
        self.assertEqual((sent[0].qty, sent[0].limit_price, sent[0].side), (10, 98.0, OrderSide.SELL))   # the fraction stays

    def test_nothing_is_sent_without_a_price_or_a_whole_share(self):
        self.assertEqual(self._send("NVDA", OrderSide.BUY, notional=50.0), (None, []))
        self.assertEqual(self._send("NVDA", OrderSide.BUY, notional=5000.0, last=None), (None, []))
        with patch.object(broker, "_dry", return_value=True), patch.object(broker, "_client", SimpleNamespace()):
            self.assertIsNone(broker.extended_limit("NVDA", OrderSide.BUY, notional=5000.0))


if __name__ == "__main__":
    unittest.main()
