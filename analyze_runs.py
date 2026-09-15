"""Compare finished backtest reports by tag: full window, OOS (before 2025-09-24), IS, the 2026-05 cash stretch, cost
sensitivity, and paired daily differences against the first tag.

    python analyze_runs.py _sz0 _sz1 _sz2
"""
import json
import math
import sys

import numpy as np

import config

OOS_END = "2025-09-24"
WINDOWS = (("full", None, None), ("OOS", None, OOS_END), ("IS", OOS_END, None), ("2026-05+", "2026-05-01", None))


def window(curve, lo, hi):
    days = [(k, c) for k, c in enumerate(curve) if (lo is None or c["date"] >= lo) and (hi is None or c["date"] < hi)]
    logs = np.log1p(np.array([c["ret"] for _, c in days]))
    equity = np.exp(np.cumsum(logs))
    drawdown = 1 - equity / np.maximum.accumulate(np.concatenate([[1.0], equity]))[1:]
    k0 = days[0][0]
    soxx_before = curve[k0 - 1]["soxx"] if k0 > 0 else 1.0
    return {"ret": equity[-1] - 1, "soxx": days[-1][1]["soxx"] / soxx_before - 1,
            "sharpe": logs.mean() / (logs.std() or 1e-9) * math.sqrt(252), "dd": drawdown.max(),
            "gross": np.mean([c["gross"] for _, c in days])}


tags = sys.argv[1:]
reports = {t: json.loads((config.STATE_DIR / f"backtest_report{t}.json").read_text(encoding="utf-8")) for t in tags}
print(f"{'tag':10} {'window':8} {'return':>9} {'SOXX':>8} {'Sharpe':>6} {'maxDD':>6} {'gross':>6}  sizing")
for t, rep in reports.items():
    for label, lo, hi in WINDOWS:
        s = window(rep["curve"], lo, hi)
        print(f"{t:10} {label:8} {s['ret']:>+9.1%} {s['soxx']:>+8.1%} {s['sharpe']:>6.2f} {s['dd']:>6.1%} {s['gross']:>6.2f}"
              + (f"  {rep.get('sizing')} refresh={rep.get('open_refresh')}" if label == "full" else ""))
    rb = rep["robustness"]
    print(f"{'':10} cost bps -> return/Sharpe {[(c['bps'], round(c['total_return'], 2), c['sharpe']) for c in rb['cost_sensitivity']]}; "
          f"Sharpe CI {rb.get('sharpe_ci95')}; DSR {rb['deflated']['dsr'] if rb.get('deflated') else None}; "
          f"turnover {rep['portfolio']['turnover_per_day']}; names {rep['portfolio']['avg_names']}")

base = {c["date"]: c["ret"] for c in reports[tags[0]]["curve"]}
for t in tags[1:]:
    v = {c["date"]: c["ret"] for c in reports[t]["curve"]}
    common = sorted(set(base) & set(v))
    for label, lo, hi in WINDOWS:
        d = np.array([v[x] - base[x] for x in common if (lo is None or x >= lo) and (hi is None or x < hi)])
        tstat = d.mean() / (d.std(ddof=1) / math.sqrt(len(d))) if len(d) > 2 and d.std(ddof=1) > 0 else float("nan")
        print(f"{t} minus {tags[0]}, {label}: {len(d)} days, {d.mean() * 1e4:+.2f} bps/day, t = {tstat:+.2f}")
