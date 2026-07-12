"""
MarketHunter

Module:
Market Scanner

Responsibilities:
- Load candles for one configured timeframe.
- Build a market snapshot.
- Run all strategies for a symbol.
- MTF data contract v1: load supplemental entry-timeframe candles
  (at most once per timeframe per scan_symbol() call) for strategies
  that declare entry_timeframe/analyze_with_entry_candles().
- Resolve LONG/SHORT direction conflicts per symbol.
- Send candidate signals through SignalPipeline.
- Persist every candidate signal into scan journal when enabled.
"""

from __future__ import annotations

import asyncio

from dataclasses import dataclass
from dataclasses import field

from loguru import logger

from models.candle import Candle
from models.market_symbol import MarketSymbol
from models.signal import Signal
from pipeline.context import SignalContext
from pipeline.signal_pipeline import SignalPipeline
from research.storage.scan_journal_repository import (
    ScanJournalRepository,
)
from services.market_data import MarketDataService
from services.snapshot_builder import SnapshotBuilder
from services.worker_pool import WorkerPool
from strategies.base_strategy import BaseStrategy


@dataclass
class SignalDecision:
    """
    Scanner-level decision for a raw strategy signal.
    """

    signal: Signal
    rejected_reason: str | None = None
    metadata: dict[str, object] = field(
        default_factory=dict,
    )


