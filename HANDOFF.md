# HANDOFF — state of SemiBand and the baton protocol between agents

Written by Claude (Fable 5.1) on 2026-09-12, at commit `fe7b998` on `main`. Purpose: any agent (Codex, Claude, a human)
can read this file, know exactly where the project stands, continue, and hand back. Sections 1–5 describe the state as
of the date above and are rewritten only by the agent that changes the state. Section 6 is append-only.

**Current-state override, 2026-09-12 afternoon:** the baseline narrative in sections 1–5 below is the original
morning snapshot, not the active setting. Beta-adjusted learning with VOL_TARGET=0.50 is now active for the next
scheduled PAPER cycle; raw labels/model, ledger backups and verification are preserved. Both website UI releases
and SemiBand's September 10 opening-price benchmark repair are deployed and verified. Read `BETA_IMPLEMENTATION.md`
and the newest session-log entries first. The user explicitly approved publishing the full source and operational
handoff to this PUBLIC GitHub repository, and `42c30af` was pushed on `codex/semiband-ui-clarity`; main is unchanged.
The user subsequently chose to KEEP the signal-sized cash-holding structure: gross1.50 and size0.60 have not been
increased. Higher-exposure research is being finalized/checkpointed only, with no further active-setting change.

## 1. What this is, in five lines

SemiBand v2.3: eleven agents (8 rule agents, 3 Claude agents) each give a direction × confidence opinion on every stock in
a 150-name AI supply-chain universe (from the earnings-ai graph). A Bayesian ridge learner (`learner.py`) blends them into a
conviction per name; `portfolio.py` turns that into a top-15 long-only book (entry 0.10, 15% cap, 150% gross ceiling, vol
target 0.50); `broker.py` trades it in an Alpaca **paper** account at the 09:30 ET open. Every opinion is scored at 10 and
20 trading days against SOXX and the weights are refit daily. `README.md` has the full mechanics and every command.

## 2. Where things stand (2026-09-12)

