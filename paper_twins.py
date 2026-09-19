"""Paper twins (2026-09-18; user: "paper 여러 개 꽂고 전략 여러 개 체크해 볼까" → virtual books instead of extra accounts). Every cycle
builds counterfactual books from the SAME signals under alternative rules, records their target weights, and marks earlier books at
official prices with the replay's conventions (drifted holdings, COST_BPS per dollar traded), so each live change carries its
own control without extra Claude calls, accounts or orders. Books:
  live_model  the live targets (stocks + sleeve) marked like the replay: the strategy's own curve next to the account's
  open_exec   the same targets traded at the next open and held to the following open (the pre-09-21 execution)
  no_floor    the live sizing without the beta floor
  alt_conf    customer_momentum under the other confidence rule (constant 0.5 <-> 0.3 + 0.05 x customers)
  raw_target  the raw-return shadow model's convictions under the live sizing
State: state/paper_twins.json ({"books": {date: {name: {"weights", "mode"}}}, "curves": {name: [{date, ret, equity}]},
"drifted": {name: weights}}). A close-mode book dated t earns close t -> close t+1; an open-mode book dated t earns open t+1 ->
open t+2; both are marked at the first cycle that has the prices (two sessions later). Read-only on the market; no orders, no LLM.
"""
import json
import re

import pandas as pd

import config
import learner
import portfolio
from agents.base import Signal, clip

NAMES = ("live_model", "open_exec", "no_floor", "alt_conf", "raw_target")


def _path():
    return config.STATE_DIR / "paper_twins.json"


def load():
    p = _path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {"books": {}, "curves": {}, "drifted": {}}


def save(d):
    _path().write_text(json.dumps(d, indent=1), encoding="utf-8")


def demeaned(signals, model, groups):
    conv, _ = learner.predict(signals, model)
    if config.DEMEAN_CONVICTION and conv:
        conv, _ = learner.demean(conv, groups, config.DEMEAN_GROUP_MIN)
    return conv


def alt_conf_signals(signals):
    """customer_momentum's rows under the other confidence rule; every other signal unchanged."""
    out = []
    for s in signals:
        if s.agent == "customer_momentum":
            m = re.match(r"(\d+) customers", s.reason or "")
            n = int(m.group(1)) if m else 1
            conf = clip(0.3 + 0.05 * n, 0.3, 0.7) if config.MOMENTUM_CONF else 0.5
            s = Signal(s.agent, s.ticker, s.direction, conf, s.horizon, s.reason)
        out.append(s)
    return out


def book(convictions, equity, realized, closes, betas, floor=True):
    """{ticker: weight} incl. the sleeve ETF, under the live sizing rules (targets, the beta floor when `floor`, the sleeve rule)."""
    targets = portfolio.targets(convictions, equity, realized_vol=realized)
    sleeve = 0.0
    if floor and config.BETA_FLOOR:
        targets, floor_usd, _ = portfolio.apply_beta_floor(targets, betas, equity, closes, realized)
        sleeve = floor_usd
    if config.IDLE_SLEEVE:
        s = portfolio.sleeve_target(targets, equity, closes, realized)
        sleeve = max(sleeve, s or 0.0)
    w = {t: usd / equity for t, usd in targets.items()}
    if sleeve > 0 and config.IDLE_SLEEVE:
        w[config.IDLE_SLEEVE] = w.get(config.IDLE_SLEEVE, 0.0) + sleeve / equity
    return w


def books(signals, model, shadow_model, groups, convictions, target_usd, sleeve_usd, equity, realized, closes, betas):
    """The five books' target weights for today."""
    live = {t: usd / equity for t, usd in target_usd.items()}
    if sleeve_usd and config.IDLE_SLEEVE:
        live[config.IDLE_SLEEVE] = live.get(config.IDLE_SLEEVE, 0.0) + sleeve_usd / equity
    out = {"live_model": live, "open_exec": dict(live)}
    out["no_floor"] = book(convictions, equity, realized, closes, betas, floor=False)
    out["alt_conf"] = book(demeaned(alt_conf_signals(signals), model, groups), equity, realized, closes, betas)
    out["raw_target"] = book(demeaned(signals, shadow_model, groups), equity, realized, closes, betas) if shadow_model else {}
    return out


