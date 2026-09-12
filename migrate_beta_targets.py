"""Backfill point-in-time beta targets without modifying the original raw labels.

The command makes timestamped database backups before applying changes. It is
safe to rerun: stored prediction betas are retained and beta labels are derived
from those stored values.
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import date, datetime
from pathlib import Path

import config
import learning_targets
import ledger
import market
import pandas as pd


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


def migrate_db(path: Path, closes, make_backup=True):
    if make_backup:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(path, path.with_name(f"{path.name}.pre-beta-{stamp}.bak"))
    betas = learning_targets.rolling_beta(closes)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    ledger._migrate(con)
    rows = con.execute("SELECT id,date,ticker,benchmark_beta FROM predictions").fetchall()
    beta_updates = []
    for row in rows:
        beta = row["benchmark_beta"]
        if beta is None:
            beta = learning_targets.beta_at(betas, row["ticker"], row["date"])
            beta_updates.append((beta, row["id"]))
    con.executemany("UPDATE predictions SET benchmark_beta = ? WHERE id = ?", beta_updates)
    score_updates = con.execute(
        "UPDATE scores SET beta_abnormal = ret - "
        "(SELECT benchmark_beta FROM predictions WHERE predictions.id = scores.prediction_id) * bench_ret "
        "WHERE beta_abnormal IS NULL"
    ).rowcount
    con.commit()
    con.close()
    return len(beta_updates), score_updates


def migrate_db_from_beta_ledger(path: Path, beta_path: Path, make_backup=True):
    """Copy the exact researched beta labels into parallel columns of their raw source ledger."""
    if make_backup:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(path, path.with_name(f"{path.name}.pre-beta-{stamp}.bak"))
    con = sqlite3.connect(path)
    ledger._migrate(con)
    con.execute("ATTACH DATABASE ? AS beta_src", (str(beta_path),))
    raw_n = con.execute("SELECT COUNT(*) FROM scores").fetchone()[0]
    beta_n = con.execute("SELECT COUNT(*) FROM beta_src.scores").fetchone()[0]
    mismatched = con.execute(
        "SELECT COUNT(*) FROM scores s LEFT JOIN beta_src.scores b "
        "ON b.prediction_id=s.prediction_id AND b.horizon=s.horizon "
        "WHERE b.prediction_id IS NULL OR b.ret != s.ret OR b.bench_ret != s.bench_ret"
    ).fetchone()[0]
    if raw_n != beta_n or mismatched:
        con.close()
        raise ValueError(f"beta ledger does not match raw ledger ({raw_n=} {beta_n=} {mismatched=})")
    con.execute(
        "UPDATE scores SET beta_abnormal = (SELECT b.abnormal FROM beta_src.scores b "
        "WHERE b.prediction_id=scores.prediction_id AND b.horizon=scores.horizon)"
    )
    con.execute(
        "UPDATE predictions SET benchmark_beta = COALESCE((SELECT (s.ret-b.abnormal)/s.bench_ret "
        "FROM scores s JOIN beta_src.scores b ON b.prediction_id=s.prediction_id AND b.horizon=s.horizon "
        "WHERE s.prediction_id=predictions.id AND ABS(s.bench_ret)>1e-12 ORDER BY s.horizon LIMIT 1), 1.0)"
    )
    con.commit()
    con.execute("DETACH DATABASE beta_src")
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
        predictions, scores = migrate_db(path, closes, make_backup=True)
        print(f"{path.name}: beta predictions={predictions}, beta scores={scores}")


if __name__ == "__main__":
    main()
