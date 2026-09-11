"""Point-in-time partial backtest of the `llm_guidance` agent (research model, cheap effort).

The three Claude agents cannot normally be backtested (no historical headlines / reports). `llm_guidance` is
the exception: its input is the company's own dated call/filing statements in the earnings-ai graph, so an
opinion "as of" a past date can be reproduced from the statements dated on or before that date.

For every universe name and every statement date d since START, Claude (config.LLM_MODEL_RESEARCH, low effort,
never the live model) is asked the live agent's question using only statements dated <= d and the 20-day price
move as of d. That opinion is held on every trading day from d until the next statement date, written into a
COPY of a finished rule-agent ledger as agent `llm_guidance`, and scored exactly like the rule agents. Then
`sweep.py --round15 --tag _llmg` compares the roster with and without it on both windows.

    python llm_backtest.py --ledger _u150b            # -> state/backtest_llmg.sqlite (+ state/llm_guidance_pit.json cache)
    python sweep.py --round15 --tag _llmg --exec open --oos-end 2025-09-24 --workers 4

Caveats: the curated metrics block the live agent also sees is not point-in-time and is left out; the model is
Sonnet at low effort, not the live Opus; structure of the graph is today's (only the statements are dated).
"""
import argparse
import json
import logging
import shutil
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import numpy as np
import pandas as pd

import config
import market
import universe as universe_mod
from agents import llm
from agents.llm_guidance import MAX_AGE_DAYS, MAX_SIGNALS, SYSTEM, _label_date
from agents.supply_chain import _load

log = logging.getLogger("llm_backtest")
START = date(2024, 6, 1)
CACHE = config.STATE_DIR / "llm_guidance_pit.json"


def statements(node):
    rows, seen = [], set()
    for q in node.get("quarterly_data") or []:
        d = _label_date(q.get("quarter"))
        key = (q.get("quarter"), (q.get("signal") or "")[:80])
        if d and key not in seen:
            seen.add(key)
            rows.append((d, q))
    rows.sort(key=lambda r: r[0])
    return rows