class Scanner:
    """
    Scans markets using multiple strategies.

    Each signal receives the Scanner timeframe before it enters
    SignalPipeline. Research trades therefore use the same interval
    that produced the original signal.

    Direction conflict resolver:
    - If one symbol has only LONG or only SHORT candidates, keep normal flow.
    - If one symbol has both LONG and SHORT candidates, compare total scores.
    - If the score gap is too small, reject both directions as mixed conflict.
    - If one direction is clearly stronger, keep that direction and reject
      the weaker direction before it reaches the pipeline.
    """

    CONFLICT_MIN_SCORE_DELTA = 15.0

    def __init__(
        self,
        market_data: MarketDataService,
        strategies: list[BaseStrategy],
        workers: int = 10,
        pipeline: SignalPipeline | None = None,
        timeframe: str = "1h",
        candle_limit: int = 500,
        scan_journal: ScanJournalRepository | None = None,
        scan_run_id: str | None = None,
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

        if scan_journal is not None and scan_run_id is None:
            raise ValueError(
                "Scanner scan_run_id is required when scan_journal is set."
            )

        self.market_data = market_data
        self.strategies = strategies
        self.snapshot_builder = SnapshotBuilder()
        self.pool = WorkerPool(workers)
        self.pipeline = pipeline
        self.timeframe = normalized_timeframe
        self.candle_limit = candle_limit
        self.scan_journal = scan_journal
        self.scan_run_id = scan_run_id

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

        raw_signals = await self._collect_raw_signals(
            symbol=symbol,
            snapshot=snapshot,
        )

        decisions = self._resolve_direction_conflicts(
            raw_signals,
        )

        accepted_signals: list[Signal] = []

        for decision in decisions:
            try:
                context = await self._process_signal(
                    signal=decision.signal,
                    snapshot=snapshot,
                    metadata=decision.metadata,
                    rejected_reason=decision.rejected_reason,
                )

                self._record_signal_context(
                    context=context,
                )

                if not context.accepted:
                    logger.debug(
                        "{} {} {} rejected: {}",
                        context.signal.symbol,
                        context.signal.strategy,
                        context.signal.direction,
                        context.rejected_reason,
                    )
                    continue

                accepted_signals.append(
                    context.signal,
                )

            except Exception as exc:
                logger.warning(
                    "{} -> signal {} failed during processing: {}",
                    symbol.symbol,
                    decision.signal.strategy,
                    exc,
                )

        return accepted_signals

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

    async def _collect_raw_signals(
        self,
        symbol: MarketSymbol,
        snapshot: object,
    ) -> list[Signal]:
        """
        Run all strategies for one symbol before pipeline processing.

        Strategies exposing entry_timeframe and
        analyze_with_entry_candles() additionally receive
        entry-timeframe candles (MTF data contract v1). Every
        distinct entry_timeframe is fetched at most once per call via
        supplemental_candles_by_timeframe, scoped to this one
        scan_symbol() invocation.
        """

        raw_signals: list[Signal] = []
        supplemental_candles_by_timeframe: dict[
            str, list[Candle] | None
        ] = {}

        for strategy in self.strategies:
            try:
                signal = await self._run_strategy(
                    strategy=strategy,
                    symbol=symbol,
                    snapshot=snapshot,
                    supplemental_candles_by_timeframe=(
                        supplemental_candles_by_timeframe
                    ),
                )

                if signal is None:
                    continue

                signal.market = symbol.market
                signal.timeframe = self.timeframe

                raw_signals.append(
                    signal,
                )

            except Exception as exc:
                logger.warning(
                    "{} -> strategy {} failed: {}",
                    symbol.symbol,
                    strategy.__class__.__name__,
                    exc,
                )

        return raw_signals

    async def _run_strategy(
        self,
        strategy: BaseStrategy,
        symbol: MarketSymbol,
        snapshot: object,
        supplemental_candles_by_timeframe: dict[
            str, list[Candle] | None
        ],
    ) -> Signal | None:
        """
        Run one strategy, routing through the MTF data contract v1
        hook when the strategy declares entry_timeframe and
        analyze_with_entry_candles(). Any other strategy is called
        exactly as before: strategy.analyze(snapshot).

        A failed supplemental fetch falls back to strategy.analyze(
        snapshot) rather than raising - the primary 1d scan must never
        fail because a secondary-timeframe fetch failed, and no
        MTF metadata is fabricated for a signal produced this way.
        """

        entry_timeframe = getattr(strategy, "entry_timeframe", None)
        analyze_with_entry_candles = getattr(
            strategy,
            "analyze_with_entry_candles",
            None,
        )

        if not entry_timeframe or not callable(
            analyze_with_entry_candles,
        ):
            return await strategy.analyze(snapshot)

        entry_candles = await self._load_supplemental_candles(
            symbol=symbol,
            snapshot=snapshot,
            timeframe=entry_timeframe,
            limit=getattr(
                strategy,
                "entry_candle_limit",
                self.candle_limit,
            ),
            cache=supplemental_candles_by_timeframe,
        )

        if entry_candles is None:
            return await strategy.analyze(snapshot)

        return await analyze_with_entry_candles(
            snapshot,
            entry_candles,
        )

    async def _load_supplemental_candles(
        self,
        symbol: MarketSymbol,
        snapshot: object,
        timeframe: str,
        limit: int,
        cache: dict[str, list[Candle] | None],
    ) -> list[Candle] | None:
        """
        Load and cache one entry-timeframe candle list per
        scan_symbol() call.

        Reuses the primary snapshot's own candles (no extra fetch)
        when the requested timeframe matches Scanner.timeframe.
        Returns the same cached list for every strategy requesting
        the same timeframe within one call, so a shared
        entry_timeframe is fetched at most once. Returns None (never
        raises) when the additional fetch fails, so callers fall back
        to strategy.analyze(snapshot) without any fabricated MTF
        metadata.
        """

        if timeframe == self.timeframe:
            return getattr(snapshot, "candles", None)

        if timeframe in cache:
            return cache[timeframe]

        try:
            entry_candles = await self.market_data.load_candles(
                symbol=symbol,
                interval=timeframe,
                limit=limit,
            )

        except Exception as exc:
            logger.warning(
                "{} -> failed to load supplemental {} candles: {}",
                symbol.symbol,
                timeframe,
                exc,
            )

            cache[timeframe] = None

            return None

        cache[timeframe] = entry_candles

        return entry_candles

    def _resolve_direction_conflicts(
        self,
        signals: list[Signal],
    ) -> list[SignalDecision]:
        """
        Resolve LONG/SHORT conflicts before pipeline processing.
        """

        if not signals:
            return []

        long_signals = [
            signal
            for signal in signals
            if self._signal_direction(signal) == "LONG"
        ]

        short_signals = [
            signal
            for signal in signals
            if self._signal_direction(signal) == "SHORT"
        ]

        if not long_signals or not short_signals:
            return [
                SignalDecision(
                    signal=signal,
                )
                for signal in signals
            ]

        long_score = self._total_score(
            long_signals,
        )

        short_score = self._total_score(
            short_signals,
        )

        score_delta = abs(
            long_score - short_score,
        )

        symbol = signals[0].symbol

        base_metadata = {
            "direction_conflict": True,
            "conflict_symbol": symbol,
            "conflict_long_score": long_score,
            "conflict_short_score": short_score,
            "conflict_score_delta": score_delta,
            "conflict_min_score_delta": self.CONFLICT_MIN_SCORE_DELTA,
            "conflict_long_signal_count": len(long_signals),
            "conflict_short_signal_count": len(short_signals),
            "conflict_long_strategies": self._strategy_names(
                long_signals,
            ),
            "conflict_short_strategies": self._strategy_names(
                short_signals,
            ),
        }

        if score_delta < self.CONFLICT_MIN_SCORE_DELTA:
            reason = (
                "Direction conflict: mixed LONG/SHORT setup "
                f"for {symbol}. LONG score {long_score:.1f}, "
                f"SHORT score {short_score:.1f}, delta "
                f"{score_delta:.1f} below required "
                f"{self.CONFLICT_MIN_SCORE_DELTA:.1f}."
            )

            logger.info(
                "{} direction conflict rejected as mixed | "
                "LONG: {} | SHORT: {} | Delta: {}",
                symbol,
                long_score,
                short_score,
                score_delta,
            )

            return [
                self._build_conflict_decision(
                    signal=signal,
                    rejected_reason=reason,
                    metadata={
                        **base_metadata,
                        "conflict_resolution": "mixed_rejected",
                        "conflict_winner_direction": "",
                        "conflict_signal_outcome": "mixed_rejected",
                    },
                    reason_to_add=(
                        "Direction conflict: mixed LONG/SHORT setup"
                    ),
                )
                for signal in signals
            ]

        if long_score > short_score:
            winner_direction = "LONG"
            loser_direction = "SHORT"
            winner_score = long_score
            loser_score = short_score
        else:
            winner_direction = "SHORT"
            loser_direction = "LONG"
            winner_score = short_score
            loser_score = long_score

        logger.info(
            "{} direction conflict resolved | Winner: {} | "
            "LONG: {} | SHORT: {} | Delta: {}",
            symbol,
            winner_direction,
            long_score,
            short_score,
            score_delta,
        )

        decisions: list[SignalDecision] = []

        for signal in signals:
            direction = self._signal_direction(
                signal,
            )

            if direction == winner_direction:
                decisions.append(
                    self._build_conflict_decision(
                        signal=signal,
                        rejected_reason=None,
                        metadata={
                            **base_metadata,
                            "conflict_resolution": "winner_selected",
                            "conflict_winner_direction": winner_direction,
                            "conflict_signal_outcome": "winner",
                        },
                        reason_to_add=(
                            "Direction conflict resolved: "
                            f"{winner_direction} stronger than "
                            f"{loser_direction}"
                        ),
                    )
                )
                continue

            if direction == loser_direction:
                reason = (
                    "Direction conflict: weaker direction rejected "
                    f"for {symbol}. {winner_direction} score "
                    f"{winner_score:.1f}, {loser_direction} score "
                    f"{loser_score:.1f}."
                )

                decisions.append(
                    self._build_conflict_decision(
                        signal=signal,
                        rejected_reason=reason,
                        metadata={
                            **base_metadata,
                            "conflict_resolution": "loser_rejected",
                            "conflict_winner_direction": winner_direction,
                            "conflict_signal_outcome": "loser_rejected",
                        },
                        reason_to_add=(
                            "Direction conflict: weaker direction rejected"
                        ),
                    )
                )
                continue

            decisions.append(
                SignalDecision(
                    signal=signal,
                    metadata={
                        **base_metadata,
                        "conflict_resolution": "ignored_unknown_direction",
                        "conflict_winner_direction": winner_direction,
                        "conflict_signal_outcome": "ignored_unknown_direction",
                    },
                )
            )

        return decisions

    async def _process_signal(
        self,
        signal: Signal,
        snapshot: object,
        metadata: dict[str, object] | None = None,
        rejected_reason: str | None = None,
    ) -> SignalContext:
        """
        Send a candidate signal through the optional pipeline.

        Scanner-level rejected signals are recorded in the scan journal
        but do not enter the pipeline, so they cannot create research trades.
        """

        context = SignalContext(
            signal=signal,
            snapshot=snapshot,
        )

        if metadata:
            context.metadata.update(
                metadata,
            )
            self._attach_signal_metadata(
                signal=signal,
                metadata=metadata,
            )

        if rejected_reason is not None:
            context.reject(
                rejected_reason,
            )
            return context

        if self.pipeline is None:
            return context

        return await self.pipeline.process(context)

    def _record_signal_context(
        self,
        context: SignalContext,
    ) -> None:
        """
        Persist one processed signal context into scan journal.
        """

        if self.scan_journal is None:
            return

        if self.scan_run_id is None:
            return

        try:
            self.scan_journal.save_signal_record_from_context(
                scan_run_id=self.scan_run_id,
                context=context,
            )

        except Exception as exc:
            logger.warning(
                "{} {} failed to write signal journal record: {}",
                context.signal.symbol,
                context.signal.strategy,
                exc,
            )

    def _build_conflict_decision(
        self,
        signal: Signal,
        rejected_reason: str | None,
        metadata: dict[str, object],
        reason_to_add: str,
    ) -> SignalDecision:
        """
        Build one conflict-aware scanner decision.
        """

        self._add_signal_reason(
            signal=signal,
            reason=reason_to_add,
        )

        return SignalDecision(
            signal=signal,
            rejected_reason=rejected_reason,
            metadata=metadata,
        )

    @staticmethod
    def _signal_direction(
        signal: Signal,
    ) -> str:
        """
        Return normalized signal direction.
        """

        return str(
            getattr(
                signal,
                "direction",
                "",
            )
        ).strip().upper()

    @staticmethod
    def _strategy_names(
        signals: list[Signal],
    ) -> list[str]:
        """
        Return sorted unique strategy names for conflict analytics.
        """

        names = {
            str(
                getattr(
                    signal,
                    "strategy",
                    "Unknown",
                )
                or "Unknown"
            )
            for signal in signals
        }

        return sorted(names)


    @staticmethod
    def _total_score(
        signals: list[Signal],
    ) -> float:
        """
        Return directional conflict score.

        Use the strongest setup as the base and add only a small
        capped confluence bonus for extra same-direction signals.

        This prevents several weak signals from overpowering one
        stronger opposite-direction setup.
        """

        scores = [
            Scanner._signal_score(signal)
            for signal in signals
        ]

        if not scores:
            return 0.0

        strongest_score = max(scores)

        confluence_bonus = min(
            max(len(scores) - 1, 0) * 5.0,
            15.0,
        )

        return strongest_score + confluence_bonus

    @staticmethod
    def _signal_score(
        signal: Signal,
    ) -> float:
        """
        Return numeric signal score.
        """

        try:
            return float(
                getattr(
                    signal,
                    "score",
                    0.0,
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            return 0.0

    @staticmethod
    def _attach_signal_metadata(
        signal: Signal,
        metadata: dict[str, object],
    ) -> None:
        """
        Attach scanner metadata to the signal if supported.
        """

        signal_metadata = getattr(
            signal,
            "metadata",
            None,
        )

        if not isinstance(signal_metadata, dict):
            return

        signal_metadata.update(
            metadata,
        )

    @staticmethod
    def _add_signal_reason(
        signal: Signal,
        reason: str,
    ) -> None:
        """
        Add a reason to a signal if supported.
        """

        add_reason = getattr(
            signal,
            "add_reason",
            None,
        )

        if add_reason is None:
            return

        add_reason(
            reason,
        )