"""Crypto main loop: real-time quotes from feed.py (Alpaca crypto websocket), 24/7.

Two things happen here:

    quotes      every ask tick is checked against today's breakout target and
                the buy fires the moment it crosses (no polling delay)
    rollover    a small timer notices the UTC day change, closes everything
                bought yesterday at the new open, and computes new targets
                from the fresh daily bar

Broker and journal are shared with the stock bot, so crypto trades land on
the dashboard with their reasons.

    python crypto_run.py            run forever
    python crypto_run.py --once     print today's targets vs current asks, exit
"""
import argparse
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

import websockets
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest, CryptoLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame

import broker
import config as shared          # .env keys
import crypto_config as config
import crypto_strategy as strategy
import feed
import journal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.FileHandler("crypto.log"), logging.StreamHandler()],
)
log = logging.getLogger("crypto")

ROLLOVER_CHECK_S = 5             # how often the timer looks for a new UTC day
HEARTBEAT_S = 300                # ask-vs-target summary line while nothing fires

_data = CryptoHistoricalDataClient(shared.API_KEY, shared.SECRET_KEY)


class State:
    """Everything the tick handler needs, refreshed once per UTC day."""

    def __init__(self):
        self.day = None            # ISO date the targets belong to
        self.targets = {}          # symbol -> breakout level, or None
        self.entry_day = {}        # symbol -> ISO date of last entry (once-per-day guard)
        self.open_exposure = 0.0
        self.equity = 0.0
        self.lock = asyncio.Lock() # one trade at a time


def _pos_key(symbol):
    return symbol.replace("/", "")   # "BTC/USD" -> "BTCUSD" as Alpaca names positions


def daily_bars(symbols):
    start = datetime.now(timezone.utc) - timedelta(days=5)
    df = _data.get_crypto_bars(
        CryptoBarsRequest(symbol_or_symbols=symbols, timeframe=TimeFrame.Day, start=start)
    ).df
    return {s: df.xs(s, level="symbol") for s in symbols
            if s in df.index.get_level_values("symbol")}


def held_crypto():
    keys = {_pos_key(s) for s in config.SYMBOLS}
    return {s: p for s, p in broker.positions().items() if s in keys}


def refresh_account(state):
    held = held_crypto()
    state.equity = float(broker.account().equity)
    state.open_exposure = sum(abs(float(p.market_value)) for p in held.values())
    return held


def load_targets(state):
    """Compute today's targets. Returns False if today's bar isn't out yet."""
    bars = daily_bars(config.SYMBOLS)
    targets = {s: strategy.target(b) for s, b in bars.items()}
    if not any(targets.values()):
        return False
    state.targets = targets
    state.day = strategy.today_utc()
    for s, t in targets.items():
        log.info("%-8s target=%s", s, f"{t:.2f}" if t else "n/a (no bar yet)")
    return True


def buy(state, symbol, price):
    room = config.MAX_TOTAL_EXPOSURE_USD - state.open_exposure
    size = min(state.equity * config.POSITION_PCT, room)
    if size < 1:
        log.warning("%s: BUY skipped, crypto exposure cap reached ($%.0f)", symbol, state.open_exposure)
        return
    level = state.targets[symbol]
    reason = f"vol breakout: ask {price:.2f} >= open + {config.K} x prev range ({level:.2f})"
    log.info("%-8s %12.2f  target=%.2f  -> BUY", symbol, price, level)
    broker.buy(symbol, size, crypto=True)
    journal.record(symbol, "BUY", reason, price, notional=size, dry_run=config.DRY_RUN)
    state.open_exposure += size


def rollover(state, held, asks):
    """New UTC day: close yesterday's positions, then load today's targets."""
    for symbol in config.SYMBOLS:
        position = held.get(_pos_key(symbol))
        if position is None:
            continue
        price = asks.get(symbol, float(position.current_price))
        reason = f"day rollover: opened {state.entry_day.get(symbol, '?')}, exit at next UTC open"
        log.info("%-8s %12.2f  -> SELL (%s)", symbol, price, reason)
        broker.close(_pos_key(symbol))
        journal.record(symbol, "SELL", reason, price, qty=position.qty, dry_run=config.DRY_RUN)
    return load_targets(state)


