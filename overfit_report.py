"""Overfitting statistics for the replay variants (round 57; read-only). Groups the stored replay reports by window and, per
window, on the dates all its variants share:

  - CSCV-PBO (Bailey, Borwein, López de Prado & Zhu 2017): how often the in-sample best variant lands below the median out of
    sample over all half/half splits of S blocks. It measures whether choosing among variants is informative, not whether an
    edge exists (near-duplicate variants sit near 0.5).
  - Hansen's SPA and Romano-Wolf StepM (arch, stationary bootstrap, block 20) against SOXX and SPY: is any variant better.
  - The deflated Sharpe of a chosen run as a function of the number of trials K (the hand count, the effective K of the
    variants' correlation matrix as a participation ratio, and small K for reference), and the Harvey-Liu BHY haircut.
  - A style regression of the chosen run's daily returns on SOXX, SPY, a low-volatility ETF and a momentum ETF.
  - With constrained-random null runs (report field null_seed): the chosen run's percentile among them, and the null median
    against SOXX (Daniel, Sornette & Wohrmann 2009).
None of these can see hindsight in the inputs (today's graph and universe); only the clean windows can.

    python overfit_report.py --dirs DIR [DIR ...] --chosen _ia0 [--trials 396]
"""
import argparse
import itertools
import json
import math
from pathlib import Path

import numpy as np
from scipy.stats import norm

WINDOWS = {"2024-26": 2024, "2019-23": 2019, "2012-18": 2012}


def load_reports(dirs):
    out = {}
    for d in dirs:
        for p in Path(d).glob("backtest_report*.json"):
            try:
                r = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            curve = r.get("curve") or []
            if len(curve) < 400 or any(k not in curve[0] for k in ("soxx", "spy")):
                continue
            if "ret" not in curve[0]:                          # older reports: the daily return from the equity level
                if "portfolio" not in curve[0]:
                    continue
                prev = 1.0
                for c in curve:
                    c["ret"] = c["portfolio"] / prev - 1
                    prev = c["portfolio"]
            tag = p.stem.replace("backtest_report", "") or "(default)"
            year = int(str(r.get("period", {}).get("start", "0"))[:4] or 0)
            win = next((w for w, y in WINDOWS.items() if year in (y, y - 1) or (w == "2024-26" and year >= 2024)), None)
            if win:
                out[(win, tag)] = {"curve": {c["date"]: c for c in curve}, "null": r.get("null_seed") is not None}
    return out


