"""Overfitting diagnostics for a backtest curve.

The strategy's knobs were chosen by ~160 sweep variants on one 220-day window,
so a raw Sharpe from that window is an in-sample number. These helpers put
error bars on it and discount it for the number of trials:

  * block-bootstrap Sharpe CI   resample 10-day blocks of daily returns (keeps autocorrelation)
  * deflated Sharpe ratio       Bailey & Lopez de Prado (2014): probability that the observed
                                Sharpe beats the best of N random trials with the same variance
  * PBO (CSCV)                  probability of backtest overfitting across sweep variants
                                (Bailey, Borwein, Lopez de Prado, Zhu 2017)
  * calendar tables             monthly / quarterly returns vs SOXX (one good quarter is not a strategy)
  * cost sensitivity            the same curve at 0 / 5 / 15 / 30 bps per unit turnover
  * rolling Sharpe              60-day window, to see whether the edge is stable or one burst
"""
import glob
import itertools
import json
import math

import numpy as np
from scipy.stats import norm

import config

ANN = math.sqrt(252)


def sharpe(rets):
    rets = np.asarray(rets, dtype=float)
    return float(np.mean(rets) / (np.std(rets) or 1e-9) * ANN) if len(rets) > 1 else 0.0


def block_bootstrap_ci(rets, block=10, n=2000, seed=0):
    """95% CI of the annualised Sharpe from resampled blocks of daily returns."""
    rets = np.asarray(rets, dtype=float)
    T = len(rets)
    if T < 2 * block:
        return None
    rng = np.random.default_rng(seed)
    starts = np.arange(0, T - block + 1)
    out = np.empty(n)
    for k in range(n):
        picks = rng.choice(starts, size=math.ceil(T / block))
        sample = np.concatenate([rets[s:s + block] for s in picks])[:T]
        out[k] = sharpe(sample)
    return [round(float(np.percentile(out, 2.5)), 2), round(float(np.percentile(out, 97.5)), 2)]


def deflated_sharpe(rets, n_trials, trial_sharpes_ann=None):
    """Probability that the observed Sharpe is real, after selecting the best of n_trials.

    trial_sharpes_ann: annualised Sharpes of the trials (from the sweep files); their variance
    sets how high the best of N random trials would be expected to reach."""
    rets = np.asarray(rets, dtype=float)
    T = len(rets)
    if T < 30 or n_trials < 1:
        return None
    sr = float(np.mean(rets) / (np.std(rets) or 1e-9))          # daily, not annualised
    if trial_sharpes_ann is not None and len(trial_sharpes_ann) > 2:
        var_sr = float(np.var(np.asarray(trial_sharpes_ann) / ANN))
    else:
        var_sr = (0.5 / ANN) ** 2                                  # a modest spread if no sweep record exists
    g = 0.5772156649
    sr0 = math.sqrt(var_sr) * ((1 - g) * norm.ppf(1 - 1 / n_trials) + g * norm.ppf(1 - 1 / (n_trials * math.e))) if n_trials > 1 else 0.0
    z = (rets - rets.mean()) / (rets.std() or 1e-9)
    skew, kurt = float(np.mean(z ** 3)), float(np.mean(z ** 4))
    denom = math.sqrt(max(1 - skew * sr + (kurt - 1) / 4 * sr ** 2, 1e-9))
    psr = norm.cdf((sr - sr0) * math.sqrt(T - 1) / denom)
    return {"dsr": round(float(psr), 3), "n_trials": int(n_trials), "sr0_ann": round(float(sr0) * ANN, 2),
            "skew": round(skew, 2), "kurtosis": round(kurt, 2)}


def sweep_trials(state_dir=None):
    """(n_trials, [annualised Sharpe per variant]) from every state/backtest_sweep*.json."""
    srs = []
    for f in glob.glob(str((state_dir or config.STATE_DIR) / "backtest_sweep*.json")):
        try:
            srs += [r["sharpe"] for r in json.loads(open(f, encoding="utf-8").read())["results"]]
        except Exception:
            continue
    return len(srs), srs


