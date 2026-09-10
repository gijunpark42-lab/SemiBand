"""LLM guidance agent — Claude reads the company's OWN latest earnings-call
signals from the graph (guidance, backlog, capacity, pricing, margins) and
judges guidance momentum. Different input from `llm_supply` (which reads
the structural position: chains, edges, transitions) and from `llm_news`
(headlines). Abstains when the newest signal is older than 180 days.
"""
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import config
from agents import llm
from agents.base import Signal
from agents.supply_chain import _load, curated_metrics

log = logging.getLogger(__name__)
NAME = "llm_guidance"
MAX_SIGNALS = 12
MAX_AGE_DAYS = 180
_DATE = re.compile(r"\((\d{2})-(\d{2})-(\d{4})\)")

SYSTEM = (
    "You are a sell-side analyst judging GUIDANCE MOMENTUM from a company's own recent earnings-call "
    "statements: is guidance being raised or cut, is backlog/capacity growing, are prices and margins "
    "moving up or down, is the tone accelerating or decelerating quarter over quarter? Decide whether "
    "the stock is likely to beat the SOXX semiconductor index over the next 1-4 weeks on that basis "
    "alone. Quote the specific figures that drive your view. Use direction near 0 and low confidence "
    "when the statements are stale, vague, or mixed."
)


def _label_date(label):
    m = _DATE.search(label or "")
    return date(int(m.group(3)), int(m.group(1)), int(m.group(2))) if m else None


def _own_signals(node):
    seen, rows = set(), []
    for q in node.get("quarterly_data") or []:
        key = (q.get("quarter"), (q.get("signal") or "")[:80])
        if key in seen:
            continue
        seen.add(key)
        rows.append(q)
    rows.sort(key=lambda q: _label_date(q.get("quarter")) or date.min, reverse=True)
    return rows[:MAX_SIGNALS]


def _one(ticker, company, node, price_line):
    rows = _own_signals(node)
    if not rows:
        return None
    newest = _label_date(rows[0].get("quarter"))
    if newest and (date.today() - newest).days > MAX_AGE_DAYS:
        return None
    lines = []
    for q in rows:
        fig = q.get("figure")
        lines.append(f"- [{q.get('quarter')}] {(q.get('signal') or '')[:500]}"
                     + (f" — figure: {str(fig)[:150]}" if fig and "no specific" not in str(fig) else ""))
    curated = curated_metrics().get(company) or {}
    curated_block = ""
    if curated:
        curated_block = ("\nCurated summary of the latest call (as of "
                         f"{curated.get('asof', '?')}):\n"
                         + "\n".join(f"- {k}: {v}" for k, v in curated.items()
                                     if k != "asof" and v and v != "—") + "\n")
    user = (f"Ticker: {ticker} ({company})\n{price_line}\n{curated_block}\n"
            f"Company's own recent call/filing statements, newest first:\n" + "\n".join(lines)
            + "\n\nGive your opinion as JSON.")
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
    graph, _, _ = _load()
    by_id = {n["id"]: n for n in graph["nodes"]}
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

    jobs = [(t, c, by_id[c]) for t, c in universe.items() if c in by_id]
    with ThreadPoolExecutor(max_workers=config.LLM_WORKERS) as pool:
        results = list(pool.map(lambda j: _one(j[0], j[1], j[2], price_line(j[0])), jobs))
    return [s for s in results if s]
