"""Customer-momentum agent (round 44, 2026-09-17; Cohen & Frazzini 2008, "Economic links and predictable returns"): a
supplier's customers' recent stock returns predict the supplier's next month. The supply-chain graph gives the customers
(edges run supplier -> customer); prices give their trailing 21-day return relative to the benchmark. Point-in-time by
construction: only the closes in the context are read. Silent for names without a priced customer.
"""
import math

import pandas as pd

import config
from agents.base import Signal, clip
from agents.graph_pit import pit_map

NAME = "customer_momentum"
DAYS = 21
GAIN = 8.0


def _links(universe, side):
    """{ticker: [linked tickers]} for side "customers" or "suppliers", restricted to universe names."""
    pit = pit_map()
    by_company = {company: ticker for ticker, company in universe.items()}
    table = pit.customers if side == "customers" else pit.suppliers
    out = {}
    for ticker, company in universe.items():
        linked = [by_company[c] for c in table.get(company, ()) if c in by_company and by_company[c] != ticker]
        if linked:
            out[ticker] = linked
    return out


def rel_returns(closes: pd.DataFrame, days=DAYS):
    """{ticker: trailing return over `days` sessions minus the benchmark's}, from the last row of the frame."""
    if config.BENCHMARK not in closes.columns:
        return {}
    bench = closes[config.BENCHMARK].dropna()
    if len(bench) <= days:
        return {}
    b = float(bench.iloc[-1] / bench.iloc[-days - 1] - 1)
    out = {}
    for t in closes.columns:
        c = closes[t].dropna()
        if len(c) > days and float(c.iloc[-days - 1]) > 0:
            out[t] = float(c.iloc[-1] / c.iloc[-days - 1] - 1) - b
    return out


def signals(universe, ctx, side, name):
    closes = ctx["closes"]
    rel = rel_returns(closes)
    links = _links(universe, side)
    out = []
    for ticker, linked in links.items():
        vals = [rel[t] for t in linked if t in rel]
        if not vals:
            continue
        avg = sum(vals) / len(vals)
        direction = math.tanh(GAIN * avg)
        confidence = clip(0.3 + 0.05 * len(vals), 0.3, 0.7)
        label = "customers" if side == "customers" else "suppliers"
        out.append(Signal(name, ticker, direction, confidence, 20,
                          f"{len(vals)} {label}, {DAYS}d return {avg * 100:+.1f}% vs {config.BENCHMARK}").clipped())
    return out


def run(universe: dict, ctx: dict) -> list[Signal]:
    return signals(universe, ctx, "customers", NAME)
