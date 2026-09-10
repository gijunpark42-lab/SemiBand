"""Combine agent signals into one conviction per ticker, and learn the agent
weights with the multiplicative-weights (Hedge) rule.

Why Hedge: with a handful of experts and only a few hundred scored
predictions, a closed-form update that provably tracks the best expert is
safer than fitting a model. Each scoring round, every agent gets a gain in
[-1, 1] (did its calls make abnormal money?) and its weight is multiplied by
exp(eta * gain). A floor keeps every agent alive so it can earn its way back.
"""
import math
from collections import defaultdict

import config


def initial_weights():
    n = len(config.AGENTS)
    return {a: 1.0 / n for a in config.AGENTS}


def combine(signals, weights):
    """-> ({ticker: conviction}, {ticker: {agent: {direction, confidence, reason}}})

    conviction = sum_i w_i * direction_i * confidence_i / sum_i w_i over the agents
    that actually spoke about the ticker, so a ticker no LLM agent covered is
    judged by the agents that did, not dragged toward zero by silence.
    """
    by_ticker = defaultdict(dict)
    for s in signals:
        by_ticker[s.ticker][s.agent] = s
    convictions, breakdown = {}, {}
    for ticker, per_agent in by_ticker.items():
        num = sum(weights.get(a, 0) * s.direction * s.confidence for a, s in per_agent.items())
        den = sum(weights.get(a, 0) for a in per_agent)
        convictions[ticker] = num / den if den else 0.0
        breakdown[ticker] = {a: {"direction": round(s.direction, 3), "confidence": round(s.confidence, 3),
                                 "horizon": s.horizon, "reason": s.reason} for a, s in per_agent.items()}
    return convictions, breakdown


def hedge_update(weights, gains):
    """gains = {agent: gain in [-1, 1]}; agents without a gain keep their weight."""
    new = {a: w * math.exp(config.HEDGE_ETA * gains.get(a, 0.0)) for a, w in weights.items()}
    total = sum(new.values()) or 1.0
    new = {a: max(w / total, config.WEIGHT_FLOOR) for a, w in new.items()}
    total = sum(new.values())
    return {a: round(w / total, 4) for a, w in new.items()}
