"""Walk-forward backtest of the point-in-time agents and the stacking learner.

What it does
  1. For every trading day t in the window, run the agents that can be computed
     honestly as of t (no look-ahead): technical, mean_reversion, risk, macro,
     events (earnings history), and point-in-time versions of supply_chain and
     neighbors that only see earnings-call signals dated <= t.
  2. Record each opinion in state/backtest.sqlite (same schema as the live
     ledger) together with the realised abnormal return vs SOXX after 5/10/20
     trading days.
  3. Walk forward: every week refit the stacking learner on rows whose outcome
     was already known at t, form the portfolio with the live sizing rules,
     and accumulate next-day returns net of 5 bps per unit of turnover.
  4. Write state/backtest_report.json: portfolio vs SOXX/SPY, per-agent IC,
     learned-vs-equal-prior IC, equity curves, and the caveats.

What it cannot do
  * fundamentals (yfinance .info is not point-in-time) and the three Claude
    agents are not simulated; they enter the live model at the equal prior.
  * the universe is today's list (survivorship), the supply-chain graph's
    structure (edges) is today's; only its dated signals are filtered by time.

Run:  python backtest.py --days 250
      python backtest.py --days 250 --exec open --tag _open   # trade at the NEXT open, like the live cycle
The live learner warm-starts from these rows at half weight (config.WARM_START_WEIGHT).

Progress: every refit the run writes state/backtest_progress.json (and uploads it to the
Blob store as semiband-v2/backtest_progress.json) with the curve so far, monthly returns,
agent IC per horizon and an ETA; the website's /backtest page polls it. The final report
also carries robustness.summary(): bootstrap Sharpe CI, deflated Sharpe for the number of
sweep trials, calendar tables, cost sensitivity and a rolling Sharpe.
"""
import argparse
import json
import logging
import math
import re
import sqlite3
import time
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd

import config
import journal
import ledger
import learner
import market
import portfolio
import robustness
import universe as universe_mod
from agents import macro, mean_reversion, ml_ranker, momentum, risk, sue, technical, events
from agents.base import Signal, clip
from agents.supply_chain import _load, _POSITIVE
from agents.neighbors import _EXPAND

log = logging.getLogger("backtest")
DB = config.STATE_DIR / "backtest.sqlite"
REPORT = config.STATE_DIR / "backtest_report.json"
PROGRESS = config.STATE_DIR / "backtest_progress.json"
PROGRESS_BLOB = "semiband-v2/backtest_progress.json"
CURVE_POINTS = 300                                   # the live page gets the curve thinned to this many points
_DATE = re.compile(r"\((\d{2})-(\d{2})-(\d{4})\)")
PIT_AGENTS = ["supply_chain", "neighbors", "technical", "mean_reversion", "events", "risk", "macro"]
EXTRA_AGENTS = {"momentum": None, "sue": None, "ml_ranker": None}   # re-testable with --extra momentum,sue,ml_ranker


def _label_date(label):
    m = _DATE.search(label or "")
    return date(int(m.group(3)), int(m.group(1)), int(m.group(2))) if m else None


