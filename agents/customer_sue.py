"""Customer earnings-surprise agent (round 46 shadow, 2026-09-18; Ramnath 2002, Zhu 2014): a customer's earnings surprise
transfers to its suppliers. For each name, the mean latest EPS surprise (%) of its graph customers whose report date is
strictly before the day and within WINDOW_DAYS calendar days; direction = tanh(surprise / SCALE), confidence 0.4, horizon 20.
Reads the earnings rows the context carries (the replay loads them once; live, market.earnings) — point-in-time by
date < asof. Silent for names without a customer that reported inside the window. The customer edges are today's graph.
"""
import math
from datetime import date

import market
from agents.base import Signal
from agents.customer_momentum import _links

NAME = "customer_sue"
WINDOW_DAYS = 42        # calendar days, about 30 sessions
SCALE = 10.0            # a 10% surprise -> direction 0.76


def run(universe: dict, ctx: dict) -> list[Signal]:
    asof = ctx.get("asof") or date.today()
    data = ctx.get("earnings") or market.earnings(list(universe))
    out = []
    for ticker, customers in _links(universe, "customers").items():
        vals = []
        for c in customers:
            rows = [r for r in (data.get(c) or []) if r["date"] < asof.isoformat() and r.get("surprise_pct") is not None]
            if not rows:
                continue
            last = max(rows, key=lambda r: r["date"])
            if (asof - date.fromisoformat(last["date"])).days <= WINDOW_DAYS:
                vals.append(float(last["surprise_pct"]))
        if not vals:
            continue
        avg = sum(vals) / len(vals)
        out.append(Signal(NAME, ticker, math.tanh(avg / SCALE), 0.4, 20,
                          f"{len(vals)} customers reported within {WINDOW_DAYS}d, mean EPS surprise {avg:+.0f}%").clipped())
    return out