**Live**
- The daily cycle (`SemiBand-Cycle`, 03:30 PT weekdays) has run once on v2.3 / 150 names: 2026-09-11. It closed all 15
  legacy positions and bought only SHEL (7.5%) → 92% cash. That is the strategy's cash regime since the August drawdown
  (the backtest's last day held one name too), not a bug. Round 17 tested exposure floors / lower entry bars / semis-only
  universes: none better. Log: `state/run_daily.log`. Dashboard: https://semiband-dashboard.vercel.app.
- Live Claude agents (`llm_supply`, `llm_guidance`, `llm_news`) run on `claude-opus-5` at HIGH effort via the local server
  for the top 100 names (~300 calls, ~40 min). Guardian (news-driven exits only) hourly during the session.
- Warm start: `state/backtest.sqlite` was replaced on 2026-09-11 15:17 with the round-22 `_nbfix` ledger (neighbors rows
  now start 2025-10-03, 14,490 rows; the old ledger with the fake constant rows is `state/backtest_prenbfix.sqlite`).
  Verified 2026-09-12. The live learner tilts to `technical` (0.26 vs prior 0.09 at 10d); that is earned (470 days of
  positive IC) and will fade only as live scored days accumulate (~60–90 days).

**Research (22 rounds, all in `RESEARCH.md`)**
- v2.3 is a plateau: horizons (10, 20), λ 150, half-life 90, entry 0.10, size 0.60, cap 0.15, top 15, band 0.30, vol
  target 0.50. Honest numbers (500 days, next-open, daily refits, tiered costs): about +690% / Sharpe 1.7 / max DD 28% /
  OOS Sharpe ~1.9 / turnover 40% a day. Noise band ±20% return / ±0.15 Sharpe. Nothing in rounds 12–22 beat it.
- Rejected, do not re-test: price stop-losses, shorts, SOXX hedge as alpha (kept as optional overlay `broker.hedge_to`,
  OFF), non-negative learner weights, inverse-vol sizing, drawdown brakes, exit hysteresis, min hold, IC blends, bagging,
  IC gates, self-monitoring exposure gates, 5-day horizon, 40-day horizon, slower rebalance, top 10/20, market-cap cap,
  CPI-day hold, momentum/SUE/ML-ranker agents (kept in `agents/`, disabled).
- **The most important finding:** the whole 2024-26 edge is the price stack (`technical`, `mean_reversion`, `risk`,
  `macro`, `events`). The same stack lost money 2019-04 → 2023-11 (−17%, Sharpe −0.14, negative IC). v2.3 is a
  relative-momentum machine on the AI supply chain with a proven edge in one regime only.
- **Data caveat:** the earnings-ai graph's dated statements start 2025-10 (85% from 2026-04). The OOS year is graph-blind,
  so backtest verdicts on `supply_chain` / `neighbors` / `llm_guidance` rest on 2026-02 → 08 only. Their real test is
  the live scoreboard. `llm_guidance` is the only Claude agent with a measured positive contribution (round 15).

**Open ideas (from RESEARCH.md "what would actually be new")**
1. Regime identification from outside the strategy (breadth, credit, semi-cycle indicators) as an on/off switch — testable
   on 2019-26 with the price-agent ledgers already built (`backtest.py --days 1200 --end 2023-12-29 --agents technical,mean_reversion,risk,macro,events`).
2. A 60-day scoring horizon for the slow (graph / filings) information; dated counterparty relations from 10-K rows once
   graph snapshots accumulate (`state/graph_snapshots/`, daily since 2026-09-11).
3. Beta-adjusted learning target (`make_beta_ledger.py`: Sharpe 1.94 / OOS 2.01 but DD 38.7%) combined with a drawdown control.
4. Backfilling 2024-25 transcripts in earnings-ai would make the OOS year graph-covered — **earnings-ai work, the user's call only**.

## 3. How to test anything (the short version of RESEARCH.md's protocol)

```
set PYTHONUTF8=1
python backtest.py --days 500 --exec open --tag _mytag            # ~6 min, 150 names; writes state/backtest_mytag.sqlite + state/backtest_report_mytag.json
python sweep.py --workers 10 --search 3 --pop 10 --exec open --oos-end 2025-09-24 --tag _mytag   # generational search, ~12 min/gen
python sweep.py --round10 --tag _open500 --exec open --oos-end 2025-09-24                        # a fixed variant list
python cycle.py --dry-run --no-llm                                 # free agents only, no orders, no Claude
```

- Judge on: full-window Sharpe, OOS Sharpe (first 250 of 470 days), max DD, turnover, and the `robustness` block
  (bootstrap CI, deflated Sharpe, best-quarter share, cost sensitivity). Compare against the round-22 `_nbfix` numbers above.
- Results depend on the ledger (the graph changes daily); to compare two variants, replay the same ledger tag.
- Add `--no-publish` for scratch runs so nothing is uploaded to Vercel Blob. Local live view: `watch_backtest.cmd`.
- Every trial, adopted or not, gets a row in `RESEARCH.md` in the existing table format, with the verdict.

## 4. Repo map and loose ends

- Branches: `main` = `fe7b998`. All `worktree-*` branches are merged except `worktree-round14` (an older variant of round
  14, superseded; safe to ignore). `.claude/worktrees/*` are Claude Code worktrees — leave them alone.
- Untracked junk at the repo root: two empty files named `Claude` and `이` (0 bytes, created 2026-09-11 19:07, probably a
  shell accident). Not deleted; the user decides.
- `web/next-env.d.ts` shows as modified — that is `next dev` rewriting it; ignore or `git checkout -- web/next-env.d.ts`.
- `graphify-out/` is a knowledge graph of the codebase (`.graphifyignore` excludes worktrees and state); refresh with
  `graphify update .` after larger code changes if you use it.
- `API_KEYS_TODO.md`: keys that are still missing for some data sources.
- Trading reads the root `company_metrics.json` of earnings-ai (stale, 172 rows) rather than `graph/company_metrics.json`
  (256 rows). Known, not yet changed; if you switch it, add the file to `snapshots.py` FILES first (point-in-time).

## 5. What NOT to do (the ones that have bitten)

- Do not tune on the 220-day window (2025-09-24 → 2026-08-10) alone: 163 variants were, and OOS Sharpe was 0.9 vs 2.3 IS.
- Do not use weekly refits in the backtest: results then depend on the refit phase (one dropped day moved OOS Sharpe 0.92 → 0.80).
- Do not read the sweep's signed gross sum as a cap (round-18 bug, fixed): hedges must not unlock long leverage.
- Do not cite the OOS year for or against the graph / LLM agents (they were silent there).
- Do not run the live LLM agents from a non-Claude environment; do not point research at `LLM_MODEL`.
- Do not commit `state/`, do not touch earnings-ai, do not push to `main`.

## 6. Baton protocol and session log

**When you (any agent) stop working**, append an entry below, newest last:

```
### YYYY-MM-DD HH:MM PT — <agent name> → <next agent or "anyone">
- Did: <what changed, with file names and commit hashes / branch>
- Results: <numbers that matter, or "no experiments">
- Unfinished / in flight: <background runs still going, half-done edits, things to verify>
- Next: <the concrete next step you would take>
```

Experiments also go into `RESEARCH.md` (that is the permanent record; this log is the pointer). Do not rewrite older
entries. If you changed sections 1–5, say so in your entry.

**When you (any agent) start**, read: this section (newest entry), `git log --oneline fe7b998..HEAD` on every branch
touched since, `git status`, the tail of `RESEARCH.md`, and `state/run_daily.log` for what the live cycle did.

### 2026-09-12 — Claude (Fable 5.1) → Codex
- Did: wrote `AGENTS.md` (rules Codex reads automatically) and this `HANDOFF.md`, branch `worktree-handoff-codex`.
  No strategy or code change. Verified the warm-start ledger swap (section 2) against both sqlite files.
- Results: no experiments this session. Last research state = round 22 (`fe7b998`).
- Unfinished / in flight: nothing running. The first live cycle after the ledger swap is the next weekday 03:30 PT run;
  check `state/run_daily.log` and the dashboard weights after it.
- Next (my recommendation): open idea 1 — an external regime switch, tested on both the 2019-23 price-agent ledger and
  the 2024-26 `_nbfix` ledger, adopted only if it protects 2019-23 without cutting 2024-26 beyond the noise band.
  Codex: log what you do here, then the user says "read HANDOFF.md" to Claude and the baton comes back.

### 2026-09-12 07:04 PT — Codex → Claude / anyone
- Did: research only in isolated checkout `C:\Users\calif\Documents\Codex\2026-09-12\semiband-research\work\semiband-experiment`, branch `codex/external-regime-gate`, commit `c4e8b39`; live source/config/state unchanged. Corrected tagged-replay warm-start contamination, exact score maturity, and fold-local scaling/source weights in the isolated code. Full report: `C:\Users\calif\Documents\Codex\2026-09-12\semiband-research\outputs\result_report.md`; resume guide: `CLAUDE_HANDOFF.md` beside it.
- Results: external 2-of-3 regime gate rejected. Exploratory beta-adjusted target + vol target 0.40: 2024-26 +631% / Sharpe 2.05 / DD 28.7% / OOS Sharpe 2.27 versus raw baseline +632% / 1.67 / 27.8% / 1.89; 2019-23 +13.9% / 0.12 / 36.4% versus −18.3% / −0.17 / 40.6%. Five focused tests pass. Block intervals cross zero, so candidate is not proven.
- Unfinished / in flight: nothing running. Candidate is offline-only; do not copy its ledger into live state because live scores still use the raw target.
- Next: if the user resumes, implement an explicit target mode and consistent point-in-time beta target for both warm-start and ongoing live scores, keep raw as default, then shadow-test 60–90 newly scored paper days. Do not change live defaults merely from this reused-window result.

### 2026-09-12 15:05 PT — Codex (Astra, xhigh) → Claude / anyone
- Did: the user subsequently explicitly authorized the beta-target implementation, operational migration, and activation at vol target 0.50. This supersedes the previous entry's offline-only / raw-default recommendation. Root agent's authoritative implementation, evidence, and rollback record is tracked `BETA_IMPLEMENTATION.md` (activation commit `fa698c2`, integrated at `463fdeb`). Research rounds 23–25 and the read-only exposure diagnostic were integrated by `1ccbee5` / `5439b0c`. Branch remains `codex/semiband-ui-clarity`; nothing was merged or pushed to main. Sections 1–5 above remain a dated historical snapshot; read this log and the tracked implementation report for current state.
- Results (root agent verification): both operational databases were backed up and migrated after explicit user approval. Added 577,944 exact historical beta labels and 2,036 frozen pre-open live prediction betas; zero live matured scores existed. Original tables/data were preserved, integrity checks passed, and both raw/beta learner arrays exactly matched the research references. Fifteen tests pass. `model.json` is the beta model, `model_raw_shadow.json` is the raw model, and ledger effective weights match. The next scheduled weekday PAPER cycle uses `LEARNER_TARGET_MODE=beta`, `VOL_TARGET=0.50`; `PAPER=True`, gross ceiling 1.50 and size 0.60 remain unchanged. Current holdings were not altered. No cycle, order, liquidation, schedule change, or Claude/LLM call was made for activation.
- Backups / rollback: root backups are `state/backtest.sqlite.pre-beta-20260912-145223-511235.bak`, `state/ledger.sqlite.pre-beta-20260912-145246-945071.bak`, and `state/model.json.pre-beta-20260912-145454.bak`; verification is `state/beta_activation_verification.json`. For a target rollback, set `LEARNER_TARGET_MODE=raw` and refit the raw model into `state/model.json` from preserved raw labels, following `BETA_IMPLEMENTATION.md`. Preserve additive beta columns and new observations. Do not restore an old ledger over subsequent live observations. Model loading rejects a model trained for the wrong target mode.
- Unfinished / in flight: no strategy changes from the UI agent. Higher-exposure research is separate and not applied. The root's illustrative replay of Friday's saved signals yielded beta targets 27.67% across four names versus raw 7.90%; gross 2.0 alone did not increase this, and size 0.80 gave beta 36.90%. These are diagnostic target calculations, not newly generated signals or placed trades. Research evidence is not proof of future performance.
- Next: Claude should read `BETA_IMPLEMENTATION.md`, the latest `RESEARCH.md` entries, and this log before changing anything. After the next scheduled paper cycle, verify the beta target/model mode and raw-shadow diagnostics in the normal logs without running an extra order-producing cycle.

### 2026-09-12 15:05 PT — Codex (Astra, xhigh), SemiBand UI → Claude / anyone
- Did: implemented and committed focused website work, preserving trading code/state and original untracked files. UI commit `856990e` adds shared `web/components/SiteHeader.tsx`, searchable/expandable `web/components/Convictions.tsx`, accessible section navigation, overview/error states, responsive cards/tables, reduced-motion/focus styling, metadata/skip link, and a responsive keyboard-accessible equity chart. Existing published rank order is preserved; the current payload has 60 published symbols, not the full 150-name research universe. Files also include `web/app/page.tsx`, `web/app/backtest/page.tsx`, `web/app/layout.tsx`, `web/app/globals.css`, and `web/components/EquityChart.tsx`.
- Benchmark cause and fix: the published dashboard snapshot had SOXX/SPY ending Sep 10 while QQQ reached a partial Sep 11 price, and the old view treated a sole baseline close as a current 0% return. Root confirmed the Python market cache can retain already-cached symbols throughout the calendar day while later-added symbols get fresher dates. No Python cache, strategy, graph, or state files were changed by this fix. Commit `2791b5a` adds server-only `web/lib/benchmarks.ts`, pure/tested `web/lib/performance.ts`, and `web/tests/performance.test.mjs`; it updates Performance, server page wiring, styles, and the npm test script. Commit `a3e0d73` makes equity chart dates explicitly New York time to avoid server/browser hydration disagreement.
- User-confirmed convention: ETF baseline is the SEPTEMBER 10, 2026 regular-session opening price, not that day's close. Later observations use completed daily closing prices. SOXX/SPY/QQQ use the same baseline and a common latest session. Portfolio performance is separately and visibly labeled as using Sep 9 account close as an opening-equity proxy; no exact opening account snapshot is fabricated. Missing opens, missing history, and stale/alignment cases are explicit, never silently converted to zero. A truly flat valid series still shows zero.
- Data source / secrets: existing production Alpaca credentials already worked; no secret value was logged, copied into the client, or changed in Vercel. The server uses Alpaca historical stock bars with `feed=sip`, `adjustment=split`, and an end at least 20 minutes old, satisfying the free historical SIP delay. Cache is five minutes. Today's daily bar is used only after 16:20 New York time, conservatively excluding unfinished closes. Source, freshness, opening prices, and baseline are visible. An API failure produces explicit unavailable data rather than falling back to a fabricated opening price. The API helper/credential header strings were absent from built client static assets. Official references: https://docs.alpaca.markets/us/reference/stockbars and https://docs.alpaca.markets/us/docs/market-data-faq.
- Results: live Sep 10 OPEN → Sep 11 CLOSE is SOXX 518.32 → 527.07 = +1.69%; SPY 758.03 → 764.29 = +0.83%; QQQ 707.55 → 714.88 = +1.04%. Portfolio proxy 1,000,000 → 1,006,860.73 = +0.69%. All seven web regression tests pass and the Next production build/type check passes. Tests cover open 100 → latest 105 = 5%, actual API fixtures, unavailable opening baselines, stale common-end alignment, New York/DST session dates, unfinished daily bars, and real flat returns. These are display/data tests, not new strategy experiments.
- Deployment: user explicitly approved the isolated web upload to existing Vercel project `semiband` and the public destination. Final READY deployment `dpl_ETfNTumhmi5znpGufWdzw1KJDAds` at https://semiband-qnohzcfsr-gijun42.vercel.app was promoted to https://semiband-dashboard.vercel.app and verified there. Production visibly shows the returns above. Final fresh browser reload had no console errors. Dashboard/backtest links, published-symbol search and no-match reset, allocation filter, ranking expansion to all 60 published symbols, agent details, pointer and keyboard charts, and desktop/mobile layout were checked. At 390px viewport the page had no horizontal document overflow; chart labels remained readable. Screenshots were inspected in the browser session, not saved as repository artifacts.
- Deployment safety / reproduction: do NOT deploy directly from the Desktop repository root with its present ignore file. A read-only dry run found it would include root `.env` and many locked `.claude/worktrees` sources; that unsafe upload was never performed. The authorized production upload instead used 22 explicitly selected web source/config files, no secrets/state/trading files, from `C:/Users/calif/Documents/Codex/2026-09-12/semiband-research/work/semiband-ui-deploy-20260912`, with existing `.vercel/project.json` metadata. Workflow: `vercel deploy --prod --skip-domain --yes`, inspect the READY build and authorized staged response, then `vercel promote <deployment-url> --yes`. Staging deliberately excluded tests and all unrelated root changes. Vercel CLI generated its standard deployment-protection bypass token for authenticated staged inspection; no token value was exposed. Existing build warning about broad local-file tracing in `web/lib/alpaca.ts` remains, but the isolated upload contained no strategy/state/credential files.
- Rollback / local caveats: the immediately preceding benchmark-capable production build is https://semiband-2o2jrhsv9-gijun42.vercel.app (`dpl_HJunfpwYm8MopyuWcYxK66C7S6bg`); it predates only the equity chart timezone fix. The UI-only release https://semiband-66dqrzo3f-gijun42.vercel.app (`dpl_CQNLQoCccVv5duu8xXEMTiBXUhiT`) predates the benchmark fix and would restore that known zero-return problem. Use Vercel promote only with an intended rollback authorization. The local `web/.env.local` Alpaca keys returned 401, whereas existing root process credentials and production credentials worked; no environment file was edited. Local validation loaded working credentials into the server process only and did not print them. All temporary Next preview servers were stopped.
- Unfinished / next: no unfinished web edits or deployments. The original root `HANDOFF.md` and agent instruction files were already untracked; this log was appended without deleting/replacing those original documents. The feature branch is ready for the user/root's normal review and push, never a main merge. Benchmark baseline is intentionally fixed to the user-confirmed Sep 10 opening; future date-convention changes need explicit product intent. Do not mistake subsequent closing-price changes for trading decisions.

### 2026-09-12 afternoon — Codex root → Claude / anyone: final user decision and public publication
- Did: verified the configured SemiBand GitHub repository is PUBLIC and the authenticated user has ADMIN access.
  Automatic review initially blocked exporting account figures/operational handoff. After that exact risk was
  explained, the user explicitly approved publishing the full current code and records. Pushed feature branch
  `codex/semiband-ui-clarity` through `42c30af`; remote/local equality verified. Main was not changed. The complete
  original HANDOFF history is now tracked, preserving all prior entries. Added the current-state override above
  sections1–5 so the old morning snapshot cannot be mistaken for active raw settings.
- Final decision: the user explicitly chose to keep the signal-sized/cash-holding structure after discussing low
  deployment. Active PAPER beta0.50 remains; gross1.50, size0.60, entry0.10, cap0.15, top15 and band0.30 stay unchanged.
  No forced 200% deployment or exposure floor was applied. Current models rechecked: beta active and raw shadow
  both load, with matching target identities. Fifteen regression tests passed again. No orders/cycle/LLM/schedule
  changes were run. Existing unrelated untracked instruction files and empty files were preserved.
- Records: dated user-facing summary is `C:/Users/calif/Documents/Codex/2026-09-12/semiband-research/outputs/FINAL_HANDOFF.md`;
  detailed implementation/rollback is `implementation_report.md` beside it. Both website deployments and benchmark
  returns remain verified as in the preceding entry. Higher-exposure research is being finalized below, not deployed.
- Next: keep this final user decision; inspect normal next-cycle beta/raw-shadow logs when that scheduled cycle
  occurs. Do not start an extra order-producing cycle or resume parameter tuning without a new request.

### 2026-09-12 afternoon — Codex root → Claude / anyone: subsequent logo request
- Did: user subsequently requested a new logo for the Earnings AI website branded "AI Supply Chain". Created a
  blue connected-node A and exact wordmark with the built-in image tool, matching the site's existing dark/blue
  palette. Refined a rough transparent draft into an opaque dark-background concept; no website code/deployment
  was changed and no existing asset was replaced.
- Local deliverable: `C:/Users/calif/Documents/Codex/2026-09-12/semiband-research/outputs/logo/ai-supply-chain-logo-dark-v1.png`
  (2172×724 PNG), with the final prompt/tool/provenance in `outputs/logo/README.md` beside it. The user can inspect
  the generated image in the Codex conversation; originals remain in the generated-images folder.
- Next: this is a logo concept, not a deployed transparent/vector production asset. Any favicon, vector treatment
  or website integration is follow-up work, not something already completed.

### 2026-09-13 23:10 PT — Claude root → anyone: Codex beta model confirmed, branch merged into main, research published
- Did: resumed after Codex. Checked the scheduler: the last cycle was Fri 2026-09-11 (Sat/Sun have no trigger),
  `SemiBand-Cycle` and `SemiBand-Guardian` are Ready, next runs Mon 2026-09-14 03:30 / 07:35 PT. The user confirmed
  (2026-09-13): use what Codex wrote, its verification is complete — so the beta-adjusted learner
  (`LEARNER_TARGET_MODE=beta`, VOL_TARGET 0.50, raw shadow kept) stays the active paper model; nothing else was changed.
  Ran Codex's suite in an isolated worktree: 15/15 pass. Merged `codex/semiband-ui-clarity` (fast-forward from
  `fe7b998`) plus the clone's two research-record commits (`40756b5`, `284e76f`: higher-exposure verdict + scripts)
  and committed the logo entry Codex had left uncommitted (`741f5f4`). Uploaded the merged `RESEARCH.md` to the Blob
  (`semiband-v2/research.md`) so the site's Decisions section carries rounds 23–25, the beta activation and the
  higher-exposure record. No cycle, order, LLM call or schedule change was run.
