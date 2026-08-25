"""Intraday crypto bot settings (Donchian breakout + ATR exits).

Runs beside crypto_run.py on DIFFERENT coins on purpose: Alpaca keeps one
position per symbol, so two bots on the same coin would fight over exits.
"""

SYMBOLS = ["XRP/USD", "DOGE/USD", "AVAX/USD"]

# --- bars & signal ---
BAR_MINUTES = 15
DONCHIAN = 20                    # entry when the ask breaks the high of the last 20 completed bars
ATR_PERIOD = 14
STOP_ATR = 1.0                   # stop  = entry - 1.0 x ATR
TAKE_ATR = 2.0                   # take  = entry + 2.0 x ATR
MAX_HOLD_MINUTES = 240           # time stop
REENTRY_COOLDOWN_MINUTES = 30    # after any exit, no new entry on that coin for this long

# --- sizing & risk ---
DRY_RUN = True
POSITION_PCT = 0.04              # 4% of equity per trade
MAX_OPEN = 3                     # concurrent positions
DAILY_LOSS_LIMIT_PCT = 0.015     # realized loss today >= 1.5% of equity -> no new entries until next UTC day
MAX_CONSEC_STOPS = 3             # this many stop-outs in a row -> pause
PAUSE_MINUTES = 240