class PointInTimeMap:
    """Dated earnings-call signals per company, so the map can be queried 'as of t'."""

    def __init__(self):
        graph, exposure, full_cap = _load()
        self.signals = {}          # company -> [(date, text)]
        for n in graph["nodes"]:
            rows = []
            for q in n.get("quarterly_data") or []:
                d = _label_date(q.get("quarter"))
                if d:
                    rows.append((d, (q.get("signal") or "").lower()))
            rows.sort()
            self.signals[n["id"]] = rows
        self.full_cap = full_cap   # company -> date flagged
        self.chains = {n["id"]: set(n.get("chains") or []) for n in graph["nodes"]}
        self.signals_chain = {}    # company -> [(date, text, chain)]
        for n in graph["nodes"]:
            rows = []
            for q in n.get("quarterly_data") or []:
                d = _label_date(q.get("quarter"))
                if d:
                    rows.append((d, (q.get("signal") or "").lower(), q.get("chain")))
            self.signals_chain[n["id"]] = rows
        self.customers, self.suppliers = {}, {}
        for e in graph["edges"]:
            self.customers.setdefault(e["source"], set()).add(e["target"])
            self.suppliers.setdefault(e["target"], set()).add(e["source"])

    def recent(self, company, asof, days):
        return [(d, t) for d, t in self.signals.get(company, []) if asof - timedelta(days=days) <= d <= asof]

    def supply_chain(self, ticker, company, asof):
        rec = self.recent(company, asof, 120)
        allrows = [d for d, _ in self.signals.get(company, []) if d <= asof]
        if not allrows:
            return None
        tight = sum(1 for _, t in rec if any(w in t for w in _POSITIVE))
        days_since = (asof - max(allrows)).days
        score = 0.15 * min(tight, 4)
        fc = self.full_cap.get(company)
        if fc and fc <= asof:
            score += 0.5 if (asof - fc).days <= 150 else 0.2
        if days_since <= 45:
            score += 0.2
        elif days_since <= 90:
            score += 0.1
        elif days_since > 180:
            score -= 0.3
        confidence = clip(0.25 + 0.05 * min(len(rec), 10) + (0.2 if days_since <= 90 else 0), 0.1, 0.9)
        return Signal("supply_chain", ticker, math.tanh(score), confidence, 20,
                      f"pit: {tight} tight markers in 120d, latest {days_since}d old")

    def neighbors(self, ticker, company, asof):
        cust, supp = self.customers.get(company, set()), self.suppliers.get(company, set())
        if not cust and not supp:
            return None

        def heat(nb):
            rec = self.recent(nb, asof, 90)
            h = 0.0
            if any(any(w in t for w in _POSITIVE) for _, t in rec):
                h += 0.5
            if rec:
                h += 0.2
            return min(h, 1.0)
        c = [heat(n) for n in cust]
        s = [heat(n) for n in supp]
        c_avg = sum(c) / len(c) if c else 0.0
        s_avg = sum(s) / len(s) if s else 0.0
        # read-through: customers' dated statements on the chains this company sells into
        my_chains = self.chains.get(company, set())
        hits, n_rt = 0, 0
        for nb in cust:
            for d, t, ch in self.signals_chain.get(nb, []):
                if asof - timedelta(days=120) <= d <= asof and ch in my_chains:
                    n_rt += 1
                    if any(w in t for w in _POSITIVE) or any(w in t for w in _EXPAND):
                        hits += 1
        rt = 0.5 * hits / n_rt if n_rt >= 3 else 0.0   # measured only; tested 2026-09-10 and rejected from the score
        direction = math.tanh(1.4 * c_avg + 0.5 * s_avg - 0.25)
        confidence = clip(0.2 + 0.05 * min(len(cust) + len(supp), 10), 0.2, 0.75)
        return Signal("neighbors", ticker, direction, confidence, 20, f"pit: customer heat {c_avg:.2f}, read-through {rt:+.2f}")


def _init_db():
    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    con.executescript(ledger.SCHEMA)
    con.close()


