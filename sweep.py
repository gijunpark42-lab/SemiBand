"""Fast parameter sweeps on top of a finished backtest.

backtest.py is the slow part (agents day by day -> state/backtest.sqlite).
This script re-simulates the walk-forward learner + portfolio from those stored
opinions in seconds, so sizing and learning knobs can be compared honestly on
the same signals:

    python sweep.py                      # run the grid, print a table, save state/backtest_sweep.json
    python sweep.py --apply              # also write the winner's knobs into state/sweep_best.json

Every variant is scored on the same 220 days: total return, excess vs SOXX,
Sharpe, max drawdown, turnover, and the 10-day IC of its convictions. Each
variant's daily returns are stored too, and the round ends with the probability
of backtest overfitting (robustness.pbo, CSCV): with ~160 variants tried on one
window, a winner whose in-sample rank does not survive out of sample is noise.
Progress (variants done, table so far) is published to the website's /backtest page.
"""
import argparse
import itertools
import json
import math
import pathlib
import random
import sqlite3
import time
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd

import backtest
import config
import learner
import market
import robustness
from agents.base import Signal

DB = config.STATE_DIR / "backtest.sqlite"
OUT = config.STATE_DIR / "backtest_sweep.json"
PIT_AGENTS = list(backtest.PIT_AGENTS)   # the live roster restricted to simulated agents (events dropped 2026-09-11; its rows stay in the ledger)

BASE = dict(min_conv=0.10, size_k=0.30, cap=0.10, gross=1.50, band=0.15, top_n=15,
            half_life=90, demean=False, horizons=(5, 10, 20), learn=True, agents_only=None, lam=None,
            stop_loss=None, cooldown=5, vol_scale=False, rebalance_every=1, swap_margin=None,
            short_k=0, short_gross=0.0, hedge=None, hedge_size=0.3,
            vol_target=None,      # portfolio-level: scale the book down when trailing 20-day realised vol exceeds this (annualised)
            ewma_halflife=None,   # smooth each name's conviction with this half-life (days) before sizing: less churn
            exec="close",         # 'open' = buy at the next open, mark open-to-open (the live rule)
            oos_end=None,         # date: rows before it are reported as out-of-sample, from it as in-sample (the tuning window)
            inv_vol=None,         # per-name risk sizing: weight x clip(ref / 20d vol, 0.5, 2); ref = 'median' (cross-section) or a number (annualised)
            dd_brake=None,        # (trigger, factor, release): book x factor once the sim equity is trigger below its high, until it is back within release
            exit_conv=None,       # hysteresis: a HELD name stays eligible down to this conviction (entry still needs min_conv)
            min_hold=0)           # a name entered fewer than this many days ago is not dropped unless its conviction turns negative


def load_signals():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT date, ticker, agent, direction, confidence, horizon FROM predictions ORDER BY date").fetchall()
    con.close()
    by_date = {}
    for r in rows:
        by_date.setdefault(r["date"], []).append(Signal(r["agent"], r["ticker"], r["direction"], r["confidence"], r["horizon"], ""))
    return by_date


