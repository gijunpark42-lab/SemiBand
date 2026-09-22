"""Insider agent (shadow candidate, 2026-09-17): open-market insider purchases (Form 4 code P) filed in the last 60 days.

Point-in-time by FILING date, the day the market could know. Derivative transactions are ignored, and so are routine
buyers (Cohen, Malloy & Pomorski 2012): an insider who also bought in the same calendar month of an earlier year is on a
schedule, not informed. Silent when nothing qualifies, so most names carry no signal on most days.

Data: state/insider/<TICKER>.json in Finnhub's insider-transactions format. Live runs refresh the files once a day when
FINNHUB_API_KEY is set (free tier, 60 calls a minute); a replay reads whatever is on disk and never calls the network.
"""
import functools
import json
import logging
import math
import os
import time
from datetime import date, timedelta

import requests

import config
from agents.base import Signal, clip

NAME = "insider"
WINDOW_DAYS = 60                  # a filing counts for this many calendar days
FETCH_BUDGET_S = int(os.getenv("INSIDER_FETCH_BUDGET_S", "300"))   # the refresh never holds a cycle longer than this; the nightly
                                                                    # task (SemiBand-Insider, 01:35 PT) runs it with a long budget
MAX_429 = 3                       # consecutive throttles that end the refresh (the rest keep yesterday's files)
MIN_USD = 10_000                  # smaller purchases are ignored
HISTORY_FROM = "2024-01-01"
log = logging.getLogger("insider")


def _dir():
    return config.STATE_DIR / "insider"


@functools.lru_cache(maxsize=1)
def _purchases():
    """{ticker: [(filing_date, insider, usd, transaction_date)]}: non-derivative code-P rows worth >= MIN_USD, oldest filing first."""
    out = {}
    folder = _dir()
    if not folder.exists():
        return out
    for f in folder.glob("*.json"):
        try:
            payload = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        data = payload.get("data") if isinstance(payload, dict) else payload
        rows = data.get("data") if isinstance(data, dict) else data
        buys = []
        for t in rows or []:
            if t.get("transactionCode") != "P" or t.get("isDerivative"):
                continue
            try:
                filed = date.fromisoformat(t["filingDate"])
                traded = date.fromisoformat(t.get("transactionDate") or t["filingDate"])
            except (KeyError, TypeError, ValueError):
                continue
            usd = abs(float(t.get("change") or 0)) * float(t.get("transactionPrice") or 0)
            if usd >= MIN_USD:
                buys.append((filed, (t.get("name") or "").strip().lower(), usd, traded))
        if buys:
            out[f.stem.upper()] = sorted(buys)
    return out


def _routine(insider, traded, earlier):
    """The same insider bought in the same calendar month of an earlier year (among purchases filed before this one)."""
    return any(name == insider and tr.month == traded.month and tr.year < traded.year for _, name, _, tr in earlier)


def refresh(universe, today=None):
    """Once a day: fetch every universe name's insider transactions from Finnhub into state/insider/. No key, no fetch."""
    key = os.getenv("FINNHUB_API_KEY")
    today = today or date.today()
    folder = _dir()
    marker = folder / f"_fetched_{today.isoformat()}"
    if not key or marker.exists():
        return 0
    folder.mkdir(parents=True, exist_ok=True)
    done, throttled, t0 = 0, 0, time.time()
    for sym in universe:
        if time.time() - t0 > FETCH_BUDGET_S or throttled >= MAX_429:
            log.warning("insider refresh stopped after %d names (%.0fs, %d throttles): the rest keep their last file", done, time.time() - t0, throttled)
            break
        try:
            r = requests.get("https://finnhub.io/api/v1/stock/insider-transactions", timeout=20,
                             params={"symbol": sym, "from": HISTORY_FROM, "to": today.isoformat(), "token": key})
            if r.status_code == 429:
                throttled += 1
                time.sleep(20)
                continue
            throttled = 0
            r.raise_for_status()
            (folder / f"{sym}.json").write_text(json.dumps({"fetched": today.isoformat(), "data": r.json()}), encoding="utf-8")
            done += 1
            time.sleep(1.1)                                   # under 60 calls a minute
        except (requests.RequestException, ValueError) as exc:
            log.warning("insider %s: %s", sym, str(exc)[:80])  # keep yesterday's file
    for old in folder.glob("_fetched_*"):
        old.unlink(missing_ok=True)
    marker.write_text(str(done), encoding="utf-8")
    _purchases.cache_clear()
    return done


def run(universe: dict, ctx: dict) -> list[Signal]:
    today = ctx.get("asof")
    if today is None:                                          # live: the cycle's date, refreshed once a day
        today = date.fromisoformat(ctx["today"]) if ctx.get("today") else date.today()
        if config.INSIDER_REFRESH_IN_CYCLE:                      # 2026-09-22: off; the nightly task keeps the files current
            refresh(universe, today)
    elif isinstance(today, str):
        today = date.fromisoformat(today)
    data = _purchases()
    out = []
    for ticker in universe:
        rows = data.get(ticker)
        if not rows:
            continue
        known = [r for r in rows if r[0] < today]              # point-in-time: filed before today (a filing lands after the pre-open signal)
        recent = [r for r in known if r[0] >= today - timedelta(days=WINDOW_DAYS)]
        buys = [r for r in recent if not _routine(r[1], r[3], [h for h in known if h[0] < r[0]])]
        if not buys:
            continue
        buyers = len({r[1] for r in buys})
        usd = sum(r[2] for r in buys)
        direction = max(math.tanh(0.4 * buyers + 0.2 * math.log10(max(usd, 1e4) / 1e5)), 0.05)
        confidence = clip(0.3 + 0.1 * buyers, 0.3, 0.7)
        newest = max(r[0] for r in buys)
        out.append(Signal(NAME, ticker, direction, confidence, 20,
                          f"{buyers} insider(s) bought ${usd:,.0f} on the open market; newest filing {(today - newest).days}d ago").clipped())
    return out


if __name__ == "__main__":                                 # nightly refresh outside the cycle: python -X utf8 -m agents.insider
    import sys
    import universe as universe_mod
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    names = universe_mod.load()
    n = refresh(names)
    log.info("insider refresh: %d of %d names fetched (budget %ds)", n, len(names), FETCH_BUDGET_S)
    sys.exit(0)
