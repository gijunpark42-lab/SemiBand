"""Donchian breakout with ATR stop / take-profit / time stop, on 15m bars.

Pure functions; scalp_run.py owns the websocket, the clock, and the state.

    levels(bars)   -> {"high": donchian high, "atr": ATR} from COMPLETED bars
    entry(...)     -> True when the ask breaks the Donchian high
    exit_reason(...) -> "stop" | "take" | "timeout" | None for an open trade
"""
from datetime import timedelta

import scalp_config as config


def levels(bars):
    """bars: DataFrame of 15m bars oldest -> newest, current partial bar already
    dropped. None if there is not enough history."""
    need = max(config.DONCHIAN, config.ATR_PERIOD + 1)
    if len(bars) < need:
        return None
    recent = bars.iloc[-config.DONCHIAN:]
    high = float(recent["high"].max())

    tail = bars.iloc[-(config.ATR_PERIOD + 1):]
    prev_close = tail["close"].shift(1)
    true_range = (tail["high"] - tail["low"]).combine(
        (tail["high"] - prev_close).abs(), max
    ).combine((tail["low"] - prev_close).abs(), max)
    atr = float(true_range.iloc[1:].mean())
    return {"high": high, "atr": atr}


def entry(ask, lvl):
    return lvl is not None and lvl["atr"] > 0 and ask > lvl["high"]


def plan(entry_price, lvl):
    """Stop and take levels for a fill at entry_price."""
    return {
        "stop": entry_price - config.STOP_ATR * lvl["atr"],
        "take": entry_price + config.TAKE_ATR * lvl["atr"],
    }


def exit_reason(trade, bid, now):
    if bid <= trade["stop"]:
        return "stop"
    if bid >= trade["take"]:
        return "take"
    if now - trade["opened_at"] >= timedelta(minutes=config.MAX_HOLD_MINUTES):
        return "timeout"
    return None
