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
import importlib
import json
import logging
import math
import os
import pickle
import re
import sqlite3
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import config
import journal
import ledger
import learner
import learning_targets
import market
import portfolio
import robustness
import snapshots
import universe as universe_mod
from agents import macro, mean_reversion, ml_ranker, momentum, risk, sue, technical, events
from agents.base import Signal, clip
from agents import indicators
from agents import graph_pit
from agents.graph_pit import PointInTimeMap

log = logging.getLogger("backtest")
DB = config.STATE_DIR / "backtest.sqlite"
REPORT = config.STATE_DIR / "backtest_report.json"
PROGRESS = config.STATE_DIR / "backtest_progress.json"
PROGRESS_BLOB = "semiband-v2/backtest_progress.json"
CURVE_POINTS = 300                                   # the live page gets the curve thinned to this many points
PROGRESS_EVERY = 5                                   # publish progress every N traded days (an upload costs ~1 s)
PUBLISH = True                                       # --no-publish: keep test runs off the website's Backtest tab
SIM_AGENTS = ["supply_chain", "neighbors", "technical", "mean_reversion", "events", "risk", "macro"]   # everything the replay can compute; all recorded
PIT_AGENTS = [a for a in SIM_AGENTS if a in config.AGENTS]   # the roster the learner and the sizing see = the live roster minus the unsimulated agents
EXTRA_AGENTS = {"momentum": None, "sue": None, "ml_ranker": None}   # re-testable with --extra momentum,sue,ml_ranker


def _prices(kind, symbols, lookback):
    """Closes or opens for a replay. With BACKTEST_PRICE_CACHE=<folder>, runs started the same day share one download
    (parallel variants would otherwise each hit yfinance)."""
    folder = os.environ.get("BACKTEST_PRICE_CACHE")
    path = Path(folder) / f"{kind}_{date.today().isoformat()}_{lookback}_{len(set(symbols))}.pkl" if folder else None
    if path is not None and path.exists():
        return pickle.loads(path.read_bytes())
    df = (market.closes(symbols, lookback_days=lookback, cache=False) if kind == "closes"
          else market.opens(symbols, lookback_days=lookback))
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_bytes(pickle.dumps(df))
        try:
            os.link(tmp, path)       # first writer wins, so parallel runs all trade on one download (2026-09-15: they diverged)
        except FileExistsError:
            pass
        finally:
            tmp.unlink(missing_ok=True)
        return pickle.loads(path.read_bytes())
    return df


