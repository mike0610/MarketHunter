"""
MarketHunter

Tests for _score_level_quality() and for how its result is threaded
into signal metadata (Level Quality Foundation v1).
"""

from __future__ import annotations

import unittest

from strategies.daily_levels import (
    DailyLevelsStrategy,
    LevelApproachContext,
    LevelQuality,
)

from .helpers import make_candle


class DailyLevelsLevelQualityTests(unittest.TestCase):
    """
    Tests for _score_level_quality() and for how its result is
    threaded into signal metadata (Level Quality Foundation v1).

    These test the pure scoring function and the metadata mapping
    directly, independent of the full analyze() pipeline - see
    DailyLevelsStrategyBaselineTests above for confirmation that
    adding this scoring did not change any of the 4 setups' behavior.
    """

    RESISTANCE = 105.0
    SUPPORT = 100.0

    def setUp(self) -> None:
        self.strategy = DailyLevelsStrategy()

    def test_single_touch_counts_as_one_reaction(self) -> None:
        """
        One near-resistance touch, validated by a pullback of at
        least 0.5% over the next 3 candles, counts as one reaction.
        """

        far_filler = [
            make_candle(95.0, 96.0, 94.0, 95.0, day_index=i)
            for i in range(5)
        ]

        touch = make_candle(
            95.0, self.RESISTANCE, 94.0, 95.0, day_index=5,
        )

        pullback = [
            make_candle(103.0, 103.5, 103.0, 103.0, day_index=6 + i)
            for i in range(3)
        ]

        reference_candles = far_filler + [touch] + pullback

        quality = self.strategy._score_level_quality(
            reference_candles=reference_candles,
            level_price=self.RESISTANCE,
            level_side="resistance",
        )

        self.assertEqual(quality.reaction_count, 1)
        self.assertEqual(quality.false_break_count, 0)
        self.assertGreaterEqual(quality.max_reaction_percent, 1.0)

        # 20 (1 valid reaction) + 10 (max deviation >= 1%).
        self.assertEqual(quality.score, 30.0)

    def test_consecutive_touches_count_as_one_reaction(self) -> None:
        """
        Several consecutive near-resistance candles merge into a
        single reaction, not one reaction per touching candle.
        """

        far_filler = [
            make_candle(95.0, 96.0, 94.0, 95.0, day_index=i)
            for i in range(2)
        ]

        touches = [
            make_candle(
                95.0, self.RESISTANCE, 94.0, 95.0, day_index=2 + i,
            )
            for i in range(3)
        ]

        pullback = [
            make_candle(103.0, 103.5, 103.0, 103.0, day_index=5 + i)
            for i in range(3)
        ]

        reference_candles = far_filler + touches + pullback

        quality = self.strategy._score_level_quality(
            reference_candles=reference_candles,
            level_price=self.RESISTANCE,
            level_side="resistance",
        )

        self.assertEqual(quality.reaction_count, 1)

    def test_touches_separated_by_gap_count_as_two_reactions(
        self,
    ) -> None:
        """
        Two near-resistance touches separated by at least
        reaction_gap_candles (2) non-near candles count as two
        distinct reactions.
        """

        far_filler = [
            make_candle(95.0, 96.0, 94.0, 95.0, day_index=0),
        ]

        touch_a = make_candle(
            95.0, self.RESISTANCE, 94.0, 95.0, day_index=1,
        )

        pullback_a = [
            make_candle(103.0, 103.5, 103.0, 103.0, day_index=2 + i)
            for i in range(3)
        ]

        touch_b = make_candle(
            95.0, self.RESISTANCE, 94.0, 95.0, day_index=5,
        )

        pullback_b = [
            make_candle(103.0, 103.5, 103.0, 103.0, day_index=6 + i)
            for i in range(3)
        ]

        reference_candles = (
            far_filler
            + [touch_a]
            + pullback_a
            + [touch_b]
            + pullback_b
        )

        quality = self.strategy._score_level_quality(
            reference_candles=reference_candles,
            level_price=self.RESISTANCE,
            level_side="resistance",
        )

        self.assertEqual(quality.reaction_count, 2)

        # 2 reactions * 20 + 10 (max deviation >= 1%, still < 2%).
        self.assertEqual(quality.score, 50.0)

    def test_false_breakout_increments_false_break_count(self) -> None:
        """
        A resistance false break (high clears tolerance, close ends
        back below the level) is counted, not treated as a reaction.
        """

        far_filler = [
            make_candle(95.0, 96.0, 94.0, 95.0, day_index=i)
            for i in range(4)
        ]

        false_break = make_candle(
            open_price=104.5,
            high=105.3,
            low=103.8,
            close=104.0,
            day_index=4,
        )

        reference_candles = far_filler + [false_break]

        quality = self.strategy._score_level_quality(
            reference_candles=reference_candles,
            level_price=self.RESISTANCE,
            level_side="resistance",
        )

        self.assertEqual(quality.reaction_count, 0)
        self.assertEqual(quality.false_break_count, 1)

        # 10 (1 false break), no reactions, no deviation bonus.
        self.assertEqual(quality.score, 10.0)

    def test_false_breakdown_increments_false_break_count(self) -> None:
        """
        A support false break (low clears tolerance, close ends back
        above the level) is counted, not treated as a reaction.
        """

        far_filler = [
            make_candle(105.0, 106.0, 104.0, 105.0, day_index=i)
            for i in range(4)
        ]

        false_break = make_candle(
            open_price=100.2,
            high=101.0,
            low=99.8,
            close=100.5,
            day_index=4,
        )

        reference_candles = far_filler + [false_break]

        quality = self.strategy._score_level_quality(
            reference_candles=reference_candles,
            level_price=self.SUPPORT,
            level_side="support",
        )

        self.assertEqual(quality.reaction_count, 0)
        self.assertEqual(quality.false_break_count, 1)
        self.assertEqual(quality.score, 10.0)

    def test_metadata_uses_resistance_score_for_resistance_setups(
        self,
    ) -> None:
        """
        A resistance-side setup (breakout/false breakout) reports
        resistance_quality as level_score, while still exposing both
        sides via daily_support_score/daily_resistance_score.
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
            is_large_bar_approach=False,
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

        self.assertEqual(metadata["level_score"], 80.0)
        self.assertEqual(metadata["level_reaction_count"], 2)
        self.assertEqual(metadata["level_false_break_count"], 1)
        self.assertEqual(metadata["level_max_reaction_percent"], 2.5)
        self.assertEqual(metadata["daily_resistance_score"], 80.0)
        self.assertEqual(metadata["daily_support_score"], 10.0)
        self.assertEqual(metadata["level_quality_version"], "v1")

    def test_metadata_uses_support_score_for_support_setups(
        self,
    ) -> None:
        """
        A support-side setup (breakdown/false breakdown) reports
        support_quality as level_score, while still exposing both
        sides via daily_support_score/daily_resistance_score.
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
            is_large_bar_approach=False,
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

        self.assertEqual(metadata["level_score"], 10.0)
        self.assertEqual(metadata["daily_resistance_score"], 80.0)
        self.assertEqual(metadata["daily_support_score"], 10.0)


if __name__ == "__main__":
    unittest.main()
