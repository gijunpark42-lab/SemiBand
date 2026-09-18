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
LLM_MODEL = "claude-opus-5"         # LIVE cycle + guardian only. 2026-09-11: Fable max ~10k tokens and 55 s per call; Opus max 105 s and up to 15k tokens -> the local server runs opus at HIGH effort
LLM_MODEL_RESEARCH = "claude-sonnet-5"   # any research / backtest script that calls Claude uses this (cheap, low effort), never Fable max
LLM_EFFORT = "max"                # Claude Code effort for the live Opus calls (low/medium/high/xhigh/max); handed to the local server when the
                                  # cycle starts it (LOCAL_CLAUDE_EFFORT_DEEP). 2026-09-15 (user): max for the 03:30 cycle. Measured: high 16 s /
                                  # ~1.1k output tokens per call, xhigh 18-30 s (2026-09-15), max ~100 s / ~7.5k (2026-09-11); a running server keeps
                                  # the effort it was started with, so a change applies to the next cycle that starts the server
LLM_WORKERS = 6                   # concurrent claude -p calls; also the server's slot count when the cycle starts it. 450 calls at max's ~100 s
                                  # need 6 slots to finish in ~2.1 h (3 slots: ~4.4 h, past the 06:30 PT open); each claude process is ~235 MB.
                                  # 2026-09-13 at xhigh: 41 s / call, 3 slots, ~1.7 h
LLM_TIMEOUT = 480                 # seconds a Claude call may take end to end (queue wait + the call). The local server allows
                                  # 420 s per call and its slots are shared with the earnings-ai Ask engine; on 2026-09-16 at max
                                  # effort 14 calls of 300-420 s were abandoned at the old 300 s while the server finished them
LLM_STAGE_DEADLINE = "09:05"     # ET clock time after which the cycle submits no new Claude call (the signals gathered so far are used),
                                  # so a slow server or API cannot push the Claude stage past the 09:30 ET open; None = no deadline
LLM_MAX_TICKERS = None            # None = every universe name gets the 3 Claude agents (user 2026-09-13: all 150). Before: 100 = top names by
                                  # preliminary |conviction| plus holdings. 2026-09-11: Opus HIGH measured 16 s and ~1k output
                                  # tokens per call, so 100 names x 3 agents = ~40 min with 2 workers, well inside the 03:30 -> 06:30 PT window
                                  # (Opus max was 105 s/call and would have missed the open; Fable max ~55 s and ~10k tokens)
WEB_SEARCH_TICKERS = 30           # llm_news may run a live web search (Claude's built-in WebSearch) for this many names: holdings + highest prelim |conviction|

# --- universe ---
BENCHMARK = "SOXX"                # agents are scored on return minus this
US_EXCHANGES = {"NASDAQ", "NYSE", "NYSE American", "AMEX"}
MAX_MARKET_CAP = None             # 2026-09-11 (user): cover every US-listed name in the graph, no cap. (2026-09-10 test, weekly refits: no cap 112 names +311%/1.97 vs cap 400B 96 names +373%/2.28 — re-baselined with the 151-name graph, see RESEARCH.md); no crypto ever
LOOKBACK_DAYS = 420               # calendar days of closes fetched for the technical agent (~290 trading days: the 200-day average is real live, as in the backtest; 260 gave ~178 rows so it silently fell back to the 50-day)

# --- agents in the ensemble (names match agents/<name>.py) ---
AGENTS = [
    # free, deterministic (read data, no LLM)
    "supply_chain",    # the map: generation transitions, sold-out capacity, freshness of own guidance
    "neighbors",       # the map, one hop out: are its customers/suppliers hot right now
    "fundamentals",    # growth, margins, valuation, analyst target (yfinance)
    "technical",       # 20/60-day momentum vs SOXX, trend, RSI
    "mean_reversion",  # 5-day overextension: fades what technical chases
    "events",          # earnings in the next week (risk) / just reported (drift). Its IC is negative at every horizon and sweep rounds
                       # 10-11 (2026-09-11) looked better without it, but the re-validation on a refreshed earnings-ai graph flipped the
                       # out-of-sample sign (Sharpe 0.82 -> 0.76 without it), so the effect is not robust: KEPT (RESEARCH.md)
    "risk",            # volatility and drawdown brake: speaks only when risk is elevated
    "macro",           # market regime (SOXX/SPY trend, VIX, 10y yield) expressed through each name's beta
    "customer_momentum",   # its graph customers' 21-day return vs SOXX (Cohen & Frazzini 2008). Round 44 (2026-09-17, VM, fixed replay):
                       # 2024-26 +1469% / Sharpe 2.33 / max DD 31.4% against +1031% / 2.14 / 30.1%; 2019-23 +69% / 0.36 / 46.8% against
                       # +52% / 0.29 / 41.2%. Failed the v4 consistency/drawdown limits; ADOPTED by the user's decision ("낙폭 증가해도
                       # 샤프랑 수익률 늘었으니까 하자") with the drawdown cost on record. Warm start = the _c3 replay ledger
    # Tested 2026-09-10 and NOT enabled: "momentum" (12-1m), "sue" (PEAD), "ml_ranker" (LightGBM) — each has a small
    # positive IC alone but adding them diluted convictions and cut backtest return (+373% -> +310% -> +265%).
    # The modules stay in agents/ for future re-tests; add a name here to re-enable.
    # Claude, via the local server (top LLM_MAX_TICKERS names only)
    "llm_supply",      # reads the supply-chain report: structure, deals, transitions
    "llm_guidance",    # reads the company's own latest call signals: guidance momentum
    "llm_news",        # reads three weeks of headlines: catalysts
]
SHADOW_AGENTS = ("insider",)      # agents run and recorded every cycle and scored like the others, but never voting: no feature, no
                                  # prior share, no weight, no place in the per-name breakdown. A candidate builds its live record
                                  # here; promotion needs its own pre-registered test (RESEARCH.md 2026-09-16, shadow agents)
