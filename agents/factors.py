"""Cross-asset factor agents: how exposed each stock is to one market factor beyond SOXX, times where that factor is heading.

One agent per factor (factor_oil, factor_fed, ...), so the stacking learner weighs each voice on its own record (user
2026-09-15: an investor weighs oil, memory prices, inflation, rate expectations, credit and the dollar). For each stock, a
regression of its daily returns on SOXX and the factor over the last WINDOW sessions gives its loading on the factor net of
SOXX; loadings are standardised across the universe. The factor's signal is its position against its 50-day average plus its
20-day move scaled by that move's one-year spread, squashed to [-1, 1]. direction = tanh(z_loading x signal): a stock that
gains when oil rises leans positive while oil trends up. Free, deterministic, daily closes only.
"""
import math

import numpy as np

import config
import market
from agents.base import Signal, clip

WINDOW = 120          # sessions behind each loading
MIN_OBS = 80          # complete sessions a stock needs inside the window
HISTORY = 320         # sessions of closes the agent reads (signal needs 270)
MEMORY = ["MU", "WDC", "000660.KS", "005930.KS"]

# factor -> (label, kind, symbols); kind "price" uses percent changes, "rate" uses level changes
FACTORS = {
    "oil": ("WTI crude", "price", ["CL=F"]),
    "fed": ("fed funds futures implied rate", "rate", ["ZQ=F"]),
    "long_rates": ("10-year Treasury yield", "rate", ["^TNX"]),
    "inflation": ("TIPS vs 7-10y Treasuries", "price", ["TIP", "IEF"]),
    "credit": ("high yield vs 7-10y Treasuries", "price", ["HYG", "IEF"]),
    "dollar": ("US dollar index", "price", ["DX-Y.NYB"]),
    "memory": ("memory makers vs SOXX", "price", MEMORY),
    "copper": ("copper", "price", ["HG=F"]),
}
SYMBOLS = sorted({s for _, _, syms in FACTORS.values() for s in syms})


def _us_calendar(closes):
    return closes.loc[closes[config.BENCHMARK].notna()].iloc[-HISTORY:]


def level(name, closes):
    """The factor's level on the SOXX calendar, or None when a needed symbol is missing."""
    c = _us_calendar(closes)
    need = FACTORS[name][2]
    if any(s not in c.columns for s in need):
        return None
    px = c[need].ffill()
    if name == "fed":
        return 100.0 - px["ZQ=F"]
    if name in ("inflation", "credit"):
        return px[need[0]] / px["IEF"]
    if name == "memory":
        basket = (1 + px.pct_change(fill_method=None).mean(axis=1, skipna=True).fillna(0.0)).cumprod()
        return basket / c[config.BENCHMARK]
    return px[need[0]]


def signal(lvl, kind):
    """Where the factor is heading, in [-1, 1]; None without a year of history."""
    s = lvl.dropna()
    if len(s) < 270:
        return None
    trend = 1.0 if s.iloc[-1] > s.iloc[-50:].mean() else -1.0
    moves = (s - s.shift(20)) if kind == "rate" else (s / s.shift(20) - 1)
    spread = float(moves.iloc[-250:].std())
    z = float(moves.iloc[-1]) / spread if spread > 0 else 0.0
    return clip(0.5 * trend + 0.5 * math.tanh(z), -1, 1)


def loadings(name, closes, tickers):
    """{ticker: loading on the factor net of SOXX}: OLS of daily returns on SOXX and the factor over the last WINDOW sessions,
    complete cases per ticker."""
    lvl = level(name, closes)
    if lvl is None:
        return {}
    c = _us_calendar(closes)
    kind = FACTORS[name][1]
    f = (lvl.diff() if kind == "rate" else lvl.pct_change(fill_method=None)).iloc[-WINDOW:].to_numpy(dtype=float)
    m = c[config.BENCHMARK].pct_change(fill_method=None).iloc[-WINDOW:].to_numpy(dtype=float)
    cols = [t for t in tickers if t in c.columns]
    if not cols:
        return {}
    y_all = c[cols].iloc[-(WINDOW + 1):].pct_change(fill_method=None).iloc[1:].to_numpy(dtype=float)
    if len(y_all) != len(f):
        return {}
    ok = ~np.isnan(y_all) & ~np.isnan(m)[:, None] & ~np.isnan(f)[:, None]
    n = ok.sum(axis=0)

    def centred(a):
        a = np.where(ok, a, 0.0)
        return np.where(ok, a - a.sum(axis=0) / np.maximum(n, 1), 0.0)

    y = centred(y_all)
    mm = centred(np.broadcast_to(m[:, None], y_all.shape))
    ff = centred(np.broadcast_to(f[:, None], y_all.shape))
    s_mm, s_ff, s_mf = (mm * mm).sum(0), (ff * ff).sum(0), (mm * ff).sum(0)
    s_ym, s_yf = (y * mm).sum(0), (y * ff).sum(0)
    det = s_mm * s_ff - s_mf ** 2
    good = (n >= MIN_OBS) & (np.abs(det) > 1e-18)
    beta = np.where(good, (s_yf * s_mm - s_ym * s_mf) / np.where(good, det, 1.0), np.nan)
    return {t: float(b) for t, b in zip(cols, beta) if np.isfinite(b)}


def make_run(factor, agent_name):
    label, kind, need = FACTORS[factor]

    def run(universe: dict, ctx: dict) -> list[Signal]:
        closes = ctx["closes"]
        if any(s not in closes.columns for s in need + [config.BENCHMARK]):
            if "asof" in ctx:                     # a replay passes every symbol it has; never download mid-replay
                return []
            closes = market.closes(list(universe) + [config.BENCHMARK] + SYMBOLS)
        lvl = level(factor, closes)
        sig = signal(lvl, kind) if lvl is not None else None
        if not sig:
            return []
        loads = loadings(factor, closes, list(universe))
        if len(loads) < 20:
            return []
        values = np.array(list(loads.values()))
        mu, sd = float(values.mean()), float(values.std())
        if sd <= 0:
            return []
        out = []
        for ticker, b in loads.items():
            z = clip((b - mu) / sd, -3, 3)
            out.append(Signal(agent_name, ticker, math.tanh(z * sig), clip(0.2 + 0.15 * abs(z) * abs(sig), 0.2, 0.6), 20,
                              f"{label}: signal {sig:+.2f}, loading z {z:+.1f} vs universe").clipped())
        return out

    return run
