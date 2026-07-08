"""
MarketHunter

Module:
Application Entry Point

Responsibilities:
- Monitor existing virtual research trades.
- Select liquid USDT perpetual Futures contracts.
- Scan one configured timeframe.
- Create virtual research trades for qualified signals.
- Persist scan runs and every candidate signal.
- Show only elite signals in Scanner output.
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
from strategies.breaker import BreakerStrategy
from strategies.breakout import BreakoutStrategy
from strategies.choch import CHoCHStrategy
from strategies.compression import CompressionStrategy
from strategies.false_breakout import FalseBreakoutStrategy
from strategies.fvg import FVGStrategy
from strategies.liquidity_pool import LiquidityPoolStrategy
from strategies.mitigation import MitigationStrategy
from strategies.order_block import OrderBlockStrategy
from strategies.premium_discount import PremiumDiscountStrategy


DATABASE_PATH = "data/research.db"

SCAN_TIMEFRAME = "1h"
SCAN_CANDLE_LIMIT = 500
SCAN_SYMBOL_LIMIT = 20
SCANNER_WORKERS = 10

MINIMUM_FUTURES_QUOTE_VOLUME_USDT = 10_000_000.0

RESEARCH_MINIMUM_PROBABILITY = 60
ELITE_MINIMUM_PROBABILITY = 80

VIRTUAL_ACCOUNT_SIZE_USDT = 1_000.0
RISK_PER_TRADE_PERCENT = 1.0
TARGET_RISK_REWARD = 2.0
VIRTUAL_TRADE_NOTIONAL_USDT = 100.0

MONITOR_CANDLE_LIMIT = 120


def build_pipeline(
    repository: ResearchRepository,
) -> SignalPipeline:
    """
    Create the MarketHunter signal pipeline.
    """

    probability_engine = ProbabilityEngine()
    risk_manager = RiskManager()
    research_manager = ResearchManager(repository)

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
        "TP: {} | SL: {} | Expired: {} | Skipped: {}",
        result.open_trades,
        result.monitored_trades,
        result.activated,
        result.closed_tp,
        result.closed_sl,
        result.expired,
        result.skipped_without_candles,
    )

    for error in result.errors:
        logger.warning(
            "Monitor error: {}",
            error,
        )


async def main() -> None:
    """
    Run one MarketHunter research cycle.
    """

    logger.info("=" * 60)
    logger.info("MarketHunter вЂ” Research Engine MVP")
    logger.info("=" * 60)

    repository = ResearchRepository(
        path=DATABASE_PATH,
    )

    scan_journal = ScanJournalRepository(
        path=DATABASE_PATH,
    )

    market_data = MarketDataService()

    scan_run_id: str | None = None
    symbols_scanned = 0
    created_trades = 0
    elite_signals_found = 0

    try:
        await market_data.ping()

        await monitor_open_trades(
            repository=repository,
            market_data=market_data,
        )

        symbols = await market_data.load_liquid_futures_symbols(
            min_quote_volume_usdt=(
                MINIMUM_FUTURES_QUOTE_VOLUME_USDT
            ),
            max_symbols=SCAN_SYMBOL_LIMIT,
        )

        if not symbols:
            logger.warning(
                "No liquid USDT perpetual Futures symbols found."
            )
            return

        symbols_scanned = len(symbols)

        logger.info(
            "Loaded liquid perpetual Futures: {}",
            len(symbols),
        )

        logger.info(
            "Scanner | Timeframe: {} | Candles: {} | "
            "Min 24h quote volume: {:.0f} USDT",
            SCAN_TIMEFRAME,
            SCAN_CANDLE_LIMIT,
            MINIMUM_FUTURES_QUOTE_VOLUME_USDT,
        )

        logger.info(
            "Research threshold: {}% | Elite threshold: {}%",
            RESEARCH_MINIMUM_PROBABILITY,
            ELITE_MINIMUM_PROBABILITY,
        )

        scan_run = scan_journal.create_scan_run(
            timeframe=SCAN_TIMEFRAME,
            candle_limit=SCAN_CANDLE_LIMIT,
            symbol_limit=SCAN_SYMBOL_LIMIT,
            min_quote_volume_usdt=(
                MINIMUM_FUTURES_QUOTE_VOLUME_USDT
            ),
            research_minimum_probability=(
                RESEARCH_MINIMUM_PROBABILITY
            ),
            elite_minimum_probability=(
                ELITE_MINIMUM_PROBABILITY
            ),
            started_at=datetime.now(UTC),
        )

        scan_run_id = scan_run.id

        logger.info(
            "Scan journal run started: {}",
            scan_run_id,
        )

        pipeline = build_pipeline(
            repository=repository,
        )

        trades_before = len(
            repository.list_all()
        )

        scanner = Scanner(
            market_data=market_data,
            strategies=[
                BreakoutStrategy(),
                FalseBreakoutStrategy(),
                CompressionStrategy(),
                CHoCHStrategy(),
                FVGStrategy(),
                OrderBlockStrategy(),
                LiquidityPoolStrategy(),
                MitigationStrategy(),
                BreakerStrategy(),
                PremiumDiscountStrategy(),
            ],
            workers=SCANNER_WORKERS,
            pipeline=pipeline,
            timeframe=SCAN_TIMEFRAME,
            candle_limit=SCAN_CANDLE_LIMIT,
            scan_journal=scan_journal,
            scan_run_id=scan_run_id,
        )

        elite_signals = await scanner.scan_many(
            symbols,
        )

        trades = repository.list_all()

        created_trades = max(
            0,
            len(trades) - trades_before,
        )

        elite_signals_found = len(elite_signals)

        signal_summary = (
            scan_journal.get_signal_record_summary(
                scan_run_id=scan_run_id,
            )
        )

        scan_journal.finish_scan_run(
            scan_run_id=scan_run_id,
            status="completed",
            finished_at=datetime.now(UTC),
            symbols_scanned=symbols_scanned,
            candidate_signals=signal_summary["total"],
            research_trades_created=created_trades,
            elite_signals_found=elite_signals_found,
        )

        logger.info("")
        logger.info("=" * 60)
        logger.info(
            "Scan journal | Total: {} | Rejected: {} | "
            "Research: {} | Elite: {}",
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

        if not elite_signals:
            logger.info(
                "No signals passed elite threshold."
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
                    "    вЂў {}",
                    reason,
                )

            logger.info("-" * 60)

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

    except Exception as exc:
        if scan_run_id is not None:
            summary = scan_journal.get_signal_record_summary(
                scan_run_id=scan_run_id,
            )

            scan_journal.finish_scan_run(
                scan_run_id=scan_run_id,
                status="failed",
                finished_at=datetime.now(UTC),
                symbols_scanned=symbols_scanned,
                candidate_signals=summary["total"],
                research_trades_created=created_trades,
                elite_signals_found=elite_signals_found,
                error=f"{type(exc).__name__}: {exc}",
            )

        raise

    finally:
        repository.close()
        scan_journal.close()
        await market_data.close()


if __name__ == "__main__":
    asyncio.run(main())
