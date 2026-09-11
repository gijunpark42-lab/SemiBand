"""Beta-adjusted learning target: copy a finished ledger and rewrite every score's `abnormal` as
ret - beta_i * bench_ret, where beta_i is the name's 60-day beta to SOXX as of the prediction date (point in time).

The learner then learns stock selection net of each name's market exposure instead of "beat SOXX", which mixes
selection with beta timing. Evaluation inside sweep.py (IC, quintiles, returns) still uses raw returns vs SOXX, so only
the training target changes.

    python make_beta_ledger.py --ledger _v24      # -> state/backtest_beta.sqlite
"""
import argparse
import shutil
import sqlite3

import numpy as np
import pandas as pd

import config
import market
import universe as universe_mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", default="_v24")
    ap.add_argument("--window", type=int, default=60)
    args = ap.parse_args()
    src = config.STATE_DIR / f"backtest{args.ledger}.sqlite"
    dst = config.STATE_DIR / "backtest_beta.sqlite"
    shutil.copy2(src, dst)
    tickers = list(universe_mod.load())
    closes = market.closes(tickers + [config.BENCHMARK], lookback_days=1000, cache=False)
    closes = closes[closes[config.BENCHMARK].notna()]
    rets = closes.pct_change()
    bench = rets[config.BENCHMARK]
    # rolling beta per name, aligned so beta at date d uses returns up to and including d
    cov = rets.rolling(args.window, min_periods=40).cov(bench)
    var = bench.rolling(args.window, min_periods=40).var()
    beta = cov.div(var, axis=0)
    pos = {d.date().isoformat(): i for i, d in enumerate(closes.index)}
    con = sqlite3.connect(dst)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT s.prediction_id AS pid, s.horizon AS h, s.ret AS ret, s.bench_ret AS bench_ret, p.date AS date, p.ticker AS ticker "
                       "FROM scores s JOIN predictions p ON p.id = s.prediction_id").fetchall()
    updates, n_default = [], 0
    for r in rows:
        i = pos.get(r["date"])
        b = float(beta[r["ticker"]].iloc[i]) if (i is not None and r["ticker"] in beta.columns) else np.nan
        if not np.isfinite(b):
            b, n_default = 1.0, n_default + 1
        b = float(np.clip(b, 0.0, 3.0))
        updates.append((r["ret"] - b * r["bench_ret"], r["pid"], r["h"]))
    con.executemany("UPDATE scores SET abnormal = ? WHERE prediction_id = ? AND horizon = ?", updates)
    con.commit()
    con.close()
    print(f"rewrote {len(updates)} scores with beta-adjusted targets ({n_default} defaulted to beta 1) -> {dst.name}")


if __name__ == "__main__":
    main()