HORIZONS = (10, 20)               # trading days after which a prediction is scored. v2.3 (2026-09-11 search, daily refits): dropping the 5-day
                                  # horizon was the biggest single gain (5-day abnormal returns are mostly noise): OOS Sharpe 0.92 -> 1.4-1.7

OPEN_REFRESH_AGENTS = ("technical", "mean_reversion", "risk", "macro", "fundamentals", "events")   # re-run right after the open on
                                  # today's first trades and replace their pre-open predictions (fundamentals re-prices P/E, P/S and
                                  # target upside). User decision 2026-09-15: signals must use the latest price. Round 27 backtests:
                                  # with labels starting at the close the signals used (score.py since 2026-09-15, warm start
                                  # backtest_orrefresh) the refresh made +895% / Sharpe 2.14 / DD 31% vs +900% / 2.14 / 30% without
                                  # it; with labels starting at the order day's close it made +712% / 1.96 / 34%. () = off
                                  # Round 31: under the order-day-open label every refresh form lost 6-7 bps/day to no refresh; only
                                  # the signal-close label in score.py makes it tie. The two are coupled: never change one alone.

# --- learning ---
WARM_START_WEIGHT = 0.5           # backtest rows (state/backtest.sqlite) count this much vs live rows in learner.fit; 0 = off
LEARNER_HALF_LIFE_DAYS = 90       # time decay of scored rows (sweep 2026-09-10: 90 beat 45 and 20 on Sharpe and return)
LEARNER_PRIOR_STRENGTH = 150.0    # lambda when walk-forward CV cannot run yet
LEARNER_LAMBDA_GRID = (150.0,)    # fixed: walk-forward CV kept picking 1000 (too timid); sweep: fixed 150 -> Sharpe 2.2-2.3 vs 1.7
LEARNER_TARGET_MODE = "beta"       # active paper model; original raw labels and comparison model remain available
# (Hedge below is kept only as a dashboard reference)
HEDGE_ETA = 0.5                   # step size: w_i *= exp(eta * gain_i)
WEIGHT_FLOOR = 0.02               # no agent is ever silenced completely (11 agents -> 22% floor mass)

# --- portfolio (long-only, margin allowed up to GROSS_TARGET) ---
CAPITAL = 1_000_000               # starting equity of the new paper account (2026-09-10); sizing uses live equity
TOP_N = 15                        # max names held
MIN_CONVICTION = 0.10             # enter only above this. 0.15 won sweep round 6 (220 days, weekly refits); the 2026-09-11 search (500 days,
                                  # daily refits, both windows) preferred 0.10 with horizons 10/20 (v2.3)
EXIT_CONVICTION = 0.04            # exit when conviction falls below this
MAX_POSITION_PCT = 0.15           # per-name cap as a share of equity (v2.3: 0.15, search gen 3; 0.10 is nearly as good)
SIZE_PER_CONVICTION = 0.60        # position = conviction x this (conviction 0.17 -> 10% = the cap); sweep round 8: 0.60/top15 +447% Sharpe 2.50 (best return)
DEMEAN_CONVICTION = True          # subtract the day's cross-sectional mean conviction (pick relative winners, less beta). Round 38 (2026-09-16):
                                  # the ridge's implicit level is a trailing-mean bias with no forecast power; demeaned 500-day replay +1110% vs
                                  # +1157% (inside noise), Sharpe 2.25 vs 2.23, max DD 24.7% vs 29.5%. Adopted 2026-09-16 (afternoon run + 09-17 cycle)
DEMEAN_GROUP = None               # round 39 candidate (2026-09-16): "chain" = demean within two graph groups: power = names whose only chain
                                  # tag is power_cooling, chip = everything else. None = one cross-sectional mean
