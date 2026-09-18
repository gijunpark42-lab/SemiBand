"""Convictions -> target dollar positions -> orders. Long-only, margin allowed.

Sizing: candidates above MIN_CONVICTION, top TOP_N, each sized by its own
conviction (conviction x SIZE_PER_CONVICTION of equity, capped per name).
GROSS_TARGET (1.5 = 50% margin) is a ceiling, never a goal — there is no
obligation to hold 15 names or to be fully invested. Buys are limited by the
broker's buying power and by the gross ceiling, never beyond either.
"""
import config


def targets(convictions, equity, realized_vol=None):
    """{ticker: target USD}.

    Each name is sized by its own conviction (conviction x SIZE_PER_CONVICTION of
    equity, capped at MAX_POSITION_PCT), so a weak day produces a small book and
    cash stays a position. GROSS_TARGET is a ceiling, not a goal: if the sized
    book exceeds it, everything is scaled down proportionally.
    realized_vol: the book's trailing annualised vol (None = unknown); when it exceeds
    config.VOL_TARGET the whole book is scaled down by VOL_TARGET / realized_vol."""
    longs = sorted(((t, c) for t, c in convictions.items() if c >= config.MIN_CONVICTION),
                   key=lambda tc: -tc[1])[:config.TOP_N]
    if not longs:
        return {}
    weights = {t: min(c * config.SIZE_PER_CONVICTION, config.MAX_POSITION_PCT) for t, c in longs}
    gross = sum(weights.values())
    if gross > config.GROSS_TARGET:
        weights = {t: w * config.GROSS_TARGET / gross for t, w in weights.items()}
    elif config.MIN_STOCK_BOOK and 0 < gross < config.MIN_STOCK_BOOK:
        # few or weak names passed the bar: scale them up to the floor, never above the per-name cap
        weights = {t: min(w * config.MIN_STOCK_BOOK / gross, config.MAX_POSITION_PCT) for t, w in weights.items()}
    if config.VOL_TARGET and realized_vol and realized_vol > config.VOL_TARGET:
        weights = {t: w * config.VOL_TARGET / realized_vol for t, w in weights.items()}
    return {t: round(w * equity, 2) for t, w in weights.items() if w * equity >= config.MIN_ORDER_USD}


def beta_floor(weights, betas, floor, cap, sleeve="__SLEEVE__"):
    """Round 42 candidate: raise the book's benchmark beta to `floor` with the idle-sleeve ETF (beta 1). weights = {ticker:
    weight}, the sleeve under `sleeve`, other "__" keys untouched; betas = {ticker: beta}, missing -> 1.0. The sleeve grows
    while gross <= cap; past the cap the stock weights are scaled down together so that gross == cap and beta == floor.
    A book already at the floor, or one that cannot be traded for beta, is returned unchanged. -> new weights"""
    stocks = {t: x for t, x in weights.items() if not t.startswith("__")}
    other = sum(abs(x) for t, x in weights.items() if t.startswith("__") and t != sleeve)
    gross = sum(abs(x) for x in stocks.values())
    beta = sum(x * betas.get(t, 1.0) for t, x in stocks.items())
    if beta + weights.get(sleeve, 0.0) >= floor:
        return dict(weights)
    need = floor - beta                                  # total sleeve weight that brings the book to the floor
    if gross + other + need <= cap:
        return {**weights, sleeve: need}
    if gross - beta <= 1e-9:
        return dict(weights)
    k = (cap - other - floor) / (gross - beta)
    if not 0.0 < k < 1.0:
        return dict(weights)
    out = {t: (x * k if not t.startswith("__") else x) for t, x in weights.items()}
    out[sleeve] = floor - k * beta
    return out


def apply_beta_floor(target_usd, betas, equity, closes, realized_vol=None):
    """Round 47: the live beta floor. While config.IDLE_SLEEVE closed above its IDLE_SLEEVE_TREND-day average, the stock book's
    beta to the benchmark is raised to config.BETA_FLOOR with the sleeve ETF through beta_floor() (cap = GROSS_TARGET, as the
    replay). betas = {ticker: beta or None}, missing -> 1.0. -> (new target_usd, sleeve USD the floor needs, note); the targets
    unchanged and 0.0 when the floor is off, not binding, or the ETF is below its average."""
    floor, etf = config.BETA_FLOOR, config.IDLE_SLEEVE
    if not floor or not etf or equity <= 0 or not target_usd:
        return target_usd, 0.0, ""
    n = config.IDLE_SLEEVE_TREND
    c = closes[etf].dropna() if etf in closes.columns else closes.iloc[:0, :0]
    if len(c) < (n or 1):
        return target_usd, 0.0, f"beta floor {floor:.2f}: no usable {etf} closes, off"
    if n and float(c.iloc[-1]) <= float(c.iloc[-n:].mean()):
        return target_usd, 0.0, f"beta floor {floor:.2f}: off ({etf} at or below its {n}-day average)"
    b = {t: float(v) for t, v in (betas or {}).items() if v is not None and v == v}
    w = {t: usd / equity for t, usd in target_usd.items()}
    beta_before = sum(x * b.get(t, 1.0) for t, x in w.items())
    out = beta_floor(w, b, float(floor), config.GROSS_TARGET)
    sleeve = out.pop("__SLEEVE__", 0.0)
    if sleeve <= 0:
        return target_usd, 0.0, f"beta floor {floor:.2f}: book beta {beta_before:.2f}, nothing to add"
    k = sum(out.values()) / sum(w.values()) if sum(w.values()) else 1.0
    new = {t: round(x * equity, 2) for t, x in out.items() if x * equity >= config.MIN_ORDER_USD}
    note = f"beta floor {floor:.2f}: book beta {beta_before:.2f} -> {etf} {sleeve:.0%} of equity" + (f", stocks scaled x{k:.2f} (gross ceiling)" if k < 0.999 else "")
    return new, round(sleeve * equity, 2), note


