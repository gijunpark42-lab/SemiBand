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
    direction REAL, confidence REAL, horizon INTEGER, reason TEXT, price_at REAL,
    benchmark_beta REAL);
CREATE INDEX IF NOT EXISTS predictions_date ON predictions(date);
CREATE TABLE IF NOT EXISTS scores(
    prediction_id INTEGER, horizon INTEGER, scored_date TEXT,
    ret REAL, bench_ret REAL, abnormal REAL, beta_abnormal REAL, hit INTEGER,
    PRIMARY KEY(prediction_id, horizon));
CREATE INDEX IF NOT EXISTS scores_scored_date ON scores(scored_date);
CREATE TABLE IF NOT EXISTS weights(date TEXT, agent TEXT, weight REAL, PRIMARY KEY(date, agent));
CREATE TABLE IF NOT EXISTS hedge_weights(date TEXT, agent TEXT, weight REAL, PRIMARY KEY(date, agent));
CREATE TABLE IF NOT EXISTS cycles(
    date TEXT PRIMARY KEY, equity REAL, cash REAL, n_positions INTEGER, n_orders INTEGER, note TEXT);
CREATE TABLE IF NOT EXISTS orders(
    id INTEGER PRIMARY KEY, date TEXT, ticker TEXT, side TEXT, notional REAL,
    reason TEXT, client_order_id TEXT, dry_run INTEGER);
CREATE TABLE IF NOT EXISTS shadow_targets(
    date TEXT, target_mode TEXT, ticker TEXT, conviction REAL, target_usd REAL,
    reference_price REAL, vol_target REAL, active INTEGER,
    PRIMARY KEY(date, target_mode, ticker));
"""


class _Connection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def connect():
    config.STATE_DIR.mkdir(exist_ok=True)
    con = sqlite3.connect(DB, factory=_Connection)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    _migrate(con)
    return con


def _migrate(con):
    """Add parallel beta fields without rewriting or dropping the original labels."""
    prediction_cols = {r[1] for r in con.execute("PRAGMA table_info(predictions)")}
    score_cols = {r[1] for r in con.execute("PRAGMA table_info(scores)")}
    if "benchmark_beta" not in prediction_cols:
        con.execute("ALTER TABLE predictions ADD COLUMN benchmark_beta REAL")
    if "beta_abnormal" not in score_cols:
        con.execute("ALTER TABLE scores ADD COLUMN beta_abnormal REAL")
    shadow_cols = {r[1] for r in con.execute("PRAGMA table_info(shadow_targets)")}
    if shadow_cols and "active" not in shadow_cols:
        con.execute("ALTER TABLE shadow_targets ADD COLUMN active INTEGER NOT NULL DEFAULT 0")


def add_predictions(date, signals, price_at, benchmark_beta=None):
    """price_at = {ticker: close used as the reference price}."""
    benchmark_beta = benchmark_beta or {}
    with connect() as con:
        con.executemany(
            "INSERT INTO predictions(date, agent, ticker, direction, confidence, horizon, reason, price_at, benchmark_beta) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            [(date, s.agent, s.ticker, s.direction, s.confidence, s.horizon, s.reason, price_at.get(s.ticker),
              benchmark_beta.get(s.ticker))
             for s in signals])


def predictions_on(date):
    """One date's recorded signals, newest row per (agent, ticker): a re-run reuses them instead of calling the agents again."""
    with connect() as con:
        rows = con.execute("SELECT agent, ticker, direction, confidence, horizon, reason FROM predictions "
                           "WHERE date = ? ORDER BY id", (date,)).fetchall()
    return list({(r["agent"], r["ticker"]): r for r in rows}.values())


def replace_predictions(date, agents, signals, price_at, benchmark_beta=None):
    """Swap one date's predictions of `agents` for fresh ones in one transaction (the open refresh re-runs the
    price-based agents on today's first trades)."""
    agents = list(agents)
    benchmark_beta = benchmark_beta or {}
    with connect() as con:
        con.execute(f"DELETE FROM predictions WHERE date = ? AND agent IN ({','.join('?' * len(agents))})", (date, *agents))
        con.executemany(
            "INSERT INTO predictions(date, agent, ticker, direction, confidence, horizon, reason, price_at, benchmark_beta) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            [(date, s.agent, s.ticker, s.direction, s.confidence, s.horizon, s.reason, price_at.get(s.ticker),
              benchmark_beta.get(s.ticker))
             for s in signals if s.agent in agents])


def order_keys(days=4):
    """{(date, ticker, side)} of the real (not dry-run) orders this program recorded in the last `days` calendar days: lets the
    foreign-order guard recognise our own position closes that went out without the ORDER_PREFIX client id."""
    with connect() as con:
        rows = con.execute("SELECT date, ticker, side FROM orders WHERE dry_run = 0 AND date >= date('now', ?)",
                           (f"-{days} days",)).fetchall()
    return {(r["date"], r["ticker"], r["side"].upper()) for r in rows}


def unscored(horizon):
    """Predictions that have no score yet for this horizon (all of them; the scorer decides maturity)."""
    with connect() as con:
        return con.execute(
            "SELECT p.* FROM predictions p LEFT JOIN scores s ON s.prediction_id = p.id AND s.horizon = ? "
            "WHERE s.prediction_id IS NULL ORDER BY p.date", (horizon,)).fetchall()


def add_score(prediction_id, horizon, scored_date, ret, bench_ret, abnormal, beta_abnormal, hit):
    with connect() as con:
        con.execute(
            "INSERT OR REPLACE INTO scores(prediction_id,horizon,scored_date,ret,bench_ret,abnormal,beta_abnormal,hit) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (prediction_id, horizon, scored_date, ret, bench_ret, abnormal, beta_abnormal, hit),
        )


def set_prediction_beta(prediction_id, beta):
    with connect() as con:
        con.execute("UPDATE predictions SET benchmark_beta = ? WHERE id = ?", (beta, prediction_id))


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


def save_shadow_targets(date, target_mode, convictions, targets, prices, vol_target, active=False):
    """Record intended positions only; these rows can never reach the broker."""
    tickers = sorted(set(convictions) | set(targets))
    with connect() as con:
        con.executemany(
            "INSERT OR REPLACE INTO shadow_targets(date,target_mode,ticker,conviction,target_usd,reference_price,vol_target,active) "
            "VALUES (?,?,?,?,?,?,?,?)",
            [(date, target_mode, ticker, convictions.get(ticker), targets.get(ticker, 0.0), prices.get(ticker), vol_target,
              int(active))
             for ticker in tickers],
        )


def cycles():
    with connect() as con:
        return [dict(r) for r in con.execute("SELECT * FROM cycles ORDER BY date")]
