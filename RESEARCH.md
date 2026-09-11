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
