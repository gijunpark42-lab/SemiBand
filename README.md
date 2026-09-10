# SemiBand v2 — self-weighting agent ensemble (Alpaca paper)

Eleven agents each give an opinion on every stock in the universe. The opinions are blended with
trust weights, the blend is traded in an Alpaca paper account, and every prediction is scored
5 / 10 / 20 trading days later against SOXX. Agents that were right gain weight; agents that
were wrong lose it. LLM work runs through the Claude Max subscription (`claude -p`) — no API key.
The universe is the US-listed slice of the earnings-ai supply-chain graph (market cap ≤ $400B; the backtest showed the mega-caps dilute returns).

## One cycle a day (`cycle.py`, 05:50 PT, orders at the 09:30 ET open)

1. If `state/liquidate_pending` exists, liquidate everything first (fresh start).
2. Abort if orders without our `sb2-` client-order prefix appeared in the last 24h — another bot is
   trading this account. `--force` overrides.
3. Universe (`universe.py`) → daily closes (`market.py`, yfinance).
4. Score matured predictions and update weights (`score.py`, `ensemble.hedge_update`). Everything
   lives in `state/ledger.sqlite`.
5. Run the ten agents (`agents/`), each with its own information source:
   - Free rule agents: `supply_chain` (the map: transitions, sold-out capacity, freshness, curated
     guidance wording) · `neighbors` (the map one hop out: are customers/suppliers hot) ·
     `fundamentals` (growth, margins, valuation, target) · `technical` (20/60-day momentum, trend,
     RSI) · `mean_reversion` (fade 5-day overextension; the opposite temperament of technical) ·
     `events` (earnings within 7 days = risk, reported within 14 days = drift) · `risk` (volatility
     and drawdown brake; speaks only when risk is elevated) · `macro` (SOXX/SPY trend, VIX, 10-year
     yield, FRED curve slope and NFCI → a regime score expressed through each name's beta)
   - Claude agents: `llm_supply` (the supply-chain report: structure, deals, transitions) ·
     `llm_guidance` (the company's own call statements + curated metrics: guidance momentum) ·
     `llm_news` (three weeks of headlines from Finnhub + yfinance: catalysts)
   - `moderator` does not vote; it writes agreement / disagreement / verdict / watch for every order.
6. Blend → conviction per ticker → targets (`portfolio.py`: conviction ≥ 0.15, top 15, 10% per name,
   150% gross, within buying power) → orders (`broker.py`).
7. Journal (`state/trades.json`) and dashboard (`state/dashboard.json`) are uploaded to Vercel Blob
   under `semiband-v2/`; `web/` renders them.

## Running

```
python cycle.py --dry-run --no-llm          # free agents only, no orders
python cycle.py --dry-run --tickers NVDA,AMD,MU
python cycle.py                             # the real thing: computes, waits for the open, sends paper orders
python liquidate.py --dry-run               # preview a full liquidation
python universe.py                          # refresh the universe
```

Python: `C:\Users\calif\AppData\Local\Python\bin\python.exe` with `PYTHONUTF8=1`.
If the local Claude server is down, `agents/llm.py` starts `dev\TradingAgents\local-claude\server.py`.

Scheduled task (weekdays 05:50 PT):

```
schtasks /Create /F /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 05:50 /TN SemiBand-Cycle /TR "cmd /c cd /d C:\Users\calif\Desktop\Trading && set PYTHONUTF8=1 && C:\Users\calif\AppData\Local\Python\bin\python.exe cycle.py >> state\run_daily.log 2>&1"
```

## Learning rule (Bayesian ridge stacking, `learner.py`)

Per horizon h in {5, 10, 20}: target y = abnormal return / scale_h; features x = [direction_i x confidence_i] +
[direction_i] for every agent (0 when silent); posterior mean w = (X'DX + lambda I)^-1 (X'Dy + lambda w0) with an
exponential time decay D (half-life 90 days) and prior mean w0 = the equal-weight blend. lambda is fixed at 150
pseudo-observations (the 2026-09-10 sweep showed walk-forward lambda selection was too timid). Conviction =
reliability-weighted blend of the three horizon predictions, clipped to [-1, 1]. Weights may go negative
(a reliably wrong agent becomes a contrarian signal). Hedge (multiplicative weights) is still computed as a
reference line on the dashboard. Day one is identical to the equal blend by construction.

## Backtest (`backtest.py`)

`python backtest.py --days 250` replays the point-in-time agents (technical, mean_reversion, risk, macro, events,
and time-filtered supply_chain / neighbors) day by day, scores every opinion against SOXX at 5/10/20 days, refits
the learner weekly on outcomes known at the time, and simulates the live sizing rules plus a top-15 rank portfolio.
Output: `state/backtest_report.json` (published to the dashboard) and `state/backtest.sqlite`, which warm-starts the
live learner at half weight (`WARM_START_WEIGHT`). Not simulated: fundamentals (no point-in-time data) and the Claude agents.

## Execution and the intraday guardian

- Orders: exits go out in full at the open; buys and trims are split into `EXECUTION_SLICES` (2) orders 10 minutes
  apart (09:30, 09:40 ET). The entry-time study (`timing.py`, hourly bars) showed the open beats every later hour.
  Each order is a marketable LIMIT (ask + 20 bps for buys, bid - 20 bps for sells) when a fresh IEX quote with a
  spread under 300 bps exists, otherwise a market order; unfilled limit remainders are cancelled and re-sent as
  market orders after `LIMIT_CLEANUP_MIN` minutes. Wide-spread small caps therefore never get run over by one print.
- `guardian.py` runs hourly during the session (Task Scheduler "SemiBand-Guardian", 07:35–13:05 PT). For each
  holding it pulls today's headlines (Finnhub + DuckDuckGo), and only when there are NEW titles asks Claude whether
  they describe a material adverse event. It exits only on action=exit with severity ≥ `GUARDIAN_EXIT_SEVERITY`
  (0.7), records the exit in `state/guardian_exits.json`, and the daily cycle will not rebuy that name for
  `GUARDIAN_COOLDOWN_DAYS` (3). It never buys. Checks appear on the dashboard under Guardian.
- Backtests showed price-based stop-losses (6–20% below entry) reduced both return and Sharpe, so there is no
  price stop; the guardian reacts to news, not to price.

## Rules

- Never write into earnings-ai (`chains/`, `graph/`, `company_metrics.json`). Read only.
- `config.PAPER = True`. There is no live-account switch.
- Output is paper-trading research, not investment advice.
- The user runs git commits and pushes unless they say otherwise.

## Web

`web/` is a Next.js app deployed on Vercel (project `semiband`, Root Directory `web`).
Env: `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `TRADES_URL`, `BLOB_READ_WRITE_TOKEN`. Deploy with
`vercel --prod` from the repo root. All code and UI text are in English.
