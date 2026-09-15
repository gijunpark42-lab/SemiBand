"""Cross-asset factor agent: fed funds futures implied rate (see agents/factors.py)."""
from agents.factors import make_run

NAME = "factor_fed"
run = make_run("fed", NAME)
