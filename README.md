# SemiBand v2 — self-weighting agent ensemble (Alpaca paper)

Ten agents each give an opinion on every stock in the universe. The opinions are blended with
trust weights, the blend is traded in an Alpaca paper account, and every prediction is scored
5 / 10 / 20 trading days later against SOXX. Agents that were right gain weight; agents that
were wrong lose it. LLM work runs through the Claude Max subscription (`claude -p`) — no API key.
The universe is the US-listed slice of the earnings-ai supply-chain graph (market cap ≤ $400B).

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
     and drawdown brake; speaks only when risk is elevated)
   - Claude agents: `llm_supply` (the supply-chain report: structure, deals, transitions) ·
     `llm_guidance` (the company's own call statements + curated metrics: guidance momentum) ·
     `llm_news` (three weeks of headlines: catalysts)
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

## Learning rule (Hedge)

Per scoring round, agent i's gain = mean over its newly scored predictions of
`direction × confidence × abnormal_return × 20`, clipped to [-1, 1].
`w_i ← w_i · exp(0.5 · gain_i)`, renormalised, floor 2%. All ten start at 10%.

## Rules

- Never write into earnings-ai (`chains/`, `graph/`, `company_metrics.json`). Read only.
- `config.PAPER = True`. There is no live-account switch.
- Output is paper-trading research, not investment advice.
- The user runs git commits and pushes unless they say otherwise.

## Web

`web/` is a Next.js app deployed on Vercel (project `semiband`, Root Directory `web`).
Env: `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `TRADES_URL`, `BLOB_READ_WRITE_TOKEN`. Deploy with
`vercel --prod` from the repo root. All code and UI text are in English.
