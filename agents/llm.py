"""Client for the local Claude server (TradingAgents/local-claude/server.py).

Every call is one `claude -p` on the Claude Max subscription. We only use the
JSON-schema path, so agents always get a dict shaped exactly as they asked.
"""
import json
import logging
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

import config

log = logging.getLogger(__name__)
DEADLINE = None                # aware datetime; after it ask_json refuses new calls at once (the cycle sets it for its Claude stage)
TIMINGS = []                   # end-to-end seconds (queue wait + the call, timeouts included) since the last timing_summary()
SKIPPED = 0                    # calls refused by the deadline since the last timing_summary()
STAGE_SKIPPED = 0              # calls refused since the cycle reset it at the start of its Claude stage (dashboard note)
MODELS_SEEN = set()            # 2026-10-06: the serving configurations the server reported (system_fingerprint: model id/effort)
API_ENABLED = False            # 2026-10-26: cycle.main / guardian.main set it from config.LLM_BACKEND; off for research scripts and tests
API_OFF = None                 # why the API path stopped for this process (billing, budget, auth, bad request); None = still on
_API_SPENT = None              # USD spent through the API, summed from state/api_spend.jsonl once per process, then kept up to date
_API_CLIENT = None
_LOCK = threading.Lock()


class StageDeadline(RuntimeError):
    """Raised instead of calling Claude once DEADLINE has passed."""


def timing_summary():
    """(calls, mean s, p90 s, max s, skipped) gathered since the last call, then reset; None when nothing was gathered."""
    global SKIPPED
    if not TIMINGS and not SKIPPED:
        return None
    t = sorted(TIMINGS)
    out = (len(t), (sum(t) / len(t)) if t else 0.0, (t[int(0.9 * (len(t) - 1))] if t else 0.0), (t[-1] if t else 0.0), SKIPPED)
    TIMINGS.clear()
    SKIPPED = 0
    return out

OPINION_SCHEMA = {
    "type": "object",
    "properties": {
        "direction": {"type": "number", "minimum": -1, "maximum": 1,
                      "description": "-1 strong avoid/sell .. +1 strong buy, 0 neutral"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "horizon_days": {"type": "integer", "enum": [5, 10, 20]},
        "reason": {"type": "string", "description": "one sentence, max 200 characters"},
    },
    "required": ["direction", "confidence", "horizon_days", "reason"],
    "additionalProperties": False,
}


def refused(exc):
    """True when a URLError means nothing is listening (the server died or never bound), not an HTTP error from it."""
    if isinstance(exc, urllib.error.HTTPError):
        return False
    reason = getattr(exc, "reason", None)
    return isinstance(reason, (ConnectionRefusedError, ConnectionResetError)) or getattr(reason, "winerror", None) in (10061, 10054)


def health():
    try:
        with urllib.request.urlopen(config.LLM_URL.rsplit("/v1", 1)[0] + "/health", timeout=3) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError):
        return False


_SERVER_LOCK = threading.Lock()   # 2026-09-22: concurrent callers (six worker threads) must never spawn two servers


def ensure_server(wait_s=40):
    """Start local-claude/server.py if it is not answering; wait until it is."""
    with _SERVER_LOCK:
        return _ensure_server(wait_s)


def _ensure_server(wait_s):
    if health():
        return True
    python = config.TRADINGAGENTS_DIR / ".venv" / "Scripts" / "python.exe"
    server = config.TRADINGAGENTS_DIR / "local-claude" / "server.py"
    if not python.exists() or not server.exists():
        log.error("local Claude server not found under %s", config.TRADINGAGENTS_DIR)
        return False
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0)
    log_file = open(config.STATE_DIR / "llm_server.log", "a", encoding="utf-8")
    env = {**os.environ, "LOCAL_CLAUDE_EFFORT_DEEP": config.LLM_EFFORT,      # opus effort and concurrent slots; the server
           "LOCAL_CLAUDE_CONCURRENCY": str(config.LLM_WORKERS)}              # reads both once, at start
    subprocess.Popen([str(python), "-X", "utf8", str(server)], cwd=str(config.TRADINGAGENTS_DIR),
                     stdout=log_file, stderr=subprocess.STDOUT, creationflags=flags, env=env)
    for _ in range(wait_s):
        time.sleep(1)
        if health():
            log.info("local Claude server started")
            return True
    log.error("local Claude server did not come up in %ss", wait_s)
    return False


def _spend_path():
    return config.STATE_DIR / "api_spend.jsonl"


def api_spent():
    """USD spent through the Claude API so far (all processes, as of this process's first look, plus its own calls)."""
    global _API_SPENT
    with _LOCK:
        if _API_SPENT is None:
            total = 0.0
            if _spend_path().exists():
                for line in _spend_path().read_text(encoding="utf-8").splitlines():
                    try:
                        total += float(json.loads(line)["usd"])
                    except (ValueError, KeyError, TypeError):
                        pass
            _API_SPENT = total
        return _API_SPENT


def _use_api(model, tools):
    global API_OFF
    if not API_ENABLED or API_OFF or tools or (model and model != config.LLM_MODEL) or not os.getenv("ANTHROPIC_API_KEY_TRADING"):
        return False
    if api_spent() >= config.LLM_API_BUDGET_USD:
        API_OFF = f"budget ${config.LLM_API_BUDGET_USD:.0f} spent"
        log.warning("Claude API off for this run (%s): calls go to the local server", API_OFF)
        return False
    return True


