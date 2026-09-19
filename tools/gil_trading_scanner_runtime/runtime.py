"""One autonomous Stage-2 discovery cycle. No decisions or execution."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import logging
import os
import sys
from pathlib import Path

from api.trading_scanner_api import DEFAULT_DB_PATH, ENV_DB_PATH
from experiment1.models import SessionState
from market_data.stooq_provider import StooqDailyProvider
from market_data.twelve_data_provider import TwelveDataDailyProvider
from market_data.yahoo_provider import YahooChartDailyProvider
from trading_scanner.market_data_adapter import MarketDataScannerAdapter
from trading_scanner.scan import run_scan_cycle
from trading_scanner.research_strategy_pipe import scan_existing_research_strategies
from trading_scanner.research_strategy_signal_store import ResearchStrategySignalStore
from trading_scanner.store import TradingScannerStore

logger = logging.getLogger("gil_trading_scanner_runtime.runtime")
EXIT_OK = 0
EXIT_FAILURE = 1
ENV_BATCH_SIZE = "TRADING_SCANNER_UNIVERSE_BATCH_SIZE"
ENV_BATCH_STATE_PATH = "TRADING_SCANNER_UNIVERSE_BATCH_STATE_PATH"


def _select_universe_batch(symbols: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[Path, int] | None]:
    """Select a persistent round-robin slice without increasing provider calls/cycle."""
    batch_size = int(os.getenv(ENV_BATCH_SIZE, "0"))
    if batch_size <= 0 or batch_size >= len(symbols):
        return symbols, None
    state_path = Path(os.getenv(ENV_BATCH_STATE_PATH, "data/trading_scanner_universe_cursor.txt"))
    try:
        cursor = int(state_path.read_text(encoding="utf-8").strip()) if state_path.exists() else 0
    except (OSError, ValueError):
        cursor = 0
    cursor %= len(symbols)
    selected = tuple(symbols[(cursor + offset) % len(symbols)] for offset in range(batch_size))
    next_cursor = (cursor + batch_size) % len(symbols)
    logger.info(
        "universe batch selected - total=%d batch=%d cursor=%d next_cursor=%d symbols=%s",
        len(symbols), len(selected), cursor, next_cursor, ",".join(selected),
    )
    return selected, (state_path, next_cursor)


def _commit_universe_cursor(state: tuple[Path, int] | None) -> None:
    if state is None:
        return
    state_path, next_cursor = state
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = state_path.with_suffix(state_path.suffix + ".tmp")
    tmp_path.write_text(str(next_cursor), encoding="utf-8")
    tmp_path.replace(state_path)


def _resolve_db_path() -> Path:
    raw = os.environ.get(ENV_DB_PATH)
    return Path(raw) if raw else Path(DEFAULT_DB_PATH)


def _build_market_data_source() -> tuple[MarketDataScannerAdapter | None, tuple[Path, int] | None]:
    provider_name = os.getenv("TRADING_SCANNER_MARKET_DATA_PROVIDER", "").strip().lower()
    if provider_name not in {"stooq", "yahoo", "twelve_data"}:
        return None, None
    symbols = tuple(
        item.strip().upper()
        for item in os.getenv("TRADING_SCANNER_UNIVERSE_SYMBOLS", "").split(",")
        if item.strip()
    )
    if not symbols:
        raise ValueError("TRADING_SCANNER_UNIVERSE_SYMBOLS is required for configured provider")
    batch_state = None
    if provider_name == "twelve_data":
        symbols, batch_state = _select_universe_batch(symbols)
    max_age = int(os.getenv("TRADING_SCANNER_MAX_DATA_AGE_SECONDS", str(4 * 24 * 3600)))
    if provider_name == "stooq":
        provider = StooqDailyProvider(symbols, max_age_seconds=max_age)
    elif provider_name == "yahoo":
        provider = YahooChartDailyProvider(symbols, max_age_seconds=max_age)
    else:
        native_history_limit = int(os.getenv("TRADING_SCANNER_HISTORY_LIMIT", "120"))
        research_history_limit = int(os.getenv("TRADING_SCANNER_RESEARCH_STRATEGY_HISTORY_LIMIT", "500"))
        # Twelve Data's free tier is rate-limited. Preload each symbol once with
        # the largest history window needed by either scanner path so the
        # unchanged Research-strategy pipe reuses the provider cache instead of
        # issuing a second request per symbol (5 symbols previously became
        # 10 requests/cycle and triggered HTTP 429).
        provider = TwelveDataDailyProvider(
            symbols,
            max_age_seconds=max_age,
            history_limit=max(native_history_limit, research_history_limit),
        )
        return MarketDataScannerAdapter(provider, history_limit=native_history_limit), batch_state
    return MarketDataScannerAdapter(provider), batch_state


def run_once():
    """Run one real-data scanner cycle without process-exit side effects.

    This is the reusable no-Slack seam consumed by Stage 9 orchestration.
    It preserves the scanner's existing fail-closed configuration rules.
    """
    source, batch_state = _build_market_data_source()
    if source is None:
        logger.info("scanner cycle skipped - no real market-data provider configured")
        return None

    store = TradingScannerStore(_resolve_db_path())
    async def run_all():
        native = await run_scan_cycle(source, store, session_state=SessionState.REGULAR)
        piped = await scan_existing_research_strategies(
            source.provider,
            history_limit=int(os.getenv("TRADING_SCANNER_RESEARCH_STRATEGY_HISTORY_LIMIT", "500")),
        )
        return native, piped

    result, piped = asyncio.run(run_all())
    piped_store_path = os.getenv("TRADING_SCANNER_RESEARCH_STRATEGY_DB_PATH", "data/research_strategy_signals.db")
    ResearchStrategySignalStore(piped_store_path).record_many(
        piped,
        seen_at=datetime.now(timezone.utc),
    )
    _commit_universe_cursor(batch_state)
    logger.info(
        "scanner cycle complete - contracts_seen=%d native_candidates=%d piped_research_strategy_candidates=%d",
        result.contracts_seen,
        len(result.candidates_recorded),
        len(piped),
    )
    return result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="gil-trading-scanner-runtime")
    parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    try:
        run_once()
    except Exception:
        logger.exception("scanner cycle failed closed")
        sys.exit(EXIT_FAILURE)

    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
