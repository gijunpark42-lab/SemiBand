"""Customer-momentum agent (round 44, 2026-09-17; Cohen & Frazzini 2008, "Economic links and predictable returns"): a
supplier's customers' recent stock returns predict the supplier's next month. The supply-chain graph gives the customers
(edges run supplier -> customer); prices give their trailing 21-day return relative to the benchmark. Point-in-time by
construction: only the closes in the context are read. Silent for names without a priced customer.
"""
import math

import numpy as np
import pandas as pd

import config
import market
from agents.base import Signal, clip
from agents.graph_pit import pit_map

NAME = "customer_momentum"
DAYS = 21
GAIN = 8.0
GATE_DAYS = 50                    # round 45: trend gate window on the benchmark
VOL_DAYS, VOL_TARGET_21D = 60, 0.10   # round 45: realised-vol scaling of the basket signal
MIN_PAIRS = 15                    # round 46: valid open/close pairs a name needs for the intraday measure, else close-to-close


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


def rel_returns_intraday(closes, opens, days=DAYS, fallback=None, min_pairs=MIN_PAIRS):
    """{ticker: compounded open->close return over the last `days` sessions of the closes frame minus the benchmark's}
    (round 46, Wang 2025: the overnight leg of connected-firm spillover reverses). Only rows of the closes index count, so a
    later open (the fill price) can never enter; a ticker with fewer than `min_pairs` valid pairs keeps its close-to-close
    value from `fallback`."""
    fallback = fallback or {}
    if opens is None or config.BENCHMARK not in closes.columns or config.BENCHMARK not in opens.columns or len(closes) <= days:
        return fallback
    idx = closes.index[-days:]
    o = opens.reindex(idx)

    def leg(t):
        if t not in o.columns:
            return None
        ratio = (closes.loc[idx, t] / o[t]).replace([np.inf, -np.inf], np.nan).dropna()
        ratio = ratio[ratio > 0]
        return float(ratio.prod() - 1) if len(ratio) >= min_pairs else None

    b = leg(config.BENCHMARK)
    if b is None:
        return fallback
    out = {}
    for t in closes.columns:
        r = leg(t)
        if r is not None:
            out[t] = r - b
        elif t in fallback:
            out[t] = fallback[t]
    return out


def trend_ok(closes):
    """False while the benchmark's last close is at or below its GATE_DAYS-session average (round 45 gate)."""
    if config.BENCHMARK not in closes.columns:
        return True
    b = closes[config.BENCHMARK].dropna()
    return len(b) < GATE_DAYS or float(b.iloc[-1]) > float(b.iloc[-GATE_DAYS:].mean())


def basket_vol(closes, linked, days=VOL_DAYS):
    """Realised vol of the linked basket's mean daily return relative to the benchmark, over `days` sessions, expressed per
    21 sessions; None when the history is too short."""
    cols = [t for t in linked if t in closes.columns]
    if not cols or config.BENCHMARK not in closes.columns:
        return None
    daily = closes[cols].pct_change().mean(axis=1) - closes[config.BENCHMARK].pct_change()
    daily = daily.dropna().iloc[-days:]
    if len(daily) < 40:
        return None
    return float(daily.std() * math.sqrt(21))


def signals(universe, ctx, side, name):
    closes = ctx["closes"]
    if config.MOMENTUM_TREND_GATE and not trend_ok(closes):
        return []
    rel = rel_returns(closes)
    intraday = False
    if config.MOMENTUM_INTRADAY:                      # round 46: the replay hands the opens in; live fetches them (no cache)
        opens = ctx.get("opens")
        if opens is None:
            opens = market.opens(list(closes.columns), 120)
        rel, intraday = rel_returns_intraday(closes, opens, fallback=rel), True
    links = _links(universe, side)
    out = []
    for ticker, linked in links.items():
        vals = [rel[t] for t in linked if t in rel]
        if not vals:
            continue
        avg = sum(vals) / len(vals)
        scale = 1.0
        if config.MOMENTUM_VOL_SCALE:
            vol = basket_vol(closes, [t for t in linked if t in rel])
            if vol:
                scale = min(max(VOL_TARGET_21D / vol, 0.25), 2.0)
        direction = math.tanh(GAIN * avg * scale)
        confidence = clip(0.3 + 0.05 * len(vals), 0.3, 0.7)
        label = "customers" if side == "customers" else "suppliers"
        out.append(Signal(name, ticker, direction, confidence, 20,
                          f"{len(vals)} {label}, {DAYS}d return {avg * 100:+.1f}% vs {config.BENCHMARK}" + (f" (vol scale {scale:.2f})" if scale != 1.0 else "") + (" (intraday)" if intraday else "")).clipped())
    return out


def run(universe: dict, ctx: dict) -> list[Signal]:
    return signals(universe, ctx, "customers", NAME)
