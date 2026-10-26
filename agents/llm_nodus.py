"""LLM Nodus agent — Claude reads everything the Nodus42 map (earnings-ai) holds on one company, plus the map's
market-wide series, and gives one overall opinion (user 2026-10-26: "nodus에 있는 모든 정보 다 읽은 담에 판단 ...
모든 거 nodus에서 종합판단").

Per name: identity and chain roles, the curated screener, the financial statements and consensus estimates, the next
earnings date, insider trades, financing, the map's exposure record, every AI-chain supplier and customer with their
deals, the non-AI relationships, and every own statement (filings included), newest first. For every name: memory
spot prices and TrendForce releases, GPU rental prices, hyperscaler capex and backlog.

Read straight from earnings-ai/graph (read-only), not through the Nodus42 MCP server (user: "mcp로 읽지마"): the MCP
serves only the graph, the screener and the evidence, and a tool round trip per section costs more time and tokens
than one prompt. One call per name; no answer reuse, because the market block changes every day.
"""
import functools
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import config
import market
from agents import llm
from agents.base import Signal
from agents.llm_guidance import _label_date
from agents.supply_chain import _load

log = logging.getLogger(__name__)
NAME = "llm_nodus"
DOSSIER_CHARS = None       # per-name cap (None = none; user 2026-10-26: "글자제한 두지 말고"); the facts come last, newest first, so a
                           # cap would drop the oldest. Measured 2026-10-26 on the 270 names: median 32.8k chars, largest NVDA 209k
                           # (~96k tokens); ~4.7M input tokens a day uncapped.
                           # Micron head to head: this dossier in one prompt 20 s / 49k input tokens; the same model reading
                           # the map through the MCP 47 s / 266k tokens over 13 turns, without the financials or insider data
FIN_QUARTERS = 8           # quarterly rows of the financial statements
INSIDER_DAYS = 90          # insider trades: totals over this window and its latest rows
INSIDER_ROWS = 15
FINANCING_DAYS = 365
TRENDFORCE_ROWS = 12       # latest TrendForce memory price releases

SYSTEM = (
    "You are the lead analyst of a portfolio that trades the AI semiconductor and infrastructure supply chain. You are "
    "given everything the Nodus42 map holds on one company: its own statements from earnings calls, filings, IR "
    "releases and executive interviews (each with its source label), its suppliers and customers with their deals, "
    "its financial statements and consensus estimates, insider trades, financing, and the curated screener, plus "
    "market-wide series from the same map (memory spot prices, GPU rental prices, hyperscaler capex) and the stock's "
    "recent move against SOXX. Weigh all of it together and decide whether the stock is likely to beat the SOXX "
    "semiconductor index over the next 1-4 weeks: demand and pricing for what it sells, its position in each chain, "
    "the trend in its numbers against expectations, what insiders and financing say, and how much the price already "
    "reflects. Name the facts that drive the call. Use direction near 0 and low confidence when the evidence is thin, "
    "stale or mixed."
)

FOOTER = ("Trading is commission-free but each order costs about 5 bps in slippage, and there is no obligation to trade: "
          "a direction near 0 with low confidence is a valid answer. Give your opinion as JSON.")


def _graph_dir():
    return config.EARNINGS_AI_DIR / "graph"


def _json(*parts):
    """graph/<parts> as JSON; {} when the file is missing or unreadable (one bad file must not silence the agent)."""
    path = _graph_dir().joinpath(*parts)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


@functools.lru_cache(maxsize=1)
def _data():
    graph, exposure, _ = _load()
    ins, outs, other = {}, {}, {}
    for e in graph["edges"]:
        outs.setdefault(e["source"], []).append(e)
        ins.setdefault(e["target"], []).append(e)
    for e in graph.get("other_edges", []):
        other.setdefault(e["source"], []).append(e)
        other.setdefault(e["target"], []).append(e)
    cash = _json("hyperscaler_cash.json")
    calendar = {}
    for c in sorted(cash.get("calendar", []), key=lambda c: c.get("date") or ""):
        if (c.get("date") or "") >= date.today().isoformat():
            calendar.setdefault(c["id"], c)
    return {"nodes": {n["id"]: n for n in graph["nodes"]}, "in": ins, "out": outs, "other": other,
            "exposure": exposure.get("companies", {}), "screener": _json("company_metrics.json"),
            "financials": _json("financials_index.json").get("companies", {}),
            "insiders": _json("insiders_index.json").get("companies", {}),
            "financing": _json("financing_index.json").get("companies", {}),
            "calendar": calendar, "hyperscaler": {c["id"]: c for c in cash.get("companies", [])}}


