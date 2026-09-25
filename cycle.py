"""One daily cycle of the self-weighting ensemble. Scheduled at 10:00 PT on
weekdays (Task Scheduler "SemiBand-Cycle"). Close mode (config.EXEC_MODE, live since
2026-09-21): signals during the session, the price agents refreshed 15 min before
the close, orders before the close (after hours if the cycle started too late);
open mode: orders right after 09:30 ET. Safe to run by hand with --dry-run.

    python cycle.py                 the real thing (waits for the open, sends paper orders)
    python cycle.py --dry-run       no orders, no waiting; still writes predictions + dashboard
    python cycle.py --no-llm        only the seven free rule agents
    python cycle.py --force         trade even if foreign (non-sb2) orders were seen in 24h
    python cycle.py --tickers NVDA,AMD   restrict the universe (testing)
    python cycle.py --reuse-signals      re-run a day from the signals already recorded today: no agent runs again, no Claude
                                         calls (same as creating state/reuse_signals before a scheduled run)

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
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import broker
import config
import ensemble
import journal
import learner
import ledger
import learning_targets
import liquidate
import market
import paper_twins
import portfolio
import score
import snapshots
import universe as universe_mod
from agents import graph_pit, llm, moderator
from agents.base import Signal
from agents.macro import EXTRA as MACRO_EXTRA

import pandas as pd

ET = ZoneInfo("America/New_York")
LIQUIDATE_MARKER = config.STATE_DIR / "liquidate_pending"
REUSE_MARKER = config.STATE_DIR / "reuse_signals"
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


def wait_until_et(hhmm, cutoff, today):
    """Close mode (round 48): sleep until `hhmm` ET on `today`; False when `cutoff` ET has already passed (no order may go out)."""
    target = pd.Timestamp(f"{today} {hhmm}", tz="America/New_York")
    last = pd.Timestamp(f"{today} {cutoff}", tz="America/New_York")
    now = pd.Timestamp.now(tz="America/New_York")
    if now >= last:
        return False
    if now < target:
        log.info("close mode: waiting until %s ET for the close refresh", hhmm)
        time.sleep((target - now).total_seconds())
    return True


def close_times(close_at):
    """(refresh, cutoff, prints_after) ET clock times for close mode, set before the session's close (a naive ET datetime:
    16:00, or 13:00 on half days) at the distances CLOSE_REFRESH_TIME, the order cutoff and 15:30 keep before 16:00."""
    def before_close(hhmm):
        h, m = map(int, hhmm.split(":"))
        return (close_at - timedelta(minutes=16 * 60 - (h * 60 + m))).strftime("%H:%M")
    cutoff = config.MOC_CUTOFF if config.CLOSE_ORDER_TYPE == "moc" else config.CLOSE_ORDER_CUTOFF
    return before_close(config.CLOSE_REFRESH_TIME), before_close(cutoff), before_close("15:30")


def extended_session_open(close_at):
    """2026-09-24: a cycle that missed the close window (the PC woke late) catches up in the extended session, until 30
    minutes before that session ends (4 h after the close: 20:00 ET, 17:00 on half days)."""
    if not config.AFTER_HOURS_CATCHUP:
        return False
    now = pd.Timestamp.now(tz="America/New_York").tz_localize(None)
    return now < pd.Timestamp(close_at) + pd.Timedelta(hours=3, minutes=30)


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
    capped by config.LLM_MAX_TICKERS (None = every name)."""
    roster = [*config.AGENTS, *config.SHADOW_AGENTS]   # shadow agents run and are recorded like the others; the learner never sees them
    free = [a for a in roster if not a.startswith("llm_")]
    llm_agents = sorted((a for a in roster if a.startswith("llm_")),
                        key=lambda a: config.LLM_ORDER.index(a) if a in config.LLM_ORDER else len(config.LLM_ORDER))   # news first
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
    deadline = config.LLM_STAGE_DEADLINE_CLOSE if config.EXEC_MODE == "close" else config.LLM_STAGE_DEADLINE   # round 48
    if deadline:      # no new Claude call after this ET time: the Claude stage must end before the execution window
        llm.DEADLINE = pd.Timestamp(f"{ctx['today']} {deadline}", tz="America/New_York").tz_convert("UTC").to_pydatetime()
    llm.timing_summary()                # start the stage's timings clean
    llm.STAGE_SKIPPED = 0
    llm.ensure_server()                 # 2026-09-22: warm and answering before the first call (a dead server lost 176 calls)
    try:
        for name in llm_agents:
            if llm.DEADLINE is not None and pd.Timestamp.now(tz="UTC") >= pd.Timestamp(llm.DEADLINE):
                log.warning("agent %-13s skipped: Claude stage deadline %s ET passed", name, deadline)
                out = []
            else:
                out = _run_agent(name, subset, ctx)
            if name in config.CARRY_FORWARD_AGENTS:                  # 2026-09-22 (user): a failed or skipped call keeps yesterday's view
                got = {s.ticker for s in out}
                carried = ledger.carried_signals(name, [t for t in subset if t not in got], ctx["today"], config.CARRY_FORWARD_SESSIONS)
                if carried:
                    log.info("agent %-13s carried %d signals from its last %d recorded sessions", name, len(carried), config.CARRY_FORWARD_SESSIONS)
                out += carried
            signals += out
            summary = llm.timing_summary()
            if summary:
                log.info("agent %-13s claude calls %d: end-to-end mean %.0fs, p90 %.0fs, max %.0fs, skipped by the deadline %d",
                         name, *summary)
    finally:
        llm.DEADLINE = None             # the moderator runs after the open and must not be refused
    return signals


