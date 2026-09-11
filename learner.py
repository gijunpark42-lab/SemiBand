"""Bayesian ridge stacking — how the ensemble learns to weight its agents.

Why not plain multiplicative weights (Hedge)?  Hedge keeps one positive
scalar per agent and only asks "did you make money". It cannot learn that an
agent is reliably WRONG (which is a usable signal with the sign flipped),
that two agents say the same thing (double counting), or whether an agent's
stated confidence carries information. Stacked generalisation — fitting a
second-level model on the base learners' outputs — is the standard ML answer,
and with ~11 agents and a few hundred scored rows per week the right
second-level model is a small, heavily regularised linear one, not a tree
ensemble (which would memorise two weeks of one regime).

The model, per horizon h in {5, 10, 20} trading days:

    y = abnormal_return_h / scale_h                     (target in "conviction units")
    x = [dir_i * conf_i for each agent i] + [dir_i for each agent i]   (0 when silent)
    y ~ N(x . w, sigma^2),  w ~ N(w0, I / lambda)       (Gaussian prior on the weights)

    posterior mean  w = (X'DX + lambda I)^-1 (X'Dy + lambda w0)

where D is an exponential time decay (recent days count more) and the prior
mean w0 is the equal-weight blend we started with. So on day one the model IS
the old ensemble; as scored rows arrive the posterior moves toward whatever
combination actually predicted abnormal returns. lambda is the prior strength
in pseudo-observations; once enough days exist it is chosen by walk-forward
cross-validation on the information coefficient (rank correlation between
prediction and realised abnormal return, the standard quant yardstick).

Outputs used elsewhere:
  * conviction per ticker  = reliability-weighted blend of the three horizon
    predictions, clipped to [-1, 1]  (reliability = each horizon's out-of-sample IC)
  * per-agent contribution = w_conf_i * dir_i * conf_i + w_dir_i * dir_i  (dashboard)
  * effective weight per agent (display) = w_conf_i + 0.5 * w_dir_i, normalised so
    sum |w| = 1; negative means the ensemble uses the agent as a contrarian signal
  * per-agent IC per horizon (scoreboard)
"""
import json
import math
from datetime import date, timedelta

import numpy as np

import config
import ledger

MODEL_FILE = config.STATE_DIR / "model.json"
HALF_LIFE_DAYS = config.LEARNER_HALF_LIFE_DAYS      # calendar days; an observation that old counts half
PRIOR_STRENGTH = config.LEARNER_PRIOR_STRENGTH      # lambda: pseudo-observations behind the equal-weight prior
LAMBDA_GRID = tuple(config.LEARNER_LAMBDA_GRID)
CV_MIN_DATES = 8               # walk-forward CV needs this many distinct prediction dates
WINSOR = 0.15                  # clip realised abnormal returns at +/-15%
DEFAULT_SCALE = {5: 0.02, 10: 0.03, 20: 0.045}   # typical |abnormal| per horizon until measured
MIN_RELIABILITY = 0.02


def agents():
    return list(config.AGENTS)


def prior_weights(n):
    """w0: equal weight on dir*conf, none on dir alone -> identical to the old blend."""
    return np.concatenate([np.full(n, 1.0 / n), np.zeros(n)])


def features(per_agent: dict, names: list) -> np.ndarray:
    """per_agent = {agent: {direction, confidence}} -> 2n vector (silent agents = 0)."""
    x = np.zeros(2 * len(names))
    for i, a in enumerate(names):
        s = per_agent.get(a)
        if s is None:
            continue
        d = float(s["direction"] if isinstance(s, dict) else s.direction)
        c = float(s["confidence"] if isinstance(s, dict) else s.confidence)
        x[i] = d * c
        x[len(names) + i] = d
    return x


