"""Protocol v3 gate (2026-09-17, from round 41 on): the common days are cut into six equal contiguous blocks; blocks 1, 3, 5 are
validation and 2, 4, 6 test; the first 20 trading days of every block are purged (10/20-day labels overlap the previous block).
Gate on the validation union (Sharpe not lower, max DD <= base + 2 pts, paired >= 0); the test union is scored once and vetoes
adoption when paired t < -1 or max DD > base + 2 pts. Read-only.

    python analyze_v3.py _base _cand [...]
"""
import json
import math
import re
import sys

import numpy as np

import config

S = config.STATE_DIR
BLOCKS, PURGE = 6, 20
tags = sys.argv[1:]
reps = {t: json.loads((S / f"backtest_report{t}.json").read_text(encoding="utf-8")) for t in tags}
curves = {t: {c["date"]: c for c in r["curve"]} for t, r in reps.items()}
cost = float(re.search(r"; ([\d.]+) bps cost per unit turnover", " ".join(reps[tags[0]]["caveats"])).group(1))
dates = sorted(set.intersection(*(set(c) for c in curves.values())))
size = len(dates) // BLOCKS
blocks = [dates[i * size:(i + 1) * size if i < BLOCKS - 1 else len(dates)] for i in range(BLOCKS)]
val = [d for i, b in enumerate(blocks) if i % 2 == 0 for d in b[PURGE:]]
test = [d for i, b in enumerate(blocks) if i % 2 == 1 for d in b[PURGE:]]


def stats(t, days):
    rets = np.array([curves[t][d]["ret"] for d in days])
    eq = np.cumprod(1 + rets)
    logs = np.log1p(rets)
    return float(np.prod(1 + rets) - 1), logs.mean() / (logs.std() or 1e-9) * math.sqrt(252), float((1 - eq / np.maximum.accumulate(eq)).max())


def paired(a, b, days):
    x = np.array([curves[b][d]["ret"] - curves[a][d]["ret"] for d in days])
    sd = x.std(ddof=1)
    return x.mean() * 1e4, (x.mean() / (sd / math.sqrt(len(x))) if sd > 0 else float("nan"))


base = tags[0]
print(f"{len(dates)} common days {dates[0]}..{dates[-1]} | {BLOCKS} blocks of ~{size} d, purge {PURGE} | validation {len(val)} d (blocks 1,3,5) | "
      f"test {len(test)} d (blocks 2,4,6) | cost {cost:g} bps | base {base}")
print("blocks:", ", ".join(f"{i + 1}:{b[0]}..{b[-1]}" for i, b in enumerate(blocks)))
for t in tags:
    rv, sv, dv = stats(t, val)
    rt, st_, dt = stats(t, test)
    print(f"{t:5} validation: return {rv:+.0%} Sharpe {sv:.2f} maxDD {dv:.1%} | test: return {rt:+.0%} Sharpe {st_:.2f} maxDD {dt:.1%}")
sv0, dv0 = stats(base, val)[1], stats(base, val)[2]
dt0 = stats(base, test)[2]
for t in tags[1:]:
    sv, dv = stats(t, val)[1], stats(t, val)[2]
    dt = stats(t, test)[2]
    mv, tv = paired(base, t, val)
    mt, tt = paired(base, t, test)
    gate = sv >= sv0 - 1e-9 and dv <= dv0 + 0.02 and mv >= 0
    veto = (not math.isnan(tt) and tt < -1) or dt > dt0 + 0.02
    print(f"{t:5} vs {base}: validation paired {mv:+.2f} bp/d (t {tv:+.2f}), Sharpe {sv:.2f} vs {sv0:.2f}, maxDD {dv:.1%} vs {dv0:.1%} -> "
          f"{'PASS' if gate else 'FAIL'} | test (once) paired {mt:+.2f} bp/d (t {tt:+.2f}), maxDD {dt:.1%} vs {dt0:.1%} -> "
          f"{'VETO' if veto else 'no veto'}")
