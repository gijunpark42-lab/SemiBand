"""Real-time earnings off Alpaca's news stream (a Benzinga feed).

Benzinga publishes a structured headline the moment a company reports:

    Acme Q2 EPS $1.20 Beats $1.05 Estimate, Sales $3.400B Beat $3.200B Estimate

These auto-generated alerts carry NO summary and NO content -- the headline is
the entire payload -- so parsing it is the whole job. That emptiness is also how
we tell an alert apart from a human-written article about the same earnings
(measured: 719 of 723 wire alerts had empty content, and every article had some).

Guidance arrives as its own item, separate from the EPS one, and often moves the
stock more, so both shapes are matched.

Symbols come from tickers.load() -- the US-listed slice of the earnings-ai
universe. Reaching the feed within a second is realistic; beating the algos
already trading the wire is not, so treat this as a drift signal, not a race.

    python earnings_stream.py           watch the earnings-ai universe
    python earnings_stream.py --all     watch everything Benzinga covers
"""
import argparse
import asyncio
import json
import logging
import re
from datetime import datetime, timezone

import websockets

import config
import tickers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.FileHandler("earnings.log", encoding="utf-8"),
              logging.StreamHandler()],
)
log = logging.getLogger("earnings")

STREAM_URL = "wss://stream.data.alpaca.markets/v1beta1/news"

# "$1.332M", "$(0.15)" (parens = negative), "$490.619K", "~$207M", "EUR64.0M".
# Non-USD matters here: ASML and other foreign filers in the universe report in
# euros, and an unmatched currency symbol would silently drop the whole clause.
_CURRENCY = "$€£¥"
_NUM = rf"[~≈]?[{_CURRENCY}]?\(?-?[\d,]*\.?\d+\)?[KMBT]?"

_QUARTER_RE = re.compile(r"\b(Q[1-4]|H[12]|FY\d{2,4}|FY)\b")
_CLAUSE_RE = re.compile(
    rf"\b(?:Adj\.?\s+)?(EPS|Sales|Revenue)\s+(?:Of\s+)?({_NUM})"
    # Bare "Up 72% YoY" is deliberately NOT a comparison verb: the number after
    # it is a percentage, not a reference value, and would poison change_pct.
    rf"(?:,?\s+(Beats?|Misses?|In[- ]Line(?:\s+With)?|Up From|Down From)\s+({_NUM}))?",
    re.I,
)
# A restatement or retraction reuses the exact "Q2 EPS $X" shape as a fresh
# print, so it parses cleanly and looks like a normal result. It is not one --
# the number is being withdrawn, not reported -- and trading it would act on a
# figure the company just disowned. Kept as its own kind rather than dropped.
_RESTATEMENT_RE = re.compile(
    r"\b(Restate[sd]?|Restatement|Misstate(?:d|ment)|Material Weakness"
    r"|Should No Longer Be Relied Upon|Overstated|Understated)\b",
    re.I,
)
_GUIDANCE_RE = re.compile(
    r"\b(Sees|Raises|Lowers|Cuts|Boosts|Narrows|Reaffirms|Issues|Withdraws)\b"
    r"[^,]{0,60}?\b(Guidance|Outlook|EPS|Sales|Revenue)\b",
    re.I,
)
_SUFFIX = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}


def _money(text):
    """'$1.332M' -> 1332000.0, '$(0.15)' -> -0.15, unparseable -> None."""
    if not text:
        return None
    token = text.strip(" ~≈" + _CURRENCY).replace(",", "").strip()
    negative = token.startswith("(")
    token = token.strip("()")
    multiplier = _SUFFIX.get(token[-1:].upper(), 1)
    if multiplier != 1:
        token = token[:-1]
    try:
        value = float(token)
    except ValueError:
        return None
    return -value * multiplier if negative else value * multiplier


def _basis(verb):
    if verb is None:
        return None
    return "yoy" if verb.lower().endswith("from") else "estimate"


