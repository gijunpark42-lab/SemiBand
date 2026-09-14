"""Frozen, offline-after-download exposure comparison. Never applies a winner.

Only this new runner and outputs/higher_exposure_20260912 are task-owned. The
existing learner and sweep are imported unchanged; reference parity is checked.
"""
import argparse
import copy
import hashlib
import json
import math
import os
from datetime import date, datetime, timezone
from pathlib import Path
import sqlite3
import time

# Keep linear algebra bounded when the two regimes run in separate processes.
for variable in ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS"):
    os.environ[variable] = "1"

import numpy as np
import pandas as pd

import config
import learner
import ledger
import robustness
import sweep

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs" / "higher_exposure_20260912"
ROSTER = ["supply_chain", "neighbors", "technical", "mean_reversion", "events", "risk", "macro"]
LEDGERS = {
    "recent": ROOT / "state/backtest_research_good_beta.sqlite",
    "stress": ROOT / "state/backtest_research_pre2024_beta.sqlite",
}
BASE = dict(lam=150.0, half_life=90, min_conv=0.10, size_k=0.60, cap=0.15,
            gross=1.50, top_n=15, band=0.30, vol_target=0.50, horizons=(10, 20),
            exec="open", oos_end="2025-09-24", cost_model="cap", target_mode="raw",
            agents_only=tuple(ROSTER))
VARIANTS = {
    "baseline": {}, "gross_200": {"gross": 2.0}, "size_080": {"size_k": 0.8},
    "gross_200_size_080": {"gross": 2.0, "size_k": 0.8},
    "rank_floor_005": {"rank_always": True, "floor_w": 0.05},
}
RATES = (0.0, 0.05, 0.10)
SNAPSHOT = OUT / "prices_adjusted_2018_20260912_complete.pkl"


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False), encoding="utf-8")


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def connect_readonly(path):
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)


def download():
    import yfinance as yf
    target = OUT / "prices_adjusted_2018_20260912.pkl"
    if target.exists():
        raise FileExistsError("Frozen snapshot already exists; do not silently overwrite it")
    symbols = {"SOXX", "SPY"}
    for database in LEDGERS.values():
        with connect_readonly(database) as connection:
            symbols.update(row[0] for row in connection.execute("SELECT DISTINCT ticker FROM predictions"))
    yf.set_tz_cache_location(str(OUT / "yfinance_cache"))
    raw = yf.download(sorted(symbols), start="2018-01-01", end="2026-09-13",
                      auto_adjust=True, progress=False, threads=True)
    closes, opens = raw["Close"].copy(), raw["Open"].copy()
    for frame in (closes, opens):
        frame.index = pd.to_datetime(frame.index).tz_localize(None).normalize()
        frame.sort_index(inplace=True)
    missing = sorted(symbols - set(closes.columns))
    if missing or closes["SOXX"].dropna().empty:
        raise ValueError(f"Incomplete price download: {missing}")
    pd.to_pickle({"closes": closes, "opens": opens}, target)
    metadata = {
        "retrieved_at": datetime.now(timezone.utc).isoformat(), "source": "yfinance adjusted daily Open/Close",
        "path": str(target), "sha256": sha256(target), "symbols": sorted(symbols),
        "rows": len(closes), "start": str(closes.index.min().date()), "end": str(closes.index.max().date()),
        "original_round24_snapshot_available": False,
        "note": "One NEW snapshot shared by both regimes and every scenario. Original round24 used uncached vendor downloads.",
        "nonmissing_close_counts": {name: int(closes[name].notna().sum()) for name in sorted(symbols)},
    }
    write_json(OUT / "price_manifest.json", metadata)
    print(json.dumps({key: metadata[key] for key in ("path", "sha256", "rows", "start", "end")} ), flush=True)