def _rows(db_path, horizon, asof, since_scored=None, dates=None):
    """Scored rows from one ledger file. since_scored: only rows scored on/after that date (what changed since
    the last load); dates: only these prediction dates. With asof, only predictions whose outcome was known by then."""
    import sqlite3
    if not db_path.exists():
        return []
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    base = ("SELECT p.date, p.ticker, p.agent, p.direction, p.confidence, s.abnormal, s.scored_date "
            "FROM predictions p JOIN scores s ON s.prediction_id = p.id AND s.horizon = ?")
    try:
        if dates is not None:
            rows = []
            dates = sorted(dates)
            for k in range(0, len(dates), 400):                       # SQLite parameter limit
                chunk = dates[k:k + 400]
                rows += con.execute(base + " WHERE p.date IN (%s)" % ",".join("?" * len(chunk)), (horizon, *chunk)).fetchall()
        elif since_scored is not None:
            rows = con.execute(base + " WHERE s.scored_date >= ?", (horizon, since_scored)).fetchall()
        else:
            rows = con.execute(base, (horizon,)).fetchall()
    finally:
        con.close()
    if asof is not None:
        cutoff = (asof - timedelta(days=int(math.ceil(horizon * 1.45)) + 1)).isoformat()
        rows = [r for r in rows if r["date"] <= cutoff]
    return rows


def _touched_dates(db_path, horizon, since_scored):
    """Prediction dates that received scores on/after since_scored (uses the scores(scored_date) index)."""
    import sqlite3
    con = sqlite3.connect(db_path)
    try:
        return [r[0] for r in con.execute(
            "SELECT DISTINCT p.date FROM scores s JOIN predictions p ON p.id = s.prediction_id "
            "WHERE s.horizon = ? AND s.scored_date >= ?", (horizon, since_scored)).fetchall()]
    finally:
        con.close()


_CACHE = {}   # (db path, horizon, names) -> {stamp, by_date: {date: (X_d, y_d)}, last_scored, arrays}


def _stamp(path):
    st = path.stat()
    return (str(path), st.st_mtime_ns, st.st_size)


def _load_source(db_path, sw, horizon, names):
    """All scored rows of one ledger file as arrays, one row per (date, ticker), ordered by (date, ticker).

    Cached per file. When the file changed since the last call, only the prediction dates that received new
    scores are re-read and rebuilt (a backtest adds one date per day, live scoring a few matured dates per
    cycle), so a refit costs O(new rows) instead of rebuilding tens of thousands of feature rows every day.
    The arrays are the same values in the same order as a full rebuild would give."""
    key = (str(db_path), horizon, tuple(names))
    stamp = _stamp(db_path)[1:]
    ent = _CACHE.get(key)
    if ent is None:
        ent = _CACHE[key] = {"stamp": None, "by_date": {}, "last_scored": None, "arrays": None}
    if ent["stamp"] != stamp:
        if ent["last_scored"] is None:
            rows = _rows(db_path, horizon, None)
        else:
            touched = _touched_dates(db_path, horizon, ent["last_scored"])
            rows = _rows(db_path, horizon, None, dates=touched) if touched else []
        per = {}
        for r in rows:
            g = per.setdefault(r["date"], {}).setdefault(r["ticker"], {"agents": {}, "y": r["abnormal"]})
            g["agents"][r["agent"]] = {"direction": r["direction"], "confidence": r["confidence"]}
            if ent["last_scored"] is None or r["scored_date"] > ent["last_scored"]:
                ent["last_scored"] = r["scored_date"]
        for d, groups in per.items():
            tks = sorted(groups)
            ent["by_date"][d] = (np.array([features(groups[tk]["agents"], names) for tk in tks]),
                                 np.array([float(np.clip(groups[tk]["y"], -WINSOR, WINSOR)) for tk in tks]))
        ent["stamp"], ent["arrays"] = stamp, None
    if ent["arrays"] is None:
        ds = sorted(ent["by_date"])
        if ds:
            X = np.concatenate([ent["by_date"][d][0] for d in ds])
            y = np.concatenate([ent["by_date"][d][1] for d in ds])
            dates = np.concatenate([np.full(len(ent["by_date"][d][1]), d) for d in ds])
        else:
            X, y, dates = np.zeros((0, 2 * len(names))), np.zeros(0), np.zeros(0, dtype=str)
        ent["arrays"] = (X, y, dates)
    X, y, dates = ent["arrays"]
    return X, y, dates, np.full(len(y), sw)


