"""Intraday guardian — hourly headline watch on current holdings.

The daily cycle decides what to own. This script only asks, once an hour
during the session, whether something NEW and material has happened to a
name we hold. It never buys.

  1. For each holding in the universe, pull today's headlines (Finnhub +
     DuckDuckGo) and keep only titles not seen before (state/guardian_seen.json).
  2. If there are new titles, one Claude call judges them: material? how
     severe? hold or exit? (schema below). No new titles -> no call.
  3. Exit only when the verdict is "exit" with severity >= GUARDIAN_EXIT_SEVERITY:
     close the position, journal it, record it in state/guardian_exits.json so
     the daily cycle does not rebuy it for GUARDIAN_COOLDOWN_DAYS.
  4. Every check is appended to the dashboard's `guardian` list (last 50).

Run:  python guardian.py            (scheduled hourly on weekdays by Task Scheduler)
      python guardian.py --dry-run  (judge, never trade)
"""
import argparse
import json
import logging
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

import broker
import config
import journal
import ledger
import market
import universe as universe_mod
from agents import llm

ET = ZoneInfo("America/New_York")
log = logging.getLogger("guardian")
SEEN = config.STATE_DIR / "guardian_seen.json"
EXITS = config.STATE_DIR / "guardian_exits.json"

SYSTEM = (
    "You are the risk officer of a long-only semiconductor portfolio. You are shown NEW headlines about a "
    "stock we currently hold. Decide whether they describe a material adverse event for the next 1-4 weeks: "
    "guidance cut, earnings miss, accounting or regulatory problem, lost major customer, supply disruption, "
    "dilutive financing, or similar. Routine coverage, price-move commentary, analyst chatter and old news "
    "are NOT material. Be conservative: exiting costs money and most headlines are noise."
)
SCHEMA = {
    "type": "object",
    "properties": {
        "material": {"type": "boolean"},
        "severity": {"type": "number", "minimum": 0, "maximum": 1, "description": "0 = nothing, 1 = thesis-breaking"},
        "action": {"type": "string", "enum": ["hold", "exit"]},
        "reason": {"type": "string", "description": "one sentence naming the headline and source"},
    },
    "required": ["material", "severity", "action", "reason"],
    "additionalProperties": False,
}


def _load(path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return default


def new_headlines(ticker, company, seen):
    items = market.finnhub_news(ticker, days=2, limit=20) + market.web_news(f"{company} {ticker}", limit=8, timelimit="d")
    fresh = []
    for it in items:
        key = it["title"].strip().lower()
        if key and key not in seen:
            fresh.append(it)
            seen.add(key)
    return fresh


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    dry = args.dry_run or config.DRY_RUN
    config.STATE_DIR.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout),
                                  logging.FileHandler(config.STATE_DIR / "guardian.log", encoding="utf-8")])
    for noisy in ("primp", "ddgs", "ddgs.ddgs", "httpx", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    now = datetime.now(ET)
    today = now.date().isoformat()
    if not dry and not broker.is_market_open():
        log.info("market closed — nothing to do")
        return 0

    universe = universe_mod.load()
    positions = {s: p for s, p in broker.positions().items() if s in universe}
    if not positions:
        log.info("no holdings")
        return 0
    seen_by = _load(SEEN, {})
    seen = set(seen_by.get(today, []))
    exits = _load(EXITS, [])
    events = []
    if not llm.ensure_server():
        log.error("local Claude server unavailable")
        return 1

    for ticker, pos in sorted(positions.items()):
        fresh = new_headlines(ticker, universe[ticker], seen)
        if not fresh:
            continue
        lines = "\n".join(f"- [{i.get('when') or '?'}] {i['title']} ({i.get('publisher') or '?'})"
                          + (f" — {i['snippet']}" if i.get("snippet") else "") for i in fresh)
        user = (f"Holding: {ticker} ({universe[ticker]}), position ${float(pos.market_value):,.0f}, "
                f"unrealized {float(pos.unrealized_plpc) * 100:+.1f}%.\nNew headlines since the last check:\n{lines}\n\n"
                "Judge as JSON.")
        try:
            v = llm.ask_json(SYSTEM, user, schema=SCHEMA)
        except Exception as exc:
            log.warning("%s: %s", ticker, exc)
            continue
        event = {"time": now.strftime("%Y-%m-%d %H:%M ET"), "ticker": ticker, "new_headlines": len(fresh),
                 "material": bool(v["material"]), "severity": round(float(v["severity"]), 2),
                 "action": v["action"], "reason": str(v["reason"])[:240], "executed": False}
        if v["action"] == "exit" and v["material"] and float(v["severity"]) >= config.GUARDIAN_EXIT_SEVERITY:
            try:
                broker.close(ticker, dry_run=dry)
                event["executed"] = not dry
                journal.record(ticker, "SELL", f"guardian exit: {event['reason']}", float(pos.current_price),
                               notional=float(pos.market_value), dry_run=dry)
                ledger.add_order(today, ticker, "SELL", float(pos.market_value), f"guardian exit: {event['reason']}",
                                 f"{config.ORDER_PREFIX}{today}-{ticker}-guardian", dry)
                exits.append({"date": today, "ticker": ticker, "reason": event["reason"]})
                log.warning("EXIT %s: %s", ticker, event["reason"])
            except Exception as exc:
                log.error("exit %s failed: %s", ticker, exc)
        else:
            log.info("%s: %d new headlines, %s (severity %.2f) — %s", ticker, len(fresh), v["action"], v["severity"], v["reason"])
        events.append(event)

    seen_by[today] = sorted(seen)
    SEEN.write_text(json.dumps({today: seen_by[today]}), encoding="utf-8")   # keep only today's memory
    EXITS.write_text(json.dumps(exits[-100:]), encoding="utf-8")
    dash = _load(journal.DASHBOARD_FILE, {})
    dash["guardian"] = (dash.get("guardian") or [])
    dash["guardian"].append({"time": now.strftime("%Y-%m-%d %H:%M ET"), "holdings": len(positions),
                             "checked": len(events), "events": events})
    dash["guardian"] = dash["guardian"][-50:]
    dash.pop("generated", None)
    journal.publish_dashboard(dash)
    log.info("checked %d holdings, %d with new headlines, %d exits", len(positions), len(events),
             sum(1 for e in events if e["executed"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
