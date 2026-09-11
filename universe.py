"""Trading universe = US-listed companies in the earnings-ai supply-chain graph
that Alpaca can trade fractionally. Cached to state/universe.json (one refresh
per day) so a cycle still starts if OneDrive has not synced earnings-ai.

    python universe.py     force a refresh and print the list
"""
import json
from datetime import date

import broker
import config

CACHE = config.STATE_DIR / "universe.json"


def _from_graph():
    graph = json.loads((config.EARNINGS_AI_DIR / "graph" / "merged_graph.json").read_text(encoding="utf-8"))
    tickers = {}
    for n in graph["nodes"]:
        t = (n.get("ticker") or "").strip().upper()
        if t and n.get("status") == "public" and n.get("exchange") in config.US_EXCHANGES:
            tickers[t] = n["id"]          # ticker -> graph node id (company name)
    return tickers


def _market_caps(tickers):
    """{ticker: market cap USD or None} from yfinance (one light request per name)."""
    import yfinance as yf
    caps = {}
    for t in tickers:
        try:
            caps[t] = yf.Ticker(t).fast_info.market_cap
        except Exception:  # missing / delisted / network hiccup -> unknown
            caps[t] = None
    return caps


def refresh():
    config.STATE_DIR.mkdir(exist_ok=True)
    mapping = _from_graph()
    ok = set(broker.tradable(list(mapping)))
    not_tradable = sorted(set(mapping) - ok)
    mapping = {t: c for t, c in mapping.items() if t in ok}
    caps = _market_caps(list(mapping))
    too_big = sorted(t for t, cap in caps.items() if config.MAX_MARKET_CAP and cap and cap > config.MAX_MARKET_CAP)
    mapping = {t: c for t, c in mapping.items() if t not in too_big}
    CACHE.write_text(json.dumps({
        "date": date.today().isoformat(),
        "max_market_cap": config.MAX_MARKET_CAP,
        "tickers": mapping,
        "market_caps": caps,
        "too_big": too_big,
        "not_tradable": not_tradable,
        "cap_unknown": sorted(t for t in mapping if caps.get(t) is None),
    }, indent=2), encoding="utf-8")
    return mapping


def load():
    """{ticker: company_name}; refreshed once per calendar day."""
    if CACHE.exists():
        data = json.loads(CACHE.read_text(encoding="utf-8"))
        if data.get("date") == date.today().isoformat():
            return data["tickers"]
    try:
        return refresh()
    except (OSError, ValueError) as exc:
        if CACHE.exists():
            return json.loads(CACHE.read_text(encoding="utf-8"))["tickers"]
        raise RuntimeError(f"cannot build the universe: {exc}") from exc


if __name__ == "__main__":
    m = refresh()
    info = json.loads(CACHE.read_text(encoding="utf-8"))
    print(len(m), "in universe:", " ".join(sorted(m)))
    print("too big (> $%.0fB):" % ((config.MAX_MARKET_CAP or 0) / 1e9), " ".join(info["too_big"]) or "(no cap)")
    print("not tradable:", info["not_tradable"], "| cap unknown:", info["cap_unknown"])
