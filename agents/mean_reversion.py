"""Mean-reversion agent — fades short-term overextension.

Deliberately the opposite temperament of `technical`: where that agent
chases 20/60-day strength, this one leans against a 5-day spike or dump
relative to SOXX and against a stretched 20-day z-score. Over time the
weights tell us which temperament the current market rewards.
"""
import math

import pandas as pd

import config
from agents.base import Signal, clip

NAME = "mean_reversion"


from agents.indicators import rsi as _rsi


def run(universe: dict, ctx: dict) -> list[Signal]:
    closes: pd.DataFrame = ctx["closes"]
    bench = closes[config.BENCHMARK].dropna()
    b5 = bench.iloc[-1] / bench.iloc[-6] - 1
    out = []
    for ticker in universe:
        if ticker not in closes.columns:
            continue
        c = closes[ticker].dropna()
        if len(c) < 40:
            continue
        rel5 = float(c.iloc[-1] / c.iloc[-6] - 1) - b5
        window = c.iloc[-20:]
        std = float(window.std())
        z = float((c.iloc[-1] - window.mean()) / std) if std > 0 else 0.0
        rsi = _rsi(c)
        raw = -math.tanh(rel5 * 12) * 0.6 - math.tanh(z / 2) * 0.4
        if rsi > 70:
            raw -= 0.2
        elif rsi < 30:
            raw += 0.2
        direction = clip(raw, -1, 1)
        confidence = clip(0.2 + min(abs(rel5) * 6 + abs(z) * 0.08, 0.6), 0.2, 0.8)
        out.append(Signal(NAME, ticker, direction, confidence, 5,
                          f"5d rel {rel5*100:+.1f}% vs {config.BENCHMARK}, 20d z {z:+.1f}, RSI {rsi:.0f} → fade").clipped())
    return out
