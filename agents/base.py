"""Shared shapes for agents.

A Signal is one agent's opinion about one ticker for one cycle:
  direction   -1 (strong sell/avoid) .. +1 (strong buy)
  confidence   0 .. 1, how much the agent trusts its own call
  horizon      trading days over which the call should play out
  reason       one line a human can read on the dashboard
An agent that has nothing to say about a ticker simply returns no Signal for it.
"""
from dataclasses import dataclass


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
