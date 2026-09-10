"""Fundamentals agent — growth, margins, valuation, analyst target.

Free (yfinance .info, cached per day). Rule-based so its opinion is fully
explainable: each factor adds or subtracts a fixed amount, direction is
tanh of the sum, confidence grows with how many factors were available.
"""
import math

import market
from agents.base import Signal, clip

NAME = "fundamentals"


def run(universe: dict, ctx: dict) -> list[Signal]:
    data = market.fundamentals(list(universe))
    out = []
    for ticker in universe:
        f = data.get(ticker) or {}
        score, why, n = 0.0, [], 0

        g = f.get("revenueGrowth")
        if g is not None:
            n += 1
            if g > 0.30:
                score += 0.4; why.append(f"rev growth {g*100:+.0f}%")
            elif g > 0.10:
                score += 0.2; why.append(f"rev growth {g*100:+.0f}%")
            elif g < 0:
                score -= 0.4; why.append(f"rev shrinking {g*100:+.0f}%")

        om = f.get("operatingMargins")
        if om is not None:
            n += 1
            if om > 0.25:
                score += 0.2; why.append(f"op margin {om*100:.0f}%")
            elif om < 0:
                score -= 0.3; why.append("loss-making")

        pe = f.get("forwardPE")
        if pe is not None and pe > 0:
            n += 1
            if pe > 60:
                score -= 0.3; why.append(f"fwd PE {pe:.0f}")
            elif pe < 15:
                score += 0.2; why.append(f"fwd PE {pe:.0f}")

        ps = f.get("priceToSalesTrailing12Months")
        if ps is not None and ps > 15:
            n += 1
            score -= 0.2; why.append(f"P/S {ps:.0f}")

        price, target = f.get("currentPrice"), f.get("targetMeanPrice")
        analysts = f.get("numberOfAnalystOpinions") or 0
        if price and target and analysts >= 3:
            n += 1
            up = target / price - 1
            if up > 0.25:
                score += 0.3; why.append(f"target {up*100:+.0f}% ({analysts} analysts)")
            elif up < 0:
                score -= 0.3; why.append(f"target {up*100:+.0f}%")

        if n == 0:
            continue
        direction = math.tanh(score)
        confidence = clip(0.3 + 0.08 * n, 0.3, 0.7)
        out.append(Signal(NAME, ticker, direction, confidence, 20, "; ".join(why) or "neutral fundamentals").clipped())
    return out