def thin(curve, n=CURVE_POINTS):
    step = max(1, len(curve) // n)
    out = curve[::step]
    return out + ([curve[-1]] if curve and (len(curve) - 1) % step else [])


def publish_progress(payload):
    """state/backtest_progress.json + the Blob copy the website polls. Never raises."""
    try:
        payload = dict(payload, updated=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        body = json.dumps(payload, ensure_ascii=False)
        PROGRESS.write_text(body, encoding="utf-8")
        journal._upload(PROGRESS_BLOB, body)
    except Exception as exc:
        log.warning("progress publish failed: %s", exc)


def run(days=250, refit_every=5, warmup=30, tag="", extra=(), cap=None, exec_mode="close"):
    """tag: suffix for the output files (state/backtest<tag>.sqlite / backtest_report<tag>.json)
    so a long build can run while sweeps read the default files.
    exec_mode: 'close' = trade at the close the signals were computed on (optimistic);
               'open'  = trade at the NEXT open and hold to the following open (what the live cycle does)."""
    global DB, REPORT, PIT_AGENTS
    extra_mods = [{"momentum": momentum, "sue": sue, "ml_ranker": ml_ranker}[e] for e in extra]
    PIT_AGENTS = PIT_AGENTS + list(extra)
    if tag:
        DB = config.STATE_DIR / f"backtest{tag}.sqlite"
        REPORT = config.STATE_DIR / f"backtest_report{tag}.json"
    config.STATE_DIR.mkdir(exist_ok=True)
    run_info = {"kind": "backtest", "tag": tag, "days": days, "exec": exec_mode, "extra": list(extra), "cap": cap,
                "started": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    publish_progress(dict(run_info, status="loading", pct=0.0, message="downloading prices and earnings"))
    try:
        return _run(days, refit_every, warmup, extra_mods, exec_mode, run_info)
    except Exception as exc:
        publish_progress(dict(run_info, status="failed", message=f"{type(exc).__name__}: {exc}"))
        raise


def _run(days, refit_every, warmup, extra_mods, exec_mode, run_info):
    if run_info["cap"]:
        config.MAX_MARKET_CAP = run_info["cap"]
        universe_mod.CACHE = config.STATE_DIR / f"universe_cap{int(run_info['cap'] / 1e9)}B.json"
        universe = universe_mod.refresh()
    else:
        universe = universe_mod.load()
    tickers = list(universe)
    extra = [config.BENCHMARK, "SPY", "^VIX", "^TNX"]
    closes = market.closes(tickers + extra, lookback_days=int(days * 1.6) + 400, cache=False)
    closes = closes[closes[config.BENCHMARK].notna() & closes["SPY"].notna()]   # drop holiday rows that only ^VIX/^TNX filled
    idx = closes.index
    bench = closes[config.BENCHMARK]
    # execution prices: close mode trades at close t; open mode buys at open t+1 and marks at open t+2
    if exec_mode == "open":
        px = market.opens(tickers + [config.BENCHMARK, "SPY"], lookback_days=int(days * 1.6) + 400).reindex(idx)
        shift = 1
    else:
        px, shift = closes, 0
    earnings = market.earnings(tickers, limit=40)
    pit = PointInTimeMap()

    _init_db()
    ledger.DB = DB                                   # learner reads through ledger.connect()
    learner.MODEL_FILE = config.STATE_DIR / "backtest_model.json"
    live_agents = config.AGENTS
    config.AGENTS = PIT_AGENTS                       # the prior and the sizing see only the simulated agents

    end = len(idx) - 21                              # need +20 trading days for scoring
    start = max(260, end - days)
    log.info("backtest %s -> %s (%d days), %d tickers", idx[start].date(), idx[end - 1].date(), end - start, len(tickers))
    run_info = dict(run_info, period={"start": idx[start].date().isoformat(), "end": idx[end - 1].date().isoformat(),
                                      "trading_days": end - start}, tickers=len(tickers), agents=PIT_AGENTS)

    equity, curve, turnover_total = 1.0, [], 0.0
    equity_rank = 1.0                                # signal-quality line: top-15 by conviction, equal weight, 100% gross
    prev_w = {}
    model = None
    ic_learned, ic_prior = [], []
    t0 = time.time()
    base = start + warmup + shift                    # benchmark curves are rebased to the first traded day
    for i in range(start, end):
        t = idx[i].date()
        window = closes.iloc[: i + 1]
        ctx = {"closes": window, "asof": t, "earnings": earnings, "today": t.isoformat()}
        signals = []
        for a in [technical, mean_reversion, risk, macro] + extra_mods:
            try:
                signals += a.run(universe, ctx)
            except Exception as exc:
                log.warning("%s @ %s: %s", a.NAME, t, exc)
        try:
            signals += events.run(universe, ctx)
        except Exception as exc:
            log.warning("events @ %s: %s", t, exc)
        for tk, company in universe.items():
            for s in (pit.supply_chain(tk, company, t), pit.neighbors(tk, company, t)):
                if s:
                    signals.append(s)
        # record predictions + realised outcomes (known only later; the learner filters by maturity)
        last = {tk: float(window[tk].iloc[-1]) for tk in tickers if not pd.isna(window[tk].iloc[-1])}
        ledger.add_predictions(t.isoformat(), signals, last)
        with ledger.connect() as con:
            rows = con.execute("SELECT id, ticker, direction FROM predictions WHERE date = ?", (t.isoformat(),)).fetchall()
            for r in rows:
                for h in config.HORIZONS:
                    c0, c1 = closes[r["ticker"]].iloc[i], closes[r["ticker"]].iloc[i + h]
                    b0, b1 = bench.iloc[i], bench.iloc[i + h]
                    if any(pd.isna(v) for v in (c0, c1, b0, b1)):
                        continue
                    abn = float(c1 / c0 - 1) - float(b1 / b0 - 1)
                    hit = None if abs(r["direction"]) < 0.1 else int((r["direction"] > 0) == (abn > 0))
                    con.execute("INSERT OR REPLACE INTO scores VALUES (?,?,?,?,?,?,?)",
                                (r["id"], h, idx[i + h].date().isoformat(), float(c1 / c0 - 1), float(b1 / b0 - 1), abn, hit))
        if i - start < warmup:
            continue
        if model is None or (i - start) % refit_every == 0:
            model = learner.fit(t, asof=t)
        conv, _ = learner.predict(signals, model)
        conv_prior, _ = learner.predict(signals, None)
        # IC of today's convictions against the 10-day outcome (evaluated later in the loop's own scores)
        y10 = {}
        for tk in conv:
            c0, c1 = closes[tk].iloc[i], closes[tk].iloc[i + 10]
            b0, b1 = bench.iloc[i], bench.iloc[i + 10]
            if not any(pd.isna(v) for v in (c0, c1, b0, b1)):
                y10[tk] = float(c1 / c0 - 1) - float(b1 / b0 - 1)
        common = [tk for tk in y10 if tk in conv_prior]
        if len(common) >= 10:
            ic_learned.append(learner.ic(np.array([conv[tk] for tk in common]), np.array([y10[tk] for tk in common])))
            ic_prior.append(learner.ic(np.array([conv_prior[tk] for tk in common]), np.array([y10[tk] for tk in common])))
        # portfolio: same sizing as live; next-day return from close t to close t+1 (close mode)
        # or from open t+1 to open t+2 (open mode, what the live cycle actually gets)
        targets = portfolio.targets(conv, config.CAPITAL)      # dollars, same rules as live
        w = {tk: v / config.CAPITAL for tk, v in targets.items()}   # -> weights
        turnover = sum(abs(w.get(tk, 0) - prev_w.get(tk, 0)) for tk in set(w) | set(prev_w))
        def day_ret(tk):
            c0, c1 = px[tk].iloc[i + shift], px[tk].iloc[i + 1 + shift]
            return None if (pd.isna(c0) or pd.isna(c1) or c0 <= 0) else float(c1 / c0) - 1
        ret = sum(w_i * r for tk, w_i in w.items() if (r := day_ret(tk)) is not None)
        ret -= turnover * config.COST_BPS / 10_000
        equity *= 1 + ret
        turnover_total += turnover
        prev_w = w
        top = sorted(conv, key=lambda tk: -conv[tk])[:config.TOP_N]
        rank_rets = [r for tk in top if (r := day_ret(tk)) is not None]
        rank_ret = float(np.mean(rank_rets)) if rank_rets else 0.0
        equity_rank *= 1 + rank_ret - 0.1 * config.COST_BPS / 10_000    # ~10% daily turnover assumed
        curve.append({"date": t.isoformat(), "portfolio": equity, "rank": equity_rank, "gross": sum(w.values()), "n": len(w),
                      "ret": ret, "turnover": turnover,
                      "soxx": float(px[config.BENCHMARK].iloc[i + 1 + shift] / px[config.BENCHMARK].iloc[base]),
                      "spy": float(px["SPY"].iloc[i + 1 + shift] / px["SPY"].iloc[base])})
        if (i - start) % 50 == 0:
            log.info("  %s equity %.3f soxx %.3f (%.0fs)", t, equity, curve[-1]["soxx"], time.time() - t0)
        if (i - start) % refit_every == 0 or i == end - 1:
            done, total, elapsed = i - start + 1, end - start, time.time() - t0
            publish_progress(dict(run_info, status="running", pct=round(done / total, 4), day=done, total_days=total,
                                  date=t.isoformat(), elapsed_s=round(elapsed), eta_s=round(elapsed / done * (total - done)),
                                  equity=round(equity, 4), rank=round(equity_rank, 4), soxx=round(curve[-1]["soxx"], 4),
                                  spy=round(curve[-1]["spy"], 4), gross=round(sum(w.values()), 3), names=len(w),
                                  turnover_per_day=round(turnover_total / len(curve), 3),
                                  ic_10d={"learned": round(float(np.mean(ic_learned)), 4) if ic_learned else None,
                                          "equal_prior": round(float(np.mean(ic_prior)), 4) if ic_prior else None},
                                  model={h: {k: v.get(k) for k in ("n_obs", "cv_ic", "agent_ic", "w_conf")}
                                         for h, v in model["horizons"].items()},
                                  holdings=sorted(w, key=lambda tk: -w[tk]),
                                  monthly=robustness.calendar(curve)["monthly"], curve=thin(curve)))

    ledger.DB = config.STATE_DIR / "ledger.sqlite"   # restore the live ledger path
    learner.MODEL_FILE = config.STATE_DIR / "model.json"
    config.AGENTS = live_agents

    rets = np.diff(np.log([1.0] + [c["portfolio"] for c in curve]))
    soxx = np.diff(np.log([1.0] + [c["soxx"] for c in curve]))
    dd = 1 - np.array([c["portfolio"] for c in curve]) / np.maximum.accumulate([c["portfolio"] for c in curve])
    n = len(curve)
    report = {
        "generated": date.today().isoformat(),
        "period": {"start": curve[0]["date"], "end": curve[-1]["date"], "trading_days": n},
        "execution": exec_mode,
        "agents": PIT_AGENTS,
        "portfolio": {
            "total_return": round(curve[-1]["portfolio"] - 1, 4),
            "soxx_return": round(curve[-1]["soxx"] - 1, 4),
            "spy_return": round(curve[-1]["spy"] - 1, 4),
            "ann_vol": round(float(np.std(rets) * math.sqrt(252)), 4),
            "sharpe": round(float(np.mean(rets) / (np.std(rets) or 1e-9) * math.sqrt(252)), 2),
            "max_drawdown": round(float(dd.max()), 4),
            "avg_gross": round(float(np.mean([c["gross"] for c in curve])), 3),
            "avg_names": round(float(np.mean([c["n"] for c in curve])), 1),
            "turnover_per_day": round(turnover_total / n, 3),
            "tracking_corr_soxx": round(float(np.corrcoef(rets, soxx)[0, 1]), 3) if n > 5 else None,
        },
        "rank_portfolio": {
            "description": f"top {config.TOP_N} by conviction, equal weight, 100% invested every day (signal quality, ignores the live sizing rules)",
            "total_return": round(curve[-1]["rank"] - 1, 4),
            "excess_vs_soxx": round(curve[-1]["rank"] - curve[-1]["soxx"], 4),
            "sharpe": round(float(np.mean(np.diff(np.log([1.0] + [c["rank"] for c in curve]))) /
                                  (np.std(np.diff(np.log([1.0] + [c["rank"] for c in curve]))) or 1e-9) * math.sqrt(252)), 2),
        },
        "ic_10d": {"learned": round(float(np.mean(ic_learned)), 4) if ic_learned else None,
                   "equal_prior": round(float(np.mean(ic_prior)), 4) if ic_prior else None,
                   "days": len(ic_learned)},
        "model_final": {h: {k: v.get(k) for k in ("n_obs", "lambda", "cv_ic", "agent_ic", "w_conf")}
                        for h, v in (model or {"horizons": {}})["horizons"].items()},
        "robustness": robustness.summary(curve),
        "curve": curve,
        "caveats": [
            "fundamentals and the three Claude agents are not simulated (no point-in-time data / too costly); they enter the live model at the equal prior",
            "universe = today's list (survivorship bias); supply-chain edges are today's structure, only dated call signals are time-filtered",
            ("trades at the NEXT open, marked open to open (what the live cycle does)" if exec_mode == "open"
             else "trades assumed at the close of day t (live trades at the next open: run --exec open for that)")
            + f"; {config.COST_BPS} bps cost per unit turnover",
            "the sizing knobs were chosen by sweeps on the 2025-09 -> 2026-08 window: numbers on that window are in-sample (see robustness.deflated)",
        ],
    }
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    publish_progress(dict(run_info, status="done", pct=1.0, day=n, total_days=n, date=curve[-1]["date"],
                          elapsed_s=round(time.time() - t0), eta_s=0, equity=round(curve[-1]["portfolio"], 4),
                          rank=round(curve[-1]["rank"], 4), soxx=round(curve[-1]["soxx"], 4), spy=round(curve[-1]["spy"], 4),
                          gross=round(curve[-1]["gross"], 3), names=curve[-1]["n"], turnover_per_day=report["portfolio"]["turnover_per_day"],
                          ic_10d=report["ic_10d"], model=report["model_final"], holdings=[],
                          monthly=report["robustness"]["calendar"]["monthly"], curve=thin(curve),
                          portfolio=report["portfolio"], rank_portfolio=report["rank_portfolio"],
                          robustness={k: v for k, v in report["robustness"].items() if k != "calendar"},
                          quarterly=report["robustness"]["calendar"]["quarterly"], caveats=report["caveats"]))
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=250)
    p.add_argument("--refit-every", type=int, default=5)
    p.add_argument("--tag", default="", help="output suffix, e.g. _500")
    p.add_argument("--extra", default="", help="comma list of optional agents to include: momentum,sue,ml_ranker")
    p.add_argument("--cap", type=float, default=None, help="override MAX_MARKET_CAP (e.g. 1e13 for no cap)")
    p.add_argument("--exec", dest="exec_mode", choices=("close", "open"), default="close",
                   help="close = trade at the signal day's close (optimistic); open = trade at the next open like the live cycle")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    r = run(days=args.days, refit_every=args.refit_every, tag=args.tag, extra=tuple(x for x in args.extra.split(",") if x), cap=args.cap,
            exec_mode=args.exec_mode)
    print(json.dumps({k: v for k, v in r.items() if k != "curve"}, indent=2)[:4000])
