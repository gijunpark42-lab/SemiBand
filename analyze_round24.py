"""Paired moving-block diagnostics for the frozen round-24 candidate.

Uses the rounded daily log returns saved by sweep.py. This is an exploratory dependence-aware
diagnostic, not a new holdout and not a replacement for prospective paper validation.
"""
import argparse
import json
import math
import sqlite3
from pathlib import Path

import numpy as np


def named(path, name):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return next(r for r in data["results"] if r["name"] == name)


def sharpe(x):
    return float(np.mean(x) / (np.std(x) or 1e-12) * math.sqrt(252))


def max_drawdown(log_rets):
    eq = np.r_[1.0, np.exp(np.cumsum(log_rets))]
    return float(np.max(1 - eq / np.maximum.accumulate(eq)))


def paired_blocks(base, candidate, block, draws, rng):
    n = len(base)
    out = []
    for _ in range(draws):
        starts = rng.integers(0, n, size=math.ceil(n / block))
        idx = np.concatenate([(np.arange(s, s + block) % n) for s in starts])[:n]
        b, c = base[idx], candidate[idx]
        out.append((sharpe(c) - sharpe(b), float(np.sum(c - b)), max_drawdown(c) - max_drawdown(b)))
    a = np.asarray(out)
    return {
        "block_days": block,
        "draws": draws,
        "delta_sharpe_ci95": [round(float(x), 3) for x in np.quantile(a[:, 0], [0.025, 0.975])],
        "p_delta_sharpe_positive": round(float(np.mean(a[:, 0] > 0)), 3),
        "delta_log_return_ci95": [round(float(x), 3) for x in np.quantile(a[:, 1], [0.025, 0.975])],
        "delta_max_drawdown_ci95": [round(float(x), 3) for x in np.quantile(a[:, 2], [0.025, 0.975])],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--beta", required=True)
    ap.add_argument("--raw-ledger", required=True)
    ap.add_argument("--beta-ledger", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    candidate_result = named(args.beta, "vol_target_040")
    candidate = np.asarray(candidate_result["rets"], dtype=float)
    def ledger_dates(path):
        con = sqlite3.connect(path)
        dates = [r[0] for r in con.execute("SELECT DISTINCT date FROM predictions ORDER BY date")]
        con.close()
        return dates
    ledger_dates_match = ledger_dates(args.raw_ledger) == ledger_dates(args.beta_ledger)
    if not ledger_dates_match:
        raise ValueError("raw and beta ledgers do not have identical ordered prediction dates")
    comparisons = {}
    for label, name in (("vs_current_vt050", "vol_target_050"), ("vs_raw_vt040", "vol_target_040")):
        base = np.asarray(named(args.raw, name)["rets"], dtype=float)
        if len(base) != len(candidate):
            raise ValueError(f"unaligned return lengths: {len(base)} vs {len(candidate)}")
        oos_n = named(args.raw, name).get("oos", {}).get("days")
        spans = {"full": (base, candidate)}
        if oos_n:
            spans["oos"] = (base[:oos_n], candidate[:oos_n])
            spans["is"] = (base[oos_n:], candidate[oos_n:])
        comparisons[label] = {}
        for span, (b, c) in spans.items():
            comparisons[label][span] = {
                "observed_delta_sharpe": round(sharpe(c) - sharpe(b), 3),
                "observed_delta_log_return": round(float(np.sum(c - b)), 3),
                "observed_delta_max_drawdown": round(max_drawdown(c) - max_drawdown(b), 3),
                "bootstrap": [paired_blocks(b, c, block, 5000, np.random.default_rng(20260912 + block))
                              for block in (40, 80)],
            }
    Path(args.out).write_text(json.dumps({
        "seed": 20260912,
        "input_note": "sweep.py rounded daily log returns; paired circular moving-block bootstrap",
        "ordered_prediction_dates_match": ledger_dates_match,
        "alignment_note": "raw/beta ledgers have identical ordered prediction dates; both sweeps used same-day yfinance calendars, but result JSON does not store per-return dates",
        "drawdown_note": "bootstrap drawdown includes initial equity 1; repository segment metrics may use a different rebasing convention",
        "interpretation": "exploratory dependence-aware diagnostic on reused data, not independent validation",
        "comparisons": comparisons,
    }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