def _num(x):
    if x is None or x == "":
        return "—"
    if isinstance(x, (int, float)):
        return f"{x:,.0f}" if abs(x) >= 100 else f"{x:,.2f}"
    return str(x)


def _pct(part, whole):
    return f"{part / whole * 100:.1f}%" if part is not None and whole else "—"


def _company_file(kind, nid):
    entry = _data()[kind].get(nid)
    return _json(kind, entry["file"]) if entry and entry.get("file") else {}


def _label(q):
    return q.get("quarter") or q.get("source") or ""


def _fact(q):
    fig = q.get("figure")
    return (f"[{_label(q)}] {q.get('signal') or ''}"
            + (f" — figure: {fig}" if fig and str(fig) not in ("no specific figure", "not stated") else ""))


def _identity(nid, n, price_line):
    roles = "; ".join(" / ".join(str(p[k]) for k in ("chain", "layer", "domain", "sector", "product") if p.get(k))
                      for p in n.get("products", []))
    return (f"Company: {nid} ({n.get('ticker')}, {n.get('exchange')}, {n.get('country')})\n{price_line}\n"
            f"Chain roles: {roles or 'none recorded'}")


def _screener(nid):
    m = _data()["screener"].get(nid)
    if not isinstance(m, dict):
        return ""
    return "Curated screener:\n" + "\n".join(f"- {k}: {v}" for k, v in m.items() if v and v != "—")


def _financials(nid):
    f = _company_file("financials", nid)
    if not f.get("quarterly") and not f.get("annual"):
        return ""
    unit = {1: "", 1000: " thousands", 1000000: " millions", 1000000000: " billions"}.get(f.get("unit"), f" x{f.get('unit')}")
    lines = [f"Financial statements ({f.get('currency')}{unit}; updated {f.get('updated')}; fiscal year ends {f.get('fiscal_year_end')}):"]
    for q in (f.get("quarterly") or [])[-FIN_QUARTERS:] + (f.get("annual") or [])[-2:]:
        rev = q.get("revenue")
        lines.append(f"- {q.get('label')} (to {q.get('end')}): revenue {_num(rev)}, gross margin {_pct(q.get('gross_profit'), rev)}, "
                     f"operating margin {_pct(q.get('operating_income'), rev)}, net income {_num(q.get('net_income'))}, "
                     f"diluted EPS {_num(q.get('eps_diluted'))}, FCF {_num(q.get('fcf'))}, capex {_num(q.get('capex'))}, "
                     f"revenue QoQ {_num((q.get('qoq') or {}).get('revenue'))}%, YoY {_num((q.get('yoy') or {}).get('revenue'))}%, "
                     f"P/E {_num(q.get('per'))}")
    for key in ("quarter", "fy", "next_fy"):
        e = (f.get("estimates") or {}).get(key)
        if e:
            lines.append(f"- consensus {e.get('label')} (to {e.get('end')}): revenue {_num(e.get('revenue_avg'))} "
                         f"({_num(e.get('revenue_low'))}-{_num(e.get('revenue_high'))}, {e.get('revenue_analysts')} analysts, "
                         f"{_num(e.get('revenue_growth_pct'))}% growth); EPS {_num(e.get('eps_avg'))} "
                         f"({_num(e.get('eps_low'))}-{_num(e.get('eps_high'))}, {_num(e.get('eps_growth_pct'))}% growth)")
    if f.get("preliminary"):
        lines.append(f"- preliminary: {json.dumps(f['preliminary'], ensure_ascii=False)}")
    return "\n".join(lines)


def _calendar(nid):
    c = _data()["calendar"].get(nid)
    return f"Next earnings: {c['date']} ({c.get('time')}, {'confirmed' if c.get('confirmed') else 'not confirmed'})" if c else ""


