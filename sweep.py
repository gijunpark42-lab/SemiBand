"""Fast parameter sweeps on top of a finished backtest.

backtest.py is the slow part (agents day by day -> state/backtest.sqlite).
This script re-simulates the walk-forward learner + portfolio from those stored
opinions in seconds, so sizing and learning knobs can be compared honestly on
the same signals:

    python sweep.py                      # run the grid, print a table, save state/backtest_sweep.json
    python sweep.py --apply              # also write the winner's knobs into state/sweep_best.json

Every variant is scored on the same 220 days: total return, excess vs SOXX,
Sharpe, max drawdown, turnover, and the 10-day IC of its convictions.
"""
import argparse
import itertools
import json
import math
import sqlite3
from datetime import date

import numpy as np
import pandas as pd

import config
import learner
import market
from agents.base import Signal

DB = config.STATE_DIR / "backtest.sqlite"
OUT = config.STATE_DIR / "backtest_sweep.json"
PIT_AGENTS = ["supply_chain", "neighbors", "technical", "mean_reversion", "events", "risk", "macro"]

BASE = dict(min_conv=0.10, size_k=0.30, cap=0.10, gross=1.50, band=0.15, top_n=15,
            half_life=90, demean=False, horizons=(5, 10, 20), learn=True, agents_only=None, lam=None)


def load_signals():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT date, ticker, agent, direction, confidence, horizon FROM predictions ORDER BY date").fetchall()
    con.close()
    by_date = {}
    for r in rows:
        by_date.setdefault(r["date"], []).append(Signal(r["agent"], r["ticker"], r["direction"], r["confidence"], r["horizon"], ""))
    return by_date


def simulate(by_date, closes, params, refit_every=5, warmup=30):
    p = dict(BASE, **params)
    learner.HALF_LIFE_DAYS = p["half_life"]
    learner.LAMBDA_GRID = (p["lam"],) if p["lam"] else tuple(config.LEARNER_LAMBDA_GRID)
    learner.PRIOR_STRENGTH = p["lam"] or config.LEARNER_PRIOR_STRENGTH
    config.HORIZONS = tuple(p["horizons"])
    dates = sorted(by_date)
    idx = closes.index
    pos_of = {d.date().isoformat(): i for i, d in enumerate(idx)}
    bench = closes[config.BENCHMARK]
    equity, prev_w, turnover_total, curve, ics = 1.0, {}, 0.0, [], []
    model = None
    for k, d in enumerate(dates):
        if k < warmup or d not in pos_of:
            continue
        i = pos_of[d]
        if i + 10 >= len(idx):
            break
        if p["learn"] and (model is None or k % refit_every == 0):
            model = learner.fit(date.fromisoformat(d), asof=date.fromisoformat(d))
        sigs = by_date[d] if not p["agents_only"] else [s for s in by_date[d] if s.agent in p["agents_only"]]
        conv, _ = learner.predict(sigs, model if p["learn"] else None)
        if p["demean"]:
            m = float(np.mean(list(conv.values())))
            conv = {t: c - m for t, c in conv.items()}
        # IC of today's convictions vs 10-day outcome
        y = {}
        for t in conv:
            c0, c1, b0, b1 = closes[t].iloc[i], closes[t].iloc[i + 10], bench.iloc[i], bench.iloc[i + 10]
            if not any(pd.isna(v) for v in (c0, c1, b0, b1)):
                y[t] = float(c1 / c0 - 1) - float(b1 / b0 - 1)
        if len(y) >= 10:
            ics.append(learner.ic(np.array([conv[t] for t in y]), np.array(list(y.values()))))
        # sizing
        longs = sorted(((t, c) for t, c in conv.items() if c >= p["min_conv"]), key=lambda tc: -tc[1])[:p["top_n"]]
        w = {t: min(c * p["size_k"], p["cap"]) for t, c in longs}
        g = sum(w.values())
        if g > p["gross"]:
            w = {t: x * p["gross"] / g for t, x in w.items()}
        # rebalance band: keep the old weight when the target moved less than band x target
        for t in list(w):
            if t in prev_w and abs(w[t] - prev_w[t]) < p["band"] * w[t]:
                w[t] = prev_w[t]
        turnover = sum(abs(w.get(t, 0) - prev_w.get(t, 0)) for t in set(w) | set(prev_w))
        ret = 0.0
        for t, wt in w.items():
            c0, c1 = closes[t].iloc[i], closes[t].iloc[i + 1]
            if not (pd.isna(c0) or pd.isna(c1)):
                ret += wt * (float(c1 / c0) - 1)
        ret -= turnover * config.COST_BPS / 10_000
        equity *= 1 + ret
        turnover_total += turnover
        prev_w = w
        curve.append({"date": d, "portfolio": equity, "gross": g if g <= p["gross"] else p["gross"], "n": len(w),
                      "soxx": float(bench.iloc[i + 1] / bench.iloc[pos_of[dates[warmup]]])})
    rets = np.diff(np.log([1.0] + [c["portfolio"] for c in curve]))
    eq = np.array([c["portfolio"] for c in curve])
    dd = 1 - eq / np.maximum.accumulate(eq)
    n = len(curve)
    return {
        "params": {k: (list(v) if isinstance(v, tuple) else v) for k, v in p.items()},
        "total_return": round(float(eq[-1] - 1), 4),
        "soxx_return": round(float(curve[-1]["soxx"] - 1), 4),
        "excess_vs_soxx": round(float(eq[-1] - curve[-1]["soxx"]), 4),
        "sharpe": round(float(np.mean(rets) / (np.std(rets) or 1e-9) * math.sqrt(252)), 2),
        "max_drawdown": round(float(dd.max()), 4),
        "ann_vol": round(float(np.std(rets) * math.sqrt(252)), 3),
        "avg_gross": round(float(np.mean([c["gross"] for c in curve])), 3),
        "avg_names": round(float(np.mean([c["n"] for c in curve])), 1),
        "turnover_per_day": round(turnover_total / n, 3),
        "ic_10d": round(float(np.mean(ics)), 4) if ics else None,
        "days": n,
    }


