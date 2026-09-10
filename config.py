"""Central settings for SemiBand v2 — the self-weighting agent ensemble.

Secrets stay in .env (ALPACA_API_KEY, ALPACA_SECRET_KEY, BLOB_READ_WRITE_TOKEN).
Everything below is a deliberate knob; change it here, not inside the modules.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
if not API_KEY or not SECRET_KEY:
    raise RuntimeError("Missing ALPACA_API_KEY / ALPACA_SECRET_KEY in .env")

PAPER = True                      # never flip this without a deliberate decision
DRY_RUN = False                   # True = log intended orders, send nothing

# --- where things live ---
STATE_DIR = ROOT / "state"        # ledger.sqlite, weights, caches, logs, dashboard.json
EARNINGS_AI_DIR = Path(os.getenv("EARNINGS_AI_DIR", "C:/Users/calif/Desktop/earnings-ai"))
TRADINGAGENTS_DIR = Path(os.getenv("TRADINGAGENTS_DIR", "C:/Users/calif/dev/TradingAgents"))

# --- LLM: the local Claude server (Claude Max subscription, no API key) ---
LLM_URL = os.getenv("LOCAL_CLAUDE_URL", "http://127.0.0.1:8765/v1")
LLM_MODEL = "claude-sonnet-5"
LLM_WORKERS = 2                   # concurrent claude -p calls (server allows 2)
LLM_MAX_TICKERS = 100             # user 2026-09-10: all agents on the whole universe (returns & accuracy first); lower to save subscription budget

# --- universe ---
BENCHMARK = "SOXX"                # agents are scored on return minus this
US_EXCHANGES = {"NASDAQ", "NYSE", "NYSE American", "AMEX"}
MAX_MARKET_CAP = 400e9            # user rule (2026-09-09): trade names under $400B market cap only; no crypto ever
LOOKBACK_DAYS = 260               # calendar days of closes fetched for the technical agent

# --- agents in the ensemble (names match agents/<name>.py) ---
AGENTS = [
    # free, deterministic (read data, no LLM)
    "supply_chain",    # the map: generation transitions, sold-out capacity, freshness of own guidance
    "neighbors",       # the map, one hop out: are its customers/suppliers hot right now
    "fundamentals",    # growth, margins, valuation, analyst target (yfinance)
    "technical",       # 20/60-day momentum vs SOXX, trend, RSI
    "mean_reversion",  # 5-day overextension: fades what technical chases
    "events",          # earnings in the next week (risk) / just reported (drift)
    "risk",            # volatility and drawdown brake: speaks only when risk is elevated
    "macro",           # market regime (SOXX/SPY trend, VIX, 10y yield) expressed through each name's beta
    # Claude, via the local server (top LLM_MAX_TICKERS names only)
    "llm_supply",      # reads the supply-chain report: structure, deals, transitions
    "llm_guidance",    # reads the company's own latest call signals: guidance momentum
    "llm_news",        # reads three weeks of headlines: catalysts
]
HORIZONS = (5, 10, 20)            # trading days after which a prediction is scored

# --- learning (multiplicative weights / Hedge) ---
HEDGE_ETA = 0.5                   # step size: w_i *= exp(eta * gain_i)
WEIGHT_FLOOR = 0.02               # no agent is ever silenced completely (11 agents -> 22% floor mass)

# --- portfolio (long-only, margin allowed up to GROSS_TARGET) ---
CAPITAL = 1_000_000               # starting equity of the new paper account (2026-09-10); sizing uses live equity
TOP_N = 15                        # max names held
MIN_CONVICTION = 0.10             # enter only above this (stacking model: silent agents count as 0, so convictions run lower than the old speaker-mean)
EXIT_CONVICTION = 0.04            # exit when conviction falls below this
MAX_POSITION_PCT = 0.10           # per-name cap as a share of equity
SIZE_PER_CONVICTION = 0.30        # position = conviction x this (conviction 0.33 -> 10% = the cap); weak convictions stay small
GROSS_TARGET = 1.50               # CEILING on gross exposure (150% of equity = 50% margin); not a target, cash is a position
COMPARE_TICKERS = ("SOXX", "SPY", "QQQ")   # benchmarks shown against the portfolio on the dashboard
MIN_ORDER_USD = 250               # ignore rebalancing dust below this
REBALANCE_BAND = 0.15             # only resize a held name when the target moved by more than 15% of it (limits churn)

# --- trading costs (Alpaca: $0 commission on US stocks; sells pay tiny SEC/FINRA fees; market orders pay the spread) ---
COST_BPS = 5                      # assumed round-trip cost per order in basis points (slippage + fees), used for the ledger and shown to agents

ORDER_PREFIX = "sb2-"             # client_order_id prefix: how we tell our orders from foreign ones
