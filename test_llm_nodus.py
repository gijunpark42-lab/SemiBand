"""llm_nodus (2026-10-26): the whole-map dossier per name, the shared market block, and a failed call staying quiet.

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_llm_nodus
"""
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import config
from agents import llm, llm_nodus, supply_chain

TODAY = date(2026, 10, 26)


class Dossier(unittest.TestCase):
    def setUp(self):
        graph = {
            "nodes": [{"id": "Chip A", "ticker": "CA", "exchange": "NASDAQ", "country": "US",
                       "products": [{"chain": "hbm_memory", "layer": "memory", "sector": "HBM", "product": "HBM4 stacks"}],
                       "quarterly_data": [
                           {"quarter": "Chip A Q1 FY2026 (01-15-2026)", "signal": "old call", "figure": "no specific figure"},
                           {"quarter": "Chip A 10-Q (07-30-2026)", "signal": "filing line", "figure": "$5B"},
                           {"quarter": "Chip A Q3 FY2026 (10-20-2026)", "signal": "newest call", "figure": "$9B"}]},
                      {"id": "Buyer B", "quarterly_data": []}],
            "edges": [{"source": "Chip A", "target": "Buyer B", "relationship": "HBM supply", "chain": "hbm_memory",
                       "contracts": [{"quarter": "Buyer B Q2 FY2026 (08-01-2026)", "signal": "multi-year HBM deal", "figure": "$2B"}]}],
            "other_edges": [{"source": "Chip A", "target": "Bank C", "relation": "partner", "relationship": "credit line",
                             "refs": [{"label": "Chip A 8-K (05-01-2026)"}]}],
        }
        self.tmp = tempfile.TemporaryDirectory()
        g = Path(self.tmp.name) / "graph"
        for d in ("financials", "insiders"):
            (g / d).mkdir(parents=True)

        def write(name, obj):
            (g / name).write_text(json.dumps(obj), encoding="utf-8")

        write("merged_graph.json", graph)
        write("exposure.json", {"companies": {"Chip A": {"primary": "memory", "signals": 3, "topics": {"hbm": 2}}}})
        write("company_metrics.json", {"Chip A": {"guidance": "Q4 guide raised", "asof": "2026-10-20"}})
        write("financials_index.json", {"companies": {"Chip A": {"file": "chip-a.json"}}})
        write("financials/chip-a.json", {"currency": "USD", "unit": 1000000, "quarterly": [
            {"label": "Q3 26", "end": "2026-09-30", "revenue": 1000.0, "gross_profit": 600.0, "operating_income": 400.0,
             "qoq": {"revenue": 12.0}, "yoy": {"revenue": 80.0}}],
            "estimates": {"quarter": {"label": "Q4 26", "end": "2026-12-31", "revenue_avg": 1100.0, "eps_avg": 2.5}}})
        write("insiders_index.json", {"companies": {"Chip A": {"file": "chip-a.json"}}})
        write("insiders/chip-a.json", {"rows": [
            {"date": "2026-10-10", "insider": "CEO X", "role": "CEO", "type": "sell", "shares": 1000, "price": 50.0,
             "value": 50000.0, "currency": "USD", "plan_10b5_1": True},
            {"date": "2026-01-02", "insider": "CFO Y", "role": "CFO", "type": "buy", "shares": 10, "price": 40.0,
             "value": 400.0, "currency": "USD"}]})
        write("memory_prices.json", {"updated": "2026-10-25", "series": [
            {"label": "DDR5 16Gb", "unit": "USD per chip", "points": [["2026-10-16", 50.0], ["2026-10-26", 55.0]]}]})
        self.patch = patch.object(config, "EARNINGS_AI_DIR", Path(self.tmp.name))
        self.patch.start()
        supply_chain._load.cache_clear()
        llm_nodus._data.cache_clear()

    def tearDown(self):
        self.patch.stop()
        supply_chain._load.cache_clear()
        llm_nodus._data.cache_clear()
        self.tmp.cleanup()

    def test_every_section_and_facts_newest_first_filings_kept(self):
        d = llm_nodus.dossier("Chip A", "PRICE LINE", TODAY)
        for part in ("Company: Chip A (CA", "PRICE LINE", "HBM4 stacks", "Q4 guide raised", "gross margin 60.0%",
                     "consensus Q4 26", "CEO X", "Map exposure", "Buyer B: HBM supply", "multi-year HBM deal",
                     "Bank C (partner): credit line"):
            self.assertIn(part, d)
        self.assertLess(d.index("newest call"), d.index("filing line"))
        self.assertLess(d.index("filing line"), d.index("old call"))
        self.assertNotIn("CFO Y", d)            # older than INSIDER_DAYS

    def test_cut_at_the_cap_keeps_the_head(self):
        with patch.object(llm_nodus, "DOSSIER_CHARS", 120):
            d = llm_nodus.dossier("Chip A", "PRICE LINE", TODAY)
        self.assertEqual(len(d), 120)
        self.assertTrue(d.startswith("Company: Chip A"))

    def test_unknown_company_abstains(self):
        self.assertIsNone(llm_nodus.dossier("Nobody", "PRICE LINE", TODAY))

    def test_market_block_survives_missing_files(self):
        block = llm_nodus.market_block()        # no gpu_prices.json or capex_backlog.json in the fixture
        self.assertIn("DDR5 16Gb", block)
        self.assertIn("+10.0%", block)

    def test_failed_call_is_quiet_and_good_call_is_a_signal(self):
        with patch.object(llm, "ask_json", side_effect=RuntimeError("boom")):
            self.assertIsNone(llm_nodus._one("CA", "Chip A", "PRICE LINE", "SYS"))
        answer = {"direction": 0.4, "confidence": 0.5, "horizon_days": 20, "reason": "deal"}
        with patch.object(llm, "ask_json", return_value=answer) as ask:
            s = llm_nodus._one("CA", "Chip A", "PRICE LINE", "SYS")
        self.assertEqual((s.agent, s.ticker, s.direction), ("llm_nodus", "CA", 0.4))
        self.assertEqual(ask.call_args.args[0], "SYS")


if __name__ == "__main__":
    unittest.main()
