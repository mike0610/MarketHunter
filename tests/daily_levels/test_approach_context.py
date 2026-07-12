"""
MarketHunter

Tests for _score_level_approach() and for how its result is threaded
into signal metadata (Approach Context v1).
"""

from __future__ import annotations

import unittest

from strategies.daily_levels import (
    DailyLevelsStrategy,
    LevelApproachContext,
    LevelQuality,
)

from .helpers import make_candle


class DailyLevelsApproachContextTests(unittest.TestCase):
    """
    Tests for _score_level_approach() and for how its result is
    threaded into signal metadata (Approach Context v1).

    These test the pure scoring function and the metadata mapping
    directly, independent of the full analyze() pipeline - see
    DailyLevelsStrategyBaselineTests above for confirmation that
    adding this scoring did not change any of the 4 setups' behavior.
    """

    RESISTANCE = 105.0
    SUPPORT = 100.0

    def setUp(self) -> None:
        self.strategy = DailyLevelsStrategy()

    def test_compression_toward_resistance(self) -> None:
        """
        Four closes drifting steadily closer to resistance, with
        shrinking candle ranges, is a compression approach.
        """

        reference_candles = [
            make_candle(99.0, 101.0, 97.0, 99.0, day_index=0),
            make_candle(101.0, 102.5, 99.5, 101.0, day_index=1),
            make_candle(103.0, 104.0, 102.0, 103.0, day_index=2),
            make_candle(104.5, 105.2, 104.3, 104.7, day_index=3),
        ]

        context = self.strategy._score_level_approach(
            reference_candles=reference_candles,
            level_price=self.RESISTANCE,
            level_side="resistance",
        )

        self.assertEqual(context.bar_count, 4)
        self.assertEqual(context.closer_close_count, 3)
        self.assertGreaterEqual(context.smaller_range_count, 2)
        self.assertGreaterEqual(context.distance_reduction_percent, 50.0)
        self.assertGreaterEqual(context.range_reduction_percent, 20.0)
        self.assertTrue(context.is_compression)

    def test_compression_toward_support(self) -> None:
        """
        Four closes drifting steadily closer to support, with
        shrinking candle ranges, is a compression approach.
        """

        reference_candles = [
            make_candle(106.0, 108.0, 104.0, 106.0, day_index=0),
            make_candle(104.0, 105.5, 102.5, 104.0, day_index=1),
            make_candle(102.0, 103.0, 101.0, 102.0, day_index=2),
            make_candle(100.3, 100.7, 99.9, 100.3, day_index=3),
        ]

        context = self.strategy._score_level_approach(
            reference_candles=reference_candles,
            level_price=self.SUPPORT,
            level_side="support",
        )

        self.assertEqual(context.bar_count, 4)
        self.assertEqual(context.closer_close_count, 3)
        self.assertGreaterEqual(context.smaller_range_count, 2)
        self.assertGreaterEqual(context.distance_reduction_percent, 50.0)
        self.assertGreaterEqual(context.range_reduction_percent, 20.0)
        self.assertTrue(context.is_compression)

    def test_equal_distant_closes_are_not_compression(self) -> None:
        """
        Four candles sitting at the same distance from the level
        never get closer to it, so closer_close_count stays 0 and no
        compression is reported.
        """

        reference_candles = [
            make_candle(95.0, 97.0, 93.0, 95.0, day_index=i)
            for i in range(4)
        ]

        context = self.strategy._score_level_approach(
            reference_candles=reference_candles,
            level_price=self.RESISTANCE,
            level_side="resistance",
        )

        self.assertEqual(context.closer_close_count, 0)
        self.assertFalse(context.is_compression)

    def test_distance_reduction_without_range_reduction_is_not_compression(
        self,
    ) -> None:
        """
        Closes drifting steadily closer to resistance is not enough
        on its own - candle ranges must also shrink by at least
        level_approach_min_range_reduction_percent.
        """

        reference_candles = [
            make_candle(99.0, 100.0, 98.0, 99.0, day_index=0),
            make_candle(101.0, 102.0, 100.0, 101.0, day_index=1),
            make_candle(103.0, 104.0, 102.0, 103.0, day_index=2),
            make_candle(104.7, 105.7, 103.7, 104.7, day_index=3),
        ]

        context = self.strategy._score_level_approach(
            reference_candles=reference_candles,
            level_price=self.RESISTANCE,
            level_side="resistance",
        )

        self.assertEqual(context.closer_close_count, 3)
        self.assertLess(context.range_reduction_percent, 20.0)
        self.assertFalse(context.is_compression)

    def test_large_last_candle_sets_is_large_bar_approach(self) -> None:
        """
        A last candle sitting within 1.0% of the level with a range
        at least 1.5x the median range of the preceding candles is
        flagged as a large-bar approach.
        """

        reference_candles = [
            make_candle(95.0, 96.0, 94.0, 95.0, day_index=0),
            make_candle(96.0, 97.0, 95.0, 96.0, day_index=1),
            make_candle(97.0, 98.0, 96.0, 97.0, day_index=2),
            make_candle(104.5, 110.0, 99.0, 104.5, day_index=3),
        ]

        context = self.strategy._score_level_approach(
            reference_candles=reference_candles,
            level_price=self.RESISTANCE,
            level_side="resistance",
        )

        self.assertTrue(context.is_large_bar_approach)
        self.assertFalse(context.is_compression)

    def test_metadata_uses_resistance_context_for_resistance_setups(
        self,
    ) -> None:
        """
        A resistance-side setup (breakout/false breakout) reports
        resistance_approach in the approach_* fields, while still
        exposing both sides via daily_support_is_compression /
        daily_resistance_is_compression.
        """

        resistance_quality = LevelQuality(
            score=80.0,
            reaction_count=2,
            false_break_count=1,
            max_reaction_percent=2.5,
        )

        support_quality = LevelQuality(
            score=10.0,
            reaction_count=0,
            false_break_count=1,
            max_reaction_percent=0.0,
        )

        resistance_approach = LevelApproachContext(
            bar_count=4,
            closer_close_count=3,
            smaller_range_count=3,
            distance_reduction_percent=90.0,
            range_reduction_percent=60.0,
            is_compression=True,
            is_large_bar_approach=False,
        )

        support_approach = LevelApproachContext(
            bar_count=4,
            closer_close_count=0,
            smaller_range_count=0,
            distance_reduction_percent=0.0,
            range_reduction_percent=0.0,
            is_compression=False,
            is_large_bar_approach=True,
        )

        signal_candle = make_candle(
            104.0, 106.5, 103.5, 106.0, day_index=61,
        )

        previous_candle = make_candle(
            102.5, 103.0, 102.0, 102.5, day_index=60,
        )

        metadata = self.strategy._metadata(
            setup_type="daily_breakout",
            level_name="daily_resistance",
            level_price=self.RESISTANCE,
            support=self.SUPPORT,
            resistance=self.RESISTANCE,
            signal_candle=signal_candle,
            previous_candle=previous_candle,
            level_range_percent=5.0,
            trigger_distance_percent=1.0,
            resistance_quality=resistance_quality,
            support_quality=support_quality,
            resistance_approach=resistance_approach,
            support_approach=support_approach,
            breakout_context="not_applicable",
            breakout_context_score_adjustment=0.0,
            false_break_context="not_applicable",
            false_break_penetration_percent=0.0,
            false_break_reclaim_percent=0.0,
            false_break_close_position_percent=0.0,
            false_break_score_adjustment=0.0,
            bounce_context="not_applicable",
            bounce_rejection_percent=0.0,
            bounce_close_position_percent=0.0,
            bounce_score_adjustment=0.0,
        )

        self.assertEqual(metadata["approach_bar_count"], 4)
        self.assertEqual(metadata["approach_closer_close_count"], 3)
        self.assertEqual(metadata["approach_smaller_range_count"], 3)
        self.assertEqual(
            metadata["approach_distance_reduction_percent"], 90.0,
        )
        self.assertEqual(
            metadata["approach_range_reduction_percent"], 60.0,
        )
        self.assertTrue(metadata["approach_is_compression"])
        self.assertFalse(metadata["approach_is_large_bar"])
        self.assertEqual(metadata["approach_context_version"], "v1")
        self.assertTrue(metadata["daily_resistance_is_compression"])
        self.assertFalse(metadata["daily_support_is_compression"])

    def test_metadata_uses_support_context_for_support_setups(
        self,
    ) -> None:
        """
        A support-side setup (breakdown/false breakdown) reports
        support_approach in the approach_* fields, while still
        exposing both sides via daily_support_is_compression /
        daily_resistance_is_compression.
        """

        resistance_quality = LevelQuality(
            score=80.0,
            reaction_count=2,
            false_break_count=1,
            max_reaction_percent=2.5,
        )

        support_quality = LevelQuality(
            score=10.0,
            reaction_count=0,
            false_break_count=1,
            max_reaction_percent=0.0,
        )

        resistance_approach = LevelApproachContext(
            bar_count=4,
            closer_close_count=0,
            smaller_range_count=0,
            distance_reduction_percent=0.0,
            range_reduction_percent=0.0,
            is_compression=False,
            is_large_bar_approach=True,
        )

        support_approach = LevelApproachContext(
            bar_count=4,
            closer_close_count=3,
            smaller_range_count=3,
            distance_reduction_percent=90.0,
            range_reduction_percent=60.0,
            is_compression=True,
            is_large_bar_approach=False,
        )

        signal_candle = make_candle(
            101.0, 101.5, 98.5, 99.0, day_index=61,
        )

        previous_candle = make_candle(
            102.5, 103.0, 102.0, 102.5, day_index=60,
        )

        metadata = self.strategy._metadata(
            setup_type="daily_breakdown",
            level_name="daily_support",
            level_price=self.SUPPORT,
            support=self.SUPPORT,
            resistance=self.RESISTANCE,
            signal_candle=signal_candle,
            previous_candle=previous_candle,
            level_range_percent=5.0,
            trigger_distance_percent=1.0,
            resistance_quality=resistance_quality,
            support_quality=support_quality,
            resistance_approach=resistance_approach,
            support_approach=support_approach,
            breakout_context="not_applicable",
            breakout_context_score_adjustment=0.0,
            false_break_context="not_applicable",
            false_break_penetration_percent=0.0,
            false_break_reclaim_percent=0.0,
            false_break_close_position_percent=0.0,
            false_break_score_adjustment=0.0,
            bounce_context="not_applicable",
            bounce_rejection_percent=0.0,
            bounce_close_position_percent=0.0,
            bounce_score_adjustment=0.0,
        )

        self.assertEqual(metadata["approach_bar_count"], 4)
        self.assertTrue(metadata["approach_is_compression"])
        self.assertFalse(metadata["approach_is_large_bar"])
        self.assertTrue(metadata["daily_support_is_compression"])
        self.assertFalse(metadata["daily_resistance_is_compression"])


if __name__ == "__main__":
    unittest.main()
