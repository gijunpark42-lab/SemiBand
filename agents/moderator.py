"""Moderator — the meeting minutes of the ensemble.

The ten signal agents never talk to each other; they each hand in an
opinion and the ensemble adds them up with weights. The moderator runs
AFTER that arithmetic, only for tickers we are about to trade, and writes a
short record a human can read on the dashboard: where the agents agreed,
where they disagreed, which side the weights favoured and why, and what
would change the call. It never changes the decision — it explains it.

One claude -p call per traded ticker, through the local server.
"""
import logging
from concurrent.futures import ThreadPoolExecutor

import config
from agents import llm

log = logging.getLogger(__name__)
NAME = "moderator"

SYSTEM = (
    "You are the moderator of an investment committee. Up to ten analyst agents have each given an "
    "independent opinion on one stock (direction -1..+1, confidence 0..1, one-line reason). The "
    "committee then combined them with the trust weights shown and reached a conviction and an "
    "order. Write the minutes of that decision in English, for a dashboard. Be concrete and short."
)

MINUTES_SCHEMA = {
    "type": "object",
    "properties": {
        "agreement": {"type": "string", "description": "what the agents agreed on, 1-2 sentences"},
        "disagreement": {"type": "string", "description": "who disagreed and why, 1-2 sentences ('none' if nobody)"},
        "verdict": {"type": "string", "description": "which side the weights favoured and what order followed, 1-2 sentences"},
        "watch": {"type": "string", "description": "one signal that would prove this call wrong, one sentence"},
    },
    "required": ["agreement", "disagreement", "verdict", "watch"],
    "additionalProperties": False,
}


def _one(decision):
    lines = []
    for a, v in decision["agents"].items():
        lines.append(f"- {a} (weight {v['weight']:.2f}): direction {v['direction']:+.2f}, "
                     f"confidence {v['confidence']:.2f} — {v['reason']}")
    size = f"${decision['notional']:,.0f}" if decision.get("notional") else "entire position"
    target = f", target ${decision['target_usd']:,.0f}" if decision.get("target_usd") else ""
    cost = decision.get("est_cost_usd", 0) or 0
    user = (
        f"Stock: {decision['ticker']}\n"
        f"Agent opinions:\n" + "\n".join(lines) + "\n"
        f"Combined conviction: {decision['conviction']:+.3f} (rule: {decision['rule']})\n"
        f"Order: {decision['side']} {size}{target}\n"
        f"Trading cost: commission $0, assumed {config.COST_BPS} bps slippage/fees (about ${cost:,.0f} on this order). "
        "Cash is a position: the committee is never obliged to trade or to be fully invested.\n\n"
        "Write the minutes as JSON."
    )
    try:
        return llm.ask_json(SYSTEM, user, schema=MINUTES_SCHEMA)
    except Exception as exc:
        log.warning("%s %s: %s", NAME, decision["ticker"], exc)
        return None


def run(decisions):
    """Attach a `discussion` dict to each decision (in place). No-op if the server is down."""
    if not decisions or not llm.ensure_server():
        return decisions
    with ThreadPoolExecutor(max_workers=config.LLM_WORKERS) as pool:
        minutes = list(pool.map(_one, decisions))
    for d, m in zip(decisions, minutes):
        if m:
            d["discussion"] = m
    return decisions
