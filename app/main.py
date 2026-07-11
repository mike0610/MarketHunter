"""
MarketHunter

Module:
Application Entry Point

Responsibilities:
- Monitor existing virtual research trades.
- Select liquid USDT Spot symbols.
- Select liquid USDT perpetual Futures contracts.
- Scan configured markets and timeframes.
- Create virtual research trades for qualified signals.
- Persist scan runs and every candidate signal.
- Show only elite signals in Scanner output.
- Send Telegram elite alerts only for Futures during Spot research phase.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from loguru import logger

from pipeline.handlers import (
    EliteSignalHandler,
    ProbabilityHandler,
    ResearchTradeHandler,
    RiskHandler,
)
from pipeline.signal_pipeline import SignalPipeline
from probability.probability_engine import ProbabilityEngine
from research.candidate_promotion_service import CandidatePromotionService
from research.binance_candle_loader import (
    BinanceTradeCandleLoader,
)
from research.manager import ResearchManager
from research.monitor_service import ResearchMonitorService
from research.statistics import ResearchStatistics
from research.storage.repository import ResearchRepository
from research.storage.scan_journal_repository import (
    ScanJournalRepository,
)
from risk.risk_manager import RiskManager
from services.market_data import MarketDataService
from services.scanner import Scanner
from telegram.elite_alerts import notify_elite_signals
from strategies.breaker import BreakerStrategy
from strategies.breakout import BreakoutStrategy
from strategies.choch import CHoCHStrategy
from strategies.compression import CompressionStrategy
from strategies.daily_levels import DailyLevelsStrategy
from strategies.false_breakout import FalseBreakoutStrategy
from strategies.fvg import FVGStrategy
from strategies.liquidity_pool import LiquidityPoolStrategy
from strategies.liquidity_sweep import LiquiditySweepStrategy
from strategies.mitigation import MitigationStrategy
from strategies.order_block import OrderBlockStrategy
from strategies.premium_discount import PremiumDiscountStrategy


DATABASE_PATH = "data/research.db"

SCAN_MARKETS = (
    "futures",
    "spot",
)

SCAN_TIMEFRAMES = (
    "1h",
    "1d",
)

SCAN_CANDLE_LIMIT = 500

FUTURES_SYMBOL_LIMIT = 20
SPOT_SYMBOL_LIMIT = 20

SCANNER_WORKERS = 10

MINIMUM_FUTURES_QUOTE_VOLUME_USDT = 10_000_000.0
MINIMUM_SPOT_QUOTE_VOLUME_USDT = 250_000.0

RESEARCH_MINIMUM_PROBABILITY = 60
ELITE_MINIMUM_PROBABILITY = 80

VIRTUAL_ACCOUNT_SIZE_USDT = 1_000.0
RISK_PER_TRADE_PERCENT = 1.0
TARGET_RISK_REWARD = 2.0
VIRTUAL_TRADE_NOTIONAL_USDT = 100.0

MONITOR_CANDLE_LIMIT = 240


def build_pipeline(
    repository: ResearchRepository,
) -> SignalPipeline:
    """
    Create the MarketHunter signal pipeline.
    """

    probability_engine = ProbabilityEngine()
    risk_manager = RiskManager()
    research_manager = ResearchManager(
        repository,
    )

    return SignalPipeline(
        handlers=[
            ProbabilityHandler(
                engine=probability_engine,
            ),
            RiskHandler(
                manager=risk_manager,
                account_size=VIRTUAL_ACCOUNT_SIZE_USDT,
                risk_percent=RISK_PER_TRADE_PERCENT,
                rr=TARGET_RISK_REWARD,
            ),
            ResearchTradeHandler(
                manager=research_manager,
                minimum_probability=(
                    RESEARCH_MINIMUM_PROBABILITY
                ),
                notional=VIRTUAL_TRADE_NOTIONAL_USDT,
            ),
            EliteSignalHandler(
                minimum_probability=ELITE_MINIMUM_PROBABILITY,
            ),
        ]
    )


def build_strategies(
    timeframe: str,
):
    """
    Create strategy instances for one scanner run.

    DailyLevelsStrategy is intentionally enabled only for 1D scans.
    """

    normalized_timeframe = str(
        timeframe or "",
    ).strip().lower()

    strategies = [
        BreakoutStrategy(),
        FalseBreakoutStrategy(),
        CompressionStrategy(),
        CHoCHStrategy(),
        FVGStrategy(),
        OrderBlockStrategy(),
        LiquidityPoolStrategy(),
        LiquiditySweepStrategy(),
        MitigationStrategy(),
        BreakerStrategy(),
        PremiumDiscountStrategy(),
    ]

    if normalized_timeframe == "1d":
        strategies.append(
            DailyLevelsStrategy(),
        )

    return strategies

def market_symbol_limit(
    market: str,
) -> int:
    """
    Return configured symbol limit for one market.
    """

    if market == "spot":
        return SPOT_SYMBOL_LIMIT

    return FUTURES_SYMBOL_LIMIT


def market_min_quote_volume(
    market: str,
) -> float:
    """
    Return configured minimum 24h quote volume for one market.
    """

    if market == "spot":
        return MINIMUM_SPOT_QUOTE_VOLUME_USDT

    return MINIMUM_FUTURES_QUOTE_VOLUME_USDT


async def load_symbols_for_market(
    market_data: MarketDataService,
    market: str,
):
    """
    Load liquid symbols for one market.
    """

    symbol_limit = market_symbol_limit(
        market,
    )

    min_quote_volume = market_min_quote_volume(
        market,
    )

    symbols = await market_data.load_liquid_symbols(
        market=market,
        min_quote_volume_usdt=min_quote_volume,
        max_symbols=symbol_limit,
    )

    logger.info(
        "Loaded liquid {} symbols: {} | Min 24h quote volume: {:.0f} USDT",
        market,
        len(symbols),
        min_quote_volume,
    )

    return symbols


async def promote_candidate_trades(
    repository: ResearchRepository,
    market_data: MarketDataService,
) -> None:
    """
    Promote candidate/watchlist trades when conditions become valid.
    """

    service = CandidatePromotionService(
        repository=repository,
    )

    candle_loader = BinanceTradeCandleLoader(
        market_data=market_data,
        limit=MONITOR_CANDLE_LIMIT,
    )

    result = await service.run_once(
        candle_loader=candle_loader,
    )

    logger.info(
        "Candidate promotion | Candidates: {} | Checked: {} | "
        "Promoted: {} | Blocked: {} | Skipped: {}",
        result.candidates,
        result.checked,
        result.promoted,
        result.blocked,
        result.skipped_without_candles,
    )

    for error in result.errors:
        logger.warning(
            "Candidate promotion error: {}",
            error,
        )


async def monitor_open_trades(
    repository: ResearchRepository,
    market_data: MarketDataService,
) -> None:
    """
    Update all waiting and active virtual trades.
    """

    service = ResearchMonitorService(
        repository=repository,
    )

    candle_loader = BinanceTradeCandleLoader(
        market_data=market_data,
        limit=MONITOR_CANDLE_LIMIT,
    )

    result = await service.run_once(
        candle_loader=candle_loader,
    )

    logger.info(
        "Monitor | Open: {} | Checked: {} | Activated: {} | "
        "TP: {} | SL: {} | Expired: {} | Candidate: {} | Skipped: {}",
        result.open_trades,
        result.monitored_trades,
        result.activated,
        result.closed_tp,
        result.closed_sl,
        result.expired,
        result.revalidated_to_candidate,
        result.skipped_without_candles,
    )

    for error in result.errors:
        logger.warning(
            "Monitor error: {}",
            error,
        )


def handle_elite_alerts(
    *,
    market: str,
    elite_signals,
) -> int:
    """
    Send Telegram elite alerts only for Futures.

    Spot elite signals are kept in research/statistics during the
    experimental Spot research phase.
    """

    if not elite_signals:
        logger.info(
            "No signals passed elite threshold."
        )

        return 0

    if market != "futures":
        logger.info(
            "Spot elite signals found: {} | Telegram skipped for research phase.",
            len(elite_signals),
        )

        return 0

    telegram_alerts_sent = notify_elite_signals(
        elite_signals,
    )

    if telegram_alerts_sent:
        logger.info(
            "Telegram elite alerts sent: {}",
            telegram_alerts_sent,
        )

    return telegram_alerts_sent


async def run_scan_for_market_timeframe(
    *,
    market: str,
    scan_timeframe: str,
    symbols,
    repository: ResearchRepository,
    scan_journal: ScanJournalRepository,
    market_data: MarketDataService,
) -> tuple[int, int]:
    """
    Run scanner once for one market and one timeframe.

    Returns:
    - created research trades
    - elite signals found
    """

    symbol_limit = market_symbol_limit(
        market,
    )

    min_quote_volume = market_min_quote_volume(
        market,
    )

    logger.info("=" * 60)
    logger.info(
        "Starting scan | Market: {} | Timeframe: {} | Symbols: {}",
        market,
        scan_timeframe,
        len(symbols),
    )

    scan_run = scan_journal.create_scan_run(
        timeframe=scan_timeframe,
        candle_limit=SCAN_CANDLE_LIMIT,
        symbol_limit=symbol_limit,
        min_quote_volume_usdt=min_quote_volume,
        research_minimum_probability=(
            RESEARCH_MINIMUM_PROBABILITY
        ),
        elite_minimum_probability=(
            ELITE_MINIMUM_PROBABILITY
        ),
        started_at=datetime.now(
            UTC,
        ),
    )

    scan_run_id = scan_run.id

    try:
        logger.info(
            "Scan journal run started: {} | Market: {} | Timeframe: {}",
            scan_run_id,
            market,
            scan_timeframe,
        )

        pipeline = build_pipeline(
            repository=repository,
        )

        trades_before = len(
            repository.list_all()
        )

        scanner = Scanner(
            market_data=market_data,
            strategies=build_strategies(timeframe=scan_timeframe),
            workers=SCANNER_WORKERS,
            pipeline=pipeline,
            timeframe=scan_timeframe,
            candle_limit=SCAN_CANDLE_LIMIT,
            scan_journal=scan_journal,
            scan_run_id=scan_run_id,
        )

        elite_signals = await scanner.scan_many(
            symbols,
        )

        trades_after = repository.list_all()

        created_trades = max(
            0,
            len(trades_after) - trades_before,
        )

        elite_signals_found = len(
            elite_signals,
        )

        signal_summary = scan_journal.get_signal_record_summary(
            scan_run_id=scan_run_id,
        )

        scan_journal.finish_scan_run(
            scan_run_id=scan_run_id,
            status="completed",
            finished_at=datetime.now(
                UTC,
            ),
            symbols_scanned=len(symbols),
            candidate_signals=signal_summary["total"],
            research_trades_created=created_trades,
            elite_signals_found=elite_signals_found,
        )

        logger.info("")
        logger.info("=" * 60)
        logger.info(
            "Scan journal | Market: {} | Timeframe: {} | Total: {} | "
            "Rejected: {} | Research: {} | Elite: {}",
            market,
            scan_timeframe,
            signal_summary["total"],
            signal_summary["rejected"],
            signal_summary["research"],
            signal_summary["elite"],
        )

        logger.info(
            "Research trades created this scan: {}",
            created_trades,
        )

        logger.info(
            "Elite signals found: {}",
            elite_signals_found,
        )

        logger.info("=" * 60)

        handle_elite_alerts(
            market=market,
            elite_signals=elite_signals,
        )

        for signal in elite_signals:
            probability = signal.metadata.get(
                "probability",
                "N/A",
            )

            risk = signal.metadata.get(
                "risk",
                {},
            )

            logger.info(
                "[{}] {} {} {} {} | Score: {} | Probability: {}%",
                signal.strategy,
                signal.market.upper(),
                signal.symbol,
                signal.timeframe,
                signal.direction,
                signal.score,
                probability,
            )

            if risk:
                logger.info(
                    "    Entry: {} | SL: {} | TP: {} | RR: {}",
                    risk.get("entry"),
                    risk.get("stop_loss"),
                    risk.get("take_profit"),
                    risk.get("risk_reward"),
                )

            for reason in signal.reasons:
                logger.info(
                    "    • {}",
                    reason,
                )

            logger.info("-" * 60)

        return (
            created_trades,
            elite_signals_found,
        )

    except Exception as exc:
        signal_summary = scan_journal.get_signal_record_summary(
            scan_run_id=scan_run_id,
        )

        scan_journal.finish_scan_run(
            scan_run_id=scan_run_id,
            status="failed",
            finished_at=datetime.now(
                UTC,
            ),
            symbols_scanned=len(symbols),
            candidate_signals=signal_summary["total"],
            research_trades_created=0,
            elite_signals_found=0,
            error=f"{type(exc).__name__}: {exc}",
        )

        raise


async def main() -> None:
    """
    Run one MarketHunter research cycle.
    """

    logger.info("=" * 60)
    logger.info("MarketHunter — Research Engine MVP")
    logger.info("=" * 60)

    repository = ResearchRepository(
        path=DATABASE_PATH,
    )

    scan_journal = ScanJournalRepository(
        path=DATABASE_PATH,
    )

    market_data = MarketDataService()

    symbols_scanned = 0
    created_trades_total = 0
    elite_signals_found_total = 0

    try:
        await market_data.ping()

        await promote_candidate_trades(
            repository=repository,
            market_data=market_data,
        )

        await monitor_open_trades(
            repository=repository,
            market_data=market_data,
        )

        logger.info(
            "Scanner | Markets: {} | Timeframes: {} | Candles: {}",
            ", ".join(SCAN_MARKETS),
            ", ".join(SCAN_TIMEFRAMES),
            SCAN_CANDLE_LIMIT,
        )

        logger.info(
            "Research threshold: {}% | Elite threshold: {}%",
            RESEARCH_MINIMUM_PROBABILITY,
            ELITE_MINIMUM_PROBABILITY,
        )

        for market in SCAN_MARKETS:
            symbols = await load_symbols_for_market(
                market_data=market_data,
                market=market,
            )

            if not symbols:
                logger.warning(
                    "No liquid {} symbols found.",
                    market,
                )

                continue

            symbols_scanned += len(
                symbols,
            )

            for scan_timeframe in SCAN_TIMEFRAMES:
                try:
                    (
                        created_trades,
                        elite_signals_found,
                    ) = await run_scan_for_market_timeframe(
                        market=market,
                        scan_timeframe=scan_timeframe,
                        symbols=symbols,
                        repository=repository,
                        scan_journal=scan_journal,
                        market_data=market_data,
                    )

                except Exception:
                    logger.exception(
                        "Scan failed | Market: {} | Timeframe: {}",
                        market,
                        scan_timeframe,
                    )

                    raise

                created_trades_total += created_trades
                elite_signals_found_total += elite_signals_found

        trades = repository.list_all()

        statistics = ResearchStatistics().calculate(
            trades,
        )

        logger.info("")
        logger.info("=" * 60)
        logger.info("Research statistics")
        logger.info("=" * 60)
        logger.info(
            "All trades: {} | Waiting: {} | Active: {} | "
            "Completed: {}",
            statistics["total"],
            statistics["waiting_entry"],
            statistics["active"],
            statistics["completed"],
        )
        logger.info(
            "Wins: {} | Losses: {} | Win rate: {:.2f}%",
            statistics["wins"],
            statistics["losses"],
            statistics["win_rate"],
        )
        logger.info(
            "Total PnL: {:.2f} USDT | Average RR: {:.2f}",
            statistics["total_profit"],
            statistics["average_rr"],
        )

        logger.info(
            "Cycle totals | Symbols loaded: {} | Research created: {} | "
            "Elite found: {}",
            symbols_scanned,
            created_trades_total,
            elite_signals_found_total,
        )

    finally:
        repository.close()
        scan_journal.close()
        await market_data.close()


if __name__ == "__main__":
    asyncio.run(
        main(),
    )
