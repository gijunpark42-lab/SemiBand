"""LLM news agent — Claude reads the last few weeks of headlines (yfinance, free)
and gives a direction. Abstains when there are no recent headlines.
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
    "You are an event-driven equity analyst. From recent headlines only, judge whether the stock "
    "is likely to beat the SOXX semiconductor index over the next 1-4 weeks. Headlines are noisy: "
    "give direction near 0 with low confidence unless there is a clear, material, recent catalyst "
    "(earnings, guidance, large contract, regulatory action, capacity or pricing news)."
)


def _one(ticker, company):
    items = market.news(ticker)
    if not items:
        return None
    lines = "\n".join(f"- [{i['when'] or '?'}] {i['title']} ({i['publisher'] or '?'})" for i in items)
    user = f"Ticker: {ticker} ({company})\nHeadlines, newest first:\n{lines}\n\nTrading is commission-free but each order costs about 5 bps in slippage, and there is no obligation to trade: a direction near 0 with low confidence is a valid answer. Give your opinion as JSON."
    try:
        o = llm.ask_json(SYSTEM, user)
    except Exception as exc:
        log.warning("%s %s: %s", NAME, ticker, exc)
        return None
    return Signal(NAME, ticker, o["direction"], o["confidence"], int(o["horizon_days"]),
                  str(o["reason"])[:200]).clipped()


def run(universe: dict, ctx: dict) -> list[Signal]:
    if not llm.ensure_server():
        return []
    with ThreadPoolExecutor(max_workers=config.LLM_WORKERS) as pool:
        results = list(pool.map(lambda kv: _one(kv[0], kv[1]), universe.items()))
    return [s for s in results if s]
