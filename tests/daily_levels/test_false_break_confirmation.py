"""
MarketHunter

Tests for Confirmed false breakout v2: scoring how decisively a false
breakout/false breakdown candle rejected the level, via
_score_false_break_confirmation() and its effect on
_detect_false_breakout_short() / _detect_false_breakdown_long().
"""

from __future__ import annotations

import unittest

from strategies.daily_levels import DailyLevelsStrategy, FalseBreakContext

from .helpers import build_candles, make_candle, make_snapshot


class DailyLevelsFalseBreakConfirmationTests(unittest.IsolatedAsyncioTestCase):
    """
    Tests for Confirmed false breakout v2: scoring how decisively a
    false breakout/false breakdown candle rejected the level, via
    _score_false_break_confirmation() and its effect on
    _detect_false_breakout_short() / _detect_false_breakdown_long().

    A legacy false break that fails confirmation still fires as
    before (weak) - only a genuinely decisive rejection is
    reclassified as *_confirmed with a score bonus.
    """

    RESISTANCE = 105.0
    SUPPORT = 100.0

    def setUp(self) -> None:
        self.strategy = DailyLevelsStrategy()

    async def test_confirmed_false_breakout_short_gets_new_setup_and_bonus(
        self,
    ) -> None:
        """
        A deep sweep with a strong reclaim and a close near the
        candle's low is a confirmed false breakout: +6, cap 85.
        """

        signal_candle = make_candle(
            104.8, 106.5, 103.0, 103.5, day_index=61,
        )

        snapshot = make_snapshot(
            build_candles(signal_candle),
        )

        signal = await self.strategy.analyze(snapshot)

        self.assertIsNotNone(signal)
        self.assertEqual(
            signal.metadata["setup_type"], "daily_false_breakout_confirmed",
        )
        self.assertEqual(signal.score, 84.0)
        self.assertEqual(signal.metadata["false_break_context"], "confirmed")
        self.assertEqual(
            signal.metadata["false_break_score_adjustment"], 6.0,
        )
        self.assertEqual(
            signal.metadata["false_break_context_version"], "v2",
        )
        self.assertIn(
            "False breakout confirmed by decisive close below resistance",
            signal.reasons,
        )

    async def test_confirmed_false_breakdown_long_gets_new_setup_and_bonus(
        self,
    ) -> None:
        """
        A deep sweep with a strong reclaim and a close near the
        candle's high is a confirmed false breakdown: +6, cap 85.
        """

        signal_candle = make_candle(
            99.5, 101.5, 98.3, 101.0, day_index=61,
        )

        snapshot = make_snapshot(
            build_candles(signal_candle),
        )

        signal = await self.strategy.analyze(snapshot)

        self.assertIsNotNone(signal)
        self.assertEqual(
            signal.metadata["setup_type"],
            "daily_false_breakdown_confirmed",
        )
        self.assertEqual(signal.score, 84.0)
        self.assertEqual(signal.metadata["false_break_context"], "confirmed")
        self.assertEqual(
            signal.metadata["false_break_score_adjustment"], 6.0,
        )

    async def test_weak_reclaim_leaves_legacy_setup(self) -> None:
        """
        A close that clears resistance-buffer penetration but barely
        reclaims (< 0.10%) back inside the level fails confirmation
        and stays a legacy daily_false_breakout.
        """

        signal_candle = make_candle(
            105.0, 106.0, 104.5, 104.95, day_index=61,
        )

        snapshot = make_snapshot(
            build_candles(signal_candle),
        )

        signal = await self.strategy.analyze(snapshot)

        self.assertIsNotNone(signal)
        self.assertEqual(
            signal.metadata["setup_type"], "daily_false_breakout",
        )
        self.assertEqual(signal.metadata["false_break_context"], "weak")
        self.assertEqual(
            signal.metadata["false_break_score_adjustment"], 0.0,
        )
        self.assertLess(
            signal.metadata["false_break_reclaim_percent"], 0.10,
        )

    async def test_wrong_close_position_leaves_legacy_setup(self) -> None:
        """
        Adequate penetration and reclaim are not enough on their own -
        a close sitting in the upper part of the candle's own range
        (close_position > 40% for a resistance rejection) also fails
        confirmation.
        """

        signal_candle = make_candle(
            105.5, 106.0, 100.0, 104.5, day_index=61,
        )

        snapshot = make_snapshot(
            build_candles(signal_candle),
        )

        signal = await self.strategy.analyze(snapshot)

        self.assertIsNotNone(signal)
        self.assertEqual(
            signal.metadata["setup_type"], "daily_false_breakout",
        )
        self.assertEqual(signal.metadata["false_break_context"], "weak")
        self.assertGreater(
            signal.metadata["false_break_close_position_percent"], 40.0,
        )

    async def test_bullish_resistance_false_break_is_not_confirmed(
        self,
    ) -> None:
        """
        Penetration, reclaim, and close_position can all pass, but a
        resistance false break only confirms on a decisive close in
        the rejection direction (close < open). A bullish candle
        never confirms, regardless of the other three conditions.
        """

        signal_candle = make_candle(
            103.2, 106.5, 103.0, 103.5, day_index=61,
        )

        snapshot = make_snapshot(
            build_candles(signal_candle),
        )

        signal = await self.strategy.analyze(snapshot)

        self.assertIsNotNone(signal)
        self.assertEqual(
            signal.metadata["setup_type"], "daily_false_breakout",
        )
        self.assertEqual(signal.metadata["false_break_context"], "weak")

    async def test_normal_breakout_has_not_applicable_false_break_context(
        self,
    ) -> None:
        """
        Plain daily_breakout/daily_breakdown are untouched by this
        task: false_break_context is always "not_applicable" there.
        """

        signal_candle = make_candle(
            104.0, 106.5, 103.5, 106.0, day_index=61,
        )

        snapshot = make_snapshot(
            build_candles(signal_candle),
        )

        signal = await self.strategy.analyze(snapshot)

        self.assertIsNotNone(signal)
        self.assertEqual(signal.metadata["setup_type"], "daily_breakout")
        self.assertEqual(
            signal.metadata["false_break_context"], "not_applicable",
        )
        self.assertEqual(
            signal.metadata["false_break_score_adjustment"], 0.0,
        )

    def test_zero_range_candle_does_not_raise(self) -> None:
        """
        A candle whose high equals its low (zero range) must not
        raise a ZeroDivisionError when computing close_position - it
        simply cannot be confirmed.
        """

        flat_candle = make_candle(
            105.0, 105.0, 105.0, 105.0, day_index=61,
        )

        context = self.strategy._score_false_break_confirmation(
            signal_candle=flat_candle,
            level_price=self.RESISTANCE,
            level_side="resistance",
        )

        self.assertIsInstance(context, FalseBreakContext)
        self.assertFalse(context.is_confirmed)
        self.assertEqual(context.close_position_percent, 0.0)


if __name__ == "__main__":
    unittest.main()