def finalize_prices():
    """Retry only completely missing symbols BEFORE any candidate is evaluated."""
    import yfinance as yf
    if SNAPSHOT.exists():
        raise FileExistsError("The validated frozen snapshot already exists")
    original = OUT / "prices_adjusted_2018_20260912.pkl"
    data = pd.read_pickle(original)
    missing = [symbol for symbol in data["closes"] if data["closes"][symbol].notna().sum() == 0]
    yf.set_tz_cache_location(str(OUT / "yfinance_cache"))
    for symbol in missing:
        raw = yf.download([symbol], start="2018-01-01", end="2026-09-13",
                          auto_adjust=True, progress=False, threads=False)
        for field, name in (("Close", "closes"), ("Open", "opens")):
            series = raw[field][symbol] if isinstance(raw.columns, pd.MultiIndex) else raw[field]
            if series.notna().sum() == 0:
                raise ValueError(f"Still missing {symbol}; do not start comparisons")
            series.index = pd.to_datetime(series.index).tz_localize(None).normalize()
            data[name][symbol] = series.reindex(data[name].index)
    pd.to_pickle(data, SNAPSHOT)
    manifest = json.loads((OUT / "price_manifest.json").read_text(encoding="utf-8"))
    manifest.update({"final_path":str(SNAPSHOT),"final_sha256":sha256(SNAPSHOT),
                     "retry_before_freeze":missing,"frozen_at":datetime.now(timezone.utc).isoformat(),
                     "remaining_all_missing_symbols":[symbol for symbol in data["closes"] if data["closes"][symbol].notna().sum() == 0]})
    write_json(OUT / "price_manifest_complete.json",manifest)
    print(json.dumps({key:manifest[key] for key in ("final_path","final_sha256","retry_before_freeze","remaining_all_missing_symbols")}),flush=True)


def build_inputs(regime, closes, opens):
    database = LEDGERS[regime]
    sweep.DB = ledger.DB = database
    config.PROGRESS_UPLOAD = "never"
    config.WARM_START_WEIGHT = 0.0
    config.AGENTS = list(ROSTER)
    config.HORIZONS = (10, 20)
    learner.HALF_LIFE_DAYS = 90
    learner.PRIOR_STRENGTH = 150.0
    learner.LAMBDA_GRID = (150.0,)
    learner.DIR_TERMS, learner.NONNEG = True, False
    learner.MODEL_FILE = OUT / f"model_{regime}_scratch.json"
    learner._CACHE.clear()
    by_date = sweep.load_signals()
    dates = sorted(by_date)
    index = closes.index
    position = {stamp.date().isoformat(): i for i, stamp in enumerate(index)}
    entries = [(day, position[day]) for k, day in enumerate(dates)
               if k >= 30 and day in position and position[day] + 10 < len(index)]
    cache_path = OUT / f"daily_models_{regime}.json"
    identity = {
        "ledger_sha256": sha256(database), "learner_sha256": sha256(ROOT / "learner.py"),
        "protocol_sha256": sha256(OUT / "protocol.md"), "roster": ROSTER,
        "target_column": "abnormal (already beta-adjusted)", "first": entries[0][0], "last": entries[-1][0],
    }
    models = {}
    if cache_path.exists():
        saved = json.loads(cache_path.read_text(encoding="utf-8"))
        if saved["identity"] != identity:
            raise ValueError("Daily-model cache identity mismatch; never combine changing sources")
        models = saved["models"]
    start = time.monotonic()
    for count, (day, _) in enumerate(entries, 1):
        if day not in models:
            models[day] = learner.fit(date.fromisoformat(day), asof=date.fromisoformat(day),
                                     target_mode="raw", model_file=learner.MODEL_FILE)
        if count % 50 == 0 or count == len(entries):
            write_json(cache_path, {"identity": identity, "models": models})
            print(f"{regime}: daily fits {count}/{len(entries)} ({time.monotonic()-start:.1f}s)", flush=True)
    days = []
    for day, i in entries:
        conv, _ = learner.predict(by_date[day], models[day])
        next_open, mark_open = opens.iloc[i + 1], opens.iloc[i + 2]
        valid = next_open.notna() & mark_open.notna() & next_open.ne(0)
        returns = (mark_open[valid] / next_open[valid] - 1).to_dict()
        days.append({"date": day, "exec_date": index[i + 1].date().isoformat(),
                     "mark_date": index[i + 2].date().isoformat(),
                     "calendar_days": int((index[i + 2] - index[i + 1]).days),
                     "conv": conv, "returns": returns})
    return by_date, days, models, identity


