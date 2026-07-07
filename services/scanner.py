"""
MarketHunter

Module:
Market Scanner

Responsibilities:
- Load market candles.
- Build a market snapshot.
- Run all strategies for a symbol.
- Optionally send every detected signal through SignalPipeline.
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

    Scanner is responsible only for finding candidate signals.

    When a SignalPipeline is provided, every candidate signal is passed
    through additional stages such as probability validation, risk
    calculation, research-trade creation, notifications, and more.
    """

    def __init__(
        self,
        market_data: MarketDataService,
        strategies: list[BaseStrategy],
        workers: int = 10,
        pipeline: SignalPipeline | None = None,
    ) -> None:
        """
        Initialize scanner dependencies.
        """

        self.market_data = market_data
        self.strategies = strategies
        self.snapshot_builder = SnapshotBuilder()
        self.pool = WorkerPool(workers)
        self.pipeline = pipeline

    async def scan_symbol(
        self,
        symbol: MarketSymbol,
    ) -> list[Signal]:
        """
        Scan one market symbol using every configured strategy.

        Returns only accepted signals. A signal rejected by the optional
        pipeline is not returned in the final result.
        """

        try:
            candles = await self.market_data.load_candles(symbol)

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

        When no pipeline is configured, the original signal is returned
        unchanged. This keeps Scanner usable for simple scans and tests.
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