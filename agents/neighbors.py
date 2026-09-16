"""Neighbors agent — the map one hop out.

`supply_chain` looks at what the company itself said. This agent looks at
who it sells to and buys from: if its customers just reported sold-out
capacity or spoke recently, demand is pulling on this name. Customers count
more than suppliers (demand pull > supply push). Free, deterministic, reads
the graph only.

Since 2026-09-16 the score is the replay's point-in-time formula (agents/graph_pit.py: the neighbours' dated statements
of the last 90 days) with asof = today. The cumulative exposure counts it scored before are undated and put its live
signals far above the replay's level (+0.41 vs +0.21 mean direction), so the learner's weights did not apply to them.
Read-through (customers' chain statements) stays measured only: it was tested 2026-09-10 and hurt the backtest
(+447% -> +335%, Sharpe 2.49 -> 2.19).
"""
from datetime import date

from agents.base import Signal

NAME = "neighbors"


def run(universe: dict, ctx: dict) -> list[Signal]:
    """universe = {ticker: company_name}; a name whose neighbours have no dated statement yet is silent, as in the replay."""
    from agents.graph_pit import pit_map
    pit = pit_map()
    asof = ctx.get("asof") or date.today()
    return [s for s in (pit.neighbors(ticker, company, asof) for ticker, company in universe.items()) if s is not None]
