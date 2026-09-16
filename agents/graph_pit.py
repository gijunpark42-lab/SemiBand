"""The graph agents' one formula: each company's dated earnings-call statements, queried "as of" a date.

The backtest replays it day by day (PointInTimeMap.supply_chain / .neighbors with asof = the simulated day). Since
2026-09-16 the live agents call the same map with asof = today, so live rows and the warm-start rows the learner was
fitted on sit on one scale. Before that the live agents scored today's cumulative exposure counts (generations,
tightness totals, launches, curated markers), which put their directions at about twice the replay's level (+0.55 vs
+0.26 for supply_chain, 99% positive vs 83%) and turned the learner's negative direction-only weights into a constant
offset of about -0.12 on every name's conviction (review, 2026-09-16).
"""
import functools
import math
import re
from datetime import date, timedelta

from agents.base import Signal, clip
from agents.supply_chain import _POSITIVE, _load

_DATE = re.compile(r"\((\d{2})-(\d{2})-(\d{4})\)")
_EXPAND = ("expand", "ramp", "increase", "double", "accelerat", "record", "sold out", "constrain", "exceed")


def _label_date(label):
    m = _DATE.search(label or "")
    return date(int(m.group(3)), int(m.group(1)), int(m.group(2))) if m else None


class PointInTimeMap:
    """Dated earnings-call signals per company, so the map can be queried 'as of t'."""

    def __init__(self):
        graph, exposure, full_cap = _load()
        self.signals = {}          # company -> [(date, text)]
        for n in graph["nodes"]:
            rows = []
            for q in n.get("quarterly_data") or []:
                d = _label_date(q.get("quarter"))
                if d:
                    rows.append((d, (q.get("signal") or "").lower()))
            rows.sort()
            self.signals[n["id"]] = rows
        self.full_cap = full_cap   # company -> date flagged
        self.chains = {n["id"]: set(n.get("chains") or []) for n in graph["nodes"]}
        self.signals_chain = {}    # company -> [(date, text, chain)]
        for n in graph["nodes"]:
            rows = []
            for q in n.get("quarterly_data") or []:
                d = _label_date(q.get("quarter"))
                if d:
                    rows.append((d, (q.get("signal") or "").lower(), q.get("chain")))
            self.signals_chain[n["id"]] = rows
        self.customers, self.suppliers = {}, {}
        for e in graph["edges"]:
            self.customers.setdefault(e["source"], set()).add(e["target"])
            self.suppliers.setdefault(e["target"], set()).add(e["source"])

    def recent(self, company, asof, days):
        return [(d, t) for d, t in self.signals.get(company, []) if asof - timedelta(days=days) <= d <= asof]

    def supply_chain(self, ticker, company, asof):
        rec = self.recent(company, asof, 120)
        allrows = [d for d, _ in self.signals.get(company, []) if d <= asof]
        if not allrows:
            return None
        tight = sum(1 for _, t in rec if any(w in t for w in _POSITIVE))
        days_since = (asof - max(allrows)).days
        score = 0.15 * min(tight, 4)
        fc = self.full_cap.get(company)
        if fc and fc <= asof:
            score += 0.5 if (asof - fc).days <= 150 else 0.2
        if days_since <= 45:
            score += 0.2
        elif days_since <= 90:
            score += 0.1
        elif days_since > 180:
            score -= 0.3
        confidence = clip(0.25 + 0.05 * min(len(rec), 10) + (0.2 if days_since <= 90 else 0), 0.1, 0.9)
        return Signal("supply_chain", ticker, math.tanh(score), confidence, 20,
                      f"pit: {tight} tight markers in 120d, latest {days_since}d old")

    def neighbors(self, ticker, company, asof):
        cust, supp = self.customers.get(company, set()), self.suppliers.get(company, set())
        if not cust and not supp:
            return None
        # No neighbour has said anything dated on or before this day (the graph's statements start 2025-10):
        # silent, like supply_chain — otherwise every name with edges gets the same tanh(-0.25) for 14 months
        # and the learner fits that constant (RESEARCH.md, "data coverage").
        if not any(d <= asof for nb in cust | supp for d, _ in self.signals.get(nb, [])):
            return None

        def heat(nb):
            rec = self.recent(nb, asof, 90)
            h = 0.0
            if any(any(w in t for w in _POSITIVE) for _, t in rec):
                h += 0.5
            if rec:
                h += 0.2
            return min(h, 1.0)
        c = [heat(n) for n in cust]
        s = [heat(n) for n in supp]
        c_avg = sum(c) / len(c) if c else 0.0
        s_avg = sum(s) / len(s) if s else 0.0
        # read-through: customers' dated statements on the chains this company sells into
        my_chains = self.chains.get(company, set())
        hits, n_rt = 0, 0
        for nb in cust:
            for d, t, ch in self.signals_chain.get(nb, []):
                if asof - timedelta(days=120) <= d <= asof and ch in my_chains:
                    n_rt += 1
                    if any(w in t for w in _POSITIVE) or any(w in t for w in _EXPAND):
                        hits += 1
        rt = 0.5 * hits / n_rt if n_rt >= 3 else 0.0   # measured only; tested 2026-09-10 and rejected from the score
        direction = math.tanh(1.4 * c_avg + 0.5 * s_avg - 0.25)
        confidence = clip(0.2 + 0.05 * min(len(cust) + len(supp), 10), 0.2, 0.75)
        return Signal("neighbors", ticker, direction, confidence, 20, f"pit: customer heat {c_avg:.2f}, read-through {rt:+.2f}")


@functools.lru_cache(maxsize=1)
def pit_map() -> PointInTimeMap:
    """One map per process, built from the graph _load() reads (config.EARNINGS_AI_DIR, set before the first call)."""
    return PointInTimeMap()
