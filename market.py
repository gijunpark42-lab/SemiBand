"""Market data from yfinance (free, no key): daily closes and headlines."""
import logging
import pickle
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import yfinance as yf

import config

log = logging.getLogger(__name__)


def closes(symbols, lookback_days=config.LOOKBACK_DAYS, cache=True) -> pd.DataFrame:
    """Adjusted daily closes, index = trading dates, columns = symbols.
    Cached per calendar day under state/ so re-runs are free (cache=False bypasses it,
    used by the backtest which needs a longer history than the daily cache holds)."""
    config.STATE_DIR.mkdir(exist_ok=True)
    symbols = sorted(set(symbols))
    if not cache:
        start = date.today() - timedelta(days=lookback_days)
        raw = yf.download(symbols, start=start.isoformat(), auto_adjust=True, progress=False, threads=True)
        df = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]].rename(columns={"Close": symbols[0]})
        df = df.dropna(how="all")
        df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
        return df
    cache = config.STATE_DIR / f"closes_{date.today().isoformat()}.pkl"
    for old in config.STATE_DIR.glob("closes_*.pkl"):
        if old != cache:
            old.unlink(missing_ok=True)
    cached = pickle.loads(cache.read_bytes()) if cache.exists() else None
    missing = symbols if cached is None else [s for s in symbols if s not in cached.columns]
    if not missing:
        return cached[symbols]
    start = date.today() - timedelta(days=lookback_days)
    raw = yf.download(missing, start=start.isoformat(), auto_adjust=True, progress=False, threads=True)
    df = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]].rename(columns={"Close": missing[0]})
    df = df.dropna(how="all")
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    if cached is not None:
        df = cached.join(df, how="outer")          # merge new columns into the day's cache
    cache.write_bytes(pickle.dumps(df))
    return df[symbols]


def news(symbol, limit=10, max_age_days=21):
    """[{title, publisher, when}] newest first; empty list if yfinance has nothing."""
    try:
        items = yf.Ticker(symbol).news or []
    except Exception as exc:  # network / parsing hiccups must not kill a cycle
        log.warning("news %s: %s", symbol, exc)
        return []
    out = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    for it in items:
        c = it.get("content") or it            # yfinance >= 0.2.5x nests under "content"
        title = c.get("title")
        when = c.get("pubDate") or c.get("providerPublishTime")
        if isinstance(when, (int, float)):
            when = datetime.fromtimestamp(when, tz=timezone.utc)
        elif isinstance(when, str):
            try:
                when = datetime.fromisoformat(when.replace("Z", "+00:00"))
            except ValueError:
                when = None
        if not title or (when and when < cutoff):
            continue
        provider = c.get("provider") or {}
        out.append({
            "title": title,
            "publisher": provider.get("displayName") if isinstance(provider, dict) else it.get("publisher"),
            "when": when.date().isoformat() if when else None,
        })
    return out[:limit]


# ---------------------------------------------------------------------------
# Per-ticker fundamentals and earnings dates (yfinance .info / earnings_dates).
# One request per ticker, so both are cached per calendar day under state/.

FUND_FIELDS = [
    "marketCap", "forwardPE", "trailingPE", "priceToSalesTrailing12Months",
    "revenueGrowth", "earningsGrowth", "grossMargins", "operatingMargins",
    "returnOnEquity", "debtToEquity", "shortPercentOfFloat",
    "targetMeanPrice", "numberOfAnalystOpinions", "currentPrice",
]


def _daily_json(name):
    """Path of today's cache for `name`; older files with the same prefix are removed."""
    config.STATE_DIR.mkdir(exist_ok=True)
    today = date.today().isoformat()
    for old in config.STATE_DIR.glob(f"{name}_*.json"):
        if not old.name.endswith(f"{today}.json"):
            old.unlink(missing_ok=True)
    return config.STATE_DIR / f"{name}_{today}.json"


def fundamentals(symbols):
    """{symbol: {field: value}} — missing/failed tickers map to {}."""
    import json
    import yfinance as yf
    path = _daily_json("fundamentals")
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    todo = [s for s in symbols if s not in data]
    for s in todo:
        try:
            info = yf.Ticker(s).info or {}
            data[s] = {k: info.get(k) for k in FUND_FIELDS}
        except Exception as exc:
            log.warning("fundamentals %s: %s", s, exc)
            data[s] = {}
    if todo:
        path.write_text(json.dumps(data), encoding="utf-8")
    return {s: data.get(s, {}) for s in symbols}


