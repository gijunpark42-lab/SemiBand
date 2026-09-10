"""Trade journal + dashboard feed for the web app.

trades.json     every order intent (also in DRY_RUN): symbol, side, price, size, reason
dashboard.json  the ensemble's state after each cycle: agent weights, scoreboard,
                today's convictions per ticker, notes

Both are written locally under state/ and, when BLOB_READ_WRITE_TOKEN is set in
.env, uploaded to the private Vercel Blob store under semiband-v2/ (the old VM bots
still write the root trades.json, so our files live apart) so web/ can read them. Upload failures are logged and never block trading.
"""
import json
import logging
import os
from datetime import datetime, timezone

import requests

import config  # loads .env

log = logging.getLogger("journal")

TRADES_FILE = config.STATE_DIR / "trades.json"
DASHBOARD_FILE = config.STATE_DIR / "dashboard.json"
BLOB_BASE = "https://blob.vercel-storage.com/"
MAX_ROWS = 500


def record(symbol, side, reason, price, notional=None, qty=None, dry_run=False):
    config.STATE_DIR.mkdir(exist_ok=True)
    rows = json.loads(TRADES_FILE.read_text(encoding="utf-8")) if TRADES_FILE.exists() else []
    rows.append({
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "symbol": symbol,
        "side": side,              # "BUY" | "SELL"
        "reason": reason,
        "price": None if price is None else round(float(price), 4),
        "notional": None if notional is None else round(float(notional), 2),
        "qty": None if qty is None else float(qty),
        "dry_run": dry_run,
    })
    rows = rows[-MAX_ROWS:]
    body = json.dumps(rows, indent=2)
    TRADES_FILE.write_text(body, encoding="utf-8")
    _upload("semiband-v2/trades.json", body)


def publish_dashboard(payload: dict):
    config.STATE_DIR.mkdir(exist_ok=True)
    payload = dict(payload, generated=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    body = json.dumps(payload, indent=2, ensure_ascii=False)
    DASHBOARD_FILE.write_text(body, encoding="utf-8")
    _upload("semiband-v2/dashboard.json", body)


def _upload(pathname, body):
    token = os.getenv("BLOB_READ_WRITE_TOKEN")
    if not token:
        return
    try:
        resp = requests.put(
            BLOB_BASE + pathname,
            data=body.encode("utf-8"),
            headers={
                "authorization": f"Bearer {token}",
                "x-api-version": "7",
                "x-vercel-blob-access": "private",
                "x-content-type": "application/json",
                "x-add-random-suffix": "0",
                "x-allow-overwrite": "1",
                "x-cache-control-max-age": "0",
            },
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as exc:
        log.warning("%s upload failed: %s", pathname, exc)
