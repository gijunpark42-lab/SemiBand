"""Score matured predictions against realized returns, then refit the learner.

For a prediction made on date D with horizon h: entry = close of D, exit =
close h trading days later, abnormal = stock return minus the benchmark's.

Two learners run on the scored rows:
  * learner.fit  - Bayesian ridge stacking (the weights actually used), see learner.py
  * Hedge        - multiplicative weights kept as a simple reference line on the
                   dashboard: gain = mean(direction * confidence * abnormal * 20), clipped
"""
import logging
from collections import defaultdict
from datetime import date

import pandas as pd

import config
import ensemble
import learner
import ledger
from agents.base import clip

log = logging.getLogger(__name__)


def run(closes: pd.DataFrame, today: str):
    """-> (effective weights for display, {agent: n newly scored}, model, hedge weights)."""
    hedge = ledger.latest_hedge_weights() or ensemble.initial_weights()
    for a in config.AGENTS:                     # a newly added agent starts at the floor
        hedge.setdefault(a, config.WEIGHT_FLOOR)
    idx = closes.index
    bench = closes[config.BENCHMARK]
    gains = defaultdict(list)
    scored = 0

    for h in config.HORIZONS:
        for p in ledger.unscored(h):
            pos = idx.searchsorted(pd.Timestamp(p["date"]))
            if pos + h >= len(idx):
                continue                        # not matured yet
            t = p["ticker"]
            if t not in closes.columns:
                continue
            c0, c1 = closes[t].iloc[pos], closes[t].iloc[pos + h]
            b0, b1 = bench.iloc[pos], bench.iloc[pos + h]
            if any(pd.isna(v) for v in (c0, c1, b0, b1)):
                continue
            ret, bench_ret = float(c1 / c0 - 1), float(b1 / b0 - 1)
            abn = ret - bench_ret
            d = p["direction"]
            hit = None if abs(d) < 0.1 else int((d > 0) == (abn > 0))
            ledger.add_score(p["id"], h, today, ret, bench_ret, abn, hit)
            gains[p["agent"]].append(clip(d * p["confidence"] * abn * 20, -1, 1))
            scored += 1

    if gains:
        mean_gains = {a: sum(g) / len(g) for a, g in gains.items()}
        hedge = ensemble.hedge_update(hedge, mean_gains)
        log.info("scored %d predictions; hedge gains %s -> %s", scored,
                 {a: round(g, 3) for a, g in mean_gains.items()}, hedge)
    ledger.save_hedge_weights(today, hedge)

    model = learner.fit(date.fromisoformat(today))
    weights = model["effective_weights"]
    log.info("stacking model: %s", {h: {k: v[k] for k in ("n_obs", "lambda", "cv_ic")}
                                     for h, v in model["horizons"].items()})
    ledger.save_weights(today, weights)
    return weights, {a: len(g) for a, g in gains.items()}, model, hedge
