"""Round 39 gate (2026-09-16) under the validation / embargo / test protocol adopted from AQuA (arXiv 2608.12841):
the gate reads only the validation window (the first 70% of the common days); a 20-trading-day embargo follows (labels are
10/20-day returns); the test window (the rest) is scored once and reported, never used to choose. Read-only.

    python analyze_round39.py _n0 _n1 _n2        # first tag = base
"""
import json
import math
import re
import sys
from pathlib import Path

import numpy as np

import config

S = config.STATE_DIR
VALIDATION_SHARE, EMBARGO_DAYS = 0.70, 20
tags = sys.argv[1:] or ["_n0", "_n1", "_n2"]
reps = {t: json.loads((S / f"backtest_report{t}.json").read_text(encoding="utf-8")) for t in tags}
curves = {t: {c["date"]: c for c in r["curve"]} for t, r in reps.items()}
cost = float(re.search(r"; ([\d.]+) bps cost per unit turnover", " ".join(reps[tags[0]]["caveats"])).group(1))
dates = sorted(set.intersection(*(set(c) for c in curves.values())))
n_val = int(len(dates) * VALIDATION_SHARE)
val, test = dates[:n_val], dates[n_val + EMBARGO_DAYS:]


def stats(t, days, bps=None):
    c = curves[t]
    rets = np.array([c[d]["ret"] - (c[d]["turnover"] * (bps - cost) / 1e4 if bps else 0.0) for d in days])
    eq = np.cumprod(1 + rets)
    logs = np.log1p(rets)
    return eq[-1] - 1, logs.mean() / (logs.std() or 1e-9) * math.sqrt(252), (1 - eq / np.maximum.accumulate(eq)).max()


def paired(a, b, days):
    x = np.array([curves[b][d]["ret"] - curves[a][d]["ret"] for d in days])
    sd = x.std(ddof=1)
    return x.mean() * 1e4, (x.mean() / (sd / math.sqrt(len(x))) if sd > 0 else float("nan"))


def book(t, days):
    c = curves[t]
    names = np.mean([(len(h) if isinstance(h, (list, tuple, dict)) else (h or 0)) for h in (c[d].get("held", c[d].get("names", 0)) for d in days)])
    gross = np.mean([c[d].get("gross", 0) or 0 for d in days])
    turn = np.mean([c[d]["turnover"] for d in days])
    return names, gross, turn


base = tags[0]
print(f"{len(dates)} common days {dates[0]}..{dates[-1]} | validation {val[0]}..{val[-1]} ({len(val)} d) | embargo {EMBARGO_DAYS} d | "
      f"test {test[0]}..{test[-1]} ({len(test)} d) | cost {cost:g} bps | base {base}")
for t in tags:
    rv, sv, dv = stats(t, val)
    rt, st_, dt = stats(t, test)
    rf, sf, df = stats(t, dates)
    nm, gr, tu = book(t, val)
    print(f"{t:5} validation: return {rv:+.0%} Sharpe {sv:.2f} maxDD {dv:.1%} names {nm:.1f} gross {gr:.2f} turnover {tu:.2f} | "
          f"test: return {rt:+.0%} Sharpe {st_:.2f} maxDD {dt:.1%} | full (informational): {rf:+.0%} / {sf:.2f} / {df:.1%}")
print()
sv0, dv0 = stats(base, val)[1], stats(base, val)[2]
for t in tags[1:]:
    sv, dv = stats(t, val)[1], stats(t, val)[2]
    mv, tv = paired(base, t, val)
    mt, tt = paired(base, t, test)
    ok_sharpe, ok_dd, ok_paired = sv >= sv0 - 1e-9, dv <= dv0 + 0.02, mv >= 0
    verdict = "PASS" if ok_sharpe and ok_dd and ok_paired else "FAIL"
    print(f"{t:5} vs {base}: validation paired {mv:+.2f} bp/d (t {tv:+.2f}); Sharpe not lower: {'ok' if ok_sharpe else 'NO'} "
          f"({sv:.2f} vs {sv0:.2f}); maxDD <= base + 2 pts: {'ok' if ok_dd else 'NO'} ({dv:.1%} vs {dv0:.1%}); paired >= 0: "
          f"{'ok' if ok_paired else 'NO'} -> {verdict} | test window (scored once, not a gate): paired {mt:+.2f} bp/d (t {tt:+.2f})")
