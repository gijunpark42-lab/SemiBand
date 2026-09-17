"""Round 42 (2026-09-17): portfolio.beta_floor, the trend-gated beta floor's pure sizing step. No network.

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_round42_flags
"""
import unittest

import portfolio


def _gross(w):
    return sum(abs(x) for x in w.values())


def _beta(w, betas):
    return sum(x * (1.0 if t.startswith("__") else betas.get(t, 1.0)) for t, x in w.items())


class BetaFloor(unittest.TestCase):
    def test_room_under_the_cap_adds_the_sleeve_only(self):
        w = {"D": 0.4, "ES": 0.4}
        betas = {"D": 0.0, "ES": 0.25}
        out = portfolio.beta_floor(w, betas, floor=0.5, cap=1.5)
        self.assertEqual(out["D"], 0.4)
        self.assertEqual(out["ES"], 0.4)
        self.assertAlmostEqual(out["__SLEEVE__"], 0.4)            # 0.5 - 0.1
        self.assertAlmostEqual(_beta(out, betas), 0.5)
        self.assertLessEqual(_gross(out), 1.5)

    def test_at_the_cap_the_stocks_shrink_so_gross_is_the_cap_and_beta_the_floor(self):
        w = {"D": 0.7, "ES": 0.7}                                  # gross 1.4, beta 0.14
        betas = {"D": 0.1, "ES": 0.1}
        out = portfolio.beta_floor(w, betas, floor=0.5, cap=1.5)
        self.assertAlmostEqual(_gross(out), 1.5)
        self.assertAlmostEqual(_beta(out, betas), 0.5)
        self.assertLess(out["D"], 0.7)
        self.assertAlmostEqual(out["D"], out["ES"])                # proportional shrink keeps the composition

    def test_a_book_at_or_above_the_floor_is_unchanged(self):
        w = {"NVDA": 0.5, "AMD": 0.5}
        self.assertEqual(portfolio.beta_floor(w, {"NVDA": 1.4, "AMD": 1.3}, 0.5, 1.5), w)
        w2 = {"D": 0.3, "__SLEEVE__": 0.6}                         # the idle sleeve already carries the beta
        self.assertEqual(portfolio.beta_floor(w2, {"D": 0.0}, 0.5, 1.5), w2)

    def test_missing_betas_default_to_one_and_other_overlays_are_kept(self):
        w = {"XYZ": 0.2, "__HEDGE__": -0.1}
        out = portfolio.beta_floor(w, {}, floor=0.5, cap=1.5)       # XYZ counts as beta 1.0 -> book beta 0.2
        self.assertEqual(out["__HEDGE__"], -0.1)
        self.assertAlmostEqual(out["__SLEEVE__"], 0.3)

    def test_an_empty_book_gets_the_floor_in_the_sleeve(self):
        out = portfolio.beta_floor({}, {}, floor=0.5, cap=1.5)
        self.assertAlmostEqual(out["__SLEEVE__"], 0.5)


if __name__ == "__main__":
    unittest.main()