- State: the live checkout `C:/Users/calif/Desktop/Trading` is still on `codex/semiband-ui-clarity` (`3d702d4`) with an
  uncommitted `HANDOFF.md` change identical to `741f5f4`. Its trading code equals main after this merge (only docs and
  research scripts differ). To move it to main: `git checkout -- HANDOFF.md && git checkout main && git pull`.
- Next: after Monday's 03:30 PT cycle, verify in `state/run_daily.log` and the dashboard payload that the active model
  is beta and the raw-shadow allocations were recorded; do not start an extra order-producing cycle. Open question the
  user raised 2026-09-13: feed `llm_guidance` earnings-call statements only (10-K/8-K rows crowd the 12-row window in
  127/149 universe names and push out 504 call statements); decision pending, no code change yet.
- Incident (2026-09-13 23:05–23:40 PT): pushing main triggered a Vercel git deployment; at the same time the newly
  uploaded RESEARCH.md contained one `### ` heading, which the /backtest markdown renderer could not consume — its
  paragraph loop never advanced, the function ran out of heap (runtime logs: "JavaScript heap out of memory") and,
  because one Fluid instance serves every route, the dashboard root returned 500 too. Fixed in three steps: rolled
  production back to Codex's verified deployment `dpl_ETfNTumhmi5znpGufWdzw1KJDAds`; re-uploaded the log with that
  heading demoted (site back at 23:35); committed a renderer fix (`6811d7d`: any heading level renders, every branch
  advances, separator-only tables skipped) and pushed it to main so the next git deployment carries it. Note: every
  push to GitHub `main` now auto-deploys production (`semiband-git-main-gijun42.vercel.app` alias) — the project's
  Production env already holds TRADES_URL, BLOB_READ_WRITE_TOKEN, BLOB_STORE_ID and the Alpaca keys, so git deploys
  do not need the local `.env.local`.

### 2026-09-14 00:05 PT — Claude root → anyone: transcripts-only inputs, every name, Opus xhigh (user decision, for Monday)

- Did: user decision 2026-09-13 (no backtest first, token budget): `llm_guidance` / `llm_supply` now read only earnings-call
  and conference statement rows (SEC filing and note rows dropped via `agents.base.NOT_TRANSCRIPT`), every universe name
  gets the Claude agents (`LLM_MAX_TICKERS = None`), live Opus effort `xhigh` handed to the local server when the cycle
  starts it (`LLM_EFFORT`; `LLM_WORKERS` 2 → 3 doubles as the server's slot count). Numbers and rationale: RESEARCH.md
  "2026-09-13 — operational decision". Tests: `test_llm_inputs.py` (4) + Codex suite (15) pass. One measured xhigh call
  (NVDA guidance: 41 s, 5.5k in / 3.1k out) through a server started with the new env; that server was stopped again so
  the cycle starts its own. Merged to main and pushed (this commit).
- State: the live checkout `C:/Users/calif/Desktop/Trading` is now on `main` (`2136b89`, fast-forwarded from the Codex
  branch after discarding its uncommitted HANDOFF.md copy of `741f5f4`); its config loads effort xhigh, 3 workers, no
  ticker cap, target mode beta, vol 0.50, PAPER. Local Claude server: down (the cycle starts it with the new env).
  Schedule unchanged: `SemiBand-Cycle` next run Monday 2026-09-14 03:30 PT.
- Next: after the Monday 2026-09-14 03:30 PT cycle check `state/llm_server.log` for `opus/xhigh` lines and ~450 calls
  finishing before 06:30 PT, and `state/run_daily.log` for target mode beta plus the raw-shadow rows. If calls error out
  mid-cycle (subscription window), set `LLM_EFFORT = "high"`. Conference fireside chats are not in the graph rows yet.

### 2026-09-14 07:00 PT — Claude root → anyone: Monday cycle reused Claude signals and refreshed price agents at the open; SHEL closed, book in cash; dashboard live marks

- Did (overnight, dashboard): `a9cf266` live mark for account equity and the benchmark comparison (latest trade in any session,
  recorded daily closes unchanged); `0c6ea50` comparison tiles follow the selected date; `1be7f4b` risk table (Sharpe with
  standard error, volatility, max drawdown, beta and information ratio vs SOXX; same formulas as backtest.py; follows the date
  slider; small-sample notice under 20 daily returns). Each verified against numbers computed from Alpaca, locally and in production.
- Did (morning): the scheduled cycle started 03:43 PT because the PC was off at 03:30; 448 Opus xhigh calls on 3 slots finished
  04:43 with no failures. The user asked for the price at order time, so `cad125d` and `fafe3d9` add the open refresh and signal
  reuse. Rehearsed on a state copy, then stopped the waiting run at 04:50 before any order and relaunched it with
  `state/reuse_signals`. At 06:30:14 the refresh ran on 151 live prices with SOXX −5.5%; 0 targets; SHEL sold at $97.14.
  Numbers and caveats: RESEARCH.md "2026-09-14 — operational decision".
- State: live checkout on main (this record on top of `fafe3d9`). Account all cash, $1,007,152, no positions. The local Claude
  server is up (xhigh, 3 slots) for the guardian. `OPEN_REFRESH_AGENTS` is on for tomorrow unless the backtest says otherwise.
- Relaunch recipe if a waiting run must pick up new code before the open: confirm no order lines today, create
  `state/reuse_signals`, stop the waiting `python cycle.py` and its cmd parent, wait for the task to show Ready, then
  `schtasks /Run /TN SemiBand-Cycle`; the log must show "reusing N signals recorded earlier".
- Next: backtest the open refresh against the next-open baseline (500 days, `--exec open`, no Claude) and decide before the
  2026-09-15 03:30 PT cycle; end-of-day record after 13:20 PT.

### 2026-09-14 07:40 PT — Claude root → anyone: open refresh backtested and switched OFF; live label start checked

- Did: five 500-day replays (RESEARCH.md round 27; commits `1a37208`, `7ca39e9`, `1b49fc1` add `--open-refresh`,
  `--label-open`, `--label-next-close` and `analyze_open_refresh.py`). With the live scorer's labels the refresh made
  +712% / Sharpe 1.96 / max DD 34.0% against +919% / 2.16 / 26.3% without it (paired OOS t = −2.17), so
  `OPEN_REFRESH_AGENTS = ()` in this commit. The live scorer's later label start was checked and is harmless (t = +0.20).
- State: live checkout on main with the refresh off for the 2026-09-15 03:30 PT cycle; the `state/reuse_signals` re-run path
  stays. Account all cash after today's SHEL sale. Research outputs: `state/backtest_report_or*.json`,
  `state/research_labels.txt`, logs `state/research_or*.log`.
- Next: the end-of-day record after 13:20 PT. Tomorrow's log should show no "open refresh" line.

### 2026-09-14 13:35 PT — Claude root → anyone: end of day, book in cash, the site's Sep 14 close pending Alpaca's daily point

- Close: account all cash, equity $1,007,151.78 against last_equity $1,006,860.73, day P/L +$291.05 (+0.03%), no positions.
  Since the Sep 10 open: Portfolio +0.72%, SOXX −4.04% (today −5.63%, nearly all of it the overnight gap: open to close
  +0.05%), SPY +0.38%, QQQ +0.23%. The seven names the pre-open plan would have bought (ES, EXC, SHEL, APD, D, MMM, ADBE)
  averaged −0.56% open to close; one day, no evidence either way.
- Guardian: ran hourly 07:35–12:35 PT, "no holdings" every time; no exits, no Claude calls.
- Site: https://semiband-dashboard.vercel.app returns 200 with published cycle 2026-09-14. The benchmark comparison and risk
  table still end at the Sep 11 close because Alpaca's daily portfolio history has no 2026-09-14 point yet (its daily points
  are stamped 20:00 ET); the live marks show after-hours prices. Check tomorrow that the Sep 14 close appears.
