"""Supply-chain agent — rule-based, free, deterministic.

Reads the earnings-ai graph (read-only) and turns a company's position into a
direction: does it GAIN or LOSE content across accelerator generation
transitions, is its capacity sold out, how fresh is its own guidance.
No LLM here on purpose: this agent is the "what the map says" baseline that
the LLM agents are measured against.
"""
import csv
import functools
import json
import math
import re
from datetime import date, datetime

import config
from agents.base import Signal, clip

NAME = "supply_chain"

GEN_SCORE = {"gained": 0.8, "retained": 0.3, "lost": -0.8}
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


def _metrics_score(m: dict, today: date) -> tuple[float, list[str]]:
    """+/- from the curated text: sold-out supply and raised guidance are bullish,
    cuts and delays bearish; halved when the source call is older than 120 days."""
    if not m:
        return 0.0, []
    text = " ".join(str(m.get(k) or "") for k in ("guidance", "supply_status", "backlog_or_b2b")).lower()
    pos = sum(1 for w in _POSITIVE if w in text)
    neg = sum(1 for w in _NEGATIVE if w in text)
    score = 0.2 * min(pos, 3) - 0.25 * min(neg, 3)
    tags = []
    if pos:
        tags.append(f"curated: {pos} bullish marker{'s' if pos > 1 else ''}")
    if neg:
        tags.append(f"curated: {neg} bearish marker{'s' if neg > 1 else ''}")
    asof = m.get("asof")
    try:
        if asof and (today - date.fromisoformat(asof)).days > 120:
            score *= 0.5
            tags.append(f"curated data {asof} (old)")
    except ValueError:
        pass
    return score, tags


def run(universe: dict, ctx: dict) -> list[Signal]:
    """universe = {ticker: company_name}."""
    graph, exposure, full_cap = _load()
    metrics = curated_metrics()
    by_id = {n["id"]: n for n in graph["nodes"]}
    today = date.today()
    out = []
    for ticker, company in universe.items():
        node = by_id.get(company)
        exp = (exposure.get("companies") or {}).get(company)
        if not node or not exp:
            continue
        score, why = _metrics_score(metrics.get(company), today)

        gens = exp.get("generations") or {}
        for key, verdict in gens.items():
            score += GEN_SCORE.get(verdict, 0)
            why.append(f"{key}:{verdict}")

        topics = exp.get("topics") or {}
        tight = topics.get("supply_tightness", 0)
        if tight:
            score += 0.15 * min(tight, 4)
            why.append(f"tightness x{tight}")
        launches = topics.get("product_launches", 0)
        if launches:
            score += 0.05 * min(launches, 3)

        when = full_cap.get(company)
        if company in full_cap:
            fresh = when and (today - when).days <= 150
            score += 0.5 if fresh else 0.2
            why.append("capacity sold out" + ("" if fresh else " (old)"))

        days = exp.get("days_since")
        if isinstance(days, (int, float)):
            if days <= 45:
                score += 0.2
            elif days <= 90:
                score += 0.1
            elif days > 180:
                score -= 0.3
                why.append(f"stale {int(days)}d")

        signals = exp.get("signals") or 0
        confidence = clip(0.25 + 0.05 * min(signals, 10) + (0.2 if isinstance(days, (int, float)) and days <= 90 else 0)
                          + (0.15 if gens else 0), 0.1, 0.9)
        direction = math.tanh(score)
        out.append(Signal(NAME, ticker, direction, confidence, 20,
                          "; ".join(why) or "in map, no strong markers").clipped())
    return out