def chain_cap(weights, groups, group, cap):
    """Round 47 candidate: the names of `group` (groups = {ticker: group}) may hold at most `cap` of equity together; above it they
    are scaled down proportionally, other names and "__" keys untouched (the freed capacity is idle: the sleeve rule may fill it).
    -> new weights"""
    members = {t: x for t, x in weights.items() if not t.startswith("__") and groups.get(t) == group}
    total = sum(members.values())
    if total <= 0 or total <= cap:
        return dict(weights)
    k = cap / total
    return {t: (x * k if t in members else x) for t, x in weights.items()}


def plan(target_usd, positions, convictions, universe, equity, buying_power, extra_proceeds=0.0):
    """-> list of {ticker, side, notional|None(close), reason_tag}. Sells first, then buys.

    positions = {symbol: alpaca Position}. Holdings outside the universe are
    left alone (they should not exist after the fresh-start liquidation).
    extra_proceeds: dollars the same cycle sells outside the universe before the buys (the idle sleeve), so a
    re-entry day is not capped by a sleeve that is about to be sold (audit 2026-09-15).
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
        else:
            # still above the bar but pushed out of the top N by stronger names: sell, so the book is
            # always the day's top N (this is what the backtest simulates; "seat protection" tested worse)
            sells.append({"ticker": s, "side": "SELL", "notional": None, "tag": f"exit: conviction {conv:+.2f} ranked outside the top {config.TOP_N}"})

    for s, tgt in target_usd.items():
        diff = tgt - held.get(s, 0.0)
        if s in held and abs(diff) < config.REBALANCE_BAND * tgt:
            continue                      # inside the band: hold, do not churn
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
    proceeds = sum((held[o["ticker"]] if o["notional"] is None else o["notional"]) for o in sells) + max(extra_proceeds, 0.0)
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


def sleeve_target(target_usd, equity, closes, realized_vol=None):
    """Dollars for config.IDLE_SLEEVE: IDLE_SLEEVE_FRACTION of the equity the stock book leaves idle, while the ETF closed
    above its IDLE_SLEEVE_TREND-day average (the backtest's rule), scaled with the vol target like the book. 0.0 when off."""
    etf = config.IDLE_SLEEVE
    if not etf or equity <= 0 or (config.HEDGE_SIZE and config.HEDGE_SYMBOL == etf):
        return 0.0
    n = config.IDLE_SLEEVE_TREND
    c = closes[etf].dropna() if etf in closes.columns else closes.iloc[:0, :0]
    if len(c) < (n or 1):
        return None                      # no usable prices (a failed download): leave the position alone rather than sell it
    if n and float(c.iloc[-1]) <= float(c.iloc[-n:].mean()):
        return 0.0
    scale = min(1.0, config.VOL_TARGET / realized_vol) if (config.VOL_TARGET and realized_vol and realized_vol > config.VOL_TARGET) else 1.0
    idle = max(0.0, scale - sum(target_usd.values()) / equity)   # the vol target caps total exposure; the sleeve only fills up to it
    usd = config.IDLE_SLEEVE_FRACTION * idle * equity
    return round(usd, 2) if usd >= config.MIN_ORDER_USD else 0.0


def plan_sleeve(target, positions):
    """The order that moves the config.IDLE_SLEEVE position to `target` dollars, with the stocks' rebalance band; [] if none."""
    etf = config.IDLE_SLEEVE
    if not etf:
        return []
    held = float(positions[etf].market_value) if etf in positions else 0.0
    if target <= 0:
        return [{"ticker": etf, "side": "SELL", "notional": None, "tag": "idle sleeve off"}] if held > 0 else []
    diff = target - held
    if held > 0 and abs(diff) < config.REBALANCE_BAND * target:
        return []
    if diff >= config.MIN_ORDER_USD:
        return [{"ticker": etf, "side": "BUY", "notional": round(diff, 2), "tag": "idle sleeve"}]
    if diff <= -config.MIN_ORDER_USD:
        return [{"ticker": etf, "side": "SELL", "notional": round(-diff, 2), "tag": "idle sleeve trim"}]
    return []


def without_sleeve_proceeds(order, fallback_buys):
    """A stock BUY after the sleeve's sale failed at the broker: the same order resized to the budget that did not count the
    sleeve's proceeds (fallback_buys = {ticker: notional} from plan() without extra_proceeds); None = no room for it there."""
    if order["ticker"] not in fallback_buys:
        return None
    return dict(order, notional=fallback_buys[order["ticker"]], tag=order["tag"] + " (sleeve sale failed: budget without its proceeds)")
