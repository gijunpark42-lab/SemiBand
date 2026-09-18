"""Chain-momentum agent (round 50): the chain's equal-weight trailing return relative to the universe, from the frame's last rows only.

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_chain_momentum
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

import config
from agents import chain_momentum, graph_pit, supply_chain


class ChainMomentum(unittest.TestCase):
    def setUp(self):
        graph = {"nodes": [{"id": "Chip A", "chains": ["hbm"], "quarterly_data": []},
                           {"id": "Chip B", "chains": ["hbm"], "quarterly_data": []},
                           {"id": "Power A", "chains": ["power_cooling"], "quarterly_data": []},
                           {"id": "Power B", "chains": ["power_cooling"], "quarterly_data": []},
                           {"id": "Lonely", "chains": ["foundry"], "quarterly_data": []},
                           {"id": "Untagged", "chains": [], "quarterly_data": []}],
                 "edges": []}
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "graph").mkdir()
        (root / "graph" / "merged_graph.json").write_text(json.dumps(graph), encoding="utf-8")
        (root / "graph" / "exposure.json").write_text(json.dumps({"companies": {}}), encoding="utf-8")
        self.patch = patch.object(config, "EARNINGS_AI_DIR", root)
        self.patch.start()
        supply_chain._load.cache_clear()
        graph_pit.pit_map.cache_clear()
        self.universe = {"CA": "Chip A", "CB": "Chip B", "PA": "Power A", "PB": "Power B", "LO": "Lonely", "UN": "Untagged"}
        idx = pd.bdate_range("2025-06-02", periods=200)
        flat = np.full(200, 100.0)

        def path(total):
            p = flat.copy()
            p[-127:] = 100.0 * (1 + np.linspace(0, total, 127))
            return p

        self.closes = pd.DataFrame({config.BENCHMARK: flat, "CA": path(0.30), "CB": path(0.10), "PA": path(-0.10), "PB": path(-0.10),
                                    "LO": path(0.50), "UN": path(0.0)}, index=idx)

    def tearDown(self):
        self.patch.stop()
        supply_chain._load.cache_clear()
        graph_pit.pit_map.cache_clear()
        self.tmp.cleanup()

    def test_chain_return_relative_to_the_universe(self):
        with patch.object(chain_momentum, "MIN_NAMES", 2):
            sig = {s.ticker: s for s in chain_momentum.run(self.universe, {"closes": self.closes})}
        self.assertEqual(sorted(sig), ["CA", "CB", "PA", "PB"])          # foundry has one member, Untagged has no tag
        # universe mean of the six = (0.30 + 0.10 - 0.10 - 0.10 + 0.50 + 0.0) / 6 = 0.1167; hbm chain = 0.20, power = -0.10
        self.assertAlmostEqual(sig["CA"].direction, np.tanh(4.0 * (0.20 - 0.7 / 6)), places=6)
        self.assertEqual(sig["CA"].direction, sig["CB"].direction)         # the same chain gives the same vote
        self.assertLess(sig["PA"].direction, 0)
        self.assertIn("1 chains, 126d chain return", sig["CA"].reason)
        self.assertEqual((sig["CA"].confidence, sig["CA"].horizon), (0.5, 20))

    def test_only_the_frames_last_rows_matter_and_short_frames_are_silent(self):
        shocked = self.closes.copy()
        shocked.iloc[:-128, :] *= 3.0
        with patch.object(chain_momentum, "MIN_NAMES", 2):
            a = {s.ticker: round(s.direction, 12) for s in chain_momentum.run(self.universe, {"closes": self.closes})}
            b = {s.ticker: round(s.direction, 12) for s in chain_momentum.run(self.universe, {"closes": shocked})}
            self.assertEqual(a, b)
            self.assertEqual(chain_momentum.run(self.universe, {"closes": self.closes.iloc[:100]}), [])


if __name__ == "__main__":
    unittest.main()
