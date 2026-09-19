"""Realised cost of the live fills against the official 09:30 open (round 46 diagnostic, pre-registered 2026-09-17). The replay
charges COST_BPS per dollar traded at the open; this measures what the paper account actually paid on top of the open. The
pre-registered rule: adopt the conviction EMA (round 45 `_e5`) iff the notional-weighted adverse slippage of the open-window
fills is >= 18.5 bps per dollar traded. Read-only; run from the live checkout (the Alpaca keys):

    python -X utf8 slippage.py [--days 14]

Adverse slippage per fill = (fill - open) / open for buys and (open - fill) / open for sells, in bps, weighted by the filled
notional. Fills after 09:45 ET (guardian exits, limit clean-ups) are listed separately: they are not open executions.
Paper fills carry the quoted spread but no market impact, so the number is a floor for a real account.
"""
import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

import broker
import config

NY = ZoneInfo("America/New_York")
BARS = "https://data.alpaca.markets/v2/stocks/bars"
OPEN_WINDOW_END = (9, 45)
REFERENCE = "open"                              # or 'close' (round 48, close mode)
THRESHOLD_BPS = 18.5


def official_opens(symbols, start, end):
    """{(YYYY-MM-DD, symbol): open} from Alpaca's daily bars, unadjusted; SIP first, IEX for what SIP leaves out."""
    out = {}
    headers = {"APCA-API-KEY-ID": config.API_KEY, "APCA-API-SECRET-KEY": config.SECRET_KEY}
    for feed in ("sip", "iex"):
        todo = sorted(set(symbols))
        for i in range(0, len(todo), 100):
            params = {"symbols": ",".join(todo[i:i + 100]), "timeframe": "1Day", "start": start, "end": end,
                      "adjustment": "raw", "feed": feed, "limit": 10000}
            while True:
                try:
                    r = requests.get(BARS, headers=headers, params=params, timeout=30)
                    r.raise_for_status()
                except Exception as exc:                       # a feed the plan does not cover: try the next one
                    print(f"bars ({feed}): {exc}")
                    break
                body = r.json()
                for symbol, bars in (body.get("bars") or {}).items():
                    for b in bars:
                        key = (b["t"][:10], symbol)
                        ref = b.get("c") if REFERENCE == "close" else b.get("o")
                        if key not in out and ref:
                            out[key] = float(ref)
                token = body.get("next_page_token")
                if not token:
                    break
                params["page_token"] = token
    return out


def fills(days):
    """Filled orders of the account in the window: (date NY, time NY, symbol, side, qty, price, type, client id)."""
    rows = []
    for o in broker.recent_orders(hours=days * 24):
        qty, price = float(o.filled_qty or 0), float(o.filled_avg_price or 0)
        if qty <= 0 or price <= 0 or o.filled_at is None:
            continue
        when = o.filled_at.astimezone(NY)
        side = str(getattr(o.side, "value", o.side)).lower()
        kind = str(getattr(o.order_type, "value", o.order_type)).lower()
        rows.append((when.date().isoformat(), when.strftime("%H:%M"), o.symbol, side, qty, price, kind, o.client_order_id or ""))
    return sorted(rows)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--window", default="09:45", help="ET time that ends the open window (pre-registered 09:45; the second execution slice fills at ~09:47)")
    p.add_argument("--exclude", default="", help="comma list of symbols to leave out, e.g. SOXX (the idle sleeve trades in size)")
    p.add_argument("--reference", choices=("open", "close"), default="open", help="close: fills against the official close, window = fills from 15:30 ET (close mode)")
    args = p.parse_args()
    global OPEN_WINDOW_END, REFERENCE
    OPEN_WINDOW_END = (int(args.window[:2]), int(args.window[3:]))
    REFERENCE = args.reference
    if REFERENCE == "close":
        OPEN_WINDOW_END = (15, 29)                     # close mode: the auction fills (16:00) are the window; earlier fills are 'later'
    skip = {s for s in args.exclude.split(",") if s}
    rows = [r for r in fills(args.days) if r[2] not in skip]
    if not rows:
        print("no fills in the window")
        return
    start, end = rows[0][0], rows[-1][0]
    opens = official_opens({r[2] for r in rows}, start, end)
    groups = defaultdict(lambda: [0.0, 0.0, 0])           # key -> [adverse $ , notional $, fills]
    missing = 0
    for day, hhmm, symbol, side, qty, price, kind, cid in rows:
        o = opens.get((day, symbol))
        if not o:
            missing += 1
            continue
        adverse = (price - o) if side == "buy" else (o - price)
        hh, mm = int(hhmm[:2]), int(hhmm[3:])
        window = ("close" if (hh, mm) > OPEN_WINDOW_END else "later") if REFERENCE == "close" else ("open" if (hh, mm) <= OPEN_WINDOW_END else "later")
        for key in (("all", window), ("side", window, side), ("type", window, kind), ("day", window, day)):
            g = groups[key]
            g[0] += adverse * qty
            g[1] += price * qty
            g[2] += 1

    def bps(g):
        return 1e4 * g[0] / g[1] if g[1] else float("nan")

    print(f"{len(rows)} fills {start}..{end}, {missing} without an official open (skipped)")
    for window in (("close", "later") if REFERENCE == "close" else ("open", "later")):
        g = groups.get(("all", window))
        if not g:
            continue
        print(f"\n[{window}] {g[2]} fills, notional ${g[1]:,.0f}: adverse slippage {bps(g):+.1f} bps per dollar traded")
        for key in sorted(k for k in groups if k[0] in ("side", "type") and k[1] == window):
            print(f"   {key[0]} {key[2]:<7} {groups[key][2]:>4} fills  {bps(groups[key]):+7.1f} bps  (${groups[key][1]:,.0f})")
        for key in sorted(k for k in groups if k[0] == "day" and k[1] == window):
            print(f"   {key[2]}  {groups[key][2]:>4} fills  {bps(groups[key]):+7.1f} bps  (${groups[key][1]:,.0f})")
    g = groups.get(("all", "close" if REFERENCE == "close" else "open"))
    if g:
        verdict = "adopt the conviction EMA" if bps(g) >= THRESHOLD_BPS else "the EMA item is closed"
        print(f"\nopen-window headline {bps(g):+.1f} bps vs the pre-registered {THRESHOLD_BPS} bps -> {verdict}")


if __name__ == "__main__":
    main()
