"""Volatility breakout on daily (UTC) bars.

    target = open_today + K x (high_yesterday - low_yesterday)

decide() is called once per symbol per poll. Return "BUY", "SELL", or None.

    bars       DataFrame of daily bars, oldest -> newest, INCLUDING today's
               partial bar (Alpaca sends it; its open is what we need).
    price      live ask right now
    position   open Alpaca Position, or None if flat
    entry_day  ISO date (UTC) of this symbol's last entry, or None

Exit is time-based, not price-based: whatever was bought yesterday is sold at
the first poll after 00:00 UTC. There is no stop-loss by design (the original
system exits at the next open); DRY_RUN and the exposure cap are the guard.
"""
from datetime import datetime, timezone

import crypto_config as config


def today_utc():
    return datetime.now(timezone.utc).date().isoformat()


def target(bars):
    """Breakout level for today, or None if the bars don't cover it."""
    if len(bars) < 2:
        return None
    today, yesterday = bars.iloc[-1], bars.iloc[-2]
    if bars.index[-1].date().isoformat() != today_utc():
        return None  # today's bar hasn't arrived yet
    return float(today["open"]) + config.K * float(yesterday["high"] - yesterday["low"])


def decide(symbol, bars, price, position, entry_day):
    if position is not None:
        return "SELL" if entry_day != today_utc() else None
    if entry_day == today_utc():
        return None  # one entry per symbol per day (also keeps DRY_RUN from re-buying every poll)
    level = target(bars)
    if level is not None and price >= level:
        return "BUY"
    return None
