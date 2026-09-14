"""Compare the open-refresh backtests with their next-open baseline (same code, same day, same universe and inputs).

    python backtest.py --days 500 --exec open --tag _orbase --no-publish
    python backtest.py --days 500 --exec open --open-refresh --tag _orrefresh --no-publish
    python backtest.py --days 500 --exec open --open-refresh --label-open --tag _orrefresh_ol --no-publish
    python analyze_open_refresh.py

Windows follow RESEARCH.md: OOS = before 2025-09-24, IS = from 2025-09-24. The paired test uses the daily return
difference (variant minus baseline) on the same dates. IC is not comparable across label definitions; judge on returns.
"""
import json
import math

import numpy as np

import config

OOS_END = "2025-09-24"
RUNS = {  # name: (tag, open_refresh, label_open, label_next_close)
    "baseline (next open)": ("_orbase", False, False, False),
    "open refresh": ("_orrefresh", True, False, False),
    "open refresh, open labels": ("_orrefresh_ol", True, True, False),
    "baseline, live labels": ("_orbase_nc", False, False, True),
    "open refresh, live labels": ("_orrefresh_nc", True, False, True),
}
WINDOWS = (("full", None, None), ("OOS", None, OOS_END), ("IS", OOS_END, None))


def window_stats(curve, lo=None, hi=None):
    days = [(k, c) for k, c in enumerate(curve) if (lo is None or c["date"] >= lo) and (hi is None or c["date"] < hi)]
    rets = np.array([c["ret"] for _, c in days])
    logs = np.log1p(rets)
    equity = np.exp(np.cumsum(logs))
    drawdown = 1 - equity / np.maximum.accumulate(np.concatenate([[1.0], equity]))[1:]
    k0 = days[0][0]
    soxx_before = curve[k0 - 1]["soxx"] if k0 > 0 else 1.0
    return {"days": len(days), "return": float(equity[-1] - 1), "soxx": float(days[-1][1]["soxx"] / soxx_before - 1),
            "sharpe": float(logs.mean() / (logs.std() or 1e-9) * math.sqrt(252)), "max_dd": float(drawdown.max()),
            "gross": float(np.mean([c["gross"] for _, c in days])), "turnover": float(np.mean([c["turnover"] for _, c in days]))}


reports = {}
for name, (tag, refresh, label_open, label_next_close) in RUNS.items():
    path = config.STATE_DIR / f"backtest_report{tag}.json"
    if not path.exists():
        print(f"{name}: {path.name} missing, skipped")
        continue
    rep = json.loads(path.read_text(encoding="utf-8"))
    assert (rep["execution"] == "open" and bool(rep.get("open_refresh")) == refresh and bool(rep.get("label_open")) == label_open
            and bool(rep.get("label_next_close")) == label_next_close), name
    reports[name] = rep

print(f"{'run':27} {'window':6} {'days':>4} {'return':>9} {'SOXX':>8} {'Sharpe':>6} {'maxDD':>6} {'gross':>6} {'turn':>5}")
for name, rep in reports.items():
    for label, lo, hi in WINDOWS:
        s = window_stats(rep["curve"], lo, hi)
        print(f"{name:27} {label:6} {s['days']:>4} {s['return']:>+9.1%} {s['soxx']:>+8.1%} {s['sharpe']:>6.2f} {s['max_dd']:>6.1%} "
              f"{s['gross']:>6.2f} {s['turnover']:>5.2f}")
    rb = rep["robustness"]
    print(f"{'':27} cost bps -> return/Sharpe {[(c['bps'], round(c['total_return'], 2), c['sharpe']) for c in rb['cost_sensitivity']]}; "
          f"Sharpe CI {rb.get('sharpe_ci95')}; DSR {rb['deflated']['dsr'] if rb.get('deflated') else None}; best quarter {rb.get('best_quarter_share')}")
    print(f"{'':27} IC10 learned {rep['ic_10d']['learned']} / prior {rep['ic_10d']['equal_prior']}; quintiles {rep['quintiles_10d']}")

base_name = "baseline (next open)"
if base_name in reports:
    b = {c["date"]: c["ret"] for c in reports[base_name]["curve"]}
    for name, rep in reports.items():
        if name == base_name:
            continue
        v = {c["date"]: c["ret"] for c in rep["curve"]}
        common = sorted(set(b) & set(v))
        for label, lo, hi in WINDOWS:
            d = np.array([v[x] - b[x] for x in common if (lo is None or x >= lo) and (hi is None or x < hi)])
            t = d.mean() / (d.std(ddof=1) / math.sqrt(len(d))) if len(d) > 2 and d.std(ddof=1) > 0 else float("nan")
            print(f"{name} minus baseline, {label}: {len(d)} days, mean {d.mean() * 1e4:+.2f} bps/day, t = {t:+.2f}, "
                  f"better on {np.mean(d > 0):.0%} of days, correlation {np.corrcoef([v[x] for x in common], [b[x] for x in common])[0, 1]:.2f}")
