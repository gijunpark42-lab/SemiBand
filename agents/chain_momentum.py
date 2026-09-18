"""Chain-momentum agent (round 50 candidate, 2026-09-18; industry momentum, Moskowitz & Grinblatt 1999): a name's direction is the
trailing DAYS-session return of its graph chains — the equal-weight return of the universe names carrying the same chain tag —
relative to the universe's mean, averaged over the name's tags. Prices only (point-in-time by construction: only the closes in the
context are read); the chain tags are today's graph (the graph-wide caveat). Silent for a name whose chains have fewer than
MIN_NAMES priced members or no tag at all. The user's "sector agent" (2026-09-18), tested as a vote rather than a fixed allocation.
"""
import math

import config
from agents.base import Signal
from agents.graph_pit import pit_map

NAME = "chain_momentum"
DAYS = 126                 # six months, the standard industry-momentum formation window
GAIN = 4.0
MIN_NAMES = 3


def trailing_returns(closes, days=DAYS):
    """{ticker: return over the last `days` sessions of the frame}, from the last row."""
    out = {}
    for t in closes.columns:
        c = closes[t].dropna()
        if len(c) > days and float(c.iloc[-days - 1]) > 0:
            out[t] = float(c.iloc[-1] / c.iloc[-days - 1] - 1)
    return out


def chain_returns(universe, rets, min_names=MIN_NAMES):
    """({tag: equal-weight trailing return of the universe names with that tag}, {ticker: tags}); tags with fewer than
    `min_names` priced members are dropped."""
    chains = pit_map().chains
    tags = {t: sorted(chains.get(company, ())) for t, company in universe.items()}
    members = {}
    for t, tg in tags.items():
        if t in rets:
            for g in tg:
                members.setdefault(g, []).append(rets[t])
    return {g: sum(v) / len(v) for g, v in members.items() if len(v) >= min_names}, tags


def run(universe: dict, ctx: dict) -> list[Signal]:
    closes = ctx["closes"]
    rets = trailing_returns(closes)
    priced = [rets[t] for t in universe if t in rets]
    if len(priced) < MIN_NAMES:
        return []
    base = sum(priced) / len(priced)
    by_chain, tags = chain_returns(universe, rets, MIN_NAMES)
    out = []
    for t in universe:
        vals = [by_chain[g] for g in tags.get(t, ()) if g in by_chain]
        if not vals:
            continue
        rel = sum(vals) / len(vals) - base
        out.append(Signal(NAME, t, math.tanh(GAIN * rel), 0.5, 20,
                          f"{len(vals)} chains, {DAYS}d chain return {rel * 100:+.1f}% vs the universe").clipped())
    return out
