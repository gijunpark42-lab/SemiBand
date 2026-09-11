"""Point-in-time copies of the earnings-ai graph.

The graph's structure (edges, node fields, confidences) is always "today's" — the backtest's biggest known
leak (RESEARCH.md, 2026-09-11). From now on every daily cycle stores a dated copy of the graph files
whenever their content changed, so that in a few months the backtest can read the graph as it was on each
simulated day instead of as it is now.

    python snapshots.py            # take a snapshot now (no-op when nothing changed)
    snapshots.take()               # called by cycle.py at the start of every cycle
    snapshots.dir_for(asof)        # latest snapshot directory dated <= asof, or None

Layout mirrors earnings-ai so config.EARNINGS_AI_DIR can simply point at a snapshot:
state/graph_snapshots/<YYYY-MM-DD>/graph/{merged_graph, exposure, evidence, capex_backlog, timelines.bundle}.json,
<date>/company_metrics.json, <date>/company_metadata.json, <date>/manifest.json (hashes).
"""
import hashlib
import json
import logging
import shutil
from datetime import date

import config

log = logging.getLogger("snapshots")
ROOT = config.STATE_DIR / "graph_snapshots"
FILES = [("graph", "merged_graph.json"), ("graph", "exposure.json"), ("graph", "evidence.json"),
         ("graph", "capex_backlog.json"), ("graph", "timelines.bundle.json"),
         ("", "company_metrics.json"), ("", "company_metadata.json")]


def _hashes():
    out = {}
    for sub, name in FILES:
        p = config.EARNINGS_AI_DIR / sub / name if sub else config.EARNINGS_AI_DIR / name
        if p.exists():
            out[name] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def latest():
    """(date string, manifest) of the newest snapshot, or (None, {})."""
    if not ROOT.exists():
        return None, {}
    dirs = sorted(d.name for d in ROOT.iterdir() if d.is_dir() and (d / "manifest.json").exists())
    if not dirs:
        return None, {}
    return dirs[-1], json.loads((ROOT / dirs[-1] / "manifest.json").read_text(encoding="utf-8"))


def take(today=None):
    """Copy the graph files into state/graph_snapshots/<today>/ if any of them changed since the last snapshot.
    Returns the snapshot date written, or None when nothing changed. Never raises (a missing graph is logged)."""
    today = (today or date.today()).isoformat()
    try:
        hashes = _hashes()
        if not hashes:
            log.warning("no earnings-ai graph files found under %s", config.EARNINGS_AI_DIR)
            return None
        _, last = latest()
        if last.get("hashes") == hashes:
            return None
        dest = ROOT / today
        dest.mkdir(parents=True, exist_ok=True)
        for sub, name in FILES:
            src = config.EARNINGS_AI_DIR / sub / name if sub else config.EARNINGS_AI_DIR / name
            if src.exists():
                (dest / sub).mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest / sub / name)
        (dest / "manifest.json").write_text(json.dumps({"date": today, "hashes": hashes}, indent=1), encoding="utf-8")
        log.info("graph snapshot %s (%d files)", today, len(hashes))
        return today
    except Exception as exc:
        log.warning("graph snapshot failed: %s", exc)
        return None


def dir_for(asof):
    """Newest snapshot directory dated <= asof (date or ISO string), or None when none exists yet."""
    if not ROOT.exists():
        return None
    asof = asof if isinstance(asof, str) else asof.isoformat()
    dirs = sorted(d.name for d in ROOT.iterdir() if d.is_dir() and d.name <= asof and (d / "manifest.json").exists())
    return ROOT / dirs[-1] if dirs else None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    d = take()
    print("snapshot written:", d or "nothing changed", "| latest:", latest()[0])
