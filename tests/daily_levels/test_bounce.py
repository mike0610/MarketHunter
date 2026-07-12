"""
MarketHunter

Tests for Daily Level Bounce v1: two new setups
(daily_support_bounce / daily_resistance_bounce) appended after all
four existing detectors in the or-chain.
"""

from __future__ import annotations

import unittest

from strategies.daily_levels import DailyLevelsStrategy

from .helpers import (
    build_candles,
    build_candles_with_approach,
    make_candle,
    make_snapshot,
)


class DailyLevelsBounceTests(unittest.IsolatedAsyncioTestCase):
    """
    Tests for Daily Level Bounce v1: two new setups
    (daily_support_bounce / daily_resistance_bounce) appended after
    all four existing detectors in the or-chain, so their priority
    and behavior stay untouched.

    A bounce only fires on a shallow touch (inside the same 0.15%
    buffer used by the breakout/sweep detectors - a deeper
    penetration is left to the false-break detectors above this one
    in the priority chain), with a decisive rejection close, and only
    while the level's approach shows no compression (compression
    instead favors a breakout).

    Note: level_name for both bounce setups is reported as
    "daily_support"/"daily_resistance" (matching the convention used
    by all four existing setups), not the literal "support"/
    "resistance" strings from the task spec prose - _metadata()
    selects which side's LevelQuality/LevelApproachContext to report
    by checking `level_name == "daily_resistance"`, so keeping this
    convention is required for that dispatch to stay correct.
    """

    RESISTANCE = 105.0
    SUPPORT = 100.0

    def setUp(self) -> None:
        self.strategy = DailyLevelsStrategy()

    async def test_support_bounce_creates_long(self) -> None:
        """
        A shallow dip into support that closes back above it with a
        decisive bullish close is a LONG daily_support_bounce.
        """

        signal_candle = make_candle(
            99.9, 101.0, 99.9, 100.7, day_index=61,
        )

        snapshot = make_snapshot(
            build_candles(signal_candle),
        )

        signal = await self.strategy.analyze(snapshot)

        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, "LONG")
        self.assertEqual(
            signal.metadata["setup_type"], "daily_support_bounce",
        )
        # base 70 + 3 (rejection >= 0.5%), no large-bar, no extreme close.
        self.assertEqual(signal.score, 73.0)
        self.assertEqual(signal.metadata["bounce_context"], "neutral")
        self.assertIn(
            "Daily support bounce confirmed by bullish rejection close",
            signal.reasons,
        )

    async def test_resistance_bounce_creates_short(self) -> None:
        """
        A shallow poke into resistance that closes back below it with
        a decisive bearish close is a SHORT daily_resistance_bounce.
        """

        signal_candle = make_candle(
            104.9, 105.1, 104.0, 104.3, day_index=61,
        )

        snapshot = make_snapshot(
            build_candles(signal_candle),
        )

        signal = await self.strategy.analyze(snapshot)

        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, "SHORT")
        self.assertEqual(
            signal.metadata["setup_type"], "daily_resistance_bounce",
        )
        # base 70 + 3 (rejection >= 0.5%), no large-bar, no extreme close.
        self.assertEqual(signal.score, 73.0)
        self.assertEqual(signal.metadata["bounce_context"], "neutral")
        self.assertIn(
            "Daily resistance bounce confirmed by bearish rejection close",
            signal.reasons,
        )

    async def test_compression_blocks_support_bounce(self) -> None:
        """
        An otherwise-valid support bounce candle does not fire while
        support_approach reports compression - compression toward the
        level favors a breakout instead, and no other setup matches
        this shallow a touch either.
        """

        approach_candles = [
            make_candle(104.0, 104.5, 102.5, 104.0, day_index=57),
            make_candle(102.5, 103.2, 101.5, 102.5, day_index=58),
            make_candle(101.3, 101.9, 100.7, 101.3, day_index=59),
            make_candle(100.4, 100.8, 100.1, 100.4, day_index=60),
        ]

        signal_candle = make_candle(
            99.9, 101.0, 99.9, 100.7, day_index=61,
        )

        snapshot = make_snapshot(
            build_candles_with_approach(signal_candle, approach_candles),
        )

        signal = await self.strategy.analyze(snapshot)

        self.assertIsNone(signal)

    async def test_compression_blocks_resistance_bounce(self) -> None:
        """
        An otherwise-valid resistance bounce candle does not fire
        while resistance_approach reports compression.
        """

        approach_candles = [
            make_candle(101.0, 102.0, 100.5, 101.0, day_index=57),
            make_candle(102.5, 103.2, 101.8, 102.5, day_index=58),
            make_candle(103.7, 104.1, 103.3, 103.7, day_index=59),
            make_candle(104.6, 104.9, 104.3, 104.6, day_index=60),
        ]

        signal_candle = make_candle(
            104.9, 105.1, 104.0, 104.3, day_index=61,
        )

        snapshot = make_snapshot(
            build_candles_with_approach(signal_candle, approach_candles),
        )

        signal = await self.strategy.analyze(snapshot)

        self.assertIsNone(signal)

    async def test_deep_penetration_goes_to_false_break_not_bounce(
        self,
    ) -> None:
        """
        A low that clears the 0.15% buffer by a wide margin falls
        outside the bounce detector's own low bound and is instead
        classified by the (higher-priority) false-break detector.
        """

        signal_candle = make_candle(
            100.5, 103.0, 99.0, 101.0, day_index=61,
        )

        snapshot = make_snapshot(
            build_candles(signal_candle),
        )

        signal = await self.strategy.analyze(snapshot)

        self.assertIsNotNone(signal)
        self.assertEqual(
            signal.metadata["setup_type"], "daily_false_breakdown",
        )
        self.assertNotEqual(
            signal.metadata["setup_type"], "daily_support_bounce",
        )

    async def test_weak_close_position_does_not_create_bounce(
        self,
    ) -> None:
        """
        A shallow, otherwise-valid touch of support with a close
        sitting low in the candle's own range (close_position < 60%)
        fails to confirm and no setup fires.
        """

        signal_candle = make_candle(
            99.9, 101.5, 99.9, 100.2, day_index=61,
        )

        snapshot = make_snapshot(
            build_candles(signal_candle),
        )

        signal = await self.strategy.analyze(snapshot)

        self.assertIsNone(signal)

    async def test_large_bar_approach_adds_bonus_to_support_bounce(
        self,
    ) -> None:
        """
        A large-range final approach candle sitting at support adds a
        +4 bounce bonus, isolated from the rejection/extreme-close
        bonuses by keeping rejection < 0.5% and close_position < 75%.
        """

        approach_candles = [
            make_candle(104.0, 104.5, 103.5, 104.0, day_index=57),
            make_candle(103.8, 104.3, 103.3, 103.8, day_index=58),
            make_candle(103.6, 104.1, 103.1, 103.6, day_index=59),
            make_candle(100.4, 104.0, 100.0, 100.4, day_index=60),
        ]

        signal_candle = make_candle(
            99.95, 100.40, 99.90, 100.22, day_index=61,
        )

        snapshot = make_snapshot(
            build_candles_with_approach(signal_candle, approach_candles),
        )

        signal = await self.strategy.analyze(snapshot)

        self.assertIsNotNone(signal)
        self.assertEqual(
            signal.metadata["setup_type"], "daily_support_bounce",
        )
        self.assertEqual(signal.score, 74.0)
        self.assertEqual(signal.metadata["bounce_context"], "large_bar")
        self.assertEqual(
            signal.metadata["bounce_score_adjustment"], 4.0,
        )
        self.assertIn(
            "Large-bar approach supports rejection from level",
            signal.reasons,
        )

    async def test_strong_rejection_and_extreme_close_get_bonuses(
        self,
    ) -> None:
        """
        A rejection >= 0.5% away from support combined with a close
        sitting in the extreme (>= 75%) part of the candle's own
        range earns both bonuses on top of the base score.
        """

        signal_candle = make_candle(
            99.95, 100.45, 99.86, 100.40, day_index=61,
        )

        snapshot = make_snapshot(
            build_candles(signal_candle),
        )

        signal = await self.strategy.analyze(snapshot)

        self.assertIsNotNone(signal)
        self.assertEqual(
            signal.metadata["setup_type"], "daily_support_bounce",
        )
        self.assertGreaterEqual(
            signal.metadata["bounce_rejection_percent"], 0.5,
        )
        self.assertGreaterEqual(
            signal.metadata["bounce_close_position_percent"], 75.0,
        )
        # base 70 + 3 (rejection) + 3 (extreme close), no large-bar.
        self.assertEqual(signal.score, 76.0)
        self.assertEqual(
            signal.metadata["bounce_score_adjustment"], 6.0,
        )

    async def test_normal_breakout_is_unaffected(self) -> None:
        """
        Daily Level Bounce v1 is appended after all four existing
        detectors, so a plain breakout still fires exactly as before,
        with bounce metadata simply marked not_applicable.
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
        self.assertEqual(
            signal.metadata["bounce_context"], "not_applicable",
        )
        self.assertEqual(
            signal.metadata["bounce_score_adjustment"], 0.0,
        )

    async def test_bounce_setup_metadata_is_populated_correctly(
        self,
    ) -> None:
        """
        A firing support bounce reports the full bounce_* metadata
        contract, including the version marker.
        """

        signal_candle = make_candle(
            99.9, 101.0, 99.9, 100.7, day_index=61,
        )

        snapshot = make_snapshot(
            build_candles(signal_candle),
        )

        signal = await self.strategy.analyze(snapshot)

        self.assertIsNotNone(signal)
        self.assertEqual(signal.metadata["level_name"], "daily_support")
        self.assertEqual(signal.metadata["bounce_context"], "neutral")
        self.assertGreaterEqual(
            signal.metadata["bounce_rejection_percent"], 0.5,
        )
        self.assertGreater(
            signal.metadata["bounce_close_position_percent"], 60.0,
        )
        self.assertEqual(
            signal.metadata["bounce_score_adjustment"], 3.0,
        )
        self.assertEqual(
            signal.metadata["bounce_context_version"], "v1",
        )


if __name__ == "__main__":
    unittest.main()
