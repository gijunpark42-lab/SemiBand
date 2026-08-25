"""Intraday crypto bot: Donchian(20x15m) breakout, ATR stop/take, 4h time stop.

    ticks        every quote is checked: ask vs the Donchian high for entries,
                 bid vs stop / take for exits (sells happen at the bid)
    bar timer    every 15 minutes, right after a bar closes, the Donchian high
                 and ATR are recomputed from completed bars
    risk         4% per trade, max 3 open, daily realized-loss limit, and a
                 pause after 3 consecutive stop-outs

Open trades live in memory (stop/take/opened_at) so exits work in DRY_RUN too;
on restart, real positions found at the broker are re-adopted with fresh
levels. Broker and journal are shared with the other bots.

    python scalp_run.py            run forever
    python scalp_run.py --once     print levels vs current asks, exit
"""
import argparse
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

import websockets
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest, CryptoLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

import broker
import config as shared
import feed
import journal
import scalp_config as config
import scalp_strategy as strategy

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.FileHandler("scalp.log"), logging.StreamHandler()],
)
log = logging.getLogger("scalp")

HEARTBEAT_S = 300
_data = CryptoHistoricalDataClient(shared.API_KEY, shared.SECRET_KEY)


def now_utc():
    return datetime.now(timezone.utc)


def pos_key(symbol):
    return symbol.replace("/", "")


class State:
    def __init__(self):
        self.levels = {}          # symbol -> {"high", "atr"} or None
        self.trades = {}          # symbol -> {"entry", "stop", "take", "opened_at", "notional", "qty"}
        self.cooldown_until = {}  # symbol -> datetime
        self.equity = 0.0
        self.day = None           # UTC date the daily P&L belongs to
        self.day_pnl = 0.0        # realized, price-based (fees not included)
        self.consec_stops = 0
        self.paused_until = None
        self.lock = asyncio.Lock()


def fetch_bars(symbols):
    tf = TimeFrame(config.BAR_MINUTES, TimeFrameUnit.Minute)
    start = now_utc() - timedelta(minutes=config.BAR_MINUTES * (config.DONCHIAN + config.ATR_PERIOD + 10))
    df = _data.get_crypto_bars(CryptoBarsRequest(symbol_or_symbols=symbols, timeframe=tf, start=start)).df
    out = {}
    current_open = now_utc().replace(second=0, microsecond=0)
    current_open -= timedelta(minutes=current_open.minute % config.BAR_MINUTES)
    for s in symbols:
        if s not in df.index.get_level_values("symbol"):
            continue
        bars = df.xs(s, level="symbol")
        out[s] = bars[bars.index < current_open]   # completed bars only
    return out


def refresh_levels(state):
    for s, bars in fetch_bars(config.SYMBOLS).items():
        state.levels[s] = strategy.levels(bars)
        lvl = state.levels[s]
        log.info("%-9s donchian=%s atr=%s", s,
                 f"{lvl['high']:.4f}" if lvl else "n/a", f"{lvl['atr']:.4f}" if lvl else "n/a")


def roll_day(state):
    today = now_utc().date().isoformat()
    if state.day != today:
        state.day, state.day_pnl = today, 0.0
        state.equity = float(broker.account().equity)


def entries_allowed(state):
    if state.paused_until and now_utc() < state.paused_until:
        return False
    if state.day_pnl <= -config.DAILY_LOSS_LIMIT_PCT * state.equity:
        return False
    return len(state.trades) < config.MAX_OPEN


def do_buy(state, symbol, ask):
    lvl = state.levels[symbol]
    size = state.equity * config.POSITION_PCT
    plan = strategy.plan(ask, lvl)
    reason = (f"donchian breakout: ask {ask:.4f} > {config.DONCHIAN}x{config.BAR_MINUTES}m high {lvl['high']:.4f}; "
              f"stop {plan['stop']:.4f} take {plan['take']:.4f}")
    log.info("%-9s %10.4f  -> BUY $%.0f (%s)", symbol, ask, size, reason)
    broker.buy(symbol, size, crypto=True)
    journal.record(symbol, "BUY", reason, ask, notional=size, dry_run=config.DRY_RUN)
    state.trades[symbol] = {"entry": ask, "opened_at": now_utc(), "notional": size,
                            "qty": size / ask, **plan}


def do_sell(state, symbol, bid, why):
    trade = state.trades.pop(symbol)
    pnl_pct = (bid - trade["entry"]) / trade["entry"]
    pnl = pnl_pct * trade["notional"]
    state.day_pnl += pnl
    state.consec_stops = state.consec_stops + 1 if why == "stop" else 0
    reason = f"{why}: bid {bid:.4f} vs entry {trade['entry']:.4f} ({pnl_pct * 100:+.2f}%, ${pnl:+.0f})"
    log.info("%-9s %10.4f  -> SELL (%s)  day_pnl=$%.0f", symbol, bid, reason, state.day_pnl)
    broker.close(pos_key(symbol))
    journal.record(symbol, "SELL", reason, bid, qty=round(trade["qty"], 6), dry_run=config.DRY_RUN)
    state.cooldown_until[symbol] = now_utc() + timedelta(minutes=config.REENTRY_COOLDOWN_MINUTES)
    if state.consec_stops >= config.MAX_CONSEC_STOPS:
        state.paused_until = now_utc() + timedelta(minutes=config.PAUSE_MINUTES)
        state.consec_stops = 0
        log.warning("%d stops in a row: pausing entries until %s", config.MAX_CONSEC_STOPS,
                    state.paused_until.strftime("%H:%M UTC"))


