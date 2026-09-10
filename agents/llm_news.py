"""LLM news agent — Claude reads recent headlines (Finnhub + yfinance, free)
plus, for the most relevant names, a keyless DuckDuckGo news search with
snippets (market.web_news), then gives a direction. Abstains when there is
nothing to read. (Claude Code's built-in WebSearch is not available in -p mode.)
"""
import logging
from concurrent.futures import ThreadPoolExecutor

import config
import market
from agents import llm
from agents.base import Signal

log = logging.getLogger(__name__)
NAME = "llm_news"

SYSTEM = (
    "You are an event-driven equity analyst. From recent headlines and web-search snippets judge whether "
    "the stock is likely to beat the SOXX semiconductor index over the next 1-4 weeks. Headlines are noisy: "
    "give direction near 0 with low confidence unless there is a clear, material, recent catalyst (earnings, "
    "guidance, large contract, regulatory action, capacity or pricing news). Name the source of anything material."
)

FOOTER = ("Trading is commission-free but each order costs about 5 bps in slippage, and there is no obligation "
          "to trade: a direction near 0 with low confidence is a valid answer. Give your opinion as JSON.")


def _one(ticker, company, search=False):
    items = market.headlines(ticker)
    lines = "\n".join(f"- [{i['when'] or '?'}] {i['title']} ({i['publisher'] or '?'})" for i in items) \
        or "(none from the feeds)"
    extra = ""
    if search:
        web = market.web_news(f"{company} {ticker}")
        if web:
            extra = "\nWeb search results (DuckDuckGo news, last week):\n" + "\n".join(
                f"- [{w['when'] or '?'}] {w['title']} ({w['publisher'] or '?'}) - {w['snippet']}" for w in web) + "\n"
    if not items and not extra:
        return None
    user = f"Ticker: {ticker} ({company})\nHeadlines, newest first:\n{lines}\n{extra}\n{FOOTER}"
    try:
        o = llm.ask_json(SYSTEM, user)
    except Exception as exc:
        log.warning("%s %s: %s", NAME, ticker, exc)
        return None
    return Signal(NAME, ticker, o["direction"], o["confidence"], int(o["horizon_days"]),
                  str(o["reason"])[:200]).clipped()


def run(universe: dict, ctx: dict) -> list[Signal]:
    """universe arrives ordered: holdings first, then by preliminary |conviction| (see cycle.run_agents);
    the first WEB_SEARCH_TICKERS names also get web-search snippets."""
    if not llm.ensure_server():
        return []
    jobs = [(t, c, i < config.WEB_SEARCH_TICKERS) for i, (t, c) in enumerate(universe.items())]
    with ThreadPoolExecutor(max_workers=config.LLM_WORKERS) as pool:
        results = list(pool.map(lambda j: _one(*j), jobs))
    return [s for s in results if s]
