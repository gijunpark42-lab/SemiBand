"""SUE agent — post-earnings-announcement drift over a 60-day window.

Standardised Unexpected Earnings: the latest EPS surprise divided by the
standard deviation of the previous surprises (Bernard-Thomas; Hou-Xue-Zhang
find it robust at short horizons). Stocks with a big positive SUE keep
drifting up for weeks after the print, and vice versa. `events` only covers
the 14 days around a print; this agent carries the drift out to 60 days,
fading linearly. Free (yfinance earnings history), point-in-time safe.
"""
import math
from datetime import date

import numpy as np

import market
from agents.base import Signal, clip

NAME = "sue"
DRIFT_DAYS = 60
MIN_HISTORY = 4


def run(universe: dict, ctx: dict) -> list[Signal]:
    asof = ctx.get("asof") or date.today()
    data = ctx.get("earnings") or market.earnings(list(universe), limit=12)
    out = []
    for ticker in universe:
        rows = [r for r in (data.get(ticker) or []) if r["date"] < asof.isoformat() and r.get("surprise_pct") is not None]
        if len(rows) < MIN_HISTORY + 1:
            continue
        last, hist = rows[0], rows[1:1 + 8]
        days = (asof - date.fromisoformat(last["date"])).days
        if days > DRIFT_DAYS or days < 1:
            continue
        sd = float(np.std([r["surprise_pct"] for r in hist])) or 5.0
        sue = float(last["surprise_pct"]) / max(sd, 2.0)
        fade = 1.0 - days / DRIFT_DAYS
        direction = math.tanh(sue / 2.0) * fade
        confidence = clip(0.3 + 0.05 * min(len(hist), 8), 0.3, 0.7) * (0.6 + 0.4 * fade)
        out.append(Signal(NAME, ticker, direction, confidence, 20,
                          f"SUE {sue:+.1f} (surprise {last['surprise_pct']:+.0f}%, sd {sd:.0f}), {days}d after the print").clipped())
    return out
