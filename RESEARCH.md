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

## 2026-09-16 — round 36, pre-registered before any result: an external regime identifier for the stock book

**Why.** The strategy's one structural weakness is known since 2026-09-11: the price stack that made +1100% in 2024–26 lost money from 2019 to 2023 (−17%, Sharpe −0.14, max DD 43%). Round 21 showed that gates driven by the strategy's own P&L whipsaw in the bad years, and concluded that only something identifying the regime *ahead of time* could help. Nothing external has been tested. The user asked on 2026-09-16 for the most valuable improvements; this is the first.

**What is screened.** Nine indicators, each known at close t, gating the stock book decided at that close (the SOXX sleeve keeps its own 200-day gate and is excluded from the screen):

| Indicator | Risk-on when |
|---|---|
| breadth 200 | more than half the universe closes above its 200-day average |
| breadth 50 | more than half above its 50-day average |
| SOXX > 200d | SOXX above its 200-day average (the sleeve's rule, applied to stocks) |
| SOXX/SPY RS | SOXX outperformed SPY over 60 sessions |
| VIX | VIX below its 200-day average |
| credit | HYG/IEF above its 200-day average |
| rates | 10-year yield lower than 63 sessions ago |
| SOXX vol | SOXX 20-day realised vol below its 1-year median |
| breadth 200 & SOXX > 200d | both |

Two modes each: stocks to cash (OFF) or halved (HALF). 18 trials.

**Data.** The 2019–23 window is a fresh replay of the live setup restricted to the five price agents (`_pre2024b`: 1,200 days ending 2023-12-29, next-open, open refresh, SOXX 200-day sleeve). The 2024–26 window is `_sl200`. The screen gates the replay's daily stock-leg return offline; it ignores the vol target's reaction and learner effects, so a winner gets a real replay before anything else.

**Selection rule, fixed now.** A gate passes only if, against the ungated stock legs:
1. 2019–23 Sharpe improves by at least +0.30;
2. 2024–26 total return stays at or above 85% of ungated and Sharpe within 0.15;
3. at most 12 switches a year in both windows.

Among passing gates the one with the highest 2019–23 Sharpe is replayed for real on both windows. The replay must reproduce condition 1 and 2 to be adopted; adoption goes live only after the user is told and the live freeze period has run. If nothing passes, the record says so and the item is closed.

**Caveats.** Survivorship favours the 2019–23 replay (today's 150 names). Eighteen trials count toward the deflated Sharpe of anything adopted. The 2019–23 window has no graph or Claude signals.

### Round 36 results (2026-09-16 01:00 PT): no external regime indicator passes; the item is closed

**The 2019–23 replay under the live setup** (`_pre2024b`: five price agents, next-open, open refresh, beta-adjusted target, SOXX 200-day sleeve, 1,170 days 2019-04-09 → 2023-11-29):

| | Return | Sharpe | Max DD |
|---|---|---|---|
| whole book (sleeve averaged 0.39 of equity) | +63% | 0.34 | 32.5% |
| stock legs only, gross of costs | +28% | 0.34 | 26% |
| the 2026-09-11 v2.3 replay of the same window, for reference | −17% | −0.14 | 43% |

The stock book under today's rules is weakly positive in the window where v2.3 lost. What changed since 09-11: the beta-adjusted learning target, the open refresh with its label, the macro yield fix, the events guards and the sleeve. Survivorship (today's 150 names) favours both replays equally. One window; not a claim of edge.

**The screen** (18 trials: nine indicators × OFF/HALF, gating the stock legs offline). Ungated: 2019–23 +28% / 0.34 / 26%; 2024–26 +996% / 2.49 / 27%.

| Indicator | Mode | 2019–23 return / Sharpe / DD | 2024–26 return / Sharpe / DD |
|---|---|---|---|
| SOXX 20d vol below 1y median | OFF | +27% / 0.41 / 23% | +157% / 1.71 / 25% |
| VIX below 200d | OFF | +28% / 0.39 / 27% | +81% / 1.06 / 40% |
| breadth 200 > 50% | HALF | +23% / 0.32 / 21% | +816% / 2.48 / 23% |
| SOXX > 200d | HALF | +19% / 0.28 / 21% | +659% / 2.45 / 26% |
| SOXX/SPY 60d RS | HALF | +17% / 0.27 / 24% | +607% / 2.52 / 19% |
| all others | | worse than ungated in 2019–23 | −30% to −70% of the 2024–26 return |

No gate reaches the pre-registered +0.30 Sharpe improvement in 2019–23; the two that improve Sharpe at all (+0.05 to +0.07, the volatility gates) cut the 2024–26 return by 84–92%. The rest lower both windows.

**Reading.** The same conclusion as round 21, now for external signals too: the weak years are choppy, and any gate that switches the book off also switches off the recoveries. The stock book's protection in bad years comes from what it already does (small books, cash as a position, the vol target), and the sleeve's own 200-day rule handles the idle money. The item is closed; no gate goes forward to a replay. Eighteen trials are added to the count.

## 2026-09-16 — round 37, pre-registered before any run: a rank learning target, with the conviction scale held fixed

**Why.** Round 32 found the learner's value at the top of the ranking while whole-universe IC is about 0.02, and the learner's walk-forward criterion is already a rank correlation. A model fitted on per-date ranks of the beta-adjusted return may order names better. The review partner's design (2026-09-16) removes the confound that such a model changes the conviction *scale* and therefore the sizing: the return model's conviction values are kept as a daily multiset and assigned to names in the rank model's order (quantile mapping), so gross, vol scaling and the sleeve are identical by construction and only the ordering changes.

**Runs.** Live flags (`_sl200`: 500 days, next-open, open refresh, signal-close label, SOXX 200-day sleeve), one shared price cache.

| Tag | Change | Role |
|---|---|---|
| `_sl200` | none | baseline (already run) |
| `_rk1` | `--rank-order`: a second ridge fitted daily on per-date normal scores of the beta-adjusted 10/20-day return (no ±15% winsor); names take the return model's conviction values in the rank model's order | candidate |
| `_cl1` | `--target-clip-sigma 2.5`: the return target clipped at ±2.5σ per horizon instead of ±15% | control: the cheap "robust to tails" version |

**Gate for `_rk1`, all required:**
1. Per-date sorted convictions equal the baseline's to 1e-12 (asserted in the replay; proves the confound is gone).
2. The rank model's daily realised 10-day IC is at or above the return model's on the same dates.
3. Sized-book paired daily difference against `_sl200` ≥ 0 over the full window and OOS (before 2025-09-24).
4. Turnover at most 1.2× the baseline's, or the return at 30 bps not lower.
5. The round 32 yardstick: the beta-adjusted alpha of (`_rk1` top-15 rank book − `_sl200` top-15 rank book) has t ≥ 1 with the same sign in both halves.

**Control rule.** If `_cl1` delivers at least 80% of `_rk1`'s gain in the sized-book paired difference, the clip is adopted instead of the rank model. Two trials, at most one adoptable; adoption goes live only after the user is told and the live freeze has run, and needs its own live wiring (a second daily fit and the mapping in `cycle.convict`).

### 2026-09-16 — reference: pre-backfill baselines from a separate session (earnings-ai backfill pre-work)

A separate agent session prepared for the user's planned backfill of 2024-25 transcripts into earnings-ai (the graph's dated statements start 2025-10: 4,156 statements, none earlier, so the 2024-26 replays run almost entirely on the price stack). It left two baselines in state/ and a handoff; nothing was committed there. Placed against the round 31-35 baselines (469 common days, 5 bps):

| Run | Flags | Return | Sharpe | Max DD | vs `_sl200` bps/day (t) |
|---|---|---|---|---|---|
| `_pre_backfill` | no refresh, signal-close label, 200-day sleeve | +1135% | 2.18 | 31.5% | +0.5 (+0.09) |
| `_pre_backfill_live` | refresh + order-day-open label | +793% | 1.91 | 35.1% | −6.5 (−1.48) |

The second run is the clean-label form (the same setting as `_g1`, +767%), not the live label; the live reference for any post-backfill comparison is `_sl200` (refresh, signal-close label, 200-day sleeve). The handoff also claims a look-ahead in the graph agents' replay path (`supply_chain.run` and `neighbors` reading today's exposure.json counts and `_heat` regardless of the simulated date; `--graph-asof` picking one snapshot for the whole run) that a backfill would inflate and saturate; the review partner is verifying it against `PointInTimeMap`. Order for Trading if the user backfills: verify or fix that path first, then backfill, then replay with `_sl200`'s flags and once more without the graph agents to isolate the effect. `llm_backtest` (a point-in-time test of `llm_guidance`) calls Claude and runs only with the user's go-ahead outside the cycle.

### Round 37 results (2026-09-16 01:25 PT): the rank target orders names worse; live stays

469 common days at 5 bps against the live baseline `_sl200`.

| Run | Return | Sharpe | Max DD | Return at 30 bps | Turnover | Top-15 rank book | vs live, bps/day (t) | OOS (t) | Rank-book alpha vs live, OOS / IS (t) |
|---|---|---|---|---|---|---|---|---|---|
| `_sl200` live | +1129% | 2.24 | 28.3% | +709% | 0.36 | +792% (2.08) | — | — | — |
| `_rk1` rank-ordered convictions | +1001% | 2.17 | 31.5% | +583% | 0.41 | +575% (1.90) | −2.5 (−0.64) | −2.6 (−0.43) | −7.1 (−1.49) / −2.7 (−0.34) |
| `_cl1` ±2.5σ clip control | +1181% | 2.26 | 29.5% | +740% | 0.36 | +772% (2.06) | +1.0 (+1.03) | −0.0 (−0.02) | −0.4 (−0.67) / −0.2 (−0.09) |

The rank model's daily 10-day IC was 0.0234 against the return model's 0.0257 on the same days.

**Gate:** `_rk1` fails conditions 2, 3 and 5 (and 1, see below). Decision, as pre-registered: keep live, no tuning. The clip control is inside noise (+1.0 bps/day, t 1.0, OOS flat) and is not adopted either; by the control rule it would only have replaced a passing rank model.

**Reading.** Fitting on per-date ranks did not order names better; with the sizing held fixed by construction it lowered the top-15 rank book from +792% to +575% and turned the book over faster (0.41 against 0.36). Whatever the learner's edge at the top of the ranking is, the return magnitudes it fits on carry information the ranks discard.

**Two records.** (1) Condition 1's cross-run check (per-date `ic_learned` / `ic_prior` identical to the baseline) did not hold, because `_sl200` ran on the 2026-09-15 price download and both round 37 runs on the 2026-09-16 one; the within-run multiset assertion held on every day, and the price difference cannot account for a gap of this size. A same-day baseline is the right comparator for any future run. (2) The sigma clip is applied after the ±15% winsor, so the control is "tighter than", not "instead of", the winsor.

## 2026-09-16 — round 38, pre-registered before any replay: an explicit intercept for the stacking ridge

**Why.** The graph agents' live rows (and the replay's since mid-2026) are almost always positive, and the learner's negative direction-only weights on them subtract about −0.1 from every conviction. The ridge has no intercept, so an always-positive feature acts as one. The review partner refitted the live dataset in memory (live ledger at 1.0, the `_sz5` warm start at 0.5, decay to 09-15, λ 150, beta target) four ways and applied each to the 09-15 rows:

