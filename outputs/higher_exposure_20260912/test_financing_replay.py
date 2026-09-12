"""Focused checks for the added financing accounting, without markets or orders."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import research_higher_exposure_20260912 as research
from analyze_results import attribution


def observation(convictions, interval=3):
    return {"date":"2020-01-02", "exec_date":"2020-01-03", "mark_date":"2020-01-06",
            "calendar_days":interval, "conv":convictions,
            "returns":dict.fromkeys([*convictions,"SOXX"],0.0)}


class FinancingReplayTests(unittest.TestCase):
    def test_weekend_interest_charges_only_borrowed_equity_fraction(self):
        row = research.replay([observation(dict.fromkeys(range(10),0.5))], research.BASE, 0.05, 0)[0]
        self.assertAlmostEqual(row["gross"],1.5)
        self.assertAlmostEqual(row["financing_cost"],0.5*0.05*3/365)
        self.assertAlmostEqual(row["portfolio"],1-row["financing_cost"])

    def test_positive_cash_has_no_financing_and_no_assumed_interest_income(self):
        row = research.replay([observation(dict.fromkeys(range(5),0.5))], research.BASE, 0.10, 0)[0]
        self.assertAlmostEqual(row["gross"],0.75)
        self.assertEqual(row["financing_cost"],0)
        self.assertEqual(row["ret"],0)

    def test_ceiling_alone_cannot_increase_small_conviction_book(self):
        day = observation({"ONE":0.13,"TWO":0.08})
        baseline = research.replay([day],research.BASE,0.05,0)[0]
        higher = research.replay([day],dict(research.BASE,gross=2),0.05,0)[0]
        self.assertEqual(baseline["weights"],higher["weights"])
        self.assertAlmostEqual(higher["gross"],0.078)

    def test_ranking_floor_keeps_only_positive_convictions(self):
        day = observation({"POS":0.01,"ZERO":0,"NEG":-0.1})
        row = research.replay([day],dict(research.BASE,rank_always=True,floor_w=0.05),0.05,0)[0]
        self.assertEqual(row["weights"],{"POS":0.05})

    def test_attribution_separates_selection_from_cash_drag_exactly(self):
        curve=[dict(gross=0.1,price_return=0.002,ret=0.0019,soxx_ret=0.01,
                    trading_cost=0.0001,financing_cost=0)]
        result=attribution(curve,[True])
        terms=result["mean_daily_bps_decomposition"]
        self.assertAlmostEqual(terms["selection"],10)
        self.assertAlmostEqual(terms["capital_utilization"],-90)
        self.assertAlmostEqual(terms["trading_cost"],-1)
        self.assertAlmostEqual(terms["account_minus_full_soxx"],-81)
        self.assertLess(result["max_absolute_identity_residual"],1e-12)

    def test_empty_book_is_retained_in_identity_but_not_sleeve_dates(self):
        curve=[dict(gross=0,price_return=0,ret=0,soxx_ret=-0.01,
                    trading_cost=0,financing_cost=0),
               dict(gross=0.1,price_return=0.002,ret=0.002,soxx_ret=0.01,
                    trading_cost=0,financing_cost=0)]
        result=attribution(curve,[True,True])
        self.assertEqual(result["days"],2)
        self.assertEqual(result["active_sleeve_days"],1)
        self.assertAlmostEqual(result["sleeve_before_cost_active_days"]["compound_return"],0.02)
        self.assertAlmostEqual(result["soxx_same_active_days"]["compound_return"],0.01)


if __name__ == "__main__":
    unittest.main()
