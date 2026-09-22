"""2026-09-22 fixes: the Claude stage survives a dead local server (one restart and one retry, one server for six threads), runs
llm_news first and carries llm_supply / llm_guidance forward from their last recorded sessions when a call fails or the deadline
passes; the insider shadow agent no longer fetches inside the cycle; close mode sends marketable orders that leave time for the
clean-up before the bell; the MOC fraction is floored to what the account holds.

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_cycle_resilience
"""
import io
import json
import tempfile
import threading
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

import broker
import config
import cycle
import ledger
from agents import insider, llm
from agents.base import Signal
from alpaca.trading.enums import OrderSide, TimeInForce


class _Reply(io.BytesIO):
    """What urlopen returns: a context manager over one chat completion."""
    def __init__(self, obj):
        super().__init__(json.dumps({"choices": [{"message": {"content": json.dumps(obj)}}]}).encode())

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class ClaudeServerRestart(unittest.TestCase):
    def setUp(self):
        self._deadline, llm.DEADLINE = llm.DEADLINE, None

    def tearDown(self):
        llm.DEADLINE = self._deadline

    def _ask(self, first_error, server_back=True):
        calls = []

        def urlopen(req, timeout=None):
            calls.append(req)
            if len(calls) == 1:
                raise first_error
            return _Reply({"direction": 1})

        with patch.object(llm.urllib.request, "urlopen", urlopen), \
                patch.object(llm, "ensure_server", return_value=server_back) as ensure:
            try:
                return llm.ask_json("s", "u"), len(calls), ensure.call_count
            except urllib.error.URLError as exc:
                return exc, len(calls), ensure.call_count

    def test_a_refused_call_restarts_the_server_and_retries_once(self):
        out, calls, starts = self._ask(urllib.error.URLError(ConnectionRefusedError(10061, "refused")))
        self.assertEqual((out, calls, starts), ({"direction": 1}, 2, 1))

    def test_an_http_error_from_the_server_is_not_retried(self):
        out, calls, starts = self._ask(urllib.error.HTTPError("http://x", 500, "boom", {}, None))
        self.assertIsInstance(out, urllib.error.HTTPError)
        self.assertEqual((calls, starts), (1, 0))

    def test_a_server_that_does_not_come_back_raises_the_refusal(self):
        out, calls, starts = self._ask(urllib.error.URLError(ConnectionRefusedError(10061, "refused")), server_back=False)
        self.assertIsInstance(out, urllib.error.URLError)
        self.assertEqual((calls, starts), (1, 1))

    def test_six_threads_start_one_server(self):
        started, up = [], threading.Event()

        def popen(*args, **kwargs):
            started.append(args)
            up.set()                                   # the server answers once it has been started
            return SimpleNamespace()

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            (root / ".venv" / "Scripts").mkdir(parents=True)
            (root / ".venv" / "Scripts" / "python.exe").write_text("")
            (root / "local-claude").mkdir()
            (root / "local-claude" / "server.py").write_text("")
            with patch.object(config, "TRADINGAGENTS_DIR", root), patch.object(config, "STATE_DIR", root), \
                    patch.object(llm, "health", side_effect=lambda: up.is_set()), \
                    patch.object(llm.subprocess, "Popen", popen), patch.object(llm.time, "sleep", lambda s: None):
                results = []
                threads = [threading.Thread(target=lambda: results.append(llm.ensure_server())) for _ in range(6)]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join()
        self.assertEqual(len(started), 1)
        self.assertEqual(results, [True] * 6)


