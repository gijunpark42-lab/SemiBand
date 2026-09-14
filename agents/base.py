"""Shared shapes for agents.

A Signal is one agent's opinion about one ticker for one cycle:
  direction   -1 (strong sell/avoid) .. +1 (strong buy)
  confidence   0 .. 1, how much the agent trusts its own call
  horizon      trading days over which the call should play out
  reason       one line a human can read on the dashboard
An agent that has nothing to say about a ticker simply returns no Signal for it.
"""
import re
from dataclasses import dataclass

# Graph statement labels that are NOT transcripts: SEC filings ("Meta 10-K (01-29-2026)") and third-party notes.
# The Claude readers keep only earnings-call and conference statements (user 2026-09-13: filing rows crowded the
# 12-row guidance window in 128 of 150 names; see RESEARCH.md).
NOT_TRANSCRIPT = re.compile(r"\b(10-K|10-Q|8-K|20-F|6-K|40-F)\b|\bnote\b", re.IGNORECASE)


@dataclass
class Signal:
    agent: str
    ticker: str
    direction: float
    confidence: float
    horizon: int
    reason: str

    def clipped(self):
        self.direction = clip(self.direction, -1, 1)
        self.confidence = clip(self.confidence, 0, 1)
        return self


def clip(x, lo, hi):
    return max(lo, min(hi, float(x)))
