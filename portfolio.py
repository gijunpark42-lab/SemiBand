"""Convictions -> target dollar positions -> orders. Long-only, margin allowed.

Sizing: candidates above MIN_CONVICTION, top TOP_N, dollars in proportion to
conviction, capped per name, GROSS_TARGET of equity in total (1.5 = 50%
margin). Anything the cap removes is not redistributed — simple and easy to
reason about on the dashboard. Buys are limited by the broker's buying power
and by the gross target, never beyond either.
"""
import config


def targets(convictions, equity):
    """{ticker: target USD}."""
    longs = sorted(((t, c) for t, c in convictions.items() if c >= config.MIN_CONVICTION),
                   key=lambda tc: -tc[1])[:config.TOP_N]
    if not longs:
        return {}
    total = sum(c for _, c in longs)
    out = {}
    for t, c in longs:
        w = min(c / total * config.GROSS_TARGET, config.MAX_POSITION_PCT)
        out[t] = round(w * equity, 2)
    return out


def plan(target_usd, positions, convictions, universe, equity, buying_power):
    """-> list of {ticker, side, notional|None(close), reason_tag}. Sells first, then buys.

    positions = {symbol: alpaca Position}. Holdings outside the universe are
    left alone (they should not exist after the fresh-start liquidation).
    """
    held = {s: float(p.market_value) for s, p in positions.items() if s in universe}
    held_total = sum(float(p.market_value) for p in positions.values())
    sells, buys = [], []

    for s, mv in held.items():
        if s in target_usd:
            continue
        conv = convictions.get(s, 0.0)
        if conv < config.MIN_CONVICTION:
            sells.append({"ticker": s, "side": "SELL", "notional": None, "tag": f"exit: conviction {conv:+.2f} below entry bar"})
        # still above the bar but pushed out of the top N: hold, no churn

    for s, tgt in target_usd.items():
        diff = tgt - held.get(s, 0.0)
        if diff >= config.MIN_ORDER_USD:
            buys.append({"ticker": s, "side": "BUY", "notional": round(diff, 2), "tag": "target"})
        elif diff <= -config.MIN_ORDER_USD:
            remaining = held[s] + diff
            if remaining < config.MIN_ORDER_USD:
                sells.append({"ticker": s, "side": "SELL", "notional": None, "tag": "trim to zero"})
            else:
                sells.append({"ticker": s, "side": "SELL", "notional": round(-diff, 2), "tag": "trim"})

    # Budget for buys: stay within GROSS_TARGET x equity after the sells, and
    # within what the broker will actually lend (buying power + proceeds).
    proceeds = sum((held[o["ticker"]] if o["notional"] is None else o["notional"]) for o in sells)
    room_to_gross = equity * config.GROSS_TARGET - (held_total - proceeds)
    budget = max(0.0, min(room_to_gross, max(buying_power, 0.0) + proceeds))
    want = sum(o["notional"] for o in buys)
    if want > budget > 0:
        scale = budget / want
        for o in buys:
            o["notional"] = round(o["notional"] * scale, 2)
            o["tag"] += f" (scaled x{scale:.2f} to gross/buying-power limit)"
        buys = [o for o in buys if o["notional"] >= config.MIN_ORDER_USD]
    elif budget <= 0:
        buys = []
    return sells + buys