def _insiders(nid, today):
    rows = [r for r in _company_file("insiders", nid).get("rows", [])
            if (r.get("date") or "") >= (today - timedelta(days=INSIDER_DAYS)).isoformat()]
    if not rows:
        return ""
    totals = {}
    for r in rows:
        t = totals.setdefault(r.get("type") or "?", [0, 0.0])
        t[0] += 1
        t[1] += r.get("value") or 0
    cur = rows[0].get("currency") or ""
    lines = [f"Insider trades, last {INSIDER_DAYS} days: "
             + "; ".join(f"{k} {n} ({_num(v)} {cur})" for k, (n, v) in sorted(totals.items()))]
    for r in sorted(rows, key=lambda r: r.get("date") or "", reverse=True)[:INSIDER_ROWS]:
        lines.append(f"- {r.get('date')} {r.get('insider')} ({r.get('role')}): {r.get('type')} {_num(r.get('shares'))} sh "
                     f"at {_num(r.get('price'))} = {_num(r.get('value'))} {r.get('currency') or ''}"
                     + (" (10b5-1 plan)" if r.get("plan_10b5_1") else ""))
    return "\n".join(lines)


def _financing(nid, today):
    rows = [r for r in _company_file("financing", nid).get("rows", [])
            if (r.get("date") or "") >= (today - timedelta(days=FINANCING_DAYS)).isoformat()]
    if not rows:
        return ""
    return "Financing, last 12 months:\n" + "\n".join(
        f"- {r.get('date')} {r.get('type')}: {r.get('title')} (USD {_num(r.get('amount_usd'))})"
        for r in sorted(rows, key=lambda r: r.get("date") or "", reverse=True))


def _cash(nid):
    c = _data()["hyperscaler"].get(nid)
    if not c:
        return ""
    return "Cash flow by quarter (USD):\n" + "\n".join(
        f"- {q.get('period')}: capex {_num(q.get('capex_usd'))}, operating cash flow {_num(q.get('ocf_usd'))}, "
        f"FCF after leases {_num(q.get('fcf_after_leases_usd'))}" for q in c.get("quarters", []))


def _exposure(nid):
    e = _data()["exposure"].get(nid)
    if not e:
        return ""
    lines = [f"Map exposure: primary role {e.get('primary')}; {e.get('signals')} statements, newest {e.get('latest')}; "
             f"{e.get('counterparties')} counterparties, {e.get('contracts_total')} deals",
             f"- topics: {json.dumps(e.get('topics') or {}, ensure_ascii=False)}",
             f"- generation transitions: {json.dumps(e.get('generations') or {}, ensure_ascii=False)}",
             f"- score by chain: {json.dumps(e.get('score_by_chain') or {}, ensure_ascii=False)}"]
    for k, v in (e.get("slots") or {}).items():
        lines.append(f"- {k}: {v} [{(e.get('slot_sources') or {}).get(k, '?')}]")
    for c in e.get("concentration") or []:
        lines.append(f"- concentration: {c.get('counterparty')} ({c.get('role')}, {c.get('pct') if c.get('pct') is not None else '?'}%)")
    return "\n".join(lines)


def _edges(nid):
    d = _data()
    lines = []
    for title, edges, other_side in (("Suppliers (AI chains)", d["in"].get(nid, []), "source"),
                                     ("Customers (AI chains)", d["out"].get(nid, []), "target")):
        if not edges:
            continue
        lines.append(f"{title}:")
        for e in edges:
            lines.append(f"- {e[other_side]}: {e.get('relationship')} [{e.get('chain')}]")
            for c in sorted(e.get("contracts", []), key=lambda c: _label_date(_label(c)) or date.min, reverse=True):
                lines.append(f"    deal {_fact(c)}")
    others = d["other"].get(nid, [])
    if others:
        lines.append("Other relationships (non-AI):")
        lines += [f"- {e['source']} -> {e['target']} ({e.get('relation')}): {e.get('relationship')} "
                  f"[{((e.get('refs') or [{}])[0]).get('label', '?')}]" for e in others]
    return "\n".join(lines)


