"""Entry-time study: when during the session should the daily book be traded?

Uses the stored backtest opinions (state/backtest.sqlite), the same walk-forward
learner and sizing as the live system, and two years of FREE hourly bars from
yfinance. For each candidate entry hour h the book decided from day t's
signals is traded on day t+1 at h and held until t+2 at h (daily rebalance at
the same hour), with 5 bps per unit turnover. The first column, "close_t",
reproduces the sweep's (optimistic) assumption of trading at the close of the
signal day itself, which live execution cannot do.

    python timing.py            -> prints a table, writes state/timing_report.json
"""
import json
import math
import sqlite3
from datetime import date, timedelta

import numpy as np
import pandas as pd
import yfinance as yf

import config
import ledger
import learner
import universe as universe_mod
from agents.base import Signal

DB = config.STATE_DIR / "backtest.sqlite"
OUT = config.STATE_DIR / "timing_report.json"
PIT_AGENTS = ["supply_chain", "neighbors", "technical", "mean_reversion", "events", "risk", "macro"]
HOURS = ["09:30", "10:30", "11:30", "12:30", "13:30", "14:30", "15:30", "close"]
SIZING = dict(min_conv=0.15, size_k=0.60, cap=0.10, gross=1.50, top_n=15)


def load_signals():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT date, ticker, agent, direction, confidence, horizon FROM predictions ORDER BY date").fetchall()
    con.close()
    by_date = {}
    for r in rows:
        by_date.setdefault(r["date"], []).append(Signal(r["agent"], r["ticker"], r["direction"], r["confidence"], r["horizon"], ""))
    return by_date


def convictions_by_date(by_date, refit_every=5, warmup=30):
    """Walk-forward learner exactly as in the sweep: {date: {ticker: conviction}}."""
    out, model = {}, None
    dates = sorted(by_date)
    for k, d in enumerate(dates):
        if k < warmup:
            continue
        if model is None or k % refit_every == 0:
            model = learner.fit(date.fromisoformat(d), asof=date.fromisoformat(d))
        conv, _ = learner.predict(by_date[d], model)
        out[d] = conv
    return out


def targets(conv):
    longs = sorted(((t, c) for t, c in conv.items() if c >= SIZING["min_conv"]), key=lambda tc: -tc[1])[:SIZING["top_n"]]
    w = {t: min(c * SIZING["size_k"], SIZING["cap"]) for t, c in longs}
    g = sum(w.values())
    if g > SIZING["gross"]:
        w = {t: x * SIZING["gross"] / g for t, x in w.items()}
    return w


def price_grid(tickers):
    """{hour: DataFrame(date x ticker)} of tradable prices at that hour (bar open; 'close' = last bar close)."""
    raw = yf.download(tickers + [config.BENCHMARK], period="730d", interval="60m", auto_adjust=True, progress=False, threads=True)
    opens, closes = raw["Open"], raw["Close"]
    idx = opens.index.tz_convert("America/New_York")
    grids = {}
    for h in HOURS:
        if h == "close":
            sel = closes[(idx.hour == 15) & (idx.minute == 30)].copy()
        else:
            hh, mm = map(int, h.split(":"))
            sel = opens[(idx.hour == hh) & (idx.minute == mm)].copy()
        sel.index = pd.to_datetime(sel.index.tz_convert("America/New_York").date)
        grids[h] = sel[~sel.index.duplicated(keep="first")]
    return grids


def simulate(convs, grid, lag_days=1):
    """Trade the book from day t's convictions at the grid's hour on t+lag, hold to the next grid row."""
    days = list(grid.index)
    pos = {d.date().isoformat() if hasattr(d, "date") else str(d): i for i, d in enumerate(days)}
    equity, prev_w, turn_total, rets = 1.0, {}, 0.0, []
    for d, conv in sorted(convs.items()):
        if d not in pos:
            continue
        i = pos[d] + lag_days
        if i + 1 >= len(days):
            break
        w = targets(conv)
        turnover = sum(abs(w.get(t, 0) - prev_w.get(t, 0)) for t in set(w) | set(prev_w))
        r = 0.0
        for t, wt in w.items():
            if t not in grid.columns:
                continue
            p0, p1 = grid[t].iloc[i], grid[t].iloc[i + 1]
            if not (pd.isna(p0) or pd.isna(p1) or p0 <= 0):
                r += wt * (float(p1 / p0) - 1)
        r -= turnover * config.COST_BPS / 10_000
        equity *= 1 + r
        rets.append(math.log(1 + r) if r > -1 else -5)
        turn_total += turnover
        prev_w = w
    n = len(rets) or 1
    return {"total_return": round(equity - 1, 4), "sharpe": round(float(np.mean(rets) / (np.std(rets) or 1e-9) * math.sqrt(252)), 2),
            "days": n, "turnover_per_day": round(turn_total / n, 3)}


def main():
    live_agents, live_h = config.AGENTS, config.HORIZONS
    config.AGENTS = PIT_AGENTS
    ledger.DB = DB
    learner.MODEL_FILE = config.STATE_DIR / "timing_model.json"
    by_date = load_signals()
    convs = convictions_by_date(by_date)
    tickers = sorted({s.ticker for sigs in by_date.values() for s in sigs})
    grids = price_grid(tickers)
    config.AGENTS, config.HORIZONS = live_agents, live_h

    results = {}
    # sweep-style optimistic reference: trade at the close of the signal day (lag 0 on the close grid)
    results["close_t (sweep assumption)"] = simulate(convs, grids["close"], lag_days=0)
    for h in HOURS:
        results[f"{h} on t+1"] = simulate(convs, grids[h], lag_days=1)
    # descriptive: average intraday path of the universe (equal-weight), in bps
    path = {}
    for a, b in zip(HOURS[:-1], HOURS[1:]):
        ga, gb = grids[a].align(grids[b], join="inner")
        rr = (gb / ga - 1).mean(axis=1)
        path[f"{a}->{b}"] = round(float(rr.mean() * 1e4), 1)
    close_g, open_g = grids["close"].align(grids["09:30"], join="inner")
    overnight = (open_g.shift(-1) / close_g - 1).mean(axis=1)
    path["close->next open (overnight)"] = round(float(overnight.mean() * 1e4), 1)

    for k, v in results.items():
        print(f"{k:28} ret {v['total_return']:+.3f} sharpe {v['sharpe']:5.2f} days {v['days']} turn {v['turnover_per_day']}")
    print("average intraday path (bps, equal-weight universe):", path)
    OUT.write_text(json.dumps({"generated": date.today().isoformat(), "results": results, "intraday_path_bps": path,
                               "sizing": SIZING}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
