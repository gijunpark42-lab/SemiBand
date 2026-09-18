"""Score matured predictions against realized returns, then refit the learner.

For a prediction made on date D with horizon h: entry = the close before D (the
one the pre-open signals were computed on, as in the backtest), exit = close h
trading days after that, abnormal = stock return minus the benchmark's.

Two learners run on the scored rows:
  * learner.fit  - Bayesian ridge stacking (the weights actually used), see learner.py
  * Hedge        - multiplicative weights kept as a simple reference line on the
                   dashboard: gain = mean(direction * confidence * abnormal * 20), clipped
"""
import logging
import math
import sqlite3
from collections import defaultdict
from datetime import date

import pandas as pd

import config
import ensemble
import learner
import ledger
import learning_targets
from agents.base import clip

log = logging.getLogger(__name__)


def run(closes: pd.DataFrame, today: str):
    """-> (effective weights for display, {agent: n newly scored}, model, hedge weights)."""
    # This scorer runs before the open; today's closing price cannot yet be known.
    closes = closes.loc[closes.index < pd.Timestamp(today)].sort_index()
    closes = closes.loc[closes[config.BENCHMARK].notna()]
    hedge = ledger.latest_hedge_weights() or ensemble.initial_weights()
    for a in config.AGENTS:                     # a newly added agent starts at the floor
        hedge.setdefault(a, config.WEIGHT_FLOOR)
    idx = closes.index
    bench = closes[config.BENCHMARK]
    gains = defaultdict(list)
    scored = 0
    betas = learning_targets.rolling_beta(closes)

    for h in config.HORIZONS:
        for p in ledger.unscored(h):
            pos = idx.searchsorted(pd.Timestamp(p["date"]))
            # entry at the close before the prediction date (2026-09-15: the backtest's label; starting at the prediction
            # day's own close cost +895% -> +712% over 500 days with the open refresh on, RESEARCH.md round 27).
            # Coupled to config.OPEN_REFRESH_AGENTS: only with this label does the refresh tie no refresh (round 31); under the
            # order-day-open label every refresh form lost 6-7 bps/day. Never change the label alone: re-test the refresh first.
            same_close = bool(config.LABEL_SAME_CLOSE_FROM) and p["date"] >= config.LABEL_SAME_CLOSE_FROM   # close mode (round 48)
            start = pos if same_close else pos - 1
            if start < 0 or start + h >= len(idx) or pos >= len(idx) or idx[pos] != pd.Timestamp(p["date"]):
                continue                        # not matured yet, or no close before the prediction date
            t = p["ticker"]
            if t not in closes.columns:
                continue
            c0, c1 = closes[t].iloc[start], closes[t].iloc[start + h]
            b0, b1 = bench.iloc[start], bench.iloc[start + h]
            if any(not math.isfinite(v) or v <= 0 for v in (c0, c1, b0, b1)):
                continue
            ret, bench_ret = float(c1 / c0 - 1), float(b1 / b0 - 1)
            abn = ret - bench_ret
            beta = p["benchmark_beta"]
            if beta is None:
                beta = learning_targets.beta_at(betas, t, p["date"], before=True)
                ledger.set_prediction_beta(p["id"], beta)
            beta_abn = learning_targets.adjusted_return(ret, bench_ret, beta)
            d = p["direction"]
            hit = None if abs(d) < 0.1 else int((d > 0) == (abn > 0))
            ledger.add_score(p["id"], h, today, ret, bench_ret, abn, beta_abn, hit)
            gains[p["agent"]].append(clip(d * p["confidence"] * abn * 20, -1, 1))
            scored += 1

    if gains:
        mean_gains = {a: sum(g) / len(g) for a, g in gains.items()}
        hedge = ensemble.hedge_update(hedge, mean_gains)
        log.info("scored %d predictions; hedge gains %s -> %s", scored,
                 {a: round(g, 3) for a, g in mean_gains.items()}, hedge)
    ledger.save_hedge_weights(today, hedge)

    active_mode = config.LEARNER_TARGET_MODE
    shadow_mode = "raw" if active_mode == "beta" else "beta"
    model = learner.fit(date.fromisoformat(today), asof=date.fromisoformat(today), target_mode=active_mode)
    try:
        learner.fit(date.fromisoformat(today), asof=date.fromisoformat(today), target_mode=shadow_mode)
    except (RuntimeError, ValueError, sqlite3.OperationalError) as exc:
        # A failed experimental shadow must not prevent an authorized rollback to the raw model.
        if active_mode != "raw":
            raise
        log.warning("beta shadow unavailable after raw rollback: %s", exc)
    weights = model["effective_weights"]
    log.info("stacking model: %s", {h: {k: v[k] for k in ("n_obs", "lambda", "cv_ic")}
                                     for h, v in model["horizons"].items()})
    ledger.save_weights(today, weights)
    return weights, {a: len(g) for a, g in gains.items()}, model, hedge
