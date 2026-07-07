"""
MarketHunter

Module:
Application Entry Point

Responsibilities:
- Configure MarketHunter dependencies.
- Monitor existing virtual research trades.
- Build the signal pipeline.
- Run Scanner.
- Store research-qualified signals as virtual trades.
- Show only elite signals in Scanner output.
"""

from __future__ import annotations

import asyncio

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

SCAN_SYMBOL_LIMIT = 20
SCANNER_WORKERS = 10

RESEARCH_MINIMUM_PROBABILITY = 40
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
    Create the standard MarketHunter signal pipeline.
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
    Process all existing virtual trades using completed Binance candles.
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
    logger.info("MarketHunter — Research Engine MVP")
    logger.info("=" * 60)

    repository = ResearchRepository(
        path=DATABASE_PATH,
    )

    market_data = MarketDataService()

    try:
        await market_data.ping()

        await monitor_open_trades(
            repository=repository,
            market_data=market_data,
        )

        pipeline = build_pipeline(repository)

        symbols = await market_data.load_symbols()

        logger.info(
            "Loaded symbols: {}",
            len(symbols),
        )

        logger.info(
            "Research threshold: {}% | Elite threshold: {}%",
            RESEARCH_MINIMUM_PROBABILITY,
            ELITE_MINIMUM_PROBABILITY,
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
        )

        elite_signals = await scanner.scan_many(
            symbols[:SCAN_SYMBOL_LIMIT],
        )

        trades = repository.list_all()

        created_trades = max(
            0,
            len(trades) - trades_before,
        )

        logger.info("")
        logger.info("=" * 60)
        logger.info(
            "Research trades created this scan: {}",
            created_trades,
        )
        logger.info(
            "Elite signals found: {}",
            len(elite_signals),
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
                "[{}] {} {} {} | Score: {} | Probability: {}%",
                signal.strategy,
                signal.market.upper(),
                signal.symbol,
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

    finally:
        repository.close()
        await market_data.close()


if __name__ == "__main__":
    asyncio.run(main())