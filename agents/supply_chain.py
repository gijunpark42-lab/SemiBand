"""Supply-chain agent — rule-based, free, deterministic.

Reads the earnings-ai graph (read-only) and turns a company's position into a
direction: does it GAIN or LOSE content across accelerator generation
transitions, is its capacity sold out, how fresh is its own guidance.
No LLM here on purpose: this agent is the "what the map says" baseline that
the LLM agents are measured against.

Since 2026-09-16 the score is the replay's point-in-time formula (agents/graph_pit.py: the company's own dated
statements, its full-capacity flag and the age of its latest call) with asof = today. The cumulative exposure counts
and curated markers it scored before are undated and put its live signals at twice the replay's level (+0.55 vs
+0.26 mean direction), so the learner's weights, fitted on replay rows, did not apply to them.
"""
import csv
import functools
import json
import re
from datetime import date, datetime

import config
from agents.base import Signal, clip

NAME = "supply_chain"

_DATE = re.compile(r"\((\d{2})-(\d{2})-(\d{4})\)")


@functools.lru_cache(maxsize=1)
def _load():
    root = config.EARNINGS_AI_DIR
    graph = json.loads((root / "graph" / "merged_graph.json").read_text(encoding="utf-8"))
    exposure = json.loads((root / "graph" / "exposure.json").read_text(encoding="utf-8"))
    full_cap = {}
    path = root / "quant" / "signal_full_capacity.csv"
    if path.exists():
        with path.open(encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if row.get("flag", "").strip() == "1":
                    m = _DATE.search(row.get("source", ""))
                    when = date(int(m.group(3)), int(m.group(1)), int(m.group(2))) if m else None
                    full_cap[row["company"].strip()] = when
    return graph, exposure, full_cap


@functools.lru_cache(maxsize=1)
def curated_metrics() -> dict:
    """earnings-ai's hand-curated screener baseline (company_metrics.json): per company,
    latest revenue growth, guidance, backlog, supply status, next catalyst, as-of date.
    Read-only; the file is the user's, never written here."""
    path = config.EARNINGS_AI_DIR / "company_metrics.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if k != "_schema" and isinstance(v, dict)}


_POSITIVE = ("sold out", "sold-out", "exceeds supply", "exceed supply", "allocation", "constrain",
             "raised", "raise", "record", "fully booked", "capacity limiting")
_NEGATIVE = ("cut", "lower", "reduced", "weak", "decline", "inventory correction", "pushout", "push-out", "delay")


def run(universe: dict, ctx: dict) -> list[Signal]:
    """universe = {ticker: company_name}. The replay's point-in-time formula with asof = today (or ctx['asof']); a
    company with no dated statement yet is silent, exactly as in the backtest (agents/graph_pit.py)."""
    from agents.graph_pit import pit_map
    pit = pit_map()
    asof = ctx.get("asof") or date.today()
    return [s for s in (pit.supply_chain(ticker, company, asof) for ticker, company in universe.items()) if s is not None]
