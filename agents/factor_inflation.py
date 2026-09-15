"""Cross-asset factor agent: TIPS vs 7-10y Treasuries (see agents/factors.py)."""
from agents.factors import make_run

NAME = "factor_inflation"
run = make_run("inflation", NAME)
