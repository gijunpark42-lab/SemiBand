# Higher-exposure comparison: operating handoff — 2026-09-12

## Decision and the user's actual concern

USER FINAL DECISION: KEEP the current signal-sized, cash-holding structure. Do not apply an exposure change. Wrap up, record and push the research only.

No supported material upgrade among the four alternatives.

Preserve the predeclared screen; do not interpret small Sharpe gaps as proof of inferiority. Higher total return with higher drawdown can be a risk-preference choice, not a statistically established improvement. This research does not apply a winner. Parent owns integration; operational gross 1.50 / size 0.60 remain unchanged by this runner.

Cash drag is real on the recent baseline's 64 days below 20% exposure: mean gross 9.8%, conditional account return +0.58%, SOXX +16.77%. Exact mean daily excess: selection -1.16bps + utilization -26.82bps − trading 0.93bps. This conditional subset is not a continuous return history.

The same-name unit-gross sleeve on its 48 active subset dates returned +11.17% before costs versus +12.76% for SOXX on exactly those dates. Cash dominated the account shortfall, but that does not establish chosen-name superiority on low-deployment days. The real PAPER account has only two sessions; live edge cannot be inferred.

## Fixed comparisons: cap-tier trading costs +5% annual financing

| Variant | Recent return / Sharpe / DD | Recent OOS Sharpe | Stress return / Sharpe / DD | Mean gross recent / stress | Recent low-day gross |
|---|---:|---:|---:|---:|---:|
| baseline | +763.32% / 2.007 / 32.7% | 2.188 | +14.51% / 0.120 / 37.2% | 93.5% / 55.2% | 9.8% |
| gross_200 | +963.33% / 1.937 / 36.5% | 2.143 | +11.69% / 0.092 / 39.6% | 103.8% / 58.9% | 9.7% |
| size_080 | +811.83% / 2.019 / 33.4% | 2.118 | +12.98% / 0.097 / 43.4% | 97.4% / 62.9% | 12.7% |
| gross_200_size_080 | +1059.97% / 1.953 / 37.1% | 2.138 | +8.69% / 0.060 / 45.3% | 111.8% / 71.2% | 12.6% |
| rank_floor_005 | +865.47% / 2.045 / 37.9% | 2.024 | +42.88% / 0.246 / 38.1% | 105.4% / 97.9% | 61.3% |

Gross 2 is a ceiling, not a deployment target. Size 0.8 scales eligible names but leaves many low-conviction dates mostly cash. Rank+5% floor materially lifts low exposure, but admits weaker positive names and is not a guaranteed whole-book floor; it must be evaluated with its drawdown, stress and cost behavior.

| Variant | 30 bps +5%: recent return / Sharpe / DD | 30 bps +5%: stress return / Sharpe / DD | 10% financing, cap costs: recent / stress returns |
|---|---:|---:|---:|
| baseline | +512.25% / 1.685 / 36.7% | -47.83% / -0.574 / 57.3% | +751.98% / +11.92% |
| gross_200 | +616.16% / 1.610 / 40.4% | -51.66% / -0.600 / 60.6% | +938.48% / +8.23% |
| size_080 | +521.18% / 1.665 / 37.7% | -55.16% / -0.637 / 62.6% | +797.23% / +9.48% |
| gross_200_size_080 | +641.34% / 1.594 / 41.5% | -61.29% / -0.676 / 67.3% | +1016.99% / +3.33% |
| rank_floor_005 | +550.53% / 1.687 / 42.2% | -66.22% / -0.746 / 70.4% | +851.74% / +39.43% |

## Validation, uncertainty and continuation

- Five predeclared variants × two regimes × two trading-cost models × three financing rates = 60 completed scenarios. Daily refits on 470 recent and 1,170 stress dates; OOS signal date strictly before 2025-09-24. Beta outcomes already occupy legacy `abnormal`, read explicitly as `target_mode='raw'`.
- Minimum screen: recent OOS Sharpe improves, full Sharpe/score do not fall. Material screen adds >0.15 full/OOS Sharpe gain, DD within 2 pp, at least 80% baseline return, nonlower stress return/Sharpe. All four alternatives fail the minimum and material screens in this run.
- Financing applies the same `max(gross-1,0)*rate*calendar_days/365` rule to every book, including baseline, inside the volatility-feedback replay. Rates 0/5/10% are hypothetical sensitivities, not broker quotes; no positive-cash yield.
- Twelve zero-financing parity comparisons against unchanged `sweep.simulate` passed, including every daily rounded log return; six sizing/financing/attribution unit tests passed. Input ledgers remained byte-identical. Current versus prior zero-financing baseline figures are recorded in the detailed report; price snapshot identity is not assumed.
- Additional paired 40/80-day bootstrap, PBO and DSR diagnostics were deliberately NOT run because the user requested immediate wrap-up. This is an explicitly incomplete statistical-diagnostic phase, not missing scenario results. Resume by running the analyzer without `--quick`; no new model fits or variant selection are needed. These reused data are not a fresh holdout; survivor-biased universe, incomplete correlated trial history and stress's price/calendar-only information set prevent a production-edge claim.
- Price snapshot is one newly fetched common adjusted Open/Close panel, 2018-01-02–2026-09-11, SHA-256 `fad4ad3c41cbbbef89c2395ce294cd0ee5ad31b6c9432ac5791ecea0f81b0458`. Original round24 frames were not retained. PLAB was retried alone before any simulation; every comparison uses the completed snapshot.
- Inherited simulator limits: nondrifting target weights, missing prices marked zero return, rebalance band after gross/vol controls can exceed the stated ceiling, no impact/fill/buying-power/margin-call modeling. Vol 50% scales down only, never up to fill cash.
- Parent's separate saved-Friday-opinion diagnostic: raw target 7.90%; activated-beta target 27.67% in 4 names; beta size 0.8 target 36.90%; gross 2 alone unchanged. These are model targets, without guardian/account-vol/bands/fills, not actual holdings or new orders.

Committed reproduction sources: `research_higher_exposure_20260912.py`, this folder's `analyze_results.py`, `test_financing_replay.py`, `protocol.md`, `attribution_protocol.md`, and this report. Large input prices/model caches/full curves/results stay local and are not committed. Run both `--regime` commands then the analyzer as described in the detailed report. No operational source/defaults, broker activity, schedules, LLM calls or dashboards changed.

Local evidence: same-folder `report.md` (full tables/uncertainty), `summary.json` (metrics/attribution), `results_recent.json` and `results_stress.json` (full curves), `price_manifest_complete.json` (provenance), daily-model caches. Root-facing copy: top-level `outputs/higher_exposure_report_20260912.md`. For continuation, audit these artifacts before any separate user-authorized deployment/integration decision.
