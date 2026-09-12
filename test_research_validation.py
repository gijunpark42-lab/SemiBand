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
    con.execute("INSERT INTO scores VALUES (?,10,?,0.1,0.0,0.1,1)", (pid, scored_date))
    con.commit()
    con.close()


class LearnerValidationTest(unittest.TestCase):
    def setUp(self):
        learner._CACHE.clear()

    def tempdir(self):
        return tempfile.TemporaryDirectory(dir=Path(__file__).parent)

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


if __name__ == "__main__":
    unittest.main()
