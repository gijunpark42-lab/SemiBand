"""Read the fixed comparison files, apply declared screens and write the report."""
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import robustness
from analyze_round24 import paired_blocks

OUT = Path(__file__).resolve().parent
NAMES = ["baseline","gross_200","size_080","gross_200_size_080","rank_floor_005"]
QUICK = "--quick" in sys.argv


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def find(results,name,cost="cap",rate=0.05):
    return next(row for row in results if row["name"] == name and row["cost"] == cost and row["annual_financing"] == rate)


def pct(number):
    return f"{number*100:+.2f}%"


def p(number):
    return "n/a" if number is None else f"{number*100:.1f}%"


def attribution(curve, mask):
    """Descriptive accounting only: normalize the SAME realized weights each day.

    The hypothetical unit-exposure sleeve omits its own turnover/financing and
    must not be presented as an executable strategy or a new adoption variant.
    """
    selected = [day for day, keep in zip(curve, mask) if keep]
    if not selected:
        return None
    gross = np.array([day["gross"] for day in selected])
    price = np.array([day["price_return"] for day in selected])
    account = np.array([day["ret"] for day in selected])
    bench = np.array([day["soxx_ret"] for day in selected])
    trading = np.array([day["trading_cost"] for day in selected])
    financing = np.array([day["financing_cost"] for day in selected])
    active = gross > 1e-12
    sleeve = np.divide(price, gross, out=np.zeros_like(price), where=active)
    selection = gross * (sleeve - bench)
    utilization = (gross - 1) * bench
    residual = account - bench - selection - utilization + trading + financing
    if np.max(np.abs(residual)) > 1e-12:
        raise AssertionError("Selection/utilization/cost attribution does not reconcile")

    def stats(returns):
        if not len(returns):
            return None
        return {"compound_return":float(np.prod(1+returns)-1),
                "mean_daily_bps":float(np.mean(returns)*10000),
                "sharpe":robustness.sharpe(np.log1p(returns))}

    return {"days":len(selected), "active_sleeve_days":int(active.sum()),
            "gross_mean":float(gross.mean()), "positive_cash_mean":float(np.maximum(1-gross,0).mean()),
            "account_net":stats(account), "soxx_same_days":stats(bench),
            "sleeve_before_cost_active_days":stats(sleeve[active]),
            "soxx_same_active_days":stats(bench[active]),
            "matched_gross_soxx_before_cost":stats(gross*bench),
            "matched_gross_soxx_identical_cost_deduction":stats(gross*bench-trading-financing),
            "mean_daily_bps_decomposition":{
                "selection":float(selection.mean()*10000),
                "capital_utilization":float(utilization.mean()*10000),
                "trading_cost":float(-trading.mean()*10000),
                "financing_cost":float(-financing.mean()*10000),
                "account_minus_full_soxx":float((account-bench).mean()*10000)},
            "max_absolute_identity_residual":float(np.max(np.abs(residual)))}


