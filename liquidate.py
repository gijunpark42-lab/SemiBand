"""Fresh start: cancel every open order and liquidate every position
(stocks and crypto) in the paper account, journaling each exit.

    python liquidate.py            do it (honors config.DRY_RUN)
    python liquidate.py --dry-run  only print what would be closed
"""
import logging
import sys
import time

import broker
import config
import journal

log = logging.getLogger("liquidate")


def run(dry_run=None, wait_s=180):
    dry = config.DRY_RUN if dry_run is None else dry_run
    pos = broker.positions()
    log.info("liquidating %d positions (dry_run=%s)", len(pos), dry)
    for s, p in sorted(pos.items()):
        journal.record(s, "SELL", "fresh start: liquidate everything before the ensemble study",
                       p.current_price, notional=float(p.market_value), dry_run=dry)
        log.info("  close %s $%.2f", s, float(p.market_value))
    if dry or not pos:
        return len(pos)
    broker.close_all(dry_run=False)
    deadline = time.time() + wait_s
    while time.time() < deadline:
        time.sleep(10)
        left = broker.positions()
        if not left:
            log.info("all positions closed")
            return len(pos)
        log.info("waiting for fills, %d left", len(left))
    log.warning("some positions still open after %ss: %s", wait_s, sorted(broker.positions()))
    return len(pos)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    n = run(dry_run="--dry-run" in sys.argv)
    print(f"{n} positions {'would be' if '--dry-run' in sys.argv else ''} closed")
