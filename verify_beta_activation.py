"""Verify migrated ledgers and fit candidate models without broker/LLM calls.

Candidate outputs do not replace model.json. The caller promotes them only after
this command and all data-preservation checks succeed.
"""
import argparse
import json
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

import numpy as np

import config
import learner
import ledger


def preserved(path, reference):
    with closing(sqlite3.connect(path)) as con:
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        con.execute("ATTACH DATABASE ? AS ref", (str(reference),))
        for table in ("predictions", "scores", "weights", "hedge_weights", "cycles", "orders"):
            columns = [r[1] for r in con.execute(f"PRAGMA ref.table_info({table})")]
            if not columns:
                continue
            fields = ",".join(f'"{col}"' for col in columns)
            for first, second in (("main", "ref"), ("ref", "main")):
                assert con.execute(f"SELECT {fields} FROM {first}.{table} EXCEPT "
                                   f"SELECT {fields} FROM {second}.{table} LIMIT 1").fetchone() is None, table
        return {"predictions": con.execute("SELECT COUNT(*) FROM predictions").fetchone()[0],
                "scores": con.execute("SELECT COUNT(*) FROM scores").fetchone()[0],
                "beta_scores": con.execute("SELECT COUNT(*) FROM scores WHERE beta_abnormal IS NOT NULL").fetchone()[0],
                "prediction_betas": con.execute("SELECT COUNT(*) FROM predictions WHERE benchmark_beta IS NOT NULL").fetchone()[0]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", required=True, type=Path)
    parser.add_argument("--raw-reference", required=True, type=Path)
    parser.add_argument("--live-reference", required=True, type=Path)
    parser.add_argument("--beta-reference", required=True, type=Path)
    args = parser.parse_args()
    root = args.state_dir.resolve()
    config.STATE_DIR = root
    ledger.DB = root / "ledger.sqlite"
    learner.MODEL_FILE = root / "model.json"
    learner._CACHE.clear()
    report = {"date": date.today().isoformat(), "vol_target": config.VOL_TARGET, "paper": config.PAPER}
    assert config.PAPER is True and config.VOL_TARGET == 0.50
    report["live"] = preserved(ledger.DB, args.live_reference)
    report["warm_start"] = preserved(root / "backtest.sqlite", args.raw_reference)
    assert report["warm_start"]["scores"] == report["warm_start"]["beta_scores"]
    print("Original predictions, scores, orders and weights preserved; SQLite integrity passes.", flush=True)
    names = learner.agents()
    report["parity"] = {}
    for h in config.HORIZONS:
        for mode, reference in (("raw", args.raw_reference), ("beta", args.beta_reference)):
            migrated = learner._load_source(root / "backtest.sqlite", 0.5, h, names, mode)
            legacy = learner._load_source(reference, 0.5, h, names, "raw")
            for actual, expected in zip(migrated, legacy):
                np.testing.assert_array_equal(actual, expected)
            report["parity"][f"{mode}_{h}d"] = len(migrated[1])
    print("Every raw and beta learner input exactly matches the corresponding research ledger.", flush=True)
    report["models"] = {}
    for mode in ("beta", "raw"):
        path = root / f"model_{mode}_candidate.json"
        model = learner.fit(date.today(), asof=date.today(), target_mode=mode, model_file=path)
        report["models"][mode] = {"path": str(path), "horizons": {
            h: {k: v[k] for k in ("n_obs", "n_dates", "scale", "cv_ic")}
            for h, v in model["horizons"].items()}}
        print(f"{mode} candidate fitted: " + str(report["models"][mode]["horizons"]), flush=True)
    report["complete"] = True
    report_path = root / "beta_activation_verification.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("PASS: candidate models verified; no orders submitted.", flush=True)


if __name__ == "__main__":
    main()