def dataset(horizon: int, names: list, asof=None):
    """-> (X, y_raw, dates, source_weight) from scored predictions at this horizon, one row per (date, ticker).

    Live rows come from state/ledger.sqlite (weight 1). If state/backtest.sqlite exists and
    WARM_START_WEIGHT > 0, its point-in-time rows are added at that weight so the model
    starts from a year of history instead of a flat prior. With asof, only predictions whose
    outcome was known by then (walk-forward backtests and sweeps)."""
    sources = [(ledger.DB, 1.0)]
    bt = config.STATE_DIR / "backtest.sqlite"
    if bt != ledger.DB and bt.exists() and config.WARM_START_WEIGHT > 0:
        sources.append((bt, config.WARM_START_WEIGHT))
    parts = [_load_source(p, sw, horizon, names) for p, sw in sources if p.exists()]
    if not parts:
        return np.zeros((0, 2 * len(names))), np.zeros(0), [], np.zeros(0)
    X = np.concatenate([p[0] for p in parts]); y = np.concatenate([p[1] for p in parts])
    dates = np.concatenate([p[2] for p in parts]); sw = np.concatenate([p[3] for p in parts])
    if asof is not None:
        cutoff = (asof - timedelta(days=int(math.ceil(horizon * 1.45)) + 1)).isoformat()
        keep = dates <= cutoff
        X, y, dates, sw = X[keep], y[keep], dates[keep], sw[keep]
    order = np.argsort(dates, kind="stable")           # keep the (date, ticker) order the old code produced
    return X[order], y[order], list(dates[order]), sw[order]


_ORD = {}   # ISO date -> ordinal; a fit sees the same few hundred dates tens of thousands of times


def _ordinals(dates):
    """Day ordinals (float) for a sequence of ISO dates, parsing each distinct date once."""
    if len(dates) == 0:
        return np.zeros(0)
    uniq, inv = np.unique(np.asarray(dates, dtype=str), return_inverse=True)
    o = np.array([_ORD.get(d) or _ORD.setdefault(d, date.fromisoformat(d).toordinal()) for d in uniq], dtype=float)
    return o[inv]


def decay_ord(ords, today):
    return np.power(0.5, (today.toordinal() - ords) / HALF_LIFE_DAYS)


def decay(dates, today):
    return decay_ord(_ordinals(dates), today)


def ridge(X, y, d, lam, w0):
    """Posterior mean of w under the Gaussian prior N(w0, I/lam) and observation weights d."""
    if len(y) == 0:
        return w0.copy()
    Xd = X * d[:, None]
    A = X.T @ Xd + lam * np.eye(X.shape[1])
    b = X.T @ (d * y) + lam * w0
    return np.linalg.solve(A, b)


def ic(pred, y):
    """Rank correlation (Spearman) between prediction and outcome; 0 when undefined."""
    if len(y) < 5 or np.std(pred) == 0 or np.std(y) == 0:
        return 0.0
    rp = np.argsort(np.argsort(pred)).astype(float)
    ry = np.argsort(np.argsort(y)).astype(float)
    return float(np.corrcoef(rp, ry)[0, 1])


def walk_forward_ic(X, y, dates, w0, lam, today, horizon, last_k=10, ords=None):
    """Mean IC over the last_k dates, each predicted from a model that only saw rows whose
    outcome was already known on that date (prediction date + horizon), so overlapping
    return windows cannot leak the answer into the training set."""
    uniq = sorted(set(dates))
    if len(uniq) < CV_MIN_DATES:
        return None
    ords = _ordinals(dates) if ords is None else ords
    gap = int(math.ceil(horizon * 1.45)) + 1
    ics = []
    for dt in uniq[-last_k:]:
        d0 = date.fromisoformat(dt)
        train = ords <= float((d0 - timedelta(days=gap)).toordinal())   # same rows as the ISO-string comparison
        test = ords == float(d0.toordinal())
        if train.sum() < 20 or test.sum() < 5:
            continue
        w = ridge(X[train], y[train], decay_ord(ords[train], d0), lam, w0)
        ics.append(ic(X[test] @ w, y[test]))
    return float(np.mean(ics)) if ics else None


