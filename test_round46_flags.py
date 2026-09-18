"""Round 46 (2026-09-18): the customer earnings-surprise shadow agent, customer momentum on open->close legs, the replay flags.

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_round46_flags
"""
import inspect
import unittest
from datetime import date
from unittest.mock import patch

import numpy as np
import pandas as pd

import config
from agents import customer_momentum, customer_sue
from test_link_momentum import LinkMomentum


class CustomerSue(LinkMomentum):
    def setUp(self):
        super().setUp()
        self.earnings = {"CLD": [{"date": "2026-03-30", "surprise_pct": -50.0}, {"date": "2026-03-20", "surprise_pct": 12.0}],
                         "TOOL": [{"date": "2026-03-10", "surprise_pct": 5.0}]}

    def test_only_customers_prints_strictly_before_the_day_count(self):
        sig = {s.ticker: s for s in customer_sue.run(self.universe, {"closes": self.closes, "asof": date(2026, 3, 25), "earnings": self.earnings})}
        self.assertEqual(sorted(sig), ["CHIP"])                                   # Chip's customer Cloud reported 03-20; Tool's customer Chip never did
        self.assertAlmostEqual(sig["CHIP"].direction, np.tanh(12 / 10), places=6)  # the 03-30 print is in the future and ignored
        self.assertIn("1 customers reported within 42d, mean EPS surprise +12%", sig["CHIP"].reason)
        self.assertEqual((sig["CHIP"].confidence, sig["CHIP"].horizon, sig["CHIP"].agent), (0.4, 20, "customer_sue"))

    def test_a_print_on_the_day_or_outside_the_window_is_silent(self):
        on_the_day = customer_sue.run(self.universe, {"closes": self.closes, "asof": date(2026, 3, 20), "earnings": self.earnings})
        self.assertEqual(on_the_day, [])
        stale = customer_sue.run(self.universe, {"closes": self.closes, "asof": date(2026, 6, 1), "earnings": self.earnings})
        self.assertEqual(stale, [])
        after = {s.ticker: s.direction for s in customer_sue.run(self.universe, {"closes": self.closes, "asof": date(2026, 4, 2), "earnings": self.earnings})}
        self.assertLess(after["CHIP"], -0.99)                                     # the newest print (-50%) replaces the older one


class IntradayMomentum(LinkMomentum):
    def _run(self, opens, flag=True):
        with patch.object(config, "MOMENTUM_INTRADAY", flag):
            return {s.ticker: s for s in customer_momentum.run(self.universe, {"closes": self.closes, "opens": opens})}

    def test_open_to_close_legs_only(self):
        plain = self._run(None, flag=False)
        overnight = self._run(self.closes.copy())                                 # open == close: the whole move is overnight
        self.assertAlmostEqual(overnight["CHIP"].direction, 0.0, places=9)
        self.assertIn("(intraday)", overnight["CHIP"].reason)
        intraday = self._run(self.closes.shift(1))                                # open == yesterday's close: the whole move is intraday
        self.assertAlmostEqual(intraday["CHIP"].direction, plain["CHIP"].direction, places=9)
        self.assertNotIn("(intraday)", plain["CHIP"].reason)

    def test_rows_after_the_closes_frame_never_enter(self):
        opens = self.closes.shift(1)
        extra = opens.copy()
        extra.loc[opens.index[-1] + pd.offsets.BDay(1)] = 1e6                       # tomorrow's open (the fill price) in the frame
        self.assertEqual({t: round(s.direction, 12) for t, s in self._run(opens).items()},
                         {t: round(s.direction, 12) for t, s in self._run(extra).items()})

    def test_too_few_pairs_fall_back_to_close_to_close(self):
        plain = self._run(None, flag=False)
        opens = self.closes.copy()
        opens.loc[opens.index[-10:], "CLD"] = np.nan                               # 11 of the last 21 sessions valid for Cloud: below MIN_PAIRS
        fallback = self._run(opens)
        self.assertAlmostEqual(fallback["CHIP"].direction, plain["CHIP"].direction, places=9)
        self.assertIsNone(customer_momentum.rel_returns_intraday(self.closes, opens).get("XXX"))
        self.assertEqual(customer_momentum.rel_returns_intraday(self.closes, None, fallback={"CHIP": 0.1}), {"CHIP": 0.1})


class ReplayFlags(unittest.TestCase):
    def test_run_takes_the_round_46_parameters_and_guards_the_exec_mode(self):
        import backtest
        params = inspect.signature(backtest.run).parameters
        self.assertIn("momentum_intraday", params)
        self.assertIn("prior_strength", params)
        with self.assertRaises(ValueError):
            backtest.run(momentum_intraday=True, exec_mode="close")


if __name__ == "__main__":
    unittest.main()
