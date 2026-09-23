"""2026-09-22 answer reuse for llm_supply / llm_guidance: the same prompt (price line aside) is not asked twice within
LLM_REUSE_MAX_DAYS unless the name's move relative to SOXX shifted by LLM_REUSE_MOVE_PP points.

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_llm_reuse
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

import config
import market
from agents import llm, llm_reuse, llm_supply

SYSTEM = "system prompt"


def price(rel):
    return f"Recent price move (last close): NVDA +12.0% over 20 trading days, SOXX +4.0% (relative {rel:+.1f}%)."


def prompt(line, report="report A"):
    return f"Ticker: NVDA (NVIDIA)\n{line}\n\n{report}\n\nGive your opinion as JSON."


ANSWER = {"direction": 0.6, "confidence": 0.7, "horizon_days": 10, "reason": "sold-out capacity"}


class Key(unittest.TestCase):
    def test_only_the_price_line_is_ignored(self):
        k = llm_reuse.key(SYSTEM, prompt(price(8.0)), price(8.0))
        self.assertEqual(k, llm_reuse.key(SYSTEM, prompt(price(-3.0)), price(-3.0)))
        self.assertNotEqual(k, llm_reuse.key(SYSTEM, prompt(price(8.0), "report B"), price(8.0)))
        self.assertNotEqual(k, llm_reuse.key("another system", prompt(price(8.0)), price(8.0)))
        with patch.object(config, "LLM_MODEL", "another-model"):
            self.assertNotEqual(k, llm_reuse.key(SYSTEM, prompt(price(8.0)), price(8.0)))

    def test_relative_reads_the_live_move_line(self):
        idx = pd.bdate_range("2026-06-01", periods=40)
        closes = pd.DataFrame({"NVDA": np.linspace(100, 130, 40), "SOXX": np.linspace(400, 420, 40)}, index=idx)
        line = market.move_line(closes, "NVDA", {})
        m = closes.NVDA.iloc[-1] / closes.NVDA.iloc[-21] - 1
        b = closes.SOXX.iloc[-1] / closes.SOXX.iloc[-21] - 1
        self.assertAlmostEqual(llm_reuse.relative(line), round((m - b) * 100, 1))
        self.assertIsNone(llm_reuse.relative("Recent price move: unavailable"))


class Session(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self._state = patch.object(config, "STATE_DIR", Path(self._tmp.name))
        self._state.start()
        self.calls = []

    def tearDown(self):
        self._state.stop()
        self._tmp.cleanup()

    def ask(self, today, line, report="report A", fail=False):
        def ask_json(system, user):
            self.calls.append(user)
            if fail:
                raise RuntimeError("server down")
            return dict(ANSWER)

        s = llm_reuse.Session("llm_supply", today)
        with patch.object(llm, "ask_json", ask_json):
            try:
                out = s.ask("NVDA", SYSTEM, prompt(line, report), line)
            except RuntimeError:
                out = None
        s.save()
        return out

    def test_the_same_question_is_asked_once(self):
        self.assertEqual(self.ask("2026-09-22", price(8.0)), (ANSWER, None))
        self.assertEqual(self.ask("2026-09-23", price(12.0)), (ANSWER, "2026-09-22"))   # 4 points: reused, no call
        self.assertEqual(len(self.calls), 1)

    def test_a_new_input_a_big_move_or_age_asks_again(self):
        self.ask("2026-09-22", price(8.0))
        self.assertIsNone(self.ask("2026-09-23", price(8.0), report="report B")[1])       # the report changed
        self.assertIsNone(self.ask("2026-09-24", price(-3.0), report="report B")[1])      # 11 points since 09-23's answer
        self.assertEqual(self.ask("2026-10-01", price(-3.0), report="report B")[1], "2026-09-24")   # 7 days: still reused
        self.assertIsNone(self.ask("2026-10-02", price(-3.0), report="report B")[1])      # 8 days: asked again
        self.assertEqual(len(self.calls), 4)

    def test_a_failed_call_keeps_the_stored_answer_and_other_agents_survive(self):
        self.ask("2026-09-22", price(8.0))
        data = json.loads(llm_reuse.path().read_text(encoding="utf-8"))
        data["llm_guidance"] = {"AMD": {"key": "k", "date": "2026-09-22", "rel": 1.0, "answer": ANSWER}}
        llm_reuse.path().write_text(json.dumps(data), encoding="utf-8")
        self.assertIsNone(self.ask("2026-09-23", price(8.0), report="report B", fail=True))
        stored = json.loads(llm_reuse.path().read_text(encoding="utf-8"))
        self.assertEqual(stored["llm_supply"]["NVDA"]["date"], "2026-09-22")
        self.assertIn("AMD", stored["llm_guidance"])


class SupplyAgent(unittest.TestCase):
    def test_a_reused_answer_says_so_in_the_reason(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp, patch.object(config, "STATE_DIR", Path(tmp)):
            build = lambda t, c: "## NVIDIA supply chain\n- NVIDIA [Q2 FY27 call (08-27-2026)]: sold out through 2027"
            with patch.object(llm, "ask_json", return_value=dict(ANSWER)) as ask:
                first = llm_reuse.Session("llm_supply", "2026-09-22")
                fresh = llm_supply._one(build, "NVDA", "NVIDIA", price(8.0), first)
                first.save()
                again = llm_supply._one(build, "NVDA", "NVIDIA", price(9.0), llm_reuse.Session("llm_supply", "2026-09-23"))
        self.assertEqual(ask.call_count, 1)
        self.assertEqual(fresh.reason, "sold-out capacity")
        self.assertEqual(again.reason, "reused from 2026-09-22 (same input): sold-out capacity")
        self.assertEqual((again.direction, again.confidence, again.horizon), (fresh.direction, fresh.confidence, fresh.horizon))


if __name__ == "__main__":
    unittest.main()