| Refit | Intercept 10d / 20d | Fit-level 10d / 20d | Graph share of the level | 09-15 mean conviction | Names ≥ 0.10 |
|---|---|---|---|---|---|
| base (live) | — | −0.063 / −0.080 | −0.044 / −0.056 (about 70%) | −0.092 | 0 |
| a1: unpenalised intercept, in convictions | −0.076 / −0.124 | −0.104 / −0.149 | −0.019 / −0.016 | −0.102 | 0 |
| a2: intercept fitted, excluded from convictions | same | — | — | −0.002 | 1 |
| c: intercept, graph direction-only terms dropped | −0.094 / −0.144 | | ≈ 0 | +0.025 (excluded) | 3 |
| b: base demeaned (`DEMEAN_CONVICTION`) | — | — | — | 0 by construction | 18 |

Walk-forward IC (last 10 dates): base −0.078 / −0.054; a1 unchanged (a constant does not move a within-date Spearman); c −0.055 / −0.018.

**Reading, fixed before the replays.** The decay-weighted target mean is −0.104 (10d) and −0.149 (20d) in conviction units: the average universe name has lagged beta × SOXX every month since April 2026 (10-day beta-abnormal: Apr −2.3%, May −3.0%, Jun −2.1%, Jul +0.1%, Aug −1.3%), and the model forecasts that to continue. That is why it holds cash and the sleeve holds SOXX. About a third of the graph agents' negative weights is that level in disguise; the rest survives an intercept. The fragility is the proxy: the level rides on a feature whose scale follows earnings-ai's ingestion profile (the Jul–Aug statement flood doubled it live). An explicit intercept keeps the feature and removes the fragility; it does not open today's book. Demeaning under the base model would buy about 18 graph-contrarian names, an artifact of the inflated direction weights, not "the same ranking with more exposure".

**Diagnostics to run first (cheap, on the existing ledgers).** The intercept's time series by refit date on the warm start (does its sign follow the monthly means above?), and its correlation with the next 20 days' realised mean beta-abnormal return. Near-zero correlation would mean the level is a bias rather than a forecast, and a2 becomes the candidate.

**Runs.** Live flags, one price cache, a same-day baseline.

| Tag | Model | Role | Gate |
|---|---|---|---|
| `_i0` | live | same-day baseline | — |
| `_i1` | a1: unpenalised intercept (constant feature, prior 0), added to convictions | robustness candidate | sized-book paired t ≥ −1 (non-inferiority); rank-book alpha t ≥ −0.5; the graph agents' share of the level near zero across refits |
| `_i2` | a2: intercept fitted, excluded from convictions | exposure-off reference | Sharpe not lower, max DD ≤ baseline + 2 points, OOS paired ≥ 0; report names ≥ 0.10 per day and gross by month |
| `_i3` | c: intercept, graph direction-only terms dropped | ordering candidate | round 32 yardstick (rank-book alpha t ≥ 1, same sign both halves) and sized-book paired ≥ 0 full and OOS |
| `_i4` | b: `DEMEAN_CONVICTION` | exposure-off reference | as `_i2` |

At most one adoptable. `_i1`'s adoption reason is robustness, not P&L; `_i2` or `_i4` would need the drawdown condition, and the expectation is that both fail it by holding stocks through Apr–Jun 2026. Live wiring only after the freeze and with a warm start that has no old-formula rows.

**Implementation notes** (from the review): a per-column λ in `ridge()` with the intercept unpenalised; `NONNEG` leaves it unconstrained; the constant column appended in `dataset()` after loading so the source cache is untouched; `walk_forward_ic` and `agent_ic` handle the extra column; the model JSON gains `"intercept": {h: b}` with a missing key read as 0; `predict()` adds mix_h · b_h and reports it as a separate "level" in the breakdown; `predict(signals, None)` and `--prior-only` stay intercept-free; the dashboard shows intercept × scale as the expected beta-abnormal return of the average name (today about −0.6% per 10 days).

## 2026-09-16 — shadow agents: pre-registered design before any code (infrastructure for rounds 39+)

**Why.** Every remaining candidate that brings new information (insider purchases, analyst revisions, short interest, redesigned macro factors) has data that is either not point-in-time or thin, so it cannot be validated by replay alone. Round 30 also showed why a new agent must not vote on day one: the equal-weight prior gives it a full share and dilutes the book for months. A shadow agent is recorded and scored like the others but has no vote, so it builds a live record at zero cost to the book.

**Design.**
- `config.SHADOW_AGENTS = ()`: agent modules run and recorded by the cycle (and replayed by the backtest with `--shadow a,b`) but excluded from `learner.agents()`, so they enter neither the features, the prior, `predict`, the effective weights nor the dashboard's weight tiles. Inert when empty.
- `cycle.run_agents` runs `config.AGENTS + config.SHADOW_AGENTS` through the same per-agent error handling and records every row; `open_refresh` refreshes a shadow price agent only if it is listed in `OPEN_REFRESH_AGENTS`.
- `learner._rows` filters `p.agent IN (config.AGENTS)` so a (date, ticker) pair covered only by a shadow agent never becomes an all-zero feature row (it would otherwise count in `n_obs`, `scale` and the walk-forward folds).
- `learner.predict` keeps shadow signals out of the per-name breakdown (they would otherwise appear in decisions, `reason_line` and the moderator's minutes with contribution 0); the dashboard gets a separate `shadow` section per name.
- Scoring is unchanged (`score.run` scores every recorded row); the scoreboard shows shadow agents labelled, with their own per-date rank IC on the beta-abnormal label and their incremental IC over the ensemble conviction.
- Backtest: `--shadow a,b` runs the modules in the day loop and records their rows without adding them to `PIT_AGENTS`; a per-agent daily IC report covers them.
- Promotion: a pre-registered test per agent — a point-in-time replay where one exists, plus at least 60 live sessions confirming the sign (per-date IC has an sd of about 0.15, so 60 sessions detect only IC ≈ 0.04 at t ≈ 2; the replay carries the evidence, the live record confirms it). A promoted agent enters with `AGENT_PRIOR[name] = 0` (not the equal share) and with its rows in the warm-start ledger from its replay.

**Equivalence test before merging.** With `SHADOW_AGENTS = ()`, convictions, orders, the model file and the dashboard must be identical to the current code on a state-copy rehearsal, and a 60-day replay must be byte-identical on the pinned graph snapshot.

**First shadow agent.** Insider open-market purchases (Finnhub, Form 4 code P, point-in-time by filing date, known from the next session; purchases only, ≥ 2 distinct officer or director buyers within 30 days as the strong form, decayed with age, bucketed by size relative to the buyer's holdings). Coverage measured on 2026-09-16: 472 purchases across 71 names since 2024-01, 14.8 a month but lumpy and TSM-heavy, so its case rests on the replay; horizon 20 days; incremental IC over `mean_reversion` reported, because purchases cluster after drawdowns.

### Round 38 results (2026-09-16 08:50 PT): the level is a bias, not a forecast; demeaning passes its gate

Five 500-day replays on one price cache and one graph snapshot (dir `2026-09-16`, hash `e5a7f9ef606e`, unchanged through the batch), same-day baseline. Every run exited cleanly.

**Diagnostic: does the fitted level forecast the average name's beta-abnormal return?** From `_i1`, the level per day (intercept × the model's stored scale) against the realised per-name-winsorised cross-sectional mean at the same horizon:

| Horizon | Level mean (sd) | Realised mean (sd) | Correlation (20-day block bootstrap 95%) | Same sign | Level > 0 | MSE level vs zero forecast (×1e-4) | Monthly sign agreement |
|---|---|---|---|---|---|---|---|
| 10d | +0.48% (0.48) | +0.13% (2.11) | +0.13 (−0.24 .. +0.47) | 62% | 87% of days | 4.55 vs 4.48 → zero better | 16/24 |
| 20d | +0.90% (0.87) | +0.11% (2.83) | +0.09 (−0.31 .. +0.43) | 61% | 89% of days | 8.96 vs 8.02 → zero better | 13/24 |

By the pre-registered reading the level is a bias — an exponentially weighted trailing mean that lags the monthly turns (positive through the 2024–25 rally, negative only from June 2026) — not a forecast. Note that in the replay the level was positive on nine days in ten, so its live effect since April 2026 (a negative level holding the book in cash) is the exception, not the rule.

**Replays** (470 common days, 5 bps):

| Run | Model | Return | Sharpe | Max DD | Return at 30 bps | Names | Gross | Turnover | vs `_i0`, bps/day (t) | OOS (t) | Gate |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `_i0` | live (same-day baseline) | +1157% | 2.23 | 29.5% | +721% | 11.7 | 1.05 | 0.36 | — | — | — |
| `_i1` | a1: intercept in convictions | +887% | 2.11 | 38.2% | +483% | 12.4 | 1.12 | 0.45 | −5.8 (−1.29) | −6.4 (−0.96) | FAIL (t < −1; rank-book alpha t −1.34 IS) |
| `_i2` | a2: intercept fitted, excluded | +941% | 2.27 | 23.5% | +570% | 10.5 | 1.00 | 0.38 | −5.3 (−1.04) | −1.1 (−0.14) | FAIL (OOS paired < 0, by a hair) |
| `_i3` | c: intercept + graph direction terms dropped | +882% | 2.09 | 38.2% | +481% | 12.4 | 1.12 | 0.45 | −5.8 (−1.29) | −6.4 (−0.96) | FAIL (full-window rank-book alpha t −0.79) |
| `_i4` | b: `DEMEAN_CONVICTION` | +1110% | 2.25 | 24.7% | +640% | 13.8 | 1.10 | 0.42 | −1.1 (−0.26) | +0.7 (+0.23) | **PASS** (Sharpe ≥, max DD ≤ +2, OOS ≥ 0) |

Final graph-agent direction weights (10d / 20d): `_i0` supply_chain −0.171 / −0.298, neighbors −0.294 / −0.324; `_i1` −0.108 / −0.214, −0.260 / −0.282 with intercept −0.059 / −0.079 (scaled units). About a third of the graph agents' negative direction weights is the level in disguise, as the in-memory diagnostic predicted.

**Reading.**
- An explicit intercept in the convictions (`_i1`) makes the book worse: the fitted level is applied every day, and since it lags the turns it adds exposure late in rallies and cuts it late in recoveries (max drawdown 38%).
- Removing the level — by the ridge's own estimate (`_i2`) or cross-sectionally (`_i4`) — lowers the maximum drawdown by 5–6 points at a return difference inside noise. The expectation that the exposure-off references would fail on drawdown by holding stocks through April–June 2026 did not hold: in those months the relative winners still did better than the level implied, and the vol target caps the rest.
- `_i4` keeps the baseline's ordering by construction (its rank line equals `_i0`'s); what changes is how many names clear the 0.10 bar on a given day: fewer when the level was pushing convictions up (2024–25), more when it was pushing them down (2026). Mean gross April–August 2026: 0.69 / 1.24 / 1.37 / 1.43 / 1.41 against a cash-heavy baseline.
- Costs: the demeaned book turns over faster (0.42 against 0.36 a day), so at 30 bps its return is +640% against +721%.

**Pre-registered verdict.** `_i4` (`DEMEAN_CONVICTION = True`) is the one adoptable variant; `_i1`, `_i2`, `_i3` are rejected. The adoption itself is decided after the review partner's critique and a state-copy rehearsal on today's signals (below). Five trials are added to the count.

### Round 38 adoption (2026-09-16 11:56 PT): `DEMEAN_CONVICTION = True`, applied the same afternoon at the user's request

