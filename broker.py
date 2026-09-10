"""Thin wrapper over the Alpaca trading API. Honors config.DRY_RUN."""
import logging
from datetime import datetime, timedelta, timezone

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import AssetClass, AssetStatus, OrderSide, QueryOrderStatus, TimeInForce
from alpaca.trading.requests import GetAssetsRequest, GetOrdersRequest, MarketOrderRequest

import config

log = logging.getLogger(__name__)
_client = TradingClient(config.API_KEY, config.SECRET_KEY, paper=config.PAPER)


def account():
    return _client.get_account()


def clock():
    return _client.get_clock()


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


def _order(symbol, notional, side, client_order_id, dry_run):
    if _dry(dry_run):
        log.info("DRY_RUN %s %s $%.2f", side.name, symbol, notional)
        return None
    order = _client.submit_order(
        MarketOrderRequest(
            symbol=symbol,
            notional=round(notional, 2),
            side=side,
            time_in_force=TimeInForce.DAY,
            client_order_id=client_order_id,
        )
    )
    log.info("%s %s $%.2f (order %s)", side.name, symbol, notional, order.id)
    return order


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
