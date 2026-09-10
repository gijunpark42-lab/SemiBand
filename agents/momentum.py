"""Long-horizon momentum agent — the classic 12-1 factor, relative to SOXX.

Jegadeesh-Titman momentum: past 12-month return skipping the most recent
month (which reverses). Inside a single industry the effect is weaker but
still positive; it complements `technical` (20/60-day) and `mean_reversion`
(5-day) by looking at a much longer window. Free, deterministic.
"""
import math

import pandas as pd

import config
from agents.base import Signal, clip

NAME = "momentum"


def run(universe: dict, ctx: dict) -> list[Signal]:
    closes: pd.DataFrame = ctx["closes"]
    bench = closes[config.BENCHMARK].dropna()
    if len(bench) < 260:
        return []
    b12 = float(bench.iloc[-22] / bench.iloc[-253] - 1)
    b6 = float(bench.iloc[-22] / bench.iloc[-127] - 1)
    out = []
    for ticker in universe:
        if ticker not in closes.columns:
            continue
        c = closes[ticker].dropna()
        if len(c) < 260:
            continue
        rel12 = float(c.iloc[-22] / c.iloc[-253] - 1) - b12     # 12-1 month, vs SOXX
        rel6 = float(c.iloc[-22] / c.iloc[-127] - 1) - b6       # 6-1 month, vs SOXX
        direction = math.tanh(2.0 * rel12 + 1.0 * rel6)
        confidence = clip(0.3 + min(abs(rel12) * 1.5, 0.5), 0.3, 0.8)
        out.append(Signal(NAME, ticker, direction, confidence, 20,
                          f"12-1m {rel12*100:+.0f}%, 6-1m {rel6*100:+.0f}% vs {config.BENCHMARK}").clipped())
    return out