async def on_quote(state, symbol, ask):
    if state.day != strategy.today_utc():
        return  # between the day change and the rollover task: hold fire
    level = state.targets.get(symbol)
    if level is None or ask < level or state.entry_day.get(symbol) == state.day:
        return
    async with state.lock:
        if state.entry_day.get(symbol) == state.day:
            return
        state.entry_day[symbol] = state.day     # claim before the slow REST calls
        try:
            await asyncio.to_thread(buy, state, symbol, ask)
        except Exception:
            log.exception("%s: buy failed", symbol)


async def rollover_task(state, asks):
    """Every few seconds: is it a new UTC day? Then close + retarget. Also
    retries load_targets until Alpaca publishes today's bar."""
    while True:
        try:
            if state.day != strategy.today_utc():
                async with state.lock:
                    held = await asyncio.to_thread(refresh_account, state)
                    ok = await asyncio.to_thread(rollover, state, held, asks)
                    if ok:
                        state.entry_day = {}
                        await asyncio.to_thread(refresh_account, state)
                    else:
                        log.info("waiting for today's daily bar...")
        except Exception:
            log.exception("rollover failed")
        await asyncio.sleep(ROLLOVER_CHECK_S)


async def heartbeat_task(state, asks):
    while True:
        await asyncio.sleep(HEARTBEAT_S)
        parts = []
        for s in config.SYMBOLS:
            t, a = state.targets.get(s), asks.get(s)
            flag = "IN" if state.entry_day.get(s) == state.day else "  "
            parts.append(f"{s} {a:.2f}/{t:.2f} {flag}" if t and a else f"{s} n/a")
        log.info("heartbeat  %s", " | ".join(parts))


async def stream(state, asks):
    """One session on the local feed (feed.py owns the Alpaca socket)."""
    async with websockets.connect(feed.LOCAL_URL, max_size=None) as socket:
        log.info("connected to feed %s", feed.LOCAL_URL)
        async for raw in socket:
            for item in json.loads(raw):
                if item.get("T") != "q" or item["S"] not in config.SYMBOLS:
                    continue
                symbol, ask = item["S"], float(item["ap"])
                asks[symbol] = ask
                await on_quote(state, symbol, ask)


async def run():
    state, asks = State(), {}
    held = refresh_account(state)
    for symbol in config.SYMBOLS:        # positions found on restart: opened "today"
        if _pos_key(symbol) in held:
            state.entry_day[symbol] = strategy.today_utc()
    load_targets(state)

    asyncio.create_task(rollover_task(state, asks))
    asyncio.create_task(heartbeat_task(state, asks))
    backoff = 1
    while True:
        try:
            await stream(state, asks)
            backoff = 1
        except Exception as exc:
            log.warning("feed dropped (%s), retrying in %ds", exc, backoff)
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 60)


def once():
    """Snapshot: today's targets against the current asks, no trading."""
    state = State()
    refresh_account(state)
    load_targets(state)
    quotes = _data.get_crypto_latest_quote(CryptoLatestQuoteRequest(symbol_or_symbols=config.SYMBOLS))
    for s in config.SYMBOLS:
        ask, t = float(quotes[s].ask_price), state.targets.get(s)
        status = "n/a" if t is None else ("ABOVE target" if ask >= t else f"{(t / ask - 1) * 100:+.2f}% to target")
        log.info("%-8s ask=%.2f  %s", s, ask, status)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="show targets vs asks and exit")
    args = parser.parse_args()

    acct = broker.account()
    log.info("paper=%s dry_run=%s equity=$%s crypto_cap=$%s symbols=%s K=%s",
             shared.PAPER, config.DRY_RUN, f"{float(acct.equity):,.2f}",
             f"{config.MAX_TOTAL_EXPOSURE_USD:,}", ",".join(config.SYMBOLS), config.K)
    if args.once:
        once()
        return
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        log.info("stopped")


if __name__ == "__main__":
    main()