def fit(today: date | None = None, asof: date | None = None) -> dict:
    """Refit all horizons from the ledger(s) and save MODEL_FILE. Returns the model.
    asof: only use rows whose outcome was known by that date (walk-forward backtests)."""
    today = today or date.today()
    names = agents()
    n = len(names)
    w0 = prior_weights(n)
    model = {"fitted": today.isoformat(), "agents": names, "horizons": {}}
    for h in config.HORIZONS:
        X, y_raw, dates, sw = dataset(h, names, asof)
        ords = _ordinals(dates)
        scale = float(np.std(y_raw)) if len(y_raw) >= 40 else DEFAULT_SCALE[h]
        scale = max(scale, 0.01)
        y = y_raw / scale
        lam, cv = PRIOR_STRENGTH, None
        if len(set(dates)) >= CV_MIN_DATES:
            scores = {l: walk_forward_ic(X, y, dates, w0, l, today, h, ords=ords) for l in LAMBDA_GRID}
            scores = {l: s for l, s in scores.items() if s is not None}
            if scores:
                lam = max(scores, key=scores.get)
                cv = scores[lam]
        d = decay_ord(ords, today) * sw if len(dates) else np.zeros(0)
        w = ridge(X, y, d, lam, w0)
        agent_ic = {}
        for i, a in enumerate(names):
            mask = X[:, i] != 0
            agent_ic[a] = round(ic(X[mask, i], y[mask]), 3) if mask.sum() >= 10 else None
        model["horizons"][str(h)] = {
            "n_obs": int(len(y)), "n_dates": len(set(dates)), "lambda": lam, "scale": round(scale, 4),
            "cv_ic": None if cv is None else round(cv, 3),
            "reliability": max(cv if cv is not None else 0.05, MIN_RELIABILITY),
            "w_conf": {a: round(float(w[i]), 4) for i, a in enumerate(names)},
            "w_dir": {a: round(float(w[n + i]), 4) for i, a in enumerate(names)},
            "agent_ic": agent_ic,
        }
    model["effective_weights"] = effective_weights(model)
    config.STATE_DIR.mkdir(exist_ok=True)
    MODEL_FILE.write_text(json.dumps(model, indent=2), encoding="utf-8")
    return model


def load() -> dict | None:
    if not MODEL_FILE.exists():
        return None
    try:
        m = json.loads(MODEL_FILE.read_text(encoding="utf-8"))
    except ValueError:
        return None
    return m if m.get("agents") == agents() else None   # roster changed -> refit from the prior


def _blend(model):
    hs = model["horizons"]
    total = sum(v["reliability"] for v in hs.values()) or 1.0
    return {h: v["reliability"] / total for h, v in hs.items()}


def effective_weights(model) -> dict:
    """Display weights: reliability-blended (w_conf + 0.5 w_dir), normalised so sum|w| = 1."""
    names = model["agents"]
    mix = _blend(model)
    eff = {a: sum(mix[h] * (v["w_conf"][a] + 0.5 * v["w_dir"][a]) for h, v in model["horizons"].items())
           for a in names}
    norm = sum(abs(x) for x in eff.values()) or 1.0
    return {a: round(x / norm, 4) for a, x in eff.items()}


def predict(signals, model=None):
    """signals: list of Signal -> ({ticker: conviction}, {ticker: {agent: breakdown}}).

    Without a model (or with one that has no data yet) this reproduces the
    equal-weight blend exactly, because the prior mean is that blend."""
    names = agents()
    n = len(names)
    model = model or {"agents": names, "horizons": {str(h): {
        "reliability": 1.0, "w_conf": {a: 1.0 / n for a in names}, "w_dir": {a: 0.0 for a in names}}
        for h in config.HORIZONS}}
    mix = _blend(model)
    by_ticker = {}
    for s in signals:
        by_ticker.setdefault(s.ticker, {})[s.agent] = s
    convictions, breakdown = {}, {}
    for ticker, per_agent in by_ticker.items():
        x = features(per_agent, names)
        pred = 0.0
        contrib = {a: 0.0 for a in per_agent}
        for h, v in model["horizons"].items():
            w = np.array([v["w_conf"][a] for a in names] + [v["w_dir"][a] for a in names])
            pred += mix[h] * float(x @ w)
            for i, a in enumerate(names):
                if a in per_agent:
                    contrib[a] += mix[h] * (v["w_conf"][a] * x[i] + v["w_dir"][a] * x[n + i])
        convictions[ticker] = float(np.clip(pred, -1.0, 1.0))
        breakdown[ticker] = {a: {"direction": round(s.direction, 3), "confidence": round(s.confidence, 3),
                                 "horizon": s.horizon, "reason": s.reason,
                                 "contribution": round(float(contrib[a]), 3)} for a, s in per_agent.items()}
    return convictions, breakdown
