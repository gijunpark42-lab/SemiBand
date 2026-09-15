"""Cross-asset factor agent: memory makers vs SOXX (see agents/factors.py)."""
from agents.factors import make_run

NAME = "factor_memory"
run = make_run("memory", NAME)
