"""The live graph agents compute exactly the replay's point-in-time formula (2026-09-16 train/serve fix). A tiny graph in a
temp directory; no network.

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_graph_pit
"""
import json
import math
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import config
from agents import graph_pit, neighbors, supply_chain


def _label(d):
    return f"Q ({d.month:02d}-{d.day:02d}-{d.year})"


class LiveAgentsUseThePointInTimeFormula(unittest.TestCase):
    def setUp(self):
        today = date.today()
        self.today = today
        nodes = [
            {"id": "Alpha Corp", "chains": ["hbm"], "quarterly_data": [
                {"quarter": _label(today - timedelta(days=30)), "signal": "capacity sold out, raised guidance", "chain": "hbm"},
                {"quarter": _label(today - timedelta(days=200)), "signal": "steady", "chain": "hbm"}]},
            {"id": "Beta Inc", "chains": ["hbm"], "quarterly_data": [
                {"quarter": _label(today - timedelta(days=10)), "signal": "demand exceeds supply", "chain": "hbm"}]},
            {"id": "Gamma Ltd", "chains": [], "quarterly_data": []},                    # no dated statement: silent
        ]
        graph = {"nodes": nodes, "edges": [{"source": "Alpha Corp", "target": "Beta Inc"}]}   # Alpha sells to Beta
        exposure = {"companies": {"Alpha Corp": {"generations": {"g1": "gained"}, "topics": {"supply_tightness": 9},
                                                 "days_since": 3, "signals": 40},
                                  "Beta Inc": {"topics": {"supply_tightness": 9}, "days_since": 2, "signals": 40},
                                  "Gamma Ltd": {"generations": {"g1": "gained"}, "days_since": 1, "signals": 40}}}
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "graph").mkdir()
        (root / "graph" / "merged_graph.json").write_text(json.dumps(graph), encoding="utf-8")
        (root / "graph" / "exposure.json").write_text(json.dumps(exposure), encoding="utf-8")
        self.patch = patch.object(config, "EARNINGS_AI_DIR", root)
        self.patch.start()
        supply_chain._load.cache_clear()
        graph_pit.pit_map.cache_clear()
        self.universe = {"ALP": "Alpha Corp", "BET": "Beta Inc", "GAM": "Gamma Ltd"}

    def tearDown(self):
        self.patch.stop()
        supply_chain._load.cache_clear()
        graph_pit.pit_map.cache_clear()
        self.tmp.cleanup()

    def test_supply_chain_matches_the_replay_formula_and_ignores_exposure_counts(self):
        live = {s.ticker: s for s in supply_chain.run(self.universe, {"today": self.today.isoformat()})}
        pit = graph_pit.PointInTimeMap()
        self.assertEqual(sorted(live), ["ALP", "BET"])                                # Gamma has no dated statement
        for tk, company in (("ALP", "Alpha Corp"), ("BET", "Beta Inc")):
            ref = pit.supply_chain(tk, company, self.today)
            self.assertEqual((live[tk].direction, live[tk].confidence, live[tk].reason),
                             (ref.direction, ref.confidence, ref.reason))
        self.assertIn("1 tight markers", live["ALP"].reason)                          # one dated statement with positive markers in 120d
        self.assertAlmostEqual(live["ALP"].direction, math.tanh(0.15 + 0.2), places=6)  # no 'gained' +0.8 or tightness x9 from exposure

    def test_neighbors_matches_the_replay_formula(self):
        live = {s.ticker: s for s in neighbors.run(self.universe, {"today": self.today.isoformat()})}
        pit = graph_pit.PointInTimeMap()
        self.assertEqual(sorted(live), ["ALP", "BET"])                                # Gamma has no edges
        for tk, company in (("ALP", "Alpha Corp"), ("BET", "Beta Inc")):
            ref = pit.neighbors(tk, company, self.today)
            self.assertEqual((live[tk].direction, live[tk].confidence, live[tk].reason),
                             (ref.direction, ref.confidence, ref.reason))
        self.assertIn("customer heat 0.70", live["ALP"].reason)                       # Beta: a positive marker within 90d (+0.5) and a statement (+0.2)

    def test_an_asof_in_the_context_is_honoured(self):
        early = self.today - timedelta(days=400)                                      # before every dated statement
        self.assertEqual(supply_chain.run(self.universe, {"asof": early}), [])
        self.assertEqual(neighbors.run(self.universe, {"asof": early}), [])


if __name__ == "__main__":
    unittest.main()
