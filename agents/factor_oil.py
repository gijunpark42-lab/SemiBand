"""Cross-asset factor agent: WTI crude (see agents/factors.py)."""
from agents.factors import make_run

NAME = "factor_oil"
run = make_run("oil", NAME)
