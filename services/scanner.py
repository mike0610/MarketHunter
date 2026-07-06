"""
MarketHunter

services/scanner.py
"""

from __future__ import annotations

import asyncio

from loguru import logger

from models.market_symbol import MarketSymbol
from models.signal import Signal
from services.market_data import MarketDataService
from services.snapshot_builder import SnapshotBuilder
from services.worker_pool import WorkerPool
from strategies.base_strategy import BaseStrategy


class Scanner:
    """
    Scans markets using the selected strategy.
    """

    def __init__(
        self,
        market_data: MarketDataService,
        strategy: BaseStrategy,
        workers: int = 10,
    ) -> None:

        self.market_data = market_data
        self.strategy = strategy
        self.snapshot_builder = SnapshotBuilder()
        self.pool = WorkerPool(workers)

    async def scan_symbol(
        self,
        symbol: MarketSymbol,
    ) -> Signal | None:
        """
        Scan one symbol.
        """

        try:

            candles = await self.market_data.load_candles(symbol)

            if len(candles) < 200:
                return None

            snapshot = self.snapshot_builder.build(
                symbol.symbol,
                candles,
            )

            signal = await self.strategy.analyze(snapshot)

            if signal is not None:
                signal.market = symbol.market

            return signal

        except Exception as exc:

            logger.warning(
                "{} -> {}",
                symbol.symbol,
                exc,
            )

            return None

    async def scan_many(
        self,
        symbols: list[MarketSymbol],
    ) -> list[Signal]:
        """
        Scan multiple symbols concurrently.
        """

        logger.info(
            "Scanning {} symbols...",
            len(symbols),
        )

        tasks = [
            self.pool.run(
                self.scan_symbol,
                symbol,
            )
            for symbol in symbols
        ]

        results = await asyncio.gather(*tasks)

        signals = [
            signal
            for signal in results
            if signal is not None
        ]

        signals.sort(
            key=lambda signal: signal.score,
            reverse=True,
        )

        logger.info(
            "Signals found: {}",
            len(signals),
        )

        return signals