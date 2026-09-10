"""Neighbors agent — the map one hop out.

`supply_chain` looks at what the company itself said. This agent looks at
who it sells to and buys from: if its customers just reported sold-out
capacity, gained content in a generation transition, or spoke recently,
demand is pulling on this name. Customers count more than suppliers
(demand pull > supply push). Free, deterministic, reads the graph only.
"""
import math

from agents.base import Signal, clip
from agents.supply_chain import _load

NAME = "neighbors"


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
        raw = 1.4 * c_avg + 0.5 * s_avg - 0.25
        direction = math.tanh(raw)
        confidence = clip(0.2 + 0.05 * min(len(cust) + len(supp), 10), 0.2, 0.75)
        why = (f"{len(cust)} customers ({c_tight} tight, {c_gained} gained content), "
               f"{len(supp)} suppliers; customer heat {c_avg:.2f}")
        out.append(Signal(NAME, ticker, direction, confidence, 20, why).clipped())
    return out