- State: live checkout on main, refresh off (`OPEN_REFRESH_AGENTS = ()`), effort xhigh, 3 workers, beta target, PAPER.
  Next cycle 2026-09-15 03:30 PT: expect "reusing" and "open refresh" lines to be absent and the Claude stage to finish before
  06:30 PT.

### 2026-09-15 02:05 PT — Claude root → anyone: latest price at order time restored and fitted; warm start swapped; conservativeness, negative convictions and shorts checked

- Did: the user reaffirmed at 01:30 PT that signals must use the latest price, with the model fitted to it, and delegated
  everything overnight. Commit `c3979a7` turns `OPEN_REFRESH_AGENTS` back on and makes `score.py` start labels at the close the
  signals used (tests 27 pass). The live warm start `state/backtest.sqlite` is now `backtest_orrefresh`; the old one is
  `state/backtest_nbfix_warmstart_20260911.sqlite`. A preview on a state copy fitted cleanly. Findings on conservativeness
  (regime behaviour, leave sizing), negative convictions (bullish map agents weighted against) and shorts (rejected in rounds 9
  and 18) are in RESEARCH.md round 28.
- State: live checkout on main with these records; the 2026-09-15 cycle runs at 03:30 PT with the refresh on; account all cash.
- Next: checkpoints 03:22, 03:37, 06:23, 06:57 and 13:27 PT. Rollback recipe in RESEARCH.md round 28.

### 2026-09-15 02:45 PT — Claude root → anyone: idle cash into SOXX adopted; Claude agents see today's latest price

- Did: user asked (2026-09-15 02:10 PT) for a more aggressive book and for every agent to see the current price. Commit
  `35b35aa`: `llm_supply` / `llm_guidance` price lines use today's newest trade when there is one (pre-market included);
  sizing knobs `MIN_STOCK_BOOK` and `IDLE_SLEEVE` plus backtest flags, a shared price cache and per-tag model files. Round 29
  (RESEARCH.md): five 500-day replays; concentration floors rejected; the trend-filtered SOXX sleeve adopted
  (+1152% / Sharpe 2.26 / DD 31.8% vs +895% / 2.14 / 31.1%). This commit turns `IDLE_SLEEVE = "SOXX"` on and adds the live
  sleeve path (`portfolio.sleeve_target`, `portfolio.plan_sleeve`, cycle wiring; tests 31 pass; dry rehearsal on a state copy).
- State: live checkout on main with the sleeve on for the 2026-09-15 03:30 PT cycle. SOXX closed below its 50-day average
  on 2026-09-14, so the sleeve starts out of the market until SOXX closes back above it.
- Next: the day's checkpoints (03:22, 03:37, 06:23, 06:57, 13:27 PT). Rollback: `IDLE_SLEEVE = None`. Open idea from the user:
  per-agent self-learning models under the stacking learner (a research round; the LightGBM ranker of 2026-09-10 hurt).
- 2026-09-15 02:45 PT, same session: a dry rehearsal showed the 03:30 PT cycle would have ABORTED: yesterday's SHEL exit went
  out through Alpaca's close_position, whose client id lacks `sb2-`, so `broker.foreign_orders` called it another bot's order.
  Fixed: an order the ledger recorded for the same New York date, symbol and side counts as ours; `broker.close` now sends a
  tagged market order when given a client id, and the cycle and guardian pass one. Verified read-only against the live account
  (the SHEL sell is no longer foreign). Also: the open refresh now takes today's ^VIX and ^TNX levels from yfinance, and the
  fundamentals re-pricing covers trailing P/E and market cap as well. User request logged for a research round: agents that
  improve themselves recursively, with the stacking learner still adjusting their weights.
- 2026-09-15 02:40 PT: macro 10-year-yield unit fix adopted (replay _sz5 vs _sz1: max DD 31.8% to 29.4%, return unchanged, paired t +0.01); RESEARCH.md round 29 addendum. Review partner and audit agent still running.

### 2026-09-15 03:10 PT — Claude root → anyone: factor agents rejected; review and audit fixes; branch-only fixes pending merge
- Did: eight cross-asset factor agents replayed on the live setup; every one alone and all eight together made the book worse (RESEARCH.md round 30), none adopted. A review partner and an audit agent found an order-blocking bug (the 120-minute wait for the open) and several sleeve and open-price issues; those went live in `8c2e3ae` before the 03:30 PT cycle. Branch-only commit (this one): events reads the last valid closes, a failed download is not cached as an empty column, the guardian's news search has its own cache key and remembers three days of headlines. Merge to main and pull into the live checkout AFTER the 2026-09-15 orders, not during the cycle.
- Open: the refreshed rows' label artifact (hybrid 'trade refreshed, learn pre-open' under review), sleeve vs bearish cash, plan() budget with sleeve sales, negative CV IC, liquidation vs foreign-order guard, EXIT_CONVICTION unused, TSM P/S currency.

### 2026-09-15 03:55 PT — Claude root → anyone: round 31 pre-registered; replay flags verified; guardian and events fixes
- Did: backtest.py gained --learn-preopen (hybrid: trade on the refreshed signals, record and learn the pre-open ones), --refresh-agents (default config.OPEN_REFRESH_AGENTS, as live) and --label-open on any --exec open run; each curve day records its held names. 60-day equivalence on one price cache: the patched refresh run is identical to the pre-patch one (curve, ledger, scores, final model); the hybrid's ledger, scores and model equal the no-refresh run's; the refresh without mean_reversion keeps mean_reversion's pre-open rows and technical's refreshed rows. The review partner found a guardian seen-memory off-by-one (from the second hourly check of a day only two previous days counted) and a benchmark date mismatch in events for a stock that stopped trading; both fixed with tests (46 pass). RESEARCH.md round 31 fixes the label (order-day open), the five runs, the gate, the stop rule and the decision rule before any 500-day run.
- Note: replays started in parallel without a price cache each trade on their own download and are not comparable (the first equivalence attempt diverged and one run crashed on the cache file). Start from an existing cache key.
- Open: gate results (_g0 _g1ref _g1 _g2 _g3); merge this branch (0d490f7 plus these fixes) into main after today's cycle process exits and before the 07:35 PT guardian.

### 2026-09-15 04:10 PT — Claude root → anyone: round 31 gate — keep the live setup
- Did: five 500-day replays per the round 31 pre-registration (RESEARCH.md). Under the order-day-open label every refresh form loses 6-7 bps/day to no refresh; the hybrid fails the gate and trips the stop rule (no more label variants); refresh without mean_reversion fails three of four conditions; the live setup (refresh, signal-close label) ties no refresh (-0.9 bps/day, t -0.17, lower drawdown). Decision as pre-registered: keep live, no config change. Also on the branch: parallel replays share the first price download that lands, an empty --refresh-agents list is refused, learner.save_model retries a momentary Windows lock (gate run _g0 died on one), and the flag tests cannot reach the network (387e55d).
- Open: merge the branch into main after today's cycle process exits and before the 07:35 PT guardian, then upload RESEARCH.md; next research to be agreed with the review partner (factor agents as shadow agents, per-agent learning), live config frozen meanwhile.

### 2026-09-15 04:25 PT — Claude root → anyone: refresh and label coupling pinned; round 32 learner ablation pre-registered
- Did: config.py and score.py comments now say the open refresh and the signal-close label are coupled (round 31: under a clean label every refresh form loses 6-7 bps/day to no refresh), so neither changes alone. The review partner showed the 74-point gap between _sz5 and _g1ref is the sleeve formula alone (identical ledgers); it stays as a risk-policy choice and is flagged to the user. backtest.py --prior-only trades on the equal-weight prior while the learner still fits daily, and each curve day records both 10-day ICs. RESEARCH.md round 32 pre-registers the learner ablation (_l0 on the clean-label no-refresh flags, _l1 on the live flags).
- Open: round 32 results (they decide research order only, not live settings); merge the branch into main after today's cycle process exits and before the 07:35 PT guardian.

### 2026-09-15 04:40 PT — Claude root → anyone: round 32 — the fitted weights make the book; per-agent learning deprioritised
- Did: learner ablation (RESEARCH.md round 32). Trading the equal-weight prior instead of the fitted weights cuts +1117% to +157% on the clean-label flags (+35 bps/day, t +2.47; OOS +58, t +2.69) and the top-15 rank book from +818% to +246%, but the learned whole-universe 10-day IC is below the prior's in the OOS half, so the pre-registered verdict is 'not demonstrated'. As pre-registered: no live change, per-agent learning deprioritised, new agents enter as shadow agents at weight 0, and future signal-quality gates use the top of the ranking (top-15 rank book, top-minus-bottom quintile spread on the order-day-open label). Two parallel replays started during the live Claude stage were killed for low memory; run research outside that stage.
- Open: review partner's critique of round 32; merge the branch into main after today's cycle process exits (before the 07:35 PT guardian) and upload RESEARCH.md; shadow-agent plumbing and factor IC screens after the live freeze.

### 2026-09-15 04:50 PT — Claude root → anyone: round 32 addendum — the edge is ~22 bps/day selection plus regime-dependent exposure; live config frozen
- Did: the review partner decomposed the learned-vs-prior gap (RESEARCH.md round 32 addendum): about two thirds beta-adjusted selection at the top of the ranking (+22 bps/day, t 1.8, similar in both halves), one third exposure timing whose beta flips between halves. Future signal-quality gates use the beta-adjusted top-15 rank book minus the equal-weight universe at t >= 1 with the same sign in both halves, with sized-book alpha and beta by half reported. The live configuration stays frozen; once the live book builds, compare its realised beta and gross with the replay (OOS beta 1.15).
- Open: merge the branch into main after today's cycle process exits and upload RESEARCH.md; shadow-agent plumbing and factor IC screens after the freeze.

