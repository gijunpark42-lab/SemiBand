"""Main loop.

Day-based trading: signals come off completed daily bars, but the live price is
polled every cycle so intraday exits (stops, targets) can still fire.
"""
import argparse
import logging
import time

import broker
import config
import data
import strategy

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()],
)
log = logging.getLogger("run")


def exposure(held):
    return sum(abs(float(p.market_value)) for p in held.values())


def cycle():
    held = broker.positions()
    bars_by_symbol = data.daily_bars(config.WATCHLIST)
    prices = data.latest_prices(config.WATCHLIST)
    open_exposure = exposure(held)

    for symbol in config.WATCHLIST:
        try:
            bars = bars_by_symbol.get(symbol)
            price = prices.get(symbol)
            if bars is None or bars.empty or price is None:
                log.warning("%s: missing data (bars=%s price=%s)", symbol, bars is not None, price)
                continue

            position = held.get(symbol)
            prev_close = float(bars["close"].iloc[-1])
            change = (price - prev_close) / prev_close * 100

            signal = strategy.decide(symbol, bars, price, position)
            log.info(
                "%-6s %10.2f  %+6.2f%%  prev=%.2f  pos=%s  -> %s",
                symbol, price, change, prev_close,
                position.qty if position else "flat", signal or "watch",
            )

            if signal == "BUY" and position is None:
                room = config.MAX_TOTAL_EXPOSURE_USD - open_exposure
                size = min(config.MAX_POSITION_USD, room)
                if size < 1:
                    log.warning("%s: BUY skipped, exposure cap reached ($%.0f)", symbol, open_exposure)
                    continue
                broker.buy(symbol, size)
                open_exposure += size
            elif signal == "SELL" and position is not None:
                broker.close(symbol)
                open_exposure -= abs(float(position.market_value))
        except Exception:
            log.exception("%s: cycle failed", symbol)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true",
                        help="run a single cycle and exit, ignoring market hours")
    args = parser.parse_args()

    acct = broker.account()
    log.info(
        "paper=%s dry_run=%s equity=$%s cap=$%s watchlist=%s",
        config.PAPER, config.DRY_RUN, f"{float(acct.equity):,.2f}",
        f"{config.MAX_TOTAL_EXPOSURE_USD:,}", ",".join(config.WATCHLIST),
    )

    if args.once:
        cycle()
        return

    while True:
        if broker.is_market_open():
            cycle()
        else:
            log.info("market closed, waiting")
        time.sleep(config.POLL_SECONDS)


if __name__ == "__main__":
    main()
