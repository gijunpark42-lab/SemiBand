"""Infrastructure follow-ups from the 2026-09-16 max-effort cycle: the Claude call timeout comes from config, and a second
graph snapshot on the same day never overwrites the first. No network.

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_infra
"""
import io
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import config
import snapshots
from agents import llm


class ClaudeCallTimeout(unittest.TestCase):
    def test_the_call_waits_config_llm_timeout_unless_told_otherwise(self):
        seen = []

        class Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout=None):
            seen.append(timeout)
            return Resp(json.dumps({"choices": [{"message": {"content": json.dumps({"direction": 0.1})}}]}).encode())

        with patch.object(config, "LLM_TIMEOUT", 480), patch.object(llm.urllib.request, "urlopen", fake_urlopen):
            self.assertEqual(llm.ask_json("s", "u"), {"direction": 0.1})
            llm.ask_json("s", "u", timeout=30)
        self.assertEqual(seen, [480, 30])


class ClaudeStageDeadline(unittest.TestCase):
    def test_calls_after_the_deadline_are_refused_at_once_and_counted(self):
        from datetime import datetime, timedelta, timezone

        def never(req, timeout=None):
            raise AssertionError("a call was made after the deadline")

        llm.timing_summary()
        with patch.object(llm, "DEADLINE", datetime.now(timezone.utc) - timedelta(seconds=1)), \
                patch.object(llm.urllib.request, "urlopen", never), patch.object(config, "LLM_TIMEOUT", 480):
            with self.assertRaises(llm.StageDeadline):
                llm.ask_json("s", "u")
        self.assertEqual(llm.timing_summary(), (0, 0.0, 0.0, 0.0, 1))                # one skipped, no timings, then reset
        self.assertIsNone(llm.timing_summary())
        self.assertGreaterEqual(llm.STAGE_SKIPPED, 1)                                # the stage total survives the per-agent reset
        llm.STAGE_SKIPPED = 0

    def test_an_agent_goes_quiet_when_the_stage_is_cut(self):
        from datetime import datetime, timedelta, timezone
        from agents import llm_news
        item = [{"when": "2026-09-16", "title": "x", "publisher": "y"}]
        with patch.object(llm, "DEADLINE", datetime.now(timezone.utc) - timedelta(seconds=1)), patch.object(config, "LLM_TIMEOUT", 480), \
                patch.object(llm_news.market, "headlines", return_value=item), self.assertNoLogs(llm_news.log, level="WARNING"):
            self.assertIsNone(llm_news._one("NVDA", "NVIDIA"))                       # refused by the deadline: None, no warning
        self.assertEqual(llm.timing_summary()[4], 1)
        llm.STAGE_SKIPPED = 0

    def test_end_to_end_seconds_are_gathered_per_call_including_failures(self):
        class Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def ok(req, timeout=None):
            return Resp(json.dumps({"choices": [{"message": {"content": "{}"}}]}).encode())

        def boom(req, timeout=None):
            raise TimeoutError("timed out")

        llm.timing_summary()
        with patch.object(llm, "DEADLINE", None), patch.object(config, "LLM_TIMEOUT", 480):
            with patch.object(llm.urllib.request, "urlopen", ok):
                llm.ask_json("s", "u")
            with patch.object(llm.urllib.request, "urlopen", boom), self.assertRaises(TimeoutError):
                llm.ask_json("s", "u")
        calls, mean, p90, mx, skipped = llm.timing_summary()
        self.assertEqual((calls, skipped), (2, 0))
        self.assertGreaterEqual(mx, mean)


class SameDaySnapshots(unittest.TestCase):
    def test_a_second_snapshot_the_same_day_gets_its_own_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, root = Path(tmp) / "earnings-ai", Path(tmp) / "snapshots"
            (src / "graph").mkdir(parents=True)
            (src / "graph" / "merged_graph.json").write_text('{"v": 1}', encoding="utf-8")
            (src / "graph" / "exposure.json").write_text('{"v": 1}', encoding="utf-8")
            today = date(2026, 9, 16)
            with patch.object(config, "EARNINGS_AI_DIR", src), patch.object(snapshots, "ROOT", root):
                self.assertEqual(snapshots.take(today), "2026-09-16")
                self.assertIsNone(snapshots.take(today))                                   # nothing changed: no-op
                (src / "graph" / "exposure.json").write_text('{"v": 2}', encoding="utf-8")
                second = snapshots.take(today)
                self.assertTrue(second.startswith("2026-09-16_"))                           # a suffixed directory, the first kept
                self.assertEqual(json.loads((root / "2026-09-16" / "graph" / "exposure.json").read_text()), {"v": 1})
                self.assertEqual(snapshots.dir_for("2026-09-16"), root / "2026-09-16")     # a pin by date stays on the first
                self.assertEqual(snapshots.dir_for(today + timedelta(days=1)).name, second)  # later dates see the newest
                self.assertEqual(snapshots.latest()[0], second)
                self.assertIsNone(snapshots.take(today))                                   # unchanged again: no-op


if __name__ == "__main__":
    unittest.main()
