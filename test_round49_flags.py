"""Round 49 (2026-09-18): the replay flags --rebalance-every and --cost-bps exist and default to the live behaviour.

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_round49_flags
"""
import inspect
import unittest

import config


class ReplayFlags(unittest.TestCase):
    def test_run_takes_the_round_49_parameters(self):
        import backtest
        params = inspect.signature(backtest.run).parameters
        self.assertIn("rebalance_every", params)
        self.assertIn("cost_bps", params)
        self.assertIsNone(params["rebalance_every"].default)
        self.assertIsNone(params["cost_bps"].default)

    def test_the_live_cost_constant_is_untouched(self):
        self.assertEqual(config.COST_BPS, 5)


if __name__ == "__main__":
    unittest.main()
