"""Thin wrapper over the Alpaca trading API. Honors config.DRY_RUN."""
import logging
from datetime import datetime, timedelta, timezone

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import AssetClass, AssetStatus, OrderSide, QueryOrderStatus, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest
from alpaca.trading.requests import GetAssetsRequest, GetOrdersRequest, LimitOrderRequest, MarketOrderRequest

import config

log = logging.getLogger(__name__)
_client = TradingClient(config.API_KEY, config.SECRET_KEY, paper=config.PAPER)
_data = StockHistoricalDataClient(config.API_KEY, config.SECRET_KEY)


def account():
    return _client.get_account()


def clock():
    return _client.get_clock()


def realized_vol(days=20):
    """Annualised std of the account's last `days` daily equity returns (portfolio history),
    or None when fewer days exist (a new account) or the request fails. Feeds config.VOL_TARGET."""
    from alpaca.trading.requests import GetPortfolioHistoryRequest
    try:
        hist = _client.get_portfolio_history(GetPortfolioHistoryRequest(period="3M", timeframe="1D"))
        eq = [float(v) for v in (hist.equity or []) if v and float(v) > 0]
    except Exception as exc:
        log.warning("portfolio history: %s", exc)
        return None
    rets = [b / a - 1 for a, b in zip(eq[:-1], eq[1:])][-days:]
    if len(rets) < days:
        return None
    mean = sum(rets) / len(rets)
    return (sum((r - mean) ** 2 for r in rets) / len(rets)) ** 0.5 * 252 ** 0.5


def is_market_open():
    return _client.get_clock().is_open


def positions():
    """{symbol: Position} for everything currently held (stocks and crypto)."""
    return {p.symbol: p for p in _client.get_all_positions()}


def tradable(symbols):
    """Subset of symbols that Alpaca lists as active, tradable, fractionable US equities."""
    assets = _client.get_all_assets(GetAssetsRequest(status=AssetStatus.ACTIVE, asset_class=AssetClass.US_EQUITY))
    ok = {a.symbol for a in assets if a.tradable and a.fractionable}
    return [s for s in symbols if s in ok]


def _dry(dry_run):
    return config.DRY_RUN if dry_run is None else dry_run


def quote(symbol):
    """(bid, ask, spread_bps) from the free IEX feed; (None, None, None) if unavailable."""
    try:
        q = _data.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=symbol))[symbol]
        bid, ask = float(q.bid_price or 0), float(q.ask_price or 0)
        age = (datetime.now(timezone.utc) - q.timestamp).total_seconds() if q.timestamp else 1e9
        if bid <= 0 or ask <= 0 or ask < bid or age > 120:      # stale (e.g. yesterday's last quote) -> no limit
            return None, None, None
        return bid, ask, (ask - bid) / ((ask + bid) / 2) * 1e4
    except Exception as exc:
        log.warning("quote %s: %s", symbol, exc)
        return None, None, None


def _order(symbol, notional, side, client_order_id, dry_run):
    """Marketable limit when a sane quote exists (fills at once, capped slippage); market otherwise."""
    if _dry(dry_run):
        log.info("DRY_RUN %s %s $%.2f", side.name, symbol, notional)
        return None
    bid, ask, spread = quote(symbol)
    if bid and spread is not None and spread <= config.MAX_SPREAD_BPS_FOR_LIMIT and config.LIMIT_COLLAR_BPS:
        collar = config.LIMIT_COLLAR_BPS / 1e4
        limit = round(ask * (1 + collar), 2) if side == OrderSide.BUY else round(bid * (1 - collar), 2)
        qty = round(notional / limit, 4)
        try:
            order = _client.submit_order(LimitOrderRequest(
                symbol=symbol, qty=qty, side=side, time_in_force=TimeInForce.DAY,
                limit_price=limit, client_order_id=client_order_id))
            log.info("%s %s $%.2f as LIMIT %.2f (spread %.0f bps, order %s)", side.name, symbol, notional, limit, spread, order.id)
            return order
        except Exception as exc:
            log.warning("limit order %s %s rejected (%s); falling back to market", side.name, symbol, exc)
    order = _client.submit_order(
        MarketOrderRequest(
            symbol=symbol,
            notional=round(notional, 2),
            side=side,
            time_in_force=TimeInForce.DAY,
            client_order_id=client_order_id,
        )
    )
    log.info("%s %s $%.2f MARKET (spread %s bps, order %s)", side.name, symbol, notional,
             f"{spread:.0f}" if spread is not None else "n/a", order.id)
    return order