def smooth_convictions(convictions, today, notes=None):
    """Round 52: conv = a x today + (1 - a) x the smoothed convictions of the last cycle date before `today`
    (state/conviction_ema.json), as the replay's --conviction-ema. Today's result is stored under today, so a same-day re-run
    (the close refresh) smooths against the same previous day. A name without a previous value keeps its own conviction; a
    previous day more than 7 calendar days back is not used."""
    a = config.CONVICTION_EMA
    if not a or not 0 < a < 1 or not convictions:
        return convictions
    path = config.STATE_DIR / "conviction_ema.json"
    try:
        hist = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        hist = {}
    earlier = sorted(d for d in hist if d < today)
    prev_day = earlier[-1] if earlier and (date.fromisoformat(today) - date.fromisoformat(earlier[-1])).days <= 7 else None
    prev = hist[prev_day] if prev_day else {}
    out = {t: a * c + (1 - a) * prev.get(t, c) for t, c in convictions.items()}
    hist[today] = out
    path.write_text(json.dumps({d: hist[d] for d in sorted(hist)[-5:]}), encoding="utf-8")
    if notes is not None:
        notes.append(f"convictions smoothed (EMA {a}) with {prev_day}'s" if prev_day else f"conviction EMA {a}: no previous day, unsmoothed")
    return out


def convict(signals, model, shadow_model, notes=None, groups=None, today=None):
    """Convictions from the active model, its breakdown, and the shadow model's convictions (demeaned when configured;
    groups = {ticker: group} demeans within DEMEAN_GROUP groups, round 39). With `today`, the active convictions are
    smoothed before demeaning (round 52, config.CONVICTION_EMA)."""
    convictions, breakdown = learner.predict(signals, model)
    if today:
        convictions = smooth_convictions(convictions, today, notes)
    shadow_convictions, _ = learner.predict(signals, shadow_model) if shadow_model else ({}, {})
    if config.DEMEAN_CONVICTION and convictions:
        convictions, means = learner.demean(convictions, groups, config.DEMEAN_GROUP_MIN)
        if notes is not None:
            if "all" in means:
                notes.append(f"convictions demeaned by {means['all']:+.3f}")
            else:
                notes.append("convictions demeaned by " + ", ".join(f"{g} {m:+.3f}" for g, m in sorted(means.items())))
    if config.DEMEAN_CONVICTION and shadow_convictions:
        shadow_convictions, _ = learner.demean(shadow_convictions, groups, config.DEMEAN_GROUP_MIN)
    return convictions, breakdown, shadow_convictions


