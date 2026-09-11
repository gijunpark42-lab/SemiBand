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

_(results table and decisions below are filled in from `state/backtest_sweep10_open500.json`)_
