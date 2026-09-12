"""Point-in-time learning targets used by both live scoring and backtests."""
from __future__ import annotations

import numpy as np
import pandas as pd

import config

BETA_WINDOW = 60
BETA_MIN_OBS = 40
BETA_MIN = 0.0
BETA_MAX = 3.0


def rolling_beta(closes: pd.DataFrame, window: int = BETA_WINDOW) -> pd.DataFrame:
    """Trailing beta to SOXX; each row uses returns available through that row only."""
    if config.BENCHMARK not in closes.columns:
        return pd.DataFrame(index=closes.index)
    rets = closes.pct_change(fill_method=None)
    bench = rets[config.BENCHMARK]
    cov = rets.rolling(window, min_periods=BETA_MIN_OBS).cov(bench)
    var = bench.rolling(window, min_periods=BETA_MIN_OBS).var()
    return cov.div(var.replace(0.0, np.nan), axis=0).clip(BETA_MIN, BETA_MAX)


def beta_at(betas: pd.DataFrame, ticker: str, asof) -> float:
    """Latest finite beta available on or before asof; conservative fallback is one."""
    if ticker not in betas.columns or betas.empty:
        return 1.0
    pos = betas.index.searchsorted(pd.Timestamp(asof), side="right") - 1
    if pos < 0:
        return 1.0
    value = betas[ticker].iloc[pos]
    return float(value) if np.isfinite(value) else 1.0


def latest_betas(closes: pd.DataFrame, tickers) -> dict[str, float]:
    betas = rolling_beta(closes)
    if betas.empty:
        return {ticker: 1.0 for ticker in tickers}
    asof = betas.index[-1]
    return {ticker: beta_at(betas, ticker, asof) for ticker in tickers}


def adjusted_return(ret: float, bench_ret: float, beta: float) -> float:
    return float(ret - beta * bench_ret)
