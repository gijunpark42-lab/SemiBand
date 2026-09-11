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
WEB_SEARCH_TICKERS = 30           # llm_news may run a live web search (Claude's built-in WebSearch) for this many names: holdings + highest prelim |conviction|

# --- universe ---
BENCHMARK = "SOXX"                # agents are scored on return minus this
US_EXCHANGES = {"NASDAQ", "NYSE", "NYSE American", "AMEX"}
MAX_MARKET_CAP = 400e9            # backtest 2026-09-10: no cap (112 names) +311%/Sharpe 1.97 vs cap 400B (96 names) +373%/2.28 -> keep the cap; no crypto ever
LOOKBACK_DAYS = 260               # calendar days of closes fetched for the technical agent

# --- agents in the ensemble (names match agents/<name>.py) ---
AGENTS = [
    # free, deterministic (read data, no LLM)
    "supply_chain",    # the map: generation transitions, sold-out capacity, freshness of own guidance
    "neighbors",       # the map, one hop out: are its customers/suppliers hot right now
    "fundamentals",    # growth, margins, valuation, analyst target (yfinance)
    "technical",       # 20/60-day momentum vs SOXX, trend, RSI
    "mean_reversion",  # 5-day overextension: fades what technical chases
    # "events" (earnings within 7 days = risk / reported within 14 days = drift) was REMOVED 2026-09-11: negative IC at every
    # horizon and sweep rounds 10-11 (500 days, next-open execution) were better without it in both windows (OOS Sharpe 1.27 -> 1.40
    # with vol targeting). The module stays in agents/ and the backtest still records its opinions for future re-tests.
    "risk",            # volatility and drawdown brake: speaks only when risk is elevated
    "macro",           # market regime (SOXX/SPY trend, VIX, 10y yield) expressed through each name's beta
    # Tested 2026-09-10 and NOT enabled: "momentum" (12-1m), "sue" (PEAD), "ml_ranker" (LightGBM) — each has a small
    # positive IC alone but adding them diluted convictions and cut backtest return (+373% -> +310% -> +265%).
    # The modules stay in agents/ for future re-tests; add a name here to re-enable.
    # Claude, via the local server (top LLM_MAX_TICKERS names only)
    "llm_supply",      # reads the supply-chain report: structure, deals, transitions
    "llm_guidance",    # reads the company's own latest call signals: guidance momentum
    "llm_news",        # reads three weeks of headlines: catalysts
]
HORIZONS = (5, 10, 20)            # trading days after which a prediction is scored

# --- learning ---
WARM_START_WEIGHT = 0.5           # backtest rows (state/backtest.sqlite) count this much vs live rows in learner.fit; 0 = off
LEARNER_HALF_LIFE_DAYS = 90       # time decay of scored rows (sweep 2026-09-10: 90 beat 45 and 20 on Sharpe and return)
LEARNER_PRIOR_STRENGTH = 150.0    # lambda when walk-forward CV cannot run yet
LEARNER_LAMBDA_GRID = (150.0,)    # fixed: walk-forward CV kept picking 1000 (too timid); sweep: fixed 150 -> Sharpe 2.2-2.3 vs 1.7
# (Hedge below is kept only as a dashboard reference)
HEDGE_ETA = 0.5                   # step size: w_i *= exp(eta * gain_i)
WEIGHT_FLOOR = 0.02               # no agent is ever silenced completely (11 agents -> 22% floor mass)

# --- portfolio (long-only, margin allowed up to GROSS_TARGET) ---
CAPITAL = 1_000_000               # starting equity of the new paper account (2026-09-10); sizing uses live equity
TOP_N = 15                        # max names held
MIN_CONVICTION = 0.15             # enter only above this (sweep round 6: 0.15 beat 0.10 and 0.20 on return and Sharpe)
EXIT_CONVICTION = 0.04            # exit when conviction falls below this
MAX_POSITION_PCT = 0.10           # per-name cap as a share of equity
SIZE_PER_CONVICTION = 0.60        # position = conviction x this (conviction 0.17 -> 10% = the cap); sweep round 8: 0.60/top15 +447% Sharpe 2.50 (best return)
DEMEAN_CONVICTION = False         # subtract the day's cross-sectional mean conviction (pick relative winners, less beta)
GROSS_TARGET = 1.50               # CEILING on gross exposure (150% of equity = 50% margin); not a target, cash is a position
VOL_TARGET = 0.50                 # portfolio vol targeting: when the book's trailing realised vol (annualised) exceeds this, scale every
                                  # target down by VOL_TARGET / realised (never up). Sweep round 10 (2026-09-11, 500 days, next-open execution):
                                  # OOS Sharpe 0.92 -> 1.27, full-window Sharpe 1.63 -> 1.91, max drawdown 39% -> 30%; None = off (see RESEARCH.md)
VOL_LOOKBACK_DAYS = 20            # trading days of the account's own daily returns behind that realised vol (no scaling until they exist)
COMPARE_TICKERS = ("SOXX", "SPY", "QQQ")   # benchmarks shown against the portfolio on the dashboard
MIN_ORDER_USD = 250               # ignore rebalancing dust below this
REBALANCE_BAND = 0.30             # only resize a held name when the target moved by more than 30% of it (sweep: same Sharpe, less churn)

# --- trading costs (Alpaca: $0 commission on US stocks; sells pay tiny SEC/FINRA fees; market orders pay the spread) ---
COST_BPS = 5                      # assumed round-trip cost per order in basis points (slippage + fees), used for the ledger and shown to agents

ORDER_PREFIX = "sb2-"             # client_order_id prefix: how we tell our orders from foreign ones

# --- execution: spread each day's buys/trims over the first hour instead of one market order at the bell ---
EXECUTION_SLICES = 2              # 2 slices -> 09:30 and 09:40 ET; the entry-time study (timing.py, 2026-09-10) showed the open beats every later hour
EXECUTION_INTERVAL_MIN = 10
LIMIT_COLLAR_BPS = 20             # buys/sells go as MARKETABLE LIMIT orders: ask x (1 + 20 bps) / bid x (1 - 20 bps); fills like a market order but cannot be run over by a wild print
MAX_SPREAD_BPS_FOR_LIMIT = 300    # if the quoted spread is wider than this (or the quote is stale/missing) fall back to a plain market order
LIMIT_CLEANUP_MIN = 8             # unfilled limit remainders are cancelled and re-sent as market orders after this many minutes

# --- intraday guardian (guardian.py, hourly during the session) ---
GUARDIAN_EXIT_SEVERITY = 0.7      # exit a holding only when Claude rates a NEW headline as material and this severe
GUARDIAN_COOLDOWN_DAYS = 3        # the daily cycle will not rebuy a name the guardian exited within this many days
