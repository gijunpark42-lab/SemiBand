"""Crypto bot settings. Shares .env / broker / journal with the stock bot."""

SYMBOLS = ["BTC/USD", "ETH/USD", "SOL/USD"]

# --- strategy: volatility breakout (Larry Williams) ---
# Day = 00:00 UTC (Alpaca crypto daily bars are UTC-aligned).
#   target = today's open + K x (yesterday's high - yesterday's low)
#   price >= target and flat            -> BUY  (once per symbol per day)
#   day rolls over                      -> close everything at the new open
K = 0.5

# --- execution ---
DRY_RUN = True                   # True = log intended orders, send nothing
POSITION_PCT = 0.10              # each entry = this share of account equity
MAX_TOTAL_EXPOSURE_USD = 30_000  # crypto-only cap, separate from the stock bot
# quotes arrive over the websocket; no polling interval
