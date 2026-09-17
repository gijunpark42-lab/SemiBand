"""Technical agent — price momentum relative to the benchmark, plus trend.

Free and deterministic. Uses the closes DataFrame the cycle already fetched.
"""
import math

import numpy as np
import pandas as pd

import config
from agents.base import Signal, clip

NAME = "technical"


from agents.indicators import rsi as _rsi


def run(universe: dict, ctx: dict) -> list[Signal]:
    closes: pd.DataFrame = ctx["closes"]
    bench = closes[config.BENCHMARK].dropna()
    b20 = bench.iloc[-1] / bench.iloc[-21] - 1
    b60 = bench.iloc[-1] / bench.iloc[-61] - 1
    residual = bool(config.TECHNICAL_RESIDUAL)          # round 40: beta-adjusted (residual) momentum
    bench_ret = bench.pct_change() if residual else None
    out = []
    for ticker in universe:
        if ticker not in closes.columns:
            continue
        c = closes[ticker].dropna()
        if len(c) < 70:
            continue
        last = float(c.iloc[-1])
        beta = 1.0
        if residual:
            pair = pd.concat([c.pct_change(), bench_ret], axis=1).dropna().iloc[-60:]
            pair = pair[np.isfinite(pair.to_numpy()).all(axis=1)]   # a non-positive price makes an inf return: drop the pair, never a NaN beta
            var = float(pair.iloc[:, 1].var()) if len(pair) >= 40 else 0.0
            beta = float(pair.cov().iloc[0, 1] / var) if var and math.isfinite(var) else 1.0
            beta = min(max(beta, 0.0), 3.0) if math.isfinite(beta) else 1.0
        rel20 = float(c.iloc[-1] / c.iloc[-21] - 1) - beta * b20
        rel60 = float(c.iloc[-1] / c.iloc[-61] - 1) - beta * b60
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
        why = (f"rel20 {rel20*100:+.1f}% rel60 {rel60*100:+.1f}% vs {config.BENCHMARK}" + (f" (beta {beta:.2f})" if residual else "") + "; "
               f"{'above' if last > sma50 else 'below'} 50d, {'above' if last > sma200 else 'below'} 200d; RSI {rsi:.0f}")
        out.append(Signal(NAME, ticker, direction, confidence, 10, why).clipped())
    return out