def open_refresh(universe, signals, today, betas, notes, at="09:30"):
    """Right after the open: add today's first trades as a price row and re-run config.OPEN_REFRESH_AGENTS, so an
    overnight gap reaches the price-based signals the way it reaches the fills. Every other signal (Claude included)
    stays as computed before the open. An agent that returns nothing keeps its pre-open signals. The refreshed agents'
    predictions for today replace the pre-open ones in the ledger. -> (signals, {symbol: live price}); {} = unchanged."""
    names = [a for a in config.OPEN_REFRESH_AGENTS if a in config.AGENTS or a in config.SHADOW_AGENTS]
    open_utc = pd.Timestamp(f"{today} {at}", tz="America/New_York").tz_convert("UTC")   # close mode passes 15:30: prints after it are today's latest
    wait = (open_utc + pd.Timedelta(seconds=30) - pd.Timestamp.now(tz="UTC")).total_seconds()
    if names and 0 < wait <= 60:
        time.sleep(wait)                                # let the opening prints land before reading them
    live = market.live_prices(list(universe) + [config.BENCHMARK, "SPY"], prefer_after=open_utc) if names else {}
    if not live:
        if names:
            log.warning("open refresh skipped: no live prices")
        return signals, {}
    base = market.closes(list(universe) + [config.BENCHMARK] + MACRO_EXTRA)
    base = base.loc[base.index < pd.Timestamp(today)]
    row = base.ffill().iloc[-1].copy()               # last close everywhere, replaced where a print from today exists
    for symbol, price in live.items():
        if symbol in row.index:
            row[symbol] = price
    for symbol, level in market.index_levels([s for s in MACRO_EXTRA if s.startswith("^")]).items():   # VIX, 10y yield now
        last_close = row.get(symbol)
        if symbol in row.index and pd.notna(last_close) and last_close > 0 and 1 / 3 <= level / last_close <= 3:   # units only: VIX spikes pass
            row[symbol] = level
        elif symbol in row.index:
            log.warning("open refresh: %s level %.3f is not on the scale of its last close %s, kept the close", symbol, level, last_close)
    live_closes = base.copy()
    live_closes.loc[pd.Timestamp(today)] = row
    ctx = {"closes": live_closes, "today": today, "live_prices": live}
    fresh = {name: _run_agent(name, universe, ctx) for name in names}
    done = [name for name in names if fresh[name]]
    if not done:
        log.warning("open refresh: no agent produced signals, keeping the pre-open ones")
        return signals, {}
    price_at = {t: float(row[t]) for t in universe if t in row.index and pd.notna(row[t])}
    ledger.replace_predictions(today, done, [s for name in done for s in fresh[name]], price_at, betas)
    last = base[config.BENCHMARK].dropna()
    gap = live[config.BENCHMARK] / float(last.iloc[-1]) - 1 if config.BENCHMARK in live and len(last) else float("nan")
    msg = (f"{'open' if at == '09:30' else 'close'} refresh: {config.BENCHMARK} {gap:+.1%} vs last close; re-ran {', '.join(done)} on today's {'first' if at == '09:30' else 'latest'} trades "
           f"({len(live)} live prices)")
    log.info(msg)
    notes.append(msg)
    return [s for s in signals if s.agent not in done] + [s for name in done for s in fresh[name]], live


def _previous_history():
    """The published cycle history, so an early-exit dashboard payload does not wipe the site's decision history."""
    if not journal.DASHBOARD_FILE.exists():
        return []
    try:
        return json.loads(journal.DASHBOARD_FILE.read_text(encoding="utf-8")).get("history") or []
    except ValueError:
        return []


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