- Rehearsal (08:48 PT, state copy, dry run, the day's 1,367 recorded signals reused, no Claude calls): convictions demeaned by −0.106; 16 orders — SELL SOXX $1,025,838; BUY D $114,671, ES $114,484, SHEL $113,809, UBER $95,479, EXC $90,432, NRG $89,346, APD $86,821, NEE $77,186, TT $77,120, MMM $76,370, HUBB $74,100, SPXC $73,855, CARR $68,918, SOLS $63,523, APH $62,855 (buys $1,278,969; estimated cost $1,152). The same signals gave 0 orders un-demeaned at the 06:30 open. The relative winners are the universe's non-chain defensives (utilities, industrials, SHEL, UBER); the chain names all sit below the mean.
- Decision: adopted (config b44aa74, comment cites the replay; 69 tests). Deviation from the pre-registration, recorded here: the review partner's critique was lost with a session restart, and the user asked for orders today ("오늘도 주문안넣었네 … 진짜 주문넣게", then "지금실행하자" at 11:50 PT), so the flag went live at 11:56 PT through an on-request extra run (`cycle.py --reuse-signals --no-llm`: the recorded signals, the six price agents refreshed on live prices, the moderator skipped, two slices 10 min apart) instead of waiting for the 09-17 cycle. A fresh read-only review of the three unreviewed commits (stage deadline, timeout/snapshot, demean) ran after the fact: no blockers for the 09-17 cycle; ten nits, two fixed on the branch (c3a698f: the dashboard's top list was ranked by |conviction|, which with demeaned values put the most-avoided names among the best longs; `backtest.py --demean` now defaults to `config.DEMEAN_CONVICTION`, `--no-demean` is the raw control), the rest are HANDOFF follow-ups.
- Afternoon run: equity $1,009,597 (SOXX had given back most of its +1.6% open gain); targets 14 — SOLS fell below the 0.10 line at the 11:56 prices; orders 15: SOXX closed in full, 14 buys in two slices (D, ES, SHEL, EXC, UBER, NRG, TT, APD, NEE, HUBB, CARR, SPXC, MMM, APH; slice-1 notionals $30.7k–$55.6k, half of each target). Four buys (NRG, TT, HUBB, CARR) went as market orders because the free IEX quote showed 500–1,000 bps spreads (the broker's fallback rule). All 29 orders filled within 1–4 s of submission and none needed the cleanup: SOXX 2,012.533 sh @ $500.52 ($1,007,514); slice 2 at 12:06:47–50 PT (limit fills in 1–3 s). Book at 12:15 PT: 14 names, long market value $1,179,982 = 117% of equity $1,005,891 (cash −$174,090 on margin), the gross the replay averaged in 2026 (1.2–1.4).
- Going forward the demeaned book is judged on live sessions like every other change; the ledger keeps the raw signals, so a raw-versus-demeaned replay of any period stays possible. Trials this round: five replays plus the rehearsal; no further variants planned.
- Replay command (tmp/run_round38.py, for the record): `backtest.py --days 500 --exec open --idle-sleeve SOXX --sleeve-fraction 1.0 --sleeve-trend 200 --no-publish --open-refresh --graph-asof 2026-09-16` plus `--demean` for `_i4` (`--intercept in` / `--intercept fit_only` / `--intercept in --drop-dir supply_chain,neighbors` for `_i1`..`_i3`), so the replay's sleeve rule was the live 200-day one.

## 2026-09-16 — round 39, pre-registered before any result: the enriched graph (2026 US earnings calls), filings out of the graph agents, chain-neutral demeaning

**Data event.** earnings-ai enriched its 2026 US earnings-call backlog today (16:54–16:57 PT; its HANDOFF runs 3–5): the graph's dated statement rows went from 4,217 to 6,000 (earnings calls 2,731 → 4,514; filings 1,059 and conferences 427 unchanged), 352 nodes / 1,400 edges (+23), one new public US name (CBRS). The new rows are dated 2026-01..05 (Jan +287, Feb +884, Mar +116, Apr +226, May +233). Snapshot `2026-09-16_1917` (19:17 PT) pins it; the morning snapshot `2026-09-16` (pre-enrichment) is what rounds 36–38 used. Conferences already feed both the graph agents (dated rows) and the Claude agents (the transcript-only filter keeps them); SEC-filing rows feed only the graph agents (the Claude agents drop them since 09-13).

**Consequences before any run.** (1) The 09-17 cycle reads the enriched graph automatically: the graph agents' recency and tightness inputs change for many names, the Claude prompts stay capped (12 rows per company), the universe grows by CBRS. (2) Every replay comparison from now on is pinned to `2026-09-16_1917` or later (`--graph-asof 2026-09-17`); the round 36–38 numbers stand on the old snapshot and are not comparable with new-snapshot runs. (3) The warm start `state/backtest.sqlite` (`_sz5`) was generated on the old graph; the new-graph baseline's ledger is the consistent warm start for the live learner (decided after the runs, with a rehearsal).

**Evaluation protocol change (from AQuA, arXiv 2608.12841, adopted 2026-09-16).** From this round the gate consults only the *validation window* = the first 70% of the common days; a 20-trading-day embargo follows (labels are 10/20-day returns); the *test window* = the remaining days is scored once per adopted candidate and reported, never used to choose among candidates. Same-day baseline, graph pin and trial counting stay. (Rounds ≤ 38 looked at both halves before deciding; that is the selection leakage the paper closes.)

**Runs** (500 days, `--exec open --open-refresh --idle-sleeve SOXX --sleeve-fraction 1.0 --sleeve-trend 200 --graph-asof 2026-09-17`, live flags including demean):
- `_n0`: new-graph baseline (live config). Compared with `_i4` (old graph, same flags, same price-cache day) for information only: the data effect.
- `_n1`: `--graph-transcripts-only` (`GRAPH_TRANSCRIPTS_ONLY`): the graph agents skip SEC-filing rows (10-K/10-Q/8-K/20-F/6-K/40-F and third-party notes). Hypothesis: filing "tight" markers are boilerplate risk-factor language, so dropping them raises the graph agents' signal quality. Gate vs `_n0` on the validation window: Sharpe not lower, max DD ≤ +2 pts, paired daily difference ≥ 0; the test window's paired sign is reported once.
- `_n2`: `--demean-group chain` (`DEMEAN_GROUP`): demean within two groups, power = names whose only chain tag is power_cooling, chip = everything else (a group under 5 names uses the whole mean). Hypothesis: the 11-of-14 power/cooling book of 09-16 is a theme bet the plain demean created; neutralising the theme keeps the relative winners of both groups. Gate as `_n1`.
- `_n3`: both switches, run only if both pass; gate vs the better single.
Stop rule: at most four replays; a variant that fails stays off. Adoption for 09-17 needs a state-copy rehearsal and the review partner. Trials this round: up to 4.

### Round 39 results (2026-09-16 19:50 PT): the enriched graph is inside noise; filings-out has no validation power; chain-neutral fails its one-shot test; the warm start moves to the new-graph ledger

Three 500-day replays on snapshot `2026-09-16_1917` (hash 85395ac5981a, unchanged through the batch), same-day price cache, 470 common days 2024-09-30..2026-08-14. Gate under the new protocol: validation 2024-09-30..2026-01-22 (329 d), embargo 20 d, test 2026-02-23..2026-08-14 (121 d, scored once).

| Run | Validation return / Sharpe / max DD | Test (one shot) return / Sharpe / max DD | Full (informational) | vs `_n0` validation paired (t) | vs `_n0` test paired (t) | Gate |
|---|---|---|---|---|---|---|
| `_n0` new-graph baseline | +523% / 2.30 / 24.7% | +65% / 1.68 / 26.6% | +1030% / 2.14 / 26.6% | — | — | base |
| `_n1` filings out of the graph agents | +517% / 2.29 / 24.7% | +77% / 1.88 / 28.7% | +1152% / 2.24 / 28.7% | −0.32 bp/d (−0.64) | +6.0 bp/d (+1.32) | FAIL (Sharpe 2.29 < 2.30, paired < 0) |
| `_n2` chain-neutral demean | +568% / 2.41 / 23.3% | +45% / 1.25 / 33.3% | +1006% / 2.13 / 33.3% | +1.98 bp/d (+0.54) | −11.1 bp/d (−1.49) | validation PASS, test window clearly worse |

Data effect (informational, same flags, same price day): old graph `_i4` +1110% / 2.25 / 24.7% against new graph `_n0` +1030% / 2.14 / 26.6%, paired −1.2 bp/d (t −0.26); before 2025-10 the two are identical (no graph rows), so all of the difference sits in 2025-10..2026-08 (−2.6 bp/d, t −0.26): the enriched 2026 calls neither help nor hurt the replay. Learned 10-day IC 0.031 (`_n0`) vs 0.027 (`_i4`).

**Reading.**
- `_n1`: the graph agents are nearly silent before 2025-10, so the validation window cannot see a graph-agent change; the variant differs from the baseline only in the graph-covered months, which are the test window (where it is +6 bp/d, t +1.3, with a higher drawdown). By the pre-registered rule the test cannot pick it. Not adopted; re-test in a round whose validation window contains graph-covered months (from 2026-01 the graph has 12 months of rows), or on live sessions.
- `_n2`: it helps in the 2024–25 rally (validation +2 bp/d) and hurts in the 2026 semis sell-off (test −11 bp/d, max DD 33% against 27%): demeaning within the chip group keeps buying the least-bad chips while the group falls, the trade-off named in the hypothesis. The one-shot test is the honest out-of-sample report and it says no. Not adopted. Protocol addendum from round 40: a candidate whose one-shot test is significantly worse (paired t < −1 or max DD > base + 2 pts) is not adopted; the test stays one-shot and is never used to rank.
- The switches `GRAPH_TRANSCRIPTS_ONLY` and `DEMEAN_GROUP` stay off; both remain available as replay flags.
- Warm start: the live learner's history (`state/backtest.sqlite` = `_sz5`, generated on the pre-enrichment graph) is replaced by `_n0`'s ledger, generated on the enriched graph the live agents now read (train = serve; the rehearsal on a state copy showed the same live graph-agent rows either way: supply_chain +0.529, neighbors +0.557). Rehearsal of tomorrow's fit on the new warm start with today's reused signals (evening prices): effective weights supply_chain −0.234, neighbors +0.184, risk 0.083, fundamentals and the three Claude agents 0.079, macro −0.067, technical 0.046, mean_reversion 0.045 (control on the old warm start: risk 0.181, fundamentals/Claude 0.116, technical 0.077, neighbors 0.068, supply_chain −0.058, macro −0.083); demean −0.159 (control −0.105); a 19-order rebalance into a mixed book (top: SHEL, STM, D, ETR, XEL, TXN, ENTG, ES; also MSFT, AMZN) with the sleeve off, against the control's trim to 10 names with the sleeve back on. The old file is kept as `state/backtest_sz5_before_n0_20260916.sqlite`.
- Trials this round: 3 replays (`_n3` not run: `_n2` failed).

## 2026-09-17 00:30 PT — literature review absorbed (user-commissioned, another session; citations verified there by DOI/arXiv): what is taken, what is pre-registered, what is dropped

**Caveat on round 15 (llm_guidance's point-in-time validation, Sonnet proxy).** The model's training data covers 2024–26, so feeding it only past statements does not make the replay point-in-time: memorised outcomes can leak (Lopez-Lira, Tang & Zhu 2025, arXiv 2504.14765; Glasserman & Lin 2023, arXiv 2309.17322: masked company names beat originals for large caps; Gao, Jiang & Yan 2025, arXiv 2512.23847, a look-ahead test; He et al. 2025, arXiv 2502.21206, chronologically trained models). Round 15's IC 0.043 and OOS contribution are therefore upper bounds, not evidence. Live trading is unaffected (the future is not in any training set); the live paper track remains the only test of the three Claude agents. Cheap forward check: an anonymised twin (`llm_guidance_anon`, company names and tickers masked) as a shadow agent, compared on live sessions only. Re-validating history with a chronologically trained model would need LLM calls outside the cycle → needs the user's approval first; not planned.

**Protocol addenda.** (a) Shadow-agent promotion expects about half of a published effect (McLean & Pontiff 2016: post-publication decay ≈ 58%). (b) Any LLM-based backtest claim carries the memorisation caveat above.

**Pre-registered queue (in this order; each a replay round with the validation/embargo/test gate; runs after the 09-17 Claude stage and only on AC power):**
- **Round 40 — residual momentum in `technical`** (Blitz, Huij & Martens 2011, doi 10.1016/j.jempfin.2011.01.003). `agents/technical.py` `rel20` = stock return − SOXX return, no beta adjustment, so after a crash the low-beta names rank as winners while the learning target is beta-adjusted. Candidate: `TECHNICAL_RESIDUAL = True` → rel20 = stock return − β × SOXX return with the trailing 60-day pair beta (as macro / the target use). Runs: `_r0` same-day baseline, `_r1` residual; also both on the 2019–23 window (`_pre2024` setup) as a robustness check, not a gate. Hypothesis: higher technical IC and a smaller momentum-crash loss in 2025Q2. Gate: the standard one on validation, test scored once. 2 replays (+2 on 2019–23).
- **Round 41 — adaptive vol target + trend-bet ablation** (Bongaerts, Kang & van Dijk 2020; Cederburg et al. 2020 as the real-time guardrail; Hood & Raughtigan 2025: vol-target alpha is mostly trend exposure, so the vol brake, the 200-day sleeve and macro may be the same bet three times). Candidate: `VOL_TARGET` = expanding median of the book's own trailing vol (causal), replacing the fixed 0.50; control: the vol brake removed. Hypothesis: lower drawdown at equal return; the ablation shows how much of the brake's value the sleeve rule already delivers. 2–3 replays.
- **Round 42 — partial SOXX beta hedge (index short, not stock shorts)** for the user's bear-market question: keep the top-quintile alpha (+1.64% per 10 days) and remove part of the market. Candidate: hedge ratio 0.5 of the book's realised beta. Judged on both windows; the 2019–23 window (2022 bear) decides its value, the 2024–26 window its cost. 2 replays.
- **Round 43 — fear-state interaction** (Daniel & Moskowitz 2016, momentum crashes): a feature `technical × fear` (fear = SOXX drawdown > 20% or VIX > 30, causal) added to the learner's columns, not a gate (round 36 closed gates). Explains the 2025Q2 V-shaped loss (−36% vs SOXX). 1–2 replays.
- **Round 44 — turnover** (Jensen, Kelly, Malamud & Pedersen 2026; Gârleanu & Pedersen 2013): a penalty on day-to-day conviction change inside the ridge (κ), evaluated at 5 and 30 bps. Rounds 12–15 already rejected sizing-side hysteresis; this is model-side. 2 replays.
- **Diagnostic (offline, no replay) — neighbors**: split the neighbours' contribution into their own momentum (already in technical; Burt & Hrdlicka 2021, doi 10.1017/S0022109020000885; Ali & Hirshleifer 2020, doi 10.1016/j.jfineco.2019.10.007) and a statement residual; only if the residual carries IC does a co-mention neighbour (Scherbina & Schlusche, ssrn 2363436) become a shadow-agent candidate. The graph-covered window is ~140 days: low power, so this is a diagnostic, not a gate.

**Shadow agents (need the shadow plumbing, `tmp/patch_shadow.py`, applied after the 09-17 cycle):** (1) insider purchases with the Cohen, Malloy & Pomorski (2012) routine/opportunistic split applied to the 472 purchases already collected (only opportunistic buys count); (2) `llm_guidance_anon` (names masked) on a subset of names per day so the Claude stage stays inside the 09:05 ET deadline; (3) later, a co-mention neighbour if the diagnostic supports it.

**Recorded, not planned.** `llm_news` horizon mismatch (headline signals fade in 1–2 days, Lopez-Lira & Tang 2023, arXiv 2304.07619; Heston & Sinha 2017): rule for live evidence only — if after 60 live sessions llm_news's 10/20-day IC is near zero outside insider-trade and conference news, narrow it to those topics. Posterior-variance sizing (Kan & Zhou 2007) is moot: sizing is conviction × 0.60, not posterior variance. Analyst-revision features (Jegadeesh et al. 2004): no revision history in the data.

**Dropped.** The Kim, Muhn & Nikolaev LLM financial-statement paper (reported as inapplicable by the reviewing session). Anything that requires LLM calls outside the scheduled cycle.

## 2026-09-17 01:45 PT — protocol v3, pre-registered before any further result: purged alternating blocks replace the contiguous 70/30 split from round 41 on

**Why.** Under the contiguous split (validation = 2024-10..2026-01, test = 2026-02..08) the validation window is the 2024–25 semis rally and the test window holds the 2026 crash and recovery. Two candidates that trim beta exposure, filings-out (round 39 `_n1`) and residual momentum (round 40 `_r1`), each lost by a hair in validation (t −0.64 both) and won the one-shot test (+6 and +10 bp/d, t +1.3 and +1.0) with lower drawdowns. A selection window that contains one regime cannot judge regime-dependent changes; changing the rule for those two rounds after seeing their results would be selection leakage, so their verdicts stand (not adopted) and the rule changes only for what comes next.

**Rule from round 41.** The common days are cut into six equal contiguous blocks; blocks 1, 3, 5 are the validation set and blocks 2, 4, 6 the test set; 20 trading days are purged from the start of every block (the 10/20-day labels overlap the previous block). The gate reads the union of the validation blocks (Sharpe not lower, max DD ≤ base + 2 pts, paired ≥ 0); the union of the test blocks is scored once per adopted candidate and vetoes adoption when its paired t < −1 or its max DD > base + 2 pts. Both unions contain rally and sell-off days. Trial counting, same-day baseline and the graph pin stay.

**Re-test, pre-registered.** `_n1` (GRAPH_TRANSCRIPTS_ONLY) and `_r1` (TECHNICAL_RESIDUAL) are re-run in the round 41 batch on that day's price cache and judged under v3 (2 trials added). Their current verdicts are not changed by anything computed on today's curves under v3; that computation is reported below for information only, never as a decision.

### Round 40 results (2026-09-17 01:50 PT): residual momentum fails the pre-registered gate; lower drawdown out of sample; 2019–23 residual run pending

Runs on snapshot `2026-09-16_1917` (hash 85395ac5981a, unchanged), price cache of 09-17, 470 common days 2024-10-01..2026-08-17. `_p0` (2019–23 baseline, live rules with demean, five price agents, 1,170 days) finished: +65% / Sharpe 0.35 / max DD 41.6% (SOXX +170%). `_p1` (2019–23 residual) was killed twice by the memory guard (a 1,200-day replay does not fit beside the user's open applications tonight; 2.4 GB free) and is queued for the daytime, after the 09-17 Claude stage.

| Run | Validation (329 d) | Test (121 d, once) | Full (informational) | vs base validation (t) | vs base test (t) | Gate |
|---|---|---|---|---|---|---|
| `_r0` baseline | +559% / 2.38 / 24.0% | +41% / 1.16 / 27.3% | +947% / 2.08 / 27.3% | — | — | base |
| `_r1` residual momentum | +513% / 2.31 / 25.6% | +60% / 1.64 / 22.6% | +1019% / 2.18 / 25.6% | −2.4 bp/d (−0.64) | +10.1 bp/d (+0.99) | FAIL (Sharpe 2.31 < 2.38, paired < 0) |

Learned 10-day IC 0.029 (`_r1`) vs 0.031 (`_r0`); turnover 0.39 vs 0.40; names and gross unchanged. Under the v3 split computed for information only (never a decision): `_r1` validation −2.0 bp/d (t −0.60), Sharpe 1.72 vs 1.79 → FAIL as well; test +3.3 bp/d (t +0.38), max DD 22.6% vs 27.3%. The same computation on round 39: `_n1` passes v3 validation (+3.1 bp/d, t +1.06) but its test max DD 28.7% vs 26.6% trips the veto by 0.1 pt; `_n2` passes validation and is vetoed by its 33.3% drawdown.

**Reading.** Residual momentum's only consistent effect is a smaller drawdown (full 25.6% vs 27.3%, test 22.6% vs 27.3%); its return effect is inside noise in both splits. Not adopted. It stays a re-test candidate in the round 41 batch under protocol v3 (fresh price day), together with `_n1`; the 2019–23 pair (`_p1` vs `_p0`) is the robustness read for that batch. Trials this round: 3 finished (+1 pending).

### 2026-09-17 04:50 PT — research VM (GCP `semiband-research`, e2-highmem-4, 32 GB) and what "the same result" means across machines

The laptop's round 40 baseline `_r0` was re-run on the VM with the same code (d02e2aa), the same price cache files (SOXX/SPY curves identical on all 470 days), the same day caches and universe, Python 3.14.7/numpy 2.4.6/pandas 3.0.3 (laptop 3.14.3, same numpy/pandas). Result `_vmr0`: +993% / Sharpe 2.11 / max DD 29.3% against the laptop's +947% / 2.08 / 27.3%. The agents' rows differ at the last floating-point digit (e.g. technical ACLS 2024-08-19: −0.6971342963925096 laptop vs …097 VM), the ridge and the 0.10 entry line turn that into a different marginal name on day 4, and the rebalance band carries the difference forward: returns identical on 19 of 470 days, books identical on 284. This is numerical path dependence, not a data or code difference.

**Rules.** (1) A comparison is valid only between runs on the same machine on the same day (the batch runners already include their own baseline); laptop numbers and VM numbers are never compared with each other. (2) The ±5% return / ±0.03 Sharpe / ±2 pts drawdown that ulp-level perturbation produced here is a floor for the noise band: no verdict rests on differences that small. (3) From this point all replay rounds run on the VM (three to four in parallel); the laptop keeps the live cycle only. Round 40's 2019–23 window is re-run as a same-machine pair on the VM (`_vp0`, `_vp1`).

### Round 40 addendum (2026-09-17 05:40 PT): the 2019–23 pair on the VM, and why the purged-block split cannot judge beta-trimming changes

Same-machine pair on the VM (`_vp0` baseline, `_vp1` residual momentum; five price agents, live rules with demean, 1,170 days 2019-04-09..2023-11-29, snapshot 2026-09-17 for the map, which has no rows in that window): `_vp0` +65% / Sharpe 0.35 / max DD 40.6%; `_vp1` +115% / 0.53 / 42.7%; learned IC 0.0084 vs 0.0076. Six-block split: odd blocks −1.05 bp/d (t −0.53), even blocks +5.58 bp/d (t +2.20).

**The flaw.** In both windows the even blocks contain every crash (2020-01..10 COVID, 2021-08..2022-05 bear, 2023; 2025-01..05 tariff crash, 2026-04..08 semis sell-off) and the odd blocks the rallies, by the accident of the block boundaries. A change that trims beta must lose a little in rallies and win in crashes, so the v3 gate (odd blocks decide) rejects it by construction and the v2 gate (first 70%, the 2024–25 rally) did the same. Residual momentum has now shown the same signature three times (2024–26 contiguous, 2024–26 blocks, 2019–23 blocks) and a full-window improvement in both windows (+1019% vs +947%, Sharpe 2.18 vs 2.08, DD 25.6% vs 27.3%; +115% vs +65%, 0.53 vs 0.35, DD +2.1 pts). Its round 40 verdict stands as FAIL under the rule that was registered for it; nothing is adopted from this addendum.

## 2026-09-17 05:45 PT — protocol v4, pre-registered before any decision run: full-window gate with block consistency and an independent window

Rule from round 41 (replaces v3's odd/even blocks; v3 was never used for a decision): (1) gate on the full common window against the same-day, same-machine baseline: paired daily difference ≥ 0, Sharpe not lower, max DD ≤ base + 2 pts; (2) consistency: with the six purged blocks, the paired difference is ≥ 0 in at least 4 of 6 blocks, so a win concentrated in one block fails; (3) independent confirmation for changes the 2019–23 window can express (price-agent and sizing changes): paired ≥ 0 there and max DD ≤ base + 3 pts; (4) trial counting and pre-registration as before; (5) live sessions remain the final test (60 sessions). No held-out slice is reserved: the independent window and the block consistency take its place, and the reasoning is that a fixed slice of two years cannot avoid being one regime.

**Round 41 (VM, all runs same machine, today's price cache, snapshot 2026-09-17):** `_w0` baseline, `_w1` `--technical-residual`, `_w2` `--graph-transcripts-only`, `_w3` both. Gate v4 for each against `_w0`; `_w3` against the better single if both pass. The 2019–23 confirmation for `_w1` is `_vp1` vs `_vp0` above (already run, same machine): paired positive, DD +2.1 pts (≤ 3). Trials: 4 (+ the 2 already run).

### Round 41 results (2026-09-17 06:30 PT, protocol v4, all runs on the VM, price cache of 09-17, snapshot 2026-09-17): filings-out adopted; residual momentum fails block consistency

| Run | Return / Sharpe / max DD | vs `_w0` paired (t) | Blocks ≥ 0 (of 6) | Gate v4 |
|---|---|---|---|---|
| `_w0` baseline (live config) | +993% / 2.11 / 29.3% | — | — | base |
| `_w1` residual momentum | +1109% / 2.23 / 24.7% | +1.9 bp/d (+0.37) | 3 [−1.4, −21.6, −5.1, +7.3, +8.9, +13.1] | FAIL (consistency) |
| `_w2` filings out of the graph agents | +1117% / 2.20 / 30.1% | +2.3 bp/d (+1.48) | 5 [0, 0, 0, +0.3, +12.8, −2.7] | **PASS** |
| `_w3` both | +937% / 2.09 / 25.1% | −1.4 bp/d (−0.26) | 2 | FAIL |

Learned 10-day IC: 0.0313 / 0.0287 / 0.0293 / 0.0267. The first three blocks are identical for `_w2` (no graph rows before 2025-10), so its evidence is the three graph-covered blocks (two positive, one negative) and the full-window t of +1.5, the strongest of any graph-agent change so far; the independent 2019–23 window cannot test it (no graph rows). Residual momentum's signature is now precise: it loses in V-shaped crash-and-rebound blocks (2025-01..05: −21.6 bp/d) and wins in prolonged drawdowns (every 2026 block, and the 2019–23 window +2.3 bp/d, t +1.5). Not adopted; a regime-conditioned version (residual only when a drawdown persists) is a candidate for round 43 with the fear feature, pre-registered there, not here.

**Adopted:** `GRAPH_TRANSCRIPTS_ONLY = True` (bbf4ed5) from the 09-18 cycle. Rehearsal on a state copy: today's graph-agent rows nearly unchanged (supply_chain 150 rows +0.522, neighbors 118 rows +0.562 against +0.529 / +0.557 with filings). Warm start: `_w2`'s ledger (filings-out, same code, today's cache) replaces `_n0`'s after today's cycle exits; the rehearsal on it gives effective weights supply_chain −0.230, neighbors +0.175, risk 0.100, fundamentals and the Claude agents 0.080, macro −0.057 (against −0.234 / +0.184 / 0.083 / 0.079 / −0.067 on `_n0`), so the swap moves the learner little. Trials this round: 4 (+2 on 2019–23 for `_w1`).

## 2026-09-17 15:30 PT — round 42, pre-registered before any result: gross ceiling 2.0, a trend-gated beta floor, both; margin interest charged in every run

**Why (user, 2026-09-17).** The closing book of 09-17 had beta 0.12 to SOXX and 15% volatility (SOXX 53%) at 142% gross: the dollar ceiling binds long before the 50% vol target, so a defensive book wastes risk budget and lags a semis rally (+1.24% against SOXX +3.39%). The user wants less risk and more upside; leverage and beta are the two levers.

**Realism fix first.** The replay never charged margin interest. From this round every run (the baseline too) pays 7% a year on long gross above 1.0 (`--margin-rate 0.07`), so leverage is not free. Earlier rounds' numbers are not comparable with these.

**Runs** (VM, same machine, same day, snapshot 2026-09-17, live config incl. filings-out; v4 gate on each window):
- 2024–26 (500 days): `_x0` baseline, `_x1` `--gross-target 2.0` (the Reg T overnight limit), `_x2` `--beta-floor 0.5` (while SOXX is above its 200-day average the book's beta is raised to 0.5 with SOXX through `portfolio.beta_floor`: the sleeve grows while gross ≤ ceiling, past it the stocks shrink together so gross = ceiling and beta = floor), `_x3` both.
- 2019–23 (1,200 days ending 2023-12-29, five price agents): `_y0`..`_y3`, the same four. This window holds the 2022 bear, where a beta floor must switch off with the trend rule.
- One value per knob (2.0, 0.5): no tuning. Hypotheses: `_x1` gains little after interest and raises drawdown; `_x2` raises return in rallies with a drawdown no worse than +2 pts because the floor is off below the 200-day average; `_x3` is the most aggressive and the most likely to fail the drawdown limit.
- Gate v4 per variant: 2024–26 full-window paired ≥ 0, Sharpe not lower, max DD ≤ base + 2 pts, ≥ 4 of 6 blocks not worse; 2019–23 confirmation paired ≥ 0 and max DD ≤ base + 3 pts. Adoption needs live wiring of the floor (cycle sleeve logic), its tests, a state-copy rehearsal and the review partner. Trials: 8.

## 2026-09-17 15:20 PT — round 43, pre-registered before any result: the vol brake — off, expanding median, stricter

**Why.** The 50% vol target is one of three trend-like brakes (with the sleeve's 200-day rule and the macro agent; Hood & Raughtigan 2025: vol-target alpha is mostly trend exposure). The replay's book averaged 61% vol, so a fixed 0.50 brakes more than half the time; AQuA's expanding-median target brakes half the time by construction. The ablation says how much the brake is worth next to the other two.

**Runs** (VM, same machine and day as their own baseline, margin interest 7%, snapshot 2026-09-17; both windows): baseline (0.50 fixed) = round 42's `_x0` / `_y0` if run the same day, else re-run; `_v1`/`_u1` `--vol-target 0` (brake off); `_v2`/`_u2` `--vol-target-mode median` (expanding median of the book's own 20-day realised vol, after 60 observations, 0.50 until then); `_v3`/`_u3` `--vol-target 0.40` (the risk-first alternative documented in rounds 12–15). Hypotheses: brake off raises return and drawdown (fails the DD limit); median ≈ baseline (inside noise); 0.40 lowers drawdown at a return cost (fails paired ≥ 0). Gate v4 per variant on 2024–26 with the 2019–23 confirmation. One value per knob, no tuning. Trials: 6 (+2 baselines if re-run).

### Round 42 results (2026-09-17 16:00 PT, protocol v4, VM, 7% margin interest in every run): leverage and beta are risk dials, none passes

| Run | 2024–26: return / Sharpe / max DD | vs `_x0` paired (t) | Blocks ≥ 0 | 2019–23: return / Sharpe / max DD | vs `_y0` paired (t) | Gate |
|---|---|---|---|---|---|---|
| baseline (`_x0` / `_y0`) | +1090% / 2.18 / 30.2% | — | — | +61% / 0.33 / 40.7% | — | base |
| gross ceiling 2.0 (`_x1` / `_y1`) | +1343% / 2.11 / 32.0% | +5.9 bp/d (+2.10) | 4/6 | +70% / 0.36 / 40.7% | +0.5 (+1.22) | FAIL (Sharpe lower) |
| beta floor 0.5, trend-gated (`_x2` / `_y2`) | +1112% / 2.19 / 31.6% | +0.4 bp/d (+0.49) | 3/6 | +57% / 0.31 / 40.7% | −0.2 (−0.28) | FAIL (consistency; 2019–23 paired < 0) |
| both (`_x3` / `_y3`) | +1391% / 2.13 / 33.4% | +6.7 bp/d (+2.27) | 4/6 | +60% / 0.32 / 40.7% | +0.1 (+0.11) | FAIL (Sharpe lower, max DD +3.2 pts) |

Average gross 1.09 / 1.20 / 1.11 / 1.22 in 2024–26 and 0.94–1.00 in 2019–23: the 1.5 ceiling and a 0.5 beta floor bind on few days, because a book as defensive as the 09-17 one (beta 0.12, vol 15%) is rare in the history. Raising the ceiling buys return at a lower Sharpe and a deeper drawdown even after interest; the floor does nothing measurable. No change to live sizing. The margin-interest charge stays in the replay from now on (baseline with interest +1090% against +993% without it on the same day: the difference is the filings-out switch, which the `_x0` baseline includes, net of the interest). Trials: 8.

## 2026-09-17 16:30 PT — shadow agent `insider`, pre-registered before its replay: opportunistic open-market insider purchases

**Definition (fixed before any result).** `agents/insider.py`: Form 4 code-P rows from Finnhub, point-in-time by filing date; a purchase counts for 60 calendar days from its filing; derivative transactions and purchases under $10k are ignored; a buyer who also bought in the same calendar month of an earlier year is routine and ignored (Cohen, Malloy & Pomorski 2012, with the two years of history available instead of their three); direction = tanh(0.4 × distinct buyers + 0.2 × log10(total dollars / 100k)), floor 0.05; confidence 0.3 + 0.1 × buyers, capped at 0.7; horizon 20; silent otherwise. Data collected 2026-09-16: 473 purchases in 71 of the 151 names since 2024-01, median filing lag 2 days, median size $64k.

**Replay (VM, `--shadow insider`, 500 days, live config, snapshot 2026-09-17, margin interest 7%).** A shadow agent never votes, so the book is the baseline's by construction (checked: the curve must equal `_x0`'s). Its rows are scored in the replay ledger. Measures, all on 20-day beta-abnormal returns: (1) event-study spread: per date, the mean outcome of names with an insider signal minus the mean of all other universe names that day, averaged over dates with a date-clustered t; (2) the same by half-year; (3) the pooled rank IC of the signal's direction among emitting rows. Expectation: about half of the published effect (McLean & Pontiff 2016), i.e. a spread around +0.4% per 20 days.

**Rules.** The agent goes live as a shadow (recorded and scored, never voting; ~3 minutes of Finnhub calls in the rule-agent stage) if measure (1) is not negative with t < −1. A voting test (adding it to `AGENTS`) needs measure (1) t ≥ 2 in the replay or 60 live sessions of shadow rows, and then passes or fails under protocol v4 like any change. Trials: 1 replay.

## 2026-09-17 17:10 PT — audit of the replay (independent read-only reviewer + own checks; user: "오버피팅, 데이터 leakage, trading cost ignoring, calculation error 따져줘 … 고쳐줘 … 루틴적으로")

**Clean:** training and labels (a label is usable only from its end date, `asof` filtered everywhere; warm start off in replays; betas trailing; winsor a constant, scale from training rows only); price adjustment (total-return convention, same for the book and the benchmarks); the arithmetic (return, Sharpe on log returns, drawdown reconcile; Sharpe on simple returns would be 2.46, with a 4.5% cash rate 2.10).

**Found and fixed (branch, 101 tests):**
1. **Frictionless daily rebalancing to constant weights** (backtest reset the book to yesterday's *targets*; the rebalance band pinned weights to targets, not to holdings; a free rebalancing bonus of roughly 7–9% a year, ×1.15–1.20 on the multiple). Fixed: holdings drift with their own returns (`backtest.drifted`), the band and the turnover see the drifted holdings, as `portfolio.plan` does live. `--no-drift` reproduces the old convention.
2. **FRED look-ahead in the macro regime**: `market.fred_latest` returned today's reading on every simulated day (NFCI −0.56 → +0.1 regime on all 470 days). Fixed: the FRED terms apply only when no `asof` is passed (live); the replay never reads them.
3. **Deflated Sharpe with the wrong trial count**: the report counted sweep files only (221 on the laptop, 0 on the VM → "1 trial", DSR 0.999). Fixed: `config.RESEARCH_TRIALS` (330) is a floor, to be raised with every round.
4. **Rank book undercharged**: a flat 0.5 bps/day; now its real membership turnover × 5 bps.
5. **Bugs**: `PIT_AGENTS` accumulated extras across in-process runs; the RSI precompute was never cleared; `best_quarter_share` could exceed 1 with a losing quarter (now against the winning quarters' sum); a held name with no price silently earned 0 while keeping its weight (now counted: `missing_return_name_days` in the report).
6. **Gate statistic**: the paired t assumed iid daily differences; `analyze_v4.py` now also prints a Newey-West t (10 lags).
7. Every report now carries `universe_ew_buy_hold`: the equal-weight buy-and-hold of the same names over the same window.

**Measured, not fixable by code (structural):** the universe is today's hindsight-selected list: equal-weight buy-and-hold of the 151 names made +245% over the 2024-10..2026-08 window (median name +126%, 93% up) against SOXX +152% and the book +1,090%, so the fair comparison line is +245%, not SOXX. The out-of-sample first 250 days were re-optimised across ~30 rounds since round 10 (their return went from +94% to ~+350%): the nominal OOS window is spent and the honest expectation is the Sharpe of round 10 (~0.9–1.0), not 2.18. Graph edges are today's structure and statement text was LLM-written in 2026 (hindsight wording); the graph agents are silent for the first ~250 days anyway. Costs: 5 bps is optimistic for the small names; the report's own table gives +893% at 15 bps and +656% at 30 bps. The label convention (signal-close label with the open refresh) was chosen because it produced the larger number (+895% vs +712%): recorded as a researcher degree of freedom.

**Pending checks (VM, same day, same machine):** `_a0` fixed replay (drift on, no FRED, margin 7%) = the new baseline for every later round; `_a1` `--no-drift` (the size of the rebalancing bonus); `_a2` `--earnings-shift 5` (perfect earnings-date knowledge); the 2019–23 pair `_b0` / `_b1`. Their numbers replace the +1,090% headline in the next report. A point-in-time constituent list (a 2024-10 universe) cannot be rebuilt from the data at hand; the equal-weight baseline is the proxy.

### Round 43 results (2026-09-17 16:30 PT, VM, margin 7%): the vol brake is a risk dial too; 0.50 stays

| Run | 2024–26: return / Sharpe / max DD | vs `_x0` (t) | Blocks ≥ 0 | 2019–23: return / Sharpe / max DD | vs `_y0` (t) | Gate |
|---|---|---|---|---|---|---|
| baseline 0.50 (`_x0` / `_y0`) | +1090% / 2.18 / 30.2% | — | — | +61% / 0.33 / 40.7% | — | base |
| brake off (`_v1` / `_u1`) | +1675% / 1.96 / 34.5% | +13.6 bp/d (+2.08) | 6/6 | +67% / 0.35 / 41.3% | +0.5 (+0.87) | FAIL (Sharpe, max DD +4.3) |
| expanding median (`_v2` / `_u2`) | +1298% / 2.14 / 32.2% | +4.8 bp/d (+1.98) | 5/6 | +64% / 0.40 / 36.5% | −0.4 (−0.29) | FAIL (Sharpe) |
| 0.40 (`_v3` / `_u3`) | +903% / 2.23 / 28.2% | −4.9 bp/d (−2.49) | 1/6 | +66% / 0.37 / 38.9% | +0.2 (+0.34) | FAIL (paired < 0) |

Off raises return with more drawdown and a lower Sharpe, stricter does the opposite, the median sits between: no setting improves return per unit of risk. Not adopted. With rounds 42–43 the three sizing dials (ceiling, beta floor, brake) are closed; further return has to come from information (agents), not from sizing. Trials: 6.

### Shadow agent `insider` — replay result (2026-09-17 16:35 PT, `_s0`, VM): recorded, no measurable edge; runs live as a shadow only

4,384 rows recorded (8.7 names a day, 59 distinct names), 4,342 scored at 20 days; the book equals the baseline's (non-voting). Event-study spread of signalled names over all other names: +0.23% per 20 days over 500 dates, overlap-adjusted t +0.23; by half-year +1.5%, +1.1%, −2.0%, −0.2%, +3.7% (2026H2, 33 dates); share of dates positive 47%; pooled rank IC among signalled rows −0.08 (more buyers or dollars did not mean more return). Signalled rows averaged +2.12% against +1.47% for all rows, but that raw gap is not date-matched. Reading: no edge is visible in this window; the published +0.8%/month is not there at half strength either. Under the pre-registered rule the agent goes live as a shadow (the spread is not negative), recorded and scored, never voting, and the voting question is revisited only with t ≥ 2 in a later replay or after 60 live sessions. Trials: 1.

### Audit re-baseline (2026-09-17 17:00 PT, VM, fixed replay): the corrected headline is +1,028% / Sharpe 2.14 / max DD 30.1%

Same day, same machine, live config (filings-out, demean, sleeve 200d), 7% margin interest, 5 bps, snapshot 2026-09-17:

| Run | Return / Sharpe / max DD | vs `_a0` paired (t, Newey-West) | What it isolates |
|---|---|---|---|
| `_a0` fixed replay (drifted holdings, no FRED look-ahead) | **+1028% / 2.14 / 30.1%** | — | the new baseline for every later round |
| `_a1` `--no-drift` (old convention) | +1090% / 2.18 / 30.2% | +1.1 bp/d (+1.33, +1.63) | the free constant-weight rebalancing: ~62 points of total return, ~3% a year |
| `_a2` `--earnings-shift 5` | +1001% / 2.11 / 30.8% | −0.5 bp/d (−0.20, −0.22) | perfect knowledge of earnings dates: small |
| `_x0` (pre-fix code, same day) | +1090% / 2.18 / 30.2% | identical to `_a1` | the FRED terms never acted on the VM (no key there); the look-ahead was a laptop-only defect |

Report fields now present in every run: equal-weight buy-and-hold of the same 142 priced names over the same window and marks **+245%** (against SOXX +152%), missing-price name-days 33 of ~6,500, deflated Sharpe 0.82 with 330 trials (expected best-of-330 Sharpe under no skill 1.46), bootstrap Sharpe CI about [1.1, 3.4]. At 30 bps the corrected book is roughly +600%. Reading for the user: the honest replay says the selection engine multiplies the universe's own +245% about four times over this window, the number is real at about 80% confidence after the search that produced it, and the live expectation stays Sharpe ~1 (the out-of-sample window was spent by rounds 10–43). `_b0` / `_b1` (2019–23, drift on/off) are the same check on the older window and are recorded when they finish.

**Audit re-baseline, 2019–23 (17:10 PT):** `_b0` fixed replay +53% / Sharpe 0.30 / max DD 41.2%; `_b1` no-drift +61% / 0.33 / 40.7% (the rebalancing convention is worth +0.44 bp/d there, t +1.4). Equal-weight buy-and-hold of the same 123 priced names over that window: **+160%**, SOXX +170%. On the older window the price-agent stack did not beat holding its own universe. The 2024–26 outperformance over the universe (+1,028% against +245%) is therefore either regime-specific or comes from what the older window cannot contain (graph statements, the Claude agents); the live paper track is the only test that separates the two. Recorded as the strongest caution in this audit.

## 2026-09-17 17:30 PT — round 44, pre-registered before any result: what the graph adds, and link momentum (customer / supplier) as new information

**Why (user: "AI 시대의 정보").** The audit left the question open whether the 2024–26 edge over the universe (+1,028% against +245%) comes from the AI-era information (graph statements, Claude agents) or from the price stack alone (which lost to its universe in 2019–23). And the classic supply-chain signal is not in the roster: a supplier's customers' stock returns predict the supplier's next month (Cohen & Frazzini 2008, ~1.5% a month in 1980–2004, decayed since); the mirror, supplier momentum for customers (Menzly & Ozbas 2010). `neighbors` reads customers' statements, not their prices.

**Agents (fixed before any result).** `agents/customer_momentum.py`: for each name, the mean trailing 21-session return of its graph customers (edges supplier → customer, universe names only) minus SOXX's; direction = tanh(8 × that); confidence 0.3 + 0.05 × customers, capped 0.7; horizon 20; silent without a priced customer. `agents/supplier_momentum.py`: the same on the supplier side. Edges are today's structure (the graph-wide caveat).

**Runs (VM, same machine and day, fixed replay, margin 7%, snapshot 2026-09-17):**
- 2024–26: `_c0` baseline; `_c1` `--agents technical,mean_reversion,risk,macro,events` (price stack only: what the graph agents add in their covered months); `_c2` `--shadow customer_momentum,supplier_momentum` (both recorded, scored, non-voting: event-study spread and IC with `insider_eval.py`); `_c3` `--extra customer_momentum` and `_c4` `--extra supplier_momentum` (voting candidates).
- 2019–23: `_d0` baseline, `_d3` and `_d4` the two voting candidates (the older window has the prices; the edges are today's).
- Gate v4 for `_c3` / `_c4` against `_c0`, confirmation on `_d3` / `_d4` against `_d0`. `_c1` is a diagnostic, not a gate. Expectation: link momentum at half the published effect would be worth about +0.5 bp/d; the graph diagnostic is expected to show most of the 2025-10 onward difference. Trials: 5 (+2 diagnostics).

### Round 44 results, 2024–26 (2026-09-17 18:05 PT, VM, fixed replay): customer momentum is a real signal; as a vote it fails block consistency; the graph agents net about zero in their covered months

| Run | Return / Sharpe / max DD | IC | vs `_c0` paired (t, NW) | Blocks ≥ 0 | Gate |
|---|---|---|---|---|---|
| `_c0` baseline | +1031% / 2.14 / 30.1% | 0.029 | — | — | base |
| `_c1` price agents only (no supply_chain / neighbors) | +1021% / 2.17 / 24.1% | 0.037 | −0.4 bp/d (−0.11, −0.13) | 3/6 [+1.0, −8.9, +3.0, −0.9, −11.2, +29.0] | diagnostic |
| `_c2` both link agents as shadows | = `_c0` by construction | | | | shadow eval below |
| `_c3` + customer_momentum (voting) | +1469% / 2.33 / 31.4% | 0.044 | +7.6 bp/d (+1.31, +1.20) | 3/6 [+17.7, −9.6, −8.6, +10.2, −2.9, +4.2] | FAIL (consistency) |
| `_c4` + supplier_momentum (voting) | +842% / 1.98 / 31.4% | 0.029 | −3.9 bp/d (−1.98, −1.78) | 1/6 | FAIL |

Shadow evaluation (`_c2` ledger, 20-day beta-abnormal, event-study spread of signalled names over the rest): **customer_momentum** 46,381 scored rows (93 names a day): +0.82% per 20 d, overlap-adjusted t +1.46, positive in every half-year (+0.99, +0.90, +0.59, +0.76, +1.16), 61% of dates positive, pooled rank IC +0.097. **supplier_momentum**: +0.89% but −0.06% in 2024H2, IC +0.015. The published customer-momentum effect (~1.5% a month, 1980–2004) shows up here at about half strength, as the protocol expected of a published anomaly.

**Reading.** (1) Customer momentum carries information (the most consistent signal measured so far), but as a voting agent it swings the whole book: it wins the 2024Q4 and 2025Q4–2026Q1 blocks and loses the two 2025 crash-and-rebound blocks, the same reversal signature as residual momentum (round 40). Not adopted as a vote under v4; from 09-18 it runs live as a shadow. Pre-registered next (round 45): the same agent gated to trend states (emit only while SOXX is above its 50-day average, the momentum-crash guard of Daniel & Moskowitz 2016), one value, judged under v4 on a fresh day, plus the 2019–23 confirmation from `_d3` / `_d4`. (2) The graph agents supply_chain and neighbors net about zero over their covered months with six points more drawdown (they helped in 2025-01..05 and 2026-01..04 and hurt in 2026-04..08). Removing them fails v4 (paired −0.4 bp/d), so they stay; the finding is recorded as the question the live Claude agents, which the replay cannot contain, will have to answer. Trials: 5 (+2 diagnostics).

**Round 44, 2019–23 confirmation (18:20 PT):** `_d0` +52% / 0.29 / 41.2%; `_d3` + customer_momentum +69% / 0.36 / 46.8% (paired +1.0 bp/d, t +0.79, 5/6 blocks, max DD +5.6 pts → FAIL on the +3 limit); `_d4` + supplier_momentum +45% / 0.26 / 46.7% (FAIL). Customer momentum therefore raises return and Sharpe on both windows and raises drawdown on both: a more-return-more-risk vote, not a free improvement. Decision stands: live shadow from 09-18, no vote; round 45 (trend-gated variant) is the pre-registered next test. Round closed; trials 8 in total (5 + 2 diagnostics + 1 confirmation pair).

### Round 44 adoption (2026-09-17 19:00 PT): customer momentum votes from the 09-18 cycle, by the user's decision, drawdown cost on record

The user chose the return and Sharpe over the drawdown ("낙폭 증가해도 샤프랑 수익률 늘었으니까 하자"). Under protocol v4 the variant had failed (block consistency 3/6 on 2024–26, drawdown +5.6 pts on 2019–23); the decision is the user's and is recorded as such. Measured cost: max drawdown 30.1% → 31.4% (2024–26) and 41.2% → 46.8% (2019–23), with the losses concentrated in sharp rebound blocks (2025-01..09). Measured gain: +1031% → +1469%, Sharpe 2.14 → 2.33 (2024–26); +52% → +69%, 0.29 → 0.36 (2019–23); learned IC 0.029 → 0.044.

Applied: `customer_momentum` appended to `config.AGENTS` after `macro` (a free agent, prices and graph edges only, not in the open refresh, as in the replay); `SHADOW_AGENTS = ("insider",)`; the live warm start replaced by the `_c3` replay ledger (fixed replay, live config, the agent's rows from 2024-08), previous file kept as `state/backtest_w2_before_c3_20260917.sqlite`. The learner refits at 03:30 with 12 voting agents (yesterday's model is rejected by its roster check). Expect a larger rebalance at the 09-18 open. Trial count for RESEARCH_TRIALS: raise to 350 at the next round.

## 2026-09-17 19:35 PT — round 45, pre-registered before any result: momentum-crash guards, the graph agents one at a time, conviction smoothing, a third horizon

**Baseline** `_e0`: the live roster of 09-18 (12 voters incl. customer_momentum), fixed replay, margin 7%, snapshot 2026-09-17, price cache of the day, VM. Every variant below is judged against it under protocol v4 (full window, 4/6 blocks, 2019–23 confirmation for passes).
- `_e1` `--momentum-gate`: customer_momentum silent while SOXX is at or below its 50-day average (Daniel & Moskowitz 2016: momentum crashes are rebounds after bear markets; round 44's losses sat in the 2025 rebound blocks). One window (50 d), no tuning.
- `_e2` `--momentum-vol-scale`: the customer basket's signal scaled by its 60-session realised vol to a 10%-per-21-day target, multiplier 0.25..2 (Barroso & Santa-Clara 2015, "Momentum has its moments").
- `_e3` no `neighbors`; `_e4` no `supply_chain` (round 44's diagnostic: both together net ≈ 0 with +6 pts drawdown; which one carries it?).
- `_e5` `--conviction-ema 0.5`: sizing-side smoothing of convictions (half yesterday, half today) against turnover 0.40/day; rounds 12–15 rejected hysteresis on the old cost model, the drifted replay and margin interest change the accounting.
- `_e6` `--horizons 10,20,40`: a third, slower label for the slow signals (customer momentum, graph statements); dropping the 5-day horizon was the biggest single gain in v2.3, adding a slower one is the untested side.
- `_e7` `--momentum-gate --momentum-vol-scale` (both guards).
Hypotheses: `_e1`/`_e2` lower the 2025 rebound losses at a small cost elsewhere; `_e3`/`_e4` identify the weaker graph agent; `_e5` cuts turnover cost with some signal lag; `_e6` is inside noise. Adoption of anything passing is decided the next evening, after the 09-18 live session, one change a day. Trials: 7.

### Round 45 results (2026-09-17 20:20 PT, VM, fixed replay, code 4871bfd): nothing passes; the trend gate is a risk dial, supply_chain carries the graph's value, conviction smoothing halves turnover at a small cost

The first batch was void: the replay instantiated a fixed tuple of agent modules, so `customer_momentum` never executed and the three momentum-guard variants were byte-identical to the baseline (fixed in 4871bfd, simulated agents outside the fixed set are imported by name, test `SimulatedRoster`; the whole batch re-run from scratch). This time `_e0` holds 48,178 customer_momentum rows and the gated runs `_e1`/`_e7` 31,122 (silent on the days SOXX sat at or below its 50-day average). `_e0` reproduces round 44's `_c3` on the full window (+1469% / 2.33 / 31.4% at 5 bps); the gate table is on the 450 common sessions 2024-10-01..2026-07-20.

| Run | Return / Sharpe / max DD | Turnover | IC | vs `_e0` paired (t, NW) | Blocks ≥ 0 | Gate |
|---|---|---|---|---|---|---|
| `_e0` live roster of 09-18 | +1573% / 2.49 / 27.1% | 0.41 | 0.044 | — | — | base |
| `_e1` momentum trend gate | +1224% / 2.29 / 22.7% | 0.40 | 0.037 | −5.4 bp/d (−1.21, −1.34) | 3/6 [−17.0, +9.9, +0.4, −1.4, −9.9, +4.7] | FAIL |
| `_e2` momentum vol scale | +1154% / 2.26 / 30.1% | 0.42 | 0.044 | −6.7 bp/d (−1.80, −1.69) | 3/6 | FAIL |
| `_e3` no neighbors | +1486% / 2.48 / 27.4% | 0.42 | 0.041 | −1.5 bp/d (−0.48, −0.64) | 2/6 | FAIL |
| `_e4` no supply_chain | +1341% / 2.39 / 27.4% | 0.42 | 0.050 | −3.6 bp/d (−1.14, −1.81) | 1/6 | FAIL |
| `_e5` conviction EMA 0.5 | +1423% / 2.42 / 25.7% | 0.24 | 0.044 | −2.3 bp/d (−0.51, −0.62) | 2/6 [−18.0, −1.9, −1.6, −15.2, +4.2, +9.8] | FAIL |
| `_e6` horizons 10/20/40 | +1420% / 2.37 / 32.9% | 0.41 | 0.046 | −2.0 bp/d (−0.43, −0.40) | 2/6 | FAIL |
| `_e7` gate + vol scale | +1105% / 2.23 / 22.6% | 0.40 | 0.037 | −7.6 bp/d (−1.64, −1.59) | 4/6 | FAIL (paired, Sharpe) |

**Reading.** (1) The momentum-crash guards behave like the sizing dials of rounds 42–43: the trend gate takes 4.4 points off the drawdown and 5 bp/d off the return (its first block, 2024Q4, is where it is silent through a rising market's dips: −17 pts), vol scaling loses on both sides. Customer momentum stays as adopted, ungated. (2) Of the two graph agents, supply_chain carries the value (−3.6 bp/d without it, 1/6 blocks) and neighbors is close to nothing (−1.5 bp/d, t −0.5): neighbors is the candidate to demote to a shadow if a later round confirms it; not touched today (removing it does not pass either). (3) Conviction smoothing halves turnover (0.41 → 0.24/day) for −2.3 bp/d at the gate's 5 bps; the reports' own cost tables put the crossover between 15 and 30 bps (at 15 bps +1163% / 2.16 against +1197% / 2.17; at 30 bps +961% / 2.01 against +874% / 1.93). The EMA is the right setting if the live cost per unit turnover is above ~15 bps and wrong below it, so the decision is deferred to a measurement, not a replay: the realised slippage of the live fills (`state/trades.json` fills against the signal close and the open) is the next diagnostic. (4) A third, slower horizon adds 5.8 points of drawdown for nothing. Nothing adopted; no 2019–23 confirmation needed; VM stopped. Trials: 7 (`RESEARCH_TRIALS` raised to 350).

## 2026-09-18 00:30 PT — literature and practitioner sweep with a two-agent debate (user: "우리랑 비슷하게 한 거 논문이나 레딧글 찾아서 향상시킬 방법 찾아내, 멀티에이전트로 서로 토론도 하고"); protocol v4.1; round 46 pre-registered before any result

**Method.** Three Sonnet scouts (multi-agent LLM trading papers 2023–26; asset-pricing evidence and free dated data for semiconductor names; practitioner reports on Reddit, GitHub, blogs and the LLM trading arenas), then an Opus proposer and an Opus skeptic, two rounds each, cross-reading the other's file; the judgement below is the session's. Reports kept in the job's tmp (`scout_llm_papers.md`, `scout_finance.md`, `scout_practitioner.md`, `debate_{proposer,skeptic}_r{1,2}.md`). Citations marked verified were fetched by the scouts (arXiv/DOI pages); UNVERIFIED items are named as such in the files.

**What the literature says about systems like this one.**
- The multi-agent LLM trading genre (TradingAgents 2412.20138, FinCon 2407.06567, FinMem 2311.13743, FinAgent 2402.18485, HedgeAgents 2502.13165) reports Sharpes of 3–8 on one to three names over months inside the models' training coverage, with no ablation of the debate or risk desks; the HedgeAgents authors' own follow-up (Profit Mirage, 2510.07920) calls the genre's backtests a mirage that evaporates past the knowledge cutoff, and FinCAD (2605.24564) measures the memorisation correction at up to −67 points of in-sample return. Of 77 agentic-trading studies audited (2605.19337), 19 met basic rigour, 2 used time-consistent splits, 1 had a cost model. The live arenas (Agent Market Arena 2510.11695, LiveTradeBench 2511.03628, nof1's Alpha Arena) show that framework design, not the backbone model, drives behaviour, that leaderboards invert between rounds, and that overtrading is the most common loss mechanism. Bybee (2305.02823): LLM-generated return expectations from news are extrapolative and negatively related to realised returns out of sample. Reading for SemiBand: the architecture already has what the practitioner consensus recommends (the LLM proposes, deterministic code sizes; a conviction floor; a learner that can down-weight an agent); nothing in this genre offers a measured improvement to import, and the live paper track remains the only evidence about the three Claude agents. The confidence-into-sizing result that looked strongest (arXiv 2609.00187, +9.2 pp a year) shrinks to +1.2 pp (p 0.14) under walk-forward checks (jjakimoto/research-issues #1470): whether the Claude agents' `direction × confidence` columns help is a live-only question (dual-log both encodings; diagnostics below).
- Asset pricing: technological-link momentum (Lee, Sun, Wang & Zhang 2019, JFE 132; Hoberg–Phillips TNIC peers, free, vintages from 1996) is the strongest untested new-information source, to be screened for overlap with customer_momentum before any trial; Wang 2025 (JFQA, "Decoding momentum spillover effects") finds the connected-firm spillover lives in the intraday leg while the overnight leg reverses — a measurement fix for customer_momentum; Ramnath 2002 / Zhu 2014: customer earnings surprises transfer to suppliers (the fundamentals channel beside the price channel); Martineau 2022 ("Rest in peace PEAD", Critical Finance Review 11): the drift is gone outside microcaps since about 2006, which questions `events`' drift leg for the large names; FINRA short interest (free, 2003–) as an avoid signal, queued; 13F crowding, Korea/Taiwan/Japan customs series and per-name MA filters dropped (eight quarterly points; level signals in a cross-sectionally demeaned book; `_e1` measured the trend filter's shape this round). Matsumoto, Pronk & Roelofsen 2011 (Q&A tone) and Bozanic et al. 2018 (vagueness) are computable on the graph's statements without LLM calls but untestable before 2025-10 — shadow candidates for later.
- Practice: the forecast-combination puzzle (equal weights beat estimated weights out of sample when histories are short and forecasters many; Bates–Granger tradition) is the strongest evidence that touches the learner. The debate found, and the session verified, that the ridge's prior strength (λ = 150 pseudo-observations against ~15–20k decayed rows per horizon) is under 1% of the fit — the "strong shrinkage to equal weights" the design describes is not there — and `config.py:99` records that walk-forward CV kept choosing λ = 1000 and was overruled by a return sweep (Sharpe 2.2–2.3 vs 1.7 on the old replay). This is the upstream assumption of every round since 10; round 46 tests it.

**Debate findings that change the protocol or the books (each verified in code by the session):**
1. **Fills were never measured.** `journal.py` stores order intents (last 500 rows) and no fill price; the replay charges `COST_BPS` once per dollar traded one-way (`backtest.py:502` `turnover = Σ|Δw|`, `:515`), so its 5 bps is the whole open-execution cost and the reports' 15/30 bps columns are one-way numbers. `slippage.py` (new, read-only) measures the notional-weighted adverse slippage of the account's fills against the official 09:30 open (Alpaca daily bars, SIP then IEX), open-window fills (≤ 09:45 ET) separated from later ones. **Pre-registered before its first run: the conviction EMA 0.5 (round 45 `_e5`: −2.3 bp/d at 5 bps, turnover 0.41 → 0.24, break-even 18.5 bps from D(c) = −2.3 + 0.17 (c − 5)) is adopted iff the open-window headline is ≥ 18.5 bps per dollar traded; otherwise the item is closed.** Caveats: paper fills carry the spread but no impact (a floor for a real account); `_e5`'s −2.3 bp/d has t −0.5, so the break-even is a tie-breaker on a measurement. (`config.py:155` calls COST_BPS a round-trip cost; the replay charges it one-way — noted, not changed.)
2. **Protocol v4.1, pre-registered, from round 46 on; no recorded verdict changes.** (a) A tie is never a pass: a block in which the candidate's and the baseline's daily returns are identical on every day is non-informative and leaves both numerator and denominator; the requirement becomes a paired difference ≥ 0 in at least two thirds of the informative blocks (rounded up), with at least three informative blocks. (b) A candidate that can act only on part of the window (graph statements from 2025-10, a series that starts late) is also scored on the affected days alone: four contiguous blocks, the first 10 days of each purged, each block at least 20 days, requirement ≥ 3 of 4; a candidate that cannot meet the block minimum is not gateable and can only be a shadow. (c) No retro-application: `GRAPH_TRANSCRIPTS_ONLY` (round 41, blocks [0, 0, 0, +0.3, +12.8, −2.7], three of them identical) is re-scored under (a)/(b) for information only, 0 trials; any revert would be its own pre-registered round. `analyze_v4.py` implements (a) and, with `--affected-from`, (b).
3. **customer_momentum's confidence** (`0.3 + 0.05 × customers`) uses today's edge count (`graph_pit` builds the customer table without an asof): a static hindsight connectivity tilt inside the `direction × confidence` column, the same class as the edges caveat. Measured in round 46 (does the count carry forward information?); if it does not, the fix (a constant confidence) is round 47's, not bundled into `_f4`.
4. `events` has voted with a negative IC at every horizon on record: split by leg (pre-earnings risk, post-earnings drift) and by cap tercile in round 46 (0 trials); a roster change is round 47's.

**Round 46 — pre-registered before any run (VM, same day and machine, fixed replay, margin 7%, snapshot of the day; gate v4.1; 2019–23 confirmation for passes; one adoption a day, the next evening after the live session).**
- `_f0` baseline = the live roster, plus `--shadow customer_sue` (new agent, non-voting: for each name, the mean latest EPS surprise (%) of its graph customers whose report date is strictly before the day and within 30 sessions; direction = tanh(surprise / 10), confidence 0.4, horizon 20; reads the `market.earnings` rows the replay already loads for `events`, point-in-time by `date < asof`). Promotion bar fixed now: event-study spread ≥ +0.4% per 20 days with t ≥ 1 and positive in ≥ 4 of 5 half-years, else it never becomes a voting candidate. A coverage census runs first (names per day with a customer print inside 30 sessions); under ~25 a day the shadow is not scored.
- `_f1 --prior-only` (diagnostic, existing flag): if its paired difference vs `_f0` has Newey-West |t| < 1, the fitted weights are not measurably better than the equal-weight blend on this window and every verdict since round 10 is recorded as conditional on a λ chosen for return.
- `_f2 --prior-strength 1000` (new flag; the CV's own repeatedly chosen value): pass = v4.1 as written, or the weaker reading pre-registered here — paired ≥ −1.5 bp/d with ≥ 5/6 blocks and max DD ≤ base (a variance argument the replay cannot score in return).
- `_f3 --drop-dir <all 12 agents>` (existing flag): the direction-only columns have prior mean zero, so this is infinite shrinkage on exactly those columns with no value to choose; same pass rule as `_f2`. If both pass, only the one with the better paired difference is adopted (one change a day).
- `_f4 --momentum-intraday` (new flag): customer_momentum measures its customers' 21-session return as the compounded open→close legs (Wang 2025), each leg from the same completed session's open and close — the agent's frame ends at the signal day, never at the next open, which is the fill price; a name with fewer than 15 of 21 valid open/close pairs falls back to close-to-close; opens and closes from the same cache day. Pass = v4.1 full-window paired ≥ 0 vs `_f0` and, in `_c3`'s worst block (block 2), a paired difference vs `_f0` of ≥ +7.6 bp/d (the block's loss relative to a no-momentum book shrinks from −9.6 to ≥ −2 bp/d); 2019–23 confirmation max DD ≤ base + 3 (it is +5.6 today). A point-in-time test guards the frame before any number is quoted.
- Zero-trial diagnostics alongside, on existing ledgers: the fills (`slippage.py`, decides the EMA); the 12×12 agent redundancy map on the `_e0` ledger (screens TNIC before any trial and re-checks the `neighbors` demotion hint); the customer-count forward-information check; `events` by leg and cap tercile; the Claude agents' sign-flip rate and confidence calibration (IC by confidence bucket, live ledger); the round-41 re-score under v4.1.
- Dropped from the scouts' 22 candidates (reasons in the debate files): a disagreement feature (round 38's intercept in another form), a fast Hedge overlay (opposite to the combination evidence; `HEDGE_ETA` is already a reference line), memorisation and self-critique prompts for the Claude agents (they restart the live clock; `llm_guidance_anon` covers the memorisation question), 13F crowding, the customs series, the per-name MA filter, meta-labelling, a per-agent turnover cap (a sizing knob), FINRA short interest (queued; < 1.5 bp/d expected after decay), TNIC momentum (queued behind the redundancy map).
- Expected: `_f1` |t| between 1 and 2 (the fitted weights help a little); `_f2` / `_f3` inside ±2 bp/d with fewer losing blocks; `_f4` a smaller worst block at a small full-window cost. Trials: 4 (+ up to 2 confirmations); `RESEARCH_TRIALS` → 356 at the close of the round.

**Round-41 re-score under v4.1 (2026-09-18 00:50 PT, 0 trials, `analyze_v4.py _w0 _w2 --affected-from 2025-10-01`):** `_w2` (filings out of the graph agents) vs `_w0`: paired +2.3 bp/d (t +1.48, Newey-West +1.76); six blocks [0, 0, 0, +0.3, +12.8, −2.7] → three ties excluded, 2 of 3 informative (need 2); the 220 affected days from 2025-10-01 in four blocks [+2.2, +14.9, +13.6, −4.8] → 3 of 4. PASS under the amended rule as well; the adoption stands on its own record.

### Round 46 zero-trial diagnostics (2026-09-18 01:20 PT, the `_c3` ledger = the live warm start, 2024-08..2026-08; `diag_round46.py` in the job's tmp)

(a) **Redundancy map** (correlation of direction × confidence over date × name; silence = 0 above the diagonal, both-spoke below): customer_momentum is close to orthogonal to every other agent (|r| ≤ 0.17: technical +0.10 / +0.13, neighbors −0.17 with silence as 0 and −0.01 when both speak); technical–mean_reversion −0.50 (by design), neighbors–supply_chain +0.60 when both speak (+0.12 with silence as 0), supply_chain–events +0.27, macro–risk −0.24, macro–technical +0.21. Reading: the roster's overlap sits in the two graph agents and in the technical / mean-reversion pair; a TNIC agent would be screened against technical and customer_momentum with this map.

(b) **customer_momentum's customer count** (46,381 scored rows, 2.8 customers per row): per-date rank IC of the count against the 20-day beta-abnormal return +0.025 (overlap-adjusted t +1.17, 500 dates) against +0.055 (t +1.97) for the direction and +0.048 (t +1.67) for direction × confidence; the mean abnormal return by count is not monotonic (1: +1.4%, 2: +3.0%, 4: +0.35%, 7: −1.8%, 8: +2.4%). The count carries no measurable forward information and the confidence weighting dilutes the direction's IC: a constant confidence (0.5) for the agent is a round-47 candidate (one replay under v4.1).

(c) **`events` by leg and cap tercile** (caps from the fundamentals cache of 2026-09-17; 18,376 scored rows): the pre-earnings leg (direction −0.25, "event risk") votes against a positive average return — names about to report made +1.5% (large), +1.4% (mid), +2.6% (small) beta-abnormal over the next 10 days (+1.8 / +1.1 / +2.4% over 20), hit rates 0.46–0.53, so its signed contribution is −1.5 to −2.6% per row; the post-earnings drift leg carries an IC of +0.076 (t +1.2) in the small tercile, 0.00 in the mid and −0.067 (t −1.0) in the large one at 10 days (+0.061 / +0.042 / −0.024 at 20): Martineau 2022's pattern, the drift alive only in the small names. Because the ridge can hold a negative weight on events and may already trade the pre-leg's error backwards, the fix is not read off the table: round-47 candidates, one replay each, are `events` without the pre-earnings leg, and its drift leg restricted to the below-median-cap names.

(d) **customer_sue coverage** (40-quarter earnings cache of 2026-09-17, today's edges, 500 sessions to 2026-08-17): 61.8 names a day on average (median 60, min 22, max 97), 92% of days at or above 25, 98 linked names — the shadow is scorable and runs in `_f0`.
