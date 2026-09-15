"""Cross-asset factor agent: high yield vs 7-10y Treasuries (see agents/factors.py)."""
from agents.factors import make_run

NAME = "factor_credit"
run = make_run("credit", NAME)
