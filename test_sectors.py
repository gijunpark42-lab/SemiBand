"""Round 55 (user: "섹터별로 나눈 담에 투자시킬까? 광학/메모리/네오클라우드…"): the graph sectors and the names-per-sector cap.
Both are off by default (config.SECTOR_MAX_NAMES None, DEMEAN_GROUP None).

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_sectors
"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import config
import portfolio
from agents import graph_pit


class SectorMap(unittest.TestCase):
    def test_layers_power_and_biopharma(self):
        pit = SimpleNamespace(
            chains={"NVIDIA": {"nvda_b200"}, "Vistra": {"power_cooling"}, "Micron": {"hbm"}, "Recursion": {"ai_drug"}, "ON": {"x"}},
            layers={"NVIDIA": ["compute_hardware", "interconnect"], "Vistra": ["cloud_infra"], "Micron": ["memory"],
                    "Recursion": ["application"], "ON": []},
            sector_tags={"Recursion": ["AI-Native Drug Discovery"], "NVIDIA": ["Training GPU"]})
        got = graph_pit.sectors_from(pit, {"NVDA": "NVIDIA", "VST": "Vistra", "MU": "Micron", "RXRX": "Recursion", "ON": "ON"})
        self.assertEqual(got, {"NVDA": "compute", "VST": "power", "MU": "memory", "RXRX": "biopharma", "ON": "power_semis"})


class SectorCap(unittest.TestCase):
    def test_at_most_n_per_sector_then_the_next_best(self):
        conv = {"U1": 0.50, "U2": 0.45, "U3": 0.40, "U4": 0.35, "M1": 0.20, "N1": 0.15, "low": 0.05}
        groups = {"U1": "power", "U2": "power", "U3": "power", "U4": "power", "M1": "memory", "N1": "networking_optical"}
        with patch.object(config, "SECTOR_MAX_NAMES", 2), patch.object(config, "TOP_N", 4), patch.object(config, "MIN_CONVICTION", 0.10), \
                patch.object(config, "VOL_TARGET", None), patch.object(config, "MIN_STOCK_BOOK", None):
            capped = portfolio.targets(conv, 1e6, groups=groups)
            uncapped = portfolio.targets(conv, 1e6)                      # no groups: the cap does not apply
        self.assertEqual(set(capped), {"U1", "U2", "M1", "N1"})
        self.assertEqual(set(uncapped), {"U1", "U2", "U3", "U4"})

    def test_off_by_default(self):
        self.assertIsNone(config.SECTOR_MAX_NAMES)
        self.assertIn(config.DEMEAN_GROUP, (None, "chain", "sector"))


if __name__ == "__main__":
    unittest.main()
