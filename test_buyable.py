"""Round 58: only seasoned, non-penny names are bought (off by default).

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_buyable
"""
import unittest

import config
import portfolio


class Buyable(unittest.TestCase):
    def test_rules(self):
        conv = {"OLD": 0.4, "NEW": 0.5, "PENNY": 0.3, "NODATA": 0.2}
        hist = {"OLD": 300, "NEW": 40, "PENNY": 400}
        price = {"OLD": 120.0, "NEW": 30.0, "PENNY": 2.5}
        self.assertEqual(set(portfolio.buyable(conv, hist, price, 252, 5.0)), {"OLD"})
        self.assertEqual(set(portfolio.buyable(conv, hist, price, 252, None)), {"OLD", "PENNY"})
        self.assertEqual(set(portfolio.buyable(conv, hist, price, None, 5.0)), {"OLD", "NEW"})
        self.assertIs(portfolio.buyable(conv, hist, price), conv)            # no rule: unchanged

    def test_off_by_default(self):
        self.assertIsNone(config.MIN_HISTORY_DAYS)
        self.assertIsNone(config.MIN_PRICE)


if __name__ == "__main__":
    unittest.main()
