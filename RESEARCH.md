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
| walk-forward IC < 0 → half size | (2024-26: +425% / 1.49) | | | | | rejected earlier |

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