def earnings(symbols, limit=8):
    """{symbol: [{date, eps_estimate, reported_eps, surprise_pct}, ...]} newest first."""
    import json
    import yfinance as yf
    path = _daily_json("earnings" if limit <= 8 else f"earnings{limit}")
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    todo = [s for s in symbols if s not in data]
    for s in todo:
        rows = []
        try:
            df = yf.Ticker(s).get_earnings_dates(limit=limit)
            if df is not None:
                for ts, r in df.iterrows():
                    def num(v):
                        return None if v is None or pd.isna(v) else float(v)
                    rows.append({
                        "date": pd.Timestamp(ts).tz_localize(None).date().isoformat(),
                        "eps_estimate": num(r.get("EPS Estimate")),
                        "reported_eps": num(r.get("Reported EPS")),
                        "surprise_pct": num(r.get("Surprise(%)")),
                    })
        except Exception as exc:
            log.warning("earnings %s: %s", s, exc)
        data[s] = sorted(rows, key=lambda r: r["date"], reverse=True)
    if todo:
        path.write_text(json.dumps(data), encoding="utf-8")
    return {s: data.get(s, []) for s in symbols}


def benchmarks(days=130):
    """{ticker: [[YYYY-MM-DD, close], ...]} for the comparison tickers, for the dashboard."""
    df = closes(list(config.COMPARE_TICKERS), lookback_days=days)
    out = {}
    for t in config.COMPARE_TICKERS:
        if t in df.columns:
            series = df[t].dropna()
            out[t] = [[d.strftime("%Y-%m-%d"), round(float(v), 4)] for d, v in series.items()]
    return out


# ---------------------------------------------------------------------------
# Optional keyed sources (free tiers). Every function degrades to "no data"
# when the key is missing or the call fails, so nothing depends on them.

def finnhub_news(symbol, days=21, limit=15):
    """[{title, publisher, when}] newest first from Finnhub company-news; [] without a key."""
    import json
    import os
    import urllib.request
    key = os.getenv("FINNHUB_API_KEY")
    if not key:
        return []
    end = date.today()
    start = end - timedelta(days=days)
    url = (f"https://finnhub.io/api/v1/company-news?symbol={symbol}&from={start.isoformat()}"
           f"&to={end.isoformat()}&token={key}")
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            items = json.load(r)
    except Exception as exc:
        log.warning("finnhub news %s: %s", symbol, exc)
        return []
    out, seen = [], set()
    for it in sorted(items, key=lambda x: x.get("datetime", 0), reverse=True):
        title = (it.get("headline") or "").strip()
        if not title or title.lower() in seen:
            continue
        seen.add(title.lower())
        when = datetime.fromtimestamp(it.get("datetime", 0), tz=timezone.utc).date().isoformat() if it.get("datetime") else None
        out.append({"title": title, "publisher": it.get("source"), "when": when})
        if len(out) >= limit:
            break
    return out


def headlines(symbol, limit=12):
    """Finnhub first (broader coverage), yfinance as fallback / top-up, de-duplicated."""
    items = finnhub_news(symbol, limit=limit)
    if len(items) < limit:
        seen = {i["title"].lower() for i in items}
        for it in news(symbol, limit=limit):
            if it["title"].lower() not in seen:
                items.append(it)
                seen.add(it["title"].lower())
    return items[:limit]


def fred_latest(series_id, days=400):
    """Latest value and the value ~20 observations earlier for a FRED series; None without a key."""
    import json
    import os
    import urllib.request
    key = os.getenv("FRED_API_KEY")
    if not key:
        return None
    path = _daily_json(f"fred_{series_id}")
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    start = (date.today() - timedelta(days=days)).isoformat()
    url = (f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={key}"
           f"&file_type=json&observation_start={start}")
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            obs = [o for o in json.load(r).get("observations", []) if o.get("value") not in (None, ".")]
    except Exception as exc:
        log.warning("fred %s: %s", series_id, exc)
        return None
    if not obs:
        return None
    vals = [float(o["value"]) for o in obs]
    out = {"series": series_id, "date": obs[-1]["date"], "latest": vals[-1],
           "prev20": vals[-21] if len(vals) > 21 else vals[0]}
    path.write_text(json.dumps(out), encoding="utf-8")
    return out


def web_news(query, limit=6, timelimit="w"):
    """Keyless web news search (DuckDuckGo via the ddgs package): [{title, publisher, when, snippet}].
    Cached per day per query. Empty list on any failure — never blocks a cycle."""
    import json
    import hashlib
    key = hashlib.md5(query.encode("utf-8")).hexdigest()[:12]
    path = _daily_json(f"webnews_{key}")
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    out = []
    try:
        from ddgs import DDGS
        for r in DDGS().news(query, timelimit=timelimit, max_results=limit):
            out.append({"title": (r.get("title") or "").strip(), "publisher": r.get("source"),
                        "when": (r.get("date") or "")[:10], "snippet": (r.get("body") or "").strip()[:220]})
    except Exception as exc:
        log.warning("web_news %s: %s", query, exc)
    path.write_text(json.dumps(out), encoding="utf-8")
    return out
