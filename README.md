# SemiBand v2

A daily trading system for the AI semiconductor supply chain. Twelve agents score every stock in the
universe, a Bayesian ridge learner re-weights each agent by how well its past calls scored, and the blend
trades a paper account once a day. Every research decision is written down before the run that tests it,
and the log of what was tried and rejected is in [RESEARCH.md](RESEARCH.md).

Live dashboard: [semiband-dashboard.vercel.app](https://semiband-dashboard.vercel.app)
Paper trading only. `config.PAPER = True` and there is no live-account switch.

## What it trades

The universe is every US-listed, Alpaca-tradable company in the [earnings-ai](https://gijun42.com)
supply-chain graph: 176 names as of 2026-09-18, from chip designers and foundries through packaging,
optics and memory to the power and cooling companies that feed the data centres. The list is rebuilt from
the graph at the start of every cycle, so a company added to the graph joins the universe the next day.

## The agents

Nine of them read data and follow fixed rules:

| Agent | What it reads |
|---|---|
| `supply_chain` | dated statements from the graph: transitions, sold-out capacity, guidance wording |
| `neighbors` | the same statements one hop out: are this name's customers and suppliers busy |
| `customer_momentum` | the 21-day return of a name's graph customers against SOXX (Cohen & Frazzini 2008) |
| `fundamentals` | growth, margins, valuation, analyst targets |
| `technical` | 20/60-day momentum against SOXX, trend, RSI |
| `mean_reversion` | 5-day overextension, the opposite temperament of `technical` |
| `events` | earnings inside a week (risk) or just reported (drift) |
| `risk` | volatility and drawdown, speaks only when risk is elevated |
| `macro` | SOXX and SPY trend, VIX, the 10-year yield, FRED curve and NFCI, expressed through each name's beta |

Three read text with Claude, one call per stock per agent through a local server on the Max subscription:
`llm_supply` (the supply-chain report), `llm_guidance` (the company's own call statements) and `llm_news`
(three weeks of headlines). A `moderator` writes the minutes for each order and casts no vote.

Shadow agents run and are scored every day but never vote. `insider` (opportunistic Form 4 purchases) is
the current one. A shadow becomes a voting candidate only through its own pre-registered replay.

## How a day runs

The scheduled cycle (`cycle.py`) starts at 03:30 PT and trades at the 09:30 ET open. From 2026-09-21 it
starts at 11:30 PT and trades in the closing auction instead, which the backtest and the live fills both
preferred.

1. Refresh the graph snapshot and the universe, download closes.
2. Score the predictions that matured today and refit the stacking model on everything known at the time.
3. Run the agents. The Claude stage has a wall-clock deadline so a slow server cannot push the run past
   the execution window.
4. Blend the opinions into one conviction per stock, subtract the day's cross-sectional mean, and size:
   enter above 0.10 conviction, 0.60 of equity per unit of conviction, 15% per name, 150% gross ceiling,
   scaled down when the book's own 20-day volatility runs above 50% annualised. Idle equity sits in SOXX
   while SOXX is above its 200-day average, and a trend-gated beta floor holds the book's beta to SOXX at
   0.5 so a rally is not missed by a defensive book.
5. Send the orders, write the journal and publish the dashboard.

`guardian.py` runs hourly during the session, reads today's headlines for each holding, and exits a
position only on a material adverse event. It never buys. Price stop-losses were tested and cut both
return and Sharpe, so there are none.

## Results

The replay is point-in-time: agents see only what existed on the simulated day, the learner refits daily
on scored outcomes, holdings drift with their own returns, and every run charges 5 bps per dollar traded
plus 7% annual interest on gross above 1.0.

Over 500 sessions from 2024-10 to 2026-08, the live configuration returned **+1,028% at Sharpe 2.14** with
a 30.1% maximum drawdown. Three comparisons matter more than the headline:

| Line | Return |
|---|---|
| the book | +1,028% |
| the same stocks held equal weight | +245% |
| SOXX | +152% |
| the book at 15 bps of cost | +893% |
| the book at 30 bps | +656% |

The universe is today's graph membership, so the equal-weight line is the honest benchmark rather than
SOXX. Selecting the best of 330 tested variants would reach Sharpe 1.46 by luck alone; the observed 2.14
clears that at 82% probability (deflated Sharpe, Bailey & López de Prado 2014). On an independent
2019-2023 window the price agents made +53% against +160% for the same names held equal weight, so the
edge measured here belongs to the 2024-2026 regime and to information the older window cannot contain.
Live expectations were set near Sharpe 1 before trading started.

## How research is run

Every change is pre-registered in [RESEARCH.md](RESEARCH.md) before the run that tests it: the hypothesis,
the exact flags, the pass number. Protocol v4.1 then decides:

- the paired daily difference against a same-day, same-machine baseline is at least zero,
- Sharpe is not lower and maximum drawdown is within 2 points,
- the paired difference is at least zero in two thirds of the informative blocks (six purged blocks, ties
  excluded; a change that can act on only part of the window is also scored on those days alone),
- an independent 2019-2023 window confirms anything that passes.

51 rounds have run this way. Six changes were adopted and more than forty were rejected, including several
that looked good on one window: stop-losses, a short book, a hedge overlay, regime gates, residual
momentum, a sector-momentum vote, weekly rebalancing, and stronger shrinkage that the cross-validation
itself preferred. `config.RESEARCH_TRIALS` (384) carries the trial count into the deflated Sharpe, so the
bar rises with every experiment.

`paper_twins.py` records counterfactual books from the same signals every day (the previous execution
rule, no beta floor, the other confidence rule, the raw-return target) and marks them at official prices
with the replay's cost model, so each live change carries its own control without a second account.

An audit runs weekly and before any adoption: look-ahead, leakage, ignored costs, arithmetic. It has
found real defects, including free daily rebalancing worth 7-9% a year, a FRED look-ahead, a wrong trial
count in the deflated Sharpe, and an undercharged rank book. They are fixed and recorded.

## Running it

```
python cycle.py --dry-run --no-llm          # rule agents only, no orders
python cycle.py                             # the real thing: computes, waits, sends paper orders
python backtest.py --days 500 --exec close  # a replay; --exec open for the old execution
python slippage.py --days 14                # what the live fills actually cost
python liquidate.py --dry-run               # preview a full liquidation
```

Python 3.13 with `PYTHONUTF8=1`. Secrets live in `.env` (`ALPACA_API_KEY`, `ALPACA_SECRET_KEY`,
`BLOB_READ_WRITE_TOKEN`); `state/` holds the ledger, models and caches and is not tracked.

Tests:

```
set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest discover -s . -p "test_*.py"
```

## The learning rule

For each horizon h in {10, 20} trading days, the target is the stock's return minus its prediction-time
60-day beta times SOXX's, divided by a scale. The features are `direction x confidence` and `direction`
for every agent, zero when an agent is silent. The posterior mean is a ridge with an exponential time
decay (90-day half-life) around a prior of the equal-weight blend, worth 150 pseudo-observations. Weights
may go negative, which makes a reliably wrong agent a contrarian signal, and several are negative today.
Conviction is the reliability-weighted blend of the horizons, clipped to [-1, 1].

Two labels are stored side by side (raw abnormal return and beta-adjusted). The inactive one is fitted in
parallel and its intended book is recorded for comparison, so switching targets is a measurement rather
than a guess.

## Web

`web/` is a Next.js app on Vercel. `/` shows the paper account, the day's decisions and the agent
scoreboard; `/backtest` shows the latest replay and the research log.

## Caveats

- Paper trading, not investment advice.
- The universe is today's graph membership, which is survivorship by construction. The equal-weight line
  is reported next to every result for that reason.
- The graph's dated statements start in 2025-10, so the graph agents are silent for the first year of any
  long replay.
- The three Claude agents cannot be replayed honestly: the models' training data covers the test window.
  Their evidence is the live scoreboard alone.
- Never write into the earnings-ai project. This repository reads its graph.
