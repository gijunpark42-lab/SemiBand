"""Cross-asset factor agent: US dollar index (see agents/factors.py)."""
from agents.factors import make_run

NAME = "factor_dollar"
run = make_run("dollar", NAME)
