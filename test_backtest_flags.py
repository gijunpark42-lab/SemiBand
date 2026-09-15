"""Round 31 replay flags are refused when they cannot mean anything. No data, no network (the checks run before loading).

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_backtest_flags
"""
import unittest

import backtest


class RefreshFlags(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
