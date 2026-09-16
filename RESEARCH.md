# Research log — what was tried, what it did, what was decided

Every idea that touched the strategy, with its test and verdict, so nothing gets re-tested by accident and
nothing gets adopted on one good window. Newest at the bottom. Raw results: `state/backtest_sweep*.json`,
`state/backtest_report*.json` (not in git; the numbers that matter are copied here).

## Evaluation protocol (since 2026-09-11)

- **Two windows.** `python backtest.py --days 500 --exec open --tag _open500` covers 2024-09 → 2026-08.
  The last 220 days (2025-09-24 → 2026-08-10) are the window every sizing knob was tuned on: **in-sample**.
  The first 250 days (2024-09-24 → 2025-09-23) never saw a sweep: **out-of-sample (OOS)**.
- **Execution.** Judge with `--exec open` (buy at the next open, mark open-to-open — what the live cycle does).
- **Adopt a change only if** OOS Sharpe improves AND full-window Sharpe does not fall AND the full-window
  score (Sharpe + 0.5 × excess vs SOXX − 0.5 × turnover/day) does not fall. One knob at a time.
- **Always read** `robustness`: bootstrap Sharpe CI, deflated Sharpe (number of trials on record), best-quarter
  share, cost sensitivity; and the round's PBO from `sweep.py`.
- **Never** re-sweep the 220-day window alone, never add/remove an agent on it alone.

## 2026-09-10 — rounds 1-9 (all on the 220-day window, close execution: in-sample by today's standard)

| Round | Question | Result | Decision |
|---|---|---|---|
| 1 (80 variants) | learner on/off, half-life, horizons, sizing grid | learning beats no-learning; half-life 90 best; technical-only has high Sharpe but low return | half-life 90 |
| 2 | lambda (20/50/150/400), sizing combos | fixed λ=150 Sharpe 2.23 vs walk-forward CV picking 1000 (too timid) | λ fixed 150 |
| 3 | λ150 × size_k × cap | size 0.45, cap 0.10, band 0.30 → +386% Sharpe 2.34 | adopted |
| 4 | price stop-losses 6-20%, cooldown | every stop reduced return AND Sharpe | no price stop; guardian reacts to news only |
| 5 | per-name vol scaling, rebalance every 2-3 days, top 10/20, min conviction | min conviction 0.15 best (Sharpe 2.45); vol scaling and slower cadence worse | min conviction 0.15 |
| 6 | 0.15 combos | size 0.60 → +447% Sharpe 2.50 | size 0.60 (v2.1) |
| 7 | momentum (12-1m), SUE, ML ranker agents | each has small positive IC alone but dilutes convictions: +373% → +310% → +265% | agents kept in `agents/`, disabled |
| 8 | top 15/20, band 0.3/0.5, swap margin (TopkDropout) | top 15 band 0.3 best; seat protection worse | v2.1 frozen |
| 9 | short book (5-10 names), SOXX hedge below 50-day | every short / hedge variant lower return, same or lower Sharpe | long-only |
| — | customer read-through in the neighbors score | +447% → +335% | kept in the LLM report only |
| — | entry hour (hourly bars) | the open beats every later hour | orders at 09:30 / 09:40 ET |
| — | market-cap cap 400B vs none | no cap +311% / 1.97 vs cap +373% / 2.28 | cap kept |

Warning about these rounds: 163 variants on one window. Deflated Sharpe of the winner on that window = 0.78
(open execution) / 0.83 (close); PBO of the quick round (9 variants, CSCV) = 0.73. The window's Sharpe 2.5 is
not a number to expect live.

## 2026-09-11 — honesty checks (no strategy change)

| Check | Result | Consequence |
|---|---|---|
| next-open execution vs signal-day close, 220 days | +447% / 2.49 (close) vs +456% / 2.31 (open) | the return is not a close-to-close artefact; execution mode is not the problem |
| 500 days, open execution, OOS vs IS | OOS +94% (SOXX +18%) Sharpe 0.91 DD 38.6% · IS +461% (SOXX +110%) Sharpe 2.35 | expect ~1 Sharpe, not 2.5; both windows beat SOXX by a lot |
| learner vs equal prior, IC only | 500d IC learned 0.018 vs equal 0.020 | misleading in isolation — see round 10 `no_learning` |
| best quarter's share of log return | 44% (500d), 61% (220d); 2026Q2 = +188% | one burst dominates the tuning window |
| cost sensitivity, 500d | 0 bps +1094% / 1.69 · 5 bps +988% / 1.63 · 15 bps +802% / 1.50 · 30 bps +582% / 1.31 | edge survives realistic small-cap costs; turnover 40%/day is the biggest lever on return |
| bootstrap Sharpe 95% CI, 500d | 0.44 to 3.03 | wide; two years is not enough to pin Sharpe within ±1 |

## 2026-09-11 — round 10 (500 days, open execution, OOS = before 2025-09-24)

Base `v21` = λ150, min conviction 0.15, size 0.60, top 15, band 0.30. Command:
`python sweep.py --round10 --tag _open500 --exec open --oos-end 2025-09-24`

Full window = 470 traded days (2024-09-24 → 2026-08-10). OOS = the first 250 of them. PBO of the round = 0.47.

| Variant | Return | Sharpe | Max DD | Turnover/day | OOS return | OOS Sharpe | OOS DD | Verdict |
|---|---|---|---|---|---|---|---|---|
| **v21** (base) | +984% | 1.63 | 38.6% | 40% | +94% | 0.92 | 38.6% | reference |
| no_learning | +59% | 0.64 | 37.2% | 18% | +2% | 0.26 | 5.2% | **rejected** — the equal prior gives tiny convictions, few names pass 0.15, gross 28%. The learner's value is conviction *scale*, not just ranking (its IC alone had hidden this) |
| lam400 | +755% | 1.61 | 34.4% | 38% | +47% | 0.62 | 32.4% | rejected — OOS worse |
| lam1000 | +475% | 1.62 | 31.4% | 34% | +57% | 1.22 | 21.6% | rejected — OOS Sharpe up but half the return in both windows, full Sharpe flat |
| voltarget 0.30 | +485% | 2.01 | 22.4% | 27% | +93% | 1.46 | 22.4% | Sharpe-first option |
| voltarget 0.40 | +540% | 1.85 | 26.5% | 30% | +85% | 1.20 | 26.5% | — |
| **voltarget 0.50** | +730% | 1.91 | 30.1% | 33% | +102% | 1.27 | 30.1% | **adopted** — OOS better on return, Sharpe and drawdown; only the in-sample 2026Q2 burst is smaller |
| ewma 2 / 3 / 5 | +615% / +739% / +771% | 1.36 / 1.47 / 1.47 | ~38% | 19% / 15% / 12% | +71% / +98% / +96% | 0.75 / 0.98 / 0.95 | 32-34% | rejected — turnover falls 3x but Sharpe falls; at 5 bps the churn is cheaper than the lag |
| ewma3 + vt0.40 | +424% | 1.67 | 25.5% | 12% | +64% | 1.01 | 25.5% | rejected |
| k0.45 | +738% | 1.59 | 38.1% | 35% | +87% | 0.91 | 38.1% | rejected — 0.60 stays |
| cap 0.15 | +1116% | 1.68 | 38.3% | 40% | +98% | 0.95 | 38.3% | candidate — slightly better in both windows (round 11) |
| top 20 | +879% | 1.63 | 38.2% | 38% | +86% | 0.92 | 38.2% | rejected |
| horizons 10/20 (drop 5d) | +1192% | 1.71 | 37.0% | 41% | +98% | 0.94 | 37.0% | candidate — better in both windows (round 11) |
| drop supply_chain | +749% | 1.37 | 38.6% | 42% | +94% | 0.92 | 38.6% | keep the agent |
| drop neighbors | +676% | 1.49 | 35.6% | 34% | +73% | 0.87 | 35.4% | keep (its IC is negative but the learner uses it as a contrarian input) |
| drop technical | +313% | 1.22 | 37.8% | 30% | +115% | 1.26 | 37.2% | keep — it is the return engine in-sample; interesting that OOS improves without it |
| drop mean_reversion | +693% | 1.32 | 40.2% | 34% | +90% | 0.87 | 40.2% | keep |
| drop events | +1106% | 1.70 | 38.6% | 39% | +111% | 1.03 | 38.6% | candidate — better in both windows; its IC is negative at every horizon (round 11) |
| drop risk | +371% | 1.41 | 37.9% | 37% | +83% | 0.96 | 37.9% | keep |
| drop macro | +603% | 1.55 | 36.7% | 29% | +74% | 0.95 | 32.1% | keep |

Note: the `drop_*` rows silence the agent but keep it in the roster (prior 1/7). Round 11 changes the roster itself
(prior 1/6), which is what removing it from `config.AGENTS` does live.

## 2026-09-11 — round 11: the round-10 winners combined (same window, same execution)

`python sweep.py --round11 --tag _open500 --exec open --oos-end 2025-09-24`

Here `noevents` removes the agent from the roster (prior 1/6). PBO of the round = 0.375.

| Variant | Return | Sharpe | Max DD | Turnover/day | OOS return | OOS Sharpe | OOS DD | Verdict |
|---|---|---|---|---|---|---|---|---|
| v21 | +984% | 1.63 | 38.6% | 40% | +94% | 0.92 | 38.6% | reference |
| vt50 | +730% | 1.91 | 30.1% | 33% | +102% | 1.27 | 30.1% | good |
| vt50 + h10_20 | +733% | 1.88 | 31.0% | 33% | +89% | 1.14 | 31.0% | rejected — the horizon change does not survive on top of vol targeting |
| **vt50 + no events** | +840% | 2.02 | 29.6% | 32% | +118% | 1.40 | 29.6% | **adopted (v2.2)** — best OOS on every metric, best full-window Sharpe and drawdown |
| vt50 + cap 0.15 | +746% | 1.89 | 30.1% | 32% | +101% | 1.25 | 30.1% | rejected — no gain over vt50 |
| vt50 + no events + h10_20 | +717% | 1.85 | 33.2% | 34% | +85% | 1.09 | 33.2% | rejected |
| vt50 + no events + h10_20 + cap 0.15 | +704% | 1.83 | 32.2% | 33% | +91% | 1.15 | 32.2% | rejected |
| no events + h10_20 + cap 0.15 (no vol target) | +1259% | 1.73 | 37.2% | 41% | +116% | 1.08 | 37.2% | highest raw return, but 37% drawdown and OOS Sharpe 1.08 vs 1.40 |
| vt40 + no events + h10_20 | +580% | 1.87 | 28.5% | 31% | +86% | 1.20 | 28.5% | rejected |
| vt60 + no events + h10_20 | +921% | 1.90 | 34.6% | 35% | +99% | 1.14 | 34.6% | rejected |

Provisional decision after round 11: vol target 0.50 + events removed. The confirmation run below overturned half of it.

## 2026-09-11 — confirmation run, and a lesson about the data

`python backtest.py --days 500 --exec open --tag _v22` (vol target 0.50, events removed) came back at **+531% / Sharpe
1.66 / OOS Sharpe 0.85**, not the +840% / 2.02 / 1.40 of the sweep. The engines agree exactly (replaying the new ledger
through `sweep.py` with band 0 reproduces +531%); the **ledgers differ**: between the morning's `_open500` run and this one,
the earnings-ai graph on disk had been updated (8,065 opinions changed on the same dates, mostly `neighbors` confidence
0.65 → 0.70 and `supply_chain`; 4,300 extra rows), and the price window moved by one day. Same rules, fresh inputs:

| Variant (fresh ledger, band 0.30) | Return | Sharpe | Max DD | OOS return | OOS Sharpe | OOS DD | IS Sharpe |
|---|---|---|---|---|---|---|---|
| v21 | +803% | 1.50 | 36.1% | +83% | 0.82 | 35.3% | 2.18 |
| vt50 | +521% | 1.63 | 27.7% | +74% | 0.96 | 27.7% | 2.34 |
| no events | +897% | 1.57 | 35.9% | +75% | **0.76** | 35.9% | 2.40 |
| vt50 + no events | +573% | 1.71 | 28.1% | +68% | 0.91 | 28.1% | 2.55 |
| vt40 + no events | +431% | 1.66 | 25.8% | +58% | 0.87 | 25.8% | 2.52 |

- **Vol targeting holds**: on both ledgers and in both windows it raises Sharpe (+0.13 to +0.28) and cuts the drawdown
  (36 → 28%), at the cost of raw return (mostly the in-sample 2026Q2 burst, which is the number we trust least).
- **Removing events does not hold**: it helped OOS on the old ledger (0.92 → 1.03) and hurt OOS on the fresh one
  (0.82 → 0.76). A change whose sign depends on which snapshot of the graph you ran is noise → **events stays**.
