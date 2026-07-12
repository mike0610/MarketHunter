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
from strategies.daily_levels import (
    DailyLevelsStrategy,
    LevelApproachContext,
    LevelQuality,
)


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


def build_candles_with_approach(
    signal_candle: Candle,
    approach_candles: list[Candle],
    resistance: float = RESISTANCE,
    support: float = SUPPORT,
) -> list[Candle]:
    """
    Build a full 63-candle window like build_candles(), but with the
    last 4 reference candles replaced by approach_candles - the ones
    _score_level_approach() reads. The remaining 56 reference candles
    are still the uniform filler that pins resistance/support, so
    approach_candles must keep every high <= resistance and every low
    >= support to avoid shifting the level itself. The last candle in
    approach_candles doubles as previous_candle (candles[-3]).
    """

    lead_padding = make_candle(
        open_price=(resistance + support) / 2,
        high=resistance,
        low=support,
        close=(resistance + support) / 2,
        day_index=0,
    )

    far_filler = make_reference_candles(
        count=56,
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

    return (
        [lead_padding]
        + far_filler
        + approach_candles
        + [signal_candle, trailing_padding]
    )


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
        )

        self.assertEqual(metadata["level_score"], 10.0)
        self.assertEqual(metadata["daily_resistance_score"], 80.0)
        self.assertEqual(metadata["daily_support_score"], 10.0)


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
        )

        self.assertEqual(metadata["approach_bar_count"], 4)
        self.assertTrue(metadata["approach_is_compression"])
        self.assertFalse(metadata["approach_is_large_bar"])
        self.assertTrue(metadata["daily_support_is_compression"])
        self.assertFalse(metadata["daily_resistance_is_compression"])


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
        """

        signal_candle = make_candle(
            104.5, 106.0, 103.5, 104.0, day_index=61,
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