def parse(item):
    """News item -> earnings/guidance event, or None if it is neither.

    Only auto-generated wire alerts are considered; an article that happens to
    discuss the same results has content attached and is skipped, because its
    headline is prose and would parse into nonsense.
    """
    if item.get("content") or item.get("summary"):
        return None

    headline = item.get("headline") or ""
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    event = {
        "symbols": item.get("symbols") or [],
        "headline": headline,
        "created_at": created,
        "latency_s": (datetime.now(timezone.utc) - created).total_seconds(),
    }

    metrics = {}
    for metric, actual, verb, reference in _CLAUSE_RE.findall(headline):
        actual_value = _money(actual)
        reference_value = _money(reference)
        change = None
        if actual_value is not None and reference_value:
            change = (actual_value - reference_value) / abs(reference_value) * 100
        metrics[metric.lower()] = {
            "actual": actual_value,
            "reference": reference_value,
            "basis": _basis(verb or None),
            "verb": verb or None,
            "change_pct": change,
        }

    quarter = _QUARTER_RE.search(headline)
    event["quarter"] = quarter.group(1) if quarter else None

    # Guidance is checked before the metrics, not after: "Sees Prelim H1 Revenue
    # $3.85M" parses as a clean Revenue clause, but it is a forward outlook, not
    # a print, and the metric shape alone cannot tell the two apart.
    guidance = _GUIDANCE_RE.search(headline)
    if guidance:
        event.update(kind="guidance", action=guidance.group(1),
                     metric=guidance.group(2).lower(), metrics=metrics)
        return event

    if metrics:
        event.update(
            kind="restatement" if _RESTATEMENT_RE.search(headline) else "earnings",
            metrics=metrics,
        )
        return event
    return None


def describe(event):
    """One-line human summary of an event."""
    seen = ",".join(event["symbols"][:4]) or "-"
    if event["kind"] == "guidance":
        # a few headlines arrive with embedded newlines; keep the log one line
        headline = " ".join(event["headline"].split())
        return f"{seen:14} GUIDANCE {event['action']:9} {headline}"

    parts = []
    for name in ("eps", "sales", "revenue"):
        metric = event["metrics"].get(name)
        if not metric:
            continue
        change = metric["change_pct"]
        arrow = "" if change is None else f" {change:+.1f}% vs {metric['basis']}"
        parts.append(f"{name.upper()} {metric['actual']:,.4g}{arrow}")
    return (f"{seen:14} {event['kind'].upper():11} {event.get('quarter') or '--':6} "
            + " | ".join(parts))


def on_earnings(event):
    """YOUR RULES GO HERE.

    Empty on purpose: this module only listens and never trades. event is the
    dict built by parse(); check event["kind"] before acting on it:

        earnings     a fresh print. metrics["eps"]/["sales"] carry actual,
                     reference, basis ("estimate" or "yoy") and change_pct.
        guidance     forward outlook, arriving separately from the print and
                     often the bigger mover. Numbers stay in the headline.
        restatement  same shape as earnings, but the figure is being withdrawn.
                     Do NOT trade it as a surprise.

    Runs on a worker task, so blocking here is safe: it will not stall the
    socket. Bursts queue up instead (16:00 ET peaks at ~15 items/min feed-wide).
    """


async def _consume(queue):
    while True:
        event = await queue.get()
        try:
            log.info("%s  (+%.1fs)", describe(event), event["latency_s"])
            on_earnings(event)
        except Exception:
            log.exception("handler failed: %s", event["headline"])
        finally:
            queue.task_done()


async def _session(symbols, queue):
    """One connection: authenticate, subscribe, pump messages until it drops."""
    async with websockets.connect(STREAM_URL, max_size=None) as socket:
        await socket.recv()
        await socket.send(json.dumps({"action": "auth", "key": config.API_KEY,
                                      "secret": config.SECRET_KEY}))
        reply = json.loads(await socket.recv())[0]
        if reply.get("T") == "error":
            raise RuntimeError(f"auth failed: {reply.get('msg')}")

        await socket.send(json.dumps({"action": "subscribe", "news": symbols}))
        reply = json.loads(await socket.recv())[0]
        if reply.get("T") == "error":
            raise RuntimeError(f"subscribe failed: {reply.get('msg')}")
        log.info("subscribed to %d symbols", len(reply.get("news", [])))

        async for raw in socket:
            for item in json.loads(raw):
                if item.get("T") != "n":
                    continue
                event = parse(item)
                if event:
                    queue.put_nowait(event)


async def run(symbols):
    queue = asyncio.Queue()
    worker = asyncio.create_task(_consume(queue))
    backoff = 1
    try:
        while True:
            try:
                await _session(symbols, queue)
                backoff = 1               # clean disconnect; reconnect promptly
            except Exception as exc:
                log.warning("stream dropped (%s), retrying in %ds", exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)
    finally:
        worker.cancel()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true",
                        help="subscribe to every symbol instead of the earnings-ai universe")
    args = parser.parse_args()

    symbols = ["*"] if args.all else tickers.load()
    log.info("watching %s", "ALL symbols" if args.all else f"{len(symbols)} earnings-ai symbols")
    try:
        asyncio.run(run(symbols))
    except KeyboardInterrupt:
        log.info("stopped")


if __name__ == "__main__":
    main()
