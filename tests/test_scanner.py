"""
MarketHunter

Tests for Scanner.scan_symbol() - a read-only regression baseline.

This is a characterization suite: it locks in the CURRENT behavior of
Scanner.scan_symbol() using local fake/stub collaborators (no Binance,
DB, API, or network involved), before any multi-timeframe (1D level ->
1h entry) work touches the scanner. services/scanner.py is not
modified by this file.

Two tests are explicitly marked as MTF boundary markers - they pin
down exactly what is expected to intentionally change or expand once
multi-timeframe work begins:
- test_1d_scanner_does_not_load_1h_candles
- test_strategy_analyze_called_with_exactly_one_argument
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from models.candle import Candle
from models.market_snapshot import MarketSnapshot
from models.market_symbol import MarketSymbol
from models.signal import Signal
from services.scanner import Scanner
from strategies.base_strategy import BaseStrategy


def make_candle(day_index: int) -> Candle:
    """
    Build a minimal, deterministic placeholder daily candle.

    Scanner.scan_symbol() only ever checks len(candles) and forwards
    the list as-is to snapshot_builder.build() - the fakes below never
    inspect individual candle fields, so these values are inert.
    """

    open_time = (
        datetime(2024, 1, 1, tzinfo=timezone.utc)
        + timedelta(days=day_index)
    )

    return Candle(
        open_time=open_time,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=1000.0,
        close_time=(
            open_time
            + timedelta(days=1)
            - timedelta(seconds=1)
        ),
        quote_volume=100000.0,
        trades=100,
        taker_buy_base_volume=500.0,
        taker_buy_quote_volume=50000.0,
    )


def make_candles(count: int = 200) -> list[Candle]:
    """
    Build `count` placeholder candles - enough to clear Scanner's own
    len(candles) < 200 guard.
    """

    return [
        make_candle(day_index=i)
        for i in range(count)
    ]


def make_symbol(
    symbol: str = "BTCUSDT",
    market: str = "spot",
) -> MarketSymbol:
    return MarketSymbol(
        symbol=symbol,
        base_asset=symbol.removesuffix("USDT"),
        quote_asset="USDT",
        market=market,
    )


def make_snapshot(
    symbol: str = "BTCUSDT",
    candles: list[Candle] | None = None,
) -> MarketSnapshot:
    return MarketSnapshot(
        symbol=symbol,
        candles=candles or [],
        ema20=0.0,
        ema50=0.0,
        ema200=0.0,
        atr14=0.0,
        avg_volume20=0.0,
        highest20=0.0,
        lowest20=0.0,
    )


class FakeMarketData:
    """
    Records every load_candles() call and always returns the same
    canned candle list, regardless of the requested interval.
    """

    def __init__(self, candles: list[Candle]) -> None:
        self.candles = candles
        self.calls: list[dict] = []

    async def load_candles(
        self,
        symbol: MarketSymbol,
        interval: str,
        limit: int,
    ) -> list[Candle]:
        self.calls.append(
            {
                "symbol": symbol,
                "interval": interval,
                "limit": limit,
            }
        )

        return self.candles


class FakeSnapshotBuilder:
    """
    Records every build() call and always returns the same canned
    MarketSnapshot, regardless of the candles passed in.
    """

    def __init__(self, snapshot: MarketSnapshot) -> None:
        self.snapshot = snapshot
        self.calls: list[dict] = []

    def build(
        self,
        symbol: str,
        candles: list[Candle],
    ) -> MarketSnapshot:
        self.calls.append(
            {
                "symbol": symbol,
                "candles": candles,
            }
        )

        return self.snapshot


class FakeStrategy(BaseStrategy):
    """
    Returns a canned signal (or None) and records every analyze()
    call, including its raw call shape (*args/**kwargs) so tests can
    assert exactly how Scanner invokes the BaseStrategy contract -
    this is deliberately looser than the real `snapshot:
    MarketSnapshot` signature so a call with an unexpected extra
    argument is recorded and inspected rather than raising a
    TypeError that Scanner's own except Exception would silently
    swallow.
    """

    def __init__(
        self,
        name: str,
        signal_or_none: Signal | None,
    ) -> None:
        self.name = name
        self._signal_or_none = signal_or_none
        self.calls: list[dict] = []

    async def analyze(
        self,
        *args,
        **kwargs,
    ) -> Signal | None:
        self.calls.append(
            {
                "args": args,
                "kwargs": kwargs,
            }
        )

        return self._signal_or_none


class FakePipeline:
    """
    Records every process() call and returns the context unchanged
    (SignalContext.accepted defaults to True), mirroring an
    always-accept pipeline so tests can isolate Scanner's own
    behavior from SignalPipeline's handler logic.
    """

    def __init__(self) -> None:
        self.calls: list = []

    async def process(
        self,
        context,
    ):
        self.calls.append(context)

        return context


def build_scanner(
    market_data: FakeMarketData,
    strategies: list[BaseStrategy],
    snapshot_builder: FakeSnapshotBuilder,
    pipeline: FakePipeline | None = None,
    timeframe: str = "1d",
) -> Scanner:
    """
    Build a Scanner wired to fakes.

    Scanner does not accept a snapshot_builder constructor argument -
    it always builds its own `SnapshotBuilder()` internally - so the
    fake is injected by reassigning the public `scanner.snapshot_builder`
    attribute after construction. This does not touch
    services/scanner.py.
    """

    scanner = Scanner(
        market_data=market_data,
        strategies=strategies,
        pipeline=pipeline,
        timeframe=timeframe,
        candle_limit=200,
    )

    scanner.snapshot_builder = snapshot_builder

    return scanner


class ScannerScanSymbolBaselineTests(unittest.IsolatedAsyncioTestCase):
    """
    Lock in the current, pre-MTF behavior of Scanner.scan_symbol().

    This is a regression baseline: any future multi-timeframe work
    must not silently change any of these outcomes unless that change
    is explicitly intended.
    """

    async def test_scan_symbol_loads_candles_once_for_configured_timeframe(
        self,
    ) -> None:
        """
        One symbol -> exactly one load_candles() call, using the
        Scanner's own configured timeframe.
        """

        candles = make_candles()
        market_data = FakeMarketData(candles)
        symbol = make_symbol()

        scanner = build_scanner(
            market_data=market_data,
            strategies=[
                FakeStrategy("Fake", None),
            ],
            snapshot_builder=FakeSnapshotBuilder(
                make_snapshot(candles=candles),
            ),
            timeframe="1d",
        )

        await scanner.scan_symbol(symbol)

        self.assertEqual(len(market_data.calls), 1)
        self.assertEqual(
            market_data.calls[0]["interval"], "1d",
        )
        self.assertIs(
            market_data.calls[0]["symbol"], symbol,
        )
        self.assertEqual(
            market_data.calls[0]["limit"], scanner.candle_limit,
        )

    async def test_snapshot_builder_receives_loaded_candles(
        self,
    ) -> None:
        """
        snapshot_builder.build() is called with exactly the candles
        load_candles() returned.
        """

        candles = make_candles()
        market_data = FakeMarketData(candles)
        snapshot_builder = FakeSnapshotBuilder(
            make_snapshot(candles=candles),
        )
        symbol = make_symbol()

        scanner = build_scanner(
            market_data=market_data,
            strategies=[
                FakeStrategy("Fake", None),
            ],
            snapshot_builder=snapshot_builder,
        )

        await scanner.scan_symbol(symbol)

        self.assertEqual(len(snapshot_builder.calls), 1)
        self.assertIs(
            snapshot_builder.calls[0]["candles"], candles,
        )
        self.assertEqual(
            snapshot_builder.calls[0]["symbol"], symbol.symbol,
        )

    async def test_all_strategies_receive_same_snapshot_object(
        self,
    ) -> None:
        """
        With two configured strategies, both receive the SAME
        MarketSnapshot instance, and candles are only ever loaded
        once (not once per strategy).
        """

        candles = make_candles()
        market_data = FakeMarketData(candles)
        snapshot = make_snapshot(candles=candles)

        strategy_a = FakeStrategy("A", None)
        strategy_b = FakeStrategy("B", None)

        scanner = build_scanner(
            market_data=market_data,
            strategies=[strategy_a, strategy_b],
            snapshot_builder=FakeSnapshotBuilder(snapshot),
        )

        await scanner.scan_symbol(make_symbol())

        self.assertEqual(len(market_data.calls), 1)

        self.assertEqual(len(strategy_a.calls), 1)
        self.assertEqual(len(strategy_b.calls), 1)

        self.assertIs(
            strategy_a.calls[0]["args"][0], snapshot,
        )
        self.assertIs(
            strategy_b.calls[0]["args"][0], snapshot,
        )
        self.assertIs(
            strategy_a.calls[0]["args"][0],
            strategy_b.calls[0]["args"][0],
        )

    async def test_scanner_fills_transport_fields_on_signal(
        self,
    ) -> None:
        """
        A strategy returns a signal with market="" - Scanner fills
        signal.market from the scanned symbol and signal.timeframe
        from its own configured timeframe.
        """

        candles = make_candles()
        symbol = make_symbol(
            symbol="ETHUSDT",
            market="futures",
        )

        raw_signal = Signal(
            symbol="ETHUSDT",
            market="",
            timeframe="",
            strategy="Fake",
            direction="LONG",
            score=80.0,
        )

        scanner = build_scanner(
            market_data=FakeMarketData(candles),
            strategies=[
                FakeStrategy("Fake", raw_signal),
            ],
            snapshot_builder=FakeSnapshotBuilder(
                make_snapshot(candles=candles),
            ),
            pipeline=FakePipeline(),
            timeframe="1d",
        )

        signals = await scanner.scan_symbol(symbol)

        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].market, "futures")
        self.assertEqual(signals[0].timeframe, "1d")

    async def test_strategy_returning_none_skips_pipeline(
        self,
    ) -> None:
        """
        A strategy that returns None contributes no signal and the
        pipeline is never invoked for it.
        """

        candles = make_candles()
        pipeline = FakePipeline()

        scanner = build_scanner(
            market_data=FakeMarketData(candles),
            strategies=[
                FakeStrategy("Fake", None),
            ],
            snapshot_builder=FakeSnapshotBuilder(
                make_snapshot(candles=candles),
            ),
            pipeline=pipeline,
        )

        signals = await scanner.scan_symbol(make_symbol())

        self.assertEqual(signals, [])
        self.assertEqual(pipeline.calls, [])

    async def test_signal_context_passed_to_pipeline_matches_contract(
        self,
    ) -> None:
        """
        The SignalContext handed to pipeline.process() already has
        market/timeframe filled in, and carries the same snapshot
        object every strategy received. The pipeline is called
        exactly once for one qualifying signal.
        """

        candles = make_candles()
        snapshot = make_snapshot(candles=candles)
        symbol = make_symbol()
        pipeline = FakePipeline()

        raw_signal = Signal(
            symbol="BTCUSDT",
            market="",
            timeframe="",
            strategy="Fake",
            direction="LONG",
            score=80.0,
        )

        scanner = build_scanner(
            market_data=FakeMarketData(candles),
            strategies=[
                FakeStrategy("Fake", raw_signal),
            ],
            snapshot_builder=FakeSnapshotBuilder(snapshot),
            pipeline=pipeline,
            timeframe="1d",
        )

        await scanner.scan_symbol(symbol)

        self.assertEqual(len(pipeline.calls), 1)

        context = pipeline.calls[0]

        self.assertEqual(context.signal.market, symbol.market)
        self.assertEqual(context.signal.timeframe, "1d")
        self.assertIs(context.snapshot, snapshot)

    async def test_multiple_same_direction_signals_all_reach_pipeline(
        self,
    ) -> None:
        """
        Two strategies producing signals in the SAME direction are
        both currently passed through to the pipeline individually -
        this pins down the actual existing behavior (no dedup/merge
        at this stage) without attempting to improve it.
        """

        candles = make_candles()
        pipeline = FakePipeline()

        signal_a = Signal(
            symbol="BTCUSDT",
            market="",
            timeframe="",
            strategy="A",
            direction="LONG",
            score=70.0,
        )

        signal_b = Signal(
            symbol="BTCUSDT",
            market="",
            timeframe="",
            strategy="B",
            direction="LONG",
            score=72.0,
        )

        scanner = build_scanner(
            market_data=FakeMarketData(candles),
            strategies=[
                FakeStrategy("A", signal_a),
                FakeStrategy("B", signal_b),
            ],
            snapshot_builder=FakeSnapshotBuilder(
                make_snapshot(candles=candles),
            ),
            pipeline=pipeline,
        )

        signals = await scanner.scan_symbol(make_symbol())

        self.assertEqual(len(signals), 2)
        self.assertEqual(len(pipeline.calls), 2)

    async def test_direction_conflict_resolver_rejects_weaker_side(
        self,
    ) -> None:
        """
        Two strategies producing opposite directions with a score
        delta at/above CONFLICT_MIN_SCORE_DELTA (15.0) resolve to only
        the stronger direction reaching the pipeline - this pins down
        the real current conflict resolver outcome, not a desired one.
        """

        candles = make_candles()
        pipeline = FakePipeline()

        long_signal = Signal(
            symbol="BTCUSDT",
            market="",
            timeframe="",
            strategy="LongFake",
            direction="LONG",
            score=80.0,
        )

        short_signal = Signal(
            symbol="BTCUSDT",
            market="",
            timeframe="",
            strategy="ShortFake",
            direction="SHORT",
            score=50.0,
        )

        scanner = build_scanner(
            market_data=FakeMarketData(candles),
            strategies=[
                FakeStrategy("LongFake", long_signal),
                FakeStrategy("ShortFake", short_signal),
            ],
            snapshot_builder=FakeSnapshotBuilder(
                make_snapshot(candles=candles),
            ),
            pipeline=pipeline,
        )

        signals = await scanner.scan_symbol(make_symbol())

        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].direction, "LONG")

        self.assertEqual(len(pipeline.calls), 1)
        self.assertEqual(
            pipeline.calls[0].signal.direction, "LONG",
        )

    async def test_1d_scanner_does_not_load_1h_candles(
        self,
    ) -> None:
        """
        MTF boundary marker: today, a Scanner configured for "1d"
        never issues a "1h" load_candles() call - there is no
        secondary-timeframe fetch anywhere in scan_symbol(). This test
        is EXPECTED to intentionally change or expand once
        multi-timeframe (1D level -> 1h entry) work begins; until
        then it documents the exact boundary being refactored.
        """

        candles = make_candles()
        market_data = FakeMarketData(candles)

        scanner = build_scanner(
            market_data=market_data,
            strategies=[
                FakeStrategy("Fake", None),
            ],
            snapshot_builder=FakeSnapshotBuilder(
                make_snapshot(candles=candles),
            ),
            timeframe="1d",
        )

        await scanner.scan_symbol(make_symbol())

        intervals_requested = {
            call["interval"] for call in market_data.calls
        }

        self.assertEqual(intervals_requested, {"1d"})
        self.assertNotIn("1h", intervals_requested)

    async def test_strategy_analyze_called_with_exactly_one_argument(
        self,
    ) -> None:
        """
        MTF boundary marker: today, Scanner calls
        strategy.analyze(snapshot) with exactly one positional
        argument (the MarketSnapshot) and no keyword arguments. This
        test is EXPECTED to intentionally change once multi-timeframe
        work introduces a second data source (e.g. lower-timeframe
        entry candles) into the strategy call; until then it documents
        the exact call shape being refactored.
        """

        candles = make_candles()
        snapshot = make_snapshot(candles=candles)
        strategy = FakeStrategy("Fake", None)

        scanner = build_scanner(
            market_data=FakeMarketData(candles),
            strategies=[strategy],
            snapshot_builder=FakeSnapshotBuilder(snapshot),
        )

        await scanner.scan_symbol(make_symbol())

        self.assertEqual(len(strategy.calls), 1)

        call = strategy.calls[0]

        self.assertEqual(len(call["args"]), 1)
        self.assertEqual(call["kwargs"], {})
        self.assertIs(call["args"][0], snapshot)


if __name__ == "__main__":
    unittest.main()
