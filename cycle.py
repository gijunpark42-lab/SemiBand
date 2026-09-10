"""One daily cycle of the self-weighting ensemble. Scheduled at 05:50 PT on
trading days (Task Scheduler "SemiBand-Cycle"): signals are computed before
the open, orders go out right after 09:30 ET. Safe to run by hand with --dry-run.

    python cycle.py                 the real thing (waits for the open, sends paper orders)
    python cycle.py --dry-run       no orders, no waiting; still writes predictions + dashboard
    python cycle.py --no-llm        only the seven free rule agents
    python cycle.py --force         trade even if foreign (non-sb2) orders were seen in 24h
    python cycle.py --tickers NVDA,AMD   restrict the universe (testing)

Steps: fresh-start liquidation if state/liquidate_pending exists -> foreign-order
guard -> universe -> closes -> score matured predictions + refit the stacking model -> run
agents -> combine -> wait for the open -> targets -> orders -> moderator minutes
-> journal + dashboard.
"""
import argparse
import importlib
import json
import logging
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import broker
import config
import ensemble
import journal
import learner
import ledger
import liquidate
import market
import portfolio
import score
import universe as universe_mod
from agents import moderator

ET = ZoneInfo("America/New_York")
LIQUIDATE_MARKER = config.STATE_DIR / "liquidate_pending"
log = logging.getLogger("cycle")


def wait_for_open(max_minutes=45):
    deadline = time.time() + max_minutes * 60
    while time.time() < deadline:
        c = broker.clock()
        if c.is_open:
            return True
        log.info("market closed; next open %s — waiting", c.next_open)
        time.sleep(30)
    return False


def _run_agent(name, universe, ctx):
    mod = importlib.import_module(f"agents.{name}")
    t0 = time.time()
    try:
        out = mod.run(universe, ctx)
    except Exception as exc:  # one broken agent must not stop the others
        log.exception("agent %s failed: %s", name, exc)
        out = []
    log.info("agent %-13s %3d signals in %4.0fs (%d tickers)", name, len(out), time.time() - t0, len(universe))
    return out


def run_agents(universe, ctx, model, held, use_llm):
    """Free agents see the whole universe; LLM agents (one claude -p call per
    ticker each) only the names the free agents rank highest plus what we hold,
    capped by config.LLM_MAX_TICKERS. This keeps a cycle to ~1/3 of the calls."""
    free = [a for a in config.AGENTS if not a.startswith("llm_")]
    llm_agents = [a for a in config.AGENTS if a.startswith("llm_")]
    signals = []
    for name in free:
        signals += _run_agent(name, universe, ctx)
    if not use_llm or not llm_agents:
        return signals
    prelim, _ = learner.predict(signals, model)
    ranked = sorted(prelim, key=lambda t: -abs(prelim[t]))
    keep = set(ranked[:config.LLM_MAX_TICKERS]) | (set(held) & set(universe))
    order = [t for t in universe if t in held] + [t for t in ranked if t in keep and t not in held]
    subset = {t: universe[t] for t in order}          # holdings first, then by prelim |conviction|
    for name in llm_agents:
        signals += _run_agent(name, subset, ctx)
    return signals


def guardian_blocked(today):
    """Names the intraday guardian exited within GUARDIAN_COOLDOWN_DAYS (state/guardian_exits.json)."""
    path = config.STATE_DIR / "guardian_exits.json"
    if not path.exists():
        return set()
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return set()
    from datetime import date, timedelta
    cutoff = (date.fromisoformat(today) - timedelta(days=config.GUARDIAN_COOLDOWN_DAYS)).isoformat()
    return {r["ticker"] for r in rows if r.get("date", "") >= cutoff}


