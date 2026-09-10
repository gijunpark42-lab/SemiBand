"""Score matured predictions against realized returns and update agent weights.

For a prediction made on date D with horizon h: entry = close of D, exit =
close h trading days later, abnormal = stock return minus the benchmark's.
An agent's gain for the round is the mean over its newly scored predictions of
    direction * confidence * abnormal * 20     (clipped to [-1, 1])
so a full-conviction call that beats SOXX by 5% earns +1, the opposite -1.
"""
import logging
from collections import defaultdict

import pandas as pd

import config
import ensemble
import ledger
from agents.base import clip

log = logging.getLogger(__name__)


def run(closes: pd.DataFrame, today: str):
    weights = ledger.latest_weights() or ensemble.initial_weights()
    for a in config.AGENTS:                     # a newly added agent starts at the floor
        weights.setdefault(a, config.WEIGHT_FLOOR)
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
        weights = ensemble.hedge_update(weights, mean_gains)
        log.info("scored %d predictions; gains %s; weights %s", scored,
                 {a: round(g, 3) for a, g in mean_gains.items()}, weights)
    ledger.save_weights(today, weights)
    return weights, {a: len(g) for a, g in gains.items()}
