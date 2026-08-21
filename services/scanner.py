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
from strategies.execution_binding import (
    StrategyExecutionBinding,
    StrategyExecutionBindingConflictError,
)


@dataclass(frozen=True, slots=True)
class _ExecutionItem:
    """
    One strategy implementation resolved for this scan, paired with
    its governed StrategyExecutionBinding when bound. binding is
    None for a legacy bare strategy - explicitly NON-PROVENANCE-
    ELIGIBLE.
    """

    implementation: BaseStrategy
    strategy_execution_binding: StrategyExecutionBinding | None


@dataclass(frozen=True, slots=True)
class _ScannedSignal:
    """
    One raw strategy signal paired with the exact governed binding
    (or None) of the strategy that produced it - carried through
    direction-conflict resolution so provenance is never lost.
    """

    signal: Signal
    strategy_execution_binding: StrategyExecutionBinding | None


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
    strategy_execution_binding: StrategyExecutionBinding | None = None


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
        strategy_bindings: list[StrategyExecutionBinding] | None = None,
    ) -> None:
        """
        Initialize scanner dependencies.

        strategy_bindings carries governed StrategyExecutionBinding
        instances, executed alongside (never inferred for) the
        legacy bare strategies list. Bindings are never constructed
        here - the caller supplies exact, already-resolved bindings.
        The same concrete implementation object bound to two
        different releases is a hard configuration error; the same
        implementation bound to the identical release twice is
        deterministically deduplicated to one execution.
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
        self.strategy_bindings = strategy_bindings or []
        self._execution_items = self._build_execution_items(
            strategies=strategies,
            strategy_bindings=self.strategy_bindings,
        )
        self.snapshot_builder = SnapshotBuilder()
        self.pool = WorkerPool(workers)
        self.pipeline = pipeline
        self.timeframe = normalized_timeframe
        self.candle_limit = candle_limit
        self.scan_journal = scan_journal
        self.scan_run_id = scan_run_id

    @staticmethod
    def _build_execution_items(
        strategies: list[BaseStrategy],
        strategy_bindings: list[StrategyExecutionBinding],
    ) -> list[_ExecutionItem]:
        """
        Resolve the exact ordered list of strategies this scan will
        execute: governed bindings first (in the order supplied),
        then legacy bare strategies (in the order supplied,
        binding=None, explicitly NON-PROVENANCE-ELIGIBLE).

        The same concrete implementation object (id(implementation))
        bound to two different releases is a hard
        StrategyExecutionBindingConflictError. The same implementation
        object bound to the identical release twice is deterministically
        deduplicated to exactly one execution item, so it cannot
        double-run. This dedupe/conflict check applies only within
        strategy_bindings - an implementation object supplied both in
        strategy_bindings and bare in strategies is not deduplicated
        across the two lists, since the legacy list carries no
        binding to compare against.

        The same concrete implementation object supplied simultaneously
        through strategy_bindings and legacy strategies is a hard
        StrategyExecutionBindingConflictError, raised before any
        execution item is produced - one concrete object must never
        run twice under mixed governed/unbound semantics.
        """

        seen_by_implementation_id: dict[int, StrategyExecutionBinding] = {}
        items: list[_ExecutionItem] = []

        for binding in strategy_bindings:
            if not isinstance(binding, StrategyExecutionBinding):
                raise TypeError(
                    "strategy_bindings must contain only "
                    "StrategyExecutionBinding instances"
                )

            implementation_key = id(binding.implementation)
            existing = seen_by_implementation_id.get(implementation_key)

            if existing is not None:
                if existing != binding:
                    raise StrategyExecutionBindingConflictError(
                        "the same strategy implementation object is bound "
                        f"to conflicting releases: {existing.release.release_key!r} "
                        f"vs {binding.release.release_key!r}"
                    )

                continue

            seen_by_implementation_id[implementation_key] = binding
            items.append(
                _ExecutionItem(
                    implementation=binding.implementation,
                    strategy_execution_binding=binding,
                )
            )

        for implementation in strategies:
            implementation_key = id(implementation)
            governed_binding = seen_by_implementation_id.get(
                implementation_key
            )

            if governed_binding is not None:
                raise StrategyExecutionBindingConflictError(
                    "the same strategy implementation object is bound "
                    f"({governed_binding.release.release_key!r}) and also "
                    "supplied as a legacy unbound strategy - one concrete "
                    "implementation cannot run under mixed governed/"
                    "unbound semantics"
                )

            items.append(
                _ExecutionItem(
                    implementation=implementation,
                    strategy_execution_binding=None,
                )
            )

        return items

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
                    strategy_execution_binding=(
                        decision.strategy_execution_binding
                    ),
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
            len(self._execution_items),
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
    ) -> list[_ScannedSignal]:
        """
        Run all resolved execution items (governed bindings, then
        legacy bare strategies) for one symbol before pipeline
        processing.

        Strategies exposing entry_timeframe and
        analyze_with_entry_candles() additionally receive
        entry-timeframe candles (MTF data contract v1). Every
        distinct entry_timeframe is fetched at most once per call via
        supplemental_candles_by_timeframe, scoped to this one
        scan_symbol() invocation.
        """

        raw_signals: list[_ScannedSignal] = []
        supplemental_candles_by_timeframe: dict[
            str, list[Candle] | None
        ] = {}

        for item in self._execution_items:
            try:
                signal = await self._run_strategy(
                    strategy=item.implementation,
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
                    _ScannedSignal(
                        signal=signal,
                        strategy_execution_binding=(
                            item.strategy_execution_binding
                        ),
                    ),
                )

            except Exception as exc:
                logger.warning(
                    "{} -> strategy {} failed: {}",
                    symbol.symbol,
                    item.implementation.__class__.__name__,
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
        scanned_signals: list[_ScannedSignal],
    ) -> list[SignalDecision]:
        """
        Resolve LONG/SHORT conflicts before pipeline processing.
        """

        if not scanned_signals:
            return []

        long_items = [
            item
            for item in scanned_signals
            if self._signal_direction(item.signal) == "LONG"
        ]

        short_items = [
            item
            for item in scanned_signals
            if self._signal_direction(item.signal) == "SHORT"
        ]

        if not long_items or not short_items:
            return [
                SignalDecision(
                    signal=item.signal,
                    strategy_execution_binding=item.strategy_execution_binding,
                )
                for item in scanned_signals
            ]

        long_score = self._total_score(
            [item.signal for item in long_items],
        )

        short_score = self._total_score(
            [item.signal for item in short_items],
        )

        score_delta = abs(
            long_score - short_score,
        )

        symbol = scanned_signals[0].signal.symbol

        base_metadata = {
            "direction_conflict": True,
            "conflict_symbol": symbol,
            "conflict_long_score": long_score,
            "conflict_short_score": short_score,
            "conflict_score_delta": score_delta,
            "conflict_min_score_delta": self.CONFLICT_MIN_SCORE_DELTA,
            "conflict_long_signal_count": len(long_items),
            "conflict_short_signal_count": len(short_items),
            "conflict_long_strategies": self._strategy_names(
                [item.signal for item in long_items],
            ),
            "conflict_short_strategies": self._strategy_names(
                [item.signal for item in short_items],
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
                    item=item,
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
                for item in scanned_signals
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

        for item in scanned_signals:
            direction = self._signal_direction(
                item.signal,
            )

            if direction == winner_direction:
                decisions.append(
                    self._build_conflict_decision(
                        item=item,
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
                        item=item,
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
                    signal=item.signal,
                    metadata={
                        **base_metadata,
                        "conflict_resolution": "ignored_unknown_direction",
                        "conflict_winner_direction": winner_direction,
                        "conflict_signal_outcome": "ignored_unknown_direction",
                    },
                    strategy_execution_binding=item.strategy_execution_binding,
                )
            )

        return decisions

    async def _process_signal(
        self,
        signal: Signal,
        snapshot: object,
        metadata: dict[str, object] | None = None,
        rejected_reason: str | None = None,
        strategy_execution_binding: StrategyExecutionBinding | None = None,
    ) -> SignalContext:
        """
        Send a candidate signal through the optional pipeline.

        Scanner-level rejected signals are recorded in the scan journal
        but do not enter the pipeline, so they cannot create research trades.
        """

        context = SignalContext(
            signal=signal,
            snapshot=snapshot,
            strategy_execution_binding=strategy_execution_binding,
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
        item: _ScannedSignal,
        rejected_reason: str | None,
        metadata: dict[str, object],
        reason_to_add: str,
    ) -> SignalDecision:
        """
        Build one conflict-aware scanner decision.
        """

        self._add_signal_reason(
            signal=item.signal,
            reason=reason_to_add,
        )

        return SignalDecision(
            signal=item.signal,
            rejected_reason=rejected_reason,
            metadata=metadata,
            strategy_execution_binding=item.strategy_execution_binding,
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