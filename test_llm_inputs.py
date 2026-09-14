"""The Claude readers see transcripts only: earnings-call and conference statements, never SEC filings or notes.

    set ALPACA_API_KEY=x && set ALPACA_SECRET_KEY=x && python -m unittest -v test_llm_inputs
"""
import unittest

from agents import llm_guidance, llm_supply


def _row(label, signal="s"):
    return {"quarter": label, "signal": signal, "figure": "no specific figure", "chain": "x"}


class GuidanceWindow(unittest.TestCase):
    def test_filings_and_notes_dropped_calls_and_conferences_kept_newest_first(self):
        node = {"quarterly_data": [
            _row("Meta 10-K (01-29-2026)"), _row("Meta 10-Q (07-30-2026)"), _row("Microsoft 8-K (09-02-2026)"),
            _row("Goldman Sachs optical note (04-17-2026)"),
            _row("Meta Q1 FY2026 (04-29-2026)", "call one"), _row("NVIDIA GTC Taipei 2026 (06-01-2026)", "keynote"),
            _row("Meta Q2 FY2026 (07-29-2026)", "call two"), _row("Meta Q2 FY2026 (07-29-2026)", "call two"),
        ]}
        labels = [q["quarter"] for q in llm_guidance._own_signals(node)]
        self.assertEqual(labels, ["Meta Q2 FY2026 (07-29-2026)", "NVIDIA GTC Taipei 2026 (06-01-2026)",
                                  "Meta Q1 FY2026 (04-29-2026)"])

    def test_window_is_capped_at_max_signals(self):
        node = {"quarterly_data": [_row(f"Meta Q1 FY{2000 + i} (01-01-{2000 + i})", f"s{i}") for i in range(20)]}
        self.assertEqual(len(llm_guidance._own_signals(node)), llm_guidance.MAX_SIGNALS)


class SupplyReport(unittest.TestCase):
    def test_filing_statement_lines_dropped_deal_lines_and_headings_kept(self):
        report = "\n".join([
            "# Supply-chain position of Meta",
            "## Latest signals from its own calls / filings (30 on record, newest 10 shown)",
            "- [Meta 10-K (01-29-2026)] filing text",
            "- [Meta Q2 FY2026 (07-29-2026)] call text — figure: 1",
            "## Suppliers → Meta (2 edges)",
            "- **NVIDIA** — supplier",
            "  latest deal [NVIDIA 10-K (02-26-2026)]: deal text",
            "## Read-through: what Meta's customers said",
            "- Microsoft [Microsoft 8-K (09-02-2026)] on nvidia_vera_rubin: filing",
            "- Microsoft [Microsoft Q4 FY2026 (07-29-2026)] on nvidia_vera_rubin: call",
        ])
        out = llm_supply._transcripts_only(report).split("\n")
        self.assertNotIn("- [Meta 10-K (01-29-2026)] filing text", out)
        self.assertNotIn("- Microsoft [Microsoft 8-K (09-02-2026)] on nvidia_vera_rubin: filing", out)
        self.assertIn("- [Meta Q2 FY2026 (07-29-2026)] call text — figure: 1", out)
        self.assertIn("  latest deal [NVIDIA 10-K (02-26-2026)]: deal text", out)
        self.assertIn("- Microsoft [Microsoft Q4 FY2026 (07-29-2026)] on nvidia_vera_rubin: call", out)
        self.assertIn("## Suppliers → Meta (2 edges)", out)

    def test_unavailable_report_passes_through(self):
        self.assertEqual(llm_supply._transcripts_only("SUPPLY_CHAIN_UNAVAILABLE: x"), "SUPPLY_CHAIN_UNAVAILABLE: x")


if __name__ == "__main__":
    unittest.main()
