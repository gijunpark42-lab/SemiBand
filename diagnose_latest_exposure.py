"""Read-only replay of saved paper opinions; never runs agents, refits or orders."""
import json
import sqlite3
from pathlib import Path

import config
import learner
import portfolio
from agents.base import Signal


def main():
    source = Path('C:/Users/calif/Desktop/Trading/state')
    with sqlite3.connect((source / 'ledger.sqlite').as_uri() + '?mode=ro', uri=True) as con:
        con.row_factory = sqlite3.Row
        latest = con.execute('SELECT MAX(date) FROM predictions').fetchone()[0]
        rows = con.execute('SELECT * FROM predictions WHERE date=? ORDER BY id', (latest,)).fetchall()
    signals = [Signal(r['agent'], r['ticker'], r['direction'], r['confidence'], r['horizon'], r['reason'])
               for r in rows]
    # Read-only broker snapshot recorded by root, not a new broker request or current quote.
    equity = 1006860.73
    results = []
    original_gross, original_size = config.GROSS_TARGET, config.SIZE_PER_CONVICTION
    try:
        for mode, filename in [('raw', 'model_raw_shadow.json'), ('beta', 'model.json')]:
            model = json.loads((source / filename).read_text(encoding='utf-8'))
            assert model['target_mode'] == mode
            convictions, _ = learner.predict(signals, model)
            if config.DEMEAN_CONVICTION and convictions:
                avg = sum(convictions.values()) / len(convictions)
                convictions = {t: c - avg for t, c in convictions.items()}
            for name, gross, size in [('baseline', 1.5, 0.6), ('gross2_only', 2.0, 0.6),
                                      ('size08_only', 1.5, 0.8), ('gross2_size08', 2.0, 0.8)]:
                config.GROSS_TARGET, config.SIZE_PER_CONVICTION = gross, size
                targets = portfolio.targets(convictions, equity, realized_vol=None)
                results.append({'mode': mode, 'variant': name, 'names': len(targets),
                                'target_usd': round(sum(targets.values()), 2),
                                'gross': sum(targets.values()) / equity, 'targets': targets})
            results.append({'mode': mode, 'top_convictions': sorted(convictions.items(), key=lambda x: -x[1])[:10]})
    finally:
        config.GROSS_TARGET, config.SIZE_PER_CONVICTION = original_gross, original_size
    payload = {'saved_opinion_date': latest, 'signals': len(signals), 'reference_equity': equity,
               'limitations': ['Uses saved opinions and newly fitted models; not fresh Monday signals.',
                               'No guardian exclusion, account volatility scaling, rebalance band or execution.',
                               'Illustrative intended targets, not realized returns or future orders.'],
               'results': results}
    out = Path('C:/Users/calif/Documents/Codex/2026-09-12/semiband-research/outputs/latest_exposure_diagnostic.json')
    out.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    print(json.dumps(payload, indent=2))


if __name__ == '__main__':
    main()