def write_handoff(summary, rows):
    """Concise public-safe handoff; detailed curves/caches remain local only."""
    base=find(rows["recent"],"baseline")
    low=summary["attribution"]["recent"]["baseline"]["baseline_below20_days"]
    a=low["mean_daily_bps_decomposition"]
    passing=[name for name,status in summary["acceptance"].items() if status["material_pass"]]
    lines=["# Higher-exposure comparison: operating handoff — 2026-09-12","",
           "## Decision and the user's actual concern","",
           "USER FINAL DECISION: KEEP the current signal-sized, cash-holding structure. Do not apply an exposure change. Wrap up, record and push the research only.","",
           "No supported material upgrade among the four alternatives." if not passing else "Material-screen pass: "+", ".join(passing)+".","",
           "Preserve the predeclared screen; do not interpret small Sharpe gaps as proof of inferiority. Higher total return with higher drawdown can be a risk-preference choice, not a statistically established improvement. This research does not apply a winner. Parent owns integration; operational gross1.50 / size0.60 remain unchanged by this runner.","",
           f"Cash drag is real on the recent baseline's {low['days']} days below20% exposure: mean gross {p(low['gross_mean'])}, conditional account return {pct(low['account_net']['compound_return'])}, SOXX {pct(low['soxx_same_days']['compound_return'])}. Exact mean daily excess: selection {a['selection']:+.2f}bps + utilization {a['capital_utilization']:+.2f}bps − trading {abs(a['trading_cost']):.2f}bps. This conditional subset is not a continuous return history.","",
           f"The same-name unit-gross sleeve on its {low['active_sleeve_days']} active subset dates returned {pct(low['sleeve_before_cost_active_days']['compound_return'])} before costs versus {pct(low['soxx_same_active_days']['compound_return'])} for SOXX on exactly those dates. Cash dominated the account shortfall, but that does not establish chosen-name superiority on low-deployment days. The real PAPER account has only two sessions; live edge cannot be inferred.","",
           "## Fixed comparisons: cap-tier trading costs +5% annual financing","",
           "| Variant | Recent return / Sharpe / DD | Recent OOS Sharpe | Stress return / Sharpe / DD | Mean gross recent / stress | Recent low-day gross |",
           "|---|---:|---:|---:|---:|---:|"]
    for name in NAMES:
        recent,stress=find(rows["recent"],name),find(rows["stress"],name)
        r,s=recent["full"],stress["full"]
        low_g=summary["low_exposure"]["recent"]["variants"][name]["gross_mean_on_baseline_below20_days"]
        lines.append(f"| {name} | {pct(r['total_return'])} / {r['sharpe']:.3f} / {p(r['max_drawdown'])} | {recent['oos']['sharpe']:.3f} | {pct(s['total_return'])} / {s['sharpe']:.3f} / {p(s['max_drawdown'])} | {p(r['gross_mean'])} / {p(s['gross_mean'])} | {p(low_g)} |")
    lines += ["","Gross2 is a ceiling, not a deployment target. Size0.8 scales eligible names but leaves many low-conviction dates mostly cash. Rank+5% floor materially lifts low exposure, but admits weaker positive names and is not a guaranteed whole-book floor; it must be evaluated with its drawdown, stress and cost behavior.","",
              "| Variant | 30bps +5%: recent return / Sharpe / DD | 30bps +5%: stress return / Sharpe / DD | 10% financing, cap costs: recent / stress returns |",
              "|---|---:|---:|---:|"]
    for name in NAMES:
        r,s=find(rows["recent"],name,"flat30")["full"],find(rows["stress"],name,"flat30")["full"]
        r10,s10=find(rows["recent"],name,rate=.10)["full"],find(rows["stress"],name,rate=.10)["full"]
        lines.append(f"| {name} | {pct(r['total_return'])} / {r['sharpe']:.3f} / {p(r['max_drawdown'])} | {pct(s['total_return'])} / {s['sharpe']:.3f} / {p(s['max_drawdown'])} | {pct(r10['total_return'])} / {pct(s10['total_return'])} |")
    lines += ["","## Validation, uncertainty and continuation","",
              "- Five predeclared variants × two regimes × two trading-cost models × three financing rates =60 completed scenarios. Daily refits on470 recent and1,170 stress dates; OOS signal date strictly before2025-09-24. Beta outcomes already occupy legacy `abnormal`, read explicitly as `target_mode='raw'`.",
              "- Minimum screen: recent OOS Sharpe improves, full Sharpe/score do not fall. Material screen adds >0.15 full/OOS Sharpe gain, DD within2pp, at least80% baseline return, nonlower stress return/Sharpe. All four alternatives fail the minimum and material screens in this run.",
              "- Financing applies the same `max(gross-1,0)*rate*calendar_days/365` rule to every book, including baseline, inside the volatility-feedback replay. Rates0/5/10% are hypothetical sensitivities, not broker quotes; no positive-cash yield.",
              "- Twelve zero-financing parity comparisons against unchanged `sweep.simulate` passed, including every daily rounded log return; six sizing/financing/attribution unit tests passed. Input ledgers remained byte-identical. Current versus prior zero-financing baseline figures are recorded in the detailed report; price snapshot identity is not assumed.",
              ("- Additional paired40/80-day bootstrap, PBO and DSR diagnostics were deliberately NOT run because the user requested immediate wrap-up. This is an explicitly incomplete statistical-diagnostic phase, not missing scenario results. Resume by running the analyzer without `--quick`; no new model fits or variant selection are needed." if QUICK else "- Paired40/80-day block intervals, PBO and historical-trial-aware DSR are in the detailed local report/summary.")+" These reused data are not a fresh holdout; survivor-biased universe, incomplete correlated trial history and stress's price/calendar-only information set prevent a production-edge claim.",
              "- Price snapshot is one newly fetched common adjusted Open/Close panel,2018-01-02–2026-09-11, SHA-256 `fad4ad3c41cbbbef89c2395ce294cd0ee5ad31b6c9432ac5791ecea0f81b0458`. Original round24 frames were not retained. PLAB was retried alone before any simulation; every comparison uses the completed snapshot.",
              "- Inherited simulator limits: nondrifting target weights, missing prices marked zero return, rebalance band after gross/vol controls can exceed the stated ceiling, no impact/fill/buying-power/margin-call modeling. Vol50% scales down only, never up to fill cash.",
              "- Parent's separate saved-Friday-opinion diagnostic: raw target7.90%; activated-beta target27.67% in4 names; beta size0.8 target36.90%; gross2 alone unchanged. These are model targets, without guardian/account-vol/bands/fills, not actual holdings or new orders.","",
              "Committed reproduction sources: `research_higher_exposure_20260912.py`, this folder's `analyze_results.py`, `test_financing_replay.py`, `protocol.md`, `attribution_protocol.md`, and this report. Large input prices/model caches/full curves/results stay local and are not committed. Run both `--regime` commands then the analyzer as described in the detailed report. No operational source/defaults, broker activity, schedules, LLM calls or dashboards changed.","",
              "Local evidence: same-folder `report.md` (full tables/uncertainty), `summary.json` (metrics/attribution), `results_recent.json` and `results_stress.json` (full curves), `price_manifest_complete.json` (provenance), daily-model caches. Root-facing copy: top-level `outputs/higher_exposure_report_20260912.md`. For continuation, audit these artifacts before any separate user-authorized deployment/integration decision.",""]
    handoff="\n".join(lines)
    # Keep compact technical labels readable in the human-facing handoff.
    for original,replacement in {"gross1.50":"gross 1.50","size0.60":"size 0.60","below20%":"below 20%",
                                 "Gross2":"Gross 2","Size0.8":"Size 0.8","30bps":"30 bps","=60":"= 60",
                                 "on470":"on 470","and1,170":"and 1,170","before2025":"before 2025",
                                 "within2pp":"within 2 pp","least80%":"least 80%","Rates0/5/10%":"Rates 0/5/10%",
                                 "paired40/80":"paired 40/80","panel,2018":"panel, 2018","Vol50%":"Vol 50%",
                                 "target7.90%":"target 7.90%","target27.67%":"target 27.67%","in4 names":"in 4 names",
                                 "size0.8":"size 0.8","target36.90%":"target 36.90%","gross2":"gross 2"}.items():
        handoff=handoff.replace(original,replacement)
    (OUT/"HANDOFF.md").write_text(handoff,encoding="utf-8")
    (ROOT.parents[1]/"outputs/higher_exposure_report_20260912.md").write_text(handoff,encoding="utf-8")


