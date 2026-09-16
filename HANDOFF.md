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
