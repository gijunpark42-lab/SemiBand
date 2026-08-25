"""Crypto main loop: 24/7, polls every POLL_SECONDS.

Same skeleton as run.py but its own config, strategy, and log. Broker and
journal are shared, so crypto trades show up on the dashboard with reasons.

    python crypto_run.py            run forever
    python crypto_run.py --once     one cycle and exit
"""
import argparse
import logging
import time
from datetime import datetime, timedelta, timezone

from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest, CryptoLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame

import broker
import config as shared          # .env keys
import crypto_config as config
import crypto_strategy as strategy
import journal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.FileHandler("crypto.log"), logging.StreamHandler()],
)
log = logging.getLogger("crypto")

_data = CryptoHistoricalDataClient(shared.API_KEY, shared.SECRET_KEY)

# symbol -> ISO date (UTC) of the last entry. Doubles as the once-per-day
# guard. A position found on restart with no memory is treated as opened
# today (it will be closed at the next rollover).
_entry_day = {}


def daily_bars(symbols):
    start = datetime.now(timezone.utc) - timedelta(days=5)
    df = _data.get_crypto_bars(
        CryptoBarsRequest(symbol_or_symbols=symbols, timeframe=TimeFrame.Day, start=start)
    ).df
    return {s: df.xs(s, level="symbol") for s in symbols
            if s in df.index.get_level_values("symbol")}


def asks(symbols):
    quotes = _data.get_crypto_latest_quote(CryptoLatestQuoteRequest(symbol_or_symbols=symbols))
    return {s: float(q.ask_price) for s, q in quotes.items()}


def cycle():
    held = {s: p for s, p in broker.positions().items() if s in {x.replace("/", "") for x in config.SYMBOLS}}
    equity = float(broker.account().equity)
    bars_by_symbol = daily_bars(config.SYMBOLS)
    prices = asks(config.SYMBOLS)
    open_exposure = sum(abs(float(p.market_value)) for p in held.values())

    for symbol in config.SYMBOLS:
        try:
            bars, price = bars_by_symbol.get(symbol), prices.get(symbol)
            if bars is None or bars.empty or price is None:
                log.warning("%s: missing data", symbol)
                continue
            position = held.get(symbol.replace("/", ""))
            if position is not None and symbol not in _entry_day:
                _entry_day[symbol] = strategy.today_utc()
            level = strategy.target(bars)
            signal = strategy.decide(symbol, bars, price, position, _entry_day.get(symbol))

            log.info("%-8s %12.2f  target=%s  pos=%s  -> %s",
                     symbol, price, f"{level:.2f}" if level else "n/a",
                     position.qty if position else "flat", signal or "watch")

            if signal == "BUY":
                room = config.MAX_TOTAL_EXPOSURE_USD - open_exposure
                size = min(equity * config.POSITION_PCT, room)
                if size < 1:
                    log.warning("%s: BUY skipped, crypto exposure cap reached ($%.0f)", symbol, open_exposure)
                    continue
                reason = f"vol breakout: ask {price:.2f} >= open + {config.K} x prev range ({level:.2f})"
                broker.buy(symbol, size, crypto=True)
                journal.record(symbol, "BUY", reason, price, notional=size, dry_run=config.DRY_RUN)
                _entry_day[symbol] = strategy.today_utc()
                open_exposure += size
            elif signal == "SELL":
                reason = f"day rollover: opened {_entry_day.get(symbol)}, exit at next UTC open"
                broker.close(symbol.replace("/", ""))
                journal.record(symbol, "SELL", reason, price, qty=position.qty, dry_run=config.DRY_RUN)
                open_exposure -= abs(float(position.market_value))
        except Exception:
            log.exception("%s: cycle failed", symbol)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="run a single cycle and exit")
    args = parser.parse_args()

    acct = broker.account()
    log.info("paper=%s dry_run=%s equity=$%s crypto_cap=$%s symbols=%s K=%s",
             shared.PAPER, config.DRY_RUN, f"{float(acct.equity):,.2f}",
             f"{config.MAX_TOTAL_EXPOSURE_USD:,}", ",".join(config.SYMBOLS), config.K)
    if args.once:
        cycle()
        return
    while True:
        cycle()
        time.sleep(config.POLL_SECONDS)


if __name__ == "__main__":
    main()
