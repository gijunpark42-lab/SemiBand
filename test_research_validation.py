import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

import config
import learner
import ledger
import learning_targets
from migrate_beta_targets import migrate_db, migrate_db_from_beta_ledger
import sweep


def make_db(path: Path, ticker: str, scored_date: str):
    con = sqlite3.connect(path)
    con.executescript(ledger.SCHEMA)
    con.execute(
        "INSERT INTO predictions(date, agent, ticker, direction, confidence, horizon, reason, price_at) "
        "VALUES ('2024-01-02', 'technical', ?, 1, 0.5, 10, '', 1)",
        (ticker,),
    )
    pid = con.execute("SELECT id FROM predictions").fetchone()[0]
    con.execute(
        "INSERT INTO scores(prediction_id,horizon,scored_date,ret,bench_ret,abnormal,beta_abnormal,hit) "
        "VALUES (?,10,?,0.1,0.0,0.1,0.08,1)", (pid, scored_date))
    con.commit()
    con.close()


class LearnerValidationTest(unittest.TestCase):
    def setUp(self):
        learner._CACHE.clear()

    def tempdir(self):
        return tempfile.TemporaryDirectory()

    def test_exact_scored_date_controls_eligibility(self):
        with self.tempdir() as td:
            root = Path(td)
            tagged = root / "backtest_trial.sqlite"
            make_db(tagged, "AAA", "2024-01-20")
            self.assertEqual(len(learner._rows(tagged, 10, date(2024, 1, 19))), 0)
            self.assertEqual(len(learner._rows(tagged, 10, date(2024, 1, 20))), 1)
            with patch.object(config, "STATE_DIR", root), patch.object(ledger, "DB", tagged):
                early = learner.dataset(10, ["technical"], asof=date(2024, 1, 19))
                mature = learner.dataset(10, ["technical"], asof=date(2024, 1, 20))
            self.assertEqual(len(early[1]), 0)
            self.assertEqual(len(mature[1]), 1)

    def test_tagged_replay_does_not_mix_default_warm_start(self):
        with self.tempdir() as td:
            root = Path(td)
            tagged = root / "backtest_trial.sqlite"
            default = root / "backtest.sqlite"
            make_db(tagged, "AAA", "2024-01-20")
            make_db(default, "BBB", "2024-01-20")
            with patch.object(config, "STATE_DIR", root), patch.object(ledger, "DB", tagged):
                data = learner.dataset(10, ["technical"], asof=date(2024, 1, 20))
            self.assertEqual(len(data[1]), 1)
            self.assertEqual(data[4].tolist(), [1.0])

    def test_live_fit_still_includes_default_warm_start(self):
        with self.tempdir() as td:
            root = Path(td)
            live = root / "ledger.sqlite"
            default = root / "backtest.sqlite"
            make_db(live, "AAA", "2024-01-20")
            make_db(default, "BBB", "2024-01-20")
            with patch.object(config, "STATE_DIR", root), patch.object(ledger, "DB", live):
                data = learner.dataset(10, ["technical"], asof=date(2024, 1, 20))
            self.assertEqual(len(data[1]), 2)
            self.assertEqual(sorted(data[4].tolist()), [0.5, 1.0])

    def test_external_vote_uses_only_trailing_data(self):
        idx = pd.date_range("2023-01-01", periods=220, freq="D")
        rising = np.arange(1.0, 221.0)
        closes = pd.DataFrame({"SPY": rising, "SOXX": rising ** 1.1,
                               "HYG": rising ** 1.05, "LQD": rising}, index=idx)
        multiplier, votes = sweep._external_regime(closes, 219)
        changed_future = closes.copy()
        changed_future.loc[idx[-1] + pd.Timedelta(days=1)] = [1.0, 1.0, 1.0, 1.0]
        multiplier_2, votes_2 = sweep._external_regime(changed_future, 219)
        self.assertEqual((multiplier, votes), (1.0, 3))
        self.assertEqual((multiplier_2, votes_2), (multiplier, votes))

    def test_walk_forward_uses_fold_scale_and_source_weights(self):
        base = date(2024, 1, 1)
        dates = [str(base + timedelta(days=i)) for i in range(15) for _ in range(6)]
        scored = [str(base + timedelta(days=i + 1)) for i in range(15) for _ in range(6)]
        x = np.ones((90, 2))
        y_raw = np.linspace(-0.2, 0.4, 90)
        source_weight = np.tile([1.0, 0.5], 45)
        captured = []

        def fake_ridge(x_train, y_train, d_train, lam, w0):
            captured.append((y_train.copy(), d_train.copy()))
            return w0.copy()

        with patch.object(learner, "ridge", side_effect=fake_ridge):
            learner.walk_forward_ic(x, y_raw, dates, scored, source_weight, np.array([0.5, 0.0]),
                                    150.0, base + timedelta(days=14), 10, last_k=1)
        train = np.array(scored) <= str(base + timedelta(days=14))
        expected_scale = max(float(np.std(y_raw[train])), 0.01)
        expected_d = learner.decay(np.array(dates)[train], base + timedelta(days=14)) * source_weight[train]
        self.assertEqual(len(captured), 1)
        np.testing.assert_allclose(captured[0][0], y_raw[train] / expected_scale)
        np.testing.assert_allclose(captured[0][1], expected_d)

    def test_beta_target_is_parallel_and_explicit(self):
        with self.tempdir() as td:
            root = Path(td)
            tagged = root / "backtest_trial.sqlite"
            make_db(tagged, "AAA", "2024-01-20")
            with patch.object(config, "STATE_DIR", root), patch.object(ledger, "DB", tagged):
                raw = learner.dataset(10, ["technical"], target_mode="raw")
                beta = learner.dataset(10, ["technical"], target_mode="beta")
            self.assertEqual(raw[1].tolist(), [0.1])
            self.assertEqual(beta[1].tolist(), [0.08])

    def test_beta_is_strictly_point_in_time(self):
        idx = pd.date_range("2024-01-01", periods=80, freq="D")
        bench = pd.Series(np.linspace(100, 140, len(idx)), index=idx)
        stock = 50 * (bench / 100) ** 1.5
        closes = pd.DataFrame({"SOXX": bench, "AAA": stock})
        before = learning_targets.rolling_beta(closes)
        value = learning_targets.beta_at(before, "AAA", idx[69])
        changed = closes.copy()
        changed.loc[idx[70]:, "AAA"] *= np.linspace(1, 4, 10)
        after = learning_targets.rolling_beta(changed)
        self.assertAlmostEqual(value, learning_targets.beta_at(after, "AAA", idx[69]), places=12)

    def test_migration_preserves_raw_label_and_adds_beta_label(self):
        with self.tempdir() as td:
            path = Path(td) / "legacy.sqlite"
            con = sqlite3.connect(path)
            con.executescript("""
                CREATE TABLE predictions(
                    id INTEGER PRIMARY KEY, date TEXT, agent TEXT, ticker TEXT,
                    direction REAL, confidence REAL, horizon INTEGER, reason TEXT, price_at REAL);
                CREATE TABLE scores(
                    prediction_id INTEGER, horizon INTEGER, scored_date TEXT,
                    ret REAL, bench_ret REAL, abnormal REAL, hit INTEGER,
                    PRIMARY KEY(prediction_id, horizon));
            """)
            con.execute("INSERT INTO predictions VALUES (1,'2024-03-10','technical','AAA',1,0.5,10,'',100)")
            con.execute("INSERT INTO scores VALUES (1,10,'2024-03-20',0.12,0.05,0.07,1)")
            con.commit()
            con.close()
            idx = pd.date_range("2024-01-01", periods=90, freq="D")
            bench = pd.Series(np.linspace(100, 150, len(idx)), index=idx)
            closes = pd.DataFrame({"SOXX": bench, "AAA": 60 * (bench / 100) ** 1.4})
            migrate_db(path, closes, make_backup=False)
            con = sqlite3.connect(path)
            raw, beta = con.execute("SELECT abnormal,beta_abnormal FROM scores").fetchone()
            stored_beta = con.execute("SELECT benchmark_beta FROM predictions").fetchone()[0]
            con.close()
            self.assertEqual(raw, 0.07)
            self.assertIsNotNone(beta)
            self.assertIsNotNone(stored_beta)
            self.assertAlmostEqual(beta, 0.12 - stored_beta * 0.05)

    def test_exact_research_beta_ledger_can_be_imported(self):
        with self.tempdir() as td:
            root = Path(td)
            raw_path, beta_path = root / "raw.sqlite", root / "beta.sqlite"
            for path, abnormal in ((raw_path, 0.07), (beta_path, 0.02)):
                con = sqlite3.connect(path)
                con.executescript("""
                    CREATE TABLE predictions(
                        id INTEGER PRIMARY KEY, date TEXT, agent TEXT, ticker TEXT,
                        direction REAL, confidence REAL, horizon INTEGER, reason TEXT, price_at REAL);
                    CREATE TABLE scores(
                        prediction_id INTEGER, horizon INTEGER, scored_date TEXT,
                        ret REAL, bench_ret REAL, abnormal REAL, hit INTEGER,
                        PRIMARY KEY(prediction_id, horizon));
                """)
                con.execute("INSERT INTO predictions VALUES (1,'2024-03-10','technical','AAA',1,0.5,10,'',100)")
                con.execute("INSERT INTO scores VALUES (1,10,'2024-03-20',0.12,0.05,?,1)", (abnormal,))
                con.commit()
                con.close()
            self.assertEqual(migrate_db_from_beta_ledger(raw_path, beta_path, make_backup=False), 1)
            con = sqlite3.connect(raw_path)
            raw, beta = con.execute("SELECT abnormal,beta_abnormal FROM scores").fetchone()
            stored_beta = con.execute("SELECT benchmark_beta FROM predictions").fetchone()[0]
            con.close()
            self.assertEqual(raw, 0.07)
            self.assertEqual(beta, 0.02)
            self.assertAlmostEqual(stored_beta, 2.0)


if __name__ == "__main__":
    unittest.main()
