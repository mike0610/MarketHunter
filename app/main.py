"""
MarketHunter

app/main.py
"""

from __future__ import annotations

import asyncio

from loguru import logger

from services.market_data import MarketDataService
from services.scanner import Scanner

from strategies.breakout import BreakoutStrategy
from strategies.false_breakout import FalseBreakoutStrategy
from strategies.compression import CompressionStrategy
from strategies.choch import CHoCHStrategy
from strategies.fvg import FVGStrategy
from strategies.order_block import OrderBlockStrategy
from strategies.liquidity_pool import LiquidityPoolStrategy
from strategies.mitigation import MitigationStrategy
from strategies.breaker import BreakerStrategy
from strategies.premium_discount import PremiumDiscountStrategy


async def main() -> None:

    logger.info("=" * 60)
    logger.info("MarketHunter")
    logger.info("=" * 60)

    market_data = MarketDataService()

    await market_data.ping()

    symbols = await market_data.load_symbols()

    logger.info(
        "Loaded symbols: {}",
        len(symbols),
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
        workers=10,
    )

    signals = await scanner.scan_many(
        symbols[:20],
    )

    logger.info("")
    logger.info("=" * 60)
    logger.info(
        "Signals found: {}",
        len(signals),
    )
    logger.info("=" * 60)

    if not signals:

        logger.info(
            "No signals found."
        )

    else:

        for signal in signals:

            logger.info(
                "[{}] {} {} {} Score:{}",
                signal.strategy,
                signal.market.upper(),
                signal.symbol,
                signal.direction,
                signal.score,
            )

            for reason in signal.reasons:

                logger.info(
                    "    • {}",
                    reason,
                )

            logger.info("-" * 60)

    await market_data.close()


if __name__ == "__main__":
    asyncio.run(main())