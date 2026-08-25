"""Trade journal: why the bot bought or sold, for the dashboard.

Every fill-intent (also in DRY_RUN) is appended to trades.json locally and,
when BLOB_READ_WRITE_TOKEN is set in .env, the whole file is re-uploaded to
Vercel Blob at a fixed pathname so the web app (web/) can read it. Upload
failures are logged and never block trading.
"""
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

log = logging.getLogger("journal")

FILE = Path(__file__).with_name("trades.json")
BLOB_URL = "https://blob.vercel-storage.com/trades.json"
MAX_ROWS = 500


def record(symbol, side, reason, price, notional=None, qty=None, dry_run=False):
    rows = json.loads(FILE.read_text(encoding="utf-8")) if FILE.exists() else []
    rows.append({
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "symbol": symbol,
        "side": side,              # "BUY" | "SELL"
        "reason": reason,
        "price": round(float(price), 4),
        "notional": None if notional is None else round(float(notional), 2),
        "qty": None if qty is None else float(qty),
        "dry_run": dry_run,
    })
    rows = rows[-MAX_ROWS:]
    body = json.dumps(rows, indent=2)
    FILE.write_text(body, encoding="utf-8")
    _upload(body)


def _upload(body):
    token = os.getenv("BLOB_READ_WRITE_TOKEN")
    if not token:
        return
    try:
        resp = requests.put(
            BLOB_URL,
            data=body.encode("utf-8"),
            headers={
                "authorization": f"Bearer {token}",
                "x-api-version": "7",
                "x-content-type": "application/json",
                "x-add-random-suffix": "0",
                "x-allow-overwrite": "1",
                "x-cache-control-max-age": "0",
            },
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as exc:
        log.warning("trades.json upload failed: %s", exc)
