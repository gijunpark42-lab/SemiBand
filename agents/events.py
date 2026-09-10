"""Events agent — earnings calendar.

Two situations, otherwise silent:
  * earnings within the next 7 calendar days  -> event risk, lean negative
  * reported within the last 14 days           -> post-earnings drift in the
    direction of the surprise, stronger when the price reaction agrees
Free (yfinance earnings dates, cached per day).
"""
import math
from datetime import date

import pandas as pd

import config
import market
from agents.base import Signal, clip

NAME = "events"
PRE_DAYS = 7
POST_DAYS = 14


def run(universe: dict, ctx: dict) -> list[Signal]:
    closes: pd.DataFrame = ctx["closes"]
    bench = closes[config.BENCHMARK]
    data = market.earnings(list(universe))
    today = date.today()
    out = []
    for ticker in universe:
        rows = data.get(ticker) or []
        if not rows:
            continue
        future = [r for r in rows if r["date"] >= today.isoformat()]
        past = [r for r in rows if r["date"] < today.isoformat()]
        if future:
            nxt = min(future, key=lambda r: r["date"])
            days = (date.fromisoformat(nxt["date"]) - today).days
            if 0 <= days <= PRE_DAYS:
                out.append(Signal(NAME, ticker, -0.25, 0.5, 5,
                                  f"earnings in {days} days: event risk, no edge").clipped())
                continue
        if past:
            last = past[0]
            days = (today - date.fromisoformat(last["date"])).days
            surprise = last.get("surprise_pct")
            if days <= POST_DAYS and surprise is not None:
                direction = math.tanh(surprise / 30)
                rel = None
                if ticker in closes.columns:
                    pos = closes.index.searchsorted(pd.Timestamp(last["date"]))
                    if 0 < pos < len(closes.index):
                        c0, c1 = closes[ticker].iloc[pos - 1], closes[ticker].iloc[-1]
                        b0, b1 = bench.iloc[pos - 1], bench.iloc[-1]
                        if not any(pd.isna(v) for v in (c0, c1, b0, b1)):
                            rel = float(c1 / c0 - 1) - float(b1 / b0 - 1)
                agrees = rel is not None and (rel > 0) == (surprise > 0)
                confidence = 0.6 if agrees else 0.35
                why = f"reported {days}d ago, EPS surprise {surprise:+.0f}%"
                if rel is not None:
                    why += f", since then {rel*100:+.1f}% vs {config.BENCHMARK}" + (" (confirms)" if agrees else " (diverges)")
                out.append(Signal(NAME, ticker, clip(direction, -1, 1), confidence, 10, why).clipped())
    return out
