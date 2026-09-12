"""Backfill point-in-time beta targets without modifying the original raw labels.

The command makes timestamped database backups before applying changes. It is
safe to rerun: stored prediction betas are retained and beta labels are derived
from those stored values.
"""
from __future__ import annotations

import argparse
import sqlite3
import math
from contextlib import closing
from datetime import date, datetime
from pathlib import Path

import config
import learning_targets
import ledger
import market
import pandas as pd


def backup_database(path):
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = path.with_name(f"{path.name}.pre-beta-{stamp}.bak")
    with closing(sqlite3.connect(path)) as source, closing(sqlite3.connect(backup)) as destination:
        source.backup(destination)
    return backup


def database_inventory(paths):
    first, tickers = None, set()
    for path in paths:
        if not path.exists():
            continue
        con = sqlite3.connect(path)
        row = con.execute("SELECT MIN(date) FROM predictions").fetchone()
        tickers.update(r[0] for r in con.execute("SELECT DISTINCT ticker FROM predictions"))
        con.close()
        if row and row[0] and (first is None or row[0] < first):
            first = row[0]
    return first, sorted(tickers)


def migrate_db(path: Path, closes, make_backup=True, *, pre_open=False):
    if make_backup:
        backup_database(path)
    if config.BENCHMARK not in closes or closes[config.BENCHMARK].notna().sum() < 41:
        raise ValueError("insufficient benchmark history for beta migration")
    betas = learning_targets.rolling_beta(closes)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        con.execute("BEGIN IMMEDIATE")
        ledger._migrate(con)
        rows = con.execute("SELECT id,date,ticker,benchmark_beta FROM predictions").fetchall()
        beta_updates = []
        values = {}
        for row in rows:
            beta = row["benchmark_beta"]
            if beta is None:
                key = (row["date"], row["ticker"])
                if key not in values:
                    if row["ticker"] not in closes.columns:
                        raise ValueError(f"missing prices for {row['ticker']}")
                    if betas.index.searchsorted(pd.Timestamp(row["date"]), side="left" if pre_open else "right") < 41:
                        raise ValueError(f"insufficient trailing history for {row['date']}")
                    values[key] = learning_targets.beta_at(betas, row["ticker"], row["date"], before=pre_open)
                beta_updates.append((values[key], row["id"]))
        con.executemany("UPDATE predictions SET benchmark_beta = ? WHERE id = ?", beta_updates)
        score_updates = con.execute(
            "UPDATE scores SET beta_abnormal = ret - "
            "(SELECT benchmark_beta FROM predictions WHERE predictions.id = scores.prediction_id) * bench_ret "
            "WHERE beta_abnormal IS NULL"
        ).rowcount
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    return len(beta_updates), score_updates


def migrate_db_from_beta_ledger(path: Path, beta_path: Path, make_backup=True):
    """Copy the exact researched beta labels into parallel columns of their raw source ledger."""
    if make_backup:
        backup_database(path)
    if path.resolve() == beta_path.resolve():
        raise ValueError("raw and beta source must be different databases")
    con = sqlite3.connect(path)
    try:
        con.execute("ATTACH DATABASE ? AS beta_src", (str(beta_path),))
        con.execute("BEGIN IMMEDIATE")
        # Identity includes the prediction itself, not merely coincidentally equal returns.
        for table, columns in (("predictions", "id,date,agent,ticker,direction,confidence,horizon,reason,price_at"),
                               ("scores", "prediction_id,horizon,scored_date,ret,bench_ret,hit")):
            for first, second in (("main", "beta_src"), ("beta_src", "main")):
                if con.execute(f"SELECT {columns} FROM {first}.{table} EXCEPT "
                               f"SELECT {columns} FROM {second}.{table} LIMIT 1").fetchone():
                    raise ValueError(f"beta ledger does not match raw {table}")
        source_columns = {r[1] for r in con.execute("PRAGMA beta_src.table_info(scores)")}
        beta_column = "beta_abnormal" if "beta_abnormal" in source_columns else "abnormal"
        beta_rows = con.execute(f"SELECT prediction_id,horizon,ret,bench_ret,{beta_column} FROM beta_src.scores "
                                "ORDER BY prediction_id,horizon").fetchall()
        inferred = {}
        for pid, horizon, ret, bench_ret, target in beta_rows:
            if any(v is None or not math.isfinite(v) for v in (ret, bench_ret, target)):
                raise ValueError("non-finite beta source label")
            if abs(bench_ret) > 1e-12:
                beta = (ret - target) / bench_ret
                if not -1e-8 <= beta <= 3.0 + 1e-8:
                    raise ValueError("beta source outside research bounds")
                if pid in inferred and abs(inferred[pid] - beta) > 1e-7:
                    raise ValueError("inconsistent prediction beta across horizons")
                inferred[pid] = min(3.0, max(0.0, beta))
        ledger._migrate(con)
        con.execute(f"UPDATE scores SET beta_abnormal = (SELECT b.{beta_column} FROM beta_src.scores b "
                    "WHERE b.prediction_id=scores.prediction_id AND b.horizon=scores.horizon) "
                    "WHERE beta_abnormal IS NULL")
        con.executemany("UPDATE predictions SET benchmark_beta = ? WHERE id = ? AND benchmark_beta IS NULL",
                        [(b, pid) for pid, b in inferred.items()])
        raw_n = len(beta_rows)
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    return raw_n


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", action="append", type=Path,
                        help="database to migrate; repeat for multiple files")
    parser.add_argument("--beta-source", type=Path,
                        help="finished research beta ledger matching a single raw --db")
    parser.add_argument("--closes-pickle", type=Path,
                        help="existing close-price DataFrame cache; avoids a new download")
    parser.add_argument("--apply", action="store_true", help="make backups and apply the migration")
    parser.add_argument("--pre-open", action="store_true", help="use only sessions before a live prediction date")
    args = parser.parse_args()
    paths = args.db or [config.STATE_DIR / "ledger.sqlite", config.STATE_DIR / "backtest.sqlite"]
    paths = [path.resolve() for path in paths if path.exists()]
    first, tickers = database_inventory(paths)
    if not paths or not first:
        raise SystemExit("no scored prediction databases found")
    print(f"databases={len(paths)} tickers={len(tickers)} first_prediction={first}")
    if not args.apply:
        print("dry run only; rerun with --apply to back up and migrate")
        return
    if args.beta_source:
        if len(paths) != 1:
            raise SystemExit("--beta-source requires exactly one --db")
        scores = migrate_db_from_beta_ledger(paths[0], args.beta_source.resolve(), make_backup=True)
        print(f"{paths[0].name}: imported {scores} exact researched beta scores")
        return
    lookback = max(1000, (date.today() - date.fromisoformat(first)).days + 400)
    closes = pd.read_pickle(args.closes_pickle) if args.closes_pickle else market.closes(
        tickers + [config.BENCHMARK], lookback_days=lookback, cache=False)
    for path in paths:
        predictions, scores = migrate_db(path, closes, make_backup=True,
                                         pre_open=args.pre_open or path.name == "ledger.sqlite")
        print(f"{path.name}: beta predictions={predictions}, beta scores={scores}")


if __name__ == "__main__":
    main()
