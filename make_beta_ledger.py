"""Beta-adjusted learning target: copy a finished ledger and populate the parallel
`beta_abnormal` label as ret - beta_i * bench_ret, where beta_i is the name's
60-day beta to SOXX as of the prediction date (point in time).

The learner then learns stock selection net of each name's market exposure instead of "beat SOXX", which mixes
selection with beta timing. Evaluation inside sweep.py (IC, quintiles, returns) still uses raw returns vs SOXX, so only
the training target changes.

    python make_beta_ledger.py --ledger _v24      # -> state/backtest_beta.sqlite
"""
import argparse
import shutil
import sqlite3
from datetime import date

import numpy as np
import pandas as pd

import config
import ledger
import market
import universe as universe_mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", default="_v24")
    ap.add_argument("--output-tag", default="_beta")
    ap.add_argument("--window", type=int, default=60)
    args = ap.parse_args()
    src = config.STATE_DIR / f"backtest{args.ledger}.sqlite"
    dst = config.STATE_DIR / f"backtest{args.output_tag}.sqlite"
    shutil.copy2(src, dst)
    tickers = list(universe_mod.load())
    con = sqlite3.connect(src)
    first_date = con.execute("SELECT MIN(date) FROM predictions").fetchone()[0]
    con.close()
    lookback = max(1000, (date.today() - date.fromisoformat(first_date)).days + 400)
    closes = market.closes(tickers + [config.BENCHMARK], lookback_days=lookback, cache=False)
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
    ledger._migrate(con)
    rows = con.execute("SELECT s.prediction_id AS pid, s.horizon AS h, s.ret AS ret, s.bench_ret AS bench_ret, p.date AS date, p.ticker AS ticker "
                       "FROM scores s JOIN predictions p ON p.id = s.prediction_id").fetchall()
    updates, n_default = [], 0
    for r in rows:
        i = pos.get(r["date"])
        b = float(beta[r["ticker"]].iloc[i]) if (i is not None and r["ticker"] in beta.columns) else np.nan
        if not np.isfinite(b):
            b, n_default = 1.0, n_default + 1
        b = float(np.clip(b, 0.0, 3.0))
        updates.append((b, r["ret"] - b * r["bench_ret"], r["pid"], r["h"]))
    con.executemany("UPDATE predictions SET benchmark_beta = ? WHERE id = ?",
                    [(b, pid) for b, _, pid, _ in updates])
    con.executemany("UPDATE scores SET beta_abnormal = ? WHERE prediction_id = ? AND horizon = ?",
                    [(target, pid, h) for _, target, pid, h in updates])
    con.commit()
    con.close()
    print(f"populated {len(updates)} parallel beta targets ({n_default} defaulted to beta 1) -> {dst.name}")


if __name__ == "__main__":
    main()
