"""Round 52 (adopted 2026-09-23): the live conviction EMA, the replay's --conviction-ema: conv = a x today + (1 - a) x the
previous cycle's smoothed value, before demeaning.

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_conviction_ema
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import config
import cycle
import learner


class ConvictionEma(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self._patches = [patch.object(config, "STATE_DIR", Path(self._tmp.name)), patch.object(config, "CONVICTION_EMA", 0.5)]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()

    def test_the_first_day_is_unsmoothed_and_the_next_blends_half_and_half(self):
        self.assertEqual(cycle.smooth_convictions({"A": 0.4, "B": -0.2}, "2026-09-24"), {"A": 0.4, "B": -0.2})
        out = cycle.smooth_convictions({"A": 0.0, "B": 0.2, "C": 0.3}, "2026-09-25")
        self.assertAlmostEqual(out["A"], 0.2)
        self.assertAlmostEqual(out["B"], 0.0)
        self.assertAlmostEqual(out["C"], 0.3)                                # no previous value: its own

    def test_a_same_day_rerun_smooths_against_the_previous_day(self):
        cycle.smooth_convictions({"A": 0.4}, "2026-09-24")
        first = cycle.smooth_convictions({"A": 0.0}, "2026-09-25")
        again = cycle.smooth_convictions({"A": 0.2}, "2026-09-25")          # the close refresh, same day
        self.assertAlmostEqual(first["A"], 0.2)
        self.assertAlmostEqual(again["A"], 0.3)                              # against 09-24, not against the first pass
        stored = json.loads((config.STATE_DIR / "conviction_ema.json").read_text(encoding="utf-8"))
        self.assertAlmostEqual(stored["2026-09-25"]["A"], 0.3)
        self.assertAlmostEqual(cycle.smooth_convictions({"A": 0.1}, "2026-09-26")["A"], 0.2)

    def test_a_stale_previous_day_is_not_used_and_off_means_off(self):
        cycle.smooth_convictions({"A": 0.4}, "2026-09-10")
        self.assertEqual(cycle.smooth_convictions({"A": 0.0}, "2026-09-24"), {"A": 0.0})     # 14 days back
        with patch.object(config, "CONVICTION_EMA", None):
            self.assertEqual(cycle.smooth_convictions({"A": 0.2}, "2026-09-25"), {"A": 0.2})

    def test_convict_smooths_before_demeaning_as_the_replay(self):
        raw = [{"A": 0.4}, {"A": 0.0, "B": 0.4}]
        with patch.object(config, "DEMEAN_CONVICTION", True), \
                patch.object(learner, "predict", side_effect=lambda signals, model: (raw.pop(0), {})):
            cycle.convict([], "model", None, today="2026-09-24")
            day2, _, _ = cycle.convict([], "model", None, today="2026-09-25")
        # smoothed {A 0.2, B 0.4} then demeaned -> {A -0.1, B +0.1}; demeaning first would give {A -0.1, B +0.2}
        self.assertAlmostEqual(day2["A"], -0.1)
        self.assertAlmostEqual(day2["B"], 0.1)

    def test_without_a_date_convict_is_unchanged(self):
        with patch.object(learner, "predict", return_value=({"A": 0.3}, {})), patch.object(config, "DEMEAN_CONVICTION", False):
            out, _, _ = cycle.convict([], "model", None)
        self.assertEqual(out, {"A": 0.3})
        self.assertFalse((config.STATE_DIR / "conviction_ema.json").exists())


if __name__ == "__main__":
    unittest.main()
