"""Protocol v4 gate (2026-09-17, from round 41 on): full-window gate against the same-day, same-machine baseline (paired daily
difference >= 0, Sharpe not lower, max DD <= base + 2 pts) plus block consistency (paired difference >= 0 in at least 4 of 6
purged blocks). The independent 2019-23 window is judged with the same script on its own pair. Read-only.

    python analyze_v4.py _base _cand [...]      (reports read from config.STATE_DIR)
"""
import json
import math
import re
import sys

import numpy as np

import config

S = config.STATE_DIR
BLOCKS, PURGE, MIN_BLOCKS = 6, 20, 4
tags = sys.argv[1:]
reps = {t: json.loads((S / f"backtest_report{t}.json").read_text(encoding="utf-8")) for t in tags}
curves = {t: {c["date"]: c for c in r["curve"]} for t, r in reps.items()}
cost = float(re.search(r"; ([\d.]+) bps cost per unit turnover", " ".join(reps[tags[0]]["caveats"])).group(1))
dates = sorted(set.intersection(*(set(c) for c in curves.values())))
size = len(dates) // BLOCKS
blocks = [dates[i * size:(i + 1) * size if i < BLOCKS - 1 else len(dates)][PURGE:] for i in range(BLOCKS)]


def stats(t, days):
    rets = np.array([curves[t][d]["ret"] for d in days])
    eq = np.cumprod(1 + rets)
    logs = np.log1p(rets)
    return float(eq[-1] - 1), logs.mean() / (logs.std() or 1e-9) * math.sqrt(252), float((1 - eq / np.maximum.accumulate(eq)).max())


def nw_t(x, lags=10):
    """Newey-West t of the mean (Bartlett weights): two variants of one book hold the same names for days, so the daily
    differences are autocorrelated and the iid t is too large (audit 2026-09-17)."""
    x = np.asarray(x, float)
    n, e = len(x), np.asarray(x, float) - np.mean(x)
    var = float(e @ e) / n
    for k in range(1, min(lags, n - 1) + 1):
        var += 2 * (1 - k / (lags + 1)) * float(e[k:] @ e[:-k]) / n
    return float(np.mean(x) / math.sqrt(var / n)) if var > 0 else float("nan")


def paired(a, b, days):
    x = np.array([curves[b][d]["ret"] - curves[a][d]["ret"] for d in days])
    sd = x.std(ddof=1)
    return x.mean() * 1e4, (x.mean() / (sd / math.sqrt(len(x))) if sd > 0 else float("nan"))


def book(t, days):
    c = curves[t]
    names = np.mean([(len(h) if isinstance(h, (list, tuple, dict)) else (h or 0)) for h in (c[d].get("held", 0) for d in days)])
    return names, np.mean([c[d].get("gross", 0) or 0 for d in days]), np.mean([c[d]["turnover"] for d in days])


base = tags[0]
print(f"{len(dates)} common days {dates[0]}..{dates[-1]} | {BLOCKS} blocks of ~{size} d (purge {PURGE}) | cost {cost:g} bps | base {base}")
for t in tags:
    r, s, dd = stats(t, dates)
    nm, gr, tu = book(t, dates)
    print(f"{t:5} full: return {r:+.0%} Sharpe {s:.2f} maxDD {dd:.1%} names {nm:.1f} gross {gr:.2f} turnover {tu:.2f} | ic {reps[t].get('ic_10d', {}).get('learned')}")
s0, dd0 = stats(base, dates)[1], stats(base, dates)[2]
for t in tags[1:]:
    s, dd = stats(t, dates)[1], stats(t, dates)[2]
    m, tt = paired(base, t, dates)
    blk = [paired(base, t, b)[0] for b in blocks]
    ok_blocks = sum(1 for x in blk if x >= 0)
    gate = m >= 0 and s >= s0 - 1e-9 and dd <= dd0 + 0.02 and ok_blocks >= MIN_BLOCKS
    nw = nw_t([curves[t][d]["ret"] - curves[base][d]["ret"] for d in dates])
    print(f"{t:5} vs {base}: paired {m:+.2f} bp/d (t {tt:+.2f}, Newey-West {nw:+.2f}) | Sharpe {s:.2f} vs {s0:.2f} | maxDD {dd:.1%} vs {dd0:.1%} | blocks >= 0: "
          f"{ok_blocks}/6 [{', '.join(f'{x:+.1f}' for x in blk)}] -> {'PASS' if gate else 'FAIL'}")
