"""Market data.

Two sources, deliberately split:
  daily_bars()    SIP = full consolidated tape. Free plan allows it as long as
                  the data is >15 min old, so completed daily bars are fine.
  latest_prices() IEX = real-time but IEX-only volume. Used for live monitoring.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestTradeRequest
from alpaca.data.timeframe import TimeFrame

import config

ET = ZoneInfo("America/New_York")
_client = StockHistoricalDataClient(config.API_KEY, config.SECRET_KEY)


def daily_bars(symbols, lookback=None):
    """{symbol: DataFrame} of COMPLETED daily bars, oldest -> newest.

    Today's partial bar is dropped: a day-based signal should only fire on a
    session that actually finished.
    """
    lookback = lookback or config.LOOKBACK_DAYS
    now = datetime.now(timezone.utc)

    request = StockBarsRequest(
        symbol_or_symbols=list(symbols),
        timeframe=TimeFrame.Day,
        start=now - timedelta(days=lookback * 2 + 10),  # pad for weekends/holidays
        end=now - timedelta(minutes=16),                # stay clear of the SIP limit
        feed=DataFeed.SIP,
    )
    df = _client.get_stock_bars(request).df
    if df.empty:
        return {}

    today = datetime.now(ET).date()
    out = {}
    for symbol in symbols:
        if symbol not in df.index.get_level_values("symbol"):
            continue
        bars = df.xs(symbol, level="symbol")
        bars = bars[[ts.astimezone(ET).date() < today for ts in bars.index]]
        out[symbol] = bars.tail(lookback)
    return out


def latest_prices(symbols):
    """{symbol: last traded price} from the real-time IEX feed."""
    trades = _client.get_stock_latest_trade(
        StockLatestTradeRequest(symbol_or_symbols=list(symbols), feed=DataFeed.IEX)
    )
    return {symbol: trade.price for symbol, trade in trades.items()}
