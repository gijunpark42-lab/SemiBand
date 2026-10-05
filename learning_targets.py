"""Point-in-time learning targets used by both live scoring and backtests."""
from __future__ import annotations

import numpy as np
import pandas as pd

import config

BETA_WINDOW = 60
BETA_MIN_OBS = 40
BETA_MIN = 0.0
BETA_MAX = 3.0


def rolling_beta(closes: pd.DataFrame, window: int = BETA_WINDOW, estimator: str | None = None) -> pd.DataFrame:
    """Trailing beta to SOXX; each row uses returns available through that row only. estimator: "ols60" (the 60-day OLS) or
    "vasicek250" (round 57); None = config.BETA_ESTIMATOR."""
    if config.BENCHMARK not in closes.columns:
        return pd.DataFrame(index=closes.index)
    closes = closes.sort_index().loc[closes[config.BENCHMARK].notna()]
    if not closes.index.is_unique:
        raise ValueError("duplicate trading dates in beta price history")
    rets = closes.pct_change(fill_method=None)
    bench = rets[config.BENCHMARK]
    if (estimator or getattr(config, "BETA_ESTIMATOR", "ols60")) == "vasicek250":
        return _vasicek(rets, bench)
    cov = rets.rolling(window, min_periods=BETA_MIN_OBS).cov(bench)
    var = bench.rolling(window, min_periods=BETA_MIN_OBS).var()
    return cov.div(var.replace(0.0, np.nan), axis=0).replace([np.inf, -np.inf], np.nan).clip(BETA_MIN, BETA_MAX)


def _vasicek(rets: pd.DataFrame, bench: pd.Series, window: int = 250, min_obs: int = 120) -> pd.DataFrame:
    """Round 57 (Levi & Welch 2017): 250-day OLS beta shrunk toward the day's cross-sectional mean, each name by its own
    precision (Vasicek): w = v / (v + se^2), v = the cross-sectional variance of the raw betas net of the mean sampling
    variance. Point-in-time: every input on a row uses returns through that row only."""
    cov = rets.rolling(window, min_periods=min_obs).cov(bench)
    var_b = bench.rolling(window, min_periods=min_obs).var().replace(0.0, np.nan)
    var_i = rets.rolling(window, min_periods=min_obs).var()
    n = rets.notna().astype(float).rolling(window, min_periods=1).sum()
    raw = cov.div(var_b, axis=0).replace([np.inf, -np.inf], np.nan)
    resid = (var_i - raw.pow(2).mul(var_b, axis=0)).clip(lower=0.0)
    se2 = resid.div(n.mul(var_b, axis=0).replace(0.0, np.nan))
    stocks = [c for c in raw.columns if c != config.BENCHMARK and not str(c).startswith("^") and c != "SPY"]
    m = raw[stocks].mean(axis=1)
    v = (raw[stocks].var(axis=1) - se2[stocks].mean(axis=1)).clip(lower=1e-4)
    w = se2.rdiv(1.0).mul(v, axis=0)                                  # v / se2 ...
    w = w.div(w + 1.0)                                                # ... -> v / (v + se2)
    shrunk = raw.mul(w) + (1.0 - w).mul(m, axis=0)
    if config.BENCHMARK in shrunk.columns:
        shrunk[config.BENCHMARK] = 1.0
    return shrunk.clip(BETA_MIN, BETA_MAX)


def beta_at(betas: pd.DataFrame, ticker: str, asof, *, before=False) -> float:
    """Beta on the latest available session; before=True for pre-open live predictions."""
    if ticker not in betas.columns or betas.empty:
        return 1.0
    pos = betas.index.searchsorted(pd.Timestamp(asof), side="left" if before else "right") - 1
    if pos < 0:
        return 1.0
    value = betas[ticker].iloc[pos]
    return float(value) if np.isfinite(value) else 1.0


def latest_betas(closes: pd.DataFrame, tickers, prediction_date=None) -> dict[str, float]:
    betas = rolling_beta(closes)
    if betas.empty:
        return {ticker: 1.0 for ticker in tickers}
    asof = prediction_date if prediction_date is not None else betas.index[-1]
    return {ticker: beta_at(betas, ticker, asof, before=prediction_date is not None) for ticker in tickers}


def adjusted_return(ret: float, bench_ret: float, beta: float) -> float:
    if not all(np.isfinite(v) for v in (ret, bench_ret, beta)) or not BETA_MIN <= beta <= BETA_MAX:
        raise ValueError("invalid return or prediction-time beta")
    return float(ret - beta * bench_ret)
