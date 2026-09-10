"""LLM supply-chain agent — Claude reads the company's supply-chain report
(the same tool TradingAgents uses) plus recent relative performance and gives
a direction. Runs through the local Claude server; no API key.
"""
import importlib.util
import logging
import os
import sys
import types
from concurrent.futures import ThreadPoolExecutor

import config
from agents import llm
from agents.base import Signal

log = logging.getLogger(__name__)
NAME = "llm_supply"

SYSTEM = (
    "You are a semiconductor / AI-infrastructure supply-chain analyst deciding whether a stock "
    "is likely to beat the SOXX semiconductor index over the next 1-4 weeks. You are given the "
    "company's position in a supply-chain map built only from earnings-call transcripts, and its "
    "recent price move versus SOXX. Weigh: generation transitions (gaining vs losing content), "
    "sold-out capacity, deal freshness, and whether the price already reflects it. "
    "Be decisive but honest: use direction near 0 and low confidence when the evidence is thin or stale."
)

REPORT_CHARS = 9000


def _report_builder():
    """Load build_supply_chain_report straight from the TradingAgents file.

    The file is loaded by path (not through the tradingagents package, whose
    __init__ pulls in langchain). It decorates one function with langchain's
    @tool; we do not have langchain here, so a no-op stand-in is registered
    when it is missing."""
    try:
        import langchain_core.tools  # noqa: F401
    except ImportError:
        pkg = types.ModuleType("langchain_core")
        tools = types.ModuleType("langchain_core.tools")
        tools.tool = lambda f: f
        pkg.tools = tools
        sys.modules["langchain_core"] = pkg
        sys.modules["langchain_core.tools"] = tools
    os.environ.setdefault("EARNINGS_AI_DIR", str(config.EARNINGS_AI_DIR))  # the tool follows our config
    path = config.TRADINGAGENTS_DIR / "tradingagents" / "agents" / "utils" / "supply_chain_tools.py"
    spec = importlib.util.spec_from_file_location("supply_chain_tools", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.build_supply_chain_report


def _one(build, ticker, company, price_line):
    report = build(ticker, company)
    if report.startswith("SUPPLY_CHAIN_UNAVAILABLE"):
        return None
    user = (f"Ticker: {ticker} ({company})\n{price_line}\n\n"
            f"{report[:REPORT_CHARS]}\n\nTrading is commission-free but each order costs about 5 bps in slippage, and there is no obligation to trade: a direction near 0 with low confidence is a valid answer. Give your opinion as JSON.")
    try:
        o = llm.ask_json(SYSTEM, user)
    except Exception as exc:  # one bad call must not kill the cycle
        log.warning("%s %s: %s", NAME, ticker, exc)
        return None
    return Signal(NAME, ticker, o["direction"], o["confidence"], int(o["horizon_days"]),
                  str(o["reason"])[:200]).clipped()


def run(universe: dict, ctx: dict) -> list[Signal]:
    if not llm.ensure_server():
        return []
    build = _report_builder()
    closes = ctx["closes"]
    bench = closes[config.BENCHMARK].dropna()
    b20 = bench.iloc[-1] / bench.iloc[-21] - 1

    def price_line(t):
        if t not in closes.columns or closes[t].dropna().shape[0] < 22:
            return "Recent price move: unavailable"
        c = closes[t].dropna()
        m20 = c.iloc[-1] / c.iloc[-21] - 1
        return (f"Recent price move: {t} {m20*100:+.1f}% over 20 trading days, "
                f"{config.BENCHMARK} {b20*100:+.1f}% (relative {(m20-b20)*100:+.1f}%).")

    with ThreadPoolExecutor(max_workers=config.LLM_WORKERS) as pool:
        results = list(pool.map(lambda kv: _one(build, kv[0], kv[1], price_line(kv[0])), universe.items()))
    return [s for s in results if s]
