"""Live scorecard (2026-10-06, read-only): the paper account's daily returns since the 09-10 start against SOXX and SPY —
cumulative return, Sharpe, Sortino, max drawdown, beta and the alpha of a regression on SOXX with a Newey-West t, and the
same for a beta-matched SOXX book. Written to state/scorecard.json and printed. It decides nothing by itself; the evaluation
rule it serves is pre-registered in RESEARCH.md (the strategy freeze of 2026-10-06).

    python -X utf8 live_scorecard.py
"""
import json
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import config

START = "2026-09-10"


def stats(r):
    r = np.asarray(r, float)
    lg = np.log1p(r)
    down = math.sqrt(float(np.mean(np.minimum(lg, 0.0) ** 2)))
    eq = np.cumprod(1 + r)
    return {"return": float(eq[-1] - 1), "sharpe": float(lg.mean() / lg.std(ddof=1) * math.sqrt(252)) if len(r) > 2 else None,
            "sortino": float(lg.mean() / down * math.sqrt(252)) if down > 0 else None,
            "max_drawdown": float((1 - eq / np.maximum.accumulate(eq)).max())}


def regression(r, b, lags=5):
    """OLS r = a + beta * b; alpha annualised with a Newey-West t."""
    r, b = np.asarray(r, float), np.asarray(b, float)
    beta = float(np.cov(r, b)[0, 1] / np.var(b, ddof=1))
    resid = r - beta * b
    e = resid - resid.mean()
    n = len(e)
    var = float(e @ e) / n
    for k in range(1, min(lags, n - 1) + 1):
        var += 2 * (1 - k / (lags + 1)) * float(e[k:] @ e[:-k]) / n
    t = float(resid.mean() / math.sqrt(var / n)) if var > 0 else float("nan")
    return {"beta": beta, "alpha_annual": float(resid.mean() * 252), "alpha_t": t}


def account_returns():
    """Daily account returns from Alpaca's portfolio history (end-of-day equity)."""
    import broker
    from alpaca.trading.requests import GetPortfolioHistoryRequest
    h = broker._client.get_portfolio_history(GetPortfolioHistoryRequest(period="6M", timeframe="1D"))
    eq = pd.Series(h.equity, index=pd.to_datetime(h.timestamp, unit="s", utc=True).tz_convert("America/New_York").date)
    eq = eq[eq.index >= pd.Timestamp(START).date()].astype(float)
    eq = eq[eq > 0]
    return eq.pct_change().dropna(), eq


def build():
    import market
    rets, eq = account_returns()
    px = market.closes([config.BENCHMARK, "SPY"], lookback_days=120, cache=False)
    bench = px.pct_change(fill_method=None)
    bench.index = [d.date() for d in bench.index]
    common = [d for d in rets.index if d in bench.index and bench.loc[d].notna().all()]
    r, s, p = rets.loc[common].to_numpy(), bench.loc[common, config.BENCHMARK].to_numpy(), bench.loc[common, "SPY"].to_numpy()
    reg = regression(r, s)
    matched = reg["beta"] * s                                        # a SOXX book at the account's own beta, rest in cash
    return {"written_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "start": START, "sessions": len(common),
            "last": str(common[-1]) if common else None, "equity": float(eq.iloc[-1]) if len(eq) else None,
            "account": stats(r), "soxx": stats(s), "spy": stats(p), "beta_matched_soxx": stats(matched), "vs_soxx": reg,
            "note": "n sessions is small: a Sharpe's standard error is about sqrt(252/n); read the alpha t, not the point estimates"}


def main():
    card = build()
    (config.STATE_DIR / "scorecard.json").write_text(json.dumps(card, indent=1), encoding="utf-8")
    a, s, m, v = card["account"], card["soxx"], card["beta_matched_soxx"], card["vs_soxx"]
    print(f"live scorecard {card['start']}..{card['last']} ({card['sessions']} sessions), equity ${card['equity']:,.0f}")
    for name, x in (("account", a), ("SOXX", s), ("SPY", card["spy"]), ("SOXX at the account's beta", m)):
        print(f"  {name:27s} {x['return']:+7.2%}  Sharpe {x['sharpe']:5.2f}  Sortino {x['sortino'] if x['sortino'] is not None else float('nan'):5.2f}  maxDD {x['max_drawdown']:.1%}")
    print(f"  vs SOXX: beta {v['beta']:.2f}, alpha {v['alpha_annual']:+.1%}/yr (NW t {v['alpha_t']:+.2f})")


if __name__ == "__main__":
    main()
