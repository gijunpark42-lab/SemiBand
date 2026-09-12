# Beta-adjusted paper learner — Claude handoff

## Decision and authorization

On 2026-09-12 the user chose beta-adjusted learning with the existing 0.50 volatility target over the report's
initial 0.40 shadow recommendation, and explicitly authorized its use in the active paper account after validation.
The user also authorized two Astra xhigh agents to improve and deploy the SemiBand and Earnings AI websites and
asked that all implementation, validation, deployment and rollback details be recorded for Claude.

This document supersedes the earlier offline-only/raw-default recommendation. PAPER remains True. The change is
one learning-target choice, not discretionary manual agent-weight tuning. Weights are refitted from data.

## Evidence behind 0.50

The pre-registered round-24 beta/0.50 result was +775.83% total return, Sharpe 2.02, max drawdown 32.62%,
OOS return +296.79%, OOS Sharpe 2.21, turnover 35.9%/day and score 5.050. Raw/0.50 produced +631.61%,
1.67, 27.84%, +210.51%, 1.89, 39.3%/day and score 3.962 respectively.
In the 2019–2023 stress window beta/0.50 produced +17.15%, Sharpe 0.14, drawdown 36.98%; raw/0.50 was
−18.29%, −0.17, 40.59%. Beta/0.40 was the lower-risk alternative: +631.13%, Sharpe 2.05, drawdown 28.74%.
The 0.03 Sharpe difference between beta/0.40 and beta/0.50 is not strong evidence to prefer the lower target.

These are reused historical windows, not new forward evidence. The paired-bootstrap intervals reported for the
0.40 candidate cross zero; they must not be represented as significance evidence for 0.50. Graph history and
survivorship limitations still apply. The simulator omits financing, impact, partial fills and account-startup
volatility behavior. Actual portfolio vol targeting waits for 20 account-return days, as before.

## Implementation

- `config.py`: `LEARNER_TARGET_MODE = "beta"`, `VOL_TARGET = 0.50`.
- `learning_targets.py`: shared rolling 60-session beta to SOXX, minimum 40 return observations, clip [0,3],
  fallback 1 for unavailable estimates. Benchmark sessions only; no implicit filling of missing price returns.
  New pre-open predictions capture the beta available strictly before the prediction date.
- `ledger.py`: additive `predictions.benchmark_beta` and `scores.beta_abnormal`; original raw labels and hits remain.
  SQLite contexts close their connections. `shadow_targets` stores date, target mode, conviction, proposed dollars,
  reference price, volatility setting and whether the model was active.
- `score.py`: newly matured rows save both raw and beta returns using the stored beta. Pre-open scoring excludes
  today's close and requires an exact prediction date in the price cache; old missing dates cannot be shifted to
  the start of a newer cache. Scores retain their actual availability date.
- `learner.py`: explicit raw/beta target selection, target-specific caches and model identity. Missing beta labels
  abort fitting; complete models are written atomically. The prior research fixes for exact score maturity,
  fold-local CV scaling/source weights and isolated tagged replays are included.
- `cycle.py`: active beta model drives the normal scheduled paper cycle. Raw is also fit and its proposed
  allocations recorded against the same opinions, equity, volatility and guardian restrictions. Both modes are
  recorded in the next dashboard/history payload. No second set of orders is sent for the shadow.
- `backtest.py`, `llm_backtest.py`, `make_beta_ledger.py`: parallel historical labels use the shared beta calculator.
  `sweep.py`/`timing.py` preserve legacy raw-label replays; sweeps accept explicit `--target-mode beta`.
- `migrate_beta_targets.py`: SQLite backups, transactional additive migration, exact prediction/score identity
  validation when importing a researched ledger. Original score columns are preserved. Historical stored betas
  inferred from imported targets are validated across horizons; unscored historical rows may retain NULL.
- `verify_beta_activation.py`: full original-table preservation/integrity checks, exact learner input equality
  against raw and beta research ledgers, then independent beta/raw candidate-model files. No broker or LLM calls.

The raw shadow is not a complete independent backtest: agent selection for costly opinions follows the active
model, and sizing uses the active account's history. Use its logged allocations for controlled forward comparison,
not as a claimed realized shadow P&L series.

## Validation and activation status

Fifteen regression tests passed, including live two-horizon scoring with a frozen beta, pre-open causality,
no score-date shifting, migration preservation/idempotence, incomplete-target rejection before model replacement,
and wrong-target model rejection on rollback. Original five causal-replay checks also remain in the suite.

Full-data rehearsal passed on `state/activation_validation/`: 577,944 historical scores imported exactly; 2,036
current paper predictions backfilled, with zero matured live scores. All original predictions, scores, orders,
cycles and weights matched their references. All raw/beta learner arrays matched the research sources exactly.
Each model uses 72,930 date/ticker observations per horizon across 500 dates. Latest CV IC is negative for both
models (beta −0.073/−0.045; raw −0.021/−0.009); historical superiority is not a claim of a currently positive IC.

Operational installation and model promotion are pending at this commit. The final activation entry below will
record actual checks and backups; do not mistake this code-ready checkpoint for completed activation.

## Rollback

Set `LEARNER_TARGET_MODE = "raw"` and refit raw into `state/model.json` using the migrated original raw labels.
The next cycle also refits automatically. Retain the additive beta columns and all newly collected observations;
do not restore an old ledger over new paper observations. A mismatched model file is rejected by `learner.load`.
Pre-migration database/model backups exist for forensic recovery, not routine model selection.

## Research artifacts

The complete report, pre-registration, original Claude handoff and checkpoint are in
`C:/Users/calif/Documents/Codex/2026-09-12/semiband-research/outputs/`.
Research checkout: `.../work/semiband-experiment`, branch `codex/external-regime-gate`.
Raw reference: `state/backtest_research_good.sqlite`, SHA256
`57D89DE04BD012AD5240175B6A7DC91C5B8F6722BFCC38E76D83E65A87225B85`.
Beta reference: `state/backtest_research_good_beta.sqlite`, SHA256
`EB2FB559CE352B56EFC29FFE803D840BFE14886FDD6A2366903D2B678AEB6E70`.

## Related website work

Earnings AI was deployed to https://gijun42.com with UI commit `a26a812` and handoff completion commit `f041fe0`.
Its own `docs/HANDOFF.md` and web-state memory record all changes and live desktop/mobile verification.
SemiBand UI initial commit is `856990e`; its agent is also repairing the SOXX/SPY 0% benchmark problem.
The published benchmark snapshot had only the comparison-baseline price for those symbols. Intraday daily-cache
reuse can leave existing SOXX/SPY columns ending earlier than later-fetched QQQ. User explicitly requested filling
the missing price data; see the UI agent's final HANDOFF entry for the actual repair and release verification.