async def on_quote(state, symbol, bid, ask):
    trade = state.trades.get(symbol)
    if trade:
        why = strategy.exit_reason(trade, bid, now_utc())
        if why:
            async with state.lock:
                if symbol in state.trades:
                    try:
                        await asyncio.to_thread(do_sell, state, symbol, bid, why)
                    except Exception:
                        log.exception("%s: sell failed", symbol)
        return
    until = state.cooldown_until.get(symbol)
    if until and now_utc() < until:
        return
    if strategy.entry(ask, state.levels.get(symbol)) and entries_allowed(state):
        async with state.lock:
            if symbol in state.trades or not entries_allowed(state):
                return
            state.trades[symbol] = {"entry": ask, "opened_at": now_utc(), "notional": 0, "qty": 0,
                                    "stop": -1, "take": float("inf")}   # claim slot before REST
            try:
                await asyncio.to_thread(do_buy, state, symbol, ask)
            except Exception:
                state.trades.pop(symbol, None)
                log.exception("%s: buy failed", symbol)


async def bar_task(state):
    """Recompute levels a few seconds after every 15m bar closes."""
    while True:
        now = now_utc()
        next_close = now.replace(second=0, microsecond=0) + timedelta(
            minutes=config.BAR_MINUTES - now.minute % config.BAR_MINUTES)
        await asyncio.sleep((next_close - now).total_seconds() + 5)
        try:
            await asyncio.to_thread(refresh_levels, state)
            await asyncio.to_thread(roll_day, state)
        except Exception:
            log.exception("level refresh failed")


async def heartbeat_task(state, quotes):
    while True:
        await asyncio.sleep(HEARTBEAT_S)
        parts = []
        for s in config.SYMBOLS:
            lvl, q, t = state.levels.get(s), quotes.get(s), state.trades.get(s)
            if not lvl or not q:
                parts.append(f"{s} n/a"); continue
            tag = f"IN@{t['entry']:.4f}" if t else f"{(lvl['high'] / q[1] - 1) * 100:+.2f}%"
            parts.append(f"{s} {q[1]:.4f}/{lvl['high']:.4f} {tag}")
        log.info("heartbeat  %s | open=%d day_pnl=$%.0f", " | ".join(parts), len(state.trades), state.day_pnl)


async def stream(state, quotes):
    async with websockets.connect(feed.LOCAL_URL, max_size=None) as socket:
        log.info("connected to feed %s", feed.LOCAL_URL)
        async for raw in socket:
            for item in json.loads(raw):
                if item.get("T") != "q" or item["S"] not in config.SYMBOLS:
                    continue
                symbol, bid, ask = item["S"], float(item["bp"]), float(item["ap"])
                quotes[symbol] = (bid, ask)
                await on_quote(state, symbol, bid, ask)


def adopt_positions(state):
    """Real positions found on startup (e.g. after a restart) get fresh levels."""
    held = broker.positions()
    for symbol in config.SYMBOLS:
        p = held.get(pos_key(symbol))
        lvl = state.levels.get(symbol)
        if p is None or lvl is None:
            continue
        entry = float(p.avg_entry_price)
        state.trades[symbol] = {"entry": entry, "opened_at": now_utc(), "notional": abs(float(p.market_value)),
                                "qty": float(p.qty), **strategy.plan(entry, lvl)}
        log.info("%-9s adopted open position @ %.4f", symbol, entry)


async def run():
    state, quotes = State(), {}
    roll_day(state)
    refresh_levels(state)
    adopt_positions(state)
    asyncio.create_task(bar_task(state))
    asyncio.create_task(heartbeat_task(state, quotes))
    backoff = 1
    while True:
        try:
            await stream(state, quotes)
            backoff = 1
        except Exception as exc:
            log.warning("feed dropped (%s), retrying in %ds", exc, backoff)
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 60)


def once():
    state = State()
    roll_day(state)
    refresh_levels(state)
    q = _data.get_crypto_latest_quote(CryptoLatestQuoteRequest(symbol_or_symbols=config.SYMBOLS))
    for s in config.SYMBOLS:
        lvl, ask = state.levels.get(s), float(q[s].ask_price)
        if lvl:
            log.info("%-9s ask=%.4f  %+.2f%% to donchian high  (stop would be -%.2f%%, take +%.2f%%)",
                     s, ask, (lvl["high"] / ask - 1) * 100,
                     config.STOP_ATR * lvl["atr"] / ask * 100, config.TAKE_ATR * lvl["atr"] / ask * 100)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    log.info("paper=%s dry_run=%s symbols=%s size=%.0f%% max_open=%d donchian=%dx%dm stop=%sATR take=%sATR",
             shared.PAPER, config.DRY_RUN, ",".join(config.SYMBOLS), config.POSITION_PCT * 100,
             config.MAX_OPEN, config.DONCHIAN, config.BAR_MINUTES, config.STOP_ATR, config.TAKE_ATR)
    if args.once:
        once()
        return
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        log.info("stopped")


if __name__ == "__main__":
    main()
