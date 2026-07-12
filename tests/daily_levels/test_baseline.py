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

from strategies.daily_levels import DailyLevelsStrategy

from .helpers import (
    RESISTANCE,
    SUPPORT,
    above_buffer,
    build_candles,
    make_candle,
    make_snapshot,
)


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

        The close sits high inside this candle's own range (close
        position 60%, above the confirmed-false-breakout <=40%
        threshold), so this stays a legacy (weak) false breakout, not
        a confirmed one - see Confirmed false breakout v2.
        """

        strategy = DailyLevelsStrategy()

        signal_candle = make_candle(
            open_price=104.5,
            high=106.0,
            low=101.0,
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

        The close sits low inside this candle's own range (close
        position 50%, below the confirmed-false-breakdown >=60%
        threshold), so this stays a legacy (weak) false breakdown,
        not a confirmed one - see Confirmed false breakout v2.
        """

        strategy = DailyLevelsStrategy()

        signal_candle = make_candle(
            open_price=100.5,
            high=103.0,
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

        Uses a weak (unconfirmed) false breakout candle so this test
        stays focused on setup priority, not on Confirmed false
        breakout v2's separate confirmed/weak classification.
        """

        strategy = DailyLevelsStrategy()

        signal_candle = make_candle(
            open_price=104.5,
            high=106.0,
            low=101.0,
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