def cleanup_open_orders(prefix, dry_run=None):
    """Cancel our still-open limit orders and re-send the unfilled remainder as market orders."""
    if _dry(dry_run):
        return 0
    n = 0
    for o in _client.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=500)):
        if not (o.client_order_id or "").startswith(prefix):
            continue
        try:
            _client.cancel_order_by_id(o.id)
            remaining = float(o.qty or 0) - float(o.filled_qty or 0)
            if remaining > 0:
                _client.submit_order(MarketOrderRequest(symbol=o.symbol, qty=round(remaining, 4), side=o.side,
                                                        time_in_force=TimeInForce.DAY,
                                                        client_order_id=(o.client_order_id + "-mkt")[:48]))
                log.info("cleanup: %s %s remaining %.4f sent as MARKET", o.side.name, o.symbol, remaining)
                n += 1
        except Exception as exc:
            log.error("cleanup %s failed: %s", o.symbol, exc)
    return n


def hedge_to(symbol, target_notional, client_order_id=None, dry_run=None):
    """Bring the SHORT position in `symbol` to -target_notional dollars (0 = flat) with one whole-share market order
    for the difference. Returns the signed share delta ordered (negative = sold short / added)."""
    pos = positions().get(symbol)
    cur_qty = float(pos.qty) if pos else 0.0
    price = float(pos.current_price) if pos else None
    if price is None:
        bid, ask, _ = quote(symbol)
        price = (bid + ask) / 2 if bid and ask else None
    if price is None:
        try:
            price = float(_client.get_latest_trade(symbol).price)   # last resort
        except Exception:
            log.warning("hedge %s: no price, skipped", symbol)
            return 0
    target_qty = -int(target_notional / price) if target_notional > 0 else 0
    delta = target_qty - cur_qty
    if abs(delta) * price < config.MIN_ORDER_USD:
        return 0
    side = OrderSide.SELL if delta < 0 else OrderSide.BUY
    if _dry(dry_run):
        log.info("DRY_RUN hedge %s %s %d shares (from %.0f to %d)", side.name, symbol, abs(int(delta)), cur_qty, target_qty)
        return int(delta)
    order = _client.submit_order(MarketOrderRequest(symbol=symbol, qty=abs(int(delta)), side=side,
                                                    time_in_force=TimeInForce.DAY, client_order_id=client_order_id))
    log.info("hedge %s %s %d shares MARKET (from %.0f to %d, order %s)", side.name, symbol, abs(int(delta)), cur_qty, target_qty, order.id)
    return int(delta)


def buy(symbol, notional, client_order_id=None, dry_run=None):
    """Market buy for a dollar amount."""
    return _order(symbol, notional, OrderSide.BUY, client_order_id, dry_run)


def sell(symbol, notional, client_order_id=None, dry_run=None):
    """Market sell for a dollar amount (partial exit)."""
    return _order(symbol, notional, OrderSide.SELL, client_order_id, dry_run)


def close(symbol, dry_run=None):
    """Liquidate the entire position in symbol."""
    if _dry(dry_run):
        log.info("DRY_RUN close %s", symbol)
        return None
    order = _client.close_position(symbol)
    log.info("CLOSE %s (order %s)", symbol, order.id)
    return order


def close_all(dry_run=None):
    """Cancel every open order and liquidate every position (stocks and crypto)."""
    if _dry(dry_run):
        log.info("DRY_RUN close_all")
        return []
    return _client.close_all_positions(cancel_orders=True)


def cancel_all():
    return _client.cancel_orders()


def recent_orders(hours=24):
    """Every order (open or closed) submitted in the last `hours`."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    out = []
    for status in (QueryOrderStatus.OPEN, QueryOrderStatus.CLOSED):
        out += _client.get_orders(GetOrdersRequest(status=status, after=since, limit=500))
    return out


def foreign_orders(hours=24):
    """Orders in the window that were NOT placed by this program (other bots)."""
    return [o for o in recent_orders(hours)
            if not (o.client_order_id or "").startswith(config.ORDER_PREFIX)]
