"""Cross-asset factor agent: copper (see agents/factors.py)."""
from agents.factors import make_run

NAME = "factor_copper"
run = make_run("copper", NAME)
