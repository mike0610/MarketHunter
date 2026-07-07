"""
MarketHunter

Module:
Market Scanner

Responsibilities:
- Load candles for one configured timeframe.
- Build a market snapshot.
- Run all strategies for a symbol.
- Send candidate signals through SignalPipeline.
"""

from __future__ import annotations

import asyncio

from loguru import logger

from models.market_symbol import MarketSymbol
from models.signal import Signal
from pipeline.context import SignalContext
from pipeline.signal_pipeline import SignalPipeline
from services.market_data import MarketDataService
from services.snapshot_builder import SnapshotBuilder
from services.worker_pool import WorkerPool
from strategies.base_strategy import BaseStrategy


class Scanner:
    """
    Scans markets using multiple strategies.

    Each signal receives the Scanner timeframe before it enters
    SignalPipeline. Research trades therefore use the same interval
    that produced the original signal.
    """

    def __init__(
        self,
        market_data: MarketDataService,
        strategies: list[BaseStrategy],
        workers: int = 10,
        pipeline: SignalPipeline | None = None,
        timeframe: str = "1h",
        candle_limit: int = 500,
    ) -> None:
        """
        Initialize scanner dependencies.
        """

        normalized_timeframe = timeframe.strip()

        if not normalized_timeframe:
            raise ValueError(
                "Scanner timeframe cannot be empty."
            )

        if candle_limit < 200:
            raise ValueError(
                "Scanner candle limit must be at least 200."
            )

        self.market_data = market_data
        self.strategies = strategies
        self.snapshot_builder = SnapshotBuilder()
        self.pool = WorkerPool(workers)
        self.pipeline = pipeline
        self.timeframe = normalized_timeframe
        self.candle_limit = candle_limit

    async def scan_symbol(
        self,
        symbol: MarketSymbol,
    ) -> list[Signal]:
        """
        Scan one market symbol using every configured strategy.
        """

        try:
            candles = await self.market_data.load_candles(
                symbol=symbol,
                interval=self.timeframe,
                limit=self.candle_limit,
            )

            if len(candles) < 200:
                logger.debug(
                    "{} skipped: only {} candles loaded.",
                    symbol.symbol,
                    len(candles),
                )
                return []

            snapshot = self.snapshot_builder.build(
                symbol.symbol,
                candles,
            )

        except Exception as exc:
            logger.warning(
                "{} -> failed to prepare market snapshot: {}",
                symbol.symbol,
                exc,
            )
            return []

        signals: list[Signal] = []

        for strategy in self.strategies:
            try:
                signal = await strategy.analyze(snapshot)

                if signal is None:
                    continue

                signal.market = symbol.market
                signal.timeframe = self.timeframe

                processed_signal = await self._process_signal(
                    signal=signal,
                    snapshot=snapshot,
                )

                if processed_signal is None:
                    continue

                signals.append(processed_signal)

            except Exception as exc:
                logger.warning(
                    "{} -> strategy {} failed: {}",
                    symbol.symbol,
                    strategy.__class__.__name__,
                    exc,
                )

        return signals

    async def scan_many(
        self,
        symbols: list[MarketSymbol],
    ) -> list[Signal]:
        """
        Scan multiple symbols concurrently.
        """

        logger.info(
            "Scanning {} {} symbols using {} strategies...",
            len(symbols),
            self.timeframe,
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
            "Accepted signals found: {}",
            len(signals),
        )

        return signals

    async def _process_signal(
        self,
        signal: Signal,
        snapshot: object,
    ) -> Signal | None:
        """
        Send a candidate signal through the optional pipeline.
        """

        if self.pipeline is None:
            return signal

        context = SignalContext(
            signal=signal,
            snapshot=snapshot,
        )

        context = await self.pipeline.process(context)

        if not context.accepted:
            logger.debug(
                "{} {} rejected by pipeline: {}",
                signal.symbol,
                signal.strategy,
                context.rejected_reason,
            )
            return None

        return context.signal