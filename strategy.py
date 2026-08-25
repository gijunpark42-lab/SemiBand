"""P/S band: buy a name when it is cheap against its OWN recent history,
sell when it is rich.

decide() is called once per symbol per cycle. Return "BUY", "SELL", or None.

    bars      DataFrame of COMPLETED daily bars, oldest -> newest.
              columns: open / high / low / close / volume / trade_count / vwap
              Today is NOT in here -- use `price` for today.
    price     live last-traded price right now (IEX real-time)
    position  the open Alpaca Position for this symbol, or None if flat

For each historical bar the P/S is computed with the revenue and share count
that were KNOWN on that date (fundamentals.ps applies the report lag), so the
band is what a trader could actually have seen. Today's P/S is then ranked
inside that band as a percentile:

    percentile <= PS_BUY_PCT   and flat     -> BUY
    percentile >= PS_SELL_PCT  and holding  -> SELL
    otherwise                               -> None

Names with no cache entry (ETFs), no full TTM (young listings), or too little
history return None -- the bot just watches them.
"""
import logging

import config
import fundamentals

log = logging.getLogger("strategy")

_cache = fundamentals.load()


def ps_band(symbol, bars):
    """Historical P/S per bar as a list, [] if the name can't be valued."""
    entry = _cache.get(symbol)
    if entry is None:
        return []
    band = []
    for ts, close in bars["close"].items():
        value = fundamentals.ps(entry, float(close), asof=ts.date().isoformat())
        if value is not None:
            band.append(value)
    return band


def percentile(value, band):
    """Share of `band` at or below `value`, 0-100."""
    return 100.0 * sum(1 for v in band if v <= value) / len(band)


def decide(symbol, bars, price, position):
    entry = _cache.get(symbol)
    if entry is None:
        return None
    today = fundamentals.ps(entry, price)
    band = ps_band(symbol, bars)
    if today is None or len(band) < config.PS_MIN_HISTORY:
        return None

    pct = percentile(today, band)
    log.debug("%s: P/S %.2f, band %.2f-%.2f, pct %.0f", symbol, today, min(band), max(band), pct)

    if position is None and pct <= config.PS_BUY_PCT:
        return "BUY"
    if position is not None and pct >= config.PS_SELL_PCT:
        return "SELL"
    return None
