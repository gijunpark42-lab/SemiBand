"""Macro agent — the market regime, applied through each name's beta.

A regime score in [-1, +1] is built from free market data: SOXX trend,
SPY trend, VIX level, and the 20-day move in the 10-year yield. A regime
signal that is identical for every stock cannot beat SOXX (it moves with
SOXX), so the agent expresses it through beta: in risk-on regimes high-beta
names get a positive direction and low-beta names a negative one, and the
reverse in risk-off. Free, deterministic, one shared data pull per day.
"""
import math

import pandas as pd

import config
import market
from agents.base import Signal, clip

NAME = "macro"
EXTRA = ["SPY", "^VIX", "^TNX"]


def _trend(series: pd.Series, n: int) -> float:
    s = series.dropna()
    if len(s) < n:
        return 0.0
    return 1.0 if s.iloc[-1] > s.iloc[-n:].mean() else -1.0


def regime(closes: pd.DataFrame) -> tuple[float, str]:
    soxx = closes[config.BENCHMARK]
    score = 0.4 * _trend(soxx, 50) + 0.3 * _trend(closes["SPY"], 200)
    why = [f"SOXX {'above' if _trend(soxx, 50) > 0 else 'below'} 50d",
           f"SPY {'above' if _trend(closes['SPY'], 200) > 0 else 'below'} 200d"]
    vix = closes["^VIX"].dropna()
    if len(vix):
        v = float(vix.iloc[-1])
        score += 0.3 if v < 18 else (-0.3 if v > 25 else 0.0)
        why.append(f"VIX {v:.0f}")
    tnx = closes["^TNX"].dropna()
    if len(tnx) > 21:
        d = float(tnx.iloc[-1] - tnx.iloc[-21]) / 10  # ^TNX is yield x 10
        if d > 0.30:
            score -= 0.2
            why.append(f"10y +{d:.2f}pt/20d")
        elif d < -0.30:
            score += 0.1
            why.append(f"10y {d:.2f}pt/20d")
    # Optional FRED inputs (free key): yield-curve slope and financial conditions.
    t10, t2 = market.fred_latest("DGS10"), market.fred_latest("DGS2")
    if t10 and t2:
        slope = t10["latest"] - t2["latest"]
        if slope < 0:
            score -= 0.1
            why.append(f"curve inverted {slope:+.2f}")
    nfci = market.fred_latest("NFCI")
    if nfci:
        if nfci["latest"] > 0:
            score -= 0.2
            why.append(f"NFCI tight {nfci['latest']:+.2f}")
        elif nfci["latest"] < -0.4:
            score += 0.1
            why.append(f"NFCI loose {nfci['latest']:+.2f}")
    return clip(score, -1, 1), ", ".join(why)


def run(universe: dict, ctx: dict) -> list[Signal]:
    closes: pd.DataFrame = ctx["closes"]
    if any(c not in closes.columns for c in EXTRA):
        closes = market.closes(list(universe) + [config.BENCHMARK] + EXTRA)
    r, why = regime(closes)
    hist, asof = ctx.get("hist"), ctx.get("asof_ts")   # backtest fast path: precomputed (name, SOXX) return pairs
    bench_ret = closes[config.BENCHMARK].pct_change() if hist is None else None
    out = []
    for ticker in universe:
        if hist is not None:
            h = hist.get(ticker)
            if h is None or "pair" not in h:
                continue
            pair = h["pair"].loc[:asof].iloc[-60:]
        else:
            if ticker not in closes.columns:
                continue
            rets = closes[ticker].pct_change()
            pair = pd.concat([rets, bench_ret], axis=1).dropna().iloc[-60:]
        if len(pair) < 40:
            continue
        cov = pair.cov().iloc[0, 1]
        var = pair.iloc[:, 1].var()
        beta = float(cov / var) if var else 1.0
        direction = math.tanh(r * (beta - 1.0) * 1.5 + r * 0.3)
        confidence = clip(0.3 + 0.3 * abs(r), 0.3, 0.6)
        out.append(Signal(NAME, ticker, direction, confidence, 10,
                          f"regime {r:+.2f} ({why}); beta {beta:.2f} vs {config.BENCHMARK}").clipped())
    return out