def _facts(n):
    seen, rows = set(), []
    for q in n.get("quarterly_data") or []:
        key = (_label(q), (q.get("signal") or "")[:80])
        if key not in seen:
            seen.add(key)
            rows.append(q)
    rows.sort(key=lambda q: _label_date(_label(q)) or date.min, reverse=True)
    return f"The company's own statements, newest first ({len(rows)}):\n" + "\n".join(f"- {_fact(q)}" for q in rows) if rows else ""


def dossier(nid, price_line, today=None):
    """The company block of the prompt, cut at DOSSIER_CHARS when one is set; None when the map has no node for it."""
    n = _data()["nodes"].get(nid)
    if not n:
        return None
    today = today or date.today()
    parts = [_identity(nid, n, price_line), _calendar(nid), _screener(nid), _financials(nid), _cash(nid),
             _insiders(nid, today), _financing(nid, today), _exposure(nid), _edges(nid), _facts(n)]
    out = "\n\n".join(p for p in parts if p)
    return out if DOSSIER_CHARS is None else out[:DOSSIER_CHARS]


def _series_change(s):
    pts = s.get("points") or []
    if len(pts) < 2:
        return ""
    (d0, v0), (d1, v1) = pts[0], pts[-1]
    return f"- {s.get('label')} ({s.get('unit')}): {d0} {_num(v0)} -> {d1} {_num(v1)}" + (f" ({(v1 / v0 - 1) * 100:+.1f}%)" if v0 else "")


def market_block():
    """Market-wide series from the map, the same for every name."""
    mem, gpu, capex = _json("memory_prices.json"), _json("gpu_prices.json"), _json("capex_backlog.json")
    lines = [f"Memory prices (updated {mem.get('updated')}; {mem.get('attribution')}):"]
    lines += [_series_change(s) for s in mem.get("series", [])]
    for t in mem.get("tables", []):
        if t.get("id") == "trendforce_memory_releases":
            lines.append("TrendForce memory price releases, newest first:")
            lines += [f"- {r[0]}: {r[1]}" + (f" ({r[3]})" if len(r) > 3 and r[3] else "") for r in t.get("rows", [])[:TRENDFORCE_ROWS]]
    lines.append(f"\nGPU rental prices (updated {gpu.get('updated')}), weekly medians:")
    lines += [_series_change({**s, "points": (s.get("points") or [])[-13:]}) for s in gpu.get("series", []) if "getdeploying" in s.get("id", "")]
    for t in gpu.get("tables", []):
        if t.get("id") == "shadeform_today":
            lines.append(f"{t.get('title')}: " + "; ".join(f"{r[0]} median {_num(r[1])}" for r in t.get("rows", [])))
    lines.append(f"\nHyperscaler capex and backlog (updated {capex.get('updated')}):")
    lines += [f"- {t.get('label')}: {t.get('value')} ({t.get('delta')}) — {t.get('detail')} [{t.get('source')}]" for t in capex.get("tiles", [])]
    lines += [f"- {b.get('name')}: {b.get('display')} ({b.get('period')})" for b in (capex.get("capex_bars") or {}).get("bars", [])]
    return "\n".join(x for x in lines if x)


def _one(ticker, nid, price_line, system):
    try:
        block = dossier(nid, price_line)
        if not block:
            return None
        o = llm.ask_json(system, f"{block}\n\n{FOOTER}")
    except llm.StageDeadline:   # the cycle's Claude stage was cut: quiet, the stage log carries the count
        return None
    except Exception as exc:    # one bad call or file must not kill the cycle
        log.warning("%s %s: %s", NAME, ticker, exc)
        return None
    return Signal(NAME, ticker, o["direction"], o["confidence"], int(o["horizon_days"]), str(o["reason"])[:200]).clipped()


def run(universe: dict, ctx: dict) -> list[Signal]:
    if not llm.ensure_server():
        return []
    _data()
    system = f"{SYSTEM}\n\nMarket-wide data from the same map:\n{market_block()}"
    closes = ctx["closes"]
    live = market.live_prices(list(universe) + [config.BENCHMARK])   # today's pre-market trades where there are any (user 2026-09-15)
    with ThreadPoolExecutor(max_workers=config.LLM_WORKERS) as pool:
        results = list(pool.map(lambda kv: _one(kv[0], kv[1], market.move_line(closes, kv[0], live), system), universe.items()))
    return [s for s in results if s]
