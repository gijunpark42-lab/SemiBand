"""Shadow agents (2026-09-16): recorded and scored, never voting. No network; a temp ledger for the row filter.

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_shadow
"""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import config
import cycle
import learner
import ledger
from agents.base import Signal


class RowFilter(unittest.TestCase):
    def test_only_the_voting_rosters_rows_become_feature_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "ledger.sqlite"
            con = sqlite3.connect(db)
            con.executescript(ledger.SCHEMA)
            for agent in ("a", "b", "zshadow"):
                con.execute("INSERT INTO predictions(date, ticker, agent, direction, confidence, horizon, reason, price_at) VALUES (?,?,?,?,?,?,?,?)",
                            ("2026-09-01", "NVDA", agent, 0.5, 0.5, 10, "", 100.0))
            con.execute("INSERT INTO predictions(date, ticker, agent, direction, confidence, horizon, reason, price_at) VALUES (?,?,?,?,?,?,?,?)",
                        ("2026-09-01", "AMD", "zshadow", 0.5, 0.5, 10, "", 100.0))     # a name only the shadow agent covered
            for pid, in con.execute("SELECT id FROM predictions").fetchall():
                con.execute("INSERT OR REPLACE INTO scores(prediction_id,horizon,scored_date,ret,bench_ret,abnormal,beta_abnormal,hit) VALUES (?,?,?,?,?,?,?,?)",
                            (pid, 10, "2026-09-16", 0.02, 0.01, 0.01, 0.01, 1))
            con.commit()
            con.close()
            all_rows = learner._rows(db, 10, None, target_mode="beta")
            voting = learner._rows(db, 10, None, target_mode="beta", agents=("a", "b"))
        self.assertEqual(len(all_rows), 4)
        self.assertEqual(sorted((r["ticker"], r["agent"]) for r in voting), [("NVDA", "a"), ("NVDA", "b")])   # AMD never becomes an all-zero row


class Breakdown(unittest.TestCase):
    def test_a_shadow_signal_changes_neither_the_conviction_nor_the_breakdown(self):
        with patch.object(config, "AGENTS", ["a", "b"]), patch.object(config, "HORIZONS", (10,)):
            base = [Signal("a", "X", 1.0, 1.0, 10, ""), Signal("b", "X", 0.5, 1.0, 10, "")]
            conv0, br0 = learner.predict(base)
            conv1, br1 = learner.predict(base + [Signal("zshadow", "X", -1.0, 1.0, 10, "shadow says no")])
        self.assertEqual(conv0, conv1)
        self.assertEqual(br0, br1)
        self.assertEqual(sorted(br1["X"]), ["a", "b"])


class Roster(unittest.TestCase):
    def test_shadow_agents_run_and_are_recorded_but_the_learner_roster_is_unchanged(self):
        ran = []

        def fake_run_agent(name, universe, ctx):
            ran.append(name)
            return [Signal(name, "X", 0.1, 0.5, 10, "")]

        with patch.object(config, "AGENTS", ["a", "b"]), patch.object(config, "SHADOW_AGENTS", ("zshadow",)), \
                patch.object(cycle, "_run_agent", fake_run_agent):
            out = cycle.run_agents({"X": "X Corp"}, {"today": "2026-09-16"}, None, {}, use_llm=False)
            self.assertEqual(learner.agents(), ["a", "b"])
        self.assertEqual(ran, ["a", "b", "zshadow"])
        self.assertEqual(sorted(s.agent for s in out), ["a", "b", "zshadow"])     # recorded rows include the shadow


if __name__ == "__main__":
    unittest.main()
