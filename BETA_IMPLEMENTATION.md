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

- `config.py`: `LEARNER_TARGET_MODE = "beta"`, `VOL_TARGET = 0.50`; active for the scheduled paper cycle.
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

The code was integrated in the operational feature branch by merge `386ca33`, and its 15 tests passed there too.
Automatic review initially required specific authorization for the operational database migration; the user
explicitly approved it, including both backups and additive beta columns. The migration then completed at 14:52 PT.
Full operational-data preservation, SQLite integrity, exact raw/beta array parity and candidate refits all passed.
The beta candidate was promoted to `state/model.json`, raw to `state/model_raw_shadow.json`, and effective weights
were saved at 14:54 PT. PAPER=True and VOL_TARGET=0.50. No trading cycle, order, liquidation, schedule change or LLM
call was executed during activation. The existing next weekday cycle will generate fresh opinions and refit both
models before using beta for its paper orders. Current holdings were not rebalanced by this maintenance step.

Operational backups (all under `C:/Users/calif/Desktop/Trading/state/`):

- `backtest.sqlite.pre-beta-20260912-145223-511235.bak` (95,694,848 bytes; original warm start).
- `ledger.sqlite.pre-beta-20260912-145246-945071.bak` (417,792 bytes; original paper predictions/orders).
- `model.json.pre-beta-20260912-145454.bak` (original raw model).

Verification: `state/beta_activation_verification.json`. Original historical scores are preserved in `abnormal`;
577,944 exact researched beta targets are stored in the parallel column. Live predictions have 2,036 frozen betas;
there are still no matured live scores. Some unscored historical predictions have NULL beta because no target
exists from which to infer it; they never enter a fitted dataset. Future historical rebuilds compute beta directly.

The user subsequently requested higher-exposure/leverage testing, then explicitly chose to KEEP the existing
signal-sized/cash-holding structure and requested final documentation/push. Activation retains gross1.50, size0.60
and existing entry rules. No extra exposure change is authorized by the final decision. Do not claim the account has been made fully invested
or increased to 200% exposure. At the read-only check, equity was $1,006,860.73, cash $930,739.31, SHEL market value
$76,121.42, buying power $3,936,097.22. Low investment reflected signal-based sizing, not lack of borrowing capacity.

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
SemiBand UI is live at https://semiband-dashboard.vercel.app. Its UI/benchmark commits are `856990e`, `2791b5a`
and `a3e0d73`; the final promoted deployment is `dpl_ETfNTumhmi5znpGufWdzw1KJDAds`. Seven benchmark regression tests,
production build and live desktop/mobile browser checks passed, with no console errors on the final reload.
The old snapshot contained only the comparison-baseline price for SOXX/SPY: it falsely displayed missing returns
as 0%. The repair fetches actual free delayed Alpaca SIP daily bars server-side with existing environment credentials
and five-minute caching; no credential file or environment edits were needed. September 10, 2026 OPEN is the fixed
baseline, followed by daily closes: SOXX $518.32→$527.07 (+1.69%), SPY $758.03→$764.29 (+0.83%), QQQ $707.55→$714.88
(+1.04%) through September 11. Portfolio +0.69% is explicitly labeled as using the previous account-close opening
proxy because exact opening account equity is unavailable. No invented opening-equity value is presented as actual.
Deployment used a staged web-only upload, excluding the root credentials and unrelated Claude worktrees.
The source HANDOFF records UI behavior, approvals, deployment verification and rollback in detail.