def keep_running():
    """2026-09-24: on battery with the lid closed the laptop still went into Modern Standby 10:07-11:50 PT and the cycle froze.
    Best effort on top of SetThreadExecutionState: a power request of types SystemRequired and ExecutionRequired (the
    latter keeps this process from being suspended in standby). Held until the process exits; a closed lid on battery can
    still win, which only a charger and the AC lid setting fix."""
    import ctypes

    class Reason(ctypes.Structure):     # REASON_CONTEXT, simple string
        _fields_ = [("Version", ctypes.c_ulong), ("Flags", ctypes.c_ulong), ("SimpleReasonString", ctypes.c_wchar_p)]

    k32 = ctypes.windll.kernel32
    k32.PowerCreateRequest.restype = ctypes.c_void_p
    k32.PowerCreateRequest.argtypes = [ctypes.POINTER(Reason)]
    k32.PowerSetRequest.argtypes = [ctypes.c_void_p, ctypes.c_int]
    handle = k32.PowerCreateRequest(ctypes.byref(Reason(0, 1, "SemiBand cycle")))
    if handle and handle != ctypes.c_void_p(-1).value:
        for kind in (1, 3):             # PowerRequestSystemRequired, PowerRequestExecutionRequired
            k32.PowerSetRequest(handle, kind)
    return handle


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-llm", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--tickers", default="")
    p.add_argument("--reuse-signals", action="store_true")
    args = p.parse_args()
    dry = args.dry_run or config.DRY_RUN

    config.STATE_DIR.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout),
                                  logging.FileHandler(config.STATE_DIR / "cycle.log", encoding="utf-8")])
    for noisy in ("primp", "ddgs", "ddgs.ddgs", "httpx", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    today = datetime.now(ET).date().isoformat()
    vol_label = f"{config.VOL_TARGET:.0%}" if config.VOL_TARGET is not None else "off"
    notes = [f"learner target mode: {config.LEARNER_TARGET_MODE}; portfolio vol target: {vol_label}"]
    log.info("=== cycle %s dry_run=%s llm=%s ===", today, dry, not args.no_llm)
    if sys.platform == "win32":         # 2026-09-22: the PC idled to sleep 11:37-11:55 PT mid-cycle; no idle sleep until this process
        import ctypes                   # exits (ES_CONTINUOUS | ES_SYSTEM_REQUIRED). A closed lid still sleeps the PC
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
        keep_running()

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
                                       "weights": ledger.latest_weights() or ensemble.initial_weights(),
                                       "history": _previous_history()})
            return 2

    snapshots.take()                 # dated copy of the earnings-ai graph whenever it changed (point-in-time backtests later)
    universe = universe_mod.load()
    if args.tickers:
        keep = {t.strip().upper() for t in args.tickers.split(",")}
        universe = {t: c for t, c in universe.items() if t in keep}
    log.info("universe: %d tickers", len(universe))

    closes = market.closes(list(universe) + [config.BENCHMARK])
    if config.EXEC_MODE == "close":                                   # round 48: the afternoon run must not see today's partial daily bar
        closes = closes.loc[closes.index < pd.Timestamp(today)]
    last_close = {t: float(closes[t].dropna().iloc[-1]) for t in universe if t in closes.columns and closes[t].dropna().size}

    reuse = args.reuse_signals or REUSE_MARKER.exists()
    recorded = ledger.predictions_on(today) if reuse else []
    model = learner.load() if recorded else None
    if model is not None:                # a re-run of a day already scored and fitted: keep that model
        weights = model.get("effective_weights") or learner.effective_weights(model)
        scored, weights_hedge = {}, ledger.latest_hedge_weights() or ensemble.initial_weights()
    else:
        weights, scored, model, weights_hedge = score.run(closes, today)
    if scored:
        notes.append("scored " + ", ".join(f"{a} {n}" for a, n in scored.items()))
    log.info("effective weights: %s", weights)

    positions = broker.positions()

    ctx = {"closes": closes, "today": today}
    if recorded:
        # Signals already recorded today by a stopped run: reuse them, so no agent and no Claude call runs twice.
        signals = [Signal(r["agent"], r["ticker"], r["direction"], r["confidence"], r["horizon"], r["reason"]) for r in recorded]
        prediction_betas = learning_targets.latest_betas(closes, {s.ticker for s in signals}, today)
        notes.append(f"reused {len(signals)} signals recorded earlier today (no agent re-run, no Claude calls)")
        log.info("reusing %d signals recorded earlier on %s", len(signals), today)
    else:
        if not args.no_llm:
            llm.ensure_server()           # 2026-09-22: warm the Claude server while the rule agents run
        signals = run_agents(universe, ctx, model, positions, use_llm=not args.no_llm)
        if llm.STAGE_SKIPPED:
            cut_at = config.LLM_STAGE_DEADLINE_CLOSE if config.EXEC_MODE == "close" else config.LLM_STAGE_DEADLINE
            notes.append(f"Claude stage cut at {cut_at} ET: {llm.STAGE_SKIPPED} calls skipped, rule agents carried the rest")
        prediction_betas = learning_targets.latest_betas(closes, {s.ticker for s in signals}, today)
        ledger.add_predictions(today, signals, last_close, prediction_betas)
    if reuse and not dry:
        REUSE_MARKER.unlink(missing_ok=True)
    shadow_mode = "raw" if config.LEARNER_TARGET_MODE == "beta" else "beta"
    shadow_model = learner.load(shadow_mode)
    groups = graph_pit.groups(universe) if config.DEMEAN_CONVICTION and config.DEMEAN_GROUP else None
    convictions, breakdown, shadow_convictions = convict(signals, model, shadow_model, notes, groups, today=today)

    # 240 minutes: the wait starts only after every agent has run, and a 03:30 PT start whose agents finish by 04:30 would
    # give up just before the 06:30 PT open with 120 (audit 2026-09-15; yesterday's run only traded after a relaunch)
    after_hours = False
    prints_after = "15:30" if config.EXEC_MODE == "close" else "09:30"
    if not dry and config.EXEC_MODE == "close":                        # round 48: the close refresh window instead of the open
        close_at = broker.session_close(today)
        if close_at is None:                                            # 2026-09-24: holidays (a DAY order would wait for the next open)
            log.info("close mode: the market does not open today — predictions recorded, no orders")
            journal.publish_dashboard({"date": today, "weights": weights, "history": _previous_history(),
                                       "notes": notes + ["market closed today: predictions recorded, no orders"]})
            return 0
        refresh_at, cutoff, prints_after = close_times(close_at)        # 15:45 / 15:55 ET; 12:45 / 12:55 on half days
        if not wait_until_et(refresh_at, cutoff, today):
            if not extended_session_open(close_at):
                log.info("close mode: past %s ET — predictions recorded, no orders", cutoff)
                journal.publish_dashboard({"date": today, "weights": weights, "history": _previous_history(),
                                           "notes": notes + [f"close mode: past {cutoff} ET, predictions recorded, no orders"]})
                return 0
            after_hours = True                                          # 2026-09-24: the PC woke late (09-21, 09-23); catch up
            log.info("close mode: past %s ET — catching up in the extended session with limit orders", cutoff)
            notes.append(f"close mode: past {cutoff} ET, caught up in the extended session (limit orders, whole shares)")
    elif not dry and not wait_for_open(max_minutes=240):
        log.info("market did not open (holiday?) — predictions recorded, no orders")
        journal.publish_dashboard({"date": today, "weights": weights, "history": _previous_history(),
                                   "notes": notes + ["market did not open: predictions recorded, no orders"]})
        return 0

    if config.OPEN_REFRESH_AGENTS:
        signals, live = open_refresh(universe, signals, today, prediction_betas, notes, at=prints_after)
        if live:
            convictions, breakdown, shadow_convictions = convict(signals, model, shadow_model, groups=groups, today=today)

    acct = broker.account()          # fresh numbers at the open
    equity, cash = float(acct.equity), float(acct.cash)
    buying_power = float(acct.buying_power)
    positions = broker.positions()
    blocked = guardian_blocked(today)
    if blocked:
        notes.append("guardian cooldown (no rebuy): " + ", ".join(sorted(blocked)))
        convictions_for_sizing = {t: c for t, c in convictions.items() if t not in blocked}
        shadow_for_sizing = {t: c for t, c in shadow_convictions.items() if t not in blocked}
    else:
        convictions_for_sizing = convictions
        shadow_for_sizing = shadow_convictions
    realized = broker.realized_vol(config.VOL_LOOKBACK_DAYS) if config.VOL_TARGET else None
    if realized is not None:
        scaled = realized > config.VOL_TARGET
        notes.append(f"realised vol {realized:.0%} ({config.VOL_LOOKBACK_DAYS}d) vs target {config.VOL_TARGET:.0%}: "
                     + (f"book scaled x{config.VOL_TARGET / realized:.2f}" if scaled else "no scaling"))
    target_usd = portfolio.targets(convictions_for_sizing, equity, realized_vol=realized)
    floor_usd = 0.0
    if config.BETA_FLOOR:                                                  # round 47: trend-gated beta floor through the sleeve ETF
        target_usd, floor_usd, why = portfolio.apply_beta_floor(target_usd, prediction_betas, equity, closes, realized)
        if why:
            notes.append(why)
    shadow_targets = portfolio.targets(shadow_for_sizing, equity, realized_vol=realized) if shadow_for_sizing else {}
    ledger.save_shadow_targets(today, config.LEARNER_TARGET_MODE, convictions, target_usd, last_close,
                               config.VOL_TARGET, active=True)
    ledger.save_shadow_targets(today, shadow_mode, shadow_convictions, shadow_targets, last_close,
                               config.VOL_TARGET, active=False)
    sleeve_orders, sleeve_proceeds = [], 0.0
    if config.IDLE_SLEEVE:
        sleeve_usd = portfolio.sleeve_target(target_usd, equity, closes, realized)
        if sleeve_usd is not None and floor_usd > sleeve_usd:               # round 47: the floor's sleeve replaces a smaller idle sleeve
            sleeve_usd = floor_usd
        sleeve_orders = [] if sleeve_usd is None else portfolio.plan_sleeve(sleeve_usd, positions)
        if sleeve_usd is None:
            notes.append(f"idle sleeve {config.IDLE_SLEEVE}: no usable closes, position left as is")
            sleeve_usd = 0.0
        if config.IDLE_SLEEVE in closes.columns and closes[config.IDLE_SLEEVE].dropna().size:
            last_close.setdefault(config.IDLE_SLEEVE, float(closes[config.IDLE_SLEEVE].dropna().iloc[-1]))   # trade record price
        notes.append(f"idle sleeve {config.IDLE_SLEEVE}: target ${sleeve_usd:,.0f}"
                     + ("" if sleeve_usd else " (off: below its trend average or no idle equity)"))
        # a sleeve sale goes out with the other sells, before the buys: count it in the stock book's buy budget, so a
        # re-entry day is not capped by a sleeve about to be sold (audit 2026-09-15; the sleeve can be ~100% of equity)
        sleeve_proceeds = sum((float(positions[o["ticker"]].market_value) if o["notional"] is None else o["notional"])
                              for o in sleeve_orders if o["side"] == "SELL" and (o["notional"] is not None or o["ticker"] in positions))
    twins_summary = {}
    try:                                                                  # paper twins (2026-09-18): counterfactual books, no orders
        twin_books = paper_twins.books(signals, model, shadow_model, groups, convictions_for_sizing, target_usd,
                                       (sleeve_usd if config.IDLE_SLEEVE else 0.0), equity, realized, closes, prediction_betas)
        paper_twins.record(today, twin_books, config.EXEC_MODE)
        paper_twins.mark(today, closes, market.official_opens)
        twins_summary = paper_twins.summary()
        notes.append("paper twins: " + paper_twins.note(twins_summary))
    except Exception as exc:
        log.warning("paper twins: %s", exc)
    orders = portfolio.plan(target_usd, positions, convictions, universe, equity, buying_power, extra_proceeds=sleeve_proceeds)
    fallback_buys = {}                # the buys sized without the sleeve's proceeds, used only if its sale fails at the broker
    if sleeve_proceeds > 0:
        fallback_buys = {o["ticker"]: o["notional"] for o in portfolio.plan(target_usd, positions, convictions, universe, equity, buying_power)
                         if o["side"] == "BUY"}
    if sleeve_orders:
        orders = ([o for o in orders if o["side"] == "SELL"] + [o for o in sleeve_orders if o["side"] == "SELL"]
                  + [o for o in orders if o["side"] == "BUY"] + [o for o in sleeve_orders if o["side"] == "BUY"])
    log.info("equity $%.0f cash $%.0f buying power $%.0f positions %d targets %d orders %d",
             equity, cash, buying_power, len(positions), len(target_usd), len(orders))

    # Execution: exits in full now; buys and trims spread over EXECUTION_SLICES slices
    # (first slice now, the rest every EXECUTION_INTERVAL_MIN minutes after the
    # dashboard is published) so we do not pay the whole opening spread at once.
    close_mode = config.EXEC_MODE == "close"                            # round 48: one slice at the close refresh
    moc = close_mode and config.CLOSE_ORDER_TYPE == "moc" and not after_hours   # 2026-09-22: paper fills MOC unreliably -> "market"
    slices = 1 if (dry or close_mode) else max(1, config.EXECUTION_SLICES)
    done, later = [], []
    sleeve_sell_failed = False
    for o in orders:
        t = o["ticker"]
        if o["side"] == "BUY" and sleeve_sell_failed and t in universe:   # never hold the sleeve AND the buys sized on its sale
            o = portfolio.without_sleeve_proceeds(o, fallback_buys)
            if o is None:
                notes.append(f"order BUY {t} skipped: the sleeve sale failed and the budget without it has no room")
                continue
        reason = reason_line(convictions.get(t, 0.0), breakdown.get(t, {})) + f" | {o['tag']}"
        coid = f"{config.ORDER_PREFIX}{today}-{t}-{o['side'].lower()}"
        try:
            if after_hours:                                             # 2026-09-24: extended session, whole-share limits only
                full = o["notional"] is None
                if full and t not in positions:
                    continue
                if o["side"] == "BUY" and done and not any(d["side"] == "BUY" for d in done):
                    time.sleep(20)                                      # the buys are sized on the sells' proceeds: let them fill
                broker.extended_limit(t, broker.OrderSide.BUY if o["side"] == "BUY" else broker.OrderSide.SELL,
                                      notional=None if full else round(o["notional"], 2),
                                      qty=float(positions[t].qty) if full else None, client_order_id=coid + "-ah", dry_run=dry)
                size = float(positions[t].market_value) if full else o["notional"]
                reason += " | extended-hours catch-up"
            elif o["side"] == "BUY":
                if moc:
                    broker.moc(t, round(o["notional"] / slices, 2), broker.OrderSide.BUY, coid + "-1", dry_run=dry)
                else:
                    broker.buy(t, round(o["notional"] / slices, 2), coid + "-1", dry_run=dry)
                size = o["notional"]
            elif o["notional"] is None:
                (broker.close_moc if moc else broker.close)(t, client_order_id=coid + "-1", dry_run=dry)
                size = float(positions[t].market_value) if t in positions else None
            else:
                if moc:
                    broker.moc(t, round(o["notional"] / slices, 2), broker.OrderSide.SELL, coid + "-1", dry_run=dry)
                else:
                    broker.sell(t, round(o["notional"] / slices, 2), coid + "-1", dry_run=dry)
                size = o["notional"]
        except Exception as exc:
            log.error("order %s %s failed: %s", o["side"], t, exc)
            notes.append(f"order {o['side']} {t} failed: {exc}")
            sleeve_sell_failed |= o["side"] == "SELL" and t == config.IDLE_SLEEVE
            continue
        if o["notional"] is not None and slices > 1:
            later.append((t, o["side"], round(o["notional"] / slices, 2), coid))
        journal.record(t, o["side"], reason + (f" | {slices} slices over {(slices - 1) * config.EXECUTION_INTERVAL_MIN} min" if slices > 1 else ""),
                       last_close.get(t), notional=size, dry_run=dry)
        ledger.add_order(today, t, o["side"], size, reason, coid, dry)
        est_cost = round((size or 0.0) * config.LIVE_COST_BPS / 10_000, 2)
        done.append({"ticker": t, "side": o["side"], "notional": size, "reason": reason, "est_cost_usd": est_cost})
    if not dry and done and close_mode and not moc and not after_hours:  # 2026-09-22: before the moderator's Claude calls (8 min on
        log.info("close mode: waiting %d min for limit fills before the market cleanup", config.CLOSE_CLEANUP_MIN)   # 09-22), so the
        time.sleep(config.CLOSE_CLEANUP_MIN * 60)                       # remainders go out as market orders before the 16:00 bell
        n = broker.cleanup_open_orders(config.ORDER_PREFIX, dry_run=dry)
        if n:
            notes.append(f"{n} limit remainders converted to market")

    # Regime hedge (v2.4): short config.HEDGE_SYMBOL by HEDGE_SIZE x equity while it closes below its HEDGE_LOOKBACK-day
    # average; flat otherwise. Scaled like the book when the vol target is active. One whole-share market order.
    if config.HEDGE_SIZE and config.HEDGE_SYMBOL in closes.columns:
        soxx = closes[config.HEDGE_SYMBOL].dropna()
        hedge_on = float(soxx.iloc[-1]) < float(soxx.iloc[-(config.HEDGE_LOOKBACK + 1):].mean())
        scale = min(1.0, config.VOL_TARGET / realized) if (config.VOL_TARGET and realized and realized > config.VOL_TARGET) else 1.0
        long_book = sum(float(p.market_value) for s, p in positions.items() if s in universe and float(p.market_value) > 0)
        long_after = long_book + sum(o["notional"] or 0.0 for o in orders if o["side"] == "BUY") - sum(
            (float(positions[o["ticker"]].market_value) if o["notional"] is None and o["ticker"] in positions else (o["notional"] or 0.0))
            for o in orders if o["side"] == "SELL")
        hedge_target = min(config.HEDGE_SIZE * equity * scale, max(long_after, 0.0)) if hedge_on else 0.0   # never a net short
        cur = positions.get(config.HEDGE_SYMBOL)
        cur_notional = -float(cur.market_value) if cur else 0.0
        if abs(hedge_target - cur_notional) >= config.REBALANCE_BAND * max(hedge_target, cur_notional, 1.0):
            try:
                delta = broker.hedge_to(config.HEDGE_SYMBOL, hedge_target, f"{config.ORDER_PREFIX}{today}-{config.HEDGE_SYMBOL}-hedge", dry_run=dry)
                side = "SELL" if delta < 0 else "BUY"
                why = (f"regime hedge: {config.HEDGE_SYMBOL} below its {config.HEDGE_LOOKBACK}-day average -> short {config.HEDGE_SIZE:.0%} of equity"
                       if hedge_on else f"regime hedge off: {config.HEDGE_SYMBOL} back above its {config.HEDGE_LOOKBACK}-day average -> cover")
                if delta:
                    journal.record(config.HEDGE_SYMBOL, side, why, float(soxx.iloc[-1]), notional=abs(hedge_target - cur_notional), dry_run=dry)
                    ledger.add_order(today, config.HEDGE_SYMBOL, side, abs(hedge_target - cur_notional), why, f"{config.ORDER_PREFIX}{today}-{config.HEDGE_SYMBOL}-hedge", dry)
                    done.append({"ticker": config.HEDGE_SYMBOL, "side": side, "notional": abs(hedge_target - cur_notional), "reason": why, "est_cost_usd": 0.0})
                notes.append(why)
            except Exception as exc:
                log.error("hedge order failed: %s", exc)
                notes.append(f"hedge order failed: {exc}")
        else:
            notes.append(f"regime hedge {'on' if hedge_on else 'off'} (unchanged)")

    if done:
        notes.append(f"estimated trading cost this cycle ${sum(d['est_cost_usd'] for d in done):,.0f} "
                     f"({config.LIVE_COST_BPS} bps per dollar traded, the measured live cost; commission $0)")
    ledger.add_cycle(today, equity, cash, len(positions), len(done), "; ".join(notes))
    ranked = sorted(convictions.items(), key=lambda kv: -kv[1])       # best longs first: with demeaned convictions about half are
                                                                       # negative, and |conv| would rank the most-avoided names on top

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
                     f"cost {config.LIVE_COST_BPS} bps per dollar traded (measured live)"),
        })
    if decisions and not args.no_llm:
        moderator.run([d for d in decisions if d["ticker"] in universe])   # minutes per traded stock; the idle sleeve has no agent debate
    history = []
    if journal.DASHBOARD_FILE.exists():
        try:
            history = json.loads(journal.DASHBOARD_FILE.read_text(encoding="utf-8")).get("history") or []
        except ValueError:
            history = []
    history = [h for h in history if h.get("date") != today]
    history.append({"date": today, "dry_run": dry, "target_mode": config.LEARNER_TARGET_MODE,
                    "weights": weights, "notes": notes, "decisions": decisions})
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
        "shadow_signals": {t: {s.agent: {"direction": round(s.direction, 3), "confidence": round(s.confidence, 3), "reason": s.reason[:200]}
                               for s in signals if s.ticker == t and s.agent in config.SHADOW_AGENTS}
                           for t in sorted({s.ticker for s in signals if s.agent in config.SHADOW_AGENTS})},
        "target_mode": config.LEARNER_TARGET_MODE,
        "shadow_target_mode": shadow_mode,
        "weights": weights,
        "weights_hedge": weights_hedge,
        "model": {h: {k: v.get(k) for k in ("n_obs", "n_dates", "lambda", "scale", "cv_ic", "reliability", "agent_ic")}
                  for h, v in model["horizons"].items()},
        "weights_history": ledger.weights_history(),
        "scoreboard": ledger.scoreboard(),
        "convictions": [{"ticker": t, "conviction": round(c, 3), "target_usd": target_usd.get(t),
                         "agents": breakdown.get(t, {})} for t, c in ranked[:60]],
        "orders": done,
        "twins": twins_summary,
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
    if not dry and done and not close_mode:                             # close mode cleaned up above (MOC: nothing to clean up)
        log.info("waiting %d min for limit fills before the market cleanup", config.LIMIT_CLEANUP_MIN)
        time.sleep(config.LIMIT_CLEANUP_MIN * 60)
        n = broker.cleanup_open_orders(config.ORDER_PREFIX, dry_run=dry)
        if n:
            notes.append(f"{n} limit remainders converted to market")
    log.info("done: %d orders; top: %s", len(done),
             ", ".join(f"{t} {c:+.2f}" for t, c in ranked[:8]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