_UNSUPPORTED = ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "minLength", "maxLength")


def _api_schema(node):
    """The schema without the keywords the API's structured outputs reject (numeric bounds, string lengths: a 400 on 2026-10-26);
    a numeric range moves into the description so the model still sees it, and the agents clip the values anyway."""
    if isinstance(node, list):
        return [_api_schema(x) for x in node]
    if not isinstance(node, dict):
        return node
    out = {k: _api_schema(v) for k, v in node.items() if k not in _UNSUPPORTED}
    if "minimum" in node or "maximum" in node:
        rng = f"from {node.get('minimum', '-inf')} to {node.get('maximum', 'inf')}"
        out["description"] = f"{node['description']} ({rng})" if node.get("description") else rng
    return out


def _ask_api(system, user, schema, effort, timeout):
    """One Messages API call with a JSON schema; returns (parsed object, serving label). Records its cost."""
    global _API_CLIENT, _API_SPENT, API_OFF
    import anthropic
    if _API_CLIENT is None:
        _API_CLIENT = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY_TRADING"], max_retries=2)
    try:
        with _API_CLIENT.with_options(timeout=timeout).beta.messages.stream(
                model=config.LLM_API_MODEL, max_tokens=32000,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],   # shared prefix (llm_nodus's market block)
                messages=[{"role": "user", "content": user}],
                output_config={"effort": effort, "format": {"type": "json_schema", "schema": _api_schema(schema)}},
                betas=["server-side-fallback-2026-07-01"], fallbacks="default") as stream:
            msg = stream.get_final_message()
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError, anthropic.BadRequestError) as exc:
        API_OFF = f"{type(exc).__name__}: {str(exc)[:160]}"      # repeats on every call (a low credit balance can come back as a 400)
        log.warning("Claude API off for this run (%s): calls go to the local server", API_OFF)
        raise
    except anthropic.APIStatusError as exc:
        if exc.status_code == 402:
            API_OFF = "billing: the credit is used up"
            log.warning("Claude API off for this run (%s): calls go to the local server", API_OFF)
        raise
    u, p = msg.usage, config.LLM_API_PRICES
    usd = (u.input_tokens * p["input"] + (u.cache_creation_input_tokens or 0) * p["cache_write"]
           + (u.cache_read_input_tokens or 0) * p["cache_read"] + u.output_tokens * p["output"]) / 1e6
    with _LOCK:
        _API_SPENT = (_API_SPENT or 0.0) + usd
        with _spend_path().open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "model": msg.model, "effort": effort,
                                "in": u.input_tokens, "cache_write": u.cache_creation_input_tokens or 0,
                                "cache_read": u.cache_read_input_tokens or 0, "out": u.output_tokens, "usd": round(usd, 5)}) + "\n")
    if msg.stop_reason != "end_turn":
        raise RuntimeError(f"Claude API stopped with {msg.stop_reason}")
    text = next(b.text for b in msg.content if b.type == "text")
    return json.loads(text), f"{msg.model}/{effort}/api"


def ask_json(system, user, schema=OPINION_SCHEMA, model=None, timeout=None, tools="", effort=None):
    """One chat completion with a JSON schema; returns the parsed object.
    tools: comma list of Claude Code built-ins to allow, e.g. "WebSearch" (server-side web search).
    timeout: seconds end to end (queue wait + the call); None = config.LLM_TIMEOUT.
    effort: Claude Code effort for this call; None = config.LLM_EFFORT (2026-10-26: sent on every call)."""
    global SKIPPED
    timeout = timeout or config.LLM_TIMEOUT
    if DEADLINE is not None and datetime.now(timezone.utc) >= DEADLINE:
        global STAGE_SKIPPED
        with _LOCK:
            SKIPPED += 1
            STAGE_SKIPPED += 1
        raise StageDeadline(f"Claude stage deadline {DEADLINE.astimezone().strftime('%H:%M')} passed: call skipped")
    t0 = time.time()
    if _use_api(model, tools):
        try:
            out, served = _ask_api(system, user, schema, effort or config.LLM_EFFORT, timeout)
            with _LOCK:
                MODELS_SEEN.add(served)
            TIMINGS.append(time.time() - t0)
            return out
        except Exception as exc:   # any API failure: this one call goes to the local server (the subscription)
            log.warning("Claude API call failed, using the local server: %s", str(exc)[:200])
    body = {
        "claude_tools": tools,
        "model": model or config.LLM_MODEL,
        "effort": effort or config.LLM_EFFORT,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "response_format": {"type": "json_schema", "json_schema": {"name": "opinion", "schema": schema}},
    }
    req = urllib.request.Request(
        config.LLM_URL + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.load(r)
        except urllib.error.URLError as exc:
            if not refused(exc):
                raise
            log.warning("local Claude server refused the call (%s): restarting it and retrying once", exc.reason)
            if not ensure_server():
                raise
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.load(r)
    finally:
        TIMINGS.append(time.time() - t0)
    with _LOCK:
        MODELS_SEEN.add(str(data.get("system_fingerprint") or data.get("model") or "?"))
    content = data["choices"][0]["message"]["content"]
    return json.loads(content)
