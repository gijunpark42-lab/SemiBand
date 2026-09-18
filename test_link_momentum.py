"""Customer / supplier momentum agents (round 44): edges from a temp graph, returns from the context's closes only.

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_link_momentum
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

import config
from agents import customer_momentum, graph_pit, supplier_momentum, supply_chain


class LinkMomentum(unittest.TestCase):
    def setUp(self):
        graph = {"nodes": [{"id": "Chip Co", "chains": ["hbm"], "quarterly_data": []},
                           {"id": "Cloud Inc", "chains": ["neocloud"], "quarterly_data": []},
                           {"id": "Tool Ltd", "chains": ["foundry"], "quarterly_data": []},
                           {"id": "Private Buyer", "chains": [], "quarterly_data": []}],
                 "edges": [{"source": "Chip Co", "target": "Cloud Inc"},        # Chip sells to Cloud
                           {"source": "Tool Ltd", "target": "Chip Co"},         # Tool sells to Chip
                           {"source": "Chip Co", "target": "Private Buyer"}]}   # a customer outside the universe
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "graph").mkdir()
        (root / "graph" / "merged_graph.json").write_text(json.dumps(graph), encoding="utf-8")
        (root / "graph" / "exposure.json").write_text(json.dumps({"companies": {}}), encoding="utf-8")
        self.patch = patch.object(config, "EARNINGS_AI_DIR", root)
        self.patch.start()
        supply_chain._load.cache_clear()
        graph_pit.pit_map.cache_clear()
        self.universe = {"CHIP": "Chip Co", "CLD": "Cloud Inc", "TOOL": "Tool Ltd"}
        idx = pd.bdate_range("2026-01-02", periods=60)
        flat = np.full(60, 100.0)
        cloud = flat.copy()
        cloud[-21:] = 100.0 * (1 + np.linspace(0, 0.20, 21))     # Cloud +20% over the last 21 sessions
        tool = flat.copy()
        tool[-21:] = 100.0 * (1 - np.linspace(0, 0.10, 21))      # Tool -10%
        self.closes = pd.DataFrame({config.BENCHMARK: flat, "CHIP": flat, "CLD": cloud, "TOOL": tool}, index=idx)

    def tearDown(self):
        self.patch.stop()
        supply_chain._load.cache_clear()
        graph_pit.pit_map.cache_clear()
        self.tmp.cleanup()

    def test_customer_momentum_flows_from_customer_to_supplier_only(self):
        sig = {s.ticker: s for s in customer_momentum.run(self.universe, {"closes": self.closes})}
        self.assertEqual(sorted(sig), ["CHIP", "TOOL"])                  # CLD has no universe customer, the private buyer is ignored
        self.assertGreater(sig["CHIP"].direction, 0.5)                    # its customer Cloud rose 20% vs a flat benchmark
        self.assertLess(sig["TOOL"].direction, 0.05)                      # Tool's customer Chip was flat
        self.assertIn("1 customers, 21d return +20.0%", sig["CHIP"].reason)
        self.assertEqual(sig["CHIP"].horizon, 20)

    def test_supplier_momentum_is_the_mirror(self):
        sig = {s.ticker: s for s in supplier_momentum.run(self.universe, {"closes": self.closes})}
        self.assertEqual(sorted(sig), ["CHIP", "CLD"])                    # CHIP's supplier is Tool (-10%), CLD's supplier is Chip (flat)
        self.assertLess(sig["CHIP"].direction, -0.4)
        self.assertEqual(sig["CHIP"].agent, "supplier_momentum")

    def test_only_the_frames_last_rows_matter(self):
        shocked = self.closes.copy()
        shocked.iloc[:-22, :] *= 5.0                                         # anything older than the window is irrelevant
        a = {s.ticker: round(s.direction, 12) for s in customer_momentum.run(self.universe, {"closes": self.closes})}
        b = {s.ticker: round(s.direction, 12) for s in customer_momentum.run(self.universe, {"closes": shocked})}
        self.assertEqual(a, b)
        self.assertEqual(customer_momentum.run(self.universe, {"closes": self.closes.iloc[:10]}), [])   # too short


if __name__ == "__main__":
    unittest.main()
