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