### 2026-09-15 06:45 PT — Claude root → anyone: 09-15 open — no orders (every conviction negative); branch merged, live checkout updated
- Did: the 03:30 PT cycle ran on schedule on 8c2e3ae: 11 agents recorded (1,381 predictions; Claude stage 03:31-04:31 PT), open refresh at 06:30:32 PT (SOXX +0.9% vs last close, six agents re-run on 146 live prices). All 150 convictions were negative (max -0.122 MKSI, min -0.277), so no name reached +0.10 and no orders went out; the SOXX sleeve was off (below its 50-day average); the raw shadow model would have held about $81k. Account $1,007,152 cash, no positions; the cycle exited 06:30:43. Main fast-forwarded to 2c43fad (0d490f7 audit guards; ea1e739 round 31 flags, guardian seen-memory and events fixes; 387e55d replay cache race fix and model-save retry; round 31-32 records) and pulled into the live checkout before the 07:35 PT guardian; RESEARCH.md uploaded (the site shows rounds 31-32). A keep-awake power request (no settings changed) holds the PC awake until 13:40 PT.
- Open: end-of-day numbers at 13:27 PT; read guardian.log after 07:35 PT (first run on the new guardian and market code); live config frozen per rounds 31-32; next research: shadow-agent plumbing and beta-adjusted top-of-ranking gates for factor agents.

### 2026-09-15 07:30 PT — Claude root → anyone: user asked for long-short; round 33 pre-registered (market-neutral replay)
- Did: after another all-cash open the user asked for orders and proposed trading long and short together. Checked first: the always-on SOXX sleeve replay (_ag1) lost to live (+870% vs +1084%, Sharpe 2.00 vs 2.24, max DD 43.3% vs 28.8%, OOS -8.8 bps/day); no live prediction has been scored yet, so this week has taught the learner nothing; the all-negative convictions come from the two graph agents' contrarian direction-only weights (-0.154 of the -0.173 mean). With the user's choice, backtest.py gained --long-short N (market-neutral: top N long, bottom N short, beta-matched, 2 bps/day borrow, no sleeve; long_short_weights is unit-tested) and RESEARCH.md round 33 pre-registers _mn1 (N=10, decides) and _mn2 (N=15, robustness) against _g1ref.
- Open: round 33 results; live stays long-only and in cash today.