class CarryForward(unittest.TestCase):
    def test_the_latest_signal_of_the_last_sessions_with_its_source_date(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            with patch.object(config, "STATE_DIR", root), patch.object(ledger, "DB", root / "ledger.sqlite"):
                def add(day, *sigs):
                    ledger.add_predictions(day, list(sigs), {s.ticker: 1.0 for s in sigs}, {s.ticker: 1.0 for s in sigs})
                add("2026-09-15", Signal("llm_supply", "OLD", 1.0, 0.9, 20, "four sessions back"))
                add("2026-09-16", Signal("llm_supply", "AAA", -1.0, 0.5, 20, "first"))
                add("2026-09-17", Signal("llm_supply", "AAA", 1.0, 0.7, 20, "second"), Signal("llm_news", "BBB", 1.0, 0.7, 10, "news"))
                add("2026-09-18", Signal("llm_supply", "BBB", 0.5, 0.6, 20, "bbb"),
                    Signal("llm_supply", "CCC", 1.0, 0.8, 20, "carried from 2026-09-15: stale"))   # a carried row is never re-carried
                add("2026-09-22", Signal("llm_supply", "AAA", 0.0, 0.1, 20, "today"))     # the date itself is never carried
                got = {s.ticker: s for s in ledger.carried_signals("llm_supply", ["AAA", "BBB", "CCC", "OLD", "ZZZ"], "2026-09-22", 3)}
                self.assertEqual(ledger.carried_signals("llm_supply", [], "2026-09-22", 3), [])
                add("2026-09-19", Signal("technical", "AAA", 1.0, 0.5, 10, "a later cycle"))   # any agent's cycle date counts: the
                later = {s.ticker for s in ledger.carried_signals("llm_supply", ["AAA", "BBB"], "2026-09-22", 2)}   # window is 09-19, 09-18
        self.assertEqual(set(got), {"AAA", "BBB"})                                # OLD is outside the window, ZZZ has no record
        self.assertEqual((got["AAA"].direction, got["AAA"].confidence, got["AAA"].horizon), (1.0, 0.7, 20))
        self.assertEqual(got["AAA"].reason, "carried from 2026-09-17: second")
        self.assertEqual((got["BBB"].agent, got["BBB"].reason), ("llm_supply", "carried from 2026-09-18: bbb"))
        self.assertEqual(later, {"BBB"})                                          # AAA's 09-17 view expired


class ClaudeStage(unittest.TestCase):
    def _run(self, fail=(), deadline_passed=False):
        ran, carried_for = [], {}

        def run_agent(name, universe, ctx):
            ran.append(name)
            return [] if name in fail else [Signal(name, t, 1.0, 0.5, 10, "fresh") for t in universe]

        def carried(agent, tickers, day, sessions):
            carried_for[agent] = list(tickers)
            return [Signal(agent, t, -1.0, 0.4, 20, "carried from 2026-09-18: x") for t in tickers]

        with patch.object(config, "AGENTS", ["technical", "llm_supply", "llm_guidance", "llm_news"]), \
                patch.object(config, "SHADOW_AGENTS", ()), patch.object(config, "EXEC_MODE", "close"), \
                patch.object(config, "LLM_STAGE_DEADLINE_CLOSE", "00:01" if deadline_passed else None), \
                patch.object(cycle, "_run_agent", run_agent), patch.object(cycle.ledger, "carried_signals", carried), \
                patch.object(cycle.learner, "predict", return_value=({"AAA": 0.1, "BBB": -0.1}, {})), \
                patch.object(cycle.llm, "ensure_server", return_value=True):
            signals = cycle.run_agents({"AAA": "A", "BBB": "B"}, {"today": "2026-09-22"}, {}, {}, use_llm=True)
        self.assertIsNone(llm.DEADLINE)                                           # the moderator must not be refused
        return ran, carried_for, signals

    def test_news_runs_first_and_a_failed_supply_is_carried(self):
        ran, carried_for, signals = self._run(fail=("llm_supply", "llm_news"))
        self.assertEqual(ran, ["technical", "llm_news", "llm_guidance", "llm_supply"])
        self.assertEqual(carried_for, {"llm_guidance": [], "llm_supply": ["AAA", "BBB"]})   # news is never carried
        by = {(s.agent, s.ticker): s.reason for s in signals}
        self.assertEqual(by[("llm_supply", "AAA")], "carried from 2026-09-18: x")
        self.assertEqual(by[("llm_guidance", "BBB")], "fresh")
        self.assertFalse(any(s.agent == "llm_news" for s in signals))

    def test_past_the_deadline_the_slow_agents_are_carried_and_news_is_left_out(self):
        ran, carried_for, signals = self._run(deadline_passed=True)
        self.assertEqual(ran, ["technical"])
        self.assertEqual(carried_for, {"llm_guidance": ["AAA", "BBB"], "llm_supply": ["AAA", "BBB"]})
        self.assertEqual({s.agent for s in signals}, {"technical", "llm_guidance", "llm_supply"})


class InsiderInCycle(unittest.TestCase):
    def test_the_cycle_run_does_not_fetch(self):
        for flag, expected in ((False, 0), (True, 1)):
            with patch.object(config, "INSIDER_REFRESH_IN_CYCLE", flag), patch.object(insider, "refresh") as refresh, \
                    patch.object(insider, "_purchases", return_value={}):
                self.assertEqual(insider.run({"AAA": "A"}, {"today": "2026-09-22"}), [])
            self.assertEqual(refresh.call_count, expected)


class CloseOrders(unittest.TestCase):
    def test_the_moc_fraction_never_exceeds_what_the_account_holds(self):
        sent = []
        client = SimpleNamespace(submit_order=lambda req: (sent.append(req) or SimpleNamespace(id=f"o{len(sent)}")),
                                 get_open_position=lambda s: SimpleNamespace(qty="388.116618904"))   # VRT, 2026-09-22
        with patch.object(broker, "_dry", return_value=False), patch.object(broker, "_client", client):
            broker.close_moc("VRT", "sb2-v")
        self.assertEqual((sent[0].qty, sent[0].time_in_force, sent[0].side), (388, TimeInForce.CLS, OrderSide.SELL))
        self.assertEqual(sent[1].qty, 0.116618)                                  # rounding gave 0.116619 > 0.116618904 held

    def test_close_orders_leave_room_for_the_cleanup_before_the_bell(self):
        self.assertIn(config.CLOSE_ORDER_TYPE, ("market", "moc"))
        last = pd.Timestamp(f"2026-09-22 {config.CLOSE_ORDER_CUTOFF}") + pd.Timedelta(minutes=config.CLOSE_CLEANUP_MIN + 1)
        self.assertLess(config.CLOSE_REFRESH_TIME, config.CLOSE_ORDER_CUTOFF)
        self.assertLess(last, pd.Timestamp("2026-09-22 16:00"))                  # remainders go out as market orders before 16:00
        self.assertEqual(config.LLM_ORDER[0], "llm_news")
        self.assertNotIn("llm_news", config.CARRY_FORWARD_AGENTS)                # a headline signal is never carried to another day


if __name__ == "__main__":
    unittest.main()
