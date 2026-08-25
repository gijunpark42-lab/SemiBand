"""Thin wrapper over the Alpaca trading API. Honors config.DRY_RUN."""
import logging

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

import config

log = logging.getLogger(__name__)
_client = TradingClient(config.API_KEY, config.SECRET_KEY, paper=config.PAPER)


def account():
    return _client.get_account()


def is_market_open():
    return _client.get_clock().is_open


def positions():
    """{symbol: Position} for everything currently held."""
    return {p.symbol: p for p in _client.get_all_positions()}


def buy(symbol, notional, crypto=False):
    """Market buy for a dollar amount. Crypto orders must be GTC (no DAY)."""
    if config.DRY_RUN:
        log.info("DRY_RUN buy %s $%.2f", symbol, notional)
        return None
    order = _client.submit_order(
        MarketOrderRequest(
            symbol=symbol,
            notional=round(notional, 2),
            side=OrderSide.BUY,
            time_in_force=TimeInForce.GTC if crypto else TimeInForce.DAY,
        )
    )
    log.info("BUY %s $%.2f (order %s)", symbol, notional, order.id)
    return order


def close(symbol):
    """Liquidate the entire position in symbol."""
    if config.DRY_RUN:
        log.info("DRY_RUN close %s", symbol)
        return None
    order = _client.close_position(symbol)
    log.info("CLOSE %s (order %s)", symbol, order.id)
    return order