def record(today, twin_books, mode):
    d = load()
    d.setdefault("books", {})[today] = {name: {"weights": {t: round(x, 6) for t, x in w.items()}, "mode": "open" if name == "open_exec" else mode}
                                        for name, w in twin_books.items()}
    save(d)


def mark_book(prev_w, w, p0, p1):
    """One period of a book: (net return, drifted weights). Names without both prices earn nothing and keep their weight."""
    rets = {t: p1[t] / p0[t] - 1 for t in w if t in p0 and t in p1 and p0[t] and p0[t] > 0 and p1[t]}
    turnover = sum(abs(w.get(t, 0.0) - prev_w.get(t, 0.0)) for t in set(w) | set(prev_w))
    ret = sum(x * rets.get(t, 0.0) for t, x in w.items()) - turnover * config.COST_BPS / 10_000
    drifted = {t: x * (1 + rets.get(t, 0.0)) / (1 + ret) for t, x in w.items()} if ret > -1 else dict(w)
    return ret, drifted


def _closes_at(closes, day):
    if pd.Timestamp(day) not in closes.index:
        return None
    row = closes.loc[pd.Timestamp(day)]
    return {t: float(v) for t, v in row.items() if pd.notna(v)}


def mark(today, closes, opens_fn=None):
    """Mark every unmarked book whose prices exist: close-mode books from the closes frame, open-mode books from `opens_fn(dates)`
    -> {date: {ticker: open}} (Alpaca daily bars live; None = skip the open books). Returns the number of book-days marked."""
    d = load()
    sessions = [ts.date().isoformat() for ts in closes.index]
    done = {name: {c["date"] for c in d.get("curves", {}).get(name, [])} for name in NAMES}
    pending = sorted(day for day in d.get("books", {}) if day < today)
    need_open = sorted({day for day in pending if any(b.get("mode") == "open" for b in d["books"][day].values())})
    opens = {}
    if need_open and opens_fn is not None:
        wanted = set()
        for day in need_open:
            later = [s for s in sessions if s > day][:2]
            wanted.update(later)
        try:
            opens = opens_fn(sorted(wanted)) or {}
        except Exception:
            opens = {}
    n = 0
    for day in pending:
        for name, bk in d["books"][day].items():
            if day in done.get(name, set()) or not bk.get("weights"):
                continue
            w = bk["weights"]
            if bk.get("mode") == "open":
                later = [s for s in sessions if s > day][:2]
                if len(later) < 2 or later[0] not in opens or later[1] not in opens:
                    continue
                p0, p1 = opens[later[0]], opens[later[1]]
            else:
                later = [s for s in sessions if s > day][:1]
                p0 = _closes_at(closes, day)
                p1 = _closes_at(closes, later[0]) if later else None
                if p0 is None or p1 is None:
                    continue
            prev = d.get("drifted", {}).get(name, {})
            ret, drifted = mark_book(prev, w, p0, p1)
            curve = d.setdefault("curves", {}).setdefault(name, [])
            equity = (curve[-1]["equity"] if curve else 1.0) * (1 + ret)
            curve.append({"date": day, "ret": round(ret, 6), "equity": round(equity, 6)})
            d.setdefault("drifted", {})[name] = {t: round(x, 6) for t, x in drifted.items()}
            done.setdefault(name, set()).add(day)
            n += 1
    if n:
        save(d)
    return n


def summary():
    """{name: {"since", "days", "return", "last"}} from the curves."""
    d = load()
    out = {}
    for name, curve in d.get("curves", {}).items():
        if curve:
            out[name] = {"since": curve[0]["date"], "days": len(curve), "return": round(curve[-1]["equity"] - 1, 4),
                         "last": {"date": curve[-1]["date"], "ret": curve[-1]["ret"]}}
    return out


def note(s):
    return ", ".join(f"{name} {v['return']:+.2%} ({v['days']} d)" for name, v in sorted(s.items())) or "no marked days yet"
