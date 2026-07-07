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
    Scans markets using multiple strategies.
    """

    def __init__(
        self,
        market_data: MarketDataService,
        strategies: list[BaseStrategy],
        workers: int = 10,
    ) -> None:

        self.market_data = market_data
        self.strategies = strategies
        self.snapshot_builder = SnapshotBuilder()
        self.pool = WorkerPool(workers)

    async def scan_symbol(
        self,
        symbol: MarketSymbol,
    ) -> list[Signal]:
        """
        Scan one symbol using all strategies.
        """

        try:

            candles = await self.market_data.load_candles(symbol)

            if len(candles) < 200:
                return []

            snapshot = self.snapshot_builder.build(
                symbol.symbol,
                candles,
            )

            signals: list[Signal] = []

            for strategy in self.strategies:

                signal = await strategy.analyze(snapshot)

                if signal is None:
                    continue

                signal.market = symbol.market

                signals.append(signal)

            return signals

        except Exception as exc:

            logger.warning(
                "{} -> {}",
                symbol.symbol,
                exc,
            )

            return []

    async def scan_many(
        self,
        symbols: list[MarketSymbol],
    ) -> list[Signal]:
        """
        Scan multiple symbols concurrently.
        """

        logger.info(
            "Scanning {} symbols using {} strategies...",
            len(symbols),
            len(self.strategies),
        )

        tasks = [
            self.pool.run(
                self.scan_symbol,
                symbol,
            )
            for symbol in symbols
        ]

        results = await asyncio.gather(*tasks)

        signals: list[Signal] = []

        for symbol_signals in results:
            signals.extend(symbol_signals)

        signals.sort(
            key=lambda signal: signal.score,
            reverse=True,
        )

        logger.info(
            "Signals found: {}",
            len(signals),
        )

        return signals