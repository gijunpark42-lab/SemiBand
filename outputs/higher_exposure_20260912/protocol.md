# Higher-exposure comparison — fixed before results

2026-09-12, Codex Astra xhigh. Research only in this isolated checkout. The parent agent owns any operational decision. No orders, LLM calls, dashboard publications, live files, default configuration, or source ledgers are modified.

## Question and five frozen variants

The user expected approximately 200% exposure but observed about 7.6%. A gross ceiling is not an exposure target: eligibility, conviction sizing, name caps and downward-only volatility control determine the actual book.

Baseline: beta-adjusted labels, signed ridge, lambda 150, half-life 90 calendar days, horizons 10/20, entry 0.10, size_k 0.60, per-name cap 0.15, top 15, gross ceiling 1.50, band 0.30, portfolio volatility target 0.50. Daily refits, 30-date warmup, next-open execution. All other optional overlays off, using the existing simulator's default seven-agent replay roster for every variant on a given ledger. Stress inputs have fewer speaking agents; silent features are preserved consistently with the existing round-24 replay.

1. `baseline`: no change.
2. `gross_200`: gross ceiling 2.00 only.
3. `size_080`: size_k 0.80 only.
4. `gross_200_size_080`: both changes, explicitly a combination attribution test.
5. `rank_floor_005`: existing rank_always=True, floor_w=0.05, otherwise baseline. Hold up to 15 positive-conviction names; each gets at least 5% before gross/volatility controls. This is a deployment-floor comparator, not a guaranteed 75% book floor and not a 200% target. It repeats the already documented round-17 setting on the now-beta target without optimizing the setting.

## Data, isolation and alignment

- Recent ledger: `state/backtest_research_good_beta.sqlite`.
- Stress ledger: `state/backtest_research_pre2024_beta.sqlite`.
- These legacy copies already put beta-adjusted outcomes in `scores.abnormal`, so the unchanged learner is called with target_mode='raw' explicitly. This means read the legacy column, not revert to raw SOXX-relative labels.
- Exact score availability (`scored_date <= fit date`), fold-local scaling, no implicit warm start. Fit each date once and share that identical model/conviction across variants because all learner inputs are identical. This is daily refitting, not frozen or sparse refitting.
- Freeze one adjusted-open/close snapshot per regime and reuse it for every variant/cost/rate. Record source paths, retrieval dates, hashes and any difference from prior reported baseline results. Do not silently fetch a new snapshot for individual variants.
- OOS signal dates are strictly before 2025-09-24; later dates are the already tuned IS window. Both periods have been reused and are exploratory. Stress is a different information set and survivorship-biased roster, not validation of graph/LLM inputs.

## Costs and financing

Run all five variants with cap-tier costs (5/10/20 bps per unit turnover using the unchanged universe market-cap snapshot) and fixed 30 bps stress; running the whole small set avoids selecting cost checks after seeing returns.

For each cost setting run 0%, 5%, and 10% annual financing. The 5% scenario is the primary comparison; 0% is only a parity/attribution reference and 10% is stress, not a claim about the broker's current rate. Debit `max(long_gross - 1, 0) * annual_rate * calendar_days_between_execution_opens / 365` from each day's equity return. Apply the exact same rule to baseline. No yield on positive cash. Financing is inside the replay, so it enters the trailing 20-return volatility control and subsequent sizing. All variants are long-only; cash=1-gross and borrowed=max(gross-1,0).

Keep the existing simulator's weight bookkeeping, missing-price treatment and rebalance-band ordering. Verify the standalone replay against unchanged sweep.simulate at zero financing, with identical cached daily models. Explicitly report any post-band ceiling overshoots; this is not a broker execution/margin feasibility simulator. No market impact, partial fills, forced liquidations or intraday margin calls are modeled.

## Metrics and decision rules

Report full/OOS/IS returns, SOXX excess, log-return Sharpe, volatility, maximum drawdown (including starting equity, plus repository convention for parity), repository score, turnover/day, gross mean/quantiles/max, positive cash, borrowing, days below 20%/50% gross, days above 100%/150%/180%, low-baseline-exposure-day comparisons, and last simulated exposures. Distinguish historical exposure from today's live holdings.

The minimum existing repository screen is: recent OOS Sharpe improves, recent full Sharpe does not fall, and recent score does not fall, with identical costs/financing. A supported material improvement additionally follows the prior experiment's noise/risk screen: full and OOS Sharpe improve by >0.15, full drawdown is at most 2 percentage points worse, cumulative return is at least 80% of positive baseline return, and stress return/Sharpe are not worse. Report both screens rather than silently weakening them for leverage. No candidate becomes a supported winner solely because it invests more.

Report paired 40/80-day circular-block diagnostic intervals (2,000 draws, fixed seed 20260912), historical-trial-aware deflated-Sharpe diagnostics, best-quarter concentration and round PBO. These are exploratory diagnostics, not significance or fresh holdout evidence. Do not optimize any variant after the results. If no variant passes, explicitly reject deployment as an evidence-based upgrade and describe which setting, if any, would mechanically increase low exposure.
