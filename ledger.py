"""SQLite ledger: every prediction, its score once the horizon has passed,
agent weights over time, cycles and orders. This is the study's memory —
the dashboard and the weight updates are both derived from it.
"""
import sqlite3

import config

DB = config.STATE_DIR / "ledger.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS predictions(
    id INTEGER PRIMARY KEY, date TEXT, agent TEXT, ticker TEXT,
    direction REAL, confidence REAL, horizon INTEGER, reason TEXT, price_at REAL);
CREATE INDEX IF NOT EXISTS predictions_date ON predictions(date);
CREATE TABLE IF NOT EXISTS scores(
    prediction_id INTEGER, horizon INTEGER, scored_date TEXT,
    ret REAL, bench_ret REAL, abnormal REAL, hit INTEGER,
    PRIMARY KEY(prediction_id, horizon));
CREATE TABLE IF NOT EXISTS weights(date TEXT, agent TEXT, weight REAL, PRIMARY KEY(date, agent));
CREATE TABLE IF NOT EXISTS hedge_weights(date TEXT, agent TEXT, weight REAL, PRIMARY KEY(date, agent));
CREATE TABLE IF NOT EXISTS cycles(
    date TEXT PRIMARY KEY, equity REAL, cash REAL, n_positions INTEGER, n_orders INTEGER, note TEXT);
CREATE TABLE IF NOT EXISTS orders(
    id INTEGER PRIMARY KEY, date TEXT, ticker TEXT, side TEXT, notional REAL,
    reason TEXT, client_order_id TEXT, dry_run INTEGER);
"""


def connect():
    config.STATE_DIR.mkdir(exist_ok=True)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def add_predictions(date, signals, price_at):
    """price_at = {ticker: close used as the reference price}."""
    with connect() as con:
        con.executemany(
            "INSERT INTO predictions(date, agent, ticker, direction, confidence, horizon, reason, price_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            [(date, s.agent, s.ticker, s.direction, s.confidence, s.horizon, s.reason, price_at.get(s.ticker))
             for s in signals])


def unscored(horizon):
    """Predictions that have no score yet for this horizon (all of them; the scorer decides maturity)."""
    with connect() as con:
        return con.execute(
            "SELECT p.* FROM predictions p LEFT JOIN scores s ON s.prediction_id = p.id AND s.horizon = ? "
            "WHERE s.prediction_id IS NULL ORDER BY p.date", (horizon,)).fetchall()


def add_score(prediction_id, horizon, scored_date, ret, bench_ret, abnormal, hit):
    with connect() as con:
        con.execute("INSERT OR REPLACE INTO scores VALUES (?,?,?,?,?,?,?)",
                    (prediction_id, horizon, scored_date, ret, bench_ret, abnormal, hit))


def save_weights(date, weights):
    with connect() as con:
        con.executemany("INSERT OR REPLACE INTO weights VALUES (?,?,?)",
                        [(date, a, w) for a, w in weights.items()])


def latest_weights():
    with connect() as con:
        row = con.execute("SELECT MAX(date) AS d FROM weights").fetchone()
        if not row or not row["d"]:
            return None
        return {r["agent"]: r["weight"] for r in
                con.execute("SELECT agent, weight FROM weights WHERE date = ?", (row["d"],))}


def save_hedge_weights(date, weights):
    with connect() as con:
        con.executemany("INSERT OR REPLACE INTO hedge_weights VALUES (?,?,?)",
                        [(date, a, w) for a, w in weights.items()])


def latest_hedge_weights():
    with connect() as con:
        row = con.execute("SELECT MAX(date) AS d FROM hedge_weights").fetchone()
        if not row or not row["d"]:
            return None
        return {r["agent"]: r["weight"] for r in
                con.execute("SELECT agent, weight FROM hedge_weights WHERE date = ?", (row["d"],))}


def weights_history():
    with connect() as con:
        return [dict(r) for r in con.execute("SELECT date, agent, weight FROM weights ORDER BY date, agent")]


def scoreboard():
    """Per agent and horizon: how many scored, hit rate, mean abnormal return."""
    with connect() as con:
        rows = con.execute(
            "SELECT p.agent, s.horizon, COUNT(*) AS n, AVG(s.hit) AS hit_rate, "
            "AVG(s.abnormal * (CASE WHEN p.direction >= 0 THEN 1 ELSE -1 END)) AS mean_abnormal_signed, "
            "AVG(s.abnormal) AS mean_abnormal "
            "FROM scores s JOIN predictions p ON p.id = s.prediction_id "
            "GROUP BY p.agent, s.horizon ORDER BY p.agent, s.horizon").fetchall()
        return [dict(r) for r in rows]


def add_cycle(date, equity, cash, n_positions, n_orders, note=""):
    with connect() as con:
        con.execute("INSERT OR REPLACE INTO cycles VALUES (?,?,?,?,?,?)",
                    (date, equity, cash, n_positions, n_orders, note))


def add_order(date, ticker, side, notional, reason, client_order_id, dry_run):
    with connect() as con:
        con.execute("INSERT INTO orders(date, ticker, side, notional, reason, client_order_id, dry_run) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (date, ticker, side, notional, reason, client_order_id, int(dry_run)))


def cycles():
    with connect() as con:
        return [dict(r) for r in con.execute("SELECT * FROM cycles ORDER BY date")]
