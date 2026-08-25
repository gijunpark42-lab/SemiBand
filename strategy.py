"""Entry: P/S band. Exit: P/S band or a guidance miss.

decide() is called once per symbol per cycle. Return "BUY", "SELL", or None.

    bars      DataFrame of COMPLETED daily bars, oldest -> newest.
              columns: open / high / low / close / volume / trade_count / vwap
              Today is NOT in here -- use `price` for today.
    price     live last-traded price right now (IEX real-time)
    position  the open Alpaca Position for this symbol, or None if flat

P/S band -- for each historical bar the P/S is computed with the revenue and
share count that were KNOWN on that date (fundamentals.ps applies the report
lag), so the band is what a trader could actually have seen. Today's P/S is
ranked inside that band as a percentile:

    percentile <= PS_BUY_PCT   and flat     -> BUY
    percentile >= PS_SELL_PCT  and holding  -> SELL
    otherwise                               -> None

run.py takes only the MAX_NEW_ENTRIES lowest-percentile BUYs per cycle, so a
sector-wide selloff buys the cheapest few instead of everything at once.

Guidance exit -- earnings_stream.py parses "Sees Q3 Adj EPS $A-$B vs $C Est;
Sees Sales $D-$E vs $F Est" wire headlines into guidance.json. guidance_exit()
closes the whole position when the company guides below the street:

    sales mid < est                                   -> exit
    sales mid >= est, eps mid < est,
        and |eps miss %| >= EPS_VS_SALES_RATIO x sales beat %   -> exit

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


def ps_percentile(symbol, bars, price):
    """Where today's P/S sits in its own history, 0-100. None if unknown."""
    entry = _cache.get(symbol)
    if entry is None:
        return None
    today = fundamentals.ps(entry, price)
    band = ps_band(symbol, bars)
    if today is None or len(band) < config.PS_MIN_HISTORY:
        return None
    pct = 100.0 * sum(1 for v in band if v <= today) / len(band)
    log.debug("%s: P/S %.2f, band %.2f-%.2f, pct %.0f", symbol, today, min(band), max(band), pct)
    return pct


def decide(symbol, bars, price, position):
    pct = ps_percentile(symbol, bars, price)
    if pct is None:
        return None
    if position is None and pct <= config.PS_BUY_PCT:
        return "BUY"
    if position is not None and pct >= config.PS_SELL_PCT:
        return "SELL"
    return None


def guidance_exit(guide):
    """True if a guidance.json entry says the company guided below the street."""
    sales, eps = guide.get("sales_pct"), guide.get("eps_pct")
    if sales is None:
        return False
    if sales < 0:
        return True
    if eps is None or eps >= 0:
        return False
    return abs(eps) >= config.EPS_VS_SALES_RATIO * sales