def replay(days, params, annual_rate, cost_bps=None):
    previous, curve = {}, []
    equity, benchmark = 1.0, 1.0
    for day in days:
        positive = params.get("rank_always", False)
        names = sorted(((ticker, conviction) for ticker, conviction in day["conv"].items()
                        if (conviction > 0 if positive else conviction >= params["min_conv"])),
                       key=lambda item: -item[1])[:params["top_n"]]
        weights = {ticker: min(conviction * params["size_k"], params["cap"]) for ticker, conviction in names}
        if positive:
            weights = {ticker: min(max(weight, params["floor_w"]), params["cap"])
                       for ticker, weight in weights.items()}
        desired_gross = sum(weights.values())
        ceiling_binds = desired_gross > params["gross"]
        if ceiling_binds:
            weights = {ticker: weight * params["gross"] / desired_gross for ticker, weight in weights.items()}
        vol_multiplier = 1.0
        if len(curve) >= 20:
            realized = float(np.std([row["ret"] for row in curve[-20:]])) * math.sqrt(252)
            if realized > params["vol_target"]:
                vol_multiplier = params["vol_target"] / realized
                weights = {ticker: weight * vol_multiplier for ticker, weight in weights.items()}
        # Match sweep ordering exactly, including its non-drifting weight book.
        for ticker in list(weights):
            if ticker in previous and abs(weights[ticker] - previous[ticker]) < params["band"] * weights[ticker]:
                weights[ticker] = previous[ticker]
        changes = {ticker: abs(weights.get(ticker, 0.0) - previous.get(ticker, 0.0))
                   for ticker in set(weights) | set(previous)}
        turnover = sum(changes.values())
        trading_cost = sum(change * sweep._cost_bps(ticker, "cap", cost_bps)
                           for ticker, change in changes.items()) / 10_000
        gross = sum(weights.values())
        borrowed = max(gross - 1.0, 0.0)
        financing = borrowed * annual_rate * day["calendar_days"] / 365.0
        price_return = sum(weight * day["returns"].get(ticker, 0.0) for ticker, weight in weights.items())
        net_return = price_return - trading_cost - financing
        if net_return <= -1:
            raise ValueError("Portfolio wiped out; cannot continue log-return replay")
        equity *= 1 + net_return
        benchmark *= 1 + day["returns"]["SOXX"]
        curve.append({"date": day["date"], "exec_date": day["exec_date"], "mark_date": day["mark_date"],
                      "calendar_days": day["calendar_days"], "portfolio": equity, "soxx": benchmark,
                      "ret": net_return, "price_return": price_return, "trading_cost": trading_cost,
                      "financing_cost": financing, "turnover": turnover, "gross": gross,
                      "cash": 1 - gross, "borrowed": borrowed, "n": len(weights),
                      "desired_gross": desired_gross, "ceiling_binds": ceiling_binds,
                      "postband_above_ceiling": gross > params["gross"] + 1e-9,
                      "vol_multiplier": vol_multiplier,
                      "missing_price_weight": sum(weight for ticker, weight in weights.items() if ticker not in day["returns"]),
                      "weights": weights})
        previous = weights
    return curve


def metrics(curve):
    if not curve:
        return None
    returns = np.asarray([row["ret"] for row in curve])
    log_returns = np.log1p(returns)
    equity = np.exp(np.cumsum(log_returns))
    with_start = np.r_[1.0, equity]
    soxx = float(np.prod([1 + row["soxx_ret"] for row in curve])) if "soxx_ret" in curve[0] else None
    # Segment benchmark is re-based from its own open-to-open returns.
    if soxx is None:
        raise ValueError("Missing segment benchmark returns")
    gross = np.asarray([row["gross"] for row in curve])
    turnover = float(np.mean([row["turnover"] for row in curve]))
    sharpe = robustness.sharpe(log_returns)
    excess = float(equity[-1] - soxx)
    return {
        "start": curve[0]["date"], "end": curve[-1]["date"], "days": len(curve),
        "total_return": float(equity[-1]-1), "soxx_return": soxx-1, "excess_vs_soxx": excess,
        "sharpe": sharpe, "ann_vol": float(np.std(log_returns)*math.sqrt(252)),
        "max_drawdown": float(np.max(1-with_start/np.maximum.accumulate(with_start))),
        "max_drawdown_repository": float(np.max(1-equity/np.maximum.accumulate(equity))),
        "turnover_per_day": turnover, "score": sharpe + 0.5*excess - 0.5*turnover,
        "gross_mean": float(gross.mean()),
        "gross_quantiles": {str(q): float(np.quantile(gross,q)) for q in (0,0.05,0.25,0.5,0.75,0.95,1)},
        "gross_below_020": float(np.mean(gross < 0.2)), "gross_below_050": float(np.mean(gross < 0.5)),
        "gross_above_100": float(np.mean(gross > 1.0)), "gross_above_150": float(np.mean(gross > 1.5)),
        "gross_at_least_180": float(np.mean(gross >= 1.8)),
        "average_cash_net": float(np.mean(1-gross)), "average_positive_cash": float(np.mean(np.maximum(1-gross,0))),
        "average_borrowed": float(np.mean(np.maximum(gross-1,0))),
        "average_names": float(np.mean([row["n"] for row in curve])),
        "ceiling_binding_fraction": float(np.mean([row["ceiling_binds"] for row in curve])),
        "postband_above_ceiling_fraction": float(np.mean([row["postband_above_ceiling"] for row in curve])),
        "vol_scaled_fraction": float(np.mean([row["vol_multiplier"] < 1 for row in curve])),
        "trading_cost_sum_equity_fractions": sum(row["trading_cost"] for row in curve),
        "financing_cost_sum_equity_fractions": sum(row["financing_cost"] for row in curve),
        "average_missing_price_weight": float(np.mean([row["missing_price_weight"] for row in curve])),
        "last_gross": float(gross[-1]), "last_names": curve[-1]["n"],
    }


