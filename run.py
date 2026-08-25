"""Main loop.

Day-based trading: signals come off completed daily bars, but the live price is
polled every cycle so intraday exits (stops, targets) can still fire.
"""
import argparse
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import broker
import config
import data
import journal
import strategy

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()],
)
log = logging.getLogger("run")


GUIDANCE_FILE = Path(__file__).with_name(config.GUIDANCE_FILE)


def exposure(held):
    return sum(abs(float(p.market_value)) for p in held.values())


def guidance_misses():
    """{symbol: entry} for names whose latest guidance says exit and which are
    still inside the re-entry cooldown."""
    if not GUIDANCE_FILE.exists():
        return {}
    book = json.loads(GUIDANCE_FILE.read_text())
    cutoff = datetime.now(timezone.utc) - timedelta(days=config.GUIDANCE_COOLDOWN_DAYS)
    return {
        s: g for s, g in book.items()
        if strategy.guidance_exit(g) and datetime.fromisoformat(g["at"]) > cutoff
    }


def _pct(value):
    return "?" if value is None else f"{value:+.1f}%"


def cycle():
    held = broker.positions()
    equity = float(broker.account().equity)
    bars_by_symbol = data.daily_bars(config.WATCHLIST)
    prices = data.latest_prices(config.WATCHLIST)
    misses = guidance_misses()
    open_exposure = exposure(held)
    candidates = []  # (percentile, symbol) for BUY signals

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

            if symbol in misses:
                # guidance miss: close everything, and no re-entry until cooldown
                miss = misses[symbol]
                signal = "SELL" if position is not None else None
                reason = f"guidance miss: sales {_pct(miss.get('sales_pct'))} eps {_pct(miss.get('eps_pct'))} vs street"
                note = f"{signal or 'blocked'} ({reason})"
            else:
                signal = strategy.decide(symbol, bars, price, position)
                pct = strategy.ps_percentile(symbol, bars, price)
                reason = None if pct is None else f"P/S percentile {pct:.0f} of own band"
                note = signal or "watch"
            log.info(
                "%-6s %10.2f  %+6.2f%%  prev=%.2f  pos=%s  -> %s",
                symbol, price, change, prev_close,
                position.qty if position else "flat", note,
            )

            if signal == "BUY" and position is None:
                candidates.append((pct, symbol, price, reason))
            elif signal == "SELL" and position is not None:
                broker.close(symbol)
                journal.record(symbol, "SELL", reason, price,
                               qty=position.qty, dry_run=config.DRY_RUN)
                open_exposure -= abs(float(position.market_value))
        except Exception:
            log.exception("%s: cycle failed", symbol)

    candidates.sort()
    if len(candidates) > config.MAX_NEW_ENTRIES:
        log.info("%d BUY candidates, taking the %d cheapest: %s",
                 len(candidates), config.MAX_NEW_ENTRIES,
                 " ".join(f"{c[1]}({c[0]:.0f})" for c in candidates[:config.MAX_NEW_ENTRIES]))
    for pct, symbol, price, reason in candidates[:config.MAX_NEW_ENTRIES]:
        try:
            room = config.MAX_TOTAL_EXPOSURE_USD - open_exposure
            size = min(equity * config.POSITION_PCT, room)
            if size < 1:
                log.warning("%s: BUY skipped, exposure cap reached ($%.0f)", symbol, open_exposure)
                continue
            broker.buy(symbol, size)
            journal.record(symbol, "BUY", reason, price, notional=size, dry_run=config.DRY_RUN)
            open_exposure += size
        except Exception:
            log.exception("%s: buy failed", symbol)


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