def simulate(by_date, closes, params, refit_every=1, warmup=30, opens=None):
    p = dict(BASE, **params)
    learner.HALF_LIFE_DAYS = p["half_life"]
    learner.LAMBDA_GRID = (p["lam"],) if p["lam"] else tuple(config.LEARNER_LAMBDA_GRID)
    learner.PRIOR_STRENGTH = p["lam"] or config.LEARNER_PRIOR_STRENGTH
    config.HORIZONS = tuple(p["horizons"])
    # agents_only = the roster itself (prior 1/n over those agents), exactly what dropping the agent from config.AGENTS does live
    config.AGENTS = list(p["agents_only"]) if p["agents_only"] else list(PIT_AGENTS)
    dates = sorted(by_date)
    idx = closes.index
    pos_of = {d.date().isoformat(): i for i, d in enumerate(idx)}
    bench = closes[config.BENCHMARK]
    # execution prices: close mode marks close t -> close t+1; open mode buys at open t+1 and marks to open t+2
    if p["exec"] == "open":
        if opens is None:
            raise ValueError("exec='open' needs the opens frame (pass --exec open to main)")
        px, shift = opens.reindex(idx), 1
    else:
        px, shift = closes, 0
    equity, prev_w, turnover_total, curve, ics = 1.0, {}, 0.0, [], []
    entry, banned, smooth = {}, {}, {}
    entry_day, peak, braked = {}, 1.0, False
    quint = [[] for _ in range(5)]                    # 10-day abnormal return by conviction quintile (signal monotonicity)
    model = None
    for k, d in enumerate(dates):
        if k < warmup or d not in pos_of:
            continue
        i = pos_of[d]
        if i + 10 >= len(idx):
            break
        if p["learn"] and (model is None or k % refit_every == 0):
            model = learner.fit(date.fromisoformat(d), asof=date.fromisoformat(d))
            if p["learn"] == "ic":
                # IC-weighted blend: w_conf_i = max(IC_i, 0) normalised to sum 1 per horizon, no direction-only terms,
                # horizons blended equally. Zero fitted parameters beyond the per-agent IC itself.
                for h, v in model["horizons"].items():
                    pos = {a: max(v["agent_ic"].get(a) or 0.0, 0.0) for a in model["agents"]}
                    tot = sum(pos.values())
                    v["w_conf"] = {a: (pos[a] / tot if tot else 1.0 / len(pos)) for a in pos}
                    v["w_dir"] = {a: 0.0 for a in pos}
                    v["reliability"] = 1.0
        sigs = by_date[d] if not p["agents_only"] else [s for s in by_date[d] if s.agent in p["agents_only"]]
        conv, _ = learner.predict(sigs, model if p["learn"] else None)
        if p["demean"]:
            m = float(np.mean(list(conv.values())))
            conv = {t: c - m for t, c in conv.items()}
        if p["ewma_halflife"]:
            a = 1 - 0.5 ** (1 / p["ewma_halflife"])
            conv = {t: a * c + (1 - a) * smooth.get(t, c) for t, c in conv.items()}
            smooth = dict(conv)
        # IC of today's convictions vs 10-day outcome
        y = {}
        for t in conv:
            c0, c1, b0, b1 = closes[t].iloc[i], closes[t].iloc[i + 10], bench.iloc[i], bench.iloc[i + 10]
            if not any(pd.isna(v) for v in (c0, c1, b0, b1)):
                y[t] = float(c1 / c0 - 1) - float(b1 / b0 - 1)
        if len(y) >= 10:
            ics.append(learner.ic(np.array([conv[t] for t in y]), np.array(list(y.values()))))
            order = sorted(y, key=lambda t: conv[t])
            for q in range(5):
                part = order[q * len(order) // 5:(q + 1) * len(order) // 5]
                if part:
                    quint[q].append(float(np.mean([y[t] for t in part])))
        # stop-loss (evaluated on closes): drop a name that fell stop_loss below its entry, sit out `cooldown` days
        if p["stop_loss"]:
            for t in list(prev_w):
                e = entry.get(t)
                c_now = closes[t].iloc[i]
                if e and not pd.isna(c_now) and c_now / e - 1 < -p["stop_loss"]:
                    banned[t] = k + p["cooldown"]
            conv = {t: c for t, c in conv.items() if banned.get(t, -1) < k}
        # sizing
        if p["rebalance_every"] > 1 and prev_w and (k - warmup) % p["rebalance_every"]:
            w = dict(prev_w)                          # hold the book on non-rebalance days
        else:
            floor = p["exit_conv"] if p["exit_conv"] is not None else p["min_conv"]
            eligible = sorted(((t, c) for t, c in conv.items()
                               if c >= p["min_conv"] or (t in prev_w and c >= floor)), key=lambda tc: -tc[1])
            longs = eligible[:p["top_n"]]
            if p["min_hold"]:
                chosen = {t for t, _ in longs}
                for t in prev_w:                       # young positions are kept even when they fell out of the ranking
                    if t not in chosen and k - entry_day.get(t, k) < p["min_hold"] and conv.get(t, -1) >= 0:
                        longs.append((t, conv[t]))
            if p["swap_margin"] is not None and prev_w:
                # TopkDropout-style: a held name still above the bar keeps its seat unless a
                # newcomer beats it by more than swap_margin (no commission, but spread + slippage)
                held_ok = [(t, c) for t, c in eligible if t in prev_w]
                newcomers = [(t, c) for t, c in eligible if t not in prev_w]
                seats = p["top_n"]
                chosen = held_ok[:seats]
                for t, c in newcomers:
                    if len(chosen) < seats:
                        chosen.append((t, c))
                    else:
                        worst = min(chosen, key=lambda tc: tc[1])
                        if c > worst[1] + p["swap_margin"]:
                            chosen.remove(worst)
                            chosen.append((t, c))
                longs = chosen
            if p["inv_vol"]:
                vols = {}
                for t, _ in longs:
                    r = closes[t].iloc[max(0, i - 20): i + 1].pct_change().dropna()
                    vols[t] = float(r.std() * math.sqrt(252)) if len(r) >= 10 else None
                known = [v for v in vols.values() if v]
                ref = (float(np.median(known)) if p["inv_vol"] == "median" else float(p["inv_vol"])) if known else None
                mult = {t: (min(max(ref / vols[t], 0.5), 2.0) if (ref and vols.get(t)) else 1.0) for t, _ in longs}
                w = {t: min(c * p["size_k"] * mult[t], p["cap"]) for t, c in longs}
            else:
                w = {t: min(c * p["size_k"], p["cap"]) for t, c in longs}
            # optional short book: the k lowest-conviction names, sized to short_gross in total
            if p["short_k"] and p["short_gross"]:
                shorts = sorted(((t, c) for t, c in conv.items() if c <= -p["min_conv"]), key=lambda tc: tc[1])[:p["short_k"]]
                tot = sum(abs(c) for _, c in shorts)
                for t, c in shorts:
                    w[t] = -p["short_gross"] * abs(c) / tot if tot else 0.0
            # optional index hedge: a synthetic -1x SOXX position (like PSQ/SOXS-third) when the regime is weak
            if p["hedge"]:
                soxx = closes[config.BENCHMARK]
                weak = (p["hedge"] == "below50" and soxx.iloc[i] < soxx.iloc[max(0, i - 50): i + 1].mean()) or                        (p["hedge"] == "always")
                if weak:
                    w["__HEDGE__"] = -p["hedge_size"]
            if p["vol_scale"] and w:
                # scale each name by (median vol / its vol): calmer names get more, wild ones less
                vols = {}
                for t in w:
                    r = closes[t].iloc[max(0, i - 40): i + 1].pct_change().dropna()
                    vols[t] = float(r.std()) if len(r) > 10 else None
                med = float(np.median([v for v in vols.values() if v])) if any(vols.values()) else None
                if med:
                    w = {t: min(x * (med / vols[t] if vols.get(t) else 1.0), p["cap"]) for t, x in w.items()}
        g = sum(w.values())
        if g > p["gross"]:
            w = {t: x * p["gross"] / g for t, x in w.items()}
        # portfolio vol targeting: trailing 20-day realised vol of the book itself; scale down only, never lever up
        if p["vol_target"] and len(curve) >= 20:
            realised = float(np.std([c["ret"] for c in curve[-20:]])) * math.sqrt(252)
            if realised > p["vol_target"]:
                w = {t: x * p["vol_target"] / realised for t, x in w.items()}
        # drawdown brake: once the book is `trigger` below its own high, run at `factor` of size until it is back within `release`
        if p["dd_brake"]:
            trigger, factor, release = p["dd_brake"]
            peak = max(peak, equity)
            dd_now = 1 - equity / peak
            braked = (dd_now >= trigger) if not braked else (dd_now > release)
            if braked:
                w = {t: x * factor for t, x in w.items()}
        # rebalance band: keep the old weight when the target moved less than band x target
        for t in list(w):
            if t in prev_w and abs(w[t] - prev_w[t]) < p["band"] * w[t]:
                w[t] = prev_w[t]
        for t in w:
            if t not in prev_w and t in closes.columns:
                entry[t] = closes[t].iloc[i]
                entry_day[t] = k
        for t in list(entry):
            if t not in w:
                entry.pop(t, None)
        turnover = sum(abs(w.get(t, 0) - prev_w.get(t, 0)) for t in set(w) | set(prev_w))
        ret = 0.0
        for t, wt in w.items():
            sym = config.BENCHMARK if t == "__HEDGE__" else t
            c0, c1 = px[sym].iloc[i + shift], px[sym].iloc[i + 1 + shift]
            if not (pd.isna(c0) or pd.isna(c1)):
                ret += wt * (float(c1 / c0) - 1)
            if wt < 0:
                ret -= abs(wt) * 0.0002        # ~5%/yr borrow / inverse-ETF drag on the short side
        ret -= turnover * config.COST_BPS / 10_000
        equity *= 1 + ret
        turnover_total += turnover
        prev_w = w
        b0 = pos_of[dates[warmup]] + shift
        curve.append({"date": d, "portfolio": equity, "gross": sum(abs(x) for x in w.values()), "n": len(w), "ret": ret,
                      "soxx": float(px[config.BENCHMARK].iloc[i + 1 + shift] / px[config.BENCHMARK].iloc[b0])})
    rets = np.diff(np.log([1.0] + [c["portfolio"] for c in curve]))
    eq = np.array([c["portfolio"] for c in curve])
    dd = 1 - eq / np.maximum.accumulate(eq)
    n = len(curve)
    out = {
        "params": {k: (list(v) if isinstance(v, tuple) else v) for k, v in p.items()},
        "rets": [round(float(r), 5) for r in rets],      # daily log returns, kept for the PBO test across variants
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
        "quintiles_10d": [round(float(np.mean(q)), 4) if q else None for q in quint],   # Q1 (lowest conviction) .. Q5
        "days": n,
    }
    if p["oos_end"]:
        out["oos"] = _segment([c for c in curve if c["date"] < p["oos_end"]], 1.0, 1.0)
        first_is = next((j for j, c in enumerate(curve) if c["date"] >= p["oos_end"]), None)
        base = curve[first_is - 1] if first_is else None
        out["is"] = _segment(curve[first_is:], base["portfolio"], base["soxx"]) if base else None
    return out


def _segment(seg, base_eq, base_soxx):
    """Return / SOXX / Sharpe / max drawdown of one slice of a curve, rebased to its first day."""
    if len(seg) < 5:
        return None
    eq = np.array([c["portfolio"] for c in seg]) / base_eq
    rets = np.diff(np.log(np.r_[1.0, eq]))
    dd = 1 - eq / np.maximum.accumulate(eq)
    return {"start": seg[0]["date"], "end": seg[-1]["date"], "days": len(seg),
            "total_return": round(float(eq[-1] - 1), 4), "soxx_return": round(float(seg[-1]["soxx"] / base_soxx - 1), 4),
            "sharpe": round(float(np.mean(rets) / (np.std(rets) or 1e-9) * math.sqrt(252)), 2),
            "max_drawdown": round(float(dd.max()), 4)}


GRID = {
    "min_conv": [0.05, 0.10, 0.15],
    "size_k": [0.20, 0.30, 0.45],
    "cap": [0.10, 0.15],
    "band": [0.15, 0.30],
    "demean": [False, True],
}


# ---------------------------------------------------------------------------
# Parallel evaluation (one process per worker; each loads the ledger and prices once)

_W = {}


def _init_worker(db_path, exec_mode, roster):
    import os, ledger as _ledger
    global DB
    DB = pathlib.Path(db_path); _ledger.DB = DB
    learner.MODEL_FILE = config.STATE_DIR / f"sweep_model_{os.getpid()}.json"
    config.AGENTS = list(roster)
    by_date = load_signals()
    tickers = sorted({s.ticker for sigs in by_date.values() for s in sigs})
    closes = market.closes(tickers + [config.BENCHMARK, "SPY"], lookback_days=800, cache=False)
    _W["by_date"], _W["closes"] = by_date, closes[closes[config.BENCHMARK].notna()]
    _W["opens"] = market.opens(tickers + [config.BENCHMARK, "SPY"], lookback_days=800) if exec_mode == "open" else None


def _eval(job):
    name, kv = job
    r = simulate(_W["by_date"], _W["closes"], kv, opens=_W["opens"])
    r["name"] = name
    return r


def evaluate(variants, common, workers, run_info, pool=None, data=None, log=None):
    """Run every (name, params) pair, sequentially or on the pool; print and publish as results arrive."""
    jobs = [(name, dict(common, **kv)) for name, kv in variants]
    results, t0 = [], time.time()
    if workers > 1:
        it = pool.imap_unordered(_eval, jobs)
    else:
        by_date, closes, opens = data
        it = (dict(simulate(by_date, closes, kv, opens=opens), name=name) for name, kv in jobs)
    for k, r in enumerate(it, 1):
        results.append(r)
        oos = f" | OOS ret {r['oos']['total_return']:+.3f} sharpe {r['oos']['sharpe']:5.2f} dd {r['oos']['max_drawdown']:.3f}" if r.get("oos") else ""
        print(f"{r['name']:32s} ret {r['total_return']:+.3f} excess {r['excess_vs_soxx']:+.3f} sharpe {r['sharpe']:5.2f} "
              f"dd {r['max_drawdown']:.3f} gross {r['avg_gross']:.2f} turn {r['turnover_per_day']:.3f} ic {r['ic_10d']}{oos}", flush=True)
        elapsed = time.time() - t0
        shown = (log or []) + results
        backtest.publish_progress(dict(run_info, status="running" if k < len(jobs) else "done", pct=round(k / len(jobs), 4),
                                       done=k, total=len(jobs), elapsed_s=round(elapsed), eta_s=round(elapsed / k * (len(jobs) - k)),
                                       results=[{kk: v for kk, v in x.items() if kk != "rets"} for x in shown]))
    return results


# ---------------------------------------------------------------------------
# Generational search: evaluate a population in parallel, keep the best, mutate it, repeat.
# Objective = mean rank over full-window Sharpe and return, OOS Sharpe and return, and (lower) full-window max drawdown,
# so a variant has to be good on all five, not spectacular on one. Every trial is appended to
# state/backtest_search<tag>.json (this raises the trial count behind the deflated Sharpe: selection on both
# windows makes the OOS window in-sample too, so the only validation left after a search is new data).

SPACE = {
    "vol_target": [None, 0.3, 0.4, 0.5, 0.6, 0.7],
    "size_k": [0.45, 0.60, 0.75],
    "min_conv": [0.10, 0.15, 0.20],
    "top_n": [10, 15, 20],
    "cap": [0.10, 0.15],
    "band": [0.30, 0.50],
    "lam": [100.0, 150.0, 250.0],
    "half_life": [60, 90, 120],
    "horizons": [(5, 10, 20), (10, 20)],
}


def objective(results):
    cols = {"sharpe": [r["sharpe"] for r in results], "ret": [r["total_return"] for r in results],
            "oos_sharpe": [r["oos"]["sharpe"] for r in results],
            "oos_return": [r["oos"]["total_return"] for r in results],
            "neg_dd": [-r["max_drawdown"] for r in results]}
    for i, r in enumerate(results):
        ranks = [sorted(v).index(v[i]) + 1 for v in cols.values()]        # 1 = worst
        r["objective"] = round(float(np.mean(ranks)) / len(results), 3)   # 1.0 = best on everything


def mutate(best, rng, tried, n):
    out, keys = [], list(SPACE)
    while len(out) < n:
        kv = dict(best)
        for k in rng.sample(keys, rng.choice((1, 1, 2))):
            kv[k] = rng.choice(SPACE[k])
        key = json.dumps({k: kv.get(k) for k in keys}, sort_keys=True)
        if key not in tried:
            tried.add(key); out.append(kv)
    return out



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--quick", action="store_true", help="only the base case and a few variants")
    ap.add_argument("--round2", action="store_true", help="second round: half-life 90 combos and lambda variants")
    ap.add_argument("--round3", action="store_true", help="third round: fixed lambda x sizing")
    ap.add_argument("--round4", action="store_true", help="fourth round: stop-loss rules on the adopted settings")
    ap.add_argument("--round5", action="store_true", help="fifth round: vol scaling, rebalance cadence, breadth")
    ap.add_argument("--round6", action="store_true", help="sixth round: min conviction 0.15 combos")
    ap.add_argument("--round7", action="store_true", help="seventh round: contribution of momentum and SUE agents (use with --tag _v2)")
    ap.add_argument("--round8", action="store_true", help="eighth round: final sizing combos on the chosen agent set")
    ap.add_argument("--round9", action="store_true", help="ninth round: short book and index hedge")
    ap.add_argument("--round10", action="store_true", help="tenth round (2026-09-11): vol targeting, EWMA smoothing, no-learning, drop-one agents; run on _open500 with --exec open --oos-end 2025-09-24")
    ap.add_argument("--round11", action="store_true", help="eleventh round (2026-09-11): round-10 winners combined (vol target x no-events x horizons 10/20 x cap)")
    ap.add_argument("--round12", action="store_true", help="twelfth round (2026-09-11): inverse-vol sizing, drawdown brake, exit hysteresis, min hold, IC-weighted blend (150-name ledger _u150b)")
    ap.add_argument("--tag", default="", help="read state/backtest<tag>.sqlite instead of the default")
    ap.add_argument("--exec", dest="exec_mode", choices=("close", "open"), default="close", help="open = next-open execution (the live rule)")
    ap.add_argument("--oos-end", default=None, help="ISO date: report rows before it as out-of-sample, from it as in-sample")
    ap.add_argument("--workers", type=int, default=1, help="processes evaluating variants in parallel (16 cores here; 10 is comfortable)")
    ap.add_argument("--search", type=int, default=0, help="generational search: this many generations of --pop variants, mutating the best (needs --oos-end)")
    ap.add_argument("--pop", type=int, default=10)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    live_agents, live_h = config.AGENTS, config.HORIZONS
    config.AGENTS = PIT_AGENTS
    import ledger
    global DB
    if args.tag:
        DB = config.STATE_DIR / f"backtest{args.tag}.sqlite"
    ledger.DB = DB
    learner.MODEL_FILE = config.STATE_DIR / "sweep_model.json"

    pool, data = None, None
    if args.workers > 1:
        import multiprocessing as mp
        pool = mp.Pool(args.workers, initializer=_init_worker, initargs=(str(DB), args.exec_mode, PIT_AGENTS))
    else:
        by_date = load_signals()
        tickers = sorted({s.ticker for sigs in by_date.values() for s in sigs})
        closes = market.closes(tickers + [config.BENCHMARK, "SPY"], lookback_days=800, cache=False)
        closes = closes[closes[config.BENCHMARK].notna()]
        opens = market.opens(tickers + [config.BENCHMARK, "SPY"], lookback_days=800) if args.exec_mode == "open" else None
        data = (by_date, closes, opens)
    common = {"exec": args.exec_mode, "oos_end": args.oos_end}

    if args.search:
        if not args.oos_end:
            raise SystemExit("--search needs --oos-end (the objective uses both windows)")
        rng = random.Random(args.seed)
        out = config.STATE_DIR / f"backtest_search{args.tag}.json"
        trials = json.loads(out.read_text(encoding="utf-8"))["trials"] if out.exists() else []
        tried = {json.dumps({k: t["params"].get(k) for k in SPACE}, sort_keys=True) for t in trials}
        best = {"vol_target": config.VOL_TARGET, "size_k": config.SIZE_PER_CONVICTION, "min_conv": config.MIN_CONVICTION,
                "top_n": config.TOP_N, "cap": config.MAX_POSITION_PCT, "band": config.REBALANCE_BAND, "lam": config.LEARNER_PRIOR_STRENGTH,
                "half_life": config.LEARNER_HALF_LIFE_DAYS, "horizons": tuple(config.HORIZONS)}   # generation 0 = the live config
        for g in range(1, args.search + 1):
            key = json.dumps({k: best.get(k) for k in SPACE}, sort_keys=True)
            pop = ([("g%d_base" % g, dict(best))] if key not in tried else [])
            tried.add(key)
            pop += [("g%d_%d" % (g, i), kv) for i, kv in enumerate(mutate(best, rng, tried, args.pop - len(pop)), 1)]
            run_info = {"kind": "sweep", "tag": f"search{args.tag} gen {g}/{args.search}", "started": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            res = evaluate(pop, common, args.workers, run_info, pool=pool, data=data, log=list(trials))
            for r in res:
                r["generation"] = g
            trials += [{k: v for k, v in r.items() if k != "rets"} for r in res]
            objective(trials)
            trials.sort(key=lambda t: -t["objective"])
            out.write_text(json.dumps({"generated": date.today().isoformat(), "trials": trials}, indent=1), encoding="utf-8")
            top = trials[0]
            best = {k: (tuple(top["params"][k]) if isinstance(top["params"][k], list) else top["params"][k]) for k in SPACE}
            print("\n== generation %d: best so far %s objective %s | ret %+.3f sharpe %.2f dd %.3f | OOS ret %+.3f sharpe %.2f | %s\n" % (
                g, top["name"], top["objective"], top["total_return"], top["sharpe"], top["max_drawdown"],
                top["oos"]["total_return"], top["oos"]["sharpe"], json.dumps({k: best[k] for k in SPACE})), flush=True)
        config.AGENTS, config.HORIZONS = live_agents, live_h
        return

    if args.round10:
        v21 = {"lam": 150.0, "min_conv": 0.15, "size_k": 0.60, "top_n": 15, "band": 0.30}
        variants = [("v21", dict(v21)),
                    ("no_learning", dict(v21, learn=False)),
                    ("lam400", dict(v21, lam=400.0)),
                    ("lam1000", dict(v21, lam=1000.0)),
                    ("voltarget0.30", dict(v21, vol_target=0.30)),
                    ("voltarget0.40", dict(v21, vol_target=0.40)),
                    ("voltarget0.50", dict(v21, vol_target=0.50)),
                    ("ewma2", dict(v21, ewma_halflife=2)),
                    ("ewma3", dict(v21, ewma_halflife=3)),
                    ("ewma5", dict(v21, ewma_halflife=5)),
                    ("ewma3_voltarget0.40", dict(v21, ewma_halflife=3, vol_target=0.40)),
                    ("k0.45", dict(v21, size_k=0.45)),
                    ("cap0.15", dict(v21, cap=0.15)),
                    ("top20", dict(v21, top_n=20)),
                    ("h10_20", dict(v21, horizons=(10, 20)))]
        for a in PIT_AGENTS:
            variants.append((f"drop_{a}", dict(v21, agents_only=tuple(x for x in PIT_AGENTS if x != a))))
    elif args.round12:
        # the "Next" list of 2026-09-11 on the 150-name ledger: risk sizing, drawdown brake, hysteresis, minimum hold, IC blend
        v23 = {"lam": 150.0, "min_conv": 0.10, "size_k": 0.60, "top_n": 15, "cap": 0.15, "band": 0.30, "vol_target": 0.50, "horizons": (10, 20)}
        variants = [("v23", dict(v23)),
                    ("invvol_median", dict(v23, inv_vol="median")),
                    ("invvol_0.40", dict(v23, inv_vol=0.40)),
                    ("invvol_0.60", dict(v23, inv_vol=0.60)),
                    ("volscale_r5", dict(v23, vol_scale=True)),
                    ("ddbrake_10_50_5", dict(v23, dd_brake=(0.10, 0.5, 0.05))),
                    ("ddbrake_15_50_5", dict(v23, dd_brake=(0.15, 0.5, 0.05))),
                    ("ddbrake_10_30_5", dict(v23, dd_brake=(0.10, 0.3, 0.05))),
                    ("ddbrake_20_50_10", dict(v23, dd_brake=(0.20, 0.5, 0.10))),
                    ("exit_0.05", dict(v23, exit_conv=0.05)),
                    ("exit_0.07", dict(v23, exit_conv=0.07)),
                    ("hold3", dict(v23, min_hold=3)),
                    ("hold5", dict(v23, min_hold=5)),
                    ("exit_0.05_hold3", dict(v23, exit_conv=0.05, min_hold=3)),
                    ("ic_blend", dict(v23, learn="ic"))]
    elif args.round11:
        # round 10's single-knob winners (each better in BOTH windows), combined: do they still hold together?
        v21 = {"lam": 150.0, "min_conv": 0.15, "size_k": 0.60, "top_n": 15, "band": 0.30}
        no_ev = tuple(x for x in PIT_AGENTS if x != "events")
        variants = [("v21", dict(v21)),
                    ("vt50", dict(v21, vol_target=0.50)),
                    ("vt50_h10_20", dict(v21, vol_target=0.50, horizons=(10, 20))),
                    ("vt50_noevents", dict(v21, vol_target=0.50, agents_only=no_ev)),
                    ("vt50_cap0.15", dict(v21, vol_target=0.50, cap=0.15)),
                    ("vt50_noevents_h10_20", dict(v21, vol_target=0.50, agents_only=no_ev, horizons=(10, 20))),
                    ("vt50_noevents_h10_20_cap0.15", dict(v21, vol_target=0.50, agents_only=no_ev, horizons=(10, 20), cap=0.15)),
                    ("noevents_h10_20_cap0.15", dict(v21, agents_only=no_ev, horizons=(10, 20), cap=0.15)),
                    ("vt40_noevents_h10_20", dict(v21, vol_target=0.40, agents_only=no_ev, horizons=(10, 20))),
                    ("vt60_noevents_h10_20", dict(v21, vol_target=0.60, agents_only=no_ev, horizons=(10, 20)))]
    elif args.round2:
        variants = [("hl90_base", {})]
        for lam in (20.0, 50.0, 150.0, 400.0):
            variants.append((f"hl90_lam{int(lam)}", {"lam": lam}))
        for k, cap, band in ((0.45, 0.10, 0.15), (0.45, 0.10, 0.30), (0.45, 0.15, 0.15), (0.30, 0.15, 0.15), (0.30, 0.10, 0.30)):
            variants.append((f"hl90_k{k}_cap{cap}_band{band}", {"size_k": k, "cap": cap, "band": band}))
        variants.append(("hl90_lam50_k0.45", {"lam": 50.0, "size_k": 0.45}))
        variants.append(("hl120", {"half_life": 120}))
        variants.append(("hl180", {"half_life": 180}))
    elif args.round4:
        base4 = {"lam": 150.0, "size_k": 0.45, "band": 0.30}
        variants = [("current", dict(base4))]
        for sl in (0.06, 0.08, 0.12, 0.20):
            variants.append((f"stop{int(sl*100)}", dict(base4, stop_loss=sl)))
        variants.append(("stop8_cool10", dict(base4, stop_loss=0.08, cooldown=10)))
    elif args.round5:
        base5 = {"lam": 150.0, "size_k": 0.45, "band": 0.30}
        variants = [("current", dict(base5)),
                    ("vol_scale", dict(base5, vol_scale=True)),
                    ("vol_scale_k0.6", dict(base5, vol_scale=True, size_k=0.60)),
                    ("rebal2", dict(base5, rebalance_every=2)),
                    ("rebal3", dict(base5, rebalance_every=3)),
                    ("band0.5", dict(base5, band=0.50)),
                    ("top10", dict(base5, top_n=10)),
                    ("top20", dict(base5, top_n=20)),
                    ("top20_cap0.08", dict(base5, top_n=20, cap=0.08)),
                    ("minconv0.05", dict(base5, min_conv=0.05)),
                    ("minconv0.15", dict(base5, min_conv=0.15)),
                    ("h5_10_only", dict(base5, horizons=(5, 10)))]
    elif args.round6:
        base6 = {"lam": 150.0, "size_k": 0.45, "band": 0.30, "min_conv": 0.15}
        variants = [("current_mc0.10", {"lam": 150.0, "size_k": 0.45, "band": 0.30}),
                    ("mc0.15", dict(base6)),
                    ("mc0.15_top20", dict(base6, top_n=20)),
                    ("mc0.15_rebal3", dict(base6, rebalance_every=3)),
                    ("mc0.15_rebal2", dict(base6, rebalance_every=2)),
                    ("mc0.15_band0.5", dict(base6, band=0.50)),
                    ("mc0.20", dict(base6, min_conv=0.20)),
                    ("mc0.15_k0.6", dict(base6, size_k=0.60)),
                    ("mc0.15_top20_rebal3", dict(base6, top_n=20, rebalance_every=3))]
    elif args.round7:
        seven = ("supply_chain", "neighbors", "technical", "mean_reversion", "events", "risk", "macro")
        b = {"lam": 150.0, "size_k": 0.45, "band": 0.30, "min_conv": 0.15}
        variants = [("nine_agents", dict(b)),
                    ("seven_agents", dict(b, agents_only=seven)),
                    ("no_momentum", dict(b, agents_only=seven + ("sue",))),
                    ("no_sue", dict(b, agents_only=seven + ("momentum",))),
                    ("nine_top20", dict(b, top_n=20)),
                    ("nine_mc0.10", dict(b, min_conv=0.10)),
                    ("momentum_only", dict(b, learn=False, agents_only=("momentum",))),
                    ("sue_only", dict(b, learn=False, agents_only=("sue",)))]
    elif args.round8:
        variants = []
        for k in (0.45, 0.60):
            for top in (15, 20):
                for band in (0.30, 0.50):
                    variants.append((f"mc0.15_k{k}_top{top}_band{band}", {"lam": 150.0, "min_conv": 0.15, "size_k": k, "top_n": top, "band": band}))
        variants.append(("mc0.15_k0.6_top20_cap0.12", {"lam": 150.0, "min_conv": 0.15, "size_k": 0.60, "top_n": 20, "cap": 0.12}))
        for m in (0.0, 0.05, 0.10):
            variants.append((f"mc0.15_k0.6_top20_swap{m}", {"lam": 150.0, "min_conv": 0.15, "size_k": 0.60, "top_n": 20, "swap_margin": m}))
    elif args.round9:
        b = {"lam": 150.0, "min_conv": 0.15, "size_k": 0.60, "top_n": 20}
        variants = [("long_only", dict(b)),
                    ("ls_short5_g0.2", dict(b, short_k=5, short_gross=0.20)),
                    ("ls_short10_g0.3", dict(b, short_k=10, short_gross=0.30)),
                    ("ls_short10_g0.5", dict(b, short_k=10, short_gross=0.50)),
                    ("hedge_below50_0.3", dict(b, hedge="below50", hedge_size=0.30)),
                    ("hedge_below50_0.5", dict(b, hedge="below50", hedge_size=0.50)),
                    ("hedge_always_0.3", dict(b, hedge="always", hedge_size=0.30)),
                    ("ls_short5_plus_hedge", dict(b, short_k=5, short_gross=0.20, hedge="below50", hedge_size=0.30))]
    elif args.round3:
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
    if not args.quick and not (args.round2 or args.round3 or args.round4 or args.round5 or args.round6 or args.round7 or args.round8 or args.round9 or args.round10 or args.round11 or args.round12):
        for combo in itertools.product(*GRID.values()):
            kv = dict(zip(GRID.keys(), combo))
            if kv == {k: BASE[k] for k in GRID}:
                continue
            variants.append(("+".join(f"{k}={v}" for k, v in kv.items()), kv))
    tag = ("2" if args.round2 else "3" if args.round3 else "4" if args.round4 else "5" if args.round5 else "6" if args.round6 else "7" if args.round7 else "8" if args.round8 else "9" if args.round9 else "10" if args.round10 else "11" if args.round11 else "12" if args.round12 else "") + args.tag
    run_info = {"kind": "sweep", "tag": tag, "total": len(variants), "started": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    t0 = time.time()
    results = evaluate(variants, common, args.workers, run_info, pool=pool, data=data)
    config.AGENTS, config.HORIZONS = live_agents, live_h
    # robust ranking: Sharpe first, then excess vs SOXX, penalise turnover
    for r in results:
        r["score"] = round(r["sharpe"] + 0.5 * r["excess_vs_soxx"] - 0.5 * r["turnover_per_day"], 3)
    results.sort(key=lambda r: -r["score"])
    # probability of backtest overfitting across this round's variants (CSCV on their daily returns)
    T = min(len(r["rets"]) for r in results)
    overfit = robustness.pbo(np.array([r["rets"][:T] for r in results]).T) if len(results) >= 2 else None
    out = OUT if not tag else config.STATE_DIR / f"backtest_sweep{tag}.json"
    out.write_text(json.dumps({"generated": date.today().isoformat(), "pbo": overfit, "results": results}, indent=2), encoding="utf-8")
    print("\nTOP 5 by score (sharpe + 0.5*excess - 0.5*turnover):")
    for r in results[:5]:
        print(f"  {r['score']:6.3f} {r['name']}")
    print("PBO (probability the in-sample winner is below the out-of-sample median):", overfit)
    backtest.publish_progress(dict(run_info, status="done", pct=1.0, done=len(results), elapsed_s=round(time.time() - t0), eta_s=0,
                                   pbo=overfit, results=[{kk: v for kk, v in x.items() if kk != "rets"} for x in results]))
    if args.apply:
        (config.STATE_DIR / "sweep_best.json").write_text(json.dumps(results[0], indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
