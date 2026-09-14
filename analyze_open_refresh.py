"""Compare the open-refresh backtest with its next-open baseline (same code, same day, same universe and ledger inputs).

    python backtest.py --days 500 --exec open --tag _orbase --no-publish
    python backtest.py --days 500 --exec open --open-refresh --tag _orrefresh --no-publish
    python analyze_open_refresh.py

Windows follow RESEARCH.md: OOS = before 2025-09-24, IS = from 2025-09-24. The paired test uses the daily return
difference (refresh minus baseline) on the same dates.
"""
import json
import math

import numpy as np

import config

OOS_END = "2025-09-24"
RUNS = {"baseline (next open)": "_orbase", "open refresh": "_orrefresh"}


def window_stats(curve, lo=None, hi=None):
    days = [(k, c) for k, c in enumerate(curve) if (lo is None or c["date"] >= lo) and (hi is None or c["date"] < hi)]
    if not days:
        return None
    rets = np.array([c["ret"] for _, c in days])
    logs = np.log1p(rets)
    equity = np.exp(np.cumsum(logs))
    drawdown = 1 - equity / np.maximum.accumulate(np.concatenate([[1.0], equity]))[1:]
    k0 = days[0][0]
    soxx_before = curve[k0 - 1]["soxx"] if k0 > 0 else 1.0
    return {"days": len(days), "return": float(equity[-1] - 1), "soxx": float(days[-1][1]["soxx"] / soxx_before - 1),
            "sharpe": float(logs.mean() / (logs.std() or 1e-9) * math.sqrt(252)), "max_dd": float(drawdown.max()),
            "gross": float(np.mean([c["gross"] for _, c in days])), "turnover": float(np.mean([c["turnover"] for _, c in days]))}


reports = {name: json.loads((config.STATE_DIR / f"backtest_report{tag}.json").read_text(encoding="utf-8"))
           for name, tag in RUNS.items()}
print(f"{'run':22} {'window':6} {'days':>4} {'return':>9} {'SOXX':>8} {'Sharpe':>6} {'maxDD':>6} {'gross':>6} {'turn':>5}")
for name, rep in reports.items():
    assert rep["execution"] == "open" and rep.get("open_refresh", False) == (name == "open refresh"), f"{name}: wrong run"
    for label, lo, hi in (("full", None, None), ("OOS", None, OOS_END), ("IS", OOS_END, None)):
        s = window_stats(rep["curve"], lo, hi)
        print(f"{name:22} {label:6} {s['days']:>4} {s['return']:>+9.1%} {s['soxx']:>+8.1%} {s['sharpe']:>6.2f} {s['max_dd']:>6.1%} "
              f"{s['gross']:>6.2f} {s['turnover']:>5.2f}")
    print(f"{'':22} IC10 learned {rep['ic_10d']['learned']} / prior {rep['ic_10d']['equal_prior']}; quintiles {rep['quintiles_10d']}; "
          f"deflated {rep['robustness'].get('deflated')}; Sharpe CI {rep['robustness'].get('sharpe_ci95')}")

base, refresh = (reports[n]["curve"] for n in RUNS)
common = sorted(set(c["date"] for c in base) & set(c["date"] for c in refresh))
b = {c["date"]: c["ret"] for c in base}
r = {c["date"]: c["ret"] for c in refresh}
for label, lo, hi in (("full", None, None), ("OOS", None, OOS_END), ("IS", OOS_END, None)):
    d = np.array([r[x] - b[x] for x in common if (lo is None or x >= lo) and (hi is None or x < hi)])
    t = d.mean() / (d.std(ddof=1) / math.sqrt(len(d))) if len(d) > 2 and d.std(ddof=1) > 0 else float("nan")
    print(f"paired daily difference, {label}: {len(d)} days, mean {d.mean() * 1e4:+.2f} bps/day, t = {t:+.2f}, "
          f"refresh better on {np.mean(d > 0):.0%} of days")
