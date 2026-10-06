"""2026-10-06 decision manifest: one append-only record per cycle of what the decision used, and a check that past forecasts
were not altered after they were made.

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_manifest
"""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import config
import ledger
import manifest
from agents.base import Signal


class Manifest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(self._tmp.name)
        self._p = [patch.object(config, "STATE_DIR", root), patch.object(ledger, "DB", root / "ledger.sqlite"),
                   patch.object(config, "API_KEY", "PKTESTSECRETKEY123"), patch.object(config, "SECRET_KEY", "SECRETVALUE987"),
                   patch.object(manifest, "code_version", return_value={"commit": "abc", "dirty": False})]
        for p in self._p:
            p.start()
        ledger.add_predictions("2026-10-01", [Signal("technical", "AAA", 0.5, 0.6, 10, "x")], {"AAA": 1.0}, {"AAA": 1.0})

    def tearDown(self):
        for p in self._p:
            p.stop()
        self._tmp.cleanup()

    def test_records_the_decision_inputs_without_secrets(self):
        man, changed = manifest.write("2026-10-02", {"AAA": "a", "BBB": "b"}, orders=[{"ticker": "AAA", "side": "BUY", "notional": 1.0}],
                                      llm_models={"claude-opus-5-20260601/max"})
        self.assertEqual(changed, [])
        files = list((config.STATE_DIR / "manifests").glob("2026-10-02_*.json"))
        self.assertEqual(len(files), 1)
        text = files[0].read_text(encoding="utf-8")
        self.assertNotIn(str(config.API_KEY), text)
        self.assertNotIn(str(config.SECRET_KEY), text)
        on_disk = json.loads(text)
        self.assertEqual(on_disk["universe"]["n"], 2)
        self.assertEqual(on_disk["llm"]["served"], ["claude-opus-5-20260601/max"])
        self.assertIn("2026-10-01", on_disk["predictions"])
        self.assertEqual(on_disk["config"]["knobs"]["TOP_N"], config.TOP_N)

    def test_a_past_forecast_changed_afterwards_is_flagged(self):
        manifest.write("2026-10-02", {"AAA": "a"})
        with sqlite3.connect(ledger.DB) as con:                          # someone rewrites a frozen forecast
            con.execute("UPDATE predictions SET direction = -0.5 WHERE date = '2026-10-01'")
        man, changed = manifest.write("2026-10-03", {"AAA": "a"})
        self.assertEqual(changed, ["2026-10-01"])
        self.assertEqual(man["past_predictions_changed"], ["2026-10-01"])

    def test_todays_rows_may_still_change(self):
        ledger.add_predictions("2026-10-02", [Signal("technical", "AAA", 0.1, 0.6, 10, "pre-refresh")], {"AAA": 1.0}, {"AAA": 1.0})
        manifest.write("2026-10-02", {"AAA": "a"})
        ledger.add_predictions("2026-10-02", [Signal("macro", "AAA", 0.2, 0.5, 10, "same day")], {"AAA": 1.0}, {"AAA": 1.0})
        _, changed = manifest.write("2026-10-02", {"AAA": "a"})          # a same-day re-run is not an alteration
        self.assertEqual(changed, [])


if __name__ == "__main__":
    unittest.main()