DEMEAN_GROUP_MIN = 5              # a group with fewer names than this uses the whole mean
GRAPH_TRANSCRIPTS_ONLY = True     # the graph agents' point-in-time map skips SEC-filing rows (10-K/10-Q/8-K/20-F/6-K/40-F, third-party
                                  # notes), as the Claude agents do since 09-13. Adopted 2026-09-17 (round 41, protocol v4 on the VM: +2.3 bp/d,
                                  # t +1.5, Sharpe 2.20 vs 2.11, max DD +0.8 pts, 5/6 blocks not worse). Live from the 09-18 cycle
TECHNICAL_RESIDUAL = False        # round 40 candidate (2026-09-17, Blitz-Huij-Martens residual momentum): technical's rel20/rel60 subtract
                                  # beta x SOXX instead of SOXX (trailing 60-day pair beta, clipped to 0..3); False = plain relative return
RESEARCH_TRIALS = 350             # audit 2026-09-17: floor for the deflated Sharpe's trial count: 221 sweep variants + ~70 hand-run;
                                  # 350 after rounds 44-45 (15 more trials, 2026-09-17); raise with every round
                                  # replays before round 39 + the trials of rounds 39-43. Raise it with every round's trial count
MOMENTUM_TREND_GATE = False       # round 45 candidate: customer_momentum stays silent while SOXX is below its 50-day average (momentum
                                  # crashes come in rebounds after bear markets, Daniel & Moskowitz 2016)
MOMENTUM_VOL_SCALE = False        # round 45 candidate: customer_momentum's signal scaled by the customer basket's realised vol to a 10%
                                  # per-21-day target, multiplier clipped to 0.25..2 (Barroso & Santa-Clara 2015)
GROSS_TARGET = 1.50               # CEILING on gross exposure (150% of equity = 50% margin); not a target, cash is a position
VOL_TARGET = 0.50                 # portfolio vol targeting: when the book's trailing realised vol (annualised) exceeds this, scale every
                                  # target down by VOL_TARGET / realised (never up). Sweep rounds 10-11 + re-validation (2026-09-11, 500 days,
                                  # next-open execution, two ledger snapshots): OOS Sharpe 0.82-0.92 -> 0.96-1.27, max drawdown 36-39% -> 28-30%,
                                  # raw return lower (mostly the in-sample 2026Q2 burst); None = off (see RESEARCH.md)
VOL_LOOKBACK_DAYS = 20            # trading days of the account's own daily returns behind that realised vol (no scaling until they exist)
MIN_STOCK_BOOK = None             # e.g. 0.5: a stock book whose sized gross is below this is scaled up to it across the names that passed
                                  # the entry bar, per-name cap still applies (user 2026-09-15: be more aggressive when few names qualify)
IDLE_SLEEVE = "SOXX"              # the part of equity the stock book leaves idle goes into this ETF (IDLE_SLEEVE_FRACTION of it) while
IDLE_SLEEVE_FRACTION = 1.0        # the ETF closed above its IDLE_SLEEVE_TREND-day average (None = always); scaled with the vol target
IDLE_SLEEVE_TREND = 200           # like the book. None = off. User 2026-09-15 ("15% invested leaves money idle"); round 29, 500 days:
                                  # +1152% / Sharpe 2.26 / DD 31.8% vs +895% / 2.14 / 31.1%, 2026-05 on +19.7% vs +0.9%
                                  # 200 days (user decision 2026-09-15, round 34): over 25 years of SOXX the 50-day rule lost to
                                  # buy-and-hold (Sharpe 0.35 vs 0.55, DD 56%) and the 200-day rule matched it (0.59, DD 42%); the
                                  # 500-day replay is a tie (+1123% / 2.23 / 28.3% vs +1084% / 2.24 / 28.8% with 50 days)
HEDGE_SYMBOL = "SOXX"             # optional regime hedge (round 18, 2026-09-11): while SOXX closes below its 50-day average, short SOXX by
HEDGE_SIZE = None                 # HEDGE_SIZE x equity (capped at the long book, never net short). OFF: with the long-gross cap applied
HEDGE_LOOKBACK = 50               # correctly it is a drawdown reducer, not a return source (150 names, daily refits: +731% / 1.78 / OOS 1.88
                                  # long-only vs +675% / 1.78 / OOS 2.03, drawdown 28.8% -> 26.7%). Set 0.5-0.7 to trade drawdown for return.
COMPARE_TICKERS = ("SOXX", "SPY", "QQQ")   # benchmarks shown against the portfolio on the dashboard
MIN_ORDER_USD = 250               # ignore rebalancing dust below this
REBALANCE_BAND = 0.30             # only resize a held name when the target moved by more than 30% of it (sweep: same Sharpe, less churn)

# --- trading costs (Alpaca: $0 commission on US stocks; sells pay tiny SEC/FINRA fees; market orders pay the spread) ---
COST_BPS = 5                      # assumed round-trip cost per order in basis points (slippage + fees), used for the ledger and shown to agents

PROGRESS_UPLOAD = "final"         # backtest/sweep progress to the Blob store: 'always' (live website view, costs Blob writes + reads),
                                  # 'final' (only the finished result; watch runs locally with watch_backtest.cmd), 'never'

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
