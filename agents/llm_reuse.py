"""2026-09-22 (user: "새 그래프 업데이트 안 됐으면 ... 부르는 게 똑같은 게 아니냐"): llm_supply and llm_guidance reuse a name's last
answer while the question is the same. Between the 09-18 and 09-22 graph snapshots 164 of 176 supply reports were identical to
the character, and the re-asked answers differed only through the price line and Claude's sampling (corr +0.77).

The key is the prompt without its price line, plus the system prompt, the model and the effort, so any change to the input,
the prompt or the model asks again. An answer older than LLM_REUSE_MAX_DAYS, or a name whose 20-day move relative to SOXX
shifted by LLM_REUSE_MOVE_PP points since the answer, is asked again too. Only fresh answers are stored
(state/llm_reuse.json); a failed call leaves the stored answer as it was.
"""
import hashlib
import json
import os
import re
import threading
from datetime import date

import config
from agents import llm

_RELATIVE = re.compile(r"\(relative ([+-]?\d+(?:\.\d+)?)%\)")


def path():
    return config.STATE_DIR / "llm_reuse.json"


def key(system, user, price_line):
    text = "\n".join([str(config.LLM_MODEL), str(config.LLM_EFFORT), system, user.replace(price_line, "")])
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:20]


def relative(price_line):
    """The name's 20-day move relative to SOXX in percentage points, read from market.move_line's text; None if unavailable."""
    m = _RELATIVE.search(price_line or "")
    return float(m.group(1)) if m else None


def _read():
    try:
        return json.loads(path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


class Session:
    """One agent's run: ask() returns (answer, None) for a fresh Claude answer or (answer, source date) for a reused one."""

    def __init__(self, agent, today):
        self.agent, self.today = agent, today
        self.cache = _read().get(agent, {})
        self.updates, self.reused = {}, 0
        self._lock = threading.Lock()

    def _still_good(self, entry, k, rel):
        if entry.get("key") != k:
            return False
        if (date.fromisoformat(self.today) - date.fromisoformat(entry["date"])).days > config.LLM_REUSE_MAX_DAYS:
            return False
        return rel is None or entry.get("rel") is None or abs(rel - entry["rel"]) < config.LLM_REUSE_MOVE_PP

    def ask(self, ticker, system, user, price_line):
        k, rel = key(system, user, price_line), relative(price_line)
        entry = self.cache.get(ticker)
        if entry and self._still_good(entry, k, rel):
            with self._lock:
                self.reused += 1
            return entry["answer"], entry["date"]
        answer = llm.ask_json(system, user)                      # raises: the caller logs it, the stored answer stays
        with self._lock:
            self.updates[ticker] = {"key": k, "date": self.today, "rel": rel, "answer": answer}
        return answer, None

    def save(self):
        if not self.updates:
            return
        data = _read()
        data.setdefault(self.agent, {}).update(self.updates)
        tmp = path().with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, path())
