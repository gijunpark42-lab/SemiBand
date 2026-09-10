"""Neighbors agent — the map one hop out.

`supply_chain` looks at what the company itself said. This agent looks at
who it sells to and buys from: if its customers just reported sold-out
capacity, gained content in a generation transition, or spoke recently,
demand is pulling on this name. Customers count more than suppliers
(demand pull > supply push). Free, deterministic, reads the graph only.
"""
import math
import re
from datetime import date, timedelta

from agents.base import Signal, clip
from agents.supply_chain import _load, _POSITIVE

NAME = "neighbors"
_DATE = re.compile(r"\((\d{2})-(\d{2})-(\d{4})\)")
_EXPAND = ("expand", "ramp", "increase", "double", "accelerat", "record", "sold out", "constrain", "exceed")


def _label_date(label):
    m = _DATE.search(label or "")
    return date(int(m.group(3)), int(m.group(1)), int(m.group(2))) if m else None


def readthrough(node, customers, by_id, asof, days=120):
    """Customers' recent statements about the chains this company sells into: (score, n, latest)."""
    my_chains = set(node.get("chains") or [])
    since = asof - timedelta(days=days)
    hits, n, latest = 0, 0, None
    for c in customers:
        cust = by_id.get(c)
        if not cust:
            continue
        for q in cust.get("quarterly_data") or []:
            d = _label_date(q.get("quarter", ""))
            if not d or d < since or d > asof or q.get("chain") not in my_chains:
                continue
            n += 1
            text = (q.get("signal") or "").lower()
            if any(w in text for w in _POSITIVE) or any(w in text for w in _EXPAND):
                hits += 1
                if latest is None or d > latest[0]:
                    latest = (d, cust["id"], q.get("chain"))
    # share of customer statements on this company's chains that are expansionary; needs >= 3 to count
    return (0.5 * hits / n if n >= 3 else 0.0), n, latest


def _heat(exp: dict) -> tuple[float, list[str]]:
    """How 'hot' one neighbour is right now, 0..1, plus tags."""
    if not exp:
        return 0.0, []
    score, tags = 0.0, []
    if (exp.get("topics") or {}).get("supply_tightness"):
        score += 0.5; tags.append("tight")
    if "gained" in (exp.get("generations") or {}).values():
        score += 0.3; tags.append("gained")
    days = exp.get("days_since")
    if isinstance(days, (int, float)) and days <= 60:
        score += 0.2; tags.append("fresh")
    return min(score, 1.0), tags


def run(universe: dict, ctx: dict) -> list[Signal]:
    graph, exposure, _ = _load()
    companies = exposure.get("companies") or {}
    by_id = {n["id"]: n for n in graph["nodes"]}
    asof = ctx.get("asof") or date.today()
    customers, suppliers = {}, {}
    for e in graph["edges"]:
        customers.setdefault(e["source"], set()).add(e["target"])
        suppliers.setdefault(e["target"], set()).add(e["source"])
    out = []
    for ticker, company in universe.items():
        cust = customers.get(company, set())
        supp = suppliers.get(company, set())
        if not cust and not supp:
            continue
        c_heat = [_heat(companies.get(n)) for n in cust]
        s_heat = [_heat(companies.get(n)) for n in supp]
        c_avg = sum(h for h, _ in c_heat) / len(c_heat) if c_heat else 0.0
        s_avg = sum(h for h, _ in s_heat) / len(s_heat) if s_heat else 0.0
        c_tight = sum(1 for _, t in c_heat if "tight" in t)
        c_gained = sum(1 for _, t in c_heat if "gained" in t)
        # read-through (customers' chain statements) was tested 2026-09-10 and HURT the backtest
        # (+447% -> +335%, Sharpe 2.49 -> 2.19); it stays out of the score. The LLM supply agent still
        # reads those statements verbatim in its report section.
        rt, rt_n, rt_latest = readthrough(by_id.get(company, {}), cust, by_id, asof)
        raw = 1.4 * c_avg + 0.5 * s_avg - 0.25
        direction = math.tanh(raw)
        confidence = clip(0.2 + 0.05 * min(len(cust) + len(supp), 10), 0.2, 0.75)
        why = (f"{len(cust)} customers ({c_tight} tight, {c_gained} gained content), "
               f"{len(supp)} suppliers; customer heat {c_avg:.2f}")
        if rt_n:
            why += f"; customers made {rt_n} statements on its chains (not scored)"
        out.append(Signal(NAME, ticker, direction, confidence, 20, why).clipped())
    return out
