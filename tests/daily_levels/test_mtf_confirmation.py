"""
MarketHunter

Tests for 1D level -> 1h Confirmation Context v1:
DailyLevelsStrategy._score_mtf_entry_confirmation() and its wiring
into analyze_with_entry_candles().

This is an observation-only scoring layer: it determines whether the
last two CLOSED 1h entry candles confirm the daily setup that just
fired, and attaches mtf_entry_confirmation_* metadata describing that
determination, but it never blocks the signal and never changes
direction/score/setup_type/reasons - mtf_entry_confirmation_applied
stays False regardless of is_confirmed.
"""

from __future__ import annotations

import unittest

from models.candle import Candle
from strategies.daily_levels import DailyLevelsStrategy, MTFEntryConfirmation

from .helpers import build_candles, make_candle, make_snapshot


def flat_candle(price: float, day_index: int) -> Candle:
    """
    A small-range entry candle centered on `price`. Used wherever a
    scenario only cares about the candle's close (e.g. the "previous"
    entry candle in continuation checks, or a filler for the ignored
    entry_candles[-1] slot).
    """

    return make_candle(price, price + 0.05, price - 0.05, price, day_index)


class DailyLevelsMtfConfirmationTests(unittest.IsolatedAsyncioTestCase):
    """
    Tests for 1D level -> 1h Confirmation Context v1.

    entry_candles[-2] is always the confirmation ("last") candle and
    entry_candles[-3] is always the prior ("previous") candle;
    entry_candles[-1] is a potentially-unclosed candle that must never
    affect the result, so every entry_candles fixture below has at
    least 3 candles: [previous, last, unclosed].
    """

    RESISTANCE = 105.0
    SUPPORT = 100.0

    def setUp(self) -> None:
        self.strategy = DailyLevelsStrategy()

    async def test_long_breakout_confirms_via_breakout_close(self) -> None:
        """
        A decisive close clearing the level by the 0.05% threshold,
        with the previous entry candle still closed at/below the
        level, confirms a LONG breakout via breakout_close.
        """

        signal_candle = make_candle(
            104.0, 106.5, 103.5, 106.0, day_index=61,
        )
        snapshot = make_snapshot(build_candles(signal_candle))

        entry_candles = [
            flat_candle(104.8, day_index=100),
            make_candle(105.0, 105.5, 104.9, 105.3, day_index=101),
            flat_candle(105.3, day_index=102),
        ]

        signal = await self.strategy.analyze_with_entry_candles(
            snapshot, entry_candles=entry_candles,
        )

        plain_signal = await self.strategy.analyze(
            make_snapshot(build_candles(signal_candle)),
        )

        self.assertIsNotNone(signal)
        self.assertEqual(signal.metadata["setup_type"], "daily_breakout")
        self.assertEqual(
            signal.metadata["mtf_entry_expected_pattern"], "continuation",
        )
        self.assertEqual(
            signal.metadata["mtf_entry_confirmation_type"], "breakout_close",
        )
        self.assertTrue(
            signal.metadata["mtf_entry_confirmation_is_confirmed"],
        )
        # MTF Confirmation Bonus v1: a confirmed context now actually
        # applies a +4 bonus, so mtf_entry_confirmation_applied is
        # True here (it means "bonus really added" as of this task,
        # not merely "confirmation was observed").
        self.assertTrue(
            signal.metadata["mtf_entry_confirmation_applied"],
        )
        self.assertEqual(signal.score, plain_signal.score + 4)

    async def test_long_breakout_confirms_via_retest_hold(self) -> None:
        """
        A decisive close holding above the level after the entry
        candle dipped back into the 0.15% tolerance band, with the
        previous entry candle already closed above the level,
        confirms a LONG breakout via retest_hold_long.
        """

        signal_candle = make_candle(
            104.0, 106.5, 103.5, 106.0, day_index=61,
        )
        snapshot = make_snapshot(build_candles(signal_candle))

        entry_candles = [
            flat_candle(105.3, day_index=100),
            make_candle(105.05, 105.5, 104.95, 105.4, day_index=101),
            flat_candle(105.4, day_index=102),
        ]

        signal = await self.strategy.analyze_with_entry_candles(
            snapshot, entry_candles=entry_candles,
        )

        self.assertIsNotNone(signal)
        self.assertEqual(
            signal.metadata["mtf_entry_confirmation_type"],
            "retest_hold_long",
        )
        self.assertTrue(
            signal.metadata["mtf_entry_confirmation_is_confirmed"],
        )
        self.assertTrue(
            signal.metadata["mtf_entry_confirmation_retested_level"],
        )

    async def test_short_breakdown_confirms_via_breakdown_close(
        self,
    ) -> None:
        """
        A decisive close clearing the level by the 0.05% threshold
        below support, with the previous entry candle still closed
        at/above the level, confirms a SHORT breakdown via
        breakdown_close.
        """

        signal_candle = make_candle(
            101.0, 101.5, 98.5, 99.0, day_index=61,
        )
        snapshot = make_snapshot(build_candles(signal_candle))

        signal_only = await self.strategy.analyze(snapshot)
        self.assertIsNotNone(signal_only)
        self.assertEqual(signal_only.metadata["setup_type"], "daily_breakdown")
        self.assertEqual(signal_only.direction, "SHORT")

        entry_candles = [
            flat_candle(100.2, day_index=100),
            make_candle(100.0, 100.05, 99.6, 99.7, day_index=101),
            flat_candle(99.7, day_index=102),
        ]

        signal = await self.strategy.analyze_with_entry_candles(
            snapshot, entry_candles=entry_candles,
        )

        self.assertIsNotNone(signal)
        self.assertEqual(
            signal.metadata["mtf_entry_expected_pattern"], "continuation",
        )
        self.assertEqual(
            signal.metadata["mtf_entry_confirmation_type"],
            "breakdown_close",
        )
        self.assertTrue(
            signal.metadata["mtf_entry_confirmation_is_confirmed"],
        )

    async def test_support_bounce_confirms_via_bullish_rejection(
        self,
    ) -> None:
        """
        A shallow low touching support within the 0.15% tolerance
        band followed by a decisive bullish close above support
        confirms a support bounce via support_rejection.
        """

        signal_candle = make_candle(
            99.9, 101.0, 99.9, 100.7, day_index=61,
        )
        snapshot = make_snapshot(build_candles(signal_candle))

        entry_candles = [
            flat_candle(100.5, day_index=100),
            make_candle(99.95, 100.40, 99.90, 100.30, day_index=101),
            flat_candle(100.30, day_index=102),
        ]

        signal = await self.strategy.analyze_with_entry_candles(
            snapshot, entry_candles=entry_candles,
        )

        self.assertIsNotNone(signal)
        self.assertEqual(
            signal.metadata["setup_type"], "daily_support_bounce",
        )
        self.assertEqual(
            signal.metadata["mtf_entry_expected_pattern"], "bounce",
        )
        self.assertEqual(
            signal.metadata["mtf_entry_confirmation_type"],
            "support_rejection",
        )
        self.assertTrue(
            signal.metadata["mtf_entry_confirmation_is_confirmed"],
        )
        self.assertTrue(
            signal.metadata["mtf_entry_confirmation_touched_level"],
        )

    async def test_resistance_bounce_confirms_via_bearish_rejection(
        self,
    ) -> None:
        """
        A shallow high touching resistance within the 0.15% tolerance
        band followed by a decisive bearish close below resistance
        confirms a resistance bounce via resistance_rejection.
        """

        signal_candle = make_candle(
            104.9, 105.1, 104.0, 104.3, day_index=61,
        )
        snapshot = make_snapshot(build_candles(signal_candle))

        entry_candles = [
            flat_candle(104.9, day_index=100),
            make_candle(105.05, 105.10, 104.60, 104.70, day_index=101),
            flat_candle(104.70, day_index=102),
        ]

        signal = await self.strategy.analyze_with_entry_candles(
            snapshot, entry_candles=entry_candles,
        )

        self.assertIsNotNone(signal)
        self.assertEqual(
            signal.metadata["setup_type"], "daily_resistance_bounce",
        )
        self.assertEqual(
            signal.metadata["mtf_entry_confirmation_type"],
            "resistance_rejection",
        )
        self.assertTrue(
            signal.metadata["mtf_entry_confirmation_is_confirmed"],
        )

    async def test_false_breakout_confirms_via_reclaim(self) -> None:
        """
        A confirmation candle that pierces above resistance intraday
        but closes back below it decisively confirms a false breakout
        reclaim.
        """

        signal_candle = make_candle(
            104.8, 106.5, 103.0, 103.5, day_index=61,
        )
        snapshot = make_snapshot(build_candles(signal_candle))

        signal_only = await self.strategy.analyze(snapshot)
        self.assertIsNotNone(signal_only)
        self.assertEqual(
            signal_only.metadata["setup_type"],
            "daily_false_breakout_confirmed",
        )

        entry_candles = [
            flat_candle(105.1, day_index=100),
            make_candle(105.2, 105.3, 104.5, 104.7, day_index=101),
            flat_candle(104.7, day_index=102),
        ]

        signal = await self.strategy.analyze_with_entry_candles(
            snapshot, entry_candles=entry_candles,
        )

        self.assertIsNotNone(signal)
        self.assertEqual(
            signal.metadata["mtf_entry_expected_pattern"],
            "false_break_reclaim",
        )
        self.assertEqual(
            signal.metadata["mtf_entry_confirmation_type"],
            "false_breakout_reclaim",
        )
        self.assertTrue(
            signal.metadata["mtf_entry_confirmation_is_confirmed"],
        )
        self.assertGreater(
            signal.metadata["mtf_entry_confirmation_penetration_percent"],
            0.0,
        )

    async def test_false_breakdown_confirms_via_reclaim(self) -> None:
        """
        A confirmation candle that pierces below support intraday but
        closes back above it decisively confirms a false breakdown
        reclaim.
        """

        signal_candle = make_candle(
            99.5, 101.5, 98.3, 101.0, day_index=61,
        )
        snapshot = make_snapshot(build_candles(signal_candle))

        signal_only = await self.strategy.analyze(snapshot)
        self.assertIsNotNone(signal_only)
        self.assertEqual(
            signal_only.metadata["setup_type"],
            "daily_false_breakdown_confirmed",
        )

        entry_candles = [
            flat_candle(99.9, day_index=100),
            make_candle(99.8, 100.5, 99.6, 100.3, day_index=101),
            flat_candle(100.3, day_index=102),
        ]

        signal = await self.strategy.analyze_with_entry_candles(
            snapshot, entry_candles=entry_candles,
        )

        self.assertIsNotNone(signal)
        self.assertEqual(
            signal.metadata["mtf_entry_confirmation_type"],
            "false_breakdown_reclaim",
        )
        self.assertTrue(
            signal.metadata["mtf_entry_confirmation_is_confirmed"],
        )
        self.assertGreater(
            signal.metadata["mtf_entry_confirmation_penetration_percent"],
            0.0,
        )

    async def test_weak_close_does_not_confirm(self) -> None:
        """
        A confirmation candle that clears the breakout threshold on
        price alone, but closes below its own open (not decisive),
        fails to confirm - is_confirmed stays False without raising.
        """

        signal_candle = make_candle(
            104.0, 106.5, 103.5, 106.0, day_index=61,
        )
        snapshot = make_snapshot(build_candles(signal_candle))

        entry_candles = [
            flat_candle(104.8, day_index=100),
            make_candle(105.3, 105.6, 104.9, 105.1, day_index=101),
            flat_candle(105.1, day_index=102),
        ]

        signal = await self.strategy.analyze_with_entry_candles(
            snapshot, entry_candles=entry_candles,
        )

        self.assertIsNotNone(signal)
        self.assertFalse(
            signal.metadata["mtf_entry_confirmation_is_confirmed"],
        )
        self.assertFalse(
            signal.metadata["mtf_entry_confirmation_applied"],
        )

    async def test_fewer_than_three_entry_candles_is_insufficient_data(
        self,
    ) -> None:
        """
        Fewer than three entry candles means there is no closed
        confirmation candle (entry_candles[-2]) and prior candle
        (entry_candles[-3]) pair to read yet.
        """

        signal_candle = make_candle(
            104.0, 106.5, 103.5, 106.0, day_index=61,
        )
        snapshot = make_snapshot(build_candles(signal_candle))

        entry_candles = [
            flat_candle(104.8, day_index=100),
            flat_candle(105.0, day_index=101),
        ]

        signal = await self.strategy.analyze_with_entry_candles(
            snapshot, entry_candles=entry_candles,
        )

        self.assertIsNotNone(signal)
        self.assertEqual(
            signal.metadata["mtf_entry_confirmation_type"],
            "insufficient_data",
        )
        self.assertFalse(
            signal.metadata["mtf_entry_confirmation_is_confirmed"],
        )
        self.assertEqual(
            signal.metadata["mtf_entry_confirmation_analyzed_candles"], 2,
        )
        self.assertIsNone(
            signal.metadata["mtf_entry_confirmation_candle_open_time"],
        )

    async def test_unclosed_last_candle_is_never_read(self) -> None:
        """
        entry_candles[-1] is treated as potentially unclosed and must
        never affect the confirmation result - even when it looks
        like a sharp reversal that would flip the outcome if it were
        (wrongly) read as the confirmation candle.
        """

        signal_candle = make_candle(
            104.0, 106.5, 103.5, 106.0, day_index=61,
        )
        snapshot = make_snapshot(build_candles(signal_candle))

        confirmation_candle = make_candle(
            105.0, 105.5, 104.9, 105.3, day_index=101,
        )
        contradicting_unclosed = make_candle(
            105.3, 105.4, 90.0, 91.0, day_index=102,
        )

        entry_candles = [
            flat_candle(104.8, day_index=100),
            confirmation_candle,
            contradicting_unclosed,
        ]

        signal = await self.strategy.analyze_with_entry_candles(
            snapshot, entry_candles=entry_candles,
        )

        self.assertIsNotNone(signal)
        self.assertTrue(
            signal.metadata["mtf_entry_confirmation_is_confirmed"],
        )
        self.assertEqual(
            signal.metadata["mtf_entry_confirmation_candle_open_time"],
            confirmation_candle.open_time.isoformat(),
        )

    async def test_unconfirmed_context_does_not_change_direction_score_or_reasons(
        self,
    ) -> None:
        """
        An unconfirmed context (weak close, fails the decisive-candle
        check) never changes direction, score, setup_type, or reasons
        versus a plain analyze() call on the same snapshot - only a
        confirmed context adds the MTF Confirmation Bonus v1 +4 (see
        test_long_breakout_confirms_via_breakout_close for that case).
        """

        signal_candle = make_candle(
            99.9, 101.0, 99.9, 100.7, day_index=61,
        )
        snapshot = make_snapshot(build_candles(signal_candle))

        plain_signal = await self.strategy.analyze(
            make_snapshot(build_candles(signal_candle)),
        )

        entry_candles = [
            flat_candle(100.5, day_index=100),
            # close < open - fails the decisive-LONG check, so this
            # support bounce does NOT confirm despite an otherwise
            # in-tolerance low.
            make_candle(100.30, 100.40, 99.90, 100.10, day_index=101),
            flat_candle(100.10, day_index=102),
        ]

        mtf_signal = await self.strategy.analyze_with_entry_candles(
            snapshot, entry_candles=entry_candles,
        )

        self.assertIsNotNone(plain_signal)
        self.assertIsNotNone(mtf_signal)
        self.assertFalse(
            mtf_signal.metadata["mtf_entry_confirmation_is_confirmed"],
        )
        self.assertFalse(
            mtf_signal.metadata["mtf_entry_confirmation_applied"],
        )
        self.assertEqual(mtf_signal.direction, plain_signal.direction)
        self.assertEqual(mtf_signal.score, plain_signal.score)
        self.assertEqual(
            mtf_signal.metadata["setup_type"],
            plain_signal.metadata["setup_type"],
        )
        self.assertEqual(mtf_signal.reasons, plain_signal.reasons)

    async def test_zero_range_confirmation_candle_does_not_raise(
        self,
    ) -> None:
        """
        A confirmation candle whose high equals its low (zero range)
        must not raise a ZeroDivisionError - close_position_percent
        falls back to 50, which fails both the decisive-LONG and
        decisive-SHORT thresholds, so is_confirmed stays False.
        """

        signal_candle = make_candle(
            104.0, 106.5, 103.5, 106.0, day_index=61,
        )
        snapshot = make_snapshot(build_candles(signal_candle))

        entry_candles = [
            flat_candle(104.8, day_index=100),
            make_candle(105.0, 105.0, 105.0, 105.0, day_index=101),
            flat_candle(105.0, day_index=102),
        ]

        signal = await self.strategy.analyze_with_entry_candles(
            snapshot, entry_candles=entry_candles,
        )

        self.assertIsNotNone(signal)
        self.assertEqual(
            signal.metadata["mtf_entry_confirmation_close_position_percent"],
            50.0,
        )
        self.assertFalse(
            signal.metadata["mtf_entry_confirmation_is_confirmed"],
        )

    def test_returns_mtf_entry_confirmation_dataclass_directly(
        self,
    ) -> None:
        """
        _score_mtf_entry_confirmation() itself returns a plain
        MTFEntryConfirmation instance and can be called directly
        (not only through analyze_with_entry_candles()).
        """

        from models.signal import Signal

        signal = Signal(
            symbol="BTCUSDT",
            market="",
            timeframe="1d",
            strategy="DailyLevels",
            direction="LONG",
            score=78.0,
            reasons=[],
            metadata={
                "setup_type": "daily_breakout",
                "level_price": self.RESISTANCE,
            },
        )

        entry_candles = [
            flat_candle(104.8, day_index=100),
            make_candle(105.0, 105.5, 104.9, 105.3, day_index=101),
            flat_candle(105.3, day_index=102),
        ]

        confirmation = self.strategy._score_mtf_entry_confirmation(
            signal, entry_candles,
        )

        self.assertIsInstance(confirmation, MTFEntryConfirmation)
        self.assertEqual(confirmation.expected_pattern, "continuation")
        self.assertEqual(confirmation.confirmation_type, "breakout_close")
        self.assertTrue(confirmation.is_confirmed)
        self.assertEqual(confirmation.analyzed_candle_count, 2)


if __name__ == "__main__":
    unittest.main()
