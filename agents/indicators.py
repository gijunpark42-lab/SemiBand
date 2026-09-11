"""Indicators shared by the rule agents.

rsi() is memoised per (ticker, last date, length) so two agents asking on the same day compute it once.
The backtest goes further: PRECOMPUTED[ticker] holds the RSI series over the whole history, computed
once with exactly the same pandas operations. diff / clip / rolling-mean are causal, so the value at row t
is bit-identical to computing on the prefix ending at t, which is what the live agent does."""
import pandas as pd

_RSI = {}
PRECOMPUTED = {}   # ticker -> pd.Series of RSI indexed by date (set by backtest.py; empty live)


def rsi_series(series: pd.Series, n=14) -> pd.Series:
    delta = series.diff()
    up = delta.clip(lower=0).rolling(n).mean()
    down = (-delta.clip(upper=0)).rolling(n).mean()
    rs = up / down.replace(0, float("nan"))
    return 100 - 100 / (1 + rs)


def rsi(series: pd.Series, n=14) -> float:
    pre = PRECOMPUTED.get(series.name) if n == 14 else None
    if pre is not None:
        return float(pre.loc[series.index[-1]])
    key = (series.name, series.index[-1], len(series), n)
    v = _RSI.get(key)
    if v is None:
        v = float(rsi_series(series, n).iloc[-1])
        if len(_RSI) > 5000:
            _RSI.clear()
        _RSI[key] = v
    return v
