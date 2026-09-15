"""Cross-asset factor agent: 10-year Treasury yield (see agents/factors.py)."""
from agents.factors import make_run

NAME = "factor_long_rates"
run = make_run("long_rates", NAME)
