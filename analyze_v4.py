"""Protocol v4 gate (2026-09-17, from round 41 on): full-window gate against the same-day, same-machine baseline (paired daily
difference >= 0, Sharpe not lower, max DD <= base + 2 pts) plus block consistency (paired difference >= 0 in at least 4 of 6
purged blocks). The independent 2019-23 window is judged with the same script on its own pair. Read-only.
v4.1 (2026-09-18, from round 46 on): a tie — a block in which the two books' daily returns are identical on every day — is never
a pass: tied blocks leave the count and the requirement is two thirds of the informative blocks (rounded up) with at least three
of them; with --affected-from YYYY-MM-DD a partial-coverage candidate is also scored on the affected days alone (four contiguous
blocks, the first 10 days of each purged, each at least 20 days, 3 of 4).

    python analyze_v4.py _base _cand [...] [--affected-from 2025-10-01]      (reports read from config.STATE_DIR)
"""
import json
import math
import re
import sys

import numpy as np

import config

S = config.STATE_DIR
BLOCKS, PURGE, MIN_BLOCKS = 6, 20, 4
args = sys.argv[1:]
AFFECTED_FROM = None                               # v4.1 (b): the first day a partial-coverage candidate can act, e.g. 2025-10-01
if "--affected-from" in args:
    k = args.index("--affected-from")
    AFFECTED_FROM = args[k + 1]
    args = args[:k] + args[k + 2:]
tags = args
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
    tie = [all(curves[t][d]["ret"] == curves[base][d]["ret"] for d in b) for b in blocks]     # v4.1 (a): identical books
    inf = [x for x, is_tie in zip(blk, tie) if not is_tie]
    ok_blocks, need = sum(1 for x in inf if x >= 0), math.ceil(2 * len(inf) / 3)
    blocks_ok = len(inf) >= 3 and ok_blocks >= need
    note = f"{ok_blocks}/{len(inf)} informative (need {need}, {sum(tie)} ties excluded)" if any(tie) else f"{ok_blocks}/{len(inf)}"
    cov = ""
    if AFFECTED_FROM:                                                                            # v4.1 (b): the affected days alone
        aff = [d for d in dates if d >= AFFECTED_FROM]
        n4 = len(aff) // 4
        cblocks = [aff[j * n4:(j + 1) * n4 if j < 3 else len(aff)][10:] for j in range(4)]
        if n4 and min(len(b) for b in cblocks) >= 20:
            cblk = [paired(base, t, b)[0] for b in cblocks]
            cok = sum(1 for x in cblk if x >= 0)
            blocks_ok = blocks_ok and cok >= 3
            cov = f" | affected {len(aff)} d from {AFFECTED_FROM}: {cok}/4 [{', '.join(f'{x:+.1f}' for x in cblk)}]"
        else:
            blocks_ok, cov = False, f" | affected days from {AFFECTED_FROM}: too few for four 20-day blocks -> not gateable"
    gate = m >= 0 and s >= s0 - 1e-9 and dd <= dd0 + 0.02 and blocks_ok
    nw = nw_t([curves[t][d]["ret"] - curves[base][d]["ret"] for d in dates])
    print(f"{t:5} vs {base}: paired {m:+.2f} bp/d (t {tt:+.2f}, Newey-West {nw:+.2f}) | Sharpe {s:.2f} vs {s0:.2f} | maxDD {dd:.1%} vs {dd0:.1%} | blocks >= 0: "
          f"{note} [{', '.join(f'{x:+.1f}' for x in blk)}]{cov} -> {'PASS' if gate else 'FAIL'}")