def open_row_window(closes, px, i):
    """Closes through day i plus one row dated day i+1 holding that day's OPEN where known (the last close elsewhere, e.g.
    ^VIX / ^TNX or a name that did not open): what the live open refresh sees at 09:30 ET. Never reads day i+1's close."""
    row = closes.iloc[: i + 1].ffill().iloc[-1].copy()
    for symbol, value in px.iloc[i + 1].items():
        if symbol in row.index and pd.notna(value) and value > 0:
            row[symbol] = value
    return pd.concat([closes.iloc[: i + 1], row.to_frame(name=closes.index[i + 1]).T])


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
    """Always writes state/backtest_progress.json (the local viewer polls it); uploads the Blob copy the website
    reads according to config.PROGRESS_UPLOAD: 'always', 'final' (done/failed only) or 'never'. Never raises."""
    if not PUBLISH:
        return
    try:
        payload = dict(payload, updated=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        body = json.dumps(payload, ensure_ascii=False)
        PROGRESS.write_text(body, encoding="utf-8")
        mode = config.PROGRESS_UPLOAD
        if mode == "always" or (mode == "final" and payload.get("status") in ("done", "failed")):
            journal._upload(PROGRESS_BLOB, body)
    except Exception as exc:
        log.warning("progress publish failed: %s", exc)


def long_short_weights(convictions, betas, n, gross):
    """Market-neutral weights (round 33): the top n convictions long and the bottom n short, equal weight within each
    leg. The book's gross is `gross`, split so the legs' betas cancel: long gross/(1+r), short gross*r/(1+r), with
    r = mean long beta / mean short beta bounded 0.5-2. Non-finite convictions are ignored; fewer than two names -> no
    book. -> {ticker: weight}"""
    finite = {tk: c for tk, c in convictions.items() if math.isfinite(c)}
    ranked = sorted(finite, key=lambda tk: finite[tk])
    k = min(n, len(ranked) // 2)
    if k == 0:
        return {}
    longs, shorts = ranked[-k:], ranked[:k]
    beta_long = sum(betas.get(tk, 1.0) for tk in longs) / k
    beta_short = sum(betas.get(tk, 1.0) for tk in shorts) / k
    r = min(2.0, max(0.5, beta_long / beta_short)) if beta_short > 0 else 1.0
    w = {tk: gross / (1 + r) / k for tk in longs}
    w.update({tk: -gross * r / (1 + r) / k for tk in shorts})
    return w


def rank_order(conv, conv_rank):
    """Round 37: the return model's conviction values, as a multiset, assigned to names in the rank model's order (quantile
    mapping), so sizing sees exactly the same values every day and only the ordering can differ. -> {ticker: conviction}"""
    names = sorted(conv, key=lambda tk: conv_rank.get(tk, 0.0))
    return dict(zip(names, sorted(conv.values())))


def run(days=250, refit_every=1, warmup=30, tag="", extra=(), cap=None, exec_mode="close", agents=None, end=None,
        open_refresh=False, label_open=False, label_next_close=False, refresh_agents=None, learn_preopen=False,
        prior_only=False, long_short=None, sleeve_mix=None, rank_order_mode=False, target_clip_sigma=None,
        intercept=None, drop_dir=(), demean=None, demean_group=None, graph_transcripts_only=None, technical_residual=None,
        margin_rate=0.0, gross_target=None, beta_floor=None, vol_target=None, vol_target_mode=None):
    """tag: suffix for the output files (state/backtest<tag>.sqlite / backtest_report<tag>.json)
    so a long build can run while sweeps read the default files.
    exec_mode: 'close' = trade at the close the signals were computed on (optimistic);
               'open'  = trade at the NEXT open and hold to the following open (what the live cycle does)."""
    global DB, REPORT, PIT_AGENTS
    if open_refresh and exec_mode != "open":
        raise ValueError("--open-refresh needs --exec open: the refreshed row is the open the trade executes at")
    if label_open and exec_mode != "open":
        raise ValueError("--label-open needs --exec open: labels start at the open the trade fills at")
    if label_open and label_next_close:
        raise ValueError("choose one label start: --label-open or --label-next-close")
    if (refresh_agents is not None or learn_preopen) and not open_refresh:
        raise ValueError("--refresh-agents and --learn-preopen only apply to --open-refresh")
    unknown = set(refresh_agents or ()) - {"technical", "mean_reversion", "risk", "macro", "events", "fundamentals"} - set(extra)
    if unknown:
        raise ValueError(f"--refresh-agents: not an open-refresh agent: {sorted(unknown)}")
    if refresh_agents is not None and not refresh_agents:
        raise ValueError("--refresh-agents: empty list (omit the flag to refresh config.OPEN_REFRESH_AGENTS)")
    if open_refresh and refresh_agents is None:
        refresh_agents = tuple(config.OPEN_REFRESH_AGENTS)   # as live (fundamentals is not simulated, so it changes nothing here)
    if long_short is not None and long_short < 1:
        raise ValueError("--long-short needs at least one name per leg")
    extra_mods = [{"momentum": momentum, "sue": sue, "ml_ranker": ml_ranker}.get(e) or importlib.import_module(f"agents.{e}")
                  for e in extra]                              # factor_* agents load by name
    if agents:
        PIT_AGENTS = [a for a in SIM_AGENTS if a in agents]
    PIT_AGENTS = PIT_AGENTS + list(extra)
    if tag:
        DB = config.STATE_DIR / f"backtest{tag}.sqlite"
        REPORT = config.STATE_DIR / f"backtest_report{tag}.json"
    config.STATE_DIR.mkdir(exist_ok=True)
    run_info = {"kind": "backtest", "tag": tag, "days": days, "exec": exec_mode, "extra": list(extra), "cap": cap, "end": end,
                "agents_requested": agents, "open_refresh": open_refresh, "label_open": label_open,
                "label_next_close": label_next_close,
                "refresh_agents": list(refresh_agents) if refresh_agents is not None else None, "learn_preopen": learn_preopen,
                "prior_only": prior_only, "long_short": long_short, "sleeve_mix": list(sleeve_mix) if sleeve_mix else None,
                "rank_order": rank_order_mode, "target_clip_sigma": target_clip_sigma,
                "intercept": intercept, "drop_dir": list(drop_dir),
                "demean": bool(config.DEMEAN_CONVICTION) if demean is None else bool(demean),   # None = as the live cycle
                "demean_group": (config.DEMEAN_GROUP if demean_group is None else demean_group) or None,           # round 39
                "graph_transcripts_only": bool(config.GRAPH_TRANSCRIPTS_ONLY) if graph_transcripts_only is None else bool(graph_transcripts_only),
                "technical_residual": bool(config.TECHNICAL_RESIDUAL) if technical_residual is None else bool(technical_residual),   # round 40
                "margin_rate": float(margin_rate or 0.0), "gross_target": gross_target, "beta_floor": beta_floor,                  # round 42
                "vol_target": vol_target, "vol_target_mode": vol_target_mode,                                                     # round 43
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
    if any(m.NAME.startswith("factor_") for m in extra_mods):   # cross-asset factor series (oil, fed funds futures, ...)
        from agents import factors
        extra = sorted(set(extra) | set(factors.SYMBOLS))
    end_date = date.fromisoformat(run_info["end"]) if run_info.get("end") else None
    lookback = int(days * 1.6) + 400 + ((date.today() - end_date).days if end_date else 0)
    closes = _prices("closes", tickers + extra, lookback)
    if end_date:
        closes = closes[closes.index <= pd.Timestamp(end_date)]              # historical window ending before today
    closes = closes[closes[config.BENCHMARK].notna() & closes["SPY"].notna()]   # drop holiday rows that only ^VIX/^TNX filled
    idx = closes.index
    bench = closes[config.BENCHMARK]
    # execution prices: close mode trades at close t; open mode buys at open t+1 and marks at open t+2
    if exec_mode == "open":
        px = _prices("opens", tickers + [config.BENCHMARK, "SPY"], lookback).reindex(idx)
        shift = 1
    else:
        px, shift = closes, 0
    earnings = market.earnings(tickers, limit=40)
    pit = PointInTimeMap(transcripts_only=run_info.get("graph_transcripts_only"))
    groups = graph_pit.groups_from(pit, universe) if run_info.get("demean_group") == "chain" else None   # round 39

    # RSI over the whole history once per ticker (causal, so identical to the day-by-day prefix computation)
    indicators.PRECOMPUTED = {tk: indicators.rsi_series(closes[tk].dropna()) for tk in tickers if tk in closes.columns}
    _init_db()
    ledger.DB = DB                                   # learner reads through ledger.connect()
    learner.MODEL_FILE = config.STATE_DIR / f"backtest_model{run_info.get('tag') or ''}.json"   # per tag: parallel runs never share it
    rank_model_file = config.STATE_DIR / f"backtest_model{run_info.get('tag') or ''}_rank.json"
    learner.TARGET_CLIP_SIGMA = run_info.get("target_clip_sigma")
    learner.INTERCEPT, learner.DROP_DIR = run_info.get("intercept"), tuple(run_info.get("drop_dir") or ())   # round 38
    live_agents, live_residual, live_gross, live_vol = config.AGENTS, config.TECHNICAL_RESIDUAL, config.GROSS_TARGET, config.VOL_TARGET
    config.AGENTS = PIT_AGENTS                       # the prior and the sizing see only the simulated agents
    config.TECHNICAL_RESIDUAL = bool(run_info.get("technical_residual"))   # round 40: the technical agent reads it per call
    if run_info.get("gross_target"):                                       # round 42: portfolio.targets reads the ceiling per call
        config.GROSS_TARGET = float(run_info["gross_target"])
    if run_info.get("vol_target") is not None:                             # round 43: 0 switches the vol brake off
        config.VOL_TARGET = float(run_info["vol_target"]) or None
    vol_hist = []                                                          # round 43: the book's own realised-vol history

    # numpy views of the price frames: the day loop reads single cells thousands of times (same float64 values as .iloc)
    C = closes.to_numpy(dtype=float)
    col = {tk: j for j, tk in enumerate(closes.columns)}
    B = C[:, col[config.BENCHMARK]]
    P = px.to_numpy(dtype=float) if px is not closes else C
    pcol = {tk: j for j, tk in enumerate(px.columns)}
    for etf in run_info.get("sleeve_mix") or ():
        if etf not in col or etf not in pcol:
            raise ValueError(f"--sleeve-mix: {etf} is not in the replay's price set (closes and opens)")
    # per-ticker full-history series for risk / macro (the agents slice them as of each day: same pandas
    # operations on the same values as recomputing from the day's prefix, computed once instead of daily)
    bench_ret_full = closes[config.BENCHMARK].pct_change()
    rolling_betas = learning_targets.rolling_beta(closes)
    hist = {}
    for tk in list(tickers) + [config.BENCHMARK]:
        if tk not in closes.columns:
            continue
        c_full = closes[tk].dropna()
        hist[tk] = {"close": c_full, "rets": c_full.pct_change().dropna()}
        if tk != config.BENCHMARK:
            hist[tk]["pair"] = pd.concat([closes[tk].pct_change(), bench_ret_full], axis=1).dropna()
    end = len(idx) - max(config.HORIZONS) - 1        # need +max(horizon) trading days for scoring
    start = max(260, end - days)
    log.info("backtest %s -> %s (%d days), %d tickers", idx[start].date(), idx[end - 1].date(), end - start, len(tickers))
    run_info = dict(run_info, period={"start": idx[start].date().isoformat(), "end": idx[end - 1].date().isoformat(),
                                      "trading_days": end - start}, tickers=len(tickers), agents=PIT_AGENTS)

    equity, curve, turnover_total = 1.0, [], 0.0
    equity_rank = 1.0                                # signal-quality line: top-15 by conviction, equal weight, 100% gross
    prev_w = {}
    model = None
    ic_learned, ic_prior = [], []
    quint = [[] for _ in range(5)]
    t0 = time.time()
    base = start + warmup + shift                    # benchmark curves are rebased to the first traded day
    label_open = bool(run_info.get("label_open"))      # labels start at day t+1's open (the fill, and what a refreshed signal saw), not at close t
    label_next_close = bool(run_info.get("label_next_close"))   # the live scorer: labels start at the close of the order day t+1
    for i in range(start, end):
        t = idx[i].date()
        window = closes.iloc[: i + 1]
        ctx = {"closes": window, "asof": t, "earnings": earnings, "today": t.isoformat(), "hist": hist, "asof_ts": idx[i]}
        signals, learned = [], []        # signals: what the day trades on; learned: what the ledger records and the learner fits
        refresh = run_info.get("open_refresh")
        refresh_names = run_info.get("refresh_agents") or ()         # the agents that see the open: config.OPEN_REFRESH_AGENTS unless overridden
        learn_preopen = bool(run_info.get("learn_preopen"))     # hybrid: trade on the refreshed signals, learn from the pre-open ones
        if refresh:
            # live open refresh: the price agents see day t+1's open before trading at it. No hist fast path and no
            # precomputed RSI here: both are indexed by date and would hand back day t+1's CLOSE for the appended row.
            open_ctx = {"closes": open_row_window(closes, px, i), "asof": t, "earnings": earnings, "today": t.isoformat()}
        mods = [m for m in (technical, mean_reversion, risk, macro) if m.NAME in PIT_AGENTS] + extra_mods
        if "events" in PIT_AGENTS:
            mods.append(events)
        for a in mods:
            at_open = bool(refresh) and a.NAME in refresh_names
            for use_open in ((True, False) if at_open and learn_preopen else (at_open,)):
                if use_open:
                    saved_rsi, indicators.PRECOMPUTED = indicators.PRECOMPUTED, {}
                try:
                    out = a.run(universe, open_ctx if use_open else ctx)
                except Exception as exc:
                    log.warning("%s @ %s: %s", a.NAME, t, exc)
                    out = []
                finally:
                    if use_open:
                        indicators.PRECOMPUTED = saved_rsi
                if use_open == at_open:
                    signals += out
                if not (use_open and learn_preopen):
                    learned += out
        for tk, company in universe.items():
            for s in ((pit.supply_chain(tk, company, t) if "supply_chain" in PIT_AGENTS else None),
                      (pit.neighbors(tk, company, t) if "neighbors" in PIT_AGENTS else None)):
                if s:
                    signals.append(s)
                    learned.append(s)
        # record predictions + realised outcomes (known only later; the learner filters by maturity)
        last = {tk: float(C[i, col[tk]]) for tk in tickers if not np.isnan(C[i, col[tk]])}
        prediction_betas = {tk: learning_targets.beta_at(rolling_betas, tk, idx[i]) for tk in last}
        ledger.add_predictions(t.isoformat(), learned, last, prediction_betas)
        with ledger.connect() as con:
            rows = con.execute("SELECT id, ticker, direction FROM predictions WHERE date = ?", (t.isoformat(),)).fetchall()
            batch = []
            for r in rows:
                j = col[r["ticker"]]
                for h in config.HORIZONS:
                    c0, c1 = C[i, j], C[i + h, j]
                    b0, b1 = B[i], B[i + h]
                    end_k = i + h
                    if label_open:
                        jp = pcol.get(r["ticker"])
                        c0, b0 = (P[i + 1, jp] if jp is not None else np.nan), P[i + 1, pcol[config.BENCHMARK]]
                    elif label_next_close:
                        c0, c1, b0, b1, end_k = C[i + 1, j], C[i + 1 + h, j], B[i + 1], B[i + 1 + h], i + 1 + h
                    if any(np.isnan(v) for v in (c0, c1, b0, b1)):
                        continue
                    ret = float(c1 / c0 - 1)
                    bench_ret = float(b1 / b0 - 1)
                    abn = ret - bench_ret
                    beta_abn = learning_targets.adjusted_return(ret, bench_ret, prediction_betas.get(r["ticker"], 1.0))
                    hit = None if abs(r["direction"]) < 0.1 else int((r["direction"] > 0) == (abn > 0))
                    batch.append((r["id"], h, idx[end_k].date().isoformat(), ret, bench_ret, abn, beta_abn, hit))
            con.executemany(
                "INSERT OR REPLACE INTO scores(prediction_id,horizon,scored_date,ret,bench_ret,abnormal,beta_abnormal,hit) "
                "VALUES (?,?,?,?,?,?,?,?)", batch)
        if i - start < warmup:
            continue
        if model is None or (i - start) % refit_every == 0:
            model = learner.fit(t, asof=t)
            if run_info.get("rank_order"):
                rank_model = learner.fit(t, asof=t, target_mode="rank", model_file=rank_model_file)
        conv, _ = learner.predict(signals, model)
        conv_prior, _ = learner.predict(signals, None)
        traded = conv_prior if run_info.get("prior_only") else conv   # learner ablation: trade on the equal-weight prior blend
        conv_rank = None
        if run_info.get("rank_order"):                                # round 37: the rank model orders, the return model sizes
            conv_rank, _ = learner.predict(signals, rank_model)
            traded = rank_order(conv, conv_rank)
            assert sorted(traded.values()) == sorted(conv.values()) and set(traded) == set(conv)
        if run_info.get("demean") and traded:                          # as cycle.convict: DEMEAN_CONVICTION (round 38), DEMEAN_GROUP (round 39)
            traded, _ = learner.demean(traded, groups, config.DEMEAN_GROUP_MIN)
        day_ic = (None, None)
        # IC of today's convictions against the 10-day outcome (evaluated later in the loop's own scores)
        y10 = {}
        for tk in conv:
            j = col[tk]
            c0, c1 = C[i, j], C[i + 10, j]
            b0, b1 = B[i], B[i + 10]
            if label_open:
                jp = pcol.get(tk)
                c0, b0 = (P[i + 1, jp] if jp is not None else np.nan), P[i + 1, pcol[config.BENCHMARK]]
            elif label_next_close:
                c0, c1, b0, b1 = C[i + 1, j], C[i + 11, j], B[i + 1], B[i + 11]
            if not any(np.isnan(v) for v in (c0, c1, b0, b1)):
                y10[tk] = float(c1 / c0 - 1) - float(b1 / b0 - 1)
        common = [tk for tk in y10 if tk in conv_prior]
        ic_rank_day = None
        if len(common) >= 10:
            ic_learned.append(learner.ic(np.array([conv[tk] for tk in common]), np.array([y10[tk] for tk in common])))
            ic_prior.append(learner.ic(np.array([conv_prior[tk] for tk in common]), np.array([y10[tk] for tk in common])))
            day_ic = (ic_learned[-1], ic_prior[-1])
            if conv_rank is not None:
                ic_rank_day = learner.ic(np.array([conv_rank[tk] for tk in common]), np.array([y10[tk] for tk in common]))
            order = sorted(common, key=lambda tk: conv[tk])       # signal monotonicity: 10-day abnormal return by conviction quintile
            for q in range(5):
                part = order[q * len(order) // 5:(q + 1) * len(order) // 5]
                if part:
                    quint[q].append(float(np.mean([y10[tk] for tk in part])))
        # portfolio: same sizing as live; next-day return from close t to close t+1 (close mode)
        # or from open t+1 to open t+2 (open mode, what the live cycle actually gets)
        if run_info.get("vol_target_mode") == "median" and len(curve) >= config.VOL_LOOKBACK_DAYS:   # round 43: expanding-median target
            vol_hist.append(float(np.std([c["ret"] for c in curve[-config.VOL_LOOKBACK_DAYS:]])) * math.sqrt(252))
            if len(vol_hist) >= 60:
                config.VOL_TARGET = float(np.median(vol_hist))
        realized = (float(np.std([c["ret"] for c in curve[-config.VOL_LOOKBACK_DAYS:]])) * math.sqrt(252)
                    if config.VOL_TARGET and len(curve) >= config.VOL_LOOKBACK_DAYS else None)
        long_short = run_info.get("long_short")
        if long_short:   # market-neutral book (round 33): gross GROSS_TARGET split so the legs' betas cancel, under the vol target
            scale = min(1.0, config.VOL_TARGET / realized) if (config.VOL_TARGET and realized and realized > config.VOL_TARGET) else 1.0
            w = long_short_weights(traded, prediction_betas, long_short, config.GROSS_TARGET * scale)
        else:
            targets = portfolio.targets(traded, config.CAPITAL, realized_vol=realized)   # dollars, same rules as live
            w = {tk: v / config.CAPITAL for tk, v in targets.items()}   # -> weights
        if config.HEDGE_SIZE and B[i] < float(np.nanmean(B[max(0, i - config.HEDGE_LOOKBACK): i + 1])):   # regime hedge, as live
            scale = min(1.0, config.VOL_TARGET / realized) if (config.VOL_TARGET and realized and realized > config.VOL_TARGET) else 1.0
            w["__HEDGE__"] = -min(config.HEDGE_SIZE * scale, sum(w.values()))   # capped at the long gross: a hedge, never a net short
        mix = run_info.get("sleeve_mix")
        if mix and not long_short:   # research (round 35): idle equity split equally across ETFs, each held while above its own average
            n_tr = config.IDLE_SLEEVE_TREND
            scale = min(1.0, config.VOL_TARGET / realized) if (config.VOL_TARGET and realized and realized > config.VOL_TARGET) else 1.0
            idle = max(0.0, scale - sum(v for tk, v in w.items() if not tk.startswith("__")))
            for etf in mix:
                s = C[:, col[etf]]
                if idle > 0 and (n_tr is None or (i >= n_tr and s[i] > float(np.nanmean(s[i - n_tr + 1: i + 1])))):
                    w[f"__SLEEVE_{etf}__"] = config.IDLE_SLEEVE_FRACTION * idle / len(mix)
        elif config.IDLE_SLEEVE and not long_short:                  # idle equity into an ETF while it trades above its average, as live
            s = C[:, col[config.IDLE_SLEEVE]]
            n_tr = config.IDLE_SLEEVE_TREND
            if n_tr is None or (i >= n_tr and s[i] > float(np.nanmean(s[i - n_tr + 1: i + 1]))):
                scale = min(1.0, config.VOL_TARGET / realized) if (config.VOL_TARGET and realized and realized > config.VOL_TARGET) else 1.0
                idle = max(0.0, scale - sum(v for tk, v in w.items() if not tk.startswith("__")))   # total capped at the vol target
                if idle > 0:
                    w["__SLEEVE__"] = config.IDLE_SLEEVE_FRACTION * idle
        floor = run_info.get("beta_floor")
        if floor and config.IDLE_SLEEVE and not long_short:            # round 42: trend-gated beta floor through the sleeve ETF
            s = C[:, col[config.IDLE_SLEEVE]]
            n_tr = config.IDLE_SLEEVE_TREND
            if n_tr is None or (i >= n_tr and s[i] > float(np.nanmean(s[i - n_tr + 1: i + 1]))):
                w = portfolio.beta_floor(w, prediction_betas, float(floor), config.GROSS_TARGET)
        for tk in w:                                                 # rebalance band, as portfolio.plan() does live: a held name is
            if tk in prev_w and abs(w[tk] - prev_w[tk]) < config.REBALANCE_BAND * abs(w[tk]):   # not resized for a move under 30% of target
                w[tk] = prev_w[tk]
        turnover = sum(abs(w.get(tk, 0) - prev_w.get(tk, 0)) for tk in set(w) | set(prev_w))
        def day_ret(tk):
            j = pcol[config.BENCHMARK if tk == "__HEDGE__" else config.IDLE_SLEEVE if tk == "__SLEEVE__"
                     else tk[9:-2] if tk.startswith("__SLEEVE_") else tk]
            c0, c1 = P[i + shift, j], P[i + 1 + shift, j]
            return None if (np.isnan(c0) or np.isnan(c1) or c0 <= 0) else float(c1 / c0) - 1
        ret = sum(w_i * r for tk, w_i in w.items() if (r := day_ret(tk)) is not None)
        leg_ret = {side: sum(w_i * r for tk, w_i in w.items() if (w_i > 0) == (side == "long") and w_i != 0
                             and not tk.startswith("__") and (r := day_ret(tk)) is not None) for side in ("long", "short")}
        ret -= abs(w.get("__HEDGE__", 0.0)) * 0.0002          # ~5%/yr borrow drag on the short side (as in sweep.py)
        ret -= sum(-x for tk, x in w.items() if x < 0 and not tk.startswith("__")) * 0.0002   # the same borrow drag on short stocks
        ret -= turnover * config.COST_BPS / 10_000
        ret -= max(0.0, sum(x for x in w.values() if x > 0) - 1.0) * run_info.get("margin_rate", 0.0) / 252   # round 42: margin interest
        equity *= 1 + ret
        turnover_total += turnover
        prev_w = w
        top = sorted(traded, key=lambda tk: -traded[tk])[:config.TOP_N]
        rank_rets = [r for tk in top if (r := day_ret(tk)) is not None]
        rank_ret = float(np.mean(rank_rets)) if rank_rets else 0.0
        equity_rank *= 1 + rank_ret - 0.1 * config.COST_BPS / 10_000    # ~10% daily turnover assumed
        curve.append({"date": t.isoformat(), "portfolio": equity, "rank": equity_rank, "gross": sum(abs(x) for x in w.values()),
                      "n": len([tk for tk in w if not tk.startswith("__")]), "hedge": round(-w.get("__HEDGE__", 0.0), 2),
                      "held": sorted(tk for tk in w if not tk.startswith("__")),
                      "ic_learned": day_ic[0], "ic_prior": day_ic[1], "ic_rank": ic_rank_day,
                      "level": ({h: round((v.get("intercept") or 0.0) * v["scale"], 6) for h, v in model["horizons"].items()}
                                if run_info.get("intercept") else None),   # the average name's expected beta-abnormal return
                      "net": round(sum(w.values()), 3), "short": round(sum(-x for x in w.values() if x < 0), 3),
                      "ret_long": leg_ret["long"], "ret_short": leg_ret["short"],
                      "sleeve": round(sum(v for tk, v in w.items() if tk.startswith("__SLEEVE")), 3),
                      "ret": ret, "turnover": turnover,
                      "soxx": float(px[config.BENCHMARK].iloc[i + 1 + shift] / px[config.BENCHMARK].iloc[base]),
                      "spy": float(px["SPY"].iloc[i + 1 + shift] / px["SPY"].iloc[base])})
        if (i - start) % 50 == 0:
            log.info("  %s equity %.3f soxx %.3f (%.0fs)", t, equity, curve[-1]["soxx"], time.time() - t0)
        if (i - start) % PROGRESS_EVERY == 0 or i == end - 1:
            done, total, elapsed = i - start + 1, end - start, time.time() - t0
            publish_progress(dict(run_info, status="running", pct=round(done / total, 4), day=done, total_days=total,
                                  date=t.isoformat(), elapsed_s=round(elapsed), eta_s=round(elapsed / done * (total - done)),
                                  equity=round(equity, 4), rank=round(equity_rank, 4), soxx=round(curve[-1]["soxx"], 4),
                                  spy=round(curve[-1]["spy"], 4), gross=round(sum(w.values()), 3), names=len(w),
                                  turnover_per_day=round(turnover_total / len(curve), 3),
                                  ic_10d={"learned": round(float(np.mean(ic_learned)), 4) if ic_learned else None,
                                          "equal_prior": round(float(np.mean(ic_prior)), 4) if ic_prior else None},
                                  quintiles_10d=[round(float(np.mean(q)), 4) if q else None for q in quint],
                                  model={h: {k: v.get(k) for k in ("n_obs", "cv_ic", "agent_ic", "w_conf")}
                                         for h, v in model["horizons"].items()},
                                  holdings=sorted((tk for tk in w if tk != "__HEDGE__"), key=lambda tk: -w[tk]),
                                  monthly=robustness.calendar(curve)["monthly"], curve=thin(curve)))

    ledger.DB = config.STATE_DIR / "ledger.sqlite"   # restore the live ledger path
    learner.MODEL_FILE = config.STATE_DIR / "model.json"
    learner.TARGET_CLIP_SIGMA = None
    learner.INTERCEPT, learner.DROP_DIR = None, ()
    config.AGENTS, config.TECHNICAL_RESIDUAL, config.GROSS_TARGET, config.VOL_TARGET = live_agents, live_residual, live_gross, live_vol

    rets = np.diff(np.log([1.0] + [c["portfolio"] for c in curve]))
    soxx = np.diff(np.log([1.0] + [c["soxx"] for c in curve]))
    dd = 1 - np.array([c["portfolio"] for c in curve]) / np.maximum.accumulate([c["portfolio"] for c in curve])
    n = len(curve)
    report = {
        "generated": date.today().isoformat(),
        "period": {"start": curve[0]["date"], "end": curve[-1]["date"], "trading_days": n},
        "execution": exec_mode,
        "open_refresh": bool(run_info.get("open_refresh")),
        "label_open": bool(run_info.get("label_open")),
        "label_next_close": bool(run_info.get("label_next_close")),
        "refresh_agents": run_info.get("refresh_agents"),
        "learn_preopen": bool(run_info.get("learn_preopen")),
        "prior_only": bool(run_info.get("prior_only")),
        "rank_order": bool(run_info.get("rank_order")), "target_clip_sigma": run_info.get("target_clip_sigma"),
        "intercept": run_info.get("intercept"), "drop_dir": run_info.get("drop_dir"), "demean": bool(run_info.get("demean")),
        "demean_group": run_info.get("demean_group"), "graph_transcripts_only": bool(run_info.get("graph_transcripts_only")),
        "technical_residual": bool(run_info.get("technical_residual")),
        "margin_rate": run_info.get("margin_rate"), "gross_target": run_info.get("gross_target"), "beta_floor": run_info.get("beta_floor"),
        "vol_target": run_info.get("vol_target"), "vol_target_mode": run_info.get("vol_target_mode"),
        "sizing": {"size": config.SIZE_PER_CONVICTION, "cap": config.MAX_POSITION_PCT, "gross": config.GROSS_TARGET,
                   "long_short": run_info.get("long_short"),
                   "min_book": config.MIN_STOCK_BOOK, "idle_sleeve": config.IDLE_SLEEVE,
                   "sleeve_fraction": config.IDLE_SLEEVE_FRACTION, "sleeve_trend": config.IDLE_SLEEVE_TREND,
                   "sleeve_mix": run_info.get("sleeve_mix")},
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
        "quintiles_10d": [round(float(np.mean(q)), 4) if q else None for q in quint],   # Q1 (lowest conviction) .. Q5: mean 10d abnormal return
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
                          ic_10d=report["ic_10d"], quintiles_10d=report["quintiles_10d"], model=report["model_final"], holdings=[],
                          monthly=report["robustness"]["calendar"]["monthly"], curve=thin(curve),
                          portfolio=report["portfolio"], rank_portfolio=report["rank_portfolio"],
                          robustness={k: v for k, v in report["robustness"].items() if k != "calendar"},
                          quarterly=report["robustness"]["calendar"]["quarterly"], caveats=report["caveats"]))
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=250)
    p.add_argument("--refit-every", type=int, default=1, help="1 = refit the learner every day like the live cycle (weekly refits made results depend on the refit phase)")
    p.add_argument("--tag", default="", help="output suffix, e.g. _500")
    p.add_argument("--extra", default="", help="comma list of optional agents to include: momentum,sue,ml_ranker")
    p.add_argument("--cap", type=float, default=None, help="override MAX_MARKET_CAP (e.g. 1e13 for no cap)")
    p.add_argument("--exec", dest="exec_mode", choices=("close", "open"), default="close",
                   help="close = trade at the signal day's close (optimistic); open = trade at the next open like the live cycle")
    p.add_argument("--no-publish", action="store_true", help="do not upload progress (equivalence tests, scratch runs)")
    p.add_argument("--agents", default=None, help="comma list restricting the replayed roster, e.g. technical,mean_reversion,risk,macro,events (pre-2024 windows have no graph signals)")
    p.add_argument("--end", default=None, help="ISO date: the window ends here instead of today (historical stress tests)")
    p.add_argument("--horizons", default=None, help="comma list overriding config.HORIZONS for this run, e.g. 10,20,40 (the ledger then carries all of them)")
    p.add_argument("--open-refresh", action="store_true", help="price agents see the next day's open appended before trading at that open, like the live open refresh (needs --exec open)")
    p.add_argument("--label-open", action="store_true", help="learning labels start at the order day's open (the fill price) instead of the signal day's close; with --open-refresh that is also the open the refreshed signals saw (needs --exec open)")
    p.add_argument("--label-next-close", action="store_true", help="learning labels start at the close of the order day t+1, as the live scorer does (score.py)")
    p.add_argument("--refresh-agents", default=None, help="with --open-refresh: comma list of the agents that see the open row (default: config.OPEN_REFRESH_AGENTS, as live), e.g. technical,risk,macro,fundamentals,events")
    p.add_argument("--learn-preopen", action="store_true", help="with --open-refresh: trade on the refreshed signals but record and learn from the signals computed before the open (hybrid)")
    p.add_argument("--rank-order", action="store_true", help="round 37: fit a second ridge on per-date normal scores of the target and trade the return model's conviction values in that model's order (sizing unchanged by construction)")
    p.add_argument("--target-clip-sigma", type=float, default=None, help="round 37 control: clip the return target at +/- k sigma per horizon instead of the +/-15%% winsor")
    p.add_argument("--intercept", choices=("in", "fit_only"), default=None, help="round 38: fit an unpenalised intercept; in = added to convictions, fit_only = recorded only")
    p.add_argument("--drop-dir", default="", help="round 38: comma list of agents whose direction-only feature is dropped at fit time, e.g. supply_chain,neighbors")
    p.add_argument("--demean", action=argparse.BooleanOptionalAction, default=None,
                   help="subtract the day's cross-sectional mean conviction before sizing; default follows config.DEMEAN_CONVICTION (True since 2026-09-16, round 38); --no-demean = the raw control")
    p.add_argument("--demean-group", choices=("chain", "none"), default=None,
                   help="round 39: demean within graph groups (chain = power-only names vs the rest); none = off; default follows config.DEMEAN_GROUP")
    p.add_argument("--graph-transcripts-only", action=argparse.BooleanOptionalAction, default=None,
                   help="round 39: the graph agents skip SEC-filing rows; default follows config.GRAPH_TRANSCRIPTS_ONLY")
    p.add_argument("--technical-residual", action=argparse.BooleanOptionalAction, default=None,
                   help="round 40: technical's relative returns are beta-adjusted residuals; default follows config.TECHNICAL_RESIDUAL")
    p.add_argument("--margin-rate", type=float, default=0.0, help="round 42: annual interest charged on long gross above 1.0, e.g. 0.07")
    p.add_argument("--gross-target", type=float, default=None, help="round 42: override GROSS_TARGET for the run, e.g. 2.0")
    p.add_argument("--beta-floor", type=float, default=None,
                   help="round 42: while the sleeve ETF is above its trend average, raise the book's beta to this floor with the ETF")
    p.add_argument("--vol-target", type=float, default=None, help="round 43: override VOL_TARGET for the run; 0 = brake off")
    p.add_argument("--vol-target-mode", choices=("fixed", "median"), default=None,
                   help="round 43: median = the target is the expanding median of the book's own 20-day realised vol (after 60 observations)")
    p.add_argument("--prior-only", action="store_true", help="trade on the equal-weight prior blend instead of the fitted weights (learner ablation); the learner is still fit daily and both ICs are recorded per day")
    p.add_argument("--long-short", type=int, default=None, help="market-neutral book (round 33): long the top N and short the bottom N convictions, gross GROSS_TARGET under the vol target split so the legs' betas cancel, 2 bps/day borrow, no sleeve")
    p.add_argument("--position-cap", type=float, default=None, help="override MAX_POSITION_PCT, e.g. 0.30")
    p.add_argument("--min-book", type=float, default=None, help="override MIN_STOCK_BOOK, e.g. 0.5")
    p.add_argument("--idle-sleeve", default=None, help="ETF for idle equity, SOXX or SPY (sets IDLE_SLEEVE)")
    p.add_argument("--sleeve-mix", default=None, help="research: comma list of ETFs from the replay's price set (e.g. SOXX,SPY) that split the idle equity equally, each held while above its own --sleeve-trend average; give --idle-sleeve too for the fraction and trend")
    p.add_argument("--sleeve-fraction", type=float, default=1.0, help="share of the idle equity put in the sleeve")
    p.add_argument("--sleeve-trend", type=int, default=50, help="only while the ETF closed above this many days' average; 0 = always")
    p.add_argument("--graph-asof", default=None, help="ISO date: build the supply-chain map from the newest graph snapshot dated <= this (state/graph_snapshots) instead of today's graph")
    args = p.parse_args()
    PUBLISH = not args.no_publish
    if args.position_cap is not None:
        config.MAX_POSITION_PCT = args.position_cap
    if args.min_book is not None:
        config.MIN_STOCK_BOOK = args.min_book
    if args.idle_sleeve:
        config.IDLE_SLEEVE = args.idle_sleeve
        config.IDLE_SLEEVE_FRACTION = args.sleeve_fraction
        config.IDLE_SLEEVE_TREND = args.sleeve_trend or None
    if args.horizons:
        config.HORIZONS = tuple(int(x) for x in args.horizons.split(","))
    if args.graph_asof:
        snap = snapshots.dir_for(args.graph_asof)
        if snap is None:
            raise SystemExit(f"no graph snapshot dated <= {args.graph_asof} under {snapshots.ROOT}")
        config.EARNINGS_AI_DIR = snap
        print("graph snapshot:", snap)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    r = run(days=args.days, refit_every=args.refit_every, tag=args.tag, extra=tuple(x for x in args.extra.split(",") if x), cap=args.cap,
            exec_mode=args.exec_mode, agents=tuple(x for x in args.agents.split(",") if x) if args.agents else None, end=args.end,
            open_refresh=args.open_refresh, label_open=args.label_open, label_next_close=args.label_next_close,
            refresh_agents=tuple(x for x in args.refresh_agents.split(",") if x) if args.refresh_agents is not None else None,
            learn_preopen=args.learn_preopen, prior_only=args.prior_only, long_short=args.long_short,
            sleeve_mix=tuple(x for x in args.sleeve_mix.split(",") if x) if args.sleeve_mix else None,
            rank_order_mode=args.rank_order, target_clip_sigma=args.target_clip_sigma,
            intercept=args.intercept, drop_dir=tuple(x for x in args.drop_dir.split(",") if x), demean=args.demean,
            demean_group=None if args.demean_group is None else ("" if args.demean_group == "none" else args.demean_group),
            graph_transcripts_only=args.graph_transcripts_only, technical_residual=args.technical_residual,
            margin_rate=args.margin_rate, gross_target=args.gross_target, beta_floor=args.beta_floor,
            vol_target=args.vol_target, vol_target_mode=args.vol_target_mode)
    print(json.dumps({k: v for k, v in r.items() if k != "curve"}, indent=2)[:4000])
