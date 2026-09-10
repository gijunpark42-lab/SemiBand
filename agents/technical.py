"""Technical agent — price momentum relative to the benchmark, plus trend.

Free and deterministic. Uses the closes DataFrame the cycle already fetched.
"""
import math

import pandas as pd

import config
from agents.base import Signal, clip

NAME = "technical"


def _rsi(series: pd.Series, n=14):
    delta = series.diff()
    up = delta.clip(lower=0).rolling(n).mean()
    down = (-delta.clip(upper=0)).rolling(n).mean()
    rs = up / down.replace(0, float("nan"))
    return float((100 - 100 / (1 + rs)).iloc[-1])


def run(universe: dict, ctx: dict) -> list[Signal]:
    closes: pd.DataFrame = ctx["closes"]
    bench = closes[config.BENCHMARK].dropna()
    b20 = bench.iloc[-1] / bench.iloc[-21] - 1
    b60 = bench.iloc[-1] / bench.iloc[-61] - 1
    out = []
    for ticker in universe:
        if ticker not in closes.columns:
            continue
        c = closes[ticker].dropna()
        if len(c) < 70:
            continue
        last = float(c.iloc[-1])
        rel20 = float(c.iloc[-1] / c.iloc[-21] - 1) - b20
        rel60 = float(c.iloc[-1] / c.iloc[-61] - 1) - b60
        sma50 = float(c.iloc[-50:].mean())
        sma200 = float(c.iloc[-200:].mean()) if len(c) >= 200 else sma50
        rsi = _rsi(c)

        raw = 4 * rel20 + 2 * rel60
        raw += 0.3 if last > sma50 else -0.3
        raw += 0.2 if last > sma200 else -0.2
        if rsi > 75:
            raw -= 0.4
        elif rsi < 25:
            raw += 0.4
        direction = math.tanh(raw)
        confidence = clip(0.3 + min(abs(rel20) * 8, 0.5), 0.2, 0.9)
        why = (f"rel20 {rel20*100:+.1f}% rel60 {rel60*100:+.1f}% vs {config.BENCHMARK}; "
               f"{'above' if last > sma50 else 'below'} 50d, {'above' if last > sma200 else 'below'} 200d; RSI {rsi:.0f}")
        out.append(Signal(NAME, ticker, direction, confidence, 10, why).clipped())
    return out