### 2026-09-15 07:50 PT — Claude root → anyone: round 33 amended before any result (gross kept at the ceiling)
- Did: the review partner found the first long-short code let the beta resize push gross to 2.25, so a pass could have been leverage. Corrected to the pre-registered gross (GROSS_TARGET split so the legs' betas cancel), non-finite convictions ignored, leg returns recorded; the two first runs were stopped unread. Stricter conditions added before any result: realised SOXX beta within 0.25 in both halves, and a shortability-restricted, higher-borrow confirmation before any live change. Corrected runs: _mn1b (N=10, decides) and _mn2b (N=15).
- Open: round 33 results; live stays long-only.

### 2026-09-15 07:45 PT — Claude root → anyone: round 33 failed (live stays long-only); round 34 pre-registered (SOXX sleeve robustness)
- Did: the round 33 market-neutral long-short book failed the gate by a wide margin (+70% and +90% against live +1084%; the short leg's beta-adjusted return was negative, turnover doubled). The user then asked whether the SOXX sleeve is overfitting or too crude: a 25-year check of its 50-day timing rule on SOXX alone loses to buy-and-hold (CAGR +5.5% vs +13.7%, Sharpe 0.35 vs 0.55); only a 200-day rule matches buy-and-hold on Sharpe with a smaller drawdown. RESEARCH.md round 34 pre-registers sleeve off (_sl0) vs the live 50-day rule (_g1ref) vs a 200-day rule (_sl200). Correction: the two previous entries stamped 07:30 and 07:50 PT were written at about 07:15 and 07:24 PT.
- Open: round 34 results (live config changes only with the user's agreement); exploratory 2-names-per-leg long-short run _mn3.

### 2026-09-15 08:00 PT — Claude root → anyone: sleeve switched to the 200-day rule (user decision); SOXX buy via a no-Claude re-run
- Did: round 34 (RESEARCH.md): sleeve off +911% / Sharpe 2.17, live 50-day +1084% / 2.24, 200-day +1123% / 2.23. The pre-registered rule kept 50 days (the 200-day Sharpe was 0.01 lower); the 25-year SOXX check favours 200 days (Sharpe 0.59 vs 0.35). The user chose 200 days and a SOXX buy today. config.IDLE_SLEEVE_TREND = 200; 53 tests pass; a state-copy rehearsal of today's re-run (recorded signals, no Claude calls) planned exactly one order: BUY SOXX $1,007,152. Exploratory, user question: long-short with 2 names per leg lost money (-7% over 470 days, max DD 45%).
- Next: pull into the live checkout, re-run today's cycle with the reuse marker, verify the SOXX fill; end-of-day report at 13:27 PT.

### 2026-09-15 08:17 PT — Claude root → anyone: 09-15 re-run placed the 200-day SOXX sleeve; filled
- Did: re-ran today's cycle at 07:57 PT on main ce12e64 with the reuse marker (the 1,382 signals recorded at 03:30, no Claude calls; open refresh on live prices, SOXX +0.3%). Stock convictions were still all negative, so the sleeve took the idle equity: two limit slices bought 2,012.533 SOXX (1,006.7692 @ 499.16 at 07:57:46 PT, 1,005.7638 @ 499.65 at 08:07:50 PT), about $1.0M. Account at 08:16 PT: equity $1,006,417, cash $2,082, SOXX market value $1,004,334. The cycle exited, the reuse marker was removed, and tomorrow's 03:30 PT run is scheduled.
- Notes: the guardian only watches universe stocks, so it does not monitor the SOXX sleeve; the sleeve exits when SOXX closes below its 200-day average (438.50 on 2026-09-15) or the vol target trims it.
- Open: end-of-day numbers at 13:27 PT; pull this HANDOFF commit into the live checkout at the end of the day.

### 2026-09-15 13:30 PT — Claude root → anyone: end of day 09-15
- Orders: the 03:30 PT cycle placed none (all 150 convictions negative; SOXX below its 50-day average). After the user asked for positions, the always-on sleeve (_ag1), a market-neutral long-short book (round 33) and a 2-names-per-leg long-short book (_mn3) all lost to live in replay. The user switched the sleeve to the 200-day rule (round 34: a tie in replay, better over 25 years of SOXX), and today's cycle was re-run at 07:57 PT without Claude calls: BUY 2,012.533 SOXX at an average $499.41 in two limit slices, about $1.0M.
- Day: equity $1,007,141 against last equity $1,007,151.78 (-$10). Since the Sep 10 open: portfolio +0.71%, SOXX -3.69%, SPY -0.08%, QQQ -0.43% (Alpaca daily bars to the close). Today: SOXX +0.36%, SPY -0.46%, QQQ -0.65%. Position: SOXX $1,005,059 (99.8% of equity).
- Site: 200, published cycle 2026-09-15; tiles and risk table match Alpaca; the risk context covers daily closes through the Sep 14 close (3 daily returns); Alpaca's daily history has no 2026-09-15 point yet.
- Guardian: six hourly runs, all 'no holdings' (SOXX is outside its universe); no exits.
- Findings: the all-negative convictions come from the two graph agents' contrarian direction weights (-0.154 of the -0.173 mean); no live prediction has been scored yet (the first 10-day scores mature around 09-24); every tested way of forcing exposure lost (rounds 17 and 29, _ag1, round 33, _mn3).
- Watch: a SOXX close below its 200-day average (438.50 today) exits the sleeve; realised book volatility above 50% trims it; on the first day stocks qualify, plan() counts the sleeve inside its gross budget and can under-size stock buys for a day (fix pending, with tests and review); background keep-awake jobs were killed by the session's memory guard (the 03:30 cycle task wakes the PC by itself).
- Open: tomorrow's 03:30 PT cycle on main (200-day sleeve, 11 agents, Opus xhigh); research queue: shadow-agent plumbing, factor IC screens, the plan() budget fix.

### 2026-09-16 00:05 PT — Claude root → anyone: round 35 keeps SOXX; live Claude agents at max effort from the 09-16 cycle; buy-budget fix on the branch
- Did: round 35 (RESEARCH.md): with a 200-day gate, SOXX alone +1123% / Sharpe 2.23 / DD 28.3% beat half-SOXX (+1024%, DD 28.2%), a SOXX+SPY mix (+1020%, DD 30.6%, OOS -1.3 bps/day t -2.0) and SPY (+908%, DD 32.9%); the mix and SPY had higher drawdowns because SPY's gate stayed on through the April 2025 semi crash (corrected in the 00:25 entry below: SPY's gate was off through April too; the difference is SOXX crossing first, 02-21 vs 03-10, plus a May whipsaw). The user's IGV idea: SOXX-IGV correlation +0.8 for 24 years, +0.39 in 2025-26 only; rejected. The user chose Opus max effort for the 03:30 cycle: config LLM_EFFORT=max, LLM_WORKERS=6 (ffa3de9, live), ~100 s/call measured on 09-11 so 450 calls need 6 slots to finish before the open. Branch only (this commit): plan() counts a sleeve sale in the same cycle toward the stock book's buy budget (audit item, material with a ~100% sleeve), with a test; merge after review and a rehearsal on 09-16, live from 09-17. The multi-ETF sleeve code stays unapplied in tmp.
- Watch on 09-16: the max-effort Claude stage's duration and signal counts (usage cap -> fewer signals), orders once agents finish, the 12-session no-stock rule (streak is 2 sessions).

### 2026-09-16 00:25 PT — Claude root → anyone: sleeve-sale failure guard; round 35 mechanism corrected
- Did: review of a579a1f found one real hazard: if the sleeve's market sell fails at the broker, the buys sized on its proceeds still go out (2.5x gross). Now the cycle keeps a fallback plan sized without the sleeve's proceeds and, if the sleeve SELL raises, resizes (or skips) the stock buys to it; unit-tested. Branch only until the 09-16 post-open rehearsal and merge (live from 09-17). RESEARCH.md round 35: the stated mechanism was wrong (SPY's gate was also off through April 2025; the difference is SOXX crossing 12 sessions earlier in Feb-Mar plus a May whipsaw), corrected in place; the decision (keep SOXX) stands.
- Review of 7f88633 (partner, 00:35 PT): sound, no blocker; merge after the 09-16 open. Follow-ups noted, not for tomorrow: the guard's predicate could be `t != config.IDLE_SLEEVE` instead of `t in universe`; a failed STOCK exit still leaves buys sized on its proceeds (bounded at ~1.65x gross by the cap); an accepted-then-rejected sleeve sell is not detected (a post-cleanup check that the sleeve position is gone when a close was sent would close it).

### 2026-09-16 01:05 PT — Claude root → anyone: improvement survey for the user; round 36 (external regime identifier) pre-registered
- Did: surveyed improvements not yet tested (RESEARCH.md rejections cross-checked): external regime identifier for the stock book (the 2019-23 hole), insider-transaction agent (Finnhub, point-in-time by filing date), analyst-revision and short-interest shadow agents, a 60-day horizon for graph information, macro factors redesigned per round 30; learner: rank / top-weighted target, posterior-variance sizing, regime-conditional weights, Kalman weights; infrastructure: shadow-agent plumbing, a mandatory 2019-23 gate, the pre-refresh shadow book. Round 36 pre-registered (nine indicators x OFF/HALF, fixed selection rule); the 2019-23 price-agent replay under the live setup (_pre2024b) is running; the screen script is tmp/regime_screen.py.
- Open: run the screen after _pre2024b finishes (outside the 03:30-05:40 Claude stage); a real replay for any passing gate.

### 2026-09-16 01:05 PT — Claude root → anyone: round 36 closed (no external regime gate passes); 2019-23 under the live setup is +63% / stocks +28%
- Did: _pre2024b (five price agents, live rules, 2019-04..2023-11): whole book +63% / Sharpe 0.34 / DD 32.5%, stock legs +28% (v2.3 on 09-11: -17%). Screened nine external indicators x OFF/HALF on both windows: none reaches +0.30 Sharpe in 2019-23 without giving up most of 2024-26 (the two volatility gates add +0.05-0.07 Sharpe there and cut 2024-26 by 84-92%). Closed; nothing goes to a replay. Next per the survey: rank / top-weighted learning target and posterior-variance sizing, designed with the review partner first (a rank target changes the conviction scale, which would confound sizing), then shadow-agent plumbing and an insider-transactions agent.

### 2026-09-16 01:55 PT — Claude root → anyone: backfill pre-work handoff absorbed (reference baselines recorded; Path B look-ahead under verification)
- Took: the graph-agent look-ahead claim (sent to the review partner with code questions), the two pre-backfill baselines as reference rows (they restate round 31: the clean-label refresh loses, no-refresh ties live), and the order verify Path B -> backfill -> replay with live flags. Dropped: running llm_backtest (LLM calls need the user's go-ahead and a slot outside the cycle); the handoff's 'live' baseline is the clean-label form. The backfill itself is earnings-ai work: the user's decision only.

### 2026-09-16 01:27 PT — Claude root → anyone: round 37 closed (rank target loses); graph-agent train/serve fix on the branch, pending review for the 03:30 cycle
- Did: round 37 (RESEARCH.md): the rank-ordered book +1001% / 2.17 against live +1129% / 2.24, rank-book alpha OOS t -1.49, daily IC lower; the sigma-clip control is inside noise. Keep live. Insider-purchase coverage (Finnhub, 2024-01..): 472 code-P purchases across 71 names, 14.8 a month but lumpy and TSM-heavy (151); usable only as a shadow agent with a point-in-time replay; low priority. The review partner found the live supply_chain / neighbors agents scoring today's cumulative exposure counts while the replay scores dated statements (live directions +0.55 / +0.41 vs replay +0.26 / +0.21), which with the learner's negative direction weights adds about -0.12 to every live conviction; fixed on the branch (1d4dfa9: PointInTimeMap moved to agents/graph_pit.py, live agents call it with asof = today; 60-day replay byte-identical pre/post; 60 tests pass). Merge before 03:30 only with the partner's no-blocker verdict and a clean rehearsal; otherwise Thursday.

### 2026-09-16 01:36 PT — Claude root → anyone: graph-agent one-code-path merged to main for the 03:30 cycle (with the budget fix and sell-failure guard, a day early)
- Rehearsal on a state copy (rule agents, no Claude, no orders) with the new formula: supply_chain 149 rows, mean direction +0.526, 100% positive, confidence 0.867; neighbors 113 rows, +0.552, 96%. The old live formula gave +0.553 / +0.413. So the gap to the warm start's overall means (+0.26 / +0.21) is a time effect of the graph (2,300 statements dated Jul-Aug 2026; warm-start rows since 2026-07-01 average +0.364 / +0.484), not the formula. The fix keeps live rows on the replay's formula (right for scoring and the warm start) but does not change today's convictions: the rehearsal planned 0 orders (top VICR -0.30). The remaining question is whether the learner's negative direction-only weights on near-constant positive graph features are a missing intercept: round 38 candidate, an explicit intercept (constant feature, prior 0) and DEMEAN_CONVICTION, pre-registered, replayed tomorrow outside the Claude stage.
- Merge: main ffa3de9 -> branch HEAD (1d4dfa9 graph fix, a579a1f sleeve-proceeds budget, 7f88633 sell-failure guard, inert round 36-37 research flags, records). Reviewed by the partner (no blocker); 60 tests; 60-day replay byte-identical pre/post. After today's cycle exits: mark the 958 old-formula live rows (09-10..09-15) as supply_chain_v0 / neighbors_v0 (tmp/mark_v0_rows.py --apply, backup first) before the 09-24 scoring; acceptance check: today's live rows should match the rehearsal's distribution.

### 2026-09-16 01:50 PT — Claude root → anyone: round 38 pre-registered (explicit intercept); the cash stance is a level forecast
- Did: the review partner's in-memory refits show the -0.12 conviction offset is about two thirds a genuine level forecast (the average name has lagged beta x SOXX every month since April 2026; decay-weighted target mean -0.10 / -0.15) and one third the graph agents' direction feature acting as a missing intercept. An explicit intercept does not open today's book (0 names >= 0.10); only removing the level does (1-3 names; demeaning the base model would buy ~18 graph-contrarian names, an artifact). RESEARCH.md round 38 pre-registers the diagnostics (intercept time series and its correlation with realised 20-day means), five runs (_i0.._i4) and the gates. Implementation and replays after today's open, outside the Claude stage; nothing live.

### 2026-09-16 02:30 PT — Claude root → anyone: the earnings-ai graph changes under running replays; pin --graph-asof for any comparison
- Found: two otherwise identical 60-day replays (01:22 and 02:20 PT) differed in 308 graph-agent rows (neighbors 291, supply_chain 17) and in nothing else, because earnings-ai rewrote graph/merged_graph.json and exposure.json at 01:39 PT. Any set of replays meant to be compared must share a graph snapshot: pass --graph-asof <date> (state/graph_snapshots/, daily since 09-11) to every run, as the round 38 runner now does. Round 38 research flags (aaab4ec, branch only) are being checked for equivalence on the pinned snapshot.
- 02:45 PT: on the pinned 2026-09-16 graph snapshot, the pre-round-38 learner/backtest (1d4dfa9) and the new code with the flags off (aaab4ec) give identical 60-day replays: 46,361 ledger rows, curve and final model all equal. The round 38 flags are inert by default (confirmed by run; the earlier mismatch was the 01:39 graph rewrite). The 07:20 runner pins --graph-asof 2026-09-16 and hashes the snapshot before and after the batch.

### 2026-09-16 06:35 PT — Claude root → anyone: 09-16 open on the new graph formula and Opus max — no orders; old-formula rows marked _v0
- Cycle: started 03:30:07; rule agents by 03:32:21 (supply_chain 149 rows +0.528, neighbors 113 rows +0.551, as the rehearsal); Claude server at max effort with 6 slots (banner effort deep=max). Claude agents: llm_supply 150/150 in 2,477 s, llm_guidance 142/150 in 3,011 s, llm_news 144/150 in 1,608 s (xhigh on 09-15: 1,168 / 1,493 / 886 s). Calls averaged ~100 s and ~11k output tokens; between ~04:42 and 04:47 the API slowed (calls of 300-420 s, one server 504 at 420 s) and 14 client calls timed out at 300 s; speed recovered by 04:50. Signals recorded 05:30:36; open refresh 06:30:40 (SOXX +1.6% vs last close, 146 live prices); equity $1,023,141; 0 targets (every conviction negative, max -0.13 AMAT, min -0.29 VICR); sleeve target $1,023,141 held within the band; 0 orders; cycle exited 06:30:54. Alpaca: SOXX 2,012.533 sh, +1.5%.
- Done: the 958 live rows the old graph formula produced (09-10..09-15) renamed supply_chain_v0 / neighbors_v0 at 06:31 (backup state/ledger_before_v0_mark_20260916_0631.sqlite; reverse UPDATE in tmp/mark_v0_rows.py), so the learner never fits on them; today's rows keep the live names.
- Follow-ups: agents/llm.ask_json timeout 300 s vs the server's 420 s (a call the client abandons still holds a server slot up to 420 s): align them before the next max-effort day; snapshots.take() overwrites the same-day snapshot dir (a timestamped dir or refuse-to-overwrite would be safer); the earnings-ai Ask engine shares the local server (opus/high calls at 04:40). Round 38 batch at 07:20 PT on the worktree code, pinned to graph snapshot 2026-09-16.

### 2026-09-16 07:40 PT — Claude root → anyone: two live fixes on the branch for tonight; shadow-agent design pre-registered; round 38 batch running
- Branch c48bb07 (review requested, merge tonight before 03:30): config.LLM_TIMEOUT = 480 replaces the hard-coded 300 s client timeout (server limit 420 s, slots shared with the earnings-ai Ask engine); snapshots.take() writes a second same-day snapshot to <date>_<HHMM> instead of overwriting (dir_for(<date>) keeps the first, later dates see the newest). 66 tests pass.
- RESEARCH.md: shadow-agent design pre-registered (config.SHADOW_AGENTS recorded and scored, never voting; learner row filter; breakdown exclusion; --shadow in the backtest; promotion by a pre-registered replay plus 60 live sessions, entering at prior 0). Code waits until the round 38 batch finishes: the batch's later runs import the worktree's learner.py and backtest.py fresh, so those files must not change mid-batch.
- Round 38 batch started 07:20 on snapshot 2026-09-16 (hash e5a7f9ef606e); results and the next step after it completes.

### 2026-09-16 08:55 PT — Claude root → anyone: round 38 — the level is a bias; DEMEAN_CONVICTION passes its pre-registered gate
- Did: five pinned replays (snapshot 2026-09-16 hash e5a7f9ef606e, same-day baseline). Diagnostic: the fitted level's correlation with the realised mean beta-abnormal is +0.13 / +0.09 with bootstrap CIs through zero and a zero forecast has lower MSE, so the level is a trailing-mean bias. An explicit intercept in convictions (_i1) and the intercept with graph direction terms dropped (_i3) lose (-5.8 bps/day, max DD 38%); the intercept fitted but excluded (_i2) ties with DD 23.5% but fails OOS >= 0 by a hair; DEMEAN_CONVICTION (_i4) PASSES: +1110% vs +1157% (t -0.26), Sharpe 2.25 vs 2.23, max DD 24.7% vs 29.5%, OOS +0.7 bps/day, 13.8 names and gross 1.10 (invested through 2026-04..08 where the baseline sat in cash). Adoption for the 09-17 cycle is pending the partner's critique and a rehearsal on today's signals (tmp/harness_demean.py). Also on the branch for tonight: LLM_TIMEOUT 480, the Claude stage deadline 09:05 ET with timing lines and a dashboard note, same-day snapshot protection (c48bb07, c4a254d, c1450a4; partner: no blocker).

### 2026-09-16 12:20 PT — Claude root → anyone: DEMEAN_CONVICTION adopted (round 38) and applied in an on-request afternoon run; branch merged to main
- User at 11:47 PT: "오늘도 주문안넣었네?? … 이거 그냥 인덱스펀드야 … 진짜 주문넣게 어떻게든 알고리즘 다시짜야해", then "지금실행하자" to the proposal (demean fix today before the close). Round 38's fix (the ridge's level is a trailing-mean bias; `DEMEAN_CONVICTION` passed its gate) went live at once: config b44aa74 (69 tests), branch fast-forwarded to main (LLM_TIMEOUT 480, stage deadline 09:05 ET + timings, same-day snapshot fix, round 38 flags), live checkout pulled, then `cycle.py --reuse-signals --no-llm` at 11:56 PT (recorded signals, price agents refreshed live, moderator skipped). Result: SOXX closed ($1,007,514), 14 names bought in two slices, all 29 orders filled in seconds; book 117% of equity. Details: RESEARCH.md "Round 38 adoption".
- Review partner (fresh agent, read-only) on d052aac..b44aa74: no blockers for 03:30. Fixed on the branch (c3a698f): dashboard/`top:` ranking by |conviction| (now signed, best longs first); `backtest.py --demean` defaults to the live config (`--no-demean` = raw control). Not fixed, for the record: a whole Claude agent skipped by the deadline is not counted in `llm.STAGE_SKIPPED` (no dashboard note; only reachable from a very late manual start); `llm_news` still fetches headlines per ticker before each `StageDeadline`, so a cut agent drains in minutes; the swallowed deadline exception text renders the machine's local time; `LLM_TIMEOUT` 480 also raises the guardian's sequential per-call timeout (worst case ~2 h per pass); the "convictions demeaned by" note records the pre-refresh mean while sizing uses the post-refresh one; `EXIT_CONVICTION` is dead (`portfolio.plan` gates on `MIN_CONVICTION`) and `web/components/Pipeline.tsx` still says "conviction ≥ 0.15" (both pre-existing).
- Tomorrow 03:30 PT: the first scheduled cycle with demeaned convictions, Opus max, 480 s client timeout and the 09:05 ET stage deadline. Expect a 10–20 name book; the sleeve stays off while stock targets exist. Dashboard history now holds two 09-16 entries (06:30 no orders, 11:56 fifteen); the afternoon trades have no moderator minutes. The four MARKET fallbacks (IEX quote spreads 400–1,000 bps on NRG/TT/HUBB/CARR/MMM) filled at normal prices.
- Session crons re-created after the restart: 13:27 PT today (end of day), 03:37 / 05:07 / 06:23 / 06:57 / 13:27 PT 09-17. Shadow-agent plumbing (tmp/patch_shadow.py + test_shadow.py) still unapplied.

### 2026-09-16 13:35 PT — Claude root → anyone: end of day — first demeaned book, +0.46% on the day; the guardian never ran (laptop on battery); charger needed for the 03:30 cycle
- Close: equity $1,010,686 (+$4,652 / +0.46% on the day; last_equity $1,006,034), 14 positions worth $1,184,776 (117% of equity, cash −$174,090), every name within ±0.6% of its fill. Since the 09-10 open: portfolio +1.07% vs SOXX −3.07%, SPY −0.53%, QQQ −0.40% (SIP daily bars). Sleeve off (SOXX sold at 11:56; the multi-ETF sleeve was never merged, round 35). Dashboard 200 on the 09-16 afternoon cycle with the demean note; tmp/verify_live_page.py needs a local dev server on port 3108 and was not run.
- Morning Claude stage (max, 6 slots): llm_supply 150/150 in 2,477 s, llm_guidance 142/150 in 3,011 s (6 client timeouts 04:45–04:47 during the API throttling: ACMR, POWL, ASML, VIAV, META, VRT), llm_news 144/150 in 1,608 s; stage 03:32–05:30; 0 orders at the open (raw convictions all negative, see the 12:20 entry for the fix).
- Guardian: no run today. Task SemiBand-Guardian has DisallowStartIfOnBatteries=true / StopIfGoingOnBatteries=true and the laptop has been on battery (20%, ~2 h left at 13:30), so every hourly start was refused (last attempt 11:49:51, result 0x800710E0 "the operator or administrator has refused the request"); guardian.log's last line is 09-15 12:35. The cycle task can start on battery (DisallowStartIfOnBatteries=false, WakeToRun=true), but a dead battery means no 03:30 run until the PC is powered on again. User notified (push + report): plug in the charger. Whether to drop the guardian task's battery condition is the user's call (a system setting).
- Next: 03:30 PT first scheduled demeaned cycle (expect 10–20 names; SOXX off while stock targets exist); session checkpoints 03:37 / 05:07 / 06:23 / 06:57 / 13:27. Shadow-agent plumbing (tmp/patch_shadow.py, test_shadow.py) still unapplied.

### 2026-09-16 20:00 PT — Claude root → anyone: AQuA items applied, the enriched graph integrated (round 39), warm start moved to the new-graph ledger for 09-17
- User (19:00 PT): apply everything from the AQuA review; earnings-ai's 2026 US earnings-call backlog is enriched (all US graph companies) and conferences are in; 10-K/8-K still not wanted. Findings: the graph went 4,217 → 6,000 dated rows (+1,783 calls, Jan–May 2026), 352 nodes / 1,400 edges, +CBRS; conferences already feed the graph agents and the Claude agents; filings feed only the graph agents. Snapshot `2026-09-16_1917` pins it; the live graph-agent rows for today are unchanged on it (rehearsal: supply_chain +0.529, neighbors +0.557), so the data moves history, not tomorrow's directions.
- Applied (branch, merged to main tonight): validation/embargo/test gate (`analyze_round39.py`, protocol in RESEARCH.md and memory); point-in-time equivalence tests (`test_point_in_time.py`: risk/macro sliced-history fast paths and the RSI precompute equal the prefix computation, future-dated graph rows change nothing); round 39 switches `GRAPH_TRANSCRIPTS_ONLY` and `DEMEAN_GROUP` (inert; `learner.demean` now shared by the cycle and the replay); 80 tests.
- Round 39 (RESEARCH.md): the enriched graph alone is inside noise (`_n0` vs old-graph `_i4` −1.2 bp/d, t −0.26); filings-out fails validation by a hair (no power there: the graph is silent before 2025-10) with a +6 bp/d one-shot test that cannot be used to choose; chain-neutral passes validation but its one-shot test is −11 bp/d with a 33% drawdown in the 2026 sell-off → not adopted. Protocol addendum from round 40: a one-shot test that is significantly worse vetoes adoption.
- Warm start: `state/backtest.sqlite` (`_sz5`, pre-enrichment graph) replaced by `_n0`'s ledger (enriched graph, live flags); old file kept as `state/backtest_sz5_before_n0_20260916.sqlite`. Rehearsal of the 09-17 fit on it (today's signals, evening prices): weights supply_chain −0.234, neighbors +0.184, risk 0.083, fundamentals/Claude 0.079; a 19-order rebalance into a mixed chip + power book (SHEL, STM, D, ETR, XEL, TXN, ENTG, ES, MSFT, AMZN …), sleeve off. Expect a large rebalance at the 09-17 open.
- Not done tonight: shadow-agent plumbing (tmp/patch_shadow.py + test_shadow.py) stays unapplied until after the 09-17 cycle (keeps tonight's live diff small); adaptive vol target (paper item) is a later round; `_n1` re-test once a validation window contains graph-covered months.

### 2026-09-17 00:35 PT — Claude root → anyone: literature review absorbed; rounds 40–44 queued; no code or live change tonight
- User forwarded another session's paper review ("논문 리뷰 시켰거든? 이거 결과 좀 써"). Absorbed into RESEARCH.md ("literature review absorbed"): the round 15 llm_guidance validation carries a memorisation caveat (its IC is an upper bound; the live track is the test; an anonymised twin goes in as a shadow agent); queued replays in order: round 40 residual (beta-adjusted) momentum in technical, 41 adaptive vol target + trend-bet ablation, 42 partial SOXX beta hedge (both windows; 2022 decides), 43 fear-state interaction feature, 44 model-side turnover penalty; an offline neighbors diagnostic; shadow agents (opportunistic insider buys per Cohen–Malloy–Pomorski, llm_guidance_anon) after the shadow plumbing. Protocol addenda: half-of-published-effect expectation for promotions; memorisation caveat on any LLM backtest claim.
- Nothing changed in code or state tonight: the 03:30 cycle runs on 926dfed with the `_n0` warm start. Round 40's code (inert `TECHNICAL_RESIDUAL` flag) and its replays come after the 09-17 open, and only on AC power (battery 21% at 00:20 PT, charger asked for twice).

### 2026-09-17 01:55 PT — Claude root → anyone: round 40 done (residual momentum not adopted), protocol v3 pre-registered, branch ahead of main by the inert round 40 switch
- Round 40 (RESEARCH.md): `_r1` fails the pre-registered gate (validation −2.4 bp/d, Sharpe 2.31 vs 2.38) and wins the one-shot test (+10 bp/d, max DD 22.6% vs 27.3%); the 2019–23 residual run `_p1` died twice on the memory guard (2.4 GB free with the user's apps open) → daytime queue after 05:40. Protocol v3 (six purged alternating blocks; test veto) applies from round 41; `_n1` and `_r1` re-tested there.
- Branch e7c153d+ (inert `TECHNICAL_RESIDUAL` in agents/technical.py, `analyze_v3.py`, records) is NOT pushed to main yet: agents/technical.py is a live file and the review partner has not read it. Review after the 03:30 cycle, then push and pull. The 03:30 cycle runs on main 5b4b783 with the `_n0` warm start; watchdog cron at 03:12 confirms no replay is running.

### 2026-09-17 06:35 PT — Claude root → anyone: research VM live; round 41 adopts filings-out for 09-18; residual momentum stays off; protocol v4
- Research VM: GCP project `semiband` (gijunpark42, $299 credit), instance `semiband-research` (us-west1-b, e2-highmem-4, 32 GB), user calif, key `~/.ssh/google_compute_engine`, layout `~/semiband/{repo,.venv,state}`, dummy `.env` (replays use yfinance and the copied universe cache; no Alpaca keys on the VM), PT timezone, `EARNINGS_AI_DIR` = newest copied snapshot. Scripts: `tmp/vm_sync.ps1` (laptop inputs → VM), `tmp/vm_run.sh runs.txt N` (N replays in parallel; needs an absolute runs path or the file beside the script). Stopped when idle (`gcloud compute instances stop semiband-research --zone us-west1-b`; start again before a batch). Same code + same cache is NOT bit-identical across machines (ulp-level agent math → different marginal names): compare only same-machine same-day runs (RESEARCH.md 04:50 entry).
- Round 40 addendum + protocol v4 (RESEARCH.md): the odd/even block split put every crash in the test blocks; v4 = full-window gate + 4-of-6 block consistency + the independent 2019–23 window + trial counting. Round 41 under v4 on the VM: `GRAPH_TRANSCRIPTS_ONLY` PASS (adopted, bbf4ed5, live from 09-18), residual momentum FAIL on consistency (V-shaped rebounds), both-switches FAIL.
- Review (read-only partner) of the round 40 switch: OFF bit-identical; ON had a NaN-beta blocker on a non-positive price → fixed (2cfc139) with a test; the replay restores the flag after a run.
- To do after today's cycle exits: push main, pull the live checkout (currently 5b4b783; branch bbf4ed5 = records + inert TECHNICAL_RESIDUAL + filings-out ON), swap the warm start to `state/backtest_w2.sqlite` (backup `_n0` as `backtest_n0_before_w2_20260917.sqlite`), record in HANDOFF; 06:57 checkpoint reads the 09-17 open (first demeaned scheduled cycle, `_n0` warm start).

### 2026-09-17 07:00 PT — Claude root → anyone: 09-17 open — first scheduled demeaned cycle on the `_n0` warm start; 15-name book at 143% gross
- Claude stage 03:32–05:30, 451 calls, 0 timeouts, 0 deadline skips (supply 95 s/call, guidance 118 s, news 64 s). Open 06:30: demean −0.156, 23 names above 0.10 (max 0.244), sleeve off. Orders 15: full exits APH, CARR, HUBB, NEE, NRG, SPXC, TT; buys ETR $119k, XEL $112k, AMZN $107k, STM $100k, MSFT $92k, AEP $91k, TXN $89k, CSCO $85k in two slices (06:30, 06:47); all 23 fills done by 06:47, no cleanup orders. Book 15 names (D, ES, SHEL, UBER, EXC, APD, MMM kept), long market value $1.45M = 143% of equity $1,018,793 (cash −$434k), day +0.8% at 06:57. Cost estimate $664. Four market-order fallbacks again on wide IEX quotes (ETR 1,015 bps, TXN, CSCO); fills normal.
- Live checkout pulled to bbf4ed5+ (records, inert TECHNICAL_RESIDUAL, GRAPH_TRANSCRIPTS_ONLY = True for 09-18); warm start swapped to `state/backtest_w2.sqlite` (filings-out, VM, 09-17 cache); `_n0` kept as `backtest_n0_before_w2_20260917.sqlite`. Research VM stopped (start it before the next batch).

### 2026-09-17 14:40 PT — Claude root → anyone: end of day — +1.24% on the first scheduled demeaned book; guardian back; checkpoints re-created after a session restart
- Close: equity $1,023,149 (+$12,579 / +1.24% on the day; last_equity $1,010,570), 15 positions worth $1,457,201 (142% of equity, cash −$434k). Since the 09-10 open: portfolio +2.31% vs SOXX +0.22%, SPY +0.60%, QQQ +1.32%. Today SOXX +3.39%, QQQ +1.73%, SPY +1.13%: the half-defensive book lagged a strong semis day and beat SPY. Winners ES +2.1%, MMM +1.4%, D +1.0%; laggards TXN −2.6%, STM −0.6%.
- Guardian ran hourly from 07:35 on AC power (15 holdings per pass, 0 exits; it starts the local Claude server itself). Dashboard 200 on the 09-17 cycle.
- The Claude Code process restarted around midday: session crons were lost (the 13:27 checkpoint ran late at 14:35) and were re-created for 09-18 (03:37, 05:07, 06:23, 06:57, 13:27). Battery was discharging again at 14:34 (96%): the charger must be in for the 03:30 cycle.
- Tomorrow 03:30: first cycle with GRAPH_TRANSCRIPTS_ONLY on and the `_w2` warm start (main 0a678ad+). Research queue on the VM (stopped now): round 42 adaptive vol target + brake ablation (code first), round 43 fear-state feature with a regime-conditioned residual momentum, round 44 turnover penalty; shadow plumbing still unapplied.

### 2026-09-17 17:10 PT — Claude root → anyone: audit done and fixed; corrected headline +1,028% / 2.14 / 30.1%; insider runs live as a shadow from 09-18; rounds 42–43 closed
- Audit (RESEARCH.md 17:10 and 17:00 entries): training/labels clean; fixed on the branch: drifted holdings in the replay (the free daily rebalancing was worth ~62 points), FRED "latest" values live-only (a laptop-only replay look-ahead), deflated Sharpe with a real trial floor (`config.RESEARCH_TRIALS = 330`, raise it every round), equal-weight universe baseline (+245%) and a missing-price counter in every report, the rank book pays its rebalancing, roster/RSI-cache/best-quarter bugs, `--earnings-shift` sensitivity (perfect dates ≈ 0.5 bp/d), Newey-West t next to the iid t in `analyze_v4.py`. Structural and unfixable by code: the hindsight universe (compare with +245%, not SOXX), the spent OOS window (expect Sharpe ~1 live), 2026-written statement text, 5 bps optimism (30 bps ≈ +600%).
- Rounds 42 (gross 2.0, beta floor 0.5, both) and 43 (vol brake off / median / 0.40): all fail v4 on 2024–26 (risk dials, not improvements). Sizing is closed; further return has to come from agents.
- Shadow agents live from 09-18: `SHADOW_AGENTS = ("insider",)` (recorded and scored, never voting; reviewer verified the plumbing is inert for the voting roster, two live blockers fixed: fetch budget + throttle stop, shadow-only tickers never enter the convictions). Insider replay: no measurable edge (+0.23% per 20 d, t 0.2); live record starts now. Finnhub answered a request in 41 s today, so the fetch moved out of the cycle: Windows task `SemiBand-Insider` at 01:35 PT runs `python -X utf8 -m agents.insider` with a 40-minute budget and writes the daily marker; the 03:30 cycle then reads `state/insider/*.json` (seeded with the 09-16 collection) without fetching.
- Research VM: `_a*` and `_b*` audit runs; stop the instance after `_b1` (about 17:20 PT). Weekly audit cron Saturday 10:07 PT (session-only; memory `routine-audit`). Checkpoints 09-18: 03:37 / 05:07 / 06:23 / 06:57 / 13:27.

### 2026-09-17 18:25 PT — Claude root → anyone: round 44 closed; two live shadows from 09-18; VM stopped
- Round 44 (RESEARCH.md): customer momentum (Cohen–Frazzini via the graph's edges) is the most consistent new signal so far (+0.82% per 20 d, positive every half-year, IC +0.10) but as a vote it adds return, Sharpe and drawdown on both windows and fails v4 block consistency (2024–26) and the drawdown limit (2019–23); supplier momentum hurts. Diagnostic: the two graph agents net about zero over their covered months with six points more drawdown. Live from 09-18: `SHADOW_AGENTS = ("insider", "customer_momentum")` (main bfa6cdb+, rehearsed on a state copy: 11 and 98 rows, book unchanged). Round 45 pre-registered: customer momentum gated to SOXX above its 50-day average.
- Tonight: `SemiBand-Insider` task 01:35 PT (first run; log `state/insider_refresh.log`), the 03:30 cycle with both shadows, checkpoints 03:37 / 05:07 / 06:23 / 06:57 / 13:27. Battery was discharging at 53% at 18:02 PT.

### 2026-09-17 19:05 PT — Claude root → anyone: customer momentum adopted as a voter for 09-18 (user decision); warm start = `_c3`; user leaving the PC
- User: "낙폭 증가해도 샤프랑 수익률 늘었으니까 하자", then "기록하고 니가 알아서 해". Done: `config.AGENTS` + `customer_momentum` (12 voters), `SHADOW_AGENTS = ("insider",)`, warm start swapped to `state/backtest_c3.sqlite` (backup `backtest_w2_before_c3_20260917.sqlite`), 104 tests. Rehearsal on a state copy and a read-only review were running at the time of writing; if either reports a blocker before 03:30 the roster change is reverted (config + warm start back to `_w2`).
- User was told: do not shut the PC down, plug in the charger and close the lid (battery 50% discharging at 18:30; the 01:35 and 03:30 tasks wake the PC from sleep only).
- 09-18 checkpoints 03:37 / 05:07 / 06:23 / 06:57 / 13:27; weekly audit Saturday 10:07. VM stopped.
- 19:15 PT: review of the voter (read-only): runs live with no further wiring; the fit rejects the 11-agent model and refits with 12 (equal priors); features zero-fill missing agents; the replay roster `SIM_AGENTS` now includes customer_momentum (untagged replays keep the live roster). Not in the open refresh, as `_c3` was measured; a refresh variant is a later test. Rehearsal on the `_c3` warm start: customer_momentum weight 0.117, plan = 4 orders on today's reused signals, no error. Nothing left to revert.