def pbo(returns_matrix, n_splits=16):
    """Probability of backtest overfitting by combinatorially symmetric cross-validation.

    returns_matrix: (T, N) daily returns of N variants. Split T into n_splits blocks; for every
    half/half combination pick the in-sample best variant and record its out-of-sample rank.
    PBO = share of combinations where the in-sample winner is below the OOS median."""
    R = np.asarray(returns_matrix, dtype=float)
    T, N = R.shape
    if N < 2 or T < 2 * n_splits:
        return None
    blocks = np.array_split(np.arange(T), n_splits)
    logits = []
    for combo in itertools.combinations(range(n_splits), n_splits // 2):
        ins = np.concatenate([blocks[i] for i in combo])
        oos = np.concatenate([blocks[i] for i in range(n_splits) if i not in combo])
        sr_in = np.array([sharpe(R[ins, j]) for j in range(N)])
        sr_out = np.array([sharpe(R[oos, j]) for j in range(N)])
        best = int(np.argmax(sr_in))
        rank = (np.sum(sr_out < sr_out[best]) + 1) / (N + 1)        # relative OOS rank of the IS winner
        logits.append(math.log(rank / (1 - rank)))
    logits = np.array(logits)
    return {"pbo": round(float(np.mean(logits <= 0)), 3), "combinations": len(logits),
            "median_oos_rank": round(float(np.median(1 / (1 + np.exp(-logits)))), 3)}


def calendar(curve, key="portfolio", bench="soxx"):
    """{'monthly': [{period, portfolio, soxx, excess}], 'quarterly': [...]} from a curve of equity levels."""
    def table(fmt):
        rows, pv, pb, cur, last = [], 1.0, 1.0, None, None
        for c in curve:
            k = fmt(c["date"])
            if k != cur:
                if cur is not None:
                    rows.append({"period": cur, "portfolio": round(last[key] / pv - 1, 4), "soxx": round(last[bench] / pb - 1, 4)})
                    pv, pb = last[key], last[bench]
                cur = k
            last = c
        if last is not None:
            rows.append({"period": cur, "portfolio": round(last[key] / pv - 1, 4), "soxx": round(last[bench] / pb - 1, 4)})
        for r in rows:
            r["excess"] = round(r["portfolio"] - r["soxx"], 4)
        return rows
    return {"monthly": table(lambda d: d[:7]),
            "quarterly": table(lambda d: f"{d[:4]}Q{(int(d[5:7]) - 1) // 3 + 1}")}


def rolling_sharpe(curve, window=60):
    eq = np.array([c["portfolio"] for c in curve])
    rets = np.diff(np.log(np.r_[1.0, eq]))
    return [{"date": curve[i - 1]["date"], "sharpe": round(sharpe(rets[i - window:i]), 2)}
            for i in range(window, len(rets) + 1)]


def cost_sensitivity(curve, bps_list=(0, 5, 15, 30)):
    """Re-price the curve at other cost levels; needs per-day 'ret' (net of config.COST_BPS) and 'turnover'."""
    if not curve or "turnover" not in curve[0]:
        return None
    out = []
    for bps in bps_list:
        eq, rets = 1.0, []
        for c in curve:
            r = c["ret"] + c["turnover"] * (config.COST_BPS - bps) / 10_000
            rets.append(math.log1p(r))
            eq *= 1 + r
        out.append({"bps": bps, "total_return": round(eq - 1, 4), "sharpe": round(sharpe(rets), 2)})
    return out


def best_quarter_share(curve):
    """How much of the total log return came from the single best quarter (1.0 = all of it)."""
    logs = [math.log1p(r["portfolio"]) for r in calendar(curve)["quarterly"]]
    tot = sum(logs)
    return round(max(logs) / tot, 3) if tot > 0 and logs else None


def summary(curve, n_trials=None, trial_sharpes=None):
    if len(curve) < 2:
        return None
    eq = np.array([c["portfolio"] for c in curve])
    rets = np.diff(np.log(np.r_[1.0, eq]))
    if n_trials is None:
        n_trials, trial_sharpes = sweep_trials()
    return {
        "sharpe": round(sharpe(rets), 2),
        "sharpe_ci95": block_bootstrap_ci(rets),
        "deflated": deflated_sharpe(rets, max(n_trials, 1), trial_sharpes),
        "calendar": calendar(curve),
        "rolling_sharpe_60d": rolling_sharpe(curve),
        "cost_sensitivity": cost_sensitivity(curve),
        "best_quarter_share": best_quarter_share(curve),
    }
