"""ML ranker agent — a small gradient-boosted cross-sectional model.

Inspired by qlib's Alpha158 + LightGBM workflow, shrunk to what a laptop and
free daily data can support: ~14 price-derived features per stock (returns
over several windows relative to SOXX, volatility, drawdown, distance from
the 52-week high, RSI, z-score, beta), a LightGBM regressor trained on the
last 250 trading days of the universe to predict the 10-day abnormal return,
refit once a week. Nonlinear where the rule agents are linear; regularised
hard (few leaves, large min_child_samples) because 96 names x 250 days is
small. Point-in-time safe: it only sees closes up to the as-of date, and
training targets stop 11 days before it.
"""
import logging
from datetime import date

import numpy as np
import pandas as pd

import config
from agents.base import Signal, clip

log = logging.getLogger(__name__)
NAME = "ml_ranker"
TRAIN_DAYS = 250
HORIZON = 10
REFIT_DAYS = 7
_cache = {"fit_date": None, "model": None, "train_ic": 0.0}


def panel_features(closes: pd.DataFrame, bench: str) -> dict:
    """{feature: DataFrame(date x ticker)} from adjusted closes; NaN where not computable."""
    px = closes.drop(columns=[c for c in closes.columns if c.startswith("^") or c == "SPY"], errors="ignore")
    b = closes[bench]
    r = px.pct_change()
    rb = b.pct_change()
    f = {}
    for n in (1, 5, 10, 20, 60, 120):
        f[f"rel{n}"] = px.pct_change(n).sub(b.pct_change(n), axis=0)
    f["vol10"] = r.rolling(10).std()
    f["vol20"] = r.rolling(20).std()
    f["vol60"] = r.rolling(60).std()
    f["dd60"] = px / px.rolling(60).max() - 1
    f["hi252"] = px / px.rolling(252).max() - 1
    delta = px.diff()
    up = delta.clip(lower=0).rolling(14).mean()
    down = (-delta.clip(upper=0)).rolling(14).mean()
    f["rsi14"] = 100 - 100 / (1 + up / down.replace(0, np.nan))
    f["z20"] = (px - px.rolling(20).mean()) / px.rolling(20).std()
    cov = r.rolling(60).cov(rb)
    f["beta60"] = cov.div(rb.rolling(60).var(), axis=0)
    f["relvol"] = f["vol20"] / f["vol60"]
    return f


def _stack(feats: dict, rows: pd.Index, tickers) -> tuple[np.ndarray, list]:
    names = list(feats)
    mats = [feats[n].loc[rows, tickers].to_numpy(dtype=float).ravel() for n in names]
    X = np.column_stack(mats)
    return X, names


def _fit(closes: pd.DataFrame, asof: date, tickers: list):
    import lightgbm as lgb
    feats = panel_features(closes, config.BENCHMARK)
    idx = closes.index
    end = len(idx) - HORIZON - 1                         # last date whose 10-day target is known
    start = max(260, end - TRAIN_DAYS)
    if end - start < 60:
        return None, 0.0
    rows = idx[start:end]
    X, names = _stack(feats, rows, tickers)
    fwd = closes[tickers].shift(-HORIZON) / closes[tickers] - 1
    bfwd = closes[config.BENCHMARK].shift(-HORIZON) / closes[config.BENCHMARK] - 1
    y = fwd.sub(bfwd, axis=0).loc[rows, tickers].to_numpy(dtype=float).ravel()
    y = np.clip(y, -0.15, 0.15)
    ok = ~np.isnan(X).any(axis=1) & ~np.isnan(y)
    X, y = X[ok], y[ok]
    if len(y) < 2000:
        return None, 0.0
    params = {"objective": "regression", "learning_rate": 0.03, "num_leaves": 15, "min_data_in_leaf": 100,
              "bagging_fraction": 0.8, "bagging_freq": 1, "feature_fraction": 0.8, "lambda_l2": 5.0,
              "verbosity": -1, "num_threads": 4}
    # honest confidence: IC on the last 20% of dates from a model that never saw them, then refit on all
    cut = int(len(y) * 0.8)
    probe = lgb.train(params, lgb.Dataset(X[:cut], y[:cut]), num_boost_round=300)
    p_hold = probe.predict(X[cut:])
    ic = float(np.corrcoef(np.argsort(np.argsort(p_hold)), np.argsort(np.argsort(y[cut:])))[0, 1]) if len(p_hold) > 50 else 0.0
    model = lgb.train(params, lgb.Dataset(X, y), num_boost_round=300)   # native API: no scikit-learn needed
    return model, ic


def run(universe: dict, ctx: dict) -> list[Signal]:
    closes: pd.DataFrame = ctx["closes"]
    asof = ctx.get("asof") or date.today()
    tickers = [t for t in universe if t in closes.columns]
    if len(closes) < 330 or len(tickers) < 20:
        return []
    if _cache["model"] is None or _cache["fit_date"] is None or (asof - _cache["fit_date"]).days >= REFIT_DAYS:
        try:
            model, ic = _fit(closes, asof, tickers)
        except Exception as exc:
            log.warning("fit failed: %s", exc)
            return []
        if model is None:
            return []
        _cache.update(fit_date=asof, model=model, train_ic=ic)
    feats = panel_features(closes.iloc[-300:], config.BENCHMARK)
    X, _ = _stack(feats, closes.index[-1:], tickers)
    ok = ~np.isnan(X).any(axis=1)
    if ok.sum() < 10:
        return []
    pred = np.full(len(tickers), np.nan)
    pred[ok] = _cache["model"].predict(X[ok])
    z = (pred - np.nanmean(pred)) / (np.nanstd(pred) or 1e-9)
    conf = clip(0.3 + 2.0 * max(_cache["train_ic"], 0.0), 0.3, 0.7)   # holdout IC 0.05 -> 0.4, 0.2 -> 0.7
    out = []
    for t, zi, pi in zip(tickers, z, pred):
        if np.isnan(zi):
            continue
        out.append(Signal(NAME, t, float(np.tanh(zi / 1.5)), conf, HORIZON,
                          f"LightGBM 10d abnormal-return forecast {pi*100:+.1f}%, cross-sectional z {zi:+.1f}").clipped())
    return out