def ask(ticker, company, rows_asof, price_line):
    lines = []
    for d, q in rows_asof:
        fig = q.get("figure")
        lines.append(f"- [{q.get('quarter')}] {(q.get('signal') or '')[:500]}"
                     + (f" — figure: {str(fig)[:150]}" if fig and "no specific" not in str(fig) else ""))
    user = (f"Ticker: {ticker} ({company})\n{price_line}\n\n"
            f"Company's own recent call/filing statements, newest first:\n" + "\n".join(lines)
            + "\n\nTrading is commission-free but each order costs about 5 bps in slippage, and there is no obligation to trade: "
              "a direction near 0 with low confidence is a valid answer. Give your opinion as JSON.")
    return llm.ask_json(SYSTEM, user, model=config.LLM_MODEL_RESEARCH)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", default="_u150b", help="tag of the finished rule-agent ledger to copy and extend")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--max-calls", type=int, default=0, help="stop after this many new Claude calls (0 = all)")
    ap.add_argument("--count-only", action="store_true", help="list how many questions would be asked and exit")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    src = config.STATE_DIR / f"backtest{args.ledger}.sqlite"
    dst = config.STATE_DIR / "backtest_llmg.sqlite"
    universe = universe_mod.load()
    graph, _, _ = _load()
    by_id = {n["id"]: n for n in graph["nodes"]}
    tickers = list(universe)
    closes = market.closes(tickers + [config.BENCHMARK], lookback_days=800, cache=False)
    closes = closes[closes[config.BENCHMARK].notna()]
    idx = closes.index
    C = closes.to_numpy(dtype=float)
    col = {tk: j for j, tk in enumerate(closes.columns)}
    B = C[:, col[config.BENCHMARK]]

    con = sqlite3.connect(src)
    ledger_dates = sorted(r[0] for r in con.execute("SELECT DISTINCT date FROM predictions"))
    con.close()
    first, last = date.fromisoformat(ledger_dates[0]), date.fromisoformat(ledger_dates[-1])

    # --- the questions: (ticker, statement date) pairs, opinions cached across runs ---
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    jobs = []
    for tk in tickers:
        node = by_id.get(universe[tk])
        if not node:
            continue
        rows = statements(node)
        dates = sorted({d for d, _ in rows if d >= START and d <= last + timedelta(days=1)})
        for d in dates:
            key = f"{tk}|{d.isoformat()}"
            if key in cache:
                continue
            asof_rows = [(dd, q) for dd, q in rows if dd <= d]
            asof_rows.sort(key=lambda r: r[0], reverse=True)
            asof_rows = asof_rows[:MAX_SIGNALS]
            if not asof_rows or (d - asof_rows[0][0]).days > MAX_AGE_DAYS:
                continue
            pos = int(idx.searchsorted(pd.Timestamp(d), side="right")) - 1
            if tk in col and pos >= 21 and not np.isnan(C[pos, col[tk]]) and not np.isnan(C[pos - 21, col[tk]]):
                rel = (C[pos, col[tk]] / C[pos - 21, col[tk]] - 1) - (B[pos] / B[pos - 21] - 1)
                price_line = f"Recent price move: {rel * 100:+.1f}% vs {config.BENCHMARK} over the last 20 trading days"
            else:
                price_line = "Recent price move: unavailable"
            jobs.append((key, tk, universe[tk], asof_rows, price_line))
    if args.max_calls:
        jobs = jobs[:args.max_calls]
    log.info("%d cached opinions, %d new questions, model %s", len(cache), len(jobs), config.LLM_MODEL_RESEARCH)
    if args.count_only:
        return
    if jobs and not llm.ensure_server():
        raise SystemExit("local Claude server not available")

    def work(job):
        key, tk, company, rows_asof, price_line = job
        try:
            o = ask(tk, company, rows_asof, price_line)
            return key, {"direction": float(o["direction"]), "confidence": float(o["confidence"]),
                         "horizon": int(o["horizon_days"]), "reason": str(o["reason"])[:200]}
        except Exception as exc:
            log.warning("%s: %s", key, exc)
            return key, None

    t0, done = time.time(), 0
    with ThreadPoolExecutor(args.workers) as ex:
        for key, o in ex.map(work, jobs):
            done += 1
            if o:
                cache[key] = o
            if done % 25 == 0 or done == len(jobs):
                CACHE.write_text(json.dumps(cache, indent=0), encoding="utf-8")
                log.info("  %d/%d opinions (%.0fs)", done, len(jobs), time.time() - t0)
    CACHE.write_text(json.dumps(cache, indent=0), encoding="utf-8")

    # --- write the held opinions into a copy of the ledger, scored like the rule agents ---
    shutil.copy2(src, dst)
    con = sqlite3.connect(dst)
    con.execute("DELETE FROM scores WHERE prediction_id IN (SELECT id FROM predictions WHERE agent = 'llm_guidance')")
    con.execute("DELETE FROM predictions WHERE agent = 'llm_guidance'")
    ledger_set = set(ledger_dates)
    n_rows = 0
    for tk in tickers:
        keys = sorted((k for k in cache if k.startswith(tk + "|")), key=lambda k: k.split("|")[1])
        for i_k, k in enumerate(keys):
            o = cache[k]
            d0 = date.fromisoformat(k.split("|")[1])
            d1 = date.fromisoformat(keys[i_k + 1].split("|")[1]) if i_k + 1 < len(keys) else last + timedelta(days=1)
            d1 = min(d1, d0 + timedelta(days=MAX_AGE_DAYS))
            for ts in idx[(idx >= pd.Timestamp(d0)) & (idx < pd.Timestamp(d1))]:
                t = ts.date().isoformat()
                if t not in ledger_set or tk not in col:
                    continue
                i = int(idx.get_loc(ts))
                if np.isnan(C[i, col[tk]]):
                    continue
                cur = con.execute("INSERT INTO predictions(date, agent, ticker, direction, confidence, horizon, reason, price_at) VALUES (?,?,?,?,?,?,?,?)",
                                  (t, "llm_guidance", tk, o["direction"], o["confidence"], o["horizon"], o["reason"], float(C[i, col[tk]])))
                pid = cur.lastrowid
                for h in config.HORIZONS:
                    if i + h >= len(idx):
                        continue
                    c0, c1, b0, b1 = C[i, col[tk]], C[i + h, col[tk]], B[i], B[i + h]
                    if any(np.isnan(v) for v in (c0, c1, b0, b1)):
                        continue
                    abn = float(c1 / c0 - 1) - float(b1 / b0 - 1)
                    hit = None if abs(o["direction"]) < 0.1 else int((o["direction"] > 0) == (abn > 0))
                    con.execute("INSERT OR REPLACE INTO scores VALUES (?,?,?,?,?,?,?)",
                                (pid, h, idx[i + h].date().isoformat(), float(c1 / c0 - 1), float(b1 / b0 - 1), abn, hit))
                n_rows += 1
    con.commit()
    con.close()
    log.info("wrote %d llm_guidance prediction rows into %s (%s -> %s)", n_rows, dst.name, first, last)


if __name__ == "__main__":
    main()
