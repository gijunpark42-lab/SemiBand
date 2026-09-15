"""Round 31 gate (pre-registered): candidates _g2 (hybrid) and _g3 (refresh without mean_reversion) against _g0 (no refresh,
same label); _g1 (refresh, same label) and _g1ref (the live setup) reported. Read-only. Usage: python gate_report.py <label name>"""
import json
import math
import re
import sys
from pathlib import Path

import numpy as np

S = Path(r"C:/Users/calif/Desktop/Trading/state")
OOS_END = "2025-09-24"
LABEL = sys.argv[1] if len(sys.argv) > 1 else "?"
RUNS = {"_g0": "no refresh", "_g1ref": "LIVE: refresh, signal-close label", "_g1": "refresh", "_g2": "hybrid",
        "_g3": "refresh without mean_reversion"}

reports = {t: json.loads((S / f"backtest_report{t}.json").read_text(encoding="utf-8")) for t in RUNS}
curves = {t: {c["date"]: c for c in r["curve"]} for t, r in reports.items()}
cost = float(re.search(r"; ([\d.]+) bps cost per unit turnover", " ".join(reports["_g0"]["caveats"])).group(1))
dates = sorted(set.intersection(*(set(c) for c in curves.values())))
oos = [d for d in dates if d < OOS_END]


def stats(tag, bps=None):
    c = curves[tag]
    rets = np.array([c[d]["ret"] - (c[d]["turnover"] * (bps - cost) / 1e4 if bps else 0.0) for d in dates])
    eq = np.cumprod(1 + rets)
    logs = np.log1p(rets)
    return {"ret": float(eq[-1] - 1), "sharpe": float(logs.mean() / (logs.std() or 1e-9) * math.sqrt(252)),
            "dd": float((1 - eq / np.maximum.accumulate(eq)).max())}


def paired(a, b, days):
    d = np.array([curves[a][x]["ret"] - curves[b][x]["ret"] for x in days])
    sd = d.std(ddof=1) if len(d) > 2 else 0.0
    return float(d.mean() * 1e4), (float(d.mean() / (sd / math.sqrt(len(d)))) if sd > 0 else float("nan"))


print(f"Round 31 gate, candidate label = {LABEL}, {len(dates)} common days ({dates[0]} .. {dates[-1]}), OOS days {len(oos)}, "
      f"cost {cost:g} bps")
print(f"{'tag':7} {'run':34} {'return':>8} {'Sharpe':>6} {'maxDD':>6} {'ret@30':>8} {'turn':>5} {'gross':>5} {'names':>5} "
      f"{'held≠g0':>7} {'vs g0 bp/d':>10} {'t':>6} {'OOS bp/d':>8} {'t':>6} {'vs g1ref t':>10}")
rows = {}
for tag, name in RUNS.items():
    s, s30 = stats(tag), stats(tag, bps=30)
    c = curves[tag]
    differs = np.mean([c[d].get("held") != curves["_g0"][d].get("held") for d in dates])
    full = paired(tag, "_g0", dates) if tag != "_g0" else (0.0, float("nan"))
    oosd = paired(tag, "_g0", oos) if tag != "_g0" else (0.0, float("nan"))
    live = paired(tag, "_g1ref", dates) if tag != "_g1ref" else (0.0, float("nan"))
    rows[tag] = dict(s=s, s30=s30, full=full, oos=oosd, live=live, differs=differs)
    print(f"{tag:7} {name:34} {s['ret']:>+8.0%} {s['sharpe']:>6.2f} {s['dd']:>6.1%} {s30['ret']:>+8.0%} "
          f"{np.mean([c[d]['turnover'] for d in dates]):>5.2f} {np.mean([c[d]['gross'] for d in dates]):>5.2f} "
          f"{np.mean([c[d]['n'] for d in dates]):>5.1f} {differs:>7.0%} {full[0]:>+10.2f} {full[1]:>+6.2f} {oosd[0]:>+8.2f} "
          f"{oosd[1]:>+6.2f} {live[1]:>+10.2f}")

print()
base = rows["_g0"]
for tag in ("_g1", "_g2", "_g3"):
    r = rows[tag]
    checks = {"paired t >= 0": r["full"][1] >= 0, "OOS mean diff >= 0": r["oos"][0] >= 0,
              "maxDD <= g0 + 2 pts": r["s"]["dd"] <= base["s"]["dd"] + 0.02, "return@30bps >= g0": r["s30"]["ret"] >= base["s30"]["ret"]}
    passed = all(checks.values())
    note = " (reported, not a candidate)" if tag == "_g1" else ""
    print(f"{tag} gate{note}: {'PASS' if passed else 'FAIL'} — " + "; ".join(f"{k}: {'ok' if v else 'NO'}" for k, v in checks.items())
          + (f"; held set differs from g0 on {r['differs']:.0%} of days" + (" (no measurable effect)" if r["differs"] < 0.10 else "")))
    if tag == "_g2" and r["full"][0] <= -4:
        print("  stop rule: the hybrid trails g0 by 4 bps/day or more -> rejected, no further label variants")
    if tag != "_g1":
        adopt = passed and r["live"][1] > 0
        print(f"  decision: {'ADOPT candidate' if adopt else 'keep live'} (passes gate: {passed}; paired t vs the live setup "
              f"_g1ref: {r['live'][1]:+.2f}, {r['live'][0]:+.2f} bps/day)")
