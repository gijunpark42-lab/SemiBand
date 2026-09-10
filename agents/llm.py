"""Client for the local Claude server (TradingAgents/local-claude/server.py).

Every call is one `claude -p` on the Claude Max subscription. We only use the
JSON-schema path, so agents always get a dict shaped exactly as they asked.
"""
import json
import logging
import subprocess
import sys
import time
import urllib.error
import urllib.request

import config

log = logging.getLogger(__name__)

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


def health():
    try:
        with urllib.request.urlopen(config.LLM_URL.rsplit("/v1", 1)[0] + "/health", timeout=3) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError):
        return False


def ensure_server(wait_s=40):
    """Start local-claude/server.py if it is not answering; wait until it is."""
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
    subprocess.Popen([str(python), "-X", "utf8", str(server)], cwd=str(config.TRADINGAGENTS_DIR),
                     stdout=log_file, stderr=subprocess.STDOUT, creationflags=flags)
    for _ in range(wait_s):
        time.sleep(1)
        if health():
            log.info("local Claude server started")
            return True
    log.error("local Claude server did not come up in %ss", wait_s)
    return False


def ask_json(system, user, schema=OPINION_SCHEMA, model=None, timeout=300):
    """One chat completion with a JSON schema; returns the parsed object."""
    body = {
        "model": model or config.LLM_MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "response_format": {"type": "json_schema", "json_schema": {"name": "opinion", "schema": schema}},
    }
    req = urllib.request.Request(
        config.LLM_URL + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    content = data["choices"][0]["message"]["content"]
    return json.loads(content)
