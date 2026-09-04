"""One autonomous Stage-2 discovery cycle. No decisions or execution."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from api.trading_scanner_api import DEFAULT_DB_PATH, ENV_DB_PATH
from experiment1.models import SessionState
from market_data.stooq_provider import StooqDailyProvider
from market_data.yahoo_provider import YahooChartDailyProvider
from trading_scanner.market_data_adapter import MarketDataScannerAdapter
from trading_scanner.scan import run_scan_cycle
from trading_scanner.store import TradingScannerStore

logger = logging.getLogger("gil_trading_scanner_runtime.runtime")
EXIT_OK = 0
EXIT_FAILURE = 1


def _resolve_db_path() -> Path:
    raw = os.environ.get(ENV_DB_PATH)
    return Path(raw) if raw else Path(DEFAULT_DB_PATH)


def _build_market_data_source() -> MarketDataScannerAdapter | None:
    provider_name = os.getenv("TRADING_SCANNER_MARKET_DATA_PROVIDER", "").strip().lower()
    if provider_name not in {"stooq", "yahoo"}:
        return None
    symbols = tuple(
        item.strip().upper()
        for item in os.getenv("TRADING_SCANNER_UNIVERSE_SYMBOLS", "").split(",")
        if item.strip()
    )
    if not symbols:
        raise ValueError("TRADING_SCANNER_UNIVERSE_SYMBOLS is required for stooq provider")
    max_age = int(os.getenv("TRADING_SCANNER_MAX_DATA_AGE_SECONDS", str(4 * 24 * 3600)))
    provider = (
        StooqDailyProvider(symbols, max_age_seconds=max_age)
        if provider_name == "stooq"
        else YahooChartDailyProvider(symbols, max_age_seconds=max_age)
    )
    return MarketDataScannerAdapter(provider)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="gil-trading-scanner-runtime")
    parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    try:
        source = _build_market_data_source()
    except Exception:
        logger.exception("scanner source configuration invalid")
        sys.exit(EXIT_FAILURE)

    if source is None:
        logger.info("scanner cycle skipped - no real market-data provider configured")
        sys.exit(EXIT_OK)

    store = TradingScannerStore(_resolve_db_path())
    try:
        result = asyncio.run(run_scan_cycle(source, store, session_state=SessionState.REGULAR))
    except Exception:
        logger.exception("scanner cycle failed closed")
        sys.exit(EXIT_FAILURE)

    logger.info(
        "scanner cycle complete - contracts_seen=%d candidates_recorded=%d",
        result.contracts_seen,
        len(result.candidates_recorded),
    )
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