def run(regime):
    prices = SNAPSHOT
    frozen = pd.read_pickle(prices)
    closes = frozen["closes"].loc[frozen["closes"]["SOXX"].notna()]
    opens = frozen["opens"].reindex(closes.index)
    inputs, days, models, identity = build_inputs(regime, closes, opens)
    state_universe = ROOT / "state/universe.json"
    sweep._CAPS = json.loads(state_universe.read_text(encoding="utf-8"))["market_caps"]
    identity.update({"prices_sha256": sha256(prices), "universe_sha256": sha256(state_universe),
                     "runner_sha256": sha256(Path(__file__)), "sweep_sha256": sha256(ROOT/"sweep.py")})
    scenarios = []
    original_fit = learner.fit
    learner.fit = lambda today=None, asof=None, target_mode=None, model_file=None: copy.deepcopy(models[today.isoformat()])
    try:
        for name, change in VARIANTS.items():
            params = dict(BASE, **change)
            for cost_label, override in (("cap",None),("flat30",30.0)):
                for rate in RATES:
                    curve = replay(days, params, rate, override)
                    for row, day in zip(curve, days):
                        row["soxx_ret"] = day["returns"]["SOXX"]
                    segments = {"full": metrics(curve),
                                "oos": metrics([row for row in curve if row["date"] < BASE["oos_end"]]),
                                "is": metrics([row for row in curve if row["date"] >= BASE["oos_end"]])}
                    parity = None
                    if rate == 0 and (cost_label == "cap" or name == "baseline"):
                        reference = sweep.simulate(inputs, closes, dict(params,cost_bps=override), opens=opens)
                        full = segments["full"]
                        checks = {"total_return": round(full["total_return"],4), "sharpe": round(full["sharpe"],2),
                                  "max_drawdown": round(full["max_drawdown_repository"],4),
                                  "avg_gross": round(full["gross_mean"],3),
                                  "turnover_per_day": round(full["turnover_per_day"],3)}
                        for key,value in checks.items():
                            if abs(value-reference[key]) > 1e-8:
                                raise AssertionError(f"{regime}/{name}/{cost_label} parity {key}: {value} vs {reference[key]}")
                        expected = [round(float(np.log1p(row["ret"])),5) for row in curve]
                        if expected != reference["rets"]:
                            raise AssertionError("Day-by-day reference return parity failed")
                        parity = {"passed":True,"daily_rounded_log_returns_equal":True,"metrics":checks}
                    scenario = {"name":name,"cost":cost_label,"annual_financing":rate,"params":params,
                                **segments,"parity":parity,"curve":curve}
                    scenarios.append(scenario)
                    print(f"{regime}/{name}/{cost_label}/rate{rate:.0%}: return {segments['full']['total_return']:.3%}, "
                          f"Sharpe {segments['full']['sharpe']:.3f}, gross {segments['full']['gross_mean']:.1%}", flush=True)
                    write_json(OUT/f"results_{regime}.json", {"identity":identity,"scenarios":scenarios})
    finally:
        learner.fit = original_fit
    if sha256(LEDGERS[regime]) != identity["ledger_sha256"]:
        raise AssertionError("Source ledger changed during research")
    print(f"{regime}: all scenarios complete; source ledger preserved", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--download",action="store_true")
    parser.add_argument("--finalize-prices",action="store_true")
    parser.add_argument("--regime",choices=LEDGERS)
    args = parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    if args.download:
        download()
    elif args.finalize_prices:
        finalize_prices()
    elif args.regime:
        run(args.regime)
    else:
        parser.error("Choose --download or --regime")


if __name__ == "__main__":
    main()