- **Lesson**: one run of this strategy carries roughly ±20% return / ±0.15 Sharpe of input noise (graph version, a one-day
  window shift). Anything smaller than that is not a result. The supply-chain graph is also not point-in-time in its
  structure (edges and confidences are today's), which the caveats already say and this episode made concrete.

**Final decision (v2.2, 2026-09-11):** `VOL_TARGET = 0.50` only. Roster unchanged (events kept). Rejected today:
no-learning, λ 400/1000, EWMA conviction smoothing (2/3/5 days), size 0.45, per-name cap 0.15, top 20, horizons 10/20
only, dropping any agent (events included, after re-validation). `backtest.py` now also applies the live 30% rebalance
band, so the engine, the sweep and `portfolio.plan()` size the book the same way.

Confirmation with the final config, `python backtest.py --days 500 --exec open --tag _v22b` (matches the sweep's `vt50`
row to the first decimal, so engine = sweep = live sizing rules):

| v2.2 | Return | SOXX | Sharpe | Max DD | Vol | Turnover/day | Avg gross |
|---|---|---|---|---|---|---|---|
| full 2024-09-25 → 2026-08-11 | +521% | +132% | 1.63 | 27.7% | 60% | 31% | 86% |
| OOS 2024-09 → 2025-09 | +74% | +12% | 0.96 | 27.7% | | | |
| IS 2025-09 → 2026-08 | +258% | +107% | 2.34 | 23.5% | | | |

Robustness: bootstrap Sharpe CI 0.53-2.87, deflated Sharpe 0.63 after 204 trials, best quarter = 38% of the log return,
conviction quintiles Q1 → Q5 = +0.14% / +0.40% / +0.27% / +0.60% / +1.94% (10-day abnormal), cost at 30 bps still
+330% / Sharpe 1.30. Versus v2.1 on the same inputs (+803% / 1.50 / DD 36% / OOS 0.82): less return, better everything else.

## Ideas tested and NOT worth re-testing (2026-09-11)

no-learning (equal prior) · λ 400 / 1000 · EWMA conviction smoothing · per-name vol scaling (round 5) · rebalance every
2-3 days · size 0.45 · cap 0.15 · top 10 / 20 · horizons 5/10 or 10/20 only · dropping any single agent · price stops ·
short book · SOXX hedge · momentum / SUE / ML-ranker agents · customer read-through · TopkDropout seat protection ·
no market-cap cap.

## Open ideas (not yet tested)

- Quantile-spread monitoring live (Q5−Q1 on the dashboard) as an early warning that the ranking stopped working.
- A point-in-time snapshot of the earnings-ai graph per month, so `neighbors` / `supply_chain` edges stop being today's.
- Regime split of the OOS year: 2025Q2 (V-shaped rebound) was the only quarter far behind SOXX (−36% excess); do not
  fix it on one occurrence, but watch for a second.

## 2026-09-11 — "did the graph update cut the return?" (answer: mostly no)

Separating the two things that changed between the morning ledger and the confirmation ledger:

| v2.1, weekly refit (old engine default) | Return | Sharpe | OOS Sharpe |
|---|---|---|---|
| old ledger, full range | +984% | 1.63 | 0.92 |
| old ledger, first day dropped (same data, refit phase shifted) | +935% | 1.58 | 0.80 |
| fresh ledger (graph updated 19:20, window +1 day) | +803% | 1.50 | 0.82 |

Dropping ONE day of the same data moved OOS Sharpe 0.92 → 0.80: the weekly refit made results depend on which
weekday the learner happened to refit on. The live cycle refits every day (`score.py`), so the honest engine setting
is `refit_every=1`, which the learner cache now makes affordable. With daily refits the two ledgers agree:

| Daily refit (= live) | Return | Sharpe | Max DD | OOS return | OOS Sharpe | OOS DD | IS Sharpe |
|---|---|---|---|---|---|---|---|
| v2.1, old ledger | +676% | 1.40 | 43.7% | +62% | 0.67 | 43.7% | 2.12 |
| v2.1, fresh ledger | +685% | 1.43 | 43.8% | +67% | 0.72 | 43.8% | 2.16 |
| v2.2 (vol target 0.50), old ledger | +488% | 1.60 | 29.2% | +66% | 0.91 | 29.2% | 2.30 |
| v2.2 (vol target 0.50), fresh ledger | +483% | 1.61 | 30.8% | +67% | 0.92 | 30.8% | 2.34 |

- The graph update changed the result by ~1%. The apparent −18% was the refit phase, not the data.
- The weekly-refit numbers reported earlier (+984%, +447% on 220 days) were optimistic versus what the live rule does;
  the daily-refit numbers above are the ones to quote from now on. `backtest.py` and `sweep.py` default to daily refits.
- v2.2 holds under daily refits, and more clearly: OOS Sharpe 0.67 → 0.91, drawdown 44% → 29%, OOS return unchanged
  (+62-67% either way); the raw-return cost is entirely in-sample.

## 2026-09-11 — generational search, 10 variants at a time (`sweep.py --search 3 --pop 10 --workers 10`)

Parallel evaluation (10 processes) plus a search loop: each generation evaluates 10 variants, ranks every trial so far by
the mean rank over five metrics (full-window Sharpe and return, OOS Sharpe and return, full-window max drawdown), and
mutates the best by one or two knobs for the next generation. Space: vol target, size, entry threshold, top N, cap, band,
lambda, half-life, horizons. Daily refits, next-open execution, fresh (v22) ledger, 34 trials in total.

| Trial | Objective | Return | Sharpe | Max DD | OOS return | OOS Sharpe | Knobs that differ from v2.2 |
|---|---|---|---|---|---|---|---|
| g1_base (= v2.2) | 0.24 | +483% | 1.61 | 30.9% | +67% | 0.92 | — |
| g1_2 | 0.73 | +718% | 1.89 | 29.0% | +123% | 1.42 | horizons 10/20 |
| g2_10 | 0.90 | +885% | 2.00 | 29.2% | +161% | 1.67 | horizons 10/20, entry 0.10 |
| **g3_3** | **0.94** | **+935%** | **2.03** | **28.9%** | **+163%** | **1.68** | horizons 10/20, entry 0.10, cap 0.15 |
| g3_5 | 0.87 | +631% | 2.08 | 22.8% | +129% | 1.77 | horizons 10/20, entry 0.10, top 10 |
| g3_1 | 0.85 | +813% | 2.02 | 29.2% | +137% | 1.56 | horizons 10/20, entry 0.10, size 0.45 |
| g3_4 | 0.80 | +787% | 1.91 | 29.9% | +149% | 1.57 | horizons 10/20, entry 0.10, λ 100 |
| g2_5 | 0.71 | +472% | 1.99 | 21.2% | +106% | 1.60 | horizons 10/20, vol target 0.30 |

- **The one big lever is dropping the 5-day horizon.** Every trial with horizons 10/20 beats every trial with 5/10/20 on
  every metric; the neighbourhood is smooth (entry 0.10 or 0.15, cap 0.10 or 0.15, size 0.45 or 0.60, λ 100-250 all land at
  Sharpe 1.9-2.1, OOS Sharpe 1.4-1.8). That is a plateau, not a spike — the kind of result that survives.
- 5-day abnormal returns are mostly noise; scoring on them fed noise into the stacking weights and into the conviction blend.
- Caveat, stated plainly: the search selected on both windows, so the OOS year is no longer untouched. What remains as
  validation is live paper trading and new months of data. The improvement (OOS Sharpe 0.92 → 1.68, OOS return +67% → +163%)
  is far outside the ±0.15 / ±20% input-noise band measured earlier, which is why it is adopted anyway.

**Decision (v2.3, 2026-09-11):** `HORIZONS = (10, 20)`, `MIN_CONVICTION = 0.10`, `MAX_POSITION_PCT = 0.15`; vol target 0.50
kept; everything else unchanged. Confirmation `python backtest.py --days 500 --exec open --tag _v23` (engine = search to the first decimal):

| v2.3 | Return | SOXX | Sharpe | Max DD | Vol | Turnover/day | Avg gross |
|---|---|---|---|---|---|---|---|
| full 2024-09-25 → 2026-08-11 | +966% | +132% | 2.08 | 28.9% | 61% | 33% | 99% |
| OOS 2024-09 → 2025-09 | +160% | +12% | 1.67 | 28.9% | | | |
| IS 2025-09 → 2026-08 | +310% | +107% | 2.51 | 23.7% | | | |

Robustness: bootstrap Sharpe CI 0.94-3.37, deflated Sharpe 0.83 after 204 trials, best quarter 32% of the log return
(was 44%), every quarter but two positive and 2025Q2 — the V-rebound quarter that lost 36% to SOXX under v2.1 — now +5%,
quintiles Q1 → Q5 = +0.2% / +0.5% / +0.2% / +0.7% / +1.8%, cost at 30 bps still +627% / Sharpe 1.74.
Versus v2.2 on the same inputs (+521% / 1.63 / DD 27.7% / OOS 0.96): twice the return, same drawdown, steadier quarters.

## Next (user direction 2026-09-11: any method is allowed — learner, weights, sizing; the goal is return per unit of risk, steady)

Ordered by expected value per hour, all to be run through the same search harness (daily refits, both windows, PBO):

1. **Sizing by risk, not by conviction alone**: weight ∝ conviction / volatility (inverse-vol), and a risk-parity variant;
   the vol target already helped at the book level, this is the same idea per name.
2. **Learner alternatives** (the ridge is a choice, not a law): (a) IC-weighted blend (each agent's trailing IC as its weight —
   simplest possible), (b) LightGBM ranker as the *stacker* over agent outputs (it was only tested as an agent), (c) online
   logistic on the sign of the abnormal return. Keep whichever wins OOS with the fewest parameters.
3. **Steadier returns**: drawdown-aware exposure (cut gross after a 10% drawdown from the equity high, restore on recovery),
   tested against the vol target it would sit on top of.
4. **Turnover**: entry/exit hysteresis (enter at 0.10, exit at 0.04 is already asymmetric) and a minimum holding period; the
   EWMA idea failed, hysteresis is the cheaper version of the same wish.
5. Point-in-time snapshots of the earnings-ai graph (monthly copies), so `neighbors` / `supply_chain` stop seeing today's edges.

## 2026-09-11 — universe to every US-listed name, live lookback fixed, graph snapshots, filings

- **Universe** (user decision): `MAX_MARKET_CAP = None`. The refreshed earnings-ai graph has 151 US-listed tickers, 150
  tradable on Alpaca (was 96 under the $400B cap). Baseline with v2.3 rules on the new universe: run `_u150` below.
- **Live lookback** `LOOKBACK_DAYS` 260 → 420 calendar days. Live had ~178 trading rows, so `technical`'s 200-day average
  silently fell back to the 50-day while the backtest (full history) used the real one — an engine/live mismatch, now closed.
- **Graph snapshots** (`snapshots.py`): every cycle copies the earnings-ai graph files into `state/graph_snapshots/<date>/`
  when their content changed (first one 2026-09-11). `backtest.py --graph-asof DATE` builds the supply-chain map from the
  newest snapshot dated <= DATE. Per-day switching inside one run comes once enough snapshots exist; until then the
  structure-is-today's caveat stands.
- **10-K / 10-Q / 8-K**: earnings-ai now carries 1,002 filing-derived rows for 137 companies (434 10-K, 255 10-Q, 313 8-K),
  dated in the `quarter` label like call statements, with `counterparty` / `counterparty_role` (91 customer, 54 supplier
  relations), `slot` and `capex` fields. They already flow through the existing agents: `supply_chain` scores their text as
  dated signals, `neighbors` reads customers' statements, `llm_guidance` reads the latest statements. 93% of the rows are
  dated Feb-Sep 2026, so a filings-specific agent could only be judged in-sample; not built today (see Next).

Baseline `_u150` (v2.3 rules, 150 names, daily refits, next-open execution) vs v2.3 on the 96-name universe:

| | Return | Sharpe | Max DD | OOS return | OOS Sharpe | IS return | IS Sharpe | Deflated Sharpe |
|---|---|---|---|---|---|---|---|---|
| v2.3, 96 names (cap $400B) | +966% | 2.08 | 28.9% | +160% | 1.67 | +310% | 2.51 | 0.83 |
| v2.3, 150 names (no cap) | +758% | 1.81 | 28.7% | +215% | 1.94 | +173% | 1.68 | 0.99 |

The wider universe is stronger out of sample (Sharpe 1.94, +215%) and weaker in the tuning window (the mega-caps
lagged the small caps in 2026H1); quintiles stay monotone (Q1 −0.0% … Q5 +1.65%), cost at 30 bps +433% / 1.40.
A profile whose OOS year is at least as good as its tuning year is the healthier one, so the no-cap universe stays
(it is also the user's decision). Two cautions: names added to the graph in 2026 were chosen knowing they matter
in 2026 (a mild look-ahead in universe construction that only fresh snapshots will remove), and 2026Q3 (partial) is
−12.8% on this universe vs −3.9% on the old one — watch the live scoreboard.

(2026-09-11, user) Universe stays wide: the small-cap-only result reflects the 2024-26 market rewarding semiconductor
small caps; with the graph data covering the whole US-listed chain, breadth is the safer bet going forward. Next steps are
listed under "Next" above; progress uploads to Vercel are now final-only (`PROGRESS_UPLOAD`), watch runs locally with
`watch_backtest.cmd`.

## 2026-09-11 — backtest speed, round 2 (results bit-identical)

Verified with a frozen price pickle fed to both code versions (the earlier 1e-8 differences were yfinance adjustment
factors changing between two downloads, not code): predictions, scores, equity curve, report and final model all
identical. Changes: the learner rebuilds only the prediction dates that received new scores (an index on
scores.scored_date; a backtest adds one date per day instead of re-featuring every row), date ordinals computed once
per fit, the day loop reads prices from numpy views and writes scores in one executemany, and `risk` / `macro`
slice precomputed full-history return series as of the day (same pandas operations on the same values; the live
agents keep the original path when no history is passed). Same 60-day loop: 173 s (yesterday morning) → 76 s → 39 s.

## 2026-09-11 — round 12: the "Next" list, tested (150-name ledger `_u150b`, daily refits, next-open, OOS split)

`python sweep.py --round12 --tag _u150b --exec open --oos-end 2025-09-24 --workers 10` (15 variants, 11 min). PBO 0.56.

| Variant | Return | Sharpe | Max DD | Turnover/day | OOS return | OOS Sharpe | OOS DD | Verdict |
|---|---|---|---|---|---|---|---|---|
| **v2.3** (base) | +758% | 1.81 | 28.7% | 41% | +215% | 1.94 | 28.7% | reference |
| inverse-vol sizing, ref = cross-section median | +774% | 1.84 | 28.3% | 44% | +213% | 1.94 | 28.3% | inside the noise band — not adopted |
| inverse-vol, ref 0.40 / 0.60 | +563% / +715% | 1.81 / 1.90 | 28.5% / 28.8% | 39% / 42% | +151% / +184% | 1.68 / 1.84 | | rejected — OOS worse |
| per-name vol scaling (round-5 knob, re-test) | +770% | 1.85 | 28.6% | 44% | +198% | 1.88 | | inside the noise band |
| drawdown brake 10% → ×0.5 (release 5%) | +359% | 1.59 | 24.8% | 35% | +129% | 1.71 | 24.8% | rejected — the vol target already does this job, the brake only costs return |
| drawdown brake 15% → ×0.5 | +577% | 1.82 | 25.4% | 36% | +160% | 1.90 | 25.4% | rejected — same Sharpe, −24% return, OOS worse |
| drawdown brake 10% → ×0.3 / 20% → ×0.5 | +231% / +416% | 1.53 / 1.57 | 22.2% / 33.6% | | +94% / +105% | 1.62 / 1.45 | | rejected |
| exit hysteresis 0.05 / 0.07 | +728% / +771% | 1.77 / 1.81 | 27.8% / 28.3% | 40% / 40% | +202% / +210% | 1.85 / 1.91 | | inside the noise band |
| minimum hold 3 / 5 days | +695% / +617% | 1.74 / 1.66 | 28.1% / 30.3% | 33% / 29% | +207% / +168% | 1.90 / 1.68 | | rejected — less turnover but worse everywhere else |
| exit 0.05 + hold 3 | +668% | 1.71 | 30.3% | 33% | +192% | 1.80 | | rejected |
| IC-weighted blend instead of the ridge | +270% | 1.14 | 51.6% | 50% | +48% | 0.70 | 51.6% | **rejected clearly** — the ridge stacker's negative weights and confidence terms matter; the simple blend is far worse |

**Decision:** nothing adopted. v2.3 stays as is. After the vol target and the 10/20 horizons, per-name risk sizing,
drawdown brakes, hysteresis and holding periods all land inside the ±20% / ±0.15 noise band or below it, and the
learner should stay the Bayesian ridge. That is a plateau, and the right response to a plateau is to stop turning knobs
on this data and let live paper results and new months decide.

Still open: LightGBM stacker (only worth it once there are more than two years of rows), `llm_guidance` quarterly
partial backtest (~800 Claude calls), graph snapshots accumulating for a point-in-time neighbors/supply_chain test.

## 2026-09-11 — LLM agents on Fable 5.1 at max effort (user decision)

`config.LLM_MODEL = "claude-fable-5-1"`; the local Claude server maps it to the full model id at `--effort max`.
Test call (llm_guidance, NVDA + AMD): 52-58 s per call, ~$0.32 of subscription budget each, opinions well formed.
At ~300 calls a day and 2 concurrent workers that is ~2 h 20 min per cycle, so the 05:50 PT start would place orders
well after the open — the cycle start needs to move to ~03:30 PT (or the worker count up) to keep the open.

## 2026-09-11 — round 13: longer horizons and a leaner learner (ledger `_h40`, scores at 10/20/40 days)

`python backtest.py --days 500 --exec open --tag _h40 --horizons 10,20,40` then `sweep.py --round13`. PBO 0.23.

| Variant | Return | Sharpe | Max DD | OOS return | OOS Sharpe | Verdict |
|---|---|---|---|---|---|---|
| **v2.3, horizons 10/20** | +741% | 1.85 | 29.0% | +209% | 1.96 | reference — best on every metric |
| horizons 10/20/40 | +696% | 1.77 | 28.2% | +189% | 1.83 | rejected |
| horizons 20/40 | +492% | 1.49 | 33.0% | +122% | 1.31 | rejected |
| horizon 20 only / 40 only | +502% / +530% | 1.53 / 1.54 | 36.8% / 29.5% | +144% / +133% | 1.47 / 1.43 | rejected — one horizon is not enough |
| 10/20 without direction-only features | +316% | 1.26 | 28.3% | +86% | 1.12 | rejected clearly — the direction-only terms carry real information |
| 10/20/40 without direction-only features | +397% | 1.37 | 27.9% | +125% | 1.40 | rejected |

**Decision:** unchanged. Dropping the 5-day horizon was the win; going longer than 20 days is not. The learner's
two feature blocks (direction × confidence and direction alone) both matter. Rounds 12-13 together: 22 variants, none
beats v2.3 outside the noise band — v2.3 is the configuration to trade, and further gains have to come from data
(graph snapshots, more months, the Claude agents' live scoreboard), not from knobs.

(2026-09-11 03:40 PT) Fable 5.1 max in the live cycle measured ~4-7k input + 2.5-4.3k output tokens per call (~$0.20-0.33 API-equivalent);
the user judged that too heavy for the Max plan and switched the live agents to Opus 5 at max effort (test call: 2.3k in / 0.5k out, 8 s).
The 03:30 cycle was stopped after 15 Fable calls and relaunched at 03:41 on Opus (predictions are recorded only after all agents finish,
so nothing was double-counted).

## 2026-09-11 — round 14: realistic costs, low-turnover variants, v2.3 knobs on 150 names, CPI-day hold (ledger `_u150b`)

Costs tiered by today's market cap: 5 bps (>$50B), 10 bps ($5-50B), 20 bps (<$5B). CPI release dates from FRED (release 10).

| Variant | Return | Sharpe | Max DD | Turnover/day | OOS return | OOS Sharpe | Verdict |
|---|---|---|---|---|---|---|---|
| **v2.3, flat 5 bps** | +758% | 1.81 | 28.7% | 41% | +215% | 1.94 | reference |
| v2.3, cap-tiered costs | +687% | 1.73 | 28.8% | 41% | +203% | 1.87 | realistic baseline: costs take ~9% of return, 0.08 Sharpe |
| tiered costs + band 0.50 | +709% | 1.77 | 28.6% | 40% | +210% | 1.90 | inside the noise band |
| tiered costs + exit 0.07 / hold 3 / rebalance every 2 | +699% / +645% / +511% | 1.74 / 1.69 / 1.61 | | 40% / 33% / 37% | +199% / +198% / +150% | 1.84 / 1.84 / 1.63 | rejected — lower turnover does not pay even at realistic costs |
| tiered costs + top 10 | +784% | 1.84 | 30.7% | 42% | +210% | 1.88 | inside the noise band, more concentrated |
| vol target 0.40 | +674% | 1.91 | 25.0% | 37% | +206% | 2.08 | the risk-first alternative: +0.1 Sharpe, −3.7 pts drawdown, −11% return |
| vol target 0.60 | +896% | 1.78 | 32.3% | 44% | +234% | 1.89 | more return, more drawdown |
| top 20 / min conviction 0.15 | +717% / +613% | 1.79 / 1.70 | 27.8% / 29.0% | 37% / 38% | +207% / +209% | 1.96 / 1.94 | inside the noise band / rejected |
| CPI-day hold (no rebalance on release days) | +691% | 1.74 | 28.8% | 41% | +203% | 1.88 | rejected — trading through CPI days is fine |
| CPI-day hold + tiered costs | +624% | 1.67 | 28.9% | 41% | +191% | 1.81 | rejected |

**Decision:** unchanged again. Realistic costs are survivable (+687% / 1.73 / OOS 1.87) and no turnover rule earns
them back; vol target 0.40 is documented as the switch to flip if drawdown ever matters more than return.
(The round's summary file was lost to a JSON bug with the date set — fixed — so no PBO for this round.)

(2026-09-11 04:40 PT) Opus 5 at max effort measured 105 s and 6-9k output tokens per call in the live cycle (64 calls in 56 min,
i.e. ~300 calls would have ended around 08:00 PT, well after the open). Relaunched on Opus at HIGH effort with the Claude agents
limited to the 60 highest preliminary-|conviction| names (`LLM_MAX_TICKERS`): test call 12 s / 2.3k in / 0.7k out. Rule of thumb
now: the LLM stage must fit in ~90 minutes (03:40 → 05:30 PT) — roughly 200 calls at ~50 s with 2 workers.

## 2026-09-11 — round 15: does `llm_guidance` earn its place? (point-in-time partial backtest)

`llm_backtest.py` re-asked the live agent's question 487 times (one per name and statement date since 2024-06, statements
dated <= that day only, Sonnet at low effort per the research-model rule, 27 min) and held each opinion until the next
statement, writing 16,551 dated rows into a copy of the 150-name ledger. `sweep.py --round15 --tag _llmg`, PBO 0.03.

| Roster | Return | Sharpe | Max DD | Turnover/day | IC 10d | OOS return | OOS Sharpe |
|---|---|---|---|---|---|---|---|
| 7 rule agents (v2.3) | +758% | 1.81 | 28.7% | 41% | 0.016 | +215% | 1.94 |
| 7 rule agents + llm_guidance | +779% | 1.83 | 28.8% | 38% | 0.016 | +220% | 1.97 |
| llm_guidance alone (learned) | +3% | 0.10 | 18.0% | 0.7% | **0.043** | ~0 | — |
| llm_guidance alone (equal prior) | +9% | 0.17 | 28.5% | 2.5% | 0.032 | ~0 | — |

- Its own ranking IC (0.043 at 10 days) is the highest of any single agent, but it speaks for few names at a time
  (only those with fresh statements), so alone it barely trades. Inside the roster it adds a little on every metric in
  both windows (+3% return, +0.02 / +0.03 Sharpe, −3 pts turnover) — small, but the first Claude agent with a measured,
  point-in-time, out-of-sample positive contribution.
- Live it runs on Opus at high effort (stronger than the Sonnet-low proxy), so the real contribution is plausibly >= this.
  Verdict: keep it, and keep paying for it. `llm_supply` and `llm_news` still cannot be backtested (no dated inputs).

## 2026-09-11 — first live cycle on v2.3 / 150 names / Opus high (what happened)

03:30 start (moved from 05:50); restarted twice while switching the Claude agents from Fable max (55 s, ~10k tokens per
call) to Opus max (105 s) to Opus HIGH (16 s, ~1k output tokens; 60 names today, 100 from tomorrow). LLM stage done 05:08,
orders at the 09:30 ET open, all 17 fills: the 15 names bought on 2026-09-10 were closed and the only name above the
0.10 entry bar was SHEL (two limit slices at 96.11 / 96.40, 7.5% of equity). Equity $1,006,625, cash 92%.

Why so defensive: the rule agents were bearish (technical negative on 64% of names, risk negative on 62), and under the
learned weights every other conviction fell below 0.10 (2nd: APD 0.089). The equal-weight prior would have bought
DELL / MU / SMCI / MRVL — the learner does not trust that mix. This matches the backtest, whose last simulated day
(2026-08-11) also held one name at 9% gross after the August drawdown: the strategy has been in its cash regime since
August, live simply inherited it. The Claude agents were mildly positive (mean direction +0.06 to +0.29), not the cause.

Two things to watch rather than fix: (1) the wide universe brings non-semiconductor graph members into the ranking
(SHEL, APD, MMM, utilities — data-centre power/materials suppliers), and today the top pick was one of them; (2) a long
cash regime forfeits any SOXX rebound. Both are the model's rules working as validated; if the user wants a floor on
exposure or a semiconductor-only universe, that is a config decision to test, not a bug.

## 2026-09-11 — round 16: are the negative agent weights right? (non-negative ridge test)

The user saw negative effective weights (supply_chain −0.046, macro −0.043 on the first live day) and asked whether that
is correct. Same objective, weights constrained >= 0 (NNLS on the augmented ridge system), 150-name ledger, PBO 0.03:

| Learner | Return | Sharpe | Max DD | IC 10d | OOS return | OOS Sharpe |
|---|---|---|---|---|---|---|
| **signed ridge (v2.3)** | +758% | 1.81 | 28.7% | 0.016 | +215% | 1.94 |
| non-negative weights | +172% | 1.01 | 29.3% | 0.001 | +32% | 0.75 |
| non-negative, no direction terms | +171% | 1.02 | 29.2% | 0.002 | +39% | 0.91 |

Forbidding negative weights destroys most of the edge in both windows. The negatives are not noise: supply_chain and
neighbors come from the same graph, and the ridge uses one and partly nets the other out (collinearity correction),
and some agents are reliably wrong at some horizon and are worth using upside down. Verdict: keep the signed ridge; a
negative display weight means "used as a correction / contrarian input", not "broken".

## 2026-09-11 — round 17: the cash regime (live went 92% cash while SOXX rallied) — lower bar, floors, always-invested, sub-universes

Ledger `_u150b`, daily refits, next-open execution, OOS split. PBO 0.93 (= no variant is a robust winner; they are all the same).

| Variant | Return | Sharpe | Max DD | Turnover/day | OOS return | OOS Sharpe | Verdict |
|---|---|---|---|---|---|---|---|
| **v2.3** (entry 0.10) | +758% | 1.81 | 28.7% | 41% | +215% | 1.94 | reference |
| entry 0.05 / 0.075 | +778% / +787% | 1.82 / 1.83 | 28.3% / 28.4% | 42% / 41% | +202% / +208% | 1.86 / 1.90 | inside the noise band, OOS slightly worse |
| exposure floor: always hold >= 8 / >= 12 names at >= 3% | +729% / +735% | 1.77 / 1.78 | 28.8% / 28.6% | 41% / 42% | +207% / +205% | 1.90 / 1.88 | rejected — forcing exposure does not add return, costs a little Sharpe |
| always invested: top 15 by conviction > 0, each >= 5% | +729% | 1.76 | 28.2% | 42% | +201% | 1.86 | rejected |
| universe: graph members with a supply-chain layer (101) | +638% | 1.74 | 30.3% | 34% | +131% | 1.48 | rejected — the "non-chain" names (utilities, gases, energy, OEM customers) help |
| universe: core semiconductor layers only (77) | +585% | 1.85 | 33.5% | 32% | +113% | 1.54 | rejected — narrower is worse out of sample |
| universe: drop the 16 names above $400B (134) | +766% | 1.81 | 27.7% | 39% | +222% | 1.97 | inside the noise band |

**Decision:** unchanged. The days when fewer than a handful of names clear the bar are, on average, days worth
sitting out — every way of forcing money to work (lower bar, floors, always-invested) gives back Sharpe and adds
nothing out of sample. Today's miss versus SOXX is the price of that rule on one day; the rule earned its Sharpe over
470 days. The wide universe is confirmed: dropping the non-semiconductor graph members hurts (OOS 1.94 → 1.48).

## 2026-09-11 — round 18: shorts and the SOXX regime hedge (and a sweep bug this round exposed)

Question from the user after a day of sitting in cash while SOXX rallied: shorts? inverse ETFs? Tested on the 150-name
ledgers (`_u150b` and today's `_v24`), daily refits, next-open execution, OOS split.

**First pass (wrong, kept for the record):** short books of the 5-10 most negative names were worse; hedging only when
the ensemble is net bearish did nothing; but "short SOXX 0.7 x equity while SOXX is below its 50-day average" looked
like a clear winner (+886% / 1.88 / OOS 2.18) and de-risking the longs in that regime looked terrible. The engine run of
the same rule came back at +675% / 1.78 — engine and sweep had always agreed before, so this was chased down: the
sweep's gross ceiling used the SIGNED sum of weights, so a −0.7 hedge let the long book run above the 150% ceiling on
hedge days. Live can never do that (buying power, `GROSS_TARGET`). Fixed (long-only gross is capped); rounds 9 and 18a
were the only ones affected, and both were short/hedge tests.

**Corrected (today's ledger, engine = sweep to the first decimal again):**

| Variant | Return | Sharpe | Max DD | Turnover/day | OOS return | OOS Sharpe | OOS DD |
|---|---|---|---|---|---|---|---|
| **long-only v2.3** | +731% | 1.78 | 28.8% | 41% | +204% | 1.88 | 28.8% |
| hedge 0.7 × equity when SOXX < 50-day | +675% | 1.78 | 26.7% | 47% | +203% | 2.03 | 23.6% |
| hedge capped at the long book (never net short), 0.7 | +685% | 1.81 | 26.7% | 47% | +191% | 1.96 | 23.6% |
| same, 1.0 | +626% | 1.78 | 26.8% | 50% | +178% | 1.93 | 26.8% |
| short book 5 / 10 names (round 18a, uncorrected cap) | +723% / +671% | 1.73 / 1.66 | | | +212% / +202% | 1.86 / 1.78 | | rejected |

**Decision:** no shorts, hedge OFF by default. Correctly measured, the regime hedge is a drawdown reducer with a return
cost (−8% return, same full-window Sharpe, OOS drawdown 28.8% → 23.6%, OOS Sharpe +0.15) — the same trade the vol target
0.40 offers, not new alpha. The code stays in (`HEDGE_SIZE`, `broker.hedge_to`, engine support, dry-run tested) as an
optional risk overlay for when drawdown matters more than return. Today specifically, SOXX is below its 50-day average
and rallied — the hedge would have lost.

## 2026-09-11 — round 19: bagging, IC gating, beta-adjusted target (today's ledger `_v24`)

| Variant | Return | Sharpe | Max DD | OOS return | OOS Sharpe | Verdict |
|---|---|---|---|---|---|---|
| v2.3 | +731% | 1.78 | 28.8% | +204% | 1.88 | reference |
| bagging over 3 sizing configs (size 0.45 / 0.60 / 0.75) | +738% | 1.79 | 28.8% | +203% | 1.88 | identical — the sizing choice does not matter |
| bagging over 5 configs (entry 0.075-0.15, top 10/20) | +730% | 1.83 | 27.3% | +188% | 1.84 | inside the noise band |
| IC gate: half size when the learner's walk-forward IC < 0 | +425% | 1.49 | 28.8% | +143% | 1.71 | rejected — low recent IC did not predict poor returns in 2024-26 |
| IC gate < 0.02 → half / → flat | +393% / +84% | 1.44 / 0.60 | | +147% / +56% | 1.74 / 1.04 | rejected |
| beta-adjusted learning target (`make_beta_ledger.py`, 60-day beta per name) | +710% | 1.94 | **38.7%** | +257% | 2.01 | mixed: better Sharpe and OOS, much deeper drawdown (the learner stops penalising high beta). Worth revisiting together with a drawdown control |

## 2026-09-11 — the regime question: 2019-2023 stress test and price vs graph agents (the most important result so far)

`backtest.py --days 1200 --end 2023-12-29 --agents technical,mean_reversion,risk,macro,events` (the graph has no dated
signals before 2024, so only the price/rule agents can be replayed there; today's 150 names, i.e. survivorship favours it):

| 2019-04 → 2023-11 (1,170 days) | Return | Sharpe | Max DD | IC 10d |
|---|---|---|---|---|
| price agents, v2.3 sizing | **−16.6%** | −0.14 | 42.6% | learned −0.028, equal prior −0.016 |
| top-15 rank line (always invested) | +99% | 0.44 | | |
| SOXX / SPY | +170% / +70% | | | |

And on 2024-26 (round 20, ledger `_v24`): price agents only +877% / 1.86 / OOS 2.05 — better than all seven rule agents
(+731% / 1.78 / 1.88); graph agents only (supply_chain, neighbors, events) +2% / 0.04; graph + risk + macro +509% / 1.67.

**Reading:** the whole 2024-26 edge is the price stack — 20/60-day relative momentum, 5-day reversal, vol, beta × regime —
and that same stack lost money for five years before the AI boom, with negative IC. The graph agents add nothing
measurable on their own and slightly dilute the price agents in 2024-26. So the honest description of v2.3 is: a
relative-momentum machine on the AI supply chain that worked in one regime. That is not curve-fit overfitting (the
plateau is wide and the OOS year holds), it is regime dependence: the same rules have no proven edge outside 2024-26.
Consequences: (1) live expectations must be regime-conditional — in a non-boom tape the rules are not known to work;
(2) the highest-value research is a regime-aware layer that protects in bad regimes without giving the good ones back
(round 21 tests self-monitoring gates on both ledgers); (3) the graph agents' value, if any, has to come from horizons
or forms not yet tested (slow information, 60-day scoring), or from the LLM readers — llm_guidance was the only one
with a measured positive contribution (round 15).

## 2026-09-11 — round 21: self-monitoring exposure gates on both regimes

Gate = scale the book when the strategy's own trailing return is below a threshold. Tested on the 2019-23 price-agent
ledger (`_pre2024`, where the rules lose) and on 2024-26 (`_v24`, where they win).

| Gate | 2019-23 return | 2019-23 Sharpe | 2019-23 DD | 2024-26 return | 2024-26 Sharpe | 2024-26 OOS Sharpe |
|---|---|---|---|---|---|---|
| none (base) | −18% | −0.16 | 45.8% | +731% | 1.78 | 1.88 |
| 60-day return < 0 → half size | −22% | −0.23 | 39.1% | +610% | 1.68 | 1.91 |
| 60-day return < −10% → flat | −9% | −0.08 | 44.2% | +730% | 1.78 | 1.88 (never fires) |
| 120-day return < 0 → half size | −36% | −0.43 | 43.9% | +731% | 1.78 | 1.88 (never fires) |
| walk-forward IC < 0 → half size | −1% | −0.01 | 36.8% | +425% | 1.49 | 1.71 |

**Decision:** no gate. In the bad regime the gates whipsaw (the strategy's bad years are choppy, not one long slide),
so cutting size after losses mostly cuts the recoveries; in the good regime they either never fire or cost Sharpe.
A strategy that has no edge in a regime cannot be rescued by watching its own P&L — it has to be switched off by
something that identifies the regime ahead of time, and nothing tested does that. The honest position stands: v2.3
is a relative-momentum strategy on the AI supply chain with a proven edge only in the 2024-26 regime.

## 2026-09-11 — what would actually be new (after 21 rounds)

- Signals that are not price momentum: the graph agents in their current form add nothing; `llm_guidance` adds a little
  and is the only Claude agent with a measured contribution. The next real experiment is a 60-day scoring horizon for the
  slow (graph / filings) information, and dated counterparty relations from the 10-K rows as a point-in-time edge set
  once snapshots accumulate.
- Regime identification from outside the strategy (breadth, credit, semiconductor cycle indicators) as an on/off switch
  — testable on 2019-26 with the price-agent ledgers already built.
- The beta-adjusted target (Sharpe 1.94 / OOS 2.01 / drawdown 38.7%) combined with a drawdown control, as the one
  learner change that moved the OOS window.

## 2026-09-11 — data coverage: the earnings-call graph only starts in 2025-10 (read this before judging any graph agent)

Counted from `graph/merged_graph.json` (`quarterly_data` labels, e.g. "NVIDIA Q1 FY2027 (05-20-2026)"):

| Month | 2025-10 | 11 | 12 | 2026-01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dated statements | 11 | 34 | 31 | 12 | 241 | 58 | 359 | 503 | 182 | 833 | 1,370 | 130 |

Nothing before 2025-10; 85% of the 3,764 rows are dated 2026-04 or later. In the `backtest.sqlite` ledger, `supply_chain`
has rows only from 2025-10-03 (16.8k) while `technical` / `macro` / `mean_reversion` have ~72k each from 2024-08-13.

**What this invalidates.** The OOS year (2024-09-24 → 2025-09-23) contains no earnings-call data at all, so every OOS verdict
on `supply_chain`, `neighbors` and `llm_guidance` (rounds 10, 15, 20) was decided with those agents silent. "Graph agents
add nothing OOS" is a consequence of the data, not evidence about the agents. Their only backtestable window is
2026-02 → 2026-08, which sits inside the tuning window (weak evidence either way). The real test is the live scoreboard.

**What it does NOT invalidate.** The price/calendar agents (`technical`, `mean_reversion`, `risk`, `macro`, `events`) use
prices and the earnings calendar, which exist for the whole 500-day window and for 2019-23. Every sizing, learner,
vol-target and horizon decision rests on them and stands.

**Artifact to fix before the next graph-agent test.** `PointInTimeMap.neighbors` (backtest.py) returns
`tanh(-0.25) = -0.245` for every name that has edges whenever no neighbour has a dated statement — i.e. a constant
negative opinion for all of 2024-08 → 2025-09, with confidence set by today's edge count. That is what the ridge
learned as neighbors' "contrarian" weight (round 10: negative IC; round 16). It should return `None` (like
`supply_chain` does) when no neighbour has any dated statement as of the day.

**Why the live learner leans on `technical`.** The warm start (`WARM_START_WEIGHT` 0.5) is fit on the ledger above,
where the price agents have 470 days of scored opinions and the graph agents ~7 months. Under the ridge, sparse agents
stay near the prior and the always-speaking agents absorb the fit: on the first live day `technical` 0.137 vs prior
0.091, `supply_chain` −0.046, `macro` −0.043. As live rows accumulate (daily refits, 90-day half-life, warm start at
half weight) the graph and Claude agents earn their weights from live scores; expect ~60-90 scored days before their
live evidence outweighs the warm start.

**Options.** (a) Backfill 2024-25 transcripts in earnings-ai (Alpha Vantage historical quarters, ~150 names × 6 quarters
≈ 900 calls; then `enrich`) — makes the OOS year graph-covered and is the only way to backtest these agents honestly;
earnings-ai work, the user's call. (b) Skip the backtest and pre-register live decision rules (per-agent live IC after
60 scored days; Q5−Q1 spread on the dashboard). Until (a) happens, (b) is the validation.

## 2026-09-11 — round 22: the neighbors point-in-time artifact, fixed (ledgers `_base` / `_nbfix`, 500 days, next-open, daily refits)

Question from the user: the live weights tilt sharply to `technical` — is that wrong? Two things were tested at once: the
artifact above (`PointInTimeMap.neighbors` now returns `None` when no neighbour has a dated statement as of the day) and
whether removing it changes where the learner puts its weight.

| | Return | Sharpe | Max DD | Turnover/day | OOS Sharpe (monthly) | IS Sharpe | IC 10d learned | neighbors rows | final w_conf technical 10d / 20d |
|---|---|---|---|---|---|---|---|---|---|
| before (fresh graph, today) | +731% | 1.78 | 28.8% | 41% | 2.03 | 1.54 | 0.017 | 55,500 from 2024-08 | 0.265 / 0.250 |
| **neighbors fix** | +687% | 1.73 | 28.1% | 40% | 1.88 | 1.54 | 0.014 | 14,490 from 2025-10 | 0.262 / 0.247 |

- The fake rows were worth a little: neighbors' constant −0.245 with confidence = today's edge count acted as a "has many
  edges in today's graph" factor over the OOS year, a mild look-ahead. Removing it costs −6% return / −0.05 Sharpe / −0.15
  OOS Sharpe — inside the noise band, and the honest number. **Adopted** (correctness, not performance).
- **The technical tilt is not the artifact.** With the fake rows gone the final technical weight is unchanged (0.26 → 0.26).
  It is what the data supports: `technical` has 470 days of positive IC (0.049 / 0.061); `supply_chain` has the highest IC of
  any agent (0.099 / 0.134) but only ~7 months of rows, so the ridge (λ 150) keeps it near the prior. Forcing weights was
  tested in round 16 and destroys the edge, so nothing is capped. The tilt will fade only as live scored months accumulate.
- Warm start: `state/backtest.sqlite` (live) should be replaced by the `_nbfix` ledger (backup the old one as
  `backtest_prenbfix.sqlite`) so the live learner stops warming up on the fake rows. Not done automatically from this
  session (shared live state); see the commit message / report for the copy commands.

## 2026-09-12 — rounds 23–25: corrected causal replay, external gate rejected, beta target retained

Before comparison, tagged replays were isolated from the operational warm start, score eligibility was corrected
to exact stored maturity dates, and CV target scaling/source weights were made fold-local. These correctness fixes
change the baseline relative to older rounds. All comparisons below use next-open execution, daily refits and the
same 2025-09-24 OOS boundary. The already repeatedly inspected OOS segment is exploratory, not untouched evidence.
The frozen protocol and full results are in the dated `semiband-research/outputs/` directory.

Round 23 tested exactly one external gate: two of SPY>SMA200, SOXX/SPY>SMA200 and HYG/LQD>SMA200 permit full exposure;
otherwise use 25%. Recent return +538.2%, Sharpe 1.67, DD 26.9%, OOS Sharpe 1.94, score 3.506 versus corrected raw
baseline +631.6%, 1.67, 27.8%, 1.89, score 3.962. Stress return −11.2%, Sharpe −0.10, DD 37.6%; a constant
matched-exposure control had −12.8%, −0.13, DD 34.8%. PBO 0.979 recent / 0.706 stress. Rejected; do not retune.

Round 24's distinct pre-registered hypothesis was beta-adjusted SOXX labels with the existing lower vol0.40 setting;
raw0.40 and beta0.50 separated risk and target effects. Original raw labels remain available in the source ledgers.

| Recent 2024–26 | Return | Sharpe | Max DD | Turn/day | Score | OOS return | OOS Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|
| Raw / vol0.50 | +631.61% | 1.67 | 27.84% | 39.3% | 3.962 | +210.51% | 1.89 |
| Raw / vol0.40 | +550.34% | 1.75 | 24.13% | 35.7% | 3.653 | +196.14% | 1.99 |
| Beta / vol0.50 | +775.83% | 2.02 | 32.62% | 35.9% | 5.050 | +296.79% | 2.21 |
| Beta / vol0.40 | +631.13% | 2.05 | 28.74% | 33.5% | 4.368 | +259.31% | 2.27 |

| Stress 2019–23 | Return | Sharpe | Max DD |
|---|---:|---:|---:|
| Raw / vol0.50 | −18.29% | −0.17 | 40.59% |
| Raw / vol0.40 | −18.0% | −0.17 | 39.2% |
| Beta / vol0.50 | +17.15% | 0.14 | 36.98% |
| Beta / vol0.40 | +13.85% | 0.12 | 36.37% |

Round 25 fixed trading costs at 30bps: recent beta0.40 +424.0%, Sharpe1.71, OOS1.96 versus raw0.40 +362.5%,
1.43, OOS1.64. Candidate DD was higher (32.6% vs25.2%). Paired 40/80-day block-bootstrap intervals for beta0.40
delta Sharpe cross zero; no statistical superiority claim. These cost tests omit borrowing costs, impact,
partial fills and operational account-history startup behavior. Current-universe survivorship and sparse early
graph history remain limitations. Original conclusion: retain beta0.40 as exploratory offline candidate only.

### Subsequent authorized operational decision (not a retroactive change to the protocol)

After discussing the 0.03 Sharpe gap versus materially higher return at beta0.50, the user selected beta0.50 for
active PAPER use, with raw preserved as a comparison/rollback model. End-to-end label consistency was implemented
for both warm start and future scores, then 15 regression tests and full-data rehearsal passed. After explicit
authorization, both operational ledgers were backed up and additively migrated, 577,944 researched beta scores
imported and 2,036 pre-open live prediction betas frozen; zero live scores had matured. Original records and exact
raw/beta learner inputs were verified. Beta was activated at 14:54 PT; no orders, cycle, LLM calls or schedule changes
were run. The next existing scheduled paper cycle uses beta. See `BETA_IMPLEMENTATION.md` for exact backups,
verification, current negative CV IC, shadow limitations and safe rollback without deleting later observations.

User subsequently requested testing higher deployment/exposure toward a $2m book on approximately $1m equity.
That is a separate predeclared experiment; gross1.50, size0.60 and entry0.10 remain unchanged pending its verdict.
Raising a ceiling alone does not force investment. Record the next experiment below when complete, including
financing, stress, cash exposure and whether its result actually addresses the current low-investment state.

## 2026-09-12 — round 26: higher exposure, financing and cash-drag attribution

Final user decision: KEEP beta0.50 with the existing signal-sized/cash-holding structure. No allocation setting
was enlarged. Five fixed variants × two regimes × two trading-cost models × financing0/5/10% =60 completed scenarios.
All470 recent and1,170 stress dates refit daily. Twelve zero-financing comparisons exactly matched unchanged sweep
daily rounded returns and metrics; six financing/sizing/attribution tests passed. Both source ledgers remained
byte-identical. One new common adjusted-price snapshot reproduced the prior zero-financing beta baselines.

| Variant (cap-tier costs + assumed5% financing) | Recent return / Sharpe / DD | OOS Sharpe | Stress return / Sharpe / DD | Recent mean gross |
|---|---:|---:|---:|---:|
| Existing beta0.50 | +763.32% /2.007 /32.7% |2.188 |+14.51% /0.120 /37.2% |93.5% |
| Gross ceiling2.00 only | +963.33% /1.937 /36.5% |2.143 |+11.69% /0.092 /39.6% |103.8% |
| Size0.80 only | +811.83% /2.019 /33.4% |2.118 |+12.98% /0.097 /43.4% |97.4% |
| Both | +1059.97% /1.953 /37.1% |2.138 |+8.69% /0.060 /45.3% |111.8% |
| Positive ranking +5% pre-control name floor | +865.47% /2.045 /37.9% |2.024 |+42.88% /0.246 /38.1% |105.4% |

All four alternatives fail the original recent OOS-Sharpe screen. Small Sharpe gaps do NOT prove inferiority;
larger return with larger drawdown is a risk-preference choice, not evidence of an improved risk-adjusted edge.
The ranking floor's apparent cap-cost stress gain reverses with30bps trading costs: stress return−66.22%, DD70.4%
versus baseline−47.83%, DD57.3%. Financing is charged identically on positive borrowing across calendar days and
feeds back into volatility control; these are assumed rates, not broker quotes. Cash earns no modeled interest.

The user's cash-drag concern is real but distinct from chosen-name quality. On the recent baseline's64 dates below
20% gross, mean exposure was9.8%, conditional account return+0.58% versus SOXX+16.77%; the daily excess attribution
was selection−1.16bps + utilization−26.82bps − trading0.93bps. On the48 active subset dates, the unit-gross same-name
sleeve returned+11.17% before costs versus SOXX+12.76%. Conditional dates are non-contiguous, not a continuous period.
Gross2 alone leaves mean low-day exposure9.7%; size0.8 raises it only12.7%; ranking floor raises it61.3% but increases
risk and turnover. Live paper history has only two sessions, insufficient to infer production selection skill.

Complete reproducibility/decision handoff is `outputs/higher_exposure_20260912/HANDOFF.md`, with runner,
protocol, attribution methodology and six tests beside it. Large frozen prices, daily-model caches, full curves,
`report.md` and `summary.json` stay local. The optional bootstrap/PBO/DSR phase was explicitly NOT run at the user's
immediate wrap-up request; resume analyzer without `--quick` only if requested. No statistical-proof claim is made.
Inherited simulator limits include nondrifting weights, missing-price zero returns, post-band ceiling overshoots
and no actual fill/margin-call feasibility. No research process remains, and no active defaults/orders changed.

## 2026-09-13 — operational decision: the Claude readers get transcript statements only, every name, Opus xhigh

User decision (2026-09-13, no backtest first: the point-in-time `llm_backtest.py` check would cost ~490 Sonnet calls the
subscription does not have this week). Three live changes, effective from the 2026-09-14 cycle once the live checkout is
on main. No sizing, learner or portfolio parameter changed; the beta model activated on 2026-09-12 stays.

1. **Transcript statements only.** `llm_guidance` and `llm_supply` read the graph's pre-extracted statement rows
   (`quarterly_data`: signal up to 500 chars plus figure up to 150 chars per row, 12 newest per company), never a raw
   transcript. Since filings entered the graph, rows sourced from 10-K / 10-Q / 8-K and third-party notes competed for
   the same 12 slots. Measured on the live universe (150 names, 2,833 rows): 1,709 own-call rows, 64 rows from other
   companies' calls, 995 filing rows (431 10-K, 310 8-K, 254 10-Q), 35 analyst/media notes, 30 conference rows (GTC
   Taipei, COMPUTEX). In the guidance window 494 of 1,692 rows were filings or notes, spread over 128 of 150 names;
   dropping them brings 165 call/conference statements back inside the window (1,363 rows after) and raises the abstain
   count only from 1 to 2 names (SHEL has no statements at all). In the supply-chain report (`REPORT_CHARS` = 9,000):
   512 filing statement lines dropped, median report 9,240 to 7,820 chars, reports over the cut 80 to 49, reports whose
   supplier/customer sections fell entirely past the cut 30 to 20. Counterparty deal lines (edges, some sourced from
   10-K) are kept: they are the map, not commentary. Implementation: `agents.base.NOT_TRANSCRIPT` (labels containing
   10-K / 10-Q / 8-K / 20-F / 6-K / 40-F or "note"), applied in `llm_guidance._own_signals` and
   `llm_supply._transcripts_only`; `test_llm_inputs.py` (4 tests). Investing.com conference fireside chats are not in the
   graph rows yet (earnings-ai side); the filter keeps any conference-labelled row automatically once they are.
2. **Every name.** `LLM_MAX_TICKERS` 100 to None: all 150 universe names get the three Claude agents (was: top 100 by
   preliminary |conviction| plus holdings).
3. **Opus xhigh.** `LLM_EFFORT = "xhigh"` (Claude Code levels: low / medium / high / xhigh / max), handed to the local
   server as `LOCAL_CLAUDE_EFFORT_DEEP` when the cycle starts it, together with `LOCAL_CLAUDE_CONCURRENCY` =
   `LLM_WORKERS` (2 to 3). One measured call (NVDA guidance, 12 call rows): 41 s, 5,530 input / 3,061 output tokens,
   versus high 15-19 s / ~3.3k / ~1.1k and max ~100 s / ~6.3k / ~7.5k (server log). Expected cycle: 450 calls, about
   1.7 h with 3 workers (2.6 h with 2), so done near 05:30 PT for the 06:30 PT open; token use per cycle roughly 2.5 M
   input + 1.4 M output, about 2.5x / 4x the 2026-09-11 cycle (300 calls at high). If the subscription window runs out
   mid-cycle, failed calls simply yield no signal for that name (the free agents still trade); `LLM_EFFORT = "high"`
   returns to the prior cost.

Not a research result: no return, IC or Sharpe was measured for this input change; the first live evidence will be the
`llm_guidance` / `llm_supply` scoreboard rows once the 10- and 20-day horizons mature.

## 2026-09-14 — operational decision: price-based agents refreshed on the first trades after the open

User decision 2026-09-14 about 04:45 PT, with SOXX trading 4.7% below Friday's close before the open: signals were computed on
Friday's close while fills happen at the open, so the price-based agents should see the price at order time. Activated the same
morning WITHOUT a backtest (the free daily data has no pre-market history); the backtest comparison is the next item.

What changed (commits `cad125d`, `fafe3d9`):

- Right after the open, `config.OPEN_REFRESH_AGENTS` (technical, mean_reversion, risk, macro, fundamentals, events) re-run on a
  price row built from each name's newest trade (`market.live_prices`: IEX real time or the 15-minute delayed consolidated
  tape; a name with no print today keeps its last close). fundamentals re-prices forward P/E, P/S and analyst-target upside at
  the live price. Their predictions for the day replace the pre-open rows in the ledger (`ledger.replace_predictions`).
- The Claude agents, supply_chain and neighbors keep their pre-open signals: price is one line of the Claude prompts, and
  re-running about 450 xhigh calls takes an hour, so it cannot finish by the open.
- `--reuse-signals` or a `state/reuse_signals` marker re-runs a day from its recorded signals and that day's fitted model: no
  agent re-run and no Claude calls. Tests: `test_open_refresh.py` (4), 23 in total.

How the day ran:

| Step | Time PT | Result |
|---|---|---|
| Scheduled run (the PC was off at 03:30) | 03:43 to 04:43 | all 11 agents; 448 Opus xhigh calls on 3 slots, no failures; 1,383 predictions recorded, then waiting |
| Rehearsal on a copy of the state, pre-market prices (SOXX −4.7%) | 04:44 | names at or above the 0.10 entry bar: 7 before the refresh (ES, EXC, SHEL, APD, D, MMM, ADBE), 0 after; the only order would close SHEL |
| Switch | 04:50 | waiting run stopped before any order, relaunched with the reuse marker |
| Open refresh | 06:30:14 | 151 live prices, SOXX −5.5% vs Friday's close; 6 agents re-ran in under a second; risk 66 to 64 signals |
| Orders | 06:30 | 0 targets; one order: SHEL market sell, 786.6221 shares filled at $97.14 at 09:33 ET |
| After | 06:38 | book all cash, equity $1,007,152; the raw shadow model also had 0 targets |

Why convictions fell: the gap raised a few fundamentals and mean-reversion scores, but risk, macro and technical reacted more
strongly under the learned weights (effective macro −0.08, risk +0.17, technical +0.07). Largest pre-market conviction changes
in the rehearsal: GOOGL −0.094, SNPS −0.093, EXC −0.087, AAPL −0.084, MMM −0.080; the largest rise was MRVL +0.076.

Caveats: the refreshed features are out of sample for a learner fitted on close-based features; walk-forward CV IC is still
negative for both models; one day proves nothing. Noted, not changed: live learning labels start at the prediction day's close
and backtest labels at the signal day's close, while fills happen at the open.

Next: backtest the refresh (price agents see day t+1's open appended before trading at that open) against the next-open
baseline, 500 days, and keep or turn off `OPEN_REFRESH_AGENTS` before the 2026-09-15 cycle.

## 2026-09-14 — round 27: the open refresh backtested (verdict OFF) and the live label start checked

Question (user, 2026-09-14): should the price-based agents see the price at order time instead of the previous close? The
live cycle ran that refresh once the same morning (entry above). Five 500-day replays on the same code (`1b49fc1`), same
data and universe: `--exec open`, daily refits, 5 bps, 150 names, no Claude calls; 470 traded days 2024-09-27 → 2026-08-13;
OOS = before 2025-09-24.

- `--open-refresh`: technical, mean_reversion, risk, macro and events see day t's closes plus a row dated t+1 holding that
  day's opens, then trade at that open. The date-indexed fast paths (hist series, precomputed RSI) are bypassed for those
  calls because they would hand back day t+1's close (`test_backtest_open_row.py`).
- `--label-open`: labels start at the open the refreshed signal saw. `--label-next-close`: labels start at the close of the
  order day, which is what the live scorer (`score.py`) does; the backtest default starts at the close the signals used.
- Runs: tags `_orbase`, `_orrefresh`, `_orrefresh_ol`, `_orbase_nc`, `_orrefresh_nc`; comparison `python analyze_open_refresh.py`
  (output `state/research_labels.txt`).

| Run | Labels start at | Return | Sharpe | Max DD | OOS Sharpe | IS Sharpe | At 30 bps | Deflated Sharpe |
|---|---|---|---|---|---|---|---|---|
| No refresh | the signal close (backtest default) | +900% | 2.14 | 29.7% | 2.38 | 1.86 | +559% / 1.75 | 0.85 |
| Refresh | the signal close | +895% | 2.14 | 31.0% | 2.25 | 2.03 | +558% / 1.75 | 0.85 |
| Refresh | the open it saw | +560% | 1.76 | 38.3% | 1.86 | 1.66 | +341% / 1.38 | 0.69 |
| No refresh | the order-day close (live scorer) | +919% | 2.16 | 26.3% | 2.48 | 1.74 | +572% / 1.77 | 0.85 |
| **Refresh (the live setup of 2026-09-14)** | the order-day close (live scorer) | +712% | 1.96 | 34.0% | 2.03 | 1.89 | +445% / 1.58 | 0.78 |

Paired daily return differences on the same dates:

- Refresh minus no refresh, both with live-scorer labels: −4.88 bps/day, t = −1.18; OOS −11.18 bps/day, t = −2.17; IS +2.10, t = +0.32.
- Refresh minus no refresh, both with signal-close labels: −0.06 bps/day, t = −0.01.
- Refresh with open labels minus no refresh: −8.92 bps/day, t = −2.00; OOS t = −2.06.
- Live-scorer labels minus signal-close labels, no refresh: +0.41 bps/day, t = +0.20.

Reading:

- The refresh matched the baseline only when its labels started at the signal close, so every label contained the overnight
  gap the refreshed signal had already observed and the learner rewarded agents for a move they had seen. With labels that
  start after the information time (the open it saw, or the live scorer's order-day close) it is worse on return, Sharpe,
  drawdown and cost robustness, and significantly worse out of sample.
- The live scorer's later label start is harmless (t = +0.20): `score.py` stays as it is.
- **Verdict: `OPEN_REFRESH_AGENTS = ()` from the 2026-09-15 cycle.** The reuse marker (`state/reuse_signals`) and the backtest
  flags stay. The single live refresh of 2026-09-14 (SHEL closed, book in cash) stands and is not reversed.

Caveats: one 470-day window dominated by one regime; today's universe (survivorship); flat 5 bps; the replay trades exactly
at the official open while the live refresh orders a few seconds later; fundamentals and the Claude agents are not
simulated, so the fundamentals re-pricing that was part of the live refresh is untested.

## 2026-09-15 — round 28: latest price at order time, fitted; conservativeness, negative convictions and shorts checked

User decision 2026-09-15 01:30 PT, after round 27 switched the refresh off: signals must use the latest price, and the model
must be fitted to it by backtesting rather than the refresh being dropped. Round 27 already holds the fit: with the refresh on,
the label start decides the result.

| Refresh on, labels start at | Return | Sharpe | Max DD | OOS Sharpe | IS Sharpe | At 30 bps |
|---|---|---|---|---|---|---|
| the close the signals used (adopted) | +895% | 2.14 | 31.0% | 2.25 | 2.03 | +558% / 1.75 |
| the order day's close (live scorer until 2026-09-14) | +712% | 1.96 | 34.0% | 2.03 | 1.89 | +445% / 1.58 |
| for reference, no refresh, signal-close labels | +900% | 2.14 | 29.7% | 2.38 | 1.86 | +559% / 1.75 |

What changed for the 2026-09-15 cycle:

- `OPEN_REFRESH_AGENTS` back on: technical, mean_reversion, risk, macro, fundamentals, events re-run on the first trades after
  the open (commit `c3979a7`).
- `score.py`: a prediction's label now starts at the close before its date, the close the pre-open signals used, as in the
  backtest. No live score had matured, so no stored score changed. Codex's scorer test keeps its unfinished-label case at
  idx[81]; a new test pins the entry close. Tests: 27 pass.
- Warm start: `state/backtest.sqlite` is now the round-27 refresh ledger (`backtest_orrefresh`: 289,471 predictions, 578,524
  scores, refreshed price-agent features, signal-close labels). The round-22 `_nbfix` warm start is saved as
  `state/backtest_nbfix_warmstart_20260911.sqlite`.
- Preview on a copy of the state (no Claude, no orders): effective weights moved mean_reversion 0.135 → 0.058, supply_chain
  −0.043 → −0.057, macro −0.080 → −0.091, risk 0.171 → 0.177, technical 0.070 → 0.077, neighbors 0.053 → 0.068. Walk-forward CV
  IC stays negative (10d −0.077, 20d −0.053). On the 2026-09-14 signals: old model 0 names at or above the 0.10 entry bar (top NRG
  0.069), new model 1 (SHEL 0.101).

Is the book too conservative? Live cycles: 2026-09-10 bought 15 names, 09-11 sold 15 and bought SHEL, 09-14 sold SHEL. The
same strategy in the 500-day replay has been mostly in cash for four months:

| Replay window (no refresh) | Strategy | SOXX | Mean gross |
|---|---|---|---|
| 2025-09-24 → 2026-05-01 | +125.6% | +77.2% | 0.94 |
| 2026-05-01 → 2026-08-14 | +0.8% | +19.3% | 0.15 |

Monthly replay gross 2026-05 to 08: 0.11, 0.18, 0.19, 0.09, with 1–2 names. The live cash stance is the validated strategy's
regime behaviour, not a live fault. The exposure increases tested in round 26 (gross ceiling 2.0, size 0.8, a positive-rank
floor) all failed the OOS-Sharpe screen, and the user kept the signal-sized structure then. Verdict: leave the sizing as is.
Revisit if live matured rows keep a negative IC after about 20 scored days.

Why convictions are mostly negative (2026-09-14 signals, live model): 20 of 150 names positive, 130 negative, 66 at or below
−0.10; 5/25/50/75/95% quantiles −0.231, −0.142, −0.093, −0.024, +0.039. The structurally bullish map agents are weighted
against: supply_chain mean direction +0.55 but mean contribution −0.065, neighbors +0.43 / −0.056. risk only ever speaks
negative (−0.32 / −0.041) and events −0.020. The largest positive contributors are fundamentals +0.021 and mean_reversion
+0.008.

Shorts: rounds 9 and 18 rejected short books of the 5–10 most negative names (+723% / +671%, Sharpe 1.73 / 1.66 against
long-only +731% / 1.78) and the SOXX hedge as a return source. With walk-forward IC negative, strongly negative convictions
are not a short signal either. Long-only stays.

Rollback, if needed: `OPEN_REFRESH_AGENTS = ()`, `git revert c3979a7` for the label start, and copy
`backtest_nbfix_warmstart_20260911.sqlite` back to `backtest.sqlite`.

## 2026-09-15 — round 29: a more aggressive book: idle cash into SOXX (adopted) vs concentration floors (rejected)

Question (user, 2026-09-15): average exposure of about 15% leaves money idle; be more aggressive, e.g. a higher per-name cap
or more money in the few names that pass the bar. Five 500-day replays on the same day's data and code (`35b35aa` plus the
sleeve), all with the adopted setup of rounds 27–28 (open refresh, labels from the signal close), `--exec open`, daily refits,
5 bps, 150 names, no Claude; prices shared through `BACKTEST_PRICE_CACHE`; comparison `python analyze_runs.py _sz0 _sz1 _sz2 _sz3 _sz4`.

- `MIN_STOCK_BOOK` (`--min-book`): when the sized stock book is below the floor, the names that passed the bar are scaled up
  to it, per-name cap still applied (`--position-cap 0.30`).
- `IDLE_SLEEVE` (`--idle-sleeve SOXX`): the equity the stock book leaves idle goes into SOXX while SOXX closed above its
  50-day average; scaled with the vol target like the book; costs and the rebalance band apply.

| Run | Return | Sharpe | Max DD | OOS return / Sharpe | IS return / Sharpe | 2026-05 on | Mean gross | At 30 bps | Deflated Sharpe |
|---|---|---|---|---|---|---|---|---|---|
| `_sz0` current sizing | +895% | 2.14 | 31.1% | +310% / 2.25 | +143% / 2.03 | +0.9% | 0.91 | +558% / 1.75 | 0.85 |
| **`_sz1` idle cash into SOXX, trend 50 (adopted)** | **+1152%** | **2.26** | 31.8% | +304% / 2.22 | +210% / 2.33 | **+19.7%** | 1.03 | **+713% / 1.87** | **0.89** |
| `_sz2` cap 0.30, floor 0.5 | +844% | 2.07 | 32.0% | +303% / 2.20 | +134% / 1.93 | +1.9% | 0.94 | +511% / 1.67 | 0.83 |
| `_sz3` cap 0.30, floor 1.0 | +780% | 1.98 | 37.8% | +261% / 1.99 | +144% / 2.00 | +3.3% | 0.98 | +447% / 1.54 | 0.79 |
| `_sz4` cap 0.30, floor 0.5, SOXX sleeve | +1079% | 2.21 | 32.7% | +298% / 2.18 | +197% / 2.28 | +18.2% | 1.03 | +648% / 1.80 | 0.87 |

SOXX over the whole window +145%; from 2026-05-01 +19.3%. Paired daily differences against `_sz0`:

- `_sz1`: +5.48 bps/day, t = +1.20; OOS −0.57, t = −1.62; IS +12.18, t = +1.27; 2026-05 on +26.82, t = +0.94.
- `_sz2`: −1.01 bps/day, t = −0.63. `_sz3`: −2.33, t = −0.79. `_sz4`: +4.14, t = +1.00.

Reading:

- Concentration does not help. Few names pass the entry bar in the cash regime, so a floor mostly scales one or two names
  (2026-05 gross only 0.27–0.34) and adds single-name risk: lower return and Sharpe, and a 37.8% drawdown at a floor of 1.0.
  Together with round 17 (exposure floors) and round 26 (gross 2.0, size 0.8), forcing stock exposure is rejected again.
- The trend-filtered SOXX sleeve raises exposure where the book is idle and only while semis are in an uptrend: return
  +257 points, Sharpe +0.12, drawdown +0.7 points, better at every cost level, deflated Sharpe 0.85 → 0.89. The gain sits in
  the IS year and the 2026 cash stretch; OOS is flat to slightly lower (Sharpe 2.25 → 2.22). The screen in round 28 already
  showed why the trend filter matters: the same sleeve without it had a 45% drawdown.
- **Adopted from the 2026-09-15 cycle: `IDLE_SLEEVE = "SOXX"`, fraction 1.0, trend 50.** Cap 0.15 and no stock floor stay.
  On 2026-09-15 SOXX closed 497.40 against a 50-day average of 530.14, so the sleeve starts out of the market.

Caveats: the gain is not statistically significant (t = +1.20) and concentrated in one regime; SOXX is also the benchmark,
so a sleeve-heavy book tracks SOXX by design; the replay trades the sleeve at the open like the stocks.

Addendum 2026-09-15 02:40 PT — macro 10-year-yield unit fix (`agents/macro.py`). Yahoo's ^TNX history is the yield in
percent (4.961 on 2026-09-14), but the rule divided the 20-day change by 10, so its ±0.30-point thresholds never fired. Replay
`_sz5` (the adopted round-29 setup plus the fix) against `_sz1`:

| Run | Return | Sharpe | Max DD | OOS Sharpe | IS Sharpe | At 30 bps |
|---|---|---|---|---|---|---|
| `_sz1` yield rule silent | +1152% | 2.26 | 31.8% | 2.22 | 2.33 | +713% / 1.87 |
| **`_sz5` yield rule fixed (adopted)** | +1158% | 2.27 | 29.4% | 2.23 | 2.35 | +722% / 1.89 |

Paired daily difference +0.02 bps/day, t = +0.01. Adopted as a correctness fix: return unchanged, drawdown 2.4 points lower.

## 2026-09-15 — round 30: cross-asset factor agents (none adopted); review partner and audit findings

Question (user, 2026-09-15): an investor weighs everything (oil, memory prices, CPI, rate-hike odds, bond markets), so add
agents for them and let the learner's weights set each voice. Built eight factor agents (commit `e0805a6`, `agents/factors.py`):
each stock's loading on a factor net of SOXX (OLS over 120 sessions, standardised across the universe) times the factor's
signal (position vs its 50-day average plus its 20-day move over its one-year spread). Factors: WTI (CL=F), fed path
(100 − ZQ=F), 10-year yield, TIP/IEF, HYG/IEF, dollar index, a MU/WDC/SK hynix/Samsung basket vs SOXX, copper. Replays on the
live setup (`_sz5`: refresh, SOXX sleeve, macro fix), 500 days, next-open, 5 bps, no Claude:

| Added to `_sz5` | Return | Sharpe | Max DD | OOS Sharpe | Paired daily t |
|---|---|---|---|---|---|
| nothing (`_sz5`) | +1158% | 2.27 | 29.4% | 2.23 | |
| oil | +933% | 2.07 | 42.3% | 1.95 | −0.82 |
| fed path | +821% | 1.95 | 40.4% | 1.82 | −1.56 |
| long rates | +1095% | 2.22 | 36.0% | 1.97 | −0.24 |
| memory | +979% | 2.08 | 34.4% | 2.10 | −0.74 |
| all eight | +673% | | | | |

Every factor alone made the book worse and raised drawdown; all eight together were the worst. Not adopted. The premise
that the weights will quiet a weak voice does not hold yet: the learner's prior gives every agent an equal share (eight new
agents hold 42% of the prior mass) and live walk-forward CV IC is negative, so a new agent trades at full voice for months
(the same dilution cut +373% to +265% when momentum, SUE and the ML ranker were added on 2026-09-10). Inflation, credit,
dollar and copper were not run alone after the review below.

Review partner critique of the design, to fix before any re-test: KRX closes are known before the US open and must be lagged
a row in both replay and live; asynchronous closes attenuate same-day loadings (use multi-day returns); MU and WDC are in the
universe, so the memory basket must leave each name out of its own factor; CL=F, HG=F and ZQ=F are unadjusted front months
whose rolls fake 20-day moves (use ETFs, ratio-spliced futures, or lagged DGS2); `market.fred_latest` is not point-in-time in
replays (it adds a constant NFCI term on all 470 days); loadings from 120 sessions carry a standard error near 0.27, so shrink
them; long rates duplicate macro's yield rule, HYG/IEF is mostly equity beta, TIP/IEF mostly duration. Gate for any re-test:
paired t ≥ +1 and OOS t ≥ 0, deflated Sharpe on the cumulative trial count, leave-one-factor-out, and new agents entering as
shadow agents with a prior weight of 0 (ledger rows, no vote) until they earn one.

Other review findings and what was done the same morning (commit `8c2e3ae` unless noted):

- **Fixed:** the wait for the open started after all agents and gave up after 120 minutes, so a 03:30 PT start whose agents
  finish by 04:30 would have placed no orders (09-14 only traded after a relaunch): now 240 minutes, and early-exit dashboard
  payloads keep the site's decision history.
- **Fixed:** live VIX / 10-year levels are checked for units only (1/3 to 3x the last close), so genuine spikes pass.
- **Fixed:** at the open, trades printed after 09:30 ET win over pre-market prints, after a short wait for opening prints.
- **Fixed:** the idle sleeve fills only up to the vol target's exposure cap (it used to refill what the vol target cut);
  the replay needs re-running before the sleeve's first buy.
- **Fixed:** a sleeve with no usable closes is left alone instead of sold.
- **Fixed:** the warm start is the `_sz5` replay (macro fix included).
- **Fixed on the branch, merged after the 09-15 orders:** a failed download was cached as an empty column for the day; the
  events agent read a NaN last row; the guardian's one-day news search hit the cycle's cached one-week search.
- **Open, needs a decision or replay:** labels of open-refreshed rows start at the previous close and include the overnight
  gap those signals saw (both reviewers; a "trade on refreshed signals, learn on pre-open signals" hybrid is being designed);
  the sleeve can override the model's bearish cash call with SOXX beta; `plan()`'s gross budget ignores sleeve sales;
  negative CV IC does not down-weight anything; a fresh-start liquidation would trip the foreign-order guard; EXIT_CONVICTION
  is unused; TSM's P/S mixes USD market cap with TWD revenue.

## 2026-09-15 — round 31, pre-registered before any 500-day run: which form of the open refresh

**Why.** Rounds 27–28 kept the open refresh at the user's direction, so every agent works from the latest price. The learner was fitted around it with signal-close labels. Both reviewers then flagged that a refreshed row's label starts at the previous close, so it includes the overnight gap the refreshed signal had already seen.

The review partner showed two things:
- That contaminated label is what pushed mean_reversion's weight down to 0.01 and rescued the refresh run.
- The two runs that traded refreshed features on clean-label weights, `_ol` and `_nc`, were the worst.

**Label, fixed in advance for every candidate run: the order-day open (`--label-open`).** Each row's learning label starts at the open of the order day, the price the book fills at, so no agent is credited with the overnight gap.

The review partner split the 10-day credit on the `_orbase` and `_orrefresh` ledgers into three parts:

| Part of the 10 days | Credit found |
|---|---|
| Overnight gap | Carries the artifact: refreshed mean_reversion −0.23 pooled correlation, refreshed technical +0.11 |
| First session | Genuine: mean_reversion +0.017 pooled whether or not its signal saw the open; macro and risk about −0.02 |
| Days 2–10 | The rest of the horizon |

The order-day close would therefore discard tradable signal.

Caveat: live fills are the 09:30:30 and 09:40 slices, not the official open. One part of refreshed mean_reversion's first-session credit comes from sharing the opening print (about +0.009 rank IC). That part is the least likely to be captured live, which matters for `_g1` and `_g2` but not `_g3`.

**Runs.** Shared settings for all five:
- 500 days, next open, 5 bps.
- SOXX sleeve: fraction 1.0, 50-day trend, 2026-09-15 formula.
- Macro fix, plus the events and closes guards.
- No Claude.

| Tag | Run | Label |
|---|---|---|
| `_g0` | Baseline, no refresh | Order-day open |
| `_g1ref` | Live setup, reference only: refresh with `config.OPEN_REFRESH_AGENTS` | Signal close |
| `_g1` | Refresh with `config.OPEN_REFRESH_AGENTS`: technical, mean_reversion, risk, macro and events replayed; fundamentals not simulated | Order-day open |
| `_g2` | Hybrid: trade on the refreshed signals, record and learn from the pre-open signals (`--learn-preopen`) | Order-day open |
| `_g3` | Refresh without mean_reversion (`--refresh-agents technical,risk,macro,fundamentals,events`) | Order-day open |

Before these runs, 60-day equivalence checks must show three things:
- The patched code reproduces the pre-patch refresh run exactly.
- The hybrid's ledger equals the no-refresh ledger.
- `_g3`'s mean_reversion rows equal the no-refresh rows, and its technical rows equal the refresh rows.

**Gate.** Applied to `_g2` and `_g3` and reported for `_g1`, each against `_g0`. All four must hold:
1. The full-window paired daily t is at least 0.
2. The mean daily difference before 2025-09-24 (OOS) is at least 0.
3. Max drawdown is no more than 2 points above `_g0`.
4. Total return at 30 bps is not below `_g0` at 30 bps.

Reported alongside:
- turnover;
- mean gross;
- names per day;
- share of days whose held set differs from `_g0`, where under 10% means no measurable effect.

**Stop rule.** If `_g2` trails `_g0` by 4 bps/day or more over the full window, the hybrid is rejected and no further label variants are tried.

**Decision rule.** The user requires latest-price signals, so the refresh stays in some form.

A candidate replaces the live setup only if it passes the gate and its full-window paired daily t against `_g1ref` is positive. If both candidates qualify, the one with the higher paired t against `_g0` wins.

Adoption means three changes:
- The candidate's refresh form goes live.
- `score.py` switches to the order-day-open label: entry at the order day's Open, from the same download as the closes. This must land before the first live scores under the current label mature around 2026-09-24, so the live ledger never mixes label definitions.
- The candidate's replay ledger becomes the warm start.

If no candidate qualifies, live stays as is, and the refresh's measured cost (`_g1ref` and `_g1` against `_g0`) is reported. At most these two variants are tried, with no tuning after the results.

### Round 31 results (2026-09-15 04:05 PT): keep the live setup

**Coverage.** 470 common days (2024-09-27 → 2026-08-13), 247 of them before 2025-09-24 (OOS), at 5 bps cost. `_g0` was re-run after its first attempt died: its own model file was momentarily locked while being replaced, likely by a scanner. The retry added in `387e55d` cannot change results.

| Run | Return | Sharpe | Max DD | Return at 30 bps | Held set ≠ `_g0` | vs `_g0` bps/day (t) | OOS bps/day (t) | Paired t vs live |
|---|---|---|---|---|---|---|---|---|
| `_g0` no refresh, order-day-open label | +1117% | 2.22 | 31.9% | +700% | — | — | — | +0.17 |
| `_g1ref` live: refresh, signal-close label | +1084% | 2.24 | 28.8% | +676% | 92% | −0.91 (−0.17) | −5.24 (−0.77) | — |
| `_g1` refresh, open label | +761% | 1.91 | 36.0% | +467% | 85% | −7.40 (−1.73) | −11.72 (−2.12) | −1.49 |
| `_g2` hybrid, open label | +780% | 1.93 | 36.3% | +482% | 82% | −6.93 (−1.68) | −12.60 (−2.52) | −1.31 |
| `_g3` refresh without mean_reversion, open label | +812% | 1.99 | 33.7% | +501% | 77% | −6.34 (−1.70) | −7.24 (−1.47) | −1.42 |

Across all five runs, turnover was 0.35–0.36 per day, mean gross 1.00–1.03, and names held 11.4–11.7.

**Gate outcome.**
- `_g2` (hybrid) fails all four conditions. At −6.9 bps/day against `_g0` it trips the stop rule, so the hybrid is rejected and no further label variants will be tried.
- `_g3` fails three of four; only the drawdown condition holds.
- `_g1` fails all four.
- **Decision, as pre-registered: keep the live setup. No config change.**

**Reading.**
- Under a label that credits no agent with the overnight gap, every form of the open refresh loses 6–7 bps/day to no refresh.
- Taking mean_reversion out of the refresh recovers little (−6.3 against −7.4 bps/day). The refreshed technical, risk, macro and events signals also cost money once the learner weights them on clean labels.
- The hybrid, which trades on refreshed signals with weights learned before the open, behaved as the review partner predicted from `_ol` and `_nc`.
- The live setup is statistically indistinguishable from the clean no-refresh baseline: −0.9 bps/day (t −0.17), with a lower drawdown (28.8% against 31.9%). Its signal-close label keeps the refreshed signals' weights low enough that the refresh costs nothing measurable.
- The refresh therefore stays live. The user requires latest-price signals, and in its live form the refresh is harmless. That harmlessness comes from the label artifact, so any future label change must be tested against a no-refresh baseline, not assumed safe.

**Other findings.**
- **Changes since round 29.** `_g1ref` (+1084%, drawdown 28.8%) uses the same flags as `_sz5` (+1158%, 29.4%). Two code changes separate them: the 2026-09-15 sleeve formula, which fills idle equity only up to the vol target's exposure, and the events data guards. Together they cost 74 points of total return and lowered drawdown by 0.6 points.
- **Caveat.** This is one 470-day window in one regime. A paired t of −1.7 is not decisive on its own; the gate and the stop rule were fixed before the runs.

**Round 31 addendum (review partner, 04:20 PT).**

- **The 74-point gap between `_sz5` and `_g1ref` is entirely the sleeve formula.** The two prediction ledgers are identical (289,471 rows), and the return difference sits on the 101 days where the sleeve differs:

  | Window | Difference, bps/day | t |
  |---|---|---|
  | Full | −1.42 | −1.76 |
  | OOS | +0.46 | +1.75 |
  | In-sample | −3.51 | −2.11 |

  Max drawdown moves from 29.4% to 28.8% and Sharpe from 2.27 to 2.24. Capping the sleeve at the vol target's exposure is a risk-policy choice, not a correctness fix. It stays, because a vol cap the sleeve can override is not a cap, and it is flagged to the user as their call.
- **"Keep live" means "no measurable cost".**
  - Daily differences have a spread of 118 bps, so the gate detects only effects of about 11 bps/day.
  - Every OOS refresh comparison since round 27 has been negative. Live-label forms ranged from −2.7 to −11.2 bps/day, though they reuse the same OOS days.
  - The replay fills at the exact open the refreshed signals saw, which flatters the refresh.
- **The refresh and the signal-close label are coupled.** The comments in `config.py` and `score.py` now say so: neither changes alone.
- **Cheapest forward evidence, planned for after the live freeze:** record each day's pre-refresh book as a shadow target set and compare it with the live book after about 60 sessions.

## 2026-09-15 — round 32, pre-registered before any run: does the re-weighting learner add value?

**Why.** Both open requests from the user assume the stacking learner's fitted weights beat a fixed equal-weight blend: agents that improve themselves under a learner that keeps re-weighting them, and more agents whose voices the learner sets. Round 31's reports do not show that:
- With the clean label (`_g0`), the learned 10-day IC (0.0151) is below the equal prior's (0.0184).
- `_g1ref`'s 0.026 against 0.013 is measured on the gap-contaminated label.
- Walk-forward CV IC is negative in every run.

The review partner therefore ranked this ablation ahead of any new agent or per-agent learning.

**Runs.** Both use 500 days, the round 31 flags and the same price cache.

| Tag | Flags | What it is |
|---|---|---|
| `_l0` | `_g0` flags + `--prior-only` | No refresh, order-day-open label |
| `_l1` | `_g1ref` flags + `--prior-only` | The live setup: refresh, signal-close label |

`--prior-only` trades on the equal-weight prior blend. The learner is still fit every day, and every curve day records both 10-day ICs.

**Checks.** `_l0`'s prediction ledger and mean learned IC must equal `_g0`'s, and `_l1`'s must equal `_g1ref`'s. Trading does not feed back into signals or fits.

**Conclusion rule.** This decides research direction only; no live change comes from this round. Learning "helps" on a flag set when all three hold:
1. The learned book's paired daily t against the prior-only book is at least +1.0 over the full window.
2. Its OOS mean difference (before 2025-09-24) is above 0.
3. The learned 10-day IC exceeds the prior's in both halves, before and after 2025-09-24.

For `_l1` that IC is on the signal-close label and is reported with that caveat. The clean-label pair (`_g0` against `_l0`) decides.

**What follows.**
- If learning helps there: per-agent learning (Stage B) and learned weights for new agents stay on the plan.
- If it doesn't: Stage B is deprioritised, and new agents enter with weights fixed in advance.

Changing the live learner would need its own pre-registered test and forward shadow data. This round adds two trials to the count.

### Round 32 results (2026-09-15 04:35 PT): the fitted weights make the book; their gain is in the top of the ranking, not in whole-universe IC

**Run notes.** The replays ran one at a time after the live Claude stage. A first attempt ran two in parallel during that stage; it was killed for low memory before it had written anything. Both checks passed: each prior-only run's ledger and mean ICs equal its learned twin's.

| Flags | Book | Return | Sharpe | Max DD | Gross | Names | Turnover | Top-15 rank book |
|---|---|---|---|---|---|---|---|---|
| Clean label, no refresh | `_g0` learned | +1117% | 2.22 | 31.9% | 1.01 | 11.5 | 0.36 | +818% (Sharpe 2.09) |
| | `_l0` equal-weight prior | +157% | 1.00 | 37.0% | 0.93 | 11.0 | 0.58 | +246% (1.31) |
| Live flags | `_g1ref` learned | +1084% | 2.24 | 28.8% | 1.00 | 11.7 | 0.36 | +792% (2.08) |
| | `_l1` equal-weight prior | +219% | 1.23 | 34.4% | 0.94 | 11.0 | 0.59 | +278% (1.40) |

**Learned minus prior, paired daily returns:**

| Pair | Full window, bps/day (t) | OOS (t) | In-sample (t) |
|---|---|---|---|
| Clean label | +35.4 (+2.47) | +57.7 (+2.69) | +10.7 (+0.57) |
| Live flags | +30.0 (+2.06) | +50.0 (+2.42) | +7.8 (+0.38) |

**10-day IC across all names:**

| Label | OOS learned / prior | In-sample learned / prior |
|---|---|---|
| Clean | −0.0092 / +0.0052 | +0.0420 / +0.0331 |
| Live (signal-close) | +0.0116 / −0.0007 | +0.0420 / +0.0278 |

**Pre-registered verdict: "learning helps" is not demonstrated** on the deciding clean-label pair. The P&L conditions pass by a wide margin, but the learned IC is below the prior's in the OOS half. On the live flags all three conditions pass, though that IC is measured on the contaminated label.

**Reading.**
- The fitted weights are what make the book work. Trading the equal-weight blend instead cuts +1117% to +157%. It also cuts the top-15 rank book (name selection only, no sizing) from +818% to +246%.
- The gain sits in the top of the ranking. The learned conviction quintiles' 10-day abnormal returns run −0.02%, +0.32%, +0.27%, +0.28%, +1.39%.
- The IC criterion measured rank correlation across all 150 names, which is the wrong yardstick for a long-only book of about 11 names. This is recorded, not used to overturn the verdict.

**Consequences, as pre-registered.**
- No live change.
- Per-agent learning (Stage B), which would add fitted parameters, is deprioritised.
- New agents enter as shadow agents at a fixed weight of 0, and gain a vote only through a later pre-registered promotion test.
- From now on, signal-quality gates measure the top of the ranking, fixed before the runs: the top-15 rank book and the top-minus-bottom quintile spread on the order-day-open label.

**Round 32 addendum (review partner, 04:45 PT).** The partner regressed the learned-minus-prior daily return gap on SOXX. The figures below are for the clean-label pair; the live pair is similar.

**What explains the 35 bps/day gap.**
- **Not turnover or exposure level.**
  - The prior book's extra turnover costs about 1.1 bps/day.
  - Over the full window, gross exposure (1.01 against 0.93) and beta (1.00 against 0.96) are close.
- **About two thirds is selection.**
  - The top-15 rank book, which ignores sizing, is ahead by 22 bps/day with near-zero beta.
  - Its SOXX-adjusted alpha is +22 bps/day (t 1.8), similar in both halves: OOS +25 (t 1.6), in-sample +27 (t 1.6).
  - Part of this is still a regime-dependent beta tilt: the rank-book difference has beta +0.45 OOS and −0.32 in-sample. That fits the learner giving more weight to signals that act through beta, such as macro and risk.
- **About one third (≈13 bps/day) is exposure timing.**
  - The sized book's beta flips between halves: OOS learned 1.15 against prior 0.62; in-sample 0.91 against 1.21.
  - The flip comes through conviction magnitudes, reliability scaling and the sleeve.
  - It helped in both halves here, but it depends on the path the market took.

**Recorded finding.** About 22 bps/day of beta-adjusted selection, plus a regime-dependent exposure component. The pre-registered verdict ("not demonstrated") stands.

**Future signal-quality gates.** This replaces the yardstick named above before it is used anywhere.
- The gate measures the top-15 rank book minus the equal-weight universe, on beta-adjusted returns. Equivalently, the rank-book difference's alpha after regressing on SOXX.
- It passes at t ≥ 1 with the same sign in both halves.
- The sized book's alpha and beta by half are reported alongside.

**Freeze.** The learner and its warm start carry the edge, and part of that edge is exposure set by regime. Changing the label, warm start, agent set, λ or sizing can therefore change live exposure even when selection looks unchanged. The live configuration stays frozen. Once the live book has built up, compare its realised beta and gross against the replay (OOS beta 1.15).

## 2026-09-15 — round 33, pre-registered before any run: a market-neutral long-short book

**Why.** The user wants the book to keep taking positions instead of sitting in cash for days, and asked to trade long and short together (2026-09-15 07:20 PT).

Earlier short tests (rounds 9 and 18) only added a short book of the 5–10 most negative names to the long-only book, and they lost. A market-neutral book that always holds the day's relative winners long and relative losers short has not been tested. It is the one form that still trades on a day like 2026-09-15, when every conviction is negative because the two graph agents shift every name down together.

This round does not change what the learner learns from. Predictions for all 150 names are recorded and scored whether or not they are traded.

**Design.** Replay only; no live change before a pass. Same flags and price cache as `_g1ref` (the live setup: refresh, signal-close label), 500 days, next-open execution, 5 bps trading cost.

1. **Selection.** Rank the day's convictions. Long the top N names equally and short the bottom N equally.
2. **Size.** Each leg is `GROSS_TARGET / 2` = 0.75 of equity, so gross stays at the existing 1.5 ceiling. Both legs scale down with the 50% vol target like the live book.
3. **Beta.** The short leg is resized so the book's beta to SOXX is about zero, using each name's point-in-time rolling beta. The resize factor is bounded to 0.5–2x.
4. **Costs.** Short stock positions pay 2 bps/day borrow, about 5%/yr, the replay's existing short convention. This comes on top of trading costs.
5. **Other rules.**
   - No SOXX sleeve.
   - The rebalance band applies to both legs.
   - All 150 names are assumed shortable. This is optimistic: some small caps are hard to borrow.

| Tag | Setup | Role |
|---|---|---|
| `_mn1` | N = 10 per leg | decides |
| `_mn2` | N = 15 per leg | robustness check |

**Gate for adopting `_mn1`, against `_g1ref`.** All five conditions must hold:
1. Higher total return over the full window.
2. Higher Sharpe over the full window.
3. Mean daily difference before 2025-09-24 (OOS) of at least 0.
4. Total return at 30 bps not below `_g1ref`'s at 30 bps.
5. `_mn2`'s full-window mean daily difference has the same sign as `_mn1`'s.

**Reported alongside:**
- max drawdown;
- beta and correlation to SOXX;
- mean gross, net and short exposure;
- turnover;
- the beta-adjusted alpha of the daily difference.

**Afterwards.**
- **If it passes:** live support for shorts is built and applied from the next cycle, and the user is told the measured numbers. That support means portfolio sizing, Alpaca shortability and borrow checks, guards, tests and partner review.
- **If it fails:** live stays long-only. No N tuning after the results.
- Either way this round adds two trials to the count.

**Round 33 amendment (07:45 PT, before any result).**

**The error in the first code.** The review partner found that the first implementation (`f359677`) did not keep the pre-registered gross. It sized each leg at 0.75 of equity and then resized the short leg by the beta ratio. Gross could therefore range from 1.13 to 2.25, and the book could run net short in dollars, so a pass could have been leverage.

**The correction**, made to the stated design before any result was seen:
- The book's gross is `GROSS_TARGET` × vol scale, split so the legs' betas cancel: long G/(1+r), short G·r/(1+r).
- Non-finite convictions are ignored.
- Each curve day records the long and short legs' returns.

The two runs started under the first code were stopped unread. They are replaced by `_mn1b` (N = 10, decides) and `_mn2b` (N = 15, robustness).

**Stricter conditions.** These were added before any result. A pass must meet the original five conditions plus:

6. The book's realised SOXX beta is within ±0.25 in both halves, before and after 2025-09-24. A pass with material beta is a beta bet, not a market-neutral result.
7. Before any live adoption, a confirmation run must also beat the live setup on return and Sharpe. That run restricts shorts to names Alpaca flags shortable and easy-to-borrow today, and charges 10 bps/day borrow on the smaller half of the universe by market cap. This is a proxy, not point-in-time, and it is run only if conditions 1–6 pass.

**Also reported:** the short leg's own beta-adjusted return per unit of short exposure. This is the clean test of whether the short signal adds anything, separate from the live comparison, which mostly measures beta in a +145% SOXX window.

### Round 33 results (2026-09-15 07:40 PT): the market-neutral long-short book fails; live stays long-only

**Setup.** 470 common days at 5 bps, with the same flags and price cache as `_g1ref`.

| Run | Return | Sharpe | Max DD | Return at 30 bps | Beta (OOS / IS) | Gross | Net | Short | Turnover | Names |
|---|---|---|---|---|---|---|---|---|---|---|
| `_g1ref` live long-only | +1084% | 2.24 | 28.8% | +676% | 0.95 (1.11 / 0.84) | 1.00 | +1.00 | 0.00 | 0.36 | 11.7 |
| `_mn1b` N = 10 (decides) | +70% | 0.74 | 30.8% | −26% | 0.14 (0.28 / 0.04) | 1.48 | +0.16 | 0.66 | 0.71 | 20 |
| `_mn2b` N = 15 | +90% | 1.03 | 21.9% | −10% | 0.09 (0.20 / 0.03) | 1.49 | +0.15 | 0.67 | 0.63 | 30 |

**Against live** (paired daily return difference, and alpha against SOXX):

| Run | Full window, bps/day (t) | OOS (t) | In-sample (t) | Book alpha vs SOXX (t) |
|---|---|---|---|---|
| `_mn1b` | −45.4 (−3.47) | −38.7 (−2.18) | −52.8 (−2.71) | +11.3 (+1.01) |
| `_mn2b` | −43.9 (−3.36) | −42.2 (−2.34) | −45.9 (−2.41) | +13.7 (+1.41) |

**The short leg on its own.** Its beta-adjusted return per unit of short exposure was −6.6 bps/day (t −0.65) in `_mn1b` and −6.1 (t −0.69) in `_mn2b`. The names the model ranks worst did not underperform their beta, so shorting them lost money.

**Gate outcome.** `_mn1b` fails conditions 1, 2, 3, 4 and 6 (its OOS beta was 0.28). Only condition 5 holds: `_mn2b` agrees in sign.

**Decision, as pre-registered:**
- Live stays long-only.
- No N tuning.
- The confirmation run (condition 7) is not needed.

**Reading.**
- The model's skill is in picking the top names (round 32), and its bottom ranks carry no short signal.
- The market-neutral book therefore sets the long leg's alpha against a losing short leg and doubles turnover.
- It also gives up the benchmark's +145% over the window.
- The gross cap and beta matching worked as designed (mean gross 1.48, beta 0.09–0.14), so the failure is the strategy, not the implementation.

**Also recorded.** The user asked beforehand whether concentrating into one or two heavily weighted names would do better. Round 29 already tested that: a per-name cap of 0.30 with book floors made +844% and +780%, against +895%, with drawdown up to 37.8%, and was rejected. A 2-names-per-leg long-short run (`_mn3`) follows. It is exploratory and not part of the gate.

## 2026-09-15 — round 34, pre-registered before any replay: is the SOXX sleeve's 50-day trend rule robust?

**Why.** The user asked whether holding SOXX with idle cash is overfitting, or simply too crude. Round 29 adopted the sleeve on weak evidence:
- +5.5 bps/day, t +1.20, over the full window;
- −0.6 bps/day, t −1.62, out of sample;
- the gain was concentrated in the 2024–26 rally.

**25-year check of the timing rule on its own.** SOXX from its 2001 listing to 2026-09-15. The signal is decided at close t and held over day t+1, with 5 bps per switch and cash earning 0.

| Rule | CAGR | Sharpe | Max DD | Days invested |
|---|---|---|---|---|
| buy & hold | +13.7% | 0.55 | 70.2% | 100% |
| above 20-day average | +2.9% | 0.24 | 49.6% | 58% |
| **above 50-day average (live)** | +5.5% | 0.35 | 56.2% | 62% |
| above 100-day average | +8.5% | 0.48 | 45.8% | 66% |
| above 200-day average | +11.0% | 0.59 | 42.2% | 66% |

**What it shows.**
- The live 50-day rule loses to buy-and-hold on both return and Sharpe over the 25 years. It also loses in 2009–2015 (Sharpe 0.42 against 0.80) and 2016–2021 (0.71 against 1.20) taken separately.
- It protected somewhat in 2001–2008 and 2022–2026.
- Only the 200-day rule matches buy-and-hold on Sharpe, and it does so with a much smaller drawdown.
- The 50-day window was a convention and was never tuned. The risk is therefore regime overfitting (one bull market), not parameter fitting.
- On 2026-09-15 SOXX, at 499.71, is 5.4% below its 50-day average and 14.0% above its 200-day average. A 200-day sleeve would be invested today.

**Runs.** 500 days with the live flags and price cache; only the sleeve differs.

| Tag | Sleeve | Status |
|---|---|---|
| `_sl0` | off (`--sleeve-fraction 0`) | new |
| `_g1ref` | 50-day rule (live) | already run |
| `_sl200` | 200-day rule (`--sleeve-trend 200`) | new |

**Decision rule.** No other window is tried. Checks are applied in this order:
1. If `_sl0`'s Sharpe is at least the better sleeve run's Sharpe, the sleeve is switched off: it adds risk without adding risk-adjusted return.
2. Otherwise, if `_sl200`'s Sharpe is at least `_g1ref`'s and its max drawdown is no more than 2 points higher, the 200-day rule replaces the 50-day rule. The 25-year check already favours 200 over 50.
3. Otherwise the live 50-day sleeve stays.

This round adds two trials to the count. The live config changes only after the user is told the numbers and agrees.

### Round 34 results (2026-09-15 07:58 PT): keep the live 50-day sleeve (a near tie)

**Setup.** 470 common days, with the live flags and price cache.

| Run | Return | Sharpe | Max DD | Mean sleeve | All-cash days | vs live, bps/day (t) | OOS (t) |
|---|---|---|---|---|---|---|---|
| `_sl0` sleeve off | +911% | 2.17 | 28.0% | 0.00 | 31 | −3.8 (−0.92) | +0.4 (+1.38) |
| `_g1ref` live 50-day sleeve | +1084% | 2.24 | 28.8% | 0.10 | 15 | — | — |
| `_sl200` 200-day sleeve | +1123% | 2.23 | 28.3% | 0.14 | 6 | +0.9 (+0.28) | +0.3 (+1.02) |

**Decision, as pre-registered: keep the live 50-day sleeve.**
- **The sleeve stays.** Sleeve off has a lower Sharpe than the better sleeve (2.17 against 2.24).
- **The 200-day rule is not adopted.** Its Sharpe is 0.01 below the 50-day rule's, so condition 2 fails.

**Reading.**
- In this window the three runs are statistically indistinguishable: every difference is within |t| < 1.4.
- The 200-day rule made slightly more, with a slightly lower drawdown and fewer than half the all-cash days.
- The 25-year check favours the 200-day rule clearly: Sharpe 0.59 against 0.35, max drawdown 42% against 56%.
- The pre-registered rule still keeps 50 days, because the 200-day replay Sharpe is 0.01 lower.
- A switch is therefore the user's call, not a research result: a change on a tie in the replay, backed only by the long-history check.

**Exploratory (user question, not a gate).** Concentrating the market-neutral book into 2 names per leg (`_mn3`) lost money:
- −7% over 470 days, Sharpe −0.08, max drawdown 45.1%;
- −73% at 30 bps;
- −55.5 bps/day against live (t −3.46).

This confirms round 29: this model's edge needs breadth.

**User decision (2026-09-15, 07:55 PT).** After seeing the numbers above, the user chose to switch the sleeve to the 200-day rule and to buy SOXX today.

By the pre-registered rule the 50-day sleeve would have stayed, because the 200-day replay's Sharpe was 0.01 lower. The switch is therefore the user's decision on a tie in the replay, backed by the 25-year check.

Live change: `IDLE_SLEEVE_TREND = 200`. SOXX, at 499.71, is 14.0% above its 200-day average, so the sleeve is invested from today's re-run of the cycle. The re-run uses the signals recorded this morning and makes no Claude calls.

## 2026-09-15 — round 35, pre-registered before any replay: which vehicle should idle equity default to?

**Why.** After the sleeve moved to the 200-day rule, the user asked whether SOXX is the right default at all, whether an ETF mix would be better, and whether "hold the sector index and trade on top of it" is a sound structure for a fund.

**Framing, stated before the numbers.** The stock universe is the semiconductor supply chain and the benchmark is SOXX, so the fund is a semiconductor fund whether or not the sleeve exists. The sleeve only decides what the fund holds when the model has no pick: the sector index (a benchmark-neutral sector fund), cash (an absolute-return fund), or something in between. That is a mandate choice for the user. The replays measure what each choice cost over 2024–26, and the 25-year ETF check shows how each vehicle behaved through two crashes.

**Runs.** 500 days, the live flags and price cache, 200-day gate throughout; only the idle vehicle differs.

| Tag | Idle vehicle | Status |
|---|---|---|
| `_sl0` | cash (sleeve off) | already run |
| `_sl200` | SOXX, all idle equity (live since today) | already run |
| `_sxh200` | SOXX, half the idle equity, the rest cash | new |
| `_sp200` | SPY, all idle equity | new |
| `_mix200` | SOXX and SPY, half each, each on its own 200-day gate | new (`--sleeve-mix SOXX,SPY`) |

QQQ is not in the replay's price set, so it appears only in the 25-year check.

**Rule.** No automatic adoption: the user chooses the mandate. The recommendation I will give is fixed here: rank by Sharpe; prefer a lower-volatility vehicle only if its Sharpe is within 0.05 of the SOXX sleeve's and its max drawdown is at least 3 points lower. The replay assumes cash earns 0, which understates every cash-heavy variant by roughly 4–5% a year over this window; that is noted, not corrected. This round adds three trials to the count.

### Round 35 results (2026-09-15 23:58 PT): keep SOXX as the idle vehicle

470 common days, live flags, 200-day gate on every sleeve.

| Run | Idle vehicle | Return | Sharpe | Max DD | Return at 30 bps | Mean sleeve | All-cash days | vs SOXX sleeve, bps/day (t) | OOS (t) |
|---|---|---|---|---|---|---|---|---|---|
| `_sl200` | SOXX (live) | +1123% | 2.23 | 28.3% | +702% | 0.14 | 6 | — | — |
| `_sxh200` | SOXX, half the idle equity | +1024% | 2.24 | 28.2% | +643% | 0.07 | 6 | −2.3 (−0.89) | +0.1 (+1.01) |
| `_mix200` | SOXX + SPY, half each | +1020% | 2.22 | 30.6% | +631% | 0.15 | 2 | −2.3 (−0.98) | −1.3 (−2.01) |
| `_sl0` | cash | +911% | 2.17 | 28.0% | +574% | 0.00 | 31 | −4.7 (−0.90) | +0.2 (+1.01) |
| `_sp200` | SPY | +908% | 2.16 | 32.9% | +555% | 0.16 | 2 | −4.7 (−0.99) | −2.6 (−2.01) |

**Decision by the pre-registered rule: keep SOXX.** No lower-volatility vehicle has both a Sharpe within 0.05 of the SOXX sleeve's and a max drawdown at least 3 points lower. The half-SOXX sleeve matches on Sharpe (2.24) but lowers the drawdown by only 0.1 point at a cost of 99 points of return.

**Reading.**
- The 25-year ETF check and the strategy replay disagree on drawdown, and the replay is the pre-registered evidence. Over 25 years a SOXX+broad-index mix cut the sleeve's own drawdown by a third; inside the strategy, over 2024–26, the mix and the SPY sleeve had *higher* drawdowns (30.6% and 32.9% against 28.3%).
- The reason is gate timing. *(Corrected below: the divergence window was 2025-02-21 to 03-10, before the April crash, during which both gates were off.)* SOXX fell through its 200-day average before SPY did, so the SOXX sleeve was out while a SPY-gated sleeve was still invested. For a semiconductor book, the semiconductor index's own trend is the better exit signal for its idle money.
- Out of sample the mix lost 1.3 bps/day to the SOXX sleeve (t −2.0), the one statistically clear difference in the table.
- Sleeve off costs about 200 points of return over the window at a similar Sharpe (2.17 against 2.23), which restates round 34.
- Caveat, as before: the window holds one bull market and one sharp crash, and cash earns 0 in the replay.

**Follow-ups.**
- The multi-ETF sleeve code written for this round stays unapplied (`tmp/patch_round35b.py`); a future mix would need its own pre-registered test.
- One part of that patch is a live bug fix independent of the vehicle: `plan()` counts a sleeve sale made in the same cycle toward the stock book's buy budget, so a re-entry day is not capped by a sleeve about to be sold (audit item; material now that the sleeve is about 100% of equity). It goes to the branch with a test and a review, and live after a rehearsal.

**Correction (review partner, 2026-09-16 00:20 PT).** The mechanism stated above is wrong in one respect. SPY's 200-day gate was also OFF through all of April 2025 (2025-03-10 to 05-12, briefly on 03-24/25). The difference between a SOXX-gated and a SPY-gated sleeve in the replay is that SOXX crossed first: its gate was OFF from 2025-02-21 while SPY's stayed ON until 03-10, about 12 sessions in which a SPY-gated sleeve stayed invested as semiconductors fell, plus SOXX's May whipsaw (ON 05-13, OFF 05-19, ON 06-03). The replay verdict therefore rests on one episode of about 12 sessions, not on a general property of the vehicles. The decision stands under the pre-registered rule; the record is corrected so the wrong mechanism is not carried forward.
