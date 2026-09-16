"""Open refresh and signal reuse: cycle.open_refresh, ledger.predictions_on / replace_predictions. No network.

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_open_refresh
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import cycle
import ledger
from agents.base import Signal


class Ledger(unittest.TestCase):
    def test_replace_swaps_only_the_named_agents_and_reuse_reads_them_back(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(ledger, "DB", Path(tmp) / "ledger.sqlite"):
            ledger.add_predictions("2026-09-14", [Signal("technical", "NVDA", 0.2, 0.5, 10, "pre-open"),
                                                  Signal("llm_news", "NVDA", 0.4, 0.6, 20, "claude")],
                                   {"NVDA": 100.0}, {"NVDA": 1.2})
            ledger.replace_predictions("2026-09-14", ["technical"], [Signal("technical", "NVDA", -0.3, 0.5, 10, "open")],
                                       {"NVDA": 95.0}, {"NVDA": 1.2})
            rows = {(r["agent"], r["ticker"]): r for r in ledger.predictions_on("2026-09-14")}
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[("technical", "NVDA")]["reason"], "open")
            self.assertEqual(rows[("llm_news", "NVDA")]["reason"], "claude")
            self.assertEqual(ledger.predictions_on("2026-09-11"), [])


class OpenRefresh(unittest.TestCase):
    def setUp(self):
        idx = pd.to_datetime(["2026-09-10", "2026-09-11"])
        self.closes = pd.DataFrame({"NVDA": [100.0, 102.0], "AMD": [50.0, 51.0], "SOXX": [500.0, 527.0],
                                    "SPY": [760.0, 764.0], "^VIX": [15.0, 16.0], "^TNX": [4.0, 4.1]}, index=idx)
        self.universe = {"NVDA": "NVIDIA", "AMD": "AMD"}
        self.pre = [Signal("technical", "NVDA", 0.5, 0.5, 10, "pre"), Signal("llm_news", "NVDA", 0.3, 0.6, 20, "claude"),
                    Signal("macro", "AMD", 0.1, 0.4, 10, "pre"), Signal("risk", "AMD", -0.2, 0.5, 10, "pre")]

    def test_price_agents_rerun_on_a_live_row_and_everything_else_is_kept(self):
        seen = {}

        def fake_run(name, universe, ctx):
            seen[name] = ctx["closes"]
            return [] if name == "risk" else [Signal(name, "NVDA", -0.4, 0.5, 10, "open")]

        notes = []
        with patch.object(cycle.market, "live_prices", return_value={"NVDA": 97.0, "SOXX": 502.0}), \
                patch.object(cycle.market, "index_levels", return_value={"^TNX": 43.0, "^VIX": 30.0}), \
                patch.object(cycle.market, "closes", return_value=self.closes), \
                patch.object(cycle, "_run_agent", side_effect=fake_run), \
                patch.object(cycle.ledger, "replace_predictions") as replace, \
                patch.object(cycle.config, "OPEN_REFRESH_AGENTS", ("technical", "risk", "macro")):
            signals, live = cycle.open_refresh(self.universe, self.pre, "2026-09-14", {"NVDA": 1.2}, notes)
        frame = seen["technical"]
        self.assertEqual(frame.index[-1], pd.Timestamp("2026-09-14"))
        self.assertEqual(frame.loc["2026-09-14", "NVDA"], 97.0)       # today's print
        self.assertEqual(frame.loc["2026-09-14", "AMD"], 51.0)        # no print today: last close
        self.assertEqual(frame.loc["2026-09-14", "^VIX"], 30.0)       # a real spike (+88%) is used
        self.assertEqual(frame.loc["2026-09-14", "^TNX"], 4.1)        # 43.0 is ten times the history's scale: last close kept
        by = {(s.agent, s.ticker): s for s in signals}
        self.assertEqual(by[("technical", "NVDA")].reason, "open")
        self.assertEqual(by[("llm_news", "NVDA")].reason, "claude")
        self.assertNotIn(("macro", "AMD"), by)                        # macro re-ran: its fresh output replaces the old
        self.assertEqual(by[("risk", "AMD")].reason, "pre")           # risk returned nothing: pre-open signal kept
        self.assertEqual(replace.call_args.args[1], ["technical", "macro"])
        self.assertEqual(live, {"NVDA": 97.0, "SOXX": 502.0})
        self.assertIn("SOXX -4.7% vs last close", notes[0])

    def test_no_live_prices_keeps_the_pre_open_signals(self):
        with patch.object(cycle.market, "live_prices", return_value={}), patch.object(cycle, "_run_agent") as run:
            signals, live = cycle.open_refresh(self.universe, self.pre, "2026-09-14", {}, [])
        self.assertEqual(signals, self.pre)
        self.assertEqual(live, {})
        run.assert_not_called()


class Fundamentals(unittest.TestCase):
    def test_live_price_reprices_the_valuation_ratios_without_touching_the_cache(self):
        from agents import fundamentals
        info = {"NVDA": {"currentPrice": 100.0, "targetMeanPrice": 122.0, "numberOfAnalystOpinions": 10,
                         "forwardPE": 62.0, "priceToSalesTrailing12Months": 16.0}}
        with patch.object(fundamentals.market, "fundamentals", return_value=info):
            before = fundamentals.run({"NVDA": "NVIDIA"}, {})[0]
            after = fundamentals.run({"NVDA": "NVIDIA"}, {"live_prices": {"NVDA": 95.0}})[0]
        self.assertLess(before.direction, 0)                   # fwd PE 62 and P/S 16 penalised, target only +22%
        self.assertGreater(after.direction, 0)                 # at 95: fwd PE 59 (no penalty), target +28%
        self.assertIn("target +28%", after.reason)
        self.assertEqual(info["NVDA"]["currentPrice"], 100.0)   # the day's cache is not modified


class LiveLabels(unittest.TestCase):
    def test_label_starts_at_the_close_before_the_prediction_date(self):
        import numpy as np
        import config
        import learner
        import score
        idx = pd.bdate_range("2024-01-01", periods=100)
        closes = pd.DataFrame({"SOXX": np.linspace(100, 160, 100), "AAA": np.linspace(50, 120, 100)}, index=idx)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(config, "STATE_DIR", root), patch.object(ledger, "DB", root / "ledger.sqlite"), \
                    patch.object(config, "AGENTS", ["technical"]), patch.object(config, "HORIZONS", (10,)), \
                    patch.object(learner, "fit", return_value={"effective_weights": {}, "horizons": {}}):
                ledger.add_predictions(str(idx[60].date()), [Signal("technical", "AAA", 1.0, 0.5, 10, "")], {"AAA": 1.0}, {"AAA": 1.0})
                score.run(closes, str(idx[90].date()))
                with ledger.connect() as con:
                    ret, bench_ret = con.execute("SELECT ret, bench_ret FROM scores").fetchone()
        self.assertAlmostEqual(ret, closes.AAA.iloc[69] / closes.AAA.iloc[59] - 1)
        self.assertAlmostEqual(bench_ret, closes.SOXX.iloc[69] / closes.SOXX.iloc[59] - 1)


class MoveLine(unittest.TestCase):
    def test_uses_todays_trade_when_there_is_one_and_the_last_close_otherwise(self):
        import market
        idx = pd.bdate_range("2026-08-01", periods=30)
        closes = pd.DataFrame({"NVDA": [100.0] * 29 + [110.0], "SOXX": [500.0] * 30}, index=idx)
        with_live = market.move_line(closes, "NVDA", {"NVDA": 90.0, "SOXX": 450.0})
        self.assertIn("latest trade, pre-market included", with_live)
        self.assertIn("NVDA -10.0% over 20 trading days, SOXX -10.0% (relative +0.0%)", with_live)
        without = market.move_line(closes, "NVDA", {})
        self.assertIn("(last close): NVDA +10.0% over 20 trading days, SOXX +0.0%", without)
        self.assertEqual(market.move_line(closes, "AMD", {}), "Recent price move: unavailable")


class Sizing(unittest.TestCase):
    def test_min_stock_book_scales_few_names_up_within_the_cap(self):
        import config
        import portfolio
        with patch.object(config, "MIN_STOCK_BOOK", 0.5), patch.object(config, "MAX_POSITION_PCT", 0.30), \
                patch.object(config, "VOL_TARGET", None), patch.object(config, "MIN_CONVICTION", 0.10), \
                patch.object(config, "SIZE_PER_CONVICTION", 0.60):
            two = portfolio.targets({"A": 0.12, "B": 0.11, "C": 0.05}, 1_000_000)
            one = portfolio.targets({"A": 0.12}, 1_000_000)
        self.assertEqual(set(two), {"A", "B"})
        self.assertAlmostEqual(sum(two.values()), 500_000, delta=1)
        self.assertAlmostEqual(two["A"] / two["B"], 12 / 11, places=6)
        self.assertEqual(one, {"A": 300_000.0})
        with patch.object(config, "MIN_STOCK_BOOK", None), patch.object(config, "VOL_TARGET", None):
            self.assertAlmostEqual(portfolio.targets({"A": 0.12}, 1_000_000)["A"], 72_000, delta=1)


class IdleSleeve(unittest.TestCase):
    def setUp(self):
        idx = pd.bdate_range("2026-06-01", periods=60)
        self.up = pd.DataFrame({"SOXX": [100.0 + k for k in range(60)]}, index=idx)      # last close above its 50-day average
        self.down = pd.DataFrame({"SOXX": [160.0 - k for k in range(60)]}, index=idx)    # last close below it

    def patches(self, **extra):
        import config
        values = {"IDLE_SLEEVE": "SOXX", "IDLE_SLEEVE_FRACTION": 1.0, "IDLE_SLEEVE_TREND": 50, "VOL_TARGET": 0.50,
                  "HEDGE_SIZE": None, "MIN_ORDER_USD": 250, "REBALANCE_BAND": 0.30, "GROSS_TARGET": 1.5}
        values.update(extra)
        return [patch.object(config, k, v) for k, v in values.items()]

    def run_with(self, fn, **extra):
        ps = self.patches(**extra)
        for p in ps:
            p.start()
        try:
            return fn()
        finally:
            for p in ps:
                p.stop()

    def test_target_is_the_idle_share_in_an_uptrend_scaled_by_the_vol_target(self):
        import portfolio
        stocks = {"A": 100_000.0, "B": 50_000.0}
        self.assertAlmostEqual(self.run_with(lambda: portfolio.sleeve_target(stocks, 1_000_000, self.up)), 850_000, delta=1)
        # vol target halves exposure: total capped at 0.5, stocks already hold 0.15, so the sleeve fills 0.35
        self.assertAlmostEqual(self.run_with(lambda: portfolio.sleeve_target(stocks, 1_000_000, self.up, realized_vol=1.0)), 350_000, delta=1)
        self.assertEqual(self.run_with(lambda: portfolio.sleeve_target({"A": 600_000.0}, 1_000_000, self.up, realized_vol=1.0)), 0.0)
        self.assertEqual(self.run_with(lambda: portfolio.sleeve_target(stocks, 1_000_000, self.down)), 0.0)
        self.assertEqual(self.run_with(lambda: portfolio.sleeve_target(stocks, 1_000_000, self.up), HEDGE_SIZE=0.5, HEDGE_SYMBOL="SOXX"), 0.0)
        self.assertEqual(self.run_with(lambda: portfolio.sleeve_target(stocks, 1_000_000, self.up), IDLE_SLEEVE=None), 0.0)
        empty = self.up.assign(SOXX=float("nan"))                       # a failed download: never sell the sleeve over it
        self.assertIsNone(self.run_with(lambda: portfolio.sleeve_target(stocks, 1_000_000, empty)))
        self.assertIsNone(self.run_with(lambda: portfolio.sleeve_target(stocks, 1_000_000, self.up.drop(columns=["SOXX"]))))

    def test_orders_buy_hold_inside_the_band_and_close_when_off(self):
        import portfolio

        class Pos:
            def __init__(self, mv):
                self.market_value = str(mv)
        self.assertEqual(self.run_with(lambda: portfolio.plan_sleeve(850_000, {})),
                         [{"ticker": "SOXX", "side": "BUY", "notional": 850_000, "tag": "idle sleeve"}])
        self.assertEqual(self.run_with(lambda: portfolio.plan_sleeve(850_000, {"SOXX": Pos(800_000)})), [])
        self.assertEqual(self.run_with(lambda: portfolio.plan_sleeve(0.0, {"SOXX": Pos(800_000)})),
                         [{"ticker": "SOXX", "side": "SELL", "notional": None, "tag": "idle sleeve off"}])
        self.assertEqual(self.run_with(lambda: portfolio.plan_sleeve(300_000, {"SOXX": Pos(800_000)})),
                         [{"ticker": "SOXX", "side": "SELL", "notional": 500_000, "tag": "idle sleeve trim"}])

    def test_a_sleeve_sold_in_the_same_cycle_frees_the_stock_buy_budget(self):
        import portfolio

        class Pos:
            def __init__(self, mv):
                self.market_value = str(mv)
        # re-entry day: the model wants $600k of stock A while a $1.0M sleeve is still held (about to be sold)
        args = ({"A": 600_000.0}, {"SOXX": Pos(1_000_000)}, {"A": 0.5}, {"A": "Alpha"}, 1_000_000, 1_000_000)
        capped = self.run_with(lambda: portfolio.plan(*args))
        self.assertEqual(capped[0]["notional"], 500_000)                       # room to the 1.5x ceiling with the sleeve still counted
        freed = self.run_with(lambda: portfolio.plan(*args, extra_proceeds=1_000_000))
        self.assertEqual(freed[0]["notional"], 600_000)                        # the sleeve sale in the same cycle frees the room
        self.assertEqual(self.run_with(lambda: portfolio.plan(*args, extra_proceeds=-5.0))[0]["notional"], 500_000)   # never negative


class ForeignOrderGuard(unittest.TestCase):
    def test_our_orders_are_recognised_by_prefix_or_ledger_and_others_are_foreign(self):
        import broker
        from datetime import datetime, timezone
        from types import SimpleNamespace as NS
        when = datetime(2026, 9, 14, 13, 30, 35, tzinfo=timezone.utc)          # 09:30 ET on 2026-09-14
        orders = [NS(client_order_id="sb2-2026-09-14-NVDA-buy-1", symbol="NVDA", side=NS(value="buy"), submitted_at=when, created_at=when),
                  NS(client_order_id="9896ed79", symbol="SHEL", side=NS(value="sell"), submitted_at=when, created_at=when),
                  NS(client_order_id="other-bot-1", symbol="AMD", side=NS(value="buy"), submitted_at=when, created_at=when)]
        with patch.object(broker, "recent_orders", return_value=orders), \
                patch.object(ledger, "order_keys", return_value={("2026-09-14", "SHEL", "SELL")}):
            foreign = broker.foreign_orders(24)
        self.assertEqual([o.symbol for o in foreign], ["AMD"])

    def test_tagged_close_sends_a_market_order_for_the_whole_position(self):
        import broker
        from types import SimpleNamespace as NS
        sent = []
        with patch.object(broker._client, "get_open_position", return_value=NS(qty="786.6221")), \
                patch.object(broker._client, "submit_order", side_effect=lambda req: sent.append(req) or NS(id="x")), \
                patch.object(broker, "_dry", return_value=False):
            broker.close("SHEL", client_order_id="sb2-2026-09-15-SHEL-sell-1")
        self.assertEqual(sent[0].client_order_id, "sb2-2026-09-15-SHEL-sell-1")
        self.assertAlmostEqual(float(sent[0].qty), 786.6221)
        self.assertEqual(sent[0].symbol, "SHEL")


class LivePrices(unittest.TestCase):
    def test_a_print_after_the_open_wins_over_a_newer_looking_pre_market_print(self):
        import market
        from types import SimpleNamespace as NS
        now = pd.Timestamp.now(tz="UTC")
        open_utc = now - pd.Timedelta(seconds=40)
        pages = {"iex": {"NVDA": {"p": 101.0, "t": (open_utc + pd.Timedelta(seconds=10)).isoformat()},
                         "AMD": {"p": 55.0, "t": (open_utc - pd.Timedelta(minutes=20)).isoformat()}},
                 "delayed_sip": {"NVDA": {"p": 99.0, "t": (open_utc - pd.Timedelta(minutes=15)).isoformat()},
                                 "AMD": {"p": 54.0, "t": (open_utc - pd.Timedelta(minutes=15)).isoformat()}}}

        def fake_get(url, timeout=None, headers=None, params=None):
            return NS(raise_for_status=lambda: None, json=lambda: {"trades": pages[params["feed"]]})
        with patch("requests.get", side_effect=fake_get):
            prices = market.live_prices(["NVDA", "AMD"], prefer_after=open_utc)
        self.assertEqual(prices["NVDA"], 101.0)                      # the post-open print
        self.assertEqual(prices["AMD"], 54.0)                        # no post-open print yet: newest pre-market print


class MacroYields(unittest.TestCase):
    def test_ten_year_rule_reads_the_yield_in_percent(self):
        import numpy as np
        from agents import macro
        idx = pd.bdate_range("2025-09-01", periods=260)
        closes = pd.DataFrame({"SOXX": np.linspace(400, 500, 260), "SPY": np.linspace(600, 700, 260), "^VIX": [20.0] * 260,
                               "^TNX": [4.0] * 239 + list(np.linspace(4.0, 4.5, 21))}, index=idx)
        with patch.object(macro.market, "fred_latest", return_value=None):
            _, why = macro.regime(closes)
        self.assertIn("10y +0.50pt/20d", why)                        # the old "/ 10" made this +0.05 and the rule silent


if __name__ == "__main__":
    unittest.main()