def cscv_pbo(R, S=16):
    T, N = R.shape
    blocks = np.array_split(R, S)
    logits = []
    for is_idx in itertools.combinations(range(S), S // 2):
        a = np.vstack([blocks[i] for i in is_idx])
        b = np.vstack([blocks[i] for i in range(S) if i not in is_idx])
        sa = a.mean(0) / a.std(0, ddof=1)
        sb = b.mean(0) / b.std(0, ddof=1)
        w = (sb.argsort().argsort()[sa.argmax()] + 1) / (N + 1)
        logits.append(math.log(w / (1 - w)))
    return float(np.mean(np.array(logits) <= 0))


def exp_max_sr(k, var_sr):
    """False strategy theorem: the expected maximum Sharpe (per period) of k independent no-skill trials."""
    if k <= 1:
        return 0.0
    g = np.euler_gamma
    return math.sqrt(var_sr) * ((1 - g) * norm.ppf(1 - 1 / k) + g * norm.ppf(1 - 1 / (k * math.e)))


def dsr(r, sr0):
    """Deflated / probabilistic Sharpe of daily returns r against a per-period hurdle sr0 (skew and kurtosis adjusted)."""
    sr = r.mean() / r.std(ddof=1)
    z = (r - r.mean()) / r.std(ddof=1)
    skew, kurt = float((z ** 3).mean()), float((z ** 4).mean())
    return float(norm.cdf((sr - sr0) * math.sqrt(len(r) - 1) / math.sqrt(1 - skew * sr + (kurt - 1) / 4 * sr * sr)))


def haircut(sr_ann, n_days, m):
    """Harvey-Liu with BHY for the top-ranked of m tests: the haircut annualised Sharpe."""
    t = sr_ann * math.sqrt(n_days / 252)
    p = 2 * (1 - norm.cdf(t))
    p_adj = min(1.0, p * m * sum(1 / j for j in range(1, m + 1)))
    return norm.ppf(1 - p_adj / 2) / math.sqrt(n_days / 252) if p_adj < 1 else 0.0


def nw_t(x, lags=10):
    x = np.asarray(x, float)
    e = x - x.mean()
    var = float(e @ e) / len(x)
    for k in range(1, lags + 1):
        var += 2 * (1 - k / (lags + 1)) * float(e[k:] @ e[:-k]) / len(x)
    return float(x.mean() / math.sqrt(var / len(x)))


def style(dates, r, etfs):
    """OLS of r on the ETFs' daily returns (aligned to `dates`); alpha annualised with a Newey-West t on the residual mean."""
    import market
    px = market.closes(list(etfs), lookback_days=4000, cache=False)
    rets = px.pct_change(fill_method=None)
    import pandas as pd
    idx = pd.to_datetime(dates)
    X = rets.reindex(idx)
    ok = X.notna().all(axis=1).to_numpy()
    X, y = X.to_numpy()[ok], np.asarray(r)[ok]
    A = np.column_stack([np.ones(len(y)), X])
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    resid = y - A[:, 1:] @ coef[1:]
    return coef, nw_t(resid), int(ok.sum())


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dirs", nargs="+", required=True)
    p.add_argument("--chosen", required=True, help="the run judged (e.g. the live configuration's baseline), per window by tag prefix")
    p.add_argument("--trials", type=int, default=396)
    p.add_argument("--etfs", default="SOXX,SPY,SPLV,MTUM")
    args = p.parse_args()
    reps = load_reports(args.dirs)
    for win in WINDOWS:
        tags = [t for (w, t) in reps if w == win]
        if not tags:
            continue
        chosen = next((t for t in tags if t.startswith(args.chosen)), None)
        variants = [t for t in tags if not reps[(win, t)]["null"]]
        nulls = [t for t in tags if reps[(win, t)]["null"]]
        dates = sorted(set.intersection(*(set(reps[(win, t)]["curve"]) for t in variants)))
        R = np.array([[reps[(win, t)]["curve"][d]["ret"] for t in variants] for d in dates])
        soxx = np.array([reps[(win, variants[0])]["curve"][d]["soxx"] for d in dates])
        spy = np.array([reps[(win, variants[0])]["curve"][d]["spy"] for d in dates])
        b_soxx, b_spy = soxx[1:] / soxx[:-1] - 1, spy[1:] / spy[:-1] - 1
        R1 = R[1:]
        print(f"\n===== {win}: {len(variants)} variants, {len(nulls)} null runs, {len(dates)} common days {dates[0]}..{dates[-1]}")
        if len(variants) >= 10:
            print(f"CSCV-PBO (S=16): {cscv_pbo(R1):.2f}   (0.5 = picking the in-sample best is uninformative)")
        try:
            from arch.bootstrap import SPA, StepM
            for name, b in (("SOXX", b_soxx), ("SPY", b_spy)):
                spa = SPA(-b, -R1, block_size=20, reps=2000, seed=0, bootstrap="stationary")
                spa.compute()
                try:
                    sm = StepM(-b, -R1, size=0.05, block_size=20, reps=2000, seed=0)
                    sm.compute()
                    n_sup = len(sm.superior_models or [])
                except ValueError:                             # arch: every variant rejected (the stepdown runs out of models)
                    n_sup = len(variants)
                print(f"SPA vs {name}: p(consistent) {float(spa.pvalues['consistent']):.3f} | StepM: {n_sup} of {len(variants)} variants beat {name}")
        except ImportError:
            print("SPA/StepM: the arch package is not installed")
        if len(variants) > 1:
            eig = np.clip(np.linalg.eigvalsh(np.corrcoef(R1.T)), 0, None)
            k_eff = float(eig.sum() ** 2 / (eig ** 2).sum())
        else:
            k_eff = 1.0
        sr_all = R1.mean(0) / R1.std(0, ddof=1)
        var_sr = float(sr_all.var(ddof=1)) if len(variants) > 1 else 1 / len(R1)
        if chosen:
            r = np.array([reps[(win, chosen)]["curve"][d]["ret"] for d in dates])[1:]
            sr_ann = r.mean() / r.std(ddof=1) * math.sqrt(252)
            print(f"chosen {chosen}: Sharpe {sr_ann:.2f}; variants' effective K (participation ratio) {k_eff:.1f}; cross-variant var(SR) {var_sr:.2e}")
            for k in sorted({5, 10, 30, max(2, round(k_eff)), args.trials}):
                h = exp_max_sr(k, var_sr)
                print(f"   K={k:4d}: hurdle Sharpe {h * math.sqrt(252):.2f}  DSR {dsr(r, h):.3f}  Harvey-Liu BHY haircut Sharpe {haircut(sr_ann, len(r), k):.2f}")
            try:
                coef, t_alpha, n = style(dates[1:], r, args.etfs.split(","))
                names = ["alpha"] + args.etfs.split(",")
                print(f"style ({n} days): " + ", ".join(f"{nm} {c:+.3f}" for nm, c in zip(names[1:], coef[1:]))
                      + f" | alpha {coef[0] * 252:+.1%}/yr (NW t {t_alpha:+.2f})")
            except Exception as exc:
                print(f"style regression skipped: {exc}")
            if nulls:
                def total(t):
                    rr = np.array([reps[(win, t)]["curve"][d]["ret"] for d in dates if d in reps[(win, t)]["curve"]])
                    return float(np.prod(1 + rr) - 1), float(rr.mean() / rr.std(ddof=1) * math.sqrt(252))
                nt = np.array([total(t) for t in nulls])
                ct = total(chosen)
                print(f"constrained-random null ({len(nulls)} runs): median {np.median(nt[:, 0]):+.0%} / Sharpe {np.median(nt[:, 1]):.2f} "
                      f"(range {nt[:, 0].min():+.0%}..{nt[:, 0].max():+.0%}); chosen {ct[0]:+.0%} / {ct[1]:.2f} -> percentile "
                      f"{(nt[:, 0] < ct[0]).mean():.0%} by return, {(nt[:, 1] < ct[1]).mean():.0%} by Sharpe; SOXX {soxx[-1] / soxx[0] - 1:+.0%}")


if __name__ == "__main__":
    main()