def reason_line(conv, per_agent):
    parts = [f"conv {conv:+.2f}"]
    for a, s in per_agent.items():
        parts.append(f"{a} {s['direction']:+.2f}x{s['confidence']:.2f}")
    return " | ".join(parts)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-llm", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--tickers", default="")
    args = p.parse_args()
    dry = args.dry_run or config.DRY_RUN

    config.STATE_DIR.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout),
                                  logging.FileHandler(config.STATE_DIR / "cycle.log", encoding="utf-8")])
    for noisy in ("primp", "ddgs", "ddgs.ddgs", "httpx", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    today = datetime.now(ET).date().isoformat()
    notes = []
    log.info("=== cycle %s dry_run=%s llm=%s ===", today, dry, not args.no_llm)

    # Signals are computed before the open (yesterday's closes, today's news and
    # fundamentals are all available); the wait for the open happens right
    # before orders go out, so orders hit the tape at 09:30 ET, not 40 min later.
    if LIQUIDATE_MARKER.exists():
        n = liquidate.run(dry_run=dry)
        notes.append(f"fresh start: liquidated {n} positions")
        if not dry:
            LIQUIDATE_MARKER.unlink()

    foreign = broker.foreign_orders(24)
    if foreign:
        syms = sorted({o.symbol for o in foreign})
        msg = f"{len(foreign)} foreign orders in 24h ({', '.join(syms[:8])}) — another bot is trading this account"
        log.warning(msg)
        notes.append(msg)
        if not args.force and not dry:
            journal.publish_dashboard({"date": today, "notes": notes + ["cycle aborted: stop the other bot or run with --force"],
                                       "weights": ledger.latest_weights() or ensemble.initial_weights()})
            return 2

    universe = universe_mod.load()
    if args.tickers:
        keep = {t.strip().upper() for t in args.tickers.split(",")}
        universe = {t: c for t, c in universe.items() if t in keep}
    log.info("universe: %d tickers", len(universe))

    closes = market.closes(list(universe) + [config.BENCHMARK])
    last_close = {t: float(closes[t].dropna().iloc[-1]) for t in universe if t in closes.columns and closes[t].dropna().size}

    weights, scored, model, weights_hedge = score.run(closes, today)
    if scored:
        notes.append("scored " + ", ".join(f"{a} {n}" for a, n in scored.items()))
    log.info("effective weights: %s", weights)

    positions = broker.positions()

    ctx = {"closes": closes, "today": today}
    signals = run_agents(universe, ctx, model, positions, use_llm=not args.no_llm)
    ledger.add_predictions(today, signals, last_close)
    convictions, breakdown = learner.predict(signals, model)
    if config.DEMEAN_CONVICTION and convictions:
        mean_conv = sum(convictions.values()) / len(convictions)
        convictions = {t: c - mean_conv for t, c in convictions.items()}
        notes.append(f"convictions demeaned by {mean_conv:+.3f}")

    if not dry and not wait_for_open(max_minutes=120):
        log.info("market did not open (holiday?) — predictions recorded, no orders")
        journal.publish_dashboard({"date": today, "weights": weights,
                                   "notes": notes + ["market did not open: predictions recorded, no orders"]})
        return 0

    acct = broker.account()          # fresh numbers at the open
    equity, cash = float(acct.equity), float(acct.cash)
    buying_power = float(acct.buying_power)
    positions = broker.positions()
    blocked = guardian_blocked(today)
    if blocked:
        notes.append("guardian cooldown (no rebuy): " + ", ".join(sorted(blocked)))
        convictions_for_sizing = {t: c for t, c in convictions.items() if t not in blocked}
    else:
        convictions_for_sizing = convictions
    target_usd = portfolio.targets(convictions_for_sizing, equity)
    orders = portfolio.plan(target_usd, positions, convictions, universe, equity, buying_power)
    log.info("equity $%.0f cash $%.0f buying power $%.0f positions %d targets %d orders %d",
             equity, cash, buying_power, len(positions), len(target_usd), len(orders))

    # Execution: exits in full now; buys and trims spread over EXECUTION_SLICES slices
    # (first slice now, the rest every EXECUTION_INTERVAL_MIN minutes after the
    # dashboard is published) so we do not pay the whole opening spread at once.
    slices = 1 if dry else max(1, config.EXECUTION_SLICES)
    done, later = [], []
    for o in orders:
        t = o["ticker"]
        reason = reason_line(convictions.get(t, 0.0), breakdown.get(t, {})) + f" | {o['tag']}"
        coid = f"{config.ORDER_PREFIX}{today}-{t}-{o['side'].lower()}"
        try:
            if o["side"] == "BUY":
                broker.buy(t, round(o["notional"] / slices, 2), coid + "-1", dry_run=dry)
                size = o["notional"]
            elif o["notional"] is None:
                broker.close(t, dry_run=dry)
                size = float(positions[t].market_value) if t in positions else None
            else:
                broker.sell(t, round(o["notional"] / slices, 2), coid + "-1", dry_run=dry)
                size = o["notional"]
        except Exception as exc:
            log.error("order %s %s failed: %s", o["side"], t, exc)
            notes.append(f"order {o['side']} {t} failed: {exc}")
            continue
        if o["notional"] is not None and slices > 1:
            later.append((t, o["side"], round(o["notional"] / slices, 2), coid))
        journal.record(t, o["side"], reason + (f" | {slices} slices over {(slices - 1) * config.EXECUTION_INTERVAL_MIN} min" if slices > 1 else ""),
                       last_close.get(t), notional=size, dry_run=dry)
        ledger.add_order(today, t, o["side"], size, reason, coid, dry)
        est_cost = round((size or 0.0) * config.COST_BPS / 10_000, 2)
        done.append({"ticker": t, "side": o["side"], "notional": size, "reason": reason, "est_cost_usd": est_cost})

    if done:
        notes.append(f"estimated trading cost this cycle ${sum(d['est_cost_usd'] for d in done):,.0f} "
                     f"({config.COST_BPS} bps per order; commission $0)")
    ledger.add_cycle(today, equity, cash, len(positions), len(done), "; ".join(notes))
    ranked = sorted(convictions.items(), key=lambda kv: -abs(kv[1]))

    # Decision records: for every order, exactly how the number was reached.
    decisions = []
    for d in done:
        t = d["ticker"]
        per_agent = breakdown.get(t, {})
        decisions.append({
            "ticker": t, "side": d["side"], "notional": d["notional"], "est_cost_usd": d["est_cost_usd"],
            "conviction": round(convictions.get(t, 0.0), 3),
            "target_usd": target_usd.get(t),
            "held_before_usd": float(positions[t].market_value) if t in positions else 0.0,
            "agents": {a: {**s, "weight": round(weights.get(a, 0), 3)} for a, s in per_agent.items()},
            "rule": (f"conviction = Bayesian ridge stacking of the agents' direction x confidence (prior = equal blend; "
                     f"weights refit daily from scored predictions, may go negative = contrarian); "
                     f"enter >= {config.MIN_CONVICTION}, exit < {config.MIN_CONVICTION}, top {config.TOP_N}; "
                     f"size = conviction x {config.SIZE_PER_CONVICTION:.0%} of equity (so weak convictions stay small and cash is fine), "
                     f"cap {config.MAX_POSITION_PCT:.0%} of equity, {config.GROSS_TARGET:.0%} gross, within buying power; "
                     f"held names resized only when the target moves > {config.REBALANCE_BAND:.0%}; "
                     f"cost assumed {config.COST_BPS} bps per order"),
        })
    if decisions and not args.no_llm:
        moderator.run(decisions)          # meeting minutes per traded ticker (explains, never changes)
    history = []
    if journal.DASHBOARD_FILE.exists():
        try:
            history = json.loads(journal.DASHBOARD_FILE.read_text(encoding="utf-8")).get("history") or []
        except ValueError:
            history = []
    history = [h for h in history if h.get("date") != today]
    history.append({"date": today, "dry_run": dry, "weights": weights, "notes": notes, "decisions": decisions})
    history = history[-30:]

    backtest = None
    bt_path = config.STATE_DIR / "backtest_report.json"
    if bt_path.exists():
        try:
            bt = json.loads(bt_path.read_text(encoding="utf-8"))
            curve = bt.get("curve") or []
            step = max(1, len(curve) // 120)
            bt["curve"] = curve[::step] + ([curve[-1]] if curve and (len(curve) - 1) % step else [])
            backtest = bt
        except ValueError:
            backtest = None
    journal.publish_dashboard({
        "backtest": backtest,
        "benchmarks": market.benchmarks(),
        "history": history,
        "decisions": decisions,
        "date": today,
        "dry_run": dry,
        "equity": equity,
        "cash": cash,
        "universe_size": len(universe),
        "weights": weights,
        "weights_hedge": weights_hedge,
        "model": {h: {k: v.get(k) for k in ("n_obs", "n_dates", "lambda", "scale", "cv_ic", "reliability", "agent_ic")}
                  for h, v in model["horizons"].items()},
        "weights_history": ledger.weights_history(),
        "scoreboard": ledger.scoreboard(),
        "convictions": [{"ticker": t, "conviction": round(c, 3), "target_usd": target_usd.get(t),
                         "agents": breakdown.get(t, {})} for t, c in ranked[:60]],
        "orders": done,
        "notes": notes,
    })
    for k in range(2, slices + 1):
        if not later:
            break
        log.info("execution slice %d/%d in %d min", k, slices, config.EXECUTION_INTERVAL_MIN)
        time.sleep(config.EXECUTION_INTERVAL_MIN * 60)
        for t, side, part, coid in later:
            try:
                (broker.buy if side == "BUY" else broker.sell)(t, part, f"{coid}-{k}", dry_run=dry)
            except Exception as exc:
                log.error("slice %d %s %s failed: %s", k, side, t, exc)
    log.info("done: %d orders; top: %s", len(done),
             ", ".join(f"{t} {c:+.2f}" for t, c in ranked[:8]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
