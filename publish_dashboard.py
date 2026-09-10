"""Re-publish state/dashboard.json to the Blob store, refreshing the backtest
section from state/backtest_report.json. Use after re-running the backtest so
the website shows the new report without waiting for the next cycle (which
would also add predictions to the live ledger if run by hand).

    python publish_dashboard.py
"""
import json

import config
import journal


def main():
    dash = json.loads(journal.DASHBOARD_FILE.read_text(encoding="utf-8")) if journal.DASHBOARD_FILE.exists() else {}
    path = config.STATE_DIR / "backtest_report.json"
    if path.exists():
        bt = json.loads(path.read_text(encoding="utf-8"))
        curve = bt.get("curve") or []
        step = max(1, len(curve) // 120)
        bt["curve"] = curve[::step] + ([curve[-1]] if curve and (len(curve) - 1) % step else [])
        dash["backtest"] = bt
    dash.pop("generated", None)
    journal.publish_dashboard(dash)
    print("published: backtest", "yes" if path.exists() else "no", "| keys", sorted(dash.keys()))


if __name__ == "__main__":
    main()
