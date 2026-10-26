"""Claude API first, local server after (2026-10-26): the API path, its spend log, the budget and the billing switch-off.

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_llm_api
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import anthropic
import httpx2

import config
from agents import llm

ANSWER = {"direction": 0.3, "confidence": 0.5, "horizon_days": 20, "reason": "r"}


def _message(answer=ANSWER, stop="end_turn"):
    usage = SimpleNamespace(input_tokens=1_000_000, cache_creation_input_tokens=0, cache_read_input_tokens=0, output_tokens=100_000)
    return SimpleNamespace(model="claude-opus-5-5", stop_reason=stop, usage=usage,
                           content=[SimpleNamespace(type="text", text=json.dumps(answer))])


def _client(message=None, error=None):
    stream = MagicMock()
    if error:
        stream.__enter__.side_effect = error
    else:
        stream.__enter__.return_value.get_final_message.return_value = message
    client = MagicMock()
    client.with_options.return_value.beta.messages.stream.return_value = stream
    return client


def _status_error(cls, code):
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("x", response=httpx2.Response(code, request=req), body=None)


class ApiFirst(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(config, "STATE_DIR", Path(self.tmp.name)), patch.object(llm, "API_ENABLED", True),
                        patch.object(llm, "API_OFF", None), patch.object(llm, "_API_SPENT", None),
                        patch.dict(os.environ, {"ANTHROPIC_API_KEY_TRADING": "k"})]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        llm._API_CLIENT = None
        self.tmp.cleanup()

    def test_api_answers_and_logs_its_cost(self):
        llm._API_CLIENT = _client(_message())
        with patch.object(llm.urllib.request, "urlopen") as local:
            self.assertEqual(llm.ask_json("s", "u", effort="max"), ANSWER)
        local.assert_not_called()
        row = json.loads((Path(self.tmp.name) / "api_spend.jsonl").read_text(encoding="utf-8"))
        self.assertEqual((row["effort"], row["usd"]), ("max", 6.0))          # 1M in x $4 + 0.1M out x $20
        self.assertAlmostEqual(llm.api_spent(), 6.0)

    def test_billing_error_switches_the_run_to_the_local_server(self):
        llm._API_CLIENT = _client(error=_status_error(anthropic.APIStatusError, 402))
        with patch.object(llm.urllib.request, "urlopen", side_effect=OSError("local")) as local:
            with self.assertRaises(OSError):
                llm.ask_json("s", "u")
        local.assert_called_once()
        self.assertIn("billing", llm.API_OFF)
        self.assertFalse(llm._use_api(None, ""))

    def test_budget_spent_means_local_only(self):
        (Path(self.tmp.name) / "api_spend.jsonl").write_text(json.dumps({"usd": config.LLM_API_BUDGET_USD}) + "\n", encoding="utf-8")
        self.assertFalse(llm._use_api(None, ""))
        self.assertIn("budget", llm.API_OFF)

    def test_api_schema_moves_bounds_into_descriptions(self):
        s = llm._api_schema(llm.OPINION_SCHEMA)
        self.assertNotIn("minimum", json.dumps(s))
        self.assertIn("(from -1 to 1)", s["properties"]["direction"]["description"])
        self.assertEqual(s["properties"]["confidence"]["description"], "from 0 to 1")
        self.assertEqual(s["properties"]["horizon_days"]["enum"], [5, 10, 20])
        self.assertEqual(llm.OPINION_SCHEMA["properties"]["confidence"]["minimum"], 0)   # the original is untouched

    def test_research_model_tools_and_disabled_flag_stay_local(self):
        self.assertFalse(llm._use_api(config.LLM_MODEL_RESEARCH, ""))
        self.assertFalse(llm._use_api(None, "WebSearch"))
        with patch.object(llm, "API_ENABLED", False):
            self.assertFalse(llm._use_api(None, ""))
        self.assertTrue(llm._use_api(None, ""))


if __name__ == "__main__":
    unittest.main()
