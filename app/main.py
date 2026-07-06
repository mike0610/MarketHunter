"""
MarketHunter

app/main.py
"""

from __future__ import annotations

import asyncio

from services.market_data import MarketDataService
from services.scanner import Scanner
from strategies.breakout import BreakoutStrategy
from utils.logger import logger


async def main() -> None:

    logger.info("=" * 60)
    logger.info("MarketHunter")
    logger.info("=" * 60)

    service = MarketDataService()

    try:
        #
        # Binance connection
        #

        await service.ping()

        #
        # Symbols
        #

        symbols = await service.load_symbols()

        logger.info("Loaded symbols: {}", len(symbols))

        #
        # Scanner
        #

        scanner = Scanner(
            market_data=service,
            strategy=BreakoutStrategy(),
            workers=10,
        )

        #
        # First test
        # Поки що скануємо лише перші 20 монет.
        #

        test_symbols = symbols[:20]

        signals = await scanner.scan_many(
            test_symbols
        )

        logger.info("")
        logger.info("=" * 60)

        if not signals:

            logger.info("No breakout signals found.")

        else:

            logger.success(
                "Found {} signals",
                len(signals),
            )

            for signal in signals:

                logger.success(
                    "{} | {} | {} | Score={}",
                    signal.symbol,
                    signal.market,
                    signal.direction,
                    signal.score,
                )

                for reason in signal.reasons:
                    logger.info("  • {}", reason)

    finally:
        await service.close()


if __name__ == "__main__":
    asyncio.run(main())