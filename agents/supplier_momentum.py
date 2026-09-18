"""Supplier-momentum agent (round 44, 2026-09-17; the upstream mirror of customer momentum, cf. Menzly & Ozbas 2010): a
customer's suppliers' trailing 21-day relative returns. Same construction as agents.customer_momentum, other edge end."""
from agents.base import Signal
from agents.customer_momentum import signals

NAME = "supplier_momentum"


def run(universe: dict, ctx: dict) -> list[Signal]:
    return signals(universe, ctx, "suppliers", NAME)
