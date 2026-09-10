"""Risk agent — the brake.

Speaks only when a name is unusually risky: realized 20-day volatility far
above the universe median, or a deep 60-day drawdown. Then it leans
negative with confidence proportional to how extreme. Silent otherwise, so
it never dilutes calm names. Free, deterministic.
"""
import math

import pandas as pd

import config
from agents.base import Signal, clip

NAME = "risk"
VOL_RATIO_TRIGGER = 1.4
DRAWDOWN_TRIGGER = -0.25          # own 60-day drawdown at least this deep ...
EXCESS_DD_TRIGGER = -0.15         # ... AND this much worse than SOXX's own drawdown (a sector-wide slide is not name risk)


def _drawdown(series: pd.Series) -> float:
    return float(series.iloc[-1] / series.iloc[-60:].max() - 1)


def run(universe: dict, ctx: dict) -> list[Signal]:
    closes: pd.DataFrame = ctx["closes"]
    bench_dd = _drawdown(closes[config.BENCHMARK].dropna())
    vols, dds = {}, {}
    for ticker in universe:
        if ticker not in closes.columns:
            continue
        c = closes[ticker].dropna()
        if len(c) < 65:
            continue
        rets = c.pct_change().dropna()
        vols[ticker] = float(rets.iloc[-20:].std() * math.sqrt(252))
        dds[ticker] = _drawdown(c)
    if not vols:
        return []
    median = sorted(vols.values())[len(vols) // 2] or 1e-9
    out = []
    for ticker, vol in vols.items():
        ratio = vol / median
        dd = dds[ticker]
        excess = dd - bench_dd
        severity = 0.0
        why = []
        if ratio >= VOL_RATIO_TRIGGER:
            severity += min((ratio - 1) * 0.6, 0.6)
            why.append(f"20d vol {vol*100:.0f}% = {ratio:.1f}x universe median")
        if dd <= DRAWDOWN_TRIGGER and excess <= EXCESS_DD_TRIGGER:
            severity += min((-excess - 0.10) * 1.5, 0.5)
            why.append(f"60d drawdown {dd*100:.0f}% vs {config.BENCHMARK} {bench_dd*100:.0f}%")
        if severity == 0:
            continue
        direction = -clip(severity, 0.1, 1.0)
        confidence = clip(0.3 + severity * 0.6, 0.3, 0.85)
        out.append(Signal(NAME, ticker, direction, confidence, 10, "; ".join(why)).clipped())
    return out
