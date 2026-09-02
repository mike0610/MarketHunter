"""
MarketHunter

tools/gil_trading_scanner_runtime/runtime.py

Module:
The GIL Trading Scanner's recurring scan cycle - one bounded pass a
systemd timer invokes on a cadence (see deploy/systemd/), mirroring
tools/experiment1_runtime/runtime.py's own pattern exactly.

Fail-closed contract: build_ibkr_universe_source() returns None today
(see trading_scanner/universe.py's own docstring for exactly why - a
genuine, honestly-reported BLOCKED-IBKR-SESSION boundary, not a
credential check). This entry point detects that and skips the scan
entirely - a normal, successful no-op, never a crash and never a
fabricated cycle result. Once a real universe source exists, this
module needs zero changes to start actually running scans.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from api.trading_scanner_api import DEFAULT_DB_PATH, ENV_DB_PATH
from experiment1.models import SessionState
from trading_scanner.scan import run_scan_cycle
from trading_scanner.store import TradingScannerStore
from trading_scanner.universe import build_ibkr_universe_source

logger = logging.getLogger("gil_trading_scanner_runtime.runtime")

EXIT_OK = 0
EXIT_FAILURE = 1


def _resolve_db_path() -> Path:
    raw = os.environ.get(ENV_DB_PATH)
    return Path(raw) if raw else Path(DEFAULT_DB_PATH)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="gil-trading-scanner-runtime")
    parser.parse_args(argv)  # no subcommands - one bounded cycle per invocation

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    universe_source = build_ibkr_universe_source()
    if universe_source is None:
        logger.info("gil trading scanner cycle skipped - BLOCKED-IBKR-SESSION (no universe source configured)")
        sys.exit(EXIT_OK)

    db_path = _resolve_db_path()
    logger.info("gil trading scanner cycle starting - db=%s", db_path)
    store = TradingScannerStore(db_path)

    try:
        result = asyncio.run(run_scan_cycle(universe_source, store, session_state=SessionState.REGULAR))
    except Exception:
        logger.exception("gil trading scanner cycle failed")
        sys.exit(EXIT_FAILURE)

    logger.info(
        "gil trading scanner cycle complete - contracts_seen=%d candidates_recorded=%d",
        result.contracts_seen,
        len(result.candidates_recorded),
    )
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
