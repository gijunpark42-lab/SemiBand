"""Trading universe, sourced from the earnings-ai project.

earnings-ai tracks the AI/semiconductor supply chain, but only its US-listed
public names can be subscribed to on Alpaca: the rest are private, subsidiaries,
or listed in Tokyo/Taipei/Seoul/Frankfurt. This pulls out that subscribable
slice and caches it to tickers.json so the bot still starts when the earnings-ai
folder is offline (it lives in OneDrive, so it is not always synced).

    python tickers.py    re-read earnings-ai and rewrite the cache
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import config

CACHE = Path(__file__).with_name("tickers.json")

# earnings-ai tags every company with the exchange it lists on; these are the
# ones Alpaca covers. Anything else (TSE, TWSE, KRX, KOSDAQ, SZSE, XETRA, ...)
# has no Alpaca symbol to subscribe to.
US_EXCHANGES = {"NASDAQ", "NYSE", "NYSE American", "AMEX"}


def _subscribable(metadata):
    """{company_name: {...}} -> sorted, de-duplicated ticker list.

    Deduplication matters: earnings-ai lists a parent and its division
    separately (Intel / Intel Foundry) and both carry the same ticker.
    """
    return sorted({
        entry["ticker"].strip()
        for entry in metadata.values()
        if entry.get("status") == "public"
        and entry.get("exchange") in US_EXCHANGES
        and entry.get("ticker", "").strip()
    })


def refresh():
    """Re-read earnings-ai, rewrite the cache, return the tickers."""
    source = Path(config.EARNINGS_AI_DIR) / "company_metadata.json"
    metadata = json.loads(source.read_text(encoding="utf-8"))
    tickers = _subscribable(metadata)

    CACHE.write_text(json.dumps({
        "source": str(source),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tickers": tickers,
    }, indent=2), encoding="utf-8")
    return tickers


def load():
    """Cached tickers, refreshing on first use."""
    if not CACHE.exists():
        return refresh()
    return json.loads(CACHE.read_text(encoding="utf-8"))["tickers"]


if __name__ == "__main__":
    source_total = len(json.loads(
        (Path(config.EARNINGS_AI_DIR) / "company_metadata.json").read_text(encoding="utf-8")
    ))
    tickers = refresh()
    print(f"{len(tickers)} subscribable of {source_total} companies -> {CACHE.name}")
    print(", ".join(tickers))
