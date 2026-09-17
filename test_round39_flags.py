"""Round 39 switches (2026-09-16): GRAPH_TRANSCRIPTS_ONLY (the graph agents skip SEC-filing rows) and DEMEAN_GROUP (demean
within power/chip groups). No network; a temp graph on disk.

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_round39_flags
"""
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import config
import cycle
import learner
from agents import graph_pit, supply_chain


def _label(d, kind="Q"):
    return f"Alpha {kind} ({d.month:02d}-{d.day:02d}-{d.year})"


class Demean(unittest.TestCase):
    def test_whole_mean_and_group_means(self):
        conv = {"A": 0.3, "B": 0.1, "C": -0.1, "D": -0.3}
        out, means = learner.demean(conv)
        self.assertAlmostEqual(means["all"], 0.0)
        self.assertEqual(out, conv)
        groups = {"A": "chip", "B": "chip", "C": "power", "D": "power"}
        out, means = learner.demean(conv, groups, min_group=2)
        self.assertAlmostEqual(means["chip"], 0.2)
        self.assertAlmostEqual(means["power"], -0.2)
        self.assertAlmostEqual(out["A"], 0.1)       # each group's relative winner ends at the same level
        self.assertAlmostEqual(out["C"], 0.1)
        self.assertAlmostEqual(out["D"], -0.1)

    def test_a_small_group_uses_the_whole_mean_and_an_unknown_ticker_is_chip(self):
        conv = {"A": 0.4, "B": 0.0, "C": -0.4}
        out, means = learner.demean(conv, {"A": "chip", "B": "chip", "C": "power"}, min_group=2)
        self.assertAlmostEqual(means["power"], 0.0)      # the whole mean, not C's own value
        self.assertAlmostEqual(out["C"], -0.4)
        out, means = learner.demean(conv, {"A": "chip"}, min_group=1)   # B and C fall into chip
        self.assertEqual(sorted(means), ["chip"])
        self.assertAlmostEqual(out["A"], 0.4)
        self.assertEqual(learner.demean({}, {"A": "chip"}), ({}, {}))


class Groups(unittest.TestCase):
    def test_power_is_only_for_power_cooling_only_names(self):
        self.assertEqual(graph_pit.group_of(["power_cooling"]), "power")
        self.assertEqual(graph_pit.group_of(["power_cooling", "foundry"]), "chip")
        self.assertEqual(graph_pit.group_of([]), "chip")
        self.assertEqual(graph_pit.group_of(None), "chip")


class ConvictWithGroups(unittest.TestCase):
    def test_the_cycle_demeans_within_groups_and_notes_each_mean(self):
        conv = {"A": 0.3, "B": 0.1, "C": -0.1, "D": -0.3}
        groups = {"A": "chip", "B": "chip", "C": "power", "D": "power"}
        notes = []
        with patch.object(config, "DEMEAN_CONVICTION", True), patch.object(config, "DEMEAN_GROUP", "chain"), \
                patch.object(config, "DEMEAN_GROUP_MIN", 2), patch.object(learner, "predict", return_value=(dict(conv), {})):
            out, _, _ = cycle.convict([], None, None, notes, groups)
        self.assertAlmostEqual(out["A"], 0.1)
        self.assertAlmostEqual(out["C"], 0.1)
        self.assertEqual(notes, ["convictions demeaned by chip +0.200, power -0.200"])
        notes = []
        with patch.object(config, "DEMEAN_CONVICTION", True), patch.object(learner, "predict", return_value=(dict(conv), {})):
            out, _, _ = cycle.convict([], None, None, notes)        # no groups: the round 38 note format is unchanged
        self.assertEqual(notes, ["convictions demeaned by +0.000"])
        self.assertEqual(out, conv)


class TranscriptsOnly(unittest.TestCase):
    def setUp(self):
        today = date.today()
        self.today = today
        nodes = [
            {"id": "Alpha Corp", "chains": ["power_cooling"], "quarterly_data": [
                {"quarter": _label(today - timedelta(days=20), "Q2 FY2026"), "signal": "demand exceeds supply", "chain": "power_cooling"},
                {"quarter": _label(today - timedelta(days=10), "10-K"), "signal": "capacity constraints sold out", "chain": "power_cooling"},
                {"quarter": _label(today - timedelta(days=5), "8-K"), "signal": "record backlog", "chain": "power_cooling"}]},
            {"id": "Beta Inc", "chains": ["foundry", "power_cooling"], "quarterly_data": []},
        ]
        graph = {"nodes": nodes, "edges": []}
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "graph").mkdir()
        (root / "graph" / "merged_graph.json").write_text(json.dumps(graph), encoding="utf-8")
        (root / "graph" / "exposure.json").write_text(json.dumps({"companies": {}}), encoding="utf-8")
        self.patch = patch.object(config, "EARNINGS_AI_DIR", root)
        self.patch.start()
        supply_chain._load.cache_clear()
        graph_pit.pit_map.cache_clear()

    def tearDown(self):
        self.patch.stop()
        supply_chain._load.cache_clear()
        graph_pit.pit_map.cache_clear()
        self.tmp.cleanup()

    def test_filing_rows_are_skipped_only_with_the_switch(self):
        full = graph_pit.PointInTimeMap(transcripts_only=False)
        calls = graph_pit.PointInTimeMap(transcripts_only=True)
        self.assertEqual(len(full.signals["Alpha Corp"]), 3)
        self.assertEqual(len(calls.signals["Alpha Corp"]), 1)
        self.assertEqual(len(calls.signals_chain["Alpha Corp"]), 1)
        s_full = full.supply_chain("ALP", "Alpha Corp", self.today)
        s_calls = calls.supply_chain("ALP", "Alpha Corp", self.today)
        self.assertGreater(s_full.direction, s_calls.direction)      # the two filing rows carried the extra tight markers
        with patch.object(config, "GRAPH_TRANSCRIPTS_ONLY", True):
            self.assertTrue(graph_pit.PointInTimeMap().transcripts_only)   # None = follow config
        with patch.object(config, "GRAPH_TRANSCRIPTS_ONLY", False):
            self.assertFalse(graph_pit.PointInTimeMap().transcripts_only)

    def test_groups_come_from_the_maps_chain_tags(self):
        pit = graph_pit.PointInTimeMap()
        groups = graph_pit.groups_from(pit, {"ALP": "Alpha Corp", "BET": "Beta Inc", "ZZZ": "Unknown Co"})
        self.assertEqual(groups, {"ALP": "power", "BET": "chip", "ZZZ": "chip"})
        self.assertEqual(graph_pit.groups({"ALP": "Alpha Corp"}), {"ALP": "power"})


if __name__ == "__main__":
    unittest.main()
