"""LLM guidance agent — Claude reads the company's OWN latest earnings-call
signals from the graph (guidance, backlog, capacity, pricing, margins) and
judges guidance momentum. Different input from `llm_supply` (which reads
the structural position: chains, edges, transitions) and from `llm_news`
(headlines). Transcripts only: earnings calls and conference appearances;
SEC filings and analyst notes are left out (2026-09-13). Abstains when the
newest statement is older than 180 days.
"""
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import config
import market
from agents import llm, llm_reuse
from agents.base import NOT_TRANSCRIPT, Signal
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
        if NOT_TRANSCRIPT.search(q.get("quarter") or ""):
            continue
        key = (q.get("quarter"), (q.get("signal") or "")[:80])
        if key in seen:
            continue
        seen.add(key)
        rows.append(q)
    rows.sort(key=lambda q: _label_date(q.get("quarter")) or date.min, reverse=True)
    return rows[:MAX_SIGNALS]


def _one(ticker, company, node, price_line, reuse=None):
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
            f"Company's own recent earnings-call and conference statements, newest first:\n" + "\n".join(lines)
            + "\n\nTrading is commission-free but each order costs about 5 bps in slippage, and there is no obligation to trade: a direction near 0 with low confidence is a valid answer. Give your opinion as JSON.")
    try:
        o, since = reuse.ask(ticker, SYSTEM, user, price_line) if reuse else (llm.ask_json(SYSTEM, user), None)
    except llm.StageDeadline:   # the cycle's Claude stage was cut: quiet, the stage log carries the count
        return None
    except Exception as exc:
        log.warning("%s %s: %s", NAME, ticker, exc)
        return None
    reason = str(o["reason"]) if since is None else f"reused from {since} (same input): {o['reason']}"
    return Signal(NAME, ticker, o["direction"], o["confidence"], int(o["horizon_days"]), reason[:200]).clipped()


def run(universe: dict, ctx: dict) -> list[Signal]:
    if not llm.ensure_server():
        return []
    graph, _, _ = _load()
    by_id = {n["id"]: n for n in graph["nodes"]}
    closes = ctx["closes"]
    live = market.live_prices(list(universe) + [config.BENCHMARK])   # today's pre-market trades where there are any (user 2026-09-15)

    def price_line(t):
        return market.move_line(closes, t, live)

    jobs = [(t, c, by_id[c]) for t, c in universe.items() if c in by_id]
    reuse = llm_reuse.Session(NAME, ctx.get("today") or date.today().isoformat()) if NAME in config.LLM_REUSE_AGENTS else None
    with ThreadPoolExecutor(max_workers=config.LLM_WORKERS) as pool:
        results = list(pool.map(lambda j: _one(j[0], j[1], j[2], price_line(j[0]), reuse), jobs))
    if reuse:
        reuse.save()
        log.info("%s: %d answers reused (same input), %d asked", NAME, reuse.reused, len(reuse.updates))
    return [s for s in results if s]
