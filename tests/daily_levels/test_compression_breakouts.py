"""
MarketHunter

Tests for Compression-aware breakout v1: activating Approach Context
v1 for the plain breakout/breakdown setups only.
"""

from __future__ import annotations

import unittest

from strategies.daily_levels import (
    DailyLevelsStrategy,
    LevelApproachContext,
    LevelQuality,
)

from .helpers import (
    build_candles,
    build_candles_with_approach,
    make_candle,
    make_snapshot,
)


class DailyLevelsCompressionAwareBreakoutTests(unittest.IsolatedAsyncioTestCase):
    """
    Tests for Compression-aware breakout v1: activating Approach
    Context v1 for the plain breakout/breakdown setups only.

    Unlike Level Quality Foundation v1 and Approach Context v1, this
    genuinely changes setup_type and signal.score for the breakout/
    breakdown setups - it is no longer observation-only for those two
    setups. False breakout/false breakdown remain untouched.
    """

    RESISTANCE = 105.0
    SUPPORT = 100.0

    def setUp(self) -> None:
        self.strategy = DailyLevelsStrategy()

    async def test_compression_breakout_long_gets_new_setup_type_and_bonus(
        self,
    ) -> None:
        """
        Four reference candles compressing toward resistance turn a
        plain breakout into daily_breakout_compression with a +6
        bonus (raised cap 84).
        """

        approach_candles = [
            make_candle(101.0, 102.0, 100.5, 101.0, day_index=57),
            make_candle(102.5, 103.2, 101.8, 102.5, day_index=58),
            make_candle(103.7, 104.1, 103.3, 103.7, day_index=59),
            make_candle(104.6, 104.9, 104.3, 104.6, day_index=60),
        ]

        signal_candle = make_candle(
            104.0, 106.5, 103.5, 106.0, day_index=61,
        )

        snapshot = make_snapshot(
            build_candles_with_approach(signal_candle, approach_candles),
        )

        signal = await self.strategy.analyze(snapshot)

        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, "LONG")
        self.assertEqual(
            signal.metadata["setup_type"], "daily_breakout_compression",
        )
        self.assertEqual(signal.score, 84.0)
        self.assertEqual(signal.metadata["breakout_context"], "compression")
        self.assertEqual(
            signal.metadata["breakout_context_score_adjustment"], 6.0,
        )
        self.assertEqual(
            signal.metadata["breakout_context_version"], "v1",
        )
        self.assertIn(
            "Pre-breakout compression confirmed over 4 bars",
            signal.reasons,
        )

    async def test_compression_breakdown_short_gets_new_setup_type_and_bonus(
        self,
    ) -> None:
        """
        Four reference candles compressing toward support turn a
        plain breakdown into daily_breakdown_compression with a +6
        bonus (raised cap 84).
        """

        approach_candles = [
            make_candle(104.0, 104.5, 102.5, 104.0, day_index=57),
            make_candle(102.5, 103.2, 101.5, 102.5, day_index=58),
            make_candle(101.3, 101.9, 100.7, 101.3, day_index=59),
            make_candle(100.4, 100.8, 100.1, 100.4, day_index=60),
        ]

        signal_candle = make_candle(
            101.0, 101.5, 98.5, 99.0, day_index=61,
        )

        snapshot = make_snapshot(
            build_candles_with_approach(signal_candle, approach_candles),
        )

        signal = await self.strategy.analyze(snapshot)

        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, "SHORT")
        self.assertEqual(
            signal.metadata["setup_type"], "daily_breakdown_compression",
        )
        self.assertEqual(signal.score, 84.0)
        self.assertEqual(signal.metadata["breakout_context"], "compression")
        self.assertEqual(
            signal.metadata["breakout_context_score_adjustment"], 6.0,
        )

    async def test_neutral_breakout_keeps_old_setup_and_score(self) -> None:
        """
        The uniform baseline reference candles (flat closes, no
        approach toward the level) leave a plain breakout's setup_type
        and score exactly as before this task.
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
        self.assertEqual(signal.score, 78.0)
        self.assertEqual(signal.metadata["breakout_context"], "neutral")
        self.assertEqual(
            signal.metadata["breakout_context_score_adjustment"], 0.0,
        )

    async def test_large_bar_breakout_gets_penalty(self) -> None:
        """
        Three small-range candles followed by one large-range candle
        sitting right at resistance applies a -4 penalty without
        renaming the setup.
        """

        approach_candles = [
            make_candle(101.0, 101.5, 100.5, 101.0, day_index=57),
            make_candle(101.2, 101.7, 100.7, 101.2, day_index=58),
            make_candle(101.4, 101.9, 100.9, 101.4, day_index=59),
            make_candle(104.6, 105.0, 100.5, 104.6, day_index=60),
        ]

        signal_candle = make_candle(
            104.0, 106.5, 103.5, 106.0, day_index=61,
        )

        snapshot = make_snapshot(
            build_candles_with_approach(signal_candle, approach_candles),
        )

        signal = await self.strategy.analyze(snapshot)

        self.assertIsNotNone(signal)
        self.assertEqual(signal.metadata["setup_type"], "daily_breakout")
        self.assertEqual(signal.score, 74.0)
        self.assertEqual(signal.metadata["breakout_context"], "large_bar")
        self.assertEqual(
            signal.metadata["breakout_context_score_adjustment"], -4.0,
        )
        self.assertIn(
            "Large-bar approach weakens breakout quality",
            signal.reasons,
        )

    async def test_large_bar_breakdown_gets_penalty(self) -> None:
        """
        Three small-range candles followed by one large-range candle
        sitting right at support applies a -4 penalty without renaming
        the setup.
        """

        approach_candles = [
            make_candle(104.0, 104.5, 103.5, 104.0, day_index=57),
            make_candle(103.8, 104.3, 103.3, 103.8, day_index=58),
            make_candle(103.6, 104.1, 103.1, 103.6, day_index=59),
            make_candle(100.4, 104.0, 100.0, 100.4, day_index=60),
        ]

        signal_candle = make_candle(
            101.0, 101.5, 98.5, 99.0, day_index=61,
        )

        snapshot = make_snapshot(
            build_candles_with_approach(signal_candle, approach_candles),
        )

        signal = await self.strategy.analyze(snapshot)

        self.assertIsNotNone(signal)
        self.assertEqual(signal.metadata["setup_type"], "daily_breakdown")
        self.assertEqual(signal.score, 74.0)
        self.assertEqual(signal.metadata["breakout_context"], "large_bar")
        self.assertEqual(
            signal.metadata["breakout_context_score_adjustment"], -4.0,
        )

    def test_compression_takes_priority_over_large_bar(self) -> None:
        """
        When is_compression and is_large_bar_approach are both true
        (a theoretical edge case Approach Context v1 can produce),
        the compression bonus applies and the large-bar penalty does
        not.
        """

        resistance_approach = LevelApproachContext(
            bar_count=4,
            closer_close_count=3,
            smaller_range_count=2,
            distance_reduction_percent=90.0,
            range_reduction_percent=30.0,
            is_compression=True,
            is_large_bar_approach=True,
        )

        support_approach = LevelApproachContext(
            bar_count=4,
            closer_close_count=0,
            smaller_range_count=0,
            distance_reduction_percent=0.0,
            range_reduction_percent=0.0,
            is_compression=False,
            is_large_bar_approach=False,
        )

        resistance_quality = LevelQuality(
            score=0.0,
            reaction_count=0,
            false_break_count=0,
            max_reaction_percent=0.0,
        )

        support_quality = LevelQuality(
            score=0.0,
            reaction_count=0,
            false_break_count=0,
            max_reaction_percent=0.0,
        )

        signal_candle = make_candle(
            104.0, 106.5, 103.5, 106.0, day_index=61,
        )

        previous_candle = make_candle(
            102.5, 103.0, 102.0, 102.5, day_index=60,
        )

        setup = self.strategy._detect_breakout_long(
            signal_candle=signal_candle,
            previous_candle=previous_candle,
            resistance=self.RESISTANCE,
            support=self.SUPPORT,
            level_range_percent=5.0,
            resistance_quality=resistance_quality,
            support_quality=support_quality,
            resistance_approach=resistance_approach,
            support_approach=support_approach,
        )

        self.assertIsNotNone(setup)
        self.assertEqual(setup.setup_type, "daily_breakout_compression")
        self.assertEqual(setup.score, 84.0)

    async def test_false_breakout_has_no_score_adjustment(self) -> None:
        """
        False breakout/false breakdown are untouched by this task:
        breakout_context is "not_applicable" and the score adjustment
        is always 0, regardless of any approach context.

        Uses a weak (unconfirmed) false breakout candle so this test
        stays focused on breakout_context, not on Confirmed false
        breakout v2's separate confirmed/weak classification.
        """

        signal_candle = make_candle(
            104.5, 106.0, 101.0, 104.0, day_index=61,
        )

        snapshot = make_snapshot(
            build_candles(signal_candle),
        )

        signal = await self.strategy.analyze(snapshot)

        self.assertIsNotNone(signal)
        self.assertEqual(
            signal.metadata["setup_type"], "daily_false_breakout",
        )
        self.assertEqual(
            signal.metadata["breakout_context"], "not_applicable",
        )
        self.assertEqual(
            signal.metadata["breakout_context_score_adjustment"], 0.0,
        )
        self.assertEqual(signal.score, 78.0)


if __name__ == "__main__":
    unittest.main()