def main():
    raw = {regime:read(OUT/f"results_{regime}.json") for regime in ("recent","stress")}
    rows = {regime:data["scenarios"] for regime,data in raw.items()}
    expected={(name,cost,rate) for name in NAMES for cost in ("cap","flat30") for rate in (0,.05,.10)}
    for regime,result in rows.items():
        if len(result)!=30 or {(row["name"],row["cost"],row["annual_financing"]) for row in result} != expected:
            raise AssertionError(f"{regime}: incomplete fixed comparison; do not publish a completion report")
        parity=[row["parity"] for row in result if row["parity"]]
        if len(parity)!=6 or not all(check["passed"] for check in parity):
            raise AssertionError(f"{regime}: expected six passed reference parity checks")
    summary = {"identity":{regime:data["identity"] for regime,data in raw.items()},"acceptance":{},
               "additional_statistical_diagnostics_skipped_for_user_wrapup":QUICK,
               "diagnostics":{},"current_run_vs_prior":{},"low_exposure":{},"attribution":{},
               "scenarios":{regime:[{key:value for key,value in row.items() if key != "curve"} for row in result]
                            for regime,result in rows.items()}}
    for name in NAMES[1:]:
        recent, base = find(rows["recent"],name), find(rows["recent"],"baseline")
        stress, stress_base = find(rows["stress"],name), find(rows["stress"],"baseline")
        r,b,s,sb = recent["full"],base["full"],stress["full"],stress_base["full"]
        minimum = {"oos_sharpe_improves":recent["oos"]["sharpe"] > base["oos"]["sharpe"],
                   "full_sharpe_not_lower":r["sharpe"] >= b["sharpe"],"score_not_lower":r["score"] >= b["score"]}
        material = {**minimum,"full_delta_sharpe_above_015":r["sharpe"]-b["sharpe"] > 0.15,
                    "oos_delta_sharpe_above_015":recent["oos"]["sharpe"]-base["oos"]["sharpe"] > 0.15,
                    "drawdown_within_2pp":r["max_drawdown"] <= b["max_drawdown"]+0.02,
                    "return_at_least_80pct_baseline":r["total_return"] >= 0.8*b["total_return"],
                    "stress_return_not_lower":s["total_return"] >= sb["total_return"],
                    "stress_sharpe_not_lower":s["sharpe"] >= sb["sharpe"]}
        summary["acceptance"][name] = {"primary_cost":"cap","primary_financing":0.05,
                                       "minimum_screen":minimum,"minimum_pass":all(minimum.values()),
                                       "material_screen":material,"material_pass":all(material.values()),
                                       "failed_material":[key for key,value in material.items() if not value]}
    for regime,result in rows.items():
        primary = [find(result,name) for name in NAMES]
        base_curve = primary[0]["curve"]
        low = np.array([row["gross"] < 0.2 for row in base_curve])
        spans = {"full":np.ones(len(base_curve),dtype=bool),"baseline_below20_days":low,
                 "oos":np.array([day["date"] < "2025-09-24" for day in base_curve])}
        summary["attribution"][regime] = {}
        summary["low_exposure"][regime] = {"baseline_low_days":int(low.sum()),"variants":{}}
        for row in primary:
            if [day["date"] for day in row["curve"]] != [day["date"] for day in base_curve]:
                raise AssertionError("Variant dates differ; attribution requires matched days")
            summary["attribution"][regime][row["name"]] = {
                span:attribution(row["curve"],mask) for span,mask in spans.items()}
            gross = np.array([day["gross"] for day in row["curve"]])
            summary["low_exposure"][regime]["variants"][row["name"]] = {
                "gross_mean_on_baseline_below20_days":float(gross[low].mean()) if low.any() else None,
                "gross_median_on_baseline_below20_days":float(np.median(gross[low])) if low.any() else None,
                "fraction_still_below20_on_baseline_low_days":float(np.mean(gross[low] < 0.2)) if low.any() else None,
                "overall_fraction_below20":row["full"]["gross_below_020"],
            }
        logs = [np.log1p([day["ret"] for day in row["curve"]]) for row in primary]
        unique, duplicate_of = [],{}
        unique_names = []
        for name,series in zip(NAMES,logs):
            same = next((i for i,other in enumerate(unique) if np.allclose(series,other,atol=1e-12,rtol=0)),None)
            if same is not None:
                duplicate_of[name] = unique_names[same]
            else:
                unique.append(series)
                unique_names.append(name)
        diagnostics = {"pbo_unique_books":robustness.pbo(np.array(unique).T) if len(unique)>1 and not QUICK else None,
                       "skipped_for_user_wrapup":QUICK,
                       "unique_books":unique_names,"duplicate_books":duplicate_of,"variants":{},"paired":{}}
        recorded_trials,trial_sharpes = robustness.sweep_trials(ROOT/"state")
        # RESEARCH already documented 204 trials BEFORE later rounds. This is a
        # lower bound, not an assertion that the full search history is known.
        trial_count = max(204,recorded_trials)+4
        for row,series in ([] if QUICK else zip(primary,logs)):
            diagnostics["variants"][row["name"]] = {
                "sharpe_ci95_block40":robustness.block_bootstrap_ci(series,block=40,n=2000,seed=20260912),
                "deflated_lower_bound_trial_count":robustness.deflated_sharpe(series,trial_count,trial_sharpes),
                "trial_count_note":"At least 204 historical trials documented; add four present alternatives. Incomplete, correlated trial history.",
                "best_quarter_share":robustness.best_quarter_share(row["curve"]),
                "quarterly":robustness.calendar(row["curve"])["quarterly"],
            }
        for name,series in ([] if QUICK else zip(NAMES[1:],logs[1:])):
            spans = {"full":np.ones(len(series),dtype=bool)}
            if regime == "recent":
                spans["oos"] = np.array([day["date"] < "2025-09-24" for day in base_curve])
            diagnostics["paired"][name] = {}
            for span,mask in spans.items():
                baseline,candidate = logs[0][mask],series[mask]
                diagnostics["paired"][name][span] = {
                    "observed_delta_sharpe":robustness.sharpe(candidate)-robustness.sharpe(baseline),
                    "bootstrap":[paired_blocks(baseline,candidate,block,2000,np.random.default_rng(20260912+block)) for block in (40,80)]}
        summary["diagnostics"][regime] = diagnostics
        prior_path = ROOT/f"state/backtest_sweep24_research_{'good' if regime=='recent' else 'pre2024'}_beta.json"
        old = next(row for row in read(prior_path)["results"] if row["name"] == "vol_target_050")
        new = find(result,"baseline",rate=0)["full"]
        summary["current_run_vs_prior"][regime] = {
            "prior_path":str(prior_path),"note":"Zero-financing cap costs; fresh common vendor snapshot, not byte-identical prior inputs.",
            "prior":{key:old[key] for key in ("total_return","sharpe","max_drawdown","avg_gross","turnover_per_day")},
            "current":{key:new[key] for key in ("total_return","sharpe","max_drawdown","gross_mean","turnover_per_day")}}
    (OUT/"summary.json").write_text(json.dumps(summary,indent=2,allow_nan=False),encoding="utf-8")
    passing = [name for name,status in summary["acceptance"].items() if status["material_pass"]]
    lines = ["# Higher-exposure research result — 2026-09-12", "",
             "## Decision", "",
             "The user explicitly chose to KEEP the current signal-sized/cash-holding structure. No exposure configuration change is authorized for this wrap-up; record and push research only.","",
             "Supported material candidates: "+(", ".join(passing) if passing else "NONE. Do not apply an exposure increase as an evidence-backed strategy upgrade.")+"", "",
             "This is not proof that every alternative is inferior. Tiny Sharpe gaps are inconclusive; a higher-return/higher-drawdown configuration can be a deliberate risk-preference choice without being a statistically supported upgrade. The declared screen and the user's separate capital-utilization question are reported independently.","",
             "All tables below use the beta-adjusted legacy ledgers, daily refits, next-open execution and one newly frozen common price snapshot. The primary financing scenario is 5% annual interest on positive borrowed exposure, charged for calendar days between opens. Cash yield is zero. Rates are sensitivity assumptions, not broker quotes.","",
             "## Primary results: cap-tier trading costs + 5% financing",""]
    for regime in ("recent","stress"):
        lines += [f"### {regime}","","| Variant | Return | Sharpe | Max DD | OOS Sharpe | Score | Turn/day | Mean gross | Mean borrowed | Mean positive cash |",
                  "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for name in NAMES:
            row = find(rows[regime],name); full = row["full"]
            lines.append(f"| {name} | {pct(full['total_return'])} | {full['sharpe']:.3f} | {p(full['max_drawdown'])} | {row['oos']['sharpe']:.3f} | {full['score']:.3f} | {p(full['turnover_per_day'])} | {p(full['gross_mean'])} | {p(full['average_borrowed'])} | {p(full['average_positive_cash'])} |")
        lines += ["",f"Signal dates: {full['start']}–{full['end']}; {full['days']} traded observations. SOXX same-period return: {pct(full['soxx_return'])}."+(" The entire stress regime falls before the OOS cutoff and uses only price/calendar opinions; it is not graph/LLM validation." if regime == "stress" else ""),""]
    lines += ["## Selected-name sleeve versus capital utilization (descriptive addendum)","",
              "Added after the fixed variants were declared in response to the user's clarification; no variants or adoption criteria changed. For each realized day, normalize the exact same held names and relative weights by that day's gross exposure. Sleeve returns below are before their own trading/financing costs and exclude zero-exposure dates. This is an attribution device, not a backtest of an investable fully deployed strategy. The account remains the actual fixed replay, with cap-tier costs and 5% financing.","",
              "| Regime / variant | Account net return | Unit-gross same-name sleeve before costs | SOXX on same active sleeve dates | Matched-gross SOXX, identical cost deduction | Mean gross / positive cash |",
              "|---|---:|---:|---:|---:|---:|"]
    for regime in ("recent","stress"):
        for name in NAMES:
            a=summary["attribution"][regime][name]["full"]
            lines.append(f"| {regime} / {name} | {pct(a['account_net']['compound_return'])} | {pct(a['sleeve_before_cost_active_days']['compound_return'])} | {pct(a['soxx_same_active_days']['compound_return'])} | {pct(a['matched_gross_soxx_identical_cost_deduction']['compound_return'])} | {p(a['gross_mean'])} / {p(a['positive_cash_mean'])} |")
    lines += ["","Matched-gross SOXX applies each variant's realized gross to the same next-open SOXX return and deducts the exact same account trading/financing amounts solely to isolate selection. These are not SOXX's own implementable transaction costs; before-cost results and OOS attribution are in summary.json. Compounded return differences are path-dependent and must not be added as causal components.","",
              "The exact DAILY arithmetic identity is: account − fully invested SOXX = gross × (sleeve − SOXX) + (gross − 1) × SOXX − trading − financing. The next table averages those terms in basis points/day; utilization is a drag in rising markets when underinvested but a benefit in falling markets, and can include leverage effects when gross exceeds 100%.","",
              "| Regime / variant / span | Days | Gross | Selection | Utilization | Trading | Financing | Account−SOXX |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for regime in ("recent","stress"):
        for span in ("full","baseline_below20_days"):
            for name in NAMES:
                a=summary["attribution"][regime][name][span]
                if a is None:
                    continue
                d=a["mean_daily_bps_decomposition"]
                lines.append(f"| {regime} / {name} / {span} | {a['days']} | {p(a['gross_mean'])} | "+" | ".join(f"{d[key]:+.2f}" for key in ("selection","capital_utilization","trading_cost","financing_cost","account_minus_full_soxx"))+" |")
    lines += ["","The low-exposure rows select exactly the dates on which the baseline deployed less than 20%; all alternatives use those same dates, including zero-exposure dates. This is a conditional diagnostic, not a continuous trading performance period. A sleeve's favorable historical returns do not validate its edge in production: the actual PAPER account has only two sessions, and these backtests are reused, survivorship-biased research. Low live deployment and historical average exposure are different questions.",""]
    lines += ["## Actual exposure, rather than allowed leverage",""]
    for regime in ("recent","stress"):
        lines += [f"### {regime}","","| Variant | Gross p05 / median / p95 / max | Below 20% | At least 180% | Mean gross on baseline <20% days | Last simulated gross | Ceiling binds | Post-band above ceiling |",
                  "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for name in NAMES:
            full = find(rows[regime],name)["full"]; quant = full["gross_quantiles"]
            low = summary["low_exposure"][regime]["variants"][name]
            lines.append(f"| {name} | {' / '.join(p(quant[str(q)] ) for q in (0.05,0.5,0.95,1))} | {p(full['gross_below_020'])} | {p(full['gross_at_least_180'])} | {p(low['gross_mean_on_baseline_below20_days'])} | {p(full['last_gross'])} | {p(full['ceiling_binding_fraction'])} | {p(full['postband_above_ceiling_fraction'])} |")
        lines += [""]
    lines += ["The rank comparator is up to 15 positive names with a 5% pre-control per-name floor. It is not a guarantee of 75%, 100% or 200% invested. The gross ceiling is applied before volatility scaling and the existing rebalance band; post-band overshoots shown here are an inherited simulator limitation, not authorized broker leverage.","",
              "## Uniform 30-bps trading-cost stress + 5% financing", "",
              "| Variant | Recent return / Sharpe / DD | Recent OOS Sharpe | Stress return / Sharpe / DD |",
              "|---|---:|---:|---:|"]
    for name in NAMES:
        recent,stress = find(rows["recent"],name,"flat30"),find(rows["stress"],name,"flat30")
        rf,sf = recent["full"],stress["full"]
        lines.append(f"| {name} | {pct(rf['total_return'])} / {rf['sharpe']:.3f} / {p(rf['max_drawdown'])} | {recent['oos']['sharpe']:.3f} | {pct(sf['total_return'])} / {sf['sharpe']:.3f} / {p(sf['max_drawdown'])} |")
    lines += ["","## Financing sensitivity at cap-tier trading costs", "",
              "| Regime / variant | 0% return / Sharpe | 5% return / Sharpe | 10% return / Sharpe |",
              "|---|---:|---:|---:|"]
    for regime in ("recent","stress"):
        for name in NAMES:
            pieces=[]
            for rate in (0,0.05,0.10):
                full=find(rows[regime],name,rate=rate)["full"]
                pieces.append(f"{pct(full['total_return'])} / {full['sharpe']:.3f}")
            lines.append(f"| {regime} / {name} | "+" | ".join(pieces)+" |")
    lines += ["","Financing feeds back into the book's trailing volatility and future targets; these are full replay sensitivities, not costs subtracted from a frozen final return. Neither short financing nor margin-call behavior is modeled because the compared books are long-only.","",
              "## Existing improvement criteria", ""]
    for name,status in summary["acceptance"].items():
        lines.append(f"- {name}: minimum repository screen {'PASS' if status['minimum_pass'] else 'FAIL'}; material/noise/risk screen {'PASS' if status['material_pass'] else 'FAIL'}. Failed material conditions: {', '.join(status['failed_material']) or 'none'}.")
    lines += ["","The minimum screen requires higher recent OOS Sharpe, nonlower full Sharpe and nonlower repository score. The material screen additionally requires >0.15 full/OOS Sharpe improvement, DD within +2 percentage points, at least 80% of baseline cumulative return, and no lower stress return/Sharpe. All comparisons have identical financing/trading assumptions.","",
              "## Reused-data diagnostics", ""]
    for regime in ("recent","stress"):
        diagnostics=summary["diagnostics"][regime]
        if diagnostics["skipped_for_user_wrapup"]:
            lines.append(f"- {regime}: additional bootstrap/PBO/DSR diagnostics NOT RUN at the user's immediate wrap-up request. All30 fixed scenarios, accounting attribution and six reference-parity checks are complete. Run analyzer without --quick to complete the optional diagnostic phase from existing local curves.")
            continue
        lines.append(f"- {regime}: PBO {json.dumps(diagnostics['pbo_unique_books'])}; duplicate books {json.dumps(diagnostics['duplicate_books'])}.")
        for name in NAMES:
            diagnostic=diagnostics["variants"][name]
            lines.append(f"  - {name}: Sharpe 95% block-40 interval {diagnostic['sharpe_ci95_block40']}; best-quarter log-return share {diagnostic['best_quarter_share']}; lower-bound-trial DSR {diagnostic['deflated_lower_bound_trial_count']}.")
        for name in NAMES[1:]:
            intervals=diagnostics["paired"][name]["full"]["bootstrap"]
            lines.append(f"  - Paired {name} minus baseline full Sharpe: "+"; ".join(f"{item['block_days']}d 95% {item['delta_sharpe_ci95']}" for item in intervals)+".")
    lines += ["","At least 204 earlier trials are documented, plus four present alternatives. The full trial history is incomplete and correlated. PBO, deflated Sharpe and 2,000-draw paired 40/80-day block intervals are diagnostics, not significance or fresh out-of-sample evidence. "+("They were not generated in this quick wrap-up run; the summary explicitly records the skipped phase." if QUICK else "Detailed OOS intervals and quarter contributions are in summary.json."),"",
              "## Snapshot, parity and limitations", ""]
    for regime in ("recent","stress"):
        comparison=summary["current_run_vs_prior"][regime]
        lines.append(f"- {regime} zero-financing baseline: prior return {pct(comparison['prior']['total_return'])}, Sharpe {comparison['prior']['sharpe']:.3f}; current snapshot {pct(comparison['current']['total_return'])}, Sharpe {comparison['current']['sharpe']:.3f}.")
        checks=[row for row in rows[regime] if row["parity"]]
        lines.append(f"- {regime}: {len(checks)} zero-financing parity checks against unchanged sweep.simulate passed, including every variant at cap costs and baseline at 30 bps; all daily rounded log returns match. Source ledger SHA-256 preserved: {raw[regime]['identity']['ledger_sha256']}.")
    manifest=read(OUT/"price_manifest_complete.json")
    lines += [f"- Frozen adjusted-price snapshot SHA-256: {manifest['final_sha256']}. Original round24 frames were not saved. PLAB's initial parallel-download cache-lock failure was retried alone before any result run; the original partial download is retained and every simulation uses the complete snapshot.",
              "- Same current market-cap tier snapshot and same seven-feature replay roster for all variants. The stress ledger speaks with five price/calendar agents; graph history starts much later. Universe survivorship and reused OOS periods remain limitations.",
              "- Simulator keeps target weights rather than explicitly drifting shares, treats missing-price positions as zero return, allows pre-vol/band gross-ceiling overshoot, and omits impact, partial fills, broker buying-power constraints, intraday margin calls and live-account startup differences. The 50% target only scales down after 20 returns; it does not lever exposure up.",
              "- Six standalone financing/sizing/attribution accounting tests pass. No operational defaults, ledgers, orders, schedules, LLM calls or dashboard publications were changed. The parent owns any integration decision.","",
              "## Current saved-opinion diagnostic (separate, supplied by parent)","",
              "Using 1,136 saved opinions from 2026-09-11 and freshly fitted models, parent measured beta baseline intended gross 27.67% in four names and size0.8 gross 36.90%; changing the gross ceiling alone left 27.67% unchanged. Raw model was 7.90% in one name. These are reference targets at $1,006,860.73 equity, without account-vol scaling, guardian exclusions, rebalance bands or execution—not fresh next-cycle signals, actual holdings, forecast returns, or orders. The beta activation itself changes the comparison from the original 7.6% holdings question.","",
              "## Reproduce", "", "```powershell", "# From the isolated semiband-experiment directory; frozen prices already exist.",
              "& 'C:\\Users\\calif\\AppData\\Local\\Python\\bin\\python.exe' -X utf8 research_higher_exposure_20260912.py --regime recent",
              "& 'C:\\Users\\calif\\AppData\\Local\\Python\\bin\\python.exe' -X utf8 research_higher_exposure_20260912.py --regime stress",
              "& 'C:\\Users\\calif\\AppData\\Local\\Python\\bin\\python.exe' -X utf8 outputs/higher_exposure_20260912/analyze_results.py", "```",""]
    (OUT/"report.md").write_text("\n".join(lines),encoding="utf-8")
    write_handoff(summary,rows)
    print(json.dumps({"supported_material_candidates":passing,"acceptance":summary["acceptance"],
                      "report":str(OUT/"report.md")},indent=2))


if __name__ == "__main__":
    main()
