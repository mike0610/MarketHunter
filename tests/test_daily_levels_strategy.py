"""
MarketHunter

Tests for DailyLevelsStrategy baseline behavior.

This is a read-only characterization suite: it locks in the CURRENT
behavior of DailyLevelsStrategy using synthetic daily candles (no
Binance/API/DB involved), before any Level Quality Foundation v1
changes touch the strategy itself. strategies/daily_levels.py is not
modified by this file.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from models.candle import Candle
from models.market_snapshot import MarketSnapshot
from strategies.daily_levels import DailyLevelsStrategy


RESISTANCE = 105.0
SUPPORT = 100.0

# breakout_buffer_percent / sweep_buffer_percent on DailyLevelsStrategy.
BUFFER_PERCENT = 0.15


def make_candle(
    open_price: float,
    high: float,
    low: float,
    close: float,
    day_index: int,
) -> Candle:
    """
    Build a deterministic daily candle for a given day offset.
    """

    open_time = (
        datetime(2024, 1, 1, tzinfo=timezone.utc)
        + timedelta(days=day_index)
    )

    return Candle(
        open_time=open_time,
        open=open_price,
        high=high,
        low=low,
        close=close,
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


def make_reference_candles(
    count: int,
    resistance: float,
    support: float,
    start_day_index: int,
) -> list[Candle]:
    """
    Build `count` uniform daily candles that pin resistance/support
    at exact known values, with a neutral midpoint close. The last
    candle in this list doubles as previous_candle in the strategy
    (candles[-3]), so its close must sit inside [support, resistance]
    for every setup's `previous_candle.close` condition to hold.
    """

    midpoint = (resistance + support) / 2

    return [
        make_candle(
            open_price=midpoint,
            high=resistance,
            low=support,
            close=midpoint,
            day_index=start_day_index + i,
        )
        for i in range(count)
    ]


def make_snapshot(
    candles: list[Candle],
    symbol: str = "BTCUSDT",
) -> MarketSnapshot:
    """
    Build a minimal MarketSnapshot. DailyLevelsStrategy only reads
    snapshot.symbol and snapshot.candles - the indicator fields below
    are unused by this strategy (it "intentionally avoids indicators"
    per its own docstring) and are set to inert placeholder values.
    """

    return MarketSnapshot(
        symbol=symbol,
        candles=candles,
        ema20=0.0,
        ema50=0.0,
        ema200=0.0,
        atr14=0.0,
        avg_volume20=0.0,
        highest20=0.0,
        lowest20=0.0,
    )


def build_candles(
    signal_candle: Candle,
    resistance: float = RESISTANCE,
    support: float = SUPPORT,
) -> list[Candle]:
    """
    Build a full 63-candle window matching what analyze() requires:
    - index 0: unused lead padding (only len(candles) matters here);
    - indices 1-60: the 60 reference candles that pin resistance/
      support (candles[-62:-2] once the list reaches length 63), the
      last of which is also previous_candle (candles[-3]);
    - index 61: the given signal_candle (candles[-2]);
    - index 62: unused trailing padding (candles[-1] is never read).
    """

    lead_padding = make_candle(
        open_price=(resistance + support) / 2,
        high=resistance,
        low=support,
        close=(resistance + support) / 2,
        day_index=0,
    )

    reference = make_reference_candles(
        count=60,
        resistance=resistance,
        support=support,
        start_day_index=1,
    )

    trailing_padding = make_candle(
        open_price=(resistance + support) / 2,
        high=resistance,
        low=support,
        close=(resistance + support) / 2,
        day_index=62,
    )

    return [lead_padding] + reference + [signal_candle, trailing_padding]


def above_buffer(level: float) -> float:
    """
    Smallest price that clears the 0.15% breakout/sweep buffer above
    `level` (mirrors DailyLevelsStrategy._above_level).
    """

    return level * (1 + BUFFER_PERCENT / 100)


def below_buffer(level: float) -> float:
    """
    Smallest price that clears the 0.15% breakout/sweep buffer below
    `level` (mirrors DailyLevelsStrategy._below_level).
    """

    return level * (1 - BUFFER_PERCENT / 100)


class DailyLevelsStrategyBaselineTests(unittest.IsolatedAsyncioTestCase):
    """
    Lock in the current, pre-upgrade behavior of DailyLevelsStrategy.

    This is a regression baseline: Level Quality Foundation v1 must
    not silently change any of these outcomes unless that change is
    explicitly intended.
    """

    async def test_daily_breakout_is_long(self) -> None:
        """
        A daily close that clears resistance + buffer is a LONG
        daily_breakout.
        """

        strategy = DailyLevelsStrategy()

        signal_candle = make_candle(
            open_price=104.0,
            high=106.5,
            low=103.5,
            close=106.0,
            day_index=61,
        )

        snapshot = make_snapshot(
            build_candles(signal_candle),
        )

        signal = await strategy.analyze(snapshot)

        self.assertIsNotNone(signal)

        self.assertEqual(
            signal.direction,
            "LONG",
        )

        self.assertEqual(
            signal.metadata["setup_type"],
            "daily_breakout",
        )

    async def test_daily_breakdown_is_short(self) -> None:
        """
        A daily close that clears support - buffer is a SHORT
        daily_breakdown.
        """

        strategy = DailyLevelsStrategy()

        signal_candle = make_candle(
            open_price=101.0,
            high=101.5,
            low=98.5,
            close=99.0,
            day_index=61,
        )

        snapshot = make_snapshot(
            build_candles(signal_candle),
        )

        signal = await strategy.analyze(snapshot)

        self.assertIsNotNone(signal)

        self.assertEqual(
            signal.direction,
            "SHORT",
        )

        self.assertEqual(
            signal.metadata["setup_type"],
            "daily_breakdown",
        )

    async def test_daily_false_breakout_is_short(self) -> None:
        """
        A high that sweeps resistance + buffer but a close back below
        resistance is a SHORT daily_false_breakout.
        """

        strategy = DailyLevelsStrategy()

        signal_candle = make_candle(
            open_price=104.5,
            high=106.0,
            low=103.5,
            close=104.0,
            day_index=61,
        )

        snapshot = make_snapshot(
            build_candles(signal_candle),
        )

        signal = await strategy.analyze(snapshot)

        self.assertIsNotNone(signal)

        self.assertEqual(
            signal.direction,
            "SHORT",
        )

        self.assertEqual(
            signal.metadata["setup_type"],
            "daily_false_breakout",
        )

    async def test_daily_false_breakdown_is_long(self) -> None:
        """
        A low that sweeps support - buffer but a close back above
        support is a LONG daily_false_breakdown.
        """

        strategy = DailyLevelsStrategy()

        signal_candle = make_candle(
            open_price=100.5,
            high=101.5,
            low=99.0,
            close=101.0,
            day_index=61,
        )

        snapshot = make_snapshot(
            build_candles(signal_candle),
        )

        signal = await strategy.analyze(snapshot)

        self.assertIsNotNone(signal)

        self.assertEqual(
            signal.direction,
            "LONG",
        )

        self.assertEqual(
            signal.metadata["setup_type"],
            "daily_false_breakdown",
        )

    async def test_fewer_than_minimum_candles_returns_none(self) -> None:
        """
        Fewer than lookback_days + 3 (63) candles yields no signal.
        """

        strategy = DailyLevelsStrategy()

        signal_candle = make_candle(
            open_price=104.0,
            high=106.5,
            low=103.5,
            close=106.0,
            day_index=61,
        )

        candles = build_candles(signal_candle)[:-1]

        self.assertEqual(
            len(candles),
            62,
        )

        snapshot = make_snapshot(candles)

        signal = await strategy.analyze(snapshot)

        self.assertIsNone(signal)

    async def test_level_range_below_minimum_returns_none(self) -> None:
        """
        A resistance/support band narrower than 3% yields no signal,
        even with an otherwise valid breakout close.
        """

        strategy = DailyLevelsStrategy()

        narrow_resistance = 101.0
        narrow_support = 99.5

        signal_candle = make_candle(
            open_price=100.5,
            high=101.5,
            low=100.0,
            close=101.3,
            day_index=61,
        )

        snapshot = make_snapshot(
            build_candles(
                signal_candle,
                resistance=narrow_resistance,
                support=narrow_support,
            ),
        )

        signal = await strategy.analyze(snapshot)

        self.assertIsNone(signal)

    async def test_breakout_inside_buffer_returns_none(self) -> None:
        """
        A close that clears resistance but stays inside the 0.15%
        buffer is not a breakout (and matches no other setup either).
        """

        strategy = DailyLevelsStrategy()

        just_inside_buffer = RESISTANCE + (
            (above_buffer(RESISTANCE) - RESISTANCE) / 2
        )

        signal_candle = make_candle(
            open_price=104.8,
            high=just_inside_buffer,
            low=104.5,
            close=just_inside_buffer,
            day_index=61,
        )

        snapshot = make_snapshot(
            build_candles(signal_candle),
        )

        signal = await strategy.analyze(snapshot)

        self.assertIsNone(signal)

    async def test_estimated_stop_distance_too_wide_returns_none(
        self,
    ) -> None:
        """
        A breakout that would otherwise fire is still discarded when
        the estimated stop distance (back to the opposite level)
        exceeds max_estimated_stop_distance_percent (8%).
        """

        strategy = DailyLevelsStrategy()

        signal_candle = make_candle(
            open_price=107.0,
            high=109.5,
            low=106.5,
            close=109.0,
            day_index=61,
        )

        snapshot = make_snapshot(
            build_candles(signal_candle),
        )

        signal = await strategy.analyze(snapshot)

        self.assertIsNone(signal)

    async def test_false_breakout_takes_priority_over_breakout(
        self,
    ) -> None:
        """
        The setup detection order (false_breakout_short checked
        before breakout_long) means a sweep-and-reject candle is
        always classified as a false breakout, never a breakout,
        even though its high alone pierces the breakout buffer too.
        """

        strategy = DailyLevelsStrategy()

        signal_candle = make_candle(
            open_price=104.5,
            high=106.0,
            low=103.5,
            close=104.0,
            day_index=61,
        )

        snapshot = make_snapshot(
            build_candles(signal_candle),
        )

        signal = await strategy.analyze(snapshot)

        self.assertIsNotNone(signal)

        self.assertEqual(
            signal.metadata["setup_type"],
            "daily_false_breakout",
        )

        self.assertNotEqual(
            signal.metadata["setup_type"],
            "daily_breakout",
        )

        self.assertEqual(
            signal.direction,
            "SHORT",
        )

    async def test_metadata_contract(self) -> None:
        """
        Lock in the metadata/signal fields the rest of the system
        currently depends on.
        """

        strategy = DailyLevelsStrategy()

        signal_candle = make_candle(
            open_price=104.0,
            high=106.5,
            low=103.5,
            close=106.0,
            day_index=61,
        )

        snapshot = make_snapshot(
            build_candles(signal_candle),
            symbol="BTCUSDT",
        )

        signal = await strategy.analyze(snapshot)

        self.assertIsNotNone(signal)

        self.assertEqual(
            signal.symbol,
            "BTCUSDT",
        )

        self.assertEqual(
            signal.timeframe,
            "1d",
        )

        self.assertEqual(
            signal.strategy,
            "DailyLevels",
        )

        self.assertFalse(
            signal.metadata["uses_indicators"],
        )

        self.assertEqual(
            signal.metadata["confirmation"],
            "daily_close",
        )

        self.assertEqual(
            signal.metadata["daily_support"],
            SUPPORT,
        )

        self.assertEqual(
            signal.metadata["daily_resistance"],
            RESISTANCE,
        )

        self.assertEqual(
            signal.metadata["lookback_days"],
            60,
        )

        self.assertEqual(
            signal.metadata["strategy_family"],
            "daily_levels",
        )


if __name__ == "__main__":
    unittest.main()