GRID = {
    "min_conv": [0.05, 0.10, 0.15],
    "size_k": [0.20, 0.30, 0.45],
    "cap": [0.10, 0.15],
    "band": [0.15, 0.30],
    "demean": [False, True],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--quick", action="store_true", help="only the base case and a few variants")
    ap.add_argument("--round2", action="store_true", help="second round: half-life 90 combos and lambda variants")
    ap.add_argument("--round3", action="store_true", help="third round: fixed lambda x sizing")
    args = ap.parse_args()

    live_agents, live_h = config.AGENTS, config.HORIZONS
    config.AGENTS = PIT_AGENTS
    import ledger
    ledger.DB = DB
    learner.MODEL_FILE = config.STATE_DIR / "sweep_model.json"

    by_date = load_signals()
    tickers = sorted({s.ticker for sigs in by_date.values() for s in sigs})
    closes = market.closes(tickers + [config.BENCHMARK, "SPY"], lookback_days=800, cache=False)
    closes = closes[closes[config.BENCHMARK].notna()]

    if args.round2:
        variants = [("hl90_base", {})]
        for lam in (20.0, 50.0, 150.0, 400.0):
            variants.append((f"hl90_lam{int(lam)}", {"lam": lam}))
        for k, cap, band in ((0.45, 0.10, 0.15), (0.45, 0.10, 0.30), (0.45, 0.15, 0.15), (0.30, 0.15, 0.15), (0.30, 0.10, 0.30)):
            variants.append((f"hl90_k{k}_cap{cap}_band{band}", {"size_k": k, "cap": cap, "band": band}))
        variants.append(("hl90_lam50_k0.45", {"lam": 50.0, "size_k": 0.45}))
        variants.append(("hl120", {"half_life": 120}))
        variants.append(("hl180", {"half_life": 180}))
    if args.round3:
        variants = [("lam150_k0.3_cap0.1", {"lam": 150.0}),
                    ("lam150_k0.45_cap0.1", {"lam": 150.0, "size_k": 0.45}),
                    ("lam150_k0.45_cap0.15", {"lam": 150.0, "size_k": 0.45, "cap": 0.15}),
                    ("lam150_k0.45_cap0.1_band0.3", {"lam": 150.0, "size_k": 0.45, "band": 0.30}),
                    ("lam150_k0.6_cap0.1", {"lam": 150.0, "size_k": 0.60}),
                    ("lam100_k0.45_cap0.1", {"lam": 100.0, "size_k": 0.45}),
                    ("lam250_k0.45_cap0.1", {"lam": 250.0, "size_k": 0.45})]
    else:
        variants = [("base", {}), ("no_learning", {"learn": False}), ("half_life_90", {"half_life": 90}),
                ("half_life_20", {"half_life": 20}), ("h10_20_only", {"horizons": (10, 20)}), ("h20_only", {"horizons": (20,)}),
                ("technical_only", {"learn": False, "agents_only": ("technical",)}),
                ("no_neighbors", {"agents_only": ("supply_chain", "technical", "mean_reversion", "events", "risk", "macro")}),
                ("price_agents_only", {"agents_only": ("technical", "mean_reversion", "risk", "macro")})]
    if not args.quick and not args.round2 and not args.round3:
        for combo in itertools.product(*GRID.values()):
            kv = dict(zip(GRID.keys(), combo))
            if kv == {k: BASE[k] for k in GRID}:
                continue
            variants.append(("+".join(f"{k}={v}" for k, v in kv.items()), kv))
    results = []
    for name, kv in variants:
        r = simulate(by_date, closes, kv)
        r["name"] = name
        results.append(r)
        print(f"{name:60s} ret {r['total_return']:+.3f} excess {r['excess_vs_soxx']:+.3f} sharpe {r['sharpe']:5.2f} "
              f"dd {r['max_drawdown']:.3f} gross {r['avg_gross']:.2f} turn {r['turnover_per_day']:.3f} ic {r['ic_10d']}", flush=True)
    config.AGENTS, config.HORIZONS = live_agents, live_h
    # robust ranking: Sharpe first, then excess vs SOXX, penalise turnover
    for r in results:
        r["score"] = round(r["sharpe"] + 0.5 * r["excess_vs_soxx"] - 0.5 * r["turnover_per_day"], 3)
    results.sort(key=lambda r: -r["score"])
    out = OUT if not (args.round2 or args.round3) else config.STATE_DIR / ("backtest_sweep2.json" if args.round2 else "backtest_sweep3.json")
    out.write_text(json.dumps({"generated": date.today().isoformat(), "results": results}, indent=2), encoding="utf-8")
    print("\nTOP 5 by score (sharpe + 0.5*excess - 0.5*turnover):")
    for r in results[:5]:
        print(f"  {r['score']:6.3f} {r['name']}")
    if args.apply:
        (config.STATE_DIR / "sweep_best.json").write_text(json.dumps(results[0], indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
