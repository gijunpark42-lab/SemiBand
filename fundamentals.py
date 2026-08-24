"""Quarterly fundamentals from Yahoo Finance, cached to fundamentals.json.

yfinance is an unofficial scraper -- it breaks, rate-limits, and throttles.
The cache is the defense: fundamentals only move once a quarter, so each
ticker is refetched at most every MAX_AGE_DAYS, and a failed fetch keeps the
old entry instead of erasing it. The bot should only ever call load() and the
ps()/ttm_revenue() helpers (all local, no network); refreshing is a manual or
scheduled job:

    python fundamentals.py            refresh stale entries (>MAX_AGE_DAYS old)
    python fundamentals.py --force    refresh everything

Per ticker the cache holds:
    revenue   {quarter_end: total revenue}   ~5-6 quarters, what Yahoo gives
    shares    {date: shares outstanding}     month-end samples, so historical
                                             P/S sees dilution/buybacks
    currency  reporting currency of revenue  ADRs report in home currency
                                             (TSM=TWD, ASML=EUR) while the
                                             price is USD, so their absolute
                                             P/S is off by the FX rate --
                                             fine for a same-stock band,
                                             wrong for cross-stock compares
"""
import argparse
import json
import logging
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

import config

log = logging.getLogger("fundamentals")

CACHE = Path(__file__).with_name("fundamentals.json")
MAX_AGE_DAYS = 7          # weekly refresh catches each name's new quarter
REPORT_LAG_DAYS = 45      # a quarter's revenue is unknown until reported;
                          # ttm_revenue() hides quarters younger than this so
                          # historical P/S (for the band) can't see the future
ETFS = {"SMH", "SOXX", "SOXL"}  # no revenue, nothing to fetch


def universe():
    """Everything the strategy needs P/S for: watchlist + all sector peers."""
    tickers = set(config.WATCHLIST)
    for group in config.SECTORS.values():
        tickers.update(group)
    return sorted(tickers - ETFS)


def _fetch(symbol):
    ticker = yf.Ticker(symbol)

    income = ticker.quarterly_income_stmt
    if income is None or income.empty or "Total Revenue" not in income.index:
        raise ValueError("no quarterly revenue on Yahoo")
    revenue = {
        ts.date().isoformat(): float(value)
        for ts, value in income.loc["Total Revenue"].items()
        if pd.notna(value)
    }

    series = ticker.get_shares_full(start=datetime.now() - timedelta(days=750))
    if series is not None and len(series):
        monthly = series.resample("ME").last().dropna()
        shares = {ts.date().isoformat(): int(v) for ts, v in monthly.items()}
    else:  # fallback: current count only (fine for young listings)
        current = ticker.fast_info.get("shares")
        if not current:
            raise ValueError("no shares outstanding on Yahoo")
        shares = {date.today().isoformat(): int(current)}

    try:
        currency = ticker.info.get("financialCurrency")
    except Exception:
        currency = None

    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "currency": currency,
        "revenue": revenue,
        "shares": shares,
    }


def _stale(entry):
    fetched = datetime.fromisoformat(entry["fetched_at"])
    return datetime.now(timezone.utc) - fetched > timedelta(days=MAX_AGE_DAYS)


def refresh(force=False):
    """Refetch stale/missing tickers, keep old data on failure, rewrite cache."""
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    todo = [t for t in universe() if force or t not in cache or _stale(cache[t])]
    log.info("refreshing %d of %d tickers", len(todo), len(universe()))

    for i, symbol in enumerate(todo):
        try:
            cache[symbol] = _fetch(symbol)
        except Exception as exc:
            log.warning("%s: fetch failed, keeping cached entry (%s)", symbol, exc)
        if i < len(todo) - 1:
            time.sleep(1)  # stay under Yahoo's rate limit

    CACHE.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    return cache


def load():
    """Cached fundamentals, fetching on first use. No network after that."""
    if not CACHE.exists():
        return refresh()
    return json.loads(CACHE.read_text(encoding="utf-8"))


# --- P/S helpers (pure lookups on a cache entry, safe to call per bar) ---

def ttm_revenue(entry, asof=None):
    """Trailing-4-quarter revenue known on `asof` (ISO date, default today).

    A quarter only counts once REPORT_LAG_DAYS have passed since quarter end.
    Returns None with fewer than 4 known quarters (young listing -> the
    caller falls back to the sector z-score path).
    """
    asof = date.fromisoformat(asof) if asof else date.today()
    cutoff = (asof - timedelta(days=REPORT_LAG_DAYS)).isoformat()
    known = sorted(q for q in entry["revenue"] if q <= cutoff)
    if len(known) < 4:
        return None
    return sum(entry["revenue"][q] for q in known[-4:])


def shares_on(entry, asof=None):
    """Shares outstanding on `asof`: latest sample on/before it, else earliest."""
    dates = sorted(entry["shares"])
    asof = asof or date.today().isoformat()
    past = [d for d in dates if d <= asof]
    return entry["shares"][past[-1] if past else dates[0]]


def ps(entry, price, asof=None):
    """Price-to-sales at `price` as of `asof`, or None if revenue is unknown."""
    revenue = ttm_revenue(entry, asof)
    if not revenue or revenue <= 0:
        return None
    return price * shares_on(entry, asof) / revenue


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="refetch everything")
    args = parser.parse_args()

    cache = refresh(force=args.force)
    with_ttm = sum(1 for e in cache.values() if ttm_revenue(e))
    print(f"{len(cache)} tickers cached, {with_ttm} with a full TTM -> {CACHE.name}")
