"""Decision manifest (2026-10-06). After the research-workflow playbook the user supplied ("How Jane Street Uses AI for Trading",
an independent synthesis by Codila of a public Jane Street interview): snapshot identity, pinned transformation behaviour and
immutable forecasts. Each cycle run appends one JSON to state/manifests/ recording what its decision used — code version, the
knobs, the universe, the graph files, the price frame, the fitted model, the warm start, the Claude model and prompt versions —
and a checksum of every date's recorded predictions. A past date whose checksum differs from the previous manifest means a
forecast was altered after it was made; the cycle notes it. Writing a manifest never stops a cycle.
"""
import hashlib
import json
import logging
import subprocess
from datetime import datetime, timezone

import config
import ledger

log = logging.getLogger(__name__)
KNOBS = ("EXEC_MODE", "CLOSE_ORDER_TYPE", "AGENTS", "SHADOW_AGENTS", "HORIZONS", "LEARNER_TARGET_MODE", "BETA_ESTIMATOR", "BETA_FLOOR",
         "CONVICTION_EMA", "DEMEAN_CONVICTION", "DEMEAN_GROUP", "SECTOR_MAX_NAMES", "TOP_N", "MIN_CONVICTION", "SIZE_PER_CONVICTION",
         "MAX_POSITION_PCT", "GROSS_TARGET", "VOL_TARGET", "IDLE_SLEEVE", "IDLE_SLEEVE_TREND", "REBALANCE_BAND", "EXCLUDED_TICKERS",
         "WARM_START_WEIGHT", "LLM_MODEL", "LLM_EFFORT", "LLM_REUSE_AGENTS", "CARRY_FORWARD_AGENTS", "RESEARCH_TRIALS")
_SECRET = ("KEY", "SECRET", "TOKEN", "PASSWORD")


def _sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def _sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def code_version():
    def git(*args):
        return subprocess.run(["git", "-C", str(config.ROOT), *args], capture_output=True, text=True, timeout=15).stdout.strip()
    try:
        return {"commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain", "--untracked-files=no"))}
    except Exception as exc:
        return {"commit": None, "error": str(exc)[:120]}


def config_snapshot():
    """The decision knobs in the clear, and a hash over every upper-case setting except secrets."""
    allv = {k: getattr(config, k) for k in dir(config) if k.isupper() and not any(s in k for s in _SECRET)}
    blob = json.dumps(allv, sort_keys=True, default=str).encode()
    return {"knobs": {k: getattr(config, k, None) for k in KNOBS}, "sha": _sha_bytes(blob)}


def prompt_hashes():
    out = {}
    for name in ("llm_supply", "llm_guidance", "llm_news", "moderator"):
        try:
            mod = __import__(f"agents.{name}", fromlist=["SYSTEM"])
            out[name] = _sha_bytes(str(getattr(mod, "SYSTEM", "")).encode())[:16]
        except Exception as exc:
            out[name] = f"error: {str(exc)[:60]}"
    return out


def prediction_checksums():
    """{date: sha of that date's prediction rows} over the live ledger."""
    out = {}
    with ledger.connect() as con:
        rows = con.execute("SELECT date, agent, ticker, direction, confidence, horizon, reason FROM predictions "
                           "ORDER BY date, agent, ticker, id").fetchall()
    cur, h = None, None
    for r in rows:
        if r[0] != cur:
            if cur is not None:
                out[cur] = h.hexdigest()[:20]
            cur, h = r[0], hashlib.sha256()
        h.update(repr(tuple(r)[1:]).encode())
    if cur is not None:
        out[cur] = h.hexdigest()[:20]
    return out


def _folder():
    d = config.STATE_DIR / "manifests"
    d.mkdir(parents=True, exist_ok=True)
    return d


def previous():
    files = sorted(_folder().glob("*.json"))
    if not files:
        return None
    try:
        return json.loads(files[-1].read_text(encoding="utf-8"))
    except ValueError:
        return None


def write(today, universe, closes=None, orders=(), llm_models=(), dry_run=False):
    """Append this run's manifest; -> (manifest, [past dates whose predictions changed since the previous manifest])."""
    graph_dir = config.STATE_DIR / "graph_snapshots" / today / "graph"
    if not graph_dir.exists():
        graph_dir = config.EARNINGS_AI_DIR / "graph"
    graph = {p.name: _sha_file(p)[:20] for p in sorted(graph_dir.glob("*.json"))} if graph_dir.exists() else {}
    model_path = config.STATE_DIR / "model.json"
    warm = config.STATE_DIR / "backtest.sqlite"
    model = {}
    if model_path.exists():
        try:
            m = json.loads(model_path.read_text(encoding="utf-8"))
            model = {"sha": _sha_file(model_path)[:20], "fitted": m.get("fitted"),
                     "effective_weights": {a: round(w, 4) for a, w in (m.get("effective_weights") or {}).items()}}
        except ValueError:
            model = {"sha": _sha_file(model_path)[:20]}
    checks = prediction_checksums()
    man = {
        "date": today,
        "dry_run": bool(dry_run),
        "written_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "code": code_version(),
        "config": config_snapshot(),
        "universe": {"n": len(universe), "sha": _sha_bytes(json.dumps(sorted(universe)).encode())[:20]},
        "graph": {"folder": str(graph_dir), "files": graph},
        "prices": ({"last_bar": str(closes.index[-1].date()), "rows": int(len(closes)), "symbols": int(closes.shape[1])}
                   if closes is not None and len(closes) else None),
        "model": model,
        "warm_start": {"sha": _sha_file(warm)[:20], "bytes": warm.stat().st_size} if warm.exists() else None,
        "llm": {"model": config.LLM_MODEL, "effort": config.LLM_EFFORT, "served": sorted(llm_models), "prompts": prompt_hashes()},
        "orders": [{"ticker": o.get("ticker"), "side": o.get("side"), "notional": o.get("notional")} for o in orders],
        "predictions": checks,
    }
    prev = previous()
    changed = sorted(d for d, h in ((prev or {}).get("predictions") or {}).items() if d < today and checks.get(d) != h)
    if changed:
        man["past_predictions_changed"] = changed
        log.warning("manifest: recorded predictions of %s changed since the previous manifest", ", ".join(changed))
    path = _folder() / f"{today}_{datetime.now(timezone.utc):%H%M%S}.json"
    path.write_text(json.dumps(man, indent=1, default=str), encoding="utf-8")
    log.info("manifest %s: code %s, universe %d (%s), graph %d files, model %s", path.name, (man["code"].get("commit") or "?")[:8],
             man["universe"]["n"], man["universe"]["sha"][:8], len(graph), (model.get("sha") or "?")[:8])
    return man, changed
