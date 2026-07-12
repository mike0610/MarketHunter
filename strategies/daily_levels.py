"""
MarketHunter

strategies/daily_levels.py

Daily Levels Strategy

Rules:
- 1D only;
- levels only;
- breakout / breakdown;
- false breakout / false breakdown;
- daily close confirmation;
- no indicators.
"""

from __future__ import annotations

from dataclasses import dataclass

from models.candle import Candle
from models.market_snapshot import MarketSnapshot
from models.signal import Signal
from strategies.base_strategy import BaseStrategy


@dataclass(slots=True)
class DailyLevelSetup:
    """
    Internal setup description for one daily level signal.
    """

    direction: str
    setup_type: str
    level_name: str
    level_price: float
    score: float
    reasons: list[str]
    metadata: dict


@dataclass(slots=True)
class LevelQuality:
    """
    Level Quality Foundation v1 - result of scoring how strong one
    daily level (support or resistance) looks, based only on past
    reactions and false breaks inside the reference window.

    This score is observation-only in v1: it never blocks a signal,
    never changes signal.score, never changes setup priority, and
    never changes the existing 0.15% / 3% / 8% thresholds.
    """

    score: float
    reaction_count: int
    false_break_count: int
    max_reaction_percent: float


@dataclass(slots=True)
class LevelApproachContext:
    """
    Approach Context v1 - result of scoring how price approached one
    daily level (support or resistance) over the last few reference
    candles, i.e. only candles known before the trigger candle.

    Consecutive closes drifting closer to the level while candle
    ranges shrink ("pidzhattia"/compression) tend to precede a real
    breakout. A single large-range candle already sitting near the
    level tends to signal exhaustion instead.

    This context is observation-only in v1: it never blocks a
    signal, never changes signal.score, never changes setup
    priority, and never changes the existing 0.15% / 3% / 8%
    thresholds.
    """

    bar_count: int
    closer_close_count: int
    smaller_range_count: int
    distance_reduction_percent: float
    range_reduction_percent: float
    is_compression: bool
    is_large_bar_approach: bool


@dataclass(frozen=True)
class FalseBreakContext:
    """
    Confirmed false breakout v2 - result of scoring how decisively a
    false breakout/false breakdown candle rejected the level: how far
    it pierced past the level (penetration), how far the close
    reclaimed back inside the level (reclaim), and where the close
    sits within the candle's own high-low range (close_position).

    Not every legacy false break is equally good: a confirmed one
    needs a real penetration, a real reclaim, and a decisive close in
    the direction of the rejection. A false break that fails
    confirmation still fires under the legacy setup_type, unchanged.
    """

    penetration_percent: float
    reclaim_percent: float
    close_position_percent: float
    is_confirmed: bool


@dataclass(frozen=True)
class MTFEntryConfirmation:
    """
    1D level -> 1h Confirmation Context v1 - result of checking
    whether the last two CLOSED entry-timeframe (1h) candles confirm
    the daily setup that just fired.

    entry_candles[-2] is treated as the confirmation candle and
    entry_candles[-3] as the prior candle; the most recent
    entry_candles[-1] is treated as potentially unclosed and is
    never read.

    This context is observation-only in v1: it never blocks a
    signal, never changes direction/score/setup_type/reasons, and
    Signal.metadata["mtf_entry_confirmation_applied"] stays False
    regardless of is_confirmed here.
    """

    expected_pattern: str
    confirmation_type: str
    analyzed_candle_count: int
    is_confirmed: bool
    touched_level: bool
    crossed_level: bool
    retested_level: bool
    penetration_percent: float
    distance_from_level_percent: float
    close_position_percent: float
    confirmation_candle_open_time: object | None


class DailyLevelsStrategy(BaseStrategy):
    """
    Daily levels strategy.

    This strategy intentionally avoids indicators. It only uses previous
    daily highs/lows and closed daily candles.

    The scanner must run this strategy on 1D only.
    """

    name = "DailyLevels"

    lookback_days = 60
    breakout_buffer_percent = 0.15
    sweep_buffer_percent = 0.15
    min_level_range_percent = 3.0
    max_estimated_stop_distance_percent = 8.0

    # Level Quality Foundation v1 - observation-only level scoring.
    level_tolerance_percent = 0.15
    reaction_gap_candles = 2
    reaction_validation_candles = 3
    reaction_validation_min_percent = 0.5
    level_score_reaction_points = 20.0
    level_score_max_reactions = 3
    level_score_false_break_points = 10.0
    level_score_max_false_breaks = 2
    level_score_deviation_bonus_percent_1 = 1.0
    level_score_deviation_bonus_percent_2 = 2.0
    level_score_deviation_bonus_points = 10.0
    level_score_cap = 100.0

    # Approach Context v1 - observation-only compression/large-bar
    # approach detection.
    level_approach_window = 4
    level_approach_max_distance_percent = 1.0
    level_approach_min_distance_reduction_percent = 50.0
    level_approach_min_range_reduction_percent = 20.0
    level_approach_min_smaller_range_count = 2
    level_approach_large_bar_multiplier = 1.5

    # Compression-aware breakout v1 - activates Approach Context v1
    # for the plain breakout/breakdown setups only. Confirmed
    # pre-breakout compression raises the score and cap; a large-bar
    # approach without compression instead applies a penalty.
    # Compression always takes priority over the large-bar penalty
    # when both are true.
    breakout_context_compression_bonus = 6.0
    breakout_context_compression_cap = 84.0
    breakout_context_large_bar_penalty = 4.0

    # Confirmed false breakout v2 - a confirmed false break needs a
    # real penetration past the level, a real reclaim back inside it,
    # and a decisive close in the rejection direction. A legacy false
    # break that fails confirmation still fires unchanged (weak).
    false_break_min_penetration_percent = 0.15
    false_break_min_reclaim_percent = 0.10
    false_break_max_close_position_percent = 40.0
    false_break_min_close_position_percent = 60.0
    false_break_confirmed_bonus = 6.0
    false_break_confirmed_cap = 85.0

    # Daily Level Bounce v1 - support/resistance rejection setups.
    # Checked after all four existing detectors in the or-chain, so
    # their priority and behavior stay untouched. A bounce only
    # fires when the touch stays inside the same 0.15% buffer used
    # by the breakout/sweep detectors (a deeper penetration is left
    # to the false-break detectors above this one) and the level
    # held with no compression on approach - compression instead
    # favors a breakout, not a bounce.
    bounce_base_score = 70.0
    bounce_large_bar_bonus = 4.0
    bounce_rejection_bonus = 3.0
    bounce_rejection_min_percent = 0.5
    bounce_extreme_close_bonus = 3.0
    bounce_extreme_close_long_percent = 75.0
    bounce_extreme_close_short_percent = 25.0
    bounce_min_close_position_long_percent = 60.0
    bounce_max_close_position_short_percent = 40.0
    bounce_score_cap = 80.0

    # MTF data contract v1 - observational delivery of entry-timeframe
    # candles alongside the primary 1D snapshot. Declaring these two
    # attributes plus analyze_with_entry_candles() is how Scanner
    # detects this strategy wants supplemental entry-timeframe data.
    # No trading logic reads entry_candles yet.
    entry_timeframe = "1h"
    entry_candle_limit = 200

    # 1D level -> 1h Confirmation Context v1 - observation-only
    # scoring of whether the last two CLOSED 1h entry candles confirm
    # the daily setup. Never blocks a signal, never changes its
    # direction/score/setup_type/reasons.
    mtf_confirmation_tolerance_percent = 0.15
    mtf_confirmation_breakout_threshold_percent = 0.05
    mtf_confirmation_close_position_long_percent = 60.0
    mtf_confirmation_close_position_short_percent = 40.0

    _MTF_EXPECTED_PATTERN_BY_SETUP_TYPE = {
        "daily_breakout": "continuation",
        "daily_breakout_compression": "continuation",
        "daily_breakdown": "continuation",
        "daily_breakdown_compression": "continuation",
        "daily_support_bounce": "bounce",
        "daily_resistance_bounce": "bounce",
        "daily_false_breakout": "false_break_reclaim",
        "daily_false_breakout_confirmed": "false_break_reclaim",
        "daily_false_breakdown": "false_break_reclaim",
        "daily_false_breakdown_confirmed": "false_break_reclaim",
    }

    def __init__(self) -> None:
        pass

    async def analyze(
        self,
        snapshot: MarketSnapshot,
    ) -> Signal | None:
        """
        Analyze daily levels.

        The latest candle may still be open on Binance. To keep the rule
        close-based, the strategy uses candles[-2] as the last closed candle.
        """

        candles = snapshot.candles

        if len(candles) < self.lookback_days + 3:
            return None

        signal_candle = candles[-2]
        previous_candle = candles[-3]

        reference_candles = candles[
            -(self.lookback_days + 2):-2
        ]

        if len(reference_candles) < self.lookback_days:
            return None

        resistance = max(
            candle.high
            for candle in reference_candles
        )

        support = min(
            candle.low
            for candle in reference_candles
        )

        if resistance <= 0 or support <= 0 or resistance <= support:
            return None

        level_range_percent = self._percent_distance(
            resistance,
            support,
        )

        if level_range_percent < self.min_level_range_percent:
            return None

        resistance_quality = self._score_level_quality(
            reference_candles=reference_candles,
            level_price=resistance,
            level_side="resistance",
        )

        support_quality = self._score_level_quality(
            reference_candles=reference_candles,
            level_price=support,
            level_side="support",
        )

        resistance_approach = self._score_level_approach(
            reference_candles=reference_candles,
            level_price=resistance,
            level_side="resistance",
        )

        support_approach = self._score_level_approach(
            reference_candles=reference_candles,
            level_price=support,
            level_side="support",
        )

        setup = (
            self._detect_false_breakout_short(
                signal_candle=signal_candle,
                previous_candle=previous_candle,
                resistance=resistance,
                support=support,
                level_range_percent=level_range_percent,
                resistance_quality=resistance_quality,
                support_quality=support_quality,
                resistance_approach=resistance_approach,
                support_approach=support_approach,
            )
            or self._detect_false_breakdown_long(
                signal_candle=signal_candle,
                previous_candle=previous_candle,
                resistance=resistance,
                support=support,
                level_range_percent=level_range_percent,
                resistance_quality=resistance_quality,
                support_quality=support_quality,
                resistance_approach=resistance_approach,
                support_approach=support_approach,
            )
            or self._detect_breakout_long(
                signal_candle=signal_candle,
                previous_candle=previous_candle,
                resistance=resistance,
                support=support,
                level_range_percent=level_range_percent,
                resistance_quality=resistance_quality,
                support_quality=support_quality,
                resistance_approach=resistance_approach,
                support_approach=support_approach,
            )
            or self._detect_breakdown_short(
                signal_candle=signal_candle,
                previous_candle=previous_candle,
                resistance=resistance,
                support=support,
                level_range_percent=level_range_percent,
                resistance_quality=resistance_quality,
                support_quality=support_quality,
                resistance_approach=resistance_approach,
                support_approach=support_approach,
            )
            or self._detect_support_bounce_long(
                signal_candle=signal_candle,
                previous_candle=previous_candle,
                resistance=resistance,
                support=support,
                level_range_percent=level_range_percent,
                resistance_quality=resistance_quality,
                support_quality=support_quality,
                resistance_approach=resistance_approach,
                support_approach=support_approach,
            )
            or self._detect_resistance_bounce_short(
                signal_candle=signal_candle,
                previous_candle=previous_candle,
                resistance=resistance,
                support=support,
                level_range_percent=level_range_percent,
                resistance_quality=resistance_quality,
                support_quality=support_quality,
                resistance_approach=resistance_approach,
                support_approach=support_approach,
            )
        )

        if setup is None:
            return None

        estimated_stop_reference = (
            support
            if setup.direction == "LONG"
            else resistance
        )

        estimated_stop_distance_percent = self._percent_distance(
            signal_candle.close,
            estimated_stop_reference,
        )

        if (
            estimated_stop_distance_percent
            > self.max_estimated_stop_distance_percent
        ):
            return None

        setup.metadata["estimated_stop_reference"] = round(
            estimated_stop_reference,
            8,
        )
        setup.metadata["estimated_stop_distance_percent"] = round(
            estimated_stop_distance_percent,
            4,
        )
        setup.metadata["max_estimated_stop_distance_percent"] = (
            self.max_estimated_stop_distance_percent
        )

        signal = Signal(
            symbol=snapshot.symbol,
            market="",
            timeframe="1d",
            strategy=self.name,
            direction=setup.direction,
            score=setup.score,
        )

        signal.reasons.extend(
            setup.reasons,
        )

        signal.metadata.update(
            setup.metadata,
        )

        return signal

    async def analyze_with_entry_candles(
        self,
        snapshot: MarketSnapshot,
        entry_candles: list[Candle],
    ) -> Signal | None:
        """
        MTF data contract v1 - observation-only entry-timeframe hook.

        Defers entirely to analyze(): direction, score, setup_type,
        and reasons are always identical to a plain analyze() call on
        the same snapshot. The only difference is that a firing
        signal also records how many entry-timeframe (1h) candles
        arrived alongside the primary 1D snapshot, so the data
        pipeline can be exercised end-to-end before any
        entry-timeframe trading logic is built on top of it.

        Timestamp alignment v1: entry_candles is filtered down to
        only the candles that opened strictly after the daily signal
        candle's own close_time (snapshot.candles[-2].close_time)
        before anything else - including confirmation scoring - ever
        sees it. Pre-close 1h candles can never confirm a daily
        setup that hadn't closed yet.
        """

        signal = await self.analyze(snapshot)

        if signal is None:
            return None

        daily_close_time = snapshot.candles[-2].close_time

        raw_entry_candle_count = len(entry_candles)

        aligned_entry_candles = self._entry_candles_after_daily_close(
            entry_candles,
            daily_close_time,
        )

        aligned_entry_candle_count = len(aligned_entry_candles)

        signal.metadata["mtf_context_version"] = "v1"
        signal.metadata["mtf_primary_timeframe"] = "1d"
        signal.metadata["mtf_entry_timeframe"] = self.entry_timeframe
        signal.metadata["mtf_entry_candle_count"] = (
            aligned_entry_candle_count
        )
        signal.metadata["mtf_entry_data_available"] = (
            aligned_entry_candle_count > 0
        )

        signal.metadata["mtf_entry_alignment_version"] = "v1"
        signal.metadata["mtf_entry_alignment_applied"] = True
        signal.metadata["mtf_daily_signal_close_time"] = (
            daily_close_time.isoformat()
        )
        signal.metadata["mtf_entry_raw_candle_count"] = (
            raw_entry_candle_count
        )
        signal.metadata["mtf_entry_aligned_candle_count"] = (
            aligned_entry_candle_count
        )
        signal.metadata["mtf_entry_discarded_candle_count"] = (
            raw_entry_candle_count - aligned_entry_candle_count
        )

        confirmation = self._score_mtf_entry_confirmation(
            signal, aligned_entry_candles,
        )

        signal.metadata["mtf_entry_expected_pattern"] = (
            confirmation.expected_pattern
        )
        signal.metadata["mtf_entry_confirmation_type"] = (
            confirmation.confirmation_type
        )
        signal.metadata["mtf_entry_confirmation_is_confirmed"] = (
            confirmation.is_confirmed
        )
        signal.metadata["mtf_entry_confirmation_analyzed_candles"] = (
            confirmation.analyzed_candle_count
        )
        signal.metadata["mtf_entry_confirmation_touched_level"] = (
            confirmation.touched_level
        )
        signal.metadata["mtf_entry_confirmation_crossed_level"] = (
            confirmation.crossed_level
        )
        signal.metadata["mtf_entry_confirmation_retested_level"] = (
            confirmation.retested_level
        )
        signal.metadata[
            "mtf_entry_confirmation_penetration_percent"
        ] = confirmation.penetration_percent
        signal.metadata["mtf_entry_confirmation_distance_percent"] = (
            confirmation.distance_from_level_percent
        )
        signal.metadata[
            "mtf_entry_confirmation_close_position_percent"
        ] = confirmation.close_position_percent
        signal.metadata["mtf_entry_confirmation_candle_open_time"] = (
            confirmation.confirmation_candle_open_time.isoformat()
            if confirmation.confirmation_candle_open_time is not None
            else None
        )
        signal.metadata["mtf_entry_confirmation_version"] = "v1"

        # Purely observational in v1: this stays False regardless of
        # confirmation.is_confirmed above - nothing yet acts on this
        # context.
        signal.metadata["mtf_entry_confirmation_applied"] = False

        return signal

    def _detect_breakout_long(
        self,
        signal_candle: Candle,
        previous_candle: Candle,
        resistance: float,
        support: float,
        level_range_percent: float,
        resistance_quality: LevelQuality,
        support_quality: LevelQuality,
        resistance_approach: LevelApproachContext,
        support_approach: LevelApproachContext,
    ) -> DailyLevelSetup | None:
        """
        LONG: daily candle closes above previous resistance.

        Compression-aware breakout v1: a confirmed pre-breakout
        compression (Approach Context v1) reclassifies this as
        daily_breakout_compression with a score bonus and a raised
        cap. Absent compression, a large-bar approach instead applies
        a score penalty. Compression always takes priority over the
        large-bar penalty when both are true.
        """

        close_distance = self._percent_distance(
            signal_candle.close,
            resistance,
        )

        if signal_candle.close <= self._above_level(
            resistance,
            self.breakout_buffer_percent,
        ):
            return None

        if previous_candle.close > resistance:
            return None

        score = 68.0

        if signal_candle.bullish:
            score += 4.0

        if signal_candle.open <= resistance:
            score += 3.0

        if close_distance >= 0.5:
            score += 3.0

        setup_type = "daily_breakout"
        score_cap = 78.0
        breakout_context = "neutral"
        breakout_context_score_adjustment = 0.0

        reasons = [
            "Daily close confirmed above previous resistance.",
            "Breakout is based only on 1D levels.",
            "No indicators used.",
        ]

        if resistance_approach.is_compression:
            setup_type = "daily_breakout_compression"
            breakout_context = "compression"
            breakout_context_score_adjustment = (
                self.breakout_context_compression_bonus
            )
            score += self.breakout_context_compression_bonus
            score_cap = self.breakout_context_compression_cap

            reasons.append(
                "Pre-breakout compression confirmed over 4 bars",
            )

        elif resistance_approach.is_large_bar_approach:
            breakout_context = "large_bar"
            breakout_context_score_adjustment = (
                -self.breakout_context_large_bar_penalty
            )
            score -= self.breakout_context_large_bar_penalty

            reasons.append(
                "Large-bar approach weakens breakout quality",
            )

        score = min(
            score,
            score_cap,
        )

        return DailyLevelSetup(
            direction="LONG",
            setup_type=setup_type,
            level_name="daily_resistance",
            level_price=resistance,
            score=score,
            reasons=reasons,
            metadata=self._metadata(
                setup_type=setup_type,
                level_name="daily_resistance",
                level_price=resistance,
                support=support,
                resistance=resistance,
                signal_candle=signal_candle,
                previous_candle=previous_candle,
                level_range_percent=level_range_percent,
                trigger_distance_percent=close_distance,
                resistance_quality=resistance_quality,
                support_quality=support_quality,
                resistance_approach=resistance_approach,
                support_approach=support_approach,
                breakout_context=breakout_context,
                breakout_context_score_adjustment=(
                    breakout_context_score_adjustment
                ),
                false_break_context="not_applicable",
                false_break_penetration_percent=0.0,
                false_break_reclaim_percent=0.0,
                false_break_close_position_percent=0.0,
                false_break_score_adjustment=0.0,
                bounce_context="not_applicable",
                bounce_rejection_percent=0.0,
                bounce_close_position_percent=0.0,
                bounce_score_adjustment=0.0,
            ),
        )

    def _detect_breakdown_short(
        self,
        signal_candle: Candle,
        previous_candle: Candle,
        resistance: float,
        support: float,
        level_range_percent: float,
        resistance_quality: LevelQuality,
        support_quality: LevelQuality,
        resistance_approach: LevelApproachContext,
        support_approach: LevelApproachContext,
    ) -> DailyLevelSetup | None:
        """
        SHORT: daily candle closes below previous support.

        Compression-aware breakout v1: mirrors _detect_breakout_long
        via support_approach. A confirmed pre-breakdown compression
        reclassifies this as daily_breakdown_compression with a score
        bonus and a raised cap. Absent compression, a large-bar
        approach instead applies a score penalty. Compression always
        takes priority over the large-bar penalty when both are true.
        """

        close_distance = self._percent_distance(
            signal_candle.close,
            support,
        )

        if signal_candle.close >= self._below_level(
            support,
            self.breakout_buffer_percent,
        ):
            return None

        if previous_candle.close < support:
            return None

        score = 68.0

        if signal_candle.bearish:
            score += 4.0

        if signal_candle.open >= support:
            score += 3.0

        if close_distance >= 0.5:
            score += 3.0

        setup_type = "daily_breakdown"
        score_cap = 78.0
        breakout_context = "neutral"
        breakout_context_score_adjustment = 0.0

        reasons = [
            "Daily close confirmed below previous support.",
            "Breakdown is based only on 1D levels.",
            "No indicators used.",
        ]

        if support_approach.is_compression:
            setup_type = "daily_breakdown_compression"
            breakout_context = "compression"
            breakout_context_score_adjustment = (
                self.breakout_context_compression_bonus
            )
            score += self.breakout_context_compression_bonus
            score_cap = self.breakout_context_compression_cap

            reasons.append(
                "Pre-breakdown compression confirmed over 4 bars",
            )

        elif support_approach.is_large_bar_approach:
            breakout_context = "large_bar"
            breakout_context_score_adjustment = (
                -self.breakout_context_large_bar_penalty
            )
            score -= self.breakout_context_large_bar_penalty

            reasons.append(
                "Large-bar approach weakens breakdown quality",
            )

        score = min(
            score,
            score_cap,
        )

        return DailyLevelSetup(
            direction="SHORT",
            setup_type=setup_type,
            level_name="daily_support",
            level_price=support,
            score=score,
            reasons=reasons,
            metadata=self._metadata(
                setup_type=setup_type,
                level_name="daily_support",
                level_price=support,
                support=support,
                resistance=resistance,
                signal_candle=signal_candle,
                previous_candle=previous_candle,
                level_range_percent=level_range_percent,
                trigger_distance_percent=close_distance,
                resistance_quality=resistance_quality,
                support_quality=support_quality,
                resistance_approach=resistance_approach,
                support_approach=support_approach,
                breakout_context=breakout_context,
                breakout_context_score_adjustment=(
                    breakout_context_score_adjustment
                ),
                false_break_context="not_applicable",
                false_break_penetration_percent=0.0,
                false_break_reclaim_percent=0.0,
                false_break_close_position_percent=0.0,
                false_break_score_adjustment=0.0,
                bounce_context="not_applicable",
                bounce_rejection_percent=0.0,
                bounce_close_position_percent=0.0,
                bounce_score_adjustment=0.0,
            ),
        )

    def _detect_false_breakout_short(
        self,
        signal_candle: Candle,
        previous_candle: Candle,
        resistance: float,
        support: float,
        level_range_percent: float,
        resistance_quality: LevelQuality,
        support_quality: LevelQuality,
        resistance_approach: LevelApproachContext,
        support_approach: LevelApproachContext,
    ) -> DailyLevelSetup | None:
        """
        SHORT: price sweeps resistance but daily candle closes back below it.

        Confirmed false breakout v2: a decisive rejection (real
        penetration past resistance, real reclaim back below it, and
        a close in the lower part of the candle) reclassifies this as
        daily_false_breakout_confirmed with a score bonus and a
        raised cap. A legacy false breakout that fails confirmation
        still fires as daily_false_breakout, unchanged.
        """

        sweep_distance = self._percent_distance(
            signal_candle.high,
            resistance,
        )

        if signal_candle.high <= self._above_level(
            resistance,
            self.sweep_buffer_percent,
        ):
            return None

        if signal_candle.close >= resistance:
            return None

        if previous_candle.close > resistance:
            return None

        score = 70.0

        if signal_candle.bearish:
            score += 4.0

        if signal_candle.close < signal_candle.open:
            score += 2.0

        if sweep_distance >= 0.5:
            score += 2.0

        setup_type = "daily_false_breakout"
        score_cap = 79.0
        false_break_context = "weak"
        false_break_score_adjustment = 0.0

        reasons = [
            "Daily candle swept previous resistance and closed back below it.",
            "False breakout is confirmed by daily close.",
            "No indicators used.",
        ]

        false_break = self._score_false_break_confirmation(
            signal_candle=signal_candle,
            level_price=resistance,
            level_side="resistance",
        )

        if false_break.is_confirmed:
            setup_type = "daily_false_breakout_confirmed"
            score_cap = self.false_break_confirmed_cap
            false_break_context = "confirmed"
            false_break_score_adjustment = self.false_break_confirmed_bonus
            score += self.false_break_confirmed_bonus

            reasons.append(
                "False breakout confirmed by decisive close below resistance",
            )

        score = min(
            score,
            score_cap,
        )

        return DailyLevelSetup(
            direction="SHORT",
            setup_type=setup_type,
            level_name="daily_resistance",
            level_price=resistance,
            score=score,
            reasons=reasons,
            metadata=self._metadata(
                setup_type=setup_type,
                level_name="daily_resistance",
                level_price=resistance,
                support=support,
                resistance=resistance,
                signal_candle=signal_candle,
                previous_candle=previous_candle,
                level_range_percent=level_range_percent,
                trigger_distance_percent=sweep_distance,
                resistance_quality=resistance_quality,
                support_quality=support_quality,
                resistance_approach=resistance_approach,
                support_approach=support_approach,
                breakout_context="not_applicable",
                breakout_context_score_adjustment=0.0,
                false_break_context=false_break_context,
                false_break_penetration_percent=(
                    false_break.penetration_percent
                ),
                false_break_reclaim_percent=false_break.reclaim_percent,
                false_break_close_position_percent=(
                    false_break.close_position_percent
                ),
                false_break_score_adjustment=false_break_score_adjustment,
                bounce_context="not_applicable",
                bounce_rejection_percent=0.0,
                bounce_close_position_percent=0.0,
                bounce_score_adjustment=0.0,
            ),
        )

    def _detect_false_breakdown_long(
        self,
        signal_candle: Candle,
        previous_candle: Candle,
        resistance: float,
        support: float,
        level_range_percent: float,
        resistance_quality: LevelQuality,
        support_quality: LevelQuality,
        resistance_approach: LevelApproachContext,
        support_approach: LevelApproachContext,
    ) -> DailyLevelSetup | None:
        """
        LONG: price sweeps support but daily candle closes back above it.

        Confirmed false breakout v2: mirrors _detect_false_breakout_short.
        A decisive rejection (real penetration past support, real
        reclaim back above it, and a close in the upper part of the
        candle) reclassifies this as daily_false_breakdown_confirmed
        with a score bonus and a raised cap. A legacy false breakdown
        that fails confirmation still fires as daily_false_breakdown,
        unchanged.
        """

        sweep_distance = self._percent_distance(
            signal_candle.low,
            support,
        )

        if signal_candle.low >= self._below_level(
            support,
            self.sweep_buffer_percent,
        ):
            return None

        if signal_candle.close <= support:
            return None

        if previous_candle.close < support:
            return None

        score = 70.0

        if signal_candle.bullish:
            score += 4.0

        if signal_candle.close > signal_candle.open:
            score += 2.0

        if sweep_distance >= 0.5:
            score += 2.0

        setup_type = "daily_false_breakdown"
        score_cap = 79.0
        false_break_context = "weak"
        false_break_score_adjustment = 0.0

        reasons = [
            "Daily candle swept previous support and closed back above it.",
            "False breakdown is confirmed by daily close.",
            "No indicators used.",
        ]

        false_break = self._score_false_break_confirmation(
            signal_candle=signal_candle,
            level_price=support,
            level_side="support",
        )

        if false_break.is_confirmed:
            setup_type = "daily_false_breakdown_confirmed"
            score_cap = self.false_break_confirmed_cap
            false_break_context = "confirmed"
            false_break_score_adjustment = self.false_break_confirmed_bonus
            score += self.false_break_confirmed_bonus

            reasons.append(
                "False breakdown confirmed by decisive close above support",
            )

        score = min(
            score,
            score_cap,
        )

        return DailyLevelSetup(
            direction="LONG",
            setup_type=setup_type,
            level_name="daily_support",
            level_price=support,
            score=score,
            reasons=reasons,
            metadata=self._metadata(
                setup_type=setup_type,
                level_name="daily_support",
                level_price=support,
                support=support,
                resistance=resistance,
                signal_candle=signal_candle,
                previous_candle=previous_candle,
                level_range_percent=level_range_percent,
                trigger_distance_percent=sweep_distance,
                resistance_quality=resistance_quality,
                support_quality=support_quality,
                resistance_approach=resistance_approach,
                support_approach=support_approach,
                breakout_context="not_applicable",
                breakout_context_score_adjustment=0.0,
                false_break_context=false_break_context,
                false_break_penetration_percent=(
                    false_break.penetration_percent
                ),
                false_break_reclaim_percent=false_break.reclaim_percent,
                false_break_close_position_percent=(
                    false_break.close_position_percent
                ),
                false_break_score_adjustment=false_break_score_adjustment,
                bounce_context="not_applicable",
                bounce_rejection_percent=0.0,
                bounce_close_position_percent=0.0,
                bounce_score_adjustment=0.0,
            ),
        )

    def _detect_support_bounce_long(
        self,
        signal_candle: Candle,
        previous_candle: Candle,
        resistance: float,
        support: float,
        level_range_percent: float,
        resistance_quality: LevelQuality,
        support_quality: LevelQuality,
        resistance_approach: LevelApproachContext,
        support_approach: LevelApproachContext,
    ) -> DailyLevelSetup | None:
        """
        LONG: daily candle rejects support from above and closes back
        into the range with a decisive bullish close.

        Daily Level Bounce v1: checked after all four existing
        detectors, so their priority is untouched. Only a touch that
        stays inside the same 0.15% buffer used by the breakout/sweep
        detectors qualifies here - a deeper penetration is left to
        the false-break detectors above this one in the priority
        chain. A bounce never fires while support_approach reports
        compression, since compression toward the level favors a
        breakout instead.
        """

        if previous_candle.close <= self._above_level(
            support,
            self.breakout_buffer_percent,
        ):
            return None

        if signal_candle.low > self._above_level(
            support,
            self.breakout_buffer_percent,
        ):
            return None

        if signal_candle.low < self._below_level(
            support,
            self.breakout_buffer_percent,
        ):
            return None

        if signal_candle.close <= support:
            return None

        if not signal_candle.bullish:
            return None

        if signal_candle.high <= signal_candle.low:
            return None

        close_position_percent = (
            (signal_candle.close - signal_candle.low)
            / (signal_candle.high - signal_candle.low)
            * 100
        )

        if (
            close_position_percent
            < self.bounce_min_close_position_long_percent
        ):
            return None

        if support_approach.is_compression:
            return None

        rejection_percent = (
            (signal_candle.close - signal_candle.low)
            / support
            * 100
        )

        score = self.bounce_base_score
        bounce_context = "neutral"
        bounce_score_adjustment = 0.0

        reasons = [
            "Daily support bounce confirmed by bullish rejection close",
        ]

        if support_approach.is_large_bar_approach:
            bounce_context = "large_bar"
            bounce_score_adjustment += self.bounce_large_bar_bonus
            score += self.bounce_large_bar_bonus

            reasons.append(
                "Large-bar approach supports rejection from level",
            )

        if rejection_percent >= self.bounce_rejection_min_percent:
            bounce_score_adjustment += self.bounce_rejection_bonus
            score += self.bounce_rejection_bonus

        if (
            close_position_percent
            >= self.bounce_extreme_close_long_percent
        ):
            bounce_score_adjustment += self.bounce_extreme_close_bonus
            score += self.bounce_extreme_close_bonus

        score = min(
            score,
            self.bounce_score_cap,
        )

        return DailyLevelSetup(
            direction="LONG",
            setup_type="daily_support_bounce",
            level_name="daily_support",
            level_price=support,
            score=score,
            reasons=reasons,
            metadata=self._metadata(
                setup_type="daily_support_bounce",
                level_name="daily_support",
                level_price=support,
                support=support,
                resistance=resistance,
                signal_candle=signal_candle,
                previous_candle=previous_candle,
                level_range_percent=level_range_percent,
                trigger_distance_percent=rejection_percent,
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
                bounce_context=bounce_context,
                bounce_rejection_percent=rejection_percent,
                bounce_close_position_percent=close_position_percent,
                bounce_score_adjustment=bounce_score_adjustment,
            ),
        )

    def _detect_resistance_bounce_short(
        self,
        signal_candle: Candle,
        previous_candle: Candle,
        resistance: float,
        support: float,
        level_range_percent: float,
        resistance_quality: LevelQuality,
        support_quality: LevelQuality,
        resistance_approach: LevelApproachContext,
        support_approach: LevelApproachContext,
    ) -> DailyLevelSetup | None:
        """
        SHORT: daily candle rejects resistance from below and closes
        back into the range with a decisive bearish close.

        Daily Level Bounce v1: mirrors _detect_support_bounce_long via
        resistance_approach. Checked after all four existing
        detectors, so their priority is untouched. Only a touch that
        stays inside the same 0.15% buffer used by the breakout/sweep
        detectors qualifies here - a deeper penetration is left to
        the false-break detectors above this one in the priority
        chain. A bounce never fires while resistance_approach reports
        compression, since compression toward the level favors a
        breakout instead.
        """

        if previous_candle.close >= self._below_level(
            resistance,
            self.breakout_buffer_percent,
        ):
            return None

        if signal_candle.high < self._below_level(
            resistance,
            self.breakout_buffer_percent,
        ):
            return None

        if signal_candle.high > self._above_level(
            resistance,
            self.breakout_buffer_percent,
        ):
            return None

        if signal_candle.close >= resistance:
            return None

        if not signal_candle.bearish:
            return None

        if signal_candle.high <= signal_candle.low:
            return None

        close_position_percent = (
            (signal_candle.close - signal_candle.low)
            / (signal_candle.high - signal_candle.low)
            * 100
        )

        if (
            close_position_percent
            > self.bounce_max_close_position_short_percent
        ):
            return None

        if resistance_approach.is_compression:
            return None

        rejection_percent = (
            (signal_candle.high - signal_candle.close)
            / resistance
            * 100
        )

        score = self.bounce_base_score
        bounce_context = "neutral"
        bounce_score_adjustment = 0.0

        reasons = [
            "Daily resistance bounce confirmed by bearish rejection close",
        ]

        if resistance_approach.is_large_bar_approach:
            bounce_context = "large_bar"
            bounce_score_adjustment += self.bounce_large_bar_bonus
            score += self.bounce_large_bar_bonus

            reasons.append(
                "Large-bar approach supports rejection from level",
            )

        if rejection_percent >= self.bounce_rejection_min_percent:
            bounce_score_adjustment += self.bounce_rejection_bonus
            score += self.bounce_rejection_bonus

        if (
            close_position_percent
            <= self.bounce_extreme_close_short_percent
        ):
            bounce_score_adjustment += self.bounce_extreme_close_bonus
            score += self.bounce_extreme_close_bonus

        score = min(
            score,
            self.bounce_score_cap,
        )

        return DailyLevelSetup(
            direction="SHORT",
            setup_type="daily_resistance_bounce",
            level_name="daily_resistance",
            level_price=resistance,
            score=score,
            reasons=reasons,
            metadata=self._metadata(
                setup_type="daily_resistance_bounce",
                level_name="daily_resistance",
                level_price=resistance,
                support=support,
                resistance=resistance,
                signal_candle=signal_candle,
                previous_candle=previous_candle,
                level_range_percent=level_range_percent,
                trigger_distance_percent=rejection_percent,
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
                bounce_context=bounce_context,
                bounce_rejection_percent=rejection_percent,
                bounce_close_position_percent=close_position_percent,
                bounce_score_adjustment=bounce_score_adjustment,
            ),
        )

    def _metadata(
        self,
        setup_type: str,
        level_name: str,
        level_price: float,
        support: float,
        resistance: float,
        signal_candle: Candle,
        previous_candle: Candle,
        level_range_percent: float,
        trigger_distance_percent: float,
        resistance_quality: LevelQuality,
        support_quality: LevelQuality,
        resistance_approach: LevelApproachContext,
        support_approach: LevelApproachContext,
        breakout_context: str,
        breakout_context_score_adjustment: float,
        false_break_context: str,
        false_break_penetration_percent: float,
        false_break_reclaim_percent: float,
        false_break_close_position_percent: float,
        false_break_score_adjustment: float,
        bounce_context: str,
        bounce_rejection_percent: float,
        bounce_close_position_percent: float,
        bounce_score_adjustment: float,
    ) -> dict:
        """
        Build metadata for scan journal and research trade storage.
        """

        level_quality = (
            resistance_quality
            if level_name == "daily_resistance"
            else support_quality
        )

        level_approach = (
            resistance_approach
            if level_name == "daily_resistance"
            else support_approach
        )

        return {
            "strategy_family": "daily_levels",
            "setup_type": setup_type,
            "level_name": level_name,
            "level_price": level_price,
            "daily_support": support,
            "daily_resistance": resistance,
            "lookback_days": self.lookback_days,
            "intended_timeframe": "1d",
            "level_range_percent": round(
                level_range_percent,
                4,
            ),
            "trigger_distance_percent": round(
                trigger_distance_percent,
                4,
            ),
            "signal_candle_open_time": signal_candle.open_time.isoformat(),
            "previous_candle_open_time": previous_candle.open_time.isoformat(),
            "confirmation": "daily_close",
            "uses_indicators": False,
            "level_score": level_quality.score,
            "level_reaction_count": level_quality.reaction_count,
            "level_false_break_count": level_quality.false_break_count,
            "level_max_reaction_percent": level_quality.max_reaction_percent,
            "daily_support_score": support_quality.score,
            "daily_resistance_score": resistance_quality.score,
            "level_quality_version": "v1",
            "approach_bar_count": level_approach.bar_count,
            "approach_closer_close_count": level_approach.closer_close_count,
            "approach_smaller_range_count": level_approach.smaller_range_count,
            "approach_distance_reduction_percent": level_approach.distance_reduction_percent,
            "approach_range_reduction_percent": level_approach.range_reduction_percent,
            "approach_is_compression": level_approach.is_compression,
            "approach_is_large_bar": level_approach.is_large_bar_approach,
            "approach_context_version": "v1",
            "daily_support_is_compression": support_approach.is_compression,
            "daily_resistance_is_compression": resistance_approach.is_compression,
            "breakout_context": breakout_context,
            "breakout_context_score_adjustment": (
                breakout_context_score_adjustment
            ),
            "breakout_context_version": "v1",
            "false_break_context": false_break_context,
            "false_break_penetration_percent": round(
                false_break_penetration_percent,
                4,
            ),
            "false_break_reclaim_percent": round(
                false_break_reclaim_percent,
                4,
            ),
            "false_break_close_position_percent": round(
                false_break_close_position_percent,
                4,
            ),
            "false_break_score_adjustment": false_break_score_adjustment,
            "false_break_context_version": "v2",
            "bounce_context": bounce_context,
            "bounce_rejection_percent": round(
                bounce_rejection_percent,
                4,
            ),
            "bounce_close_position_percent": round(
                bounce_close_position_percent,
                4,
            ),
            "bounce_score_adjustment": bounce_score_adjustment,
            "bounce_context_version": "v1",
        }

    def _score_level_quality(
        self,
        reference_candles: list[Candle],
        level_price: float,
        level_side: str,
    ) -> LevelQuality:
        """
        Level Quality Foundation v1.

        Score how strong one daily level looks, using only past
        reactions and false breaks inside reference_candles:
        - a candle is "near" the level if its touch price (high for
          resistance, low for support) sits within
          level_tolerance_percent of level_price;
        - consecutive near candles count as ONE reaction;
        - a new reaction only starts after at least
          reaction_gap_candles candles outside tolerance since the
          previous reaction ended;
        - a reaction is valid if, within the next
          reaction_validation_candles candles, price moved away from
          the level by at least reaction_validation_min_percent;
        - a false break is a candle whose touch price clears
          tolerance on the wrong side but whose close ends back on
          the level's side.

        This score is observation-only: it is attached to signal
        metadata but does not affect which setup fires, signal.score,
        setup priority, or any existing threshold.
        """

        is_resistance = level_side == "resistance"

        tolerance = level_price * (
            self.level_tolerance_percent / 100
        )

        reaction_ends = self._group_reaction_ends(
            reference_candles=reference_candles,
            level_price=level_price,
            tolerance=tolerance,
            is_resistance=is_resistance,
        )

        reaction_count = 0
        max_reaction_percent = 0.0

        for end_index in reaction_ends:
            deviation_percent = self._reaction_deviation_percent(
                reference_candles=reference_candles,
                end_index=end_index,
                level_price=level_price,
                is_resistance=is_resistance,
            )

            if deviation_percent >= self.reaction_validation_min_percent:
                reaction_count += 1

                max_reaction_percent = max(
                    max_reaction_percent,
                    deviation_percent,
                )

        false_break_count = sum(
            1
            for candle in reference_candles
            if self._is_false_break(
                candle=candle,
                level_price=level_price,
                tolerance=tolerance,
                is_resistance=is_resistance,
            )
        )

        score = 0.0

        score += min(
            reaction_count,
            self.level_score_max_reactions,
        ) * self.level_score_reaction_points

        score += min(
            false_break_count,
            self.level_score_max_false_breaks,
        ) * self.level_score_false_break_points

        if max_reaction_percent >= self.level_score_deviation_bonus_percent_1:
            score += self.level_score_deviation_bonus_points

        if max_reaction_percent >= self.level_score_deviation_bonus_percent_2:
            score += self.level_score_deviation_bonus_points

        score = min(
            score,
            self.level_score_cap,
        )

        return LevelQuality(
            score=score,
            reaction_count=reaction_count,
            false_break_count=false_break_count,
            max_reaction_percent=round(
                max_reaction_percent,
                4,
            ),
        )

    def _group_reaction_ends(
        self,
        reference_candles: list[Candle],
        level_price: float,
        tolerance: float,
        is_resistance: bool,
    ) -> list[int]:
        """
        Return the end index (inside reference_candles) of each
        merged reaction.

        Consecutive near candles extend the current reaction. A near
        candle that follows fewer than reaction_gap_candles non-near
        candles since the previous reaction also merges into it,
        rather than starting a new reaction.
        """

        reaction_ends: list[int] = []

        in_reaction = False
        gap_since_last_reaction = self.reaction_gap_candles

        for index, candle in enumerate(reference_candles):
            near = self._is_near_level(
                candle=candle,
                level_price=level_price,
                tolerance=tolerance,
                is_resistance=is_resistance,
            )

            if not near:
                in_reaction = False
                gap_since_last_reaction += 1
                continue

            starts_new_reaction = (
                not reaction_ends
                or (
                    not in_reaction
                    and gap_since_last_reaction
                    >= self.reaction_gap_candles
                )
            )

            if starts_new_reaction:
                reaction_ends.append(index)
            else:
                reaction_ends[-1] = index

            in_reaction = True
            gap_since_last_reaction = 0

        return reaction_ends

    def _reaction_deviation_percent(
        self,
        reference_candles: list[Candle],
        end_index: int,
        level_price: float,
        is_resistance: bool,
    ) -> float:
        """
        Return how far (in percent) price moved away from the level
        within reaction_validation_candles candles following
        end_index. Movement back toward or through the level
        contributes zero, never a negative deviation.
        """

        max_deviation = 0.0

        follow_up_candles = reference_candles[
            end_index + 1:
            end_index + 1 + self.reaction_validation_candles
        ]

        for candle in follow_up_candles:
            away_price = (
                candle.low
                if is_resistance
                else candle.high
            )

            if is_resistance:
                deviation = (
                    level_price
                    - away_price
                ) / level_price * 100

            else:
                deviation = (
                    away_price
                    - level_price
                ) / level_price * 100

            max_deviation = max(
                max_deviation,
                deviation,
            )

        return max_deviation

    @staticmethod
    def _is_near_level(
        candle: Candle,
        level_price: float,
        tolerance: float,
        is_resistance: bool,
    ) -> bool:
        """
        Return True when the candle's touch price sits within
        tolerance of the level.
        """

        touch_price = (
            candle.high
            if is_resistance
            else candle.low
        )

        return abs(
            touch_price - level_price
        ) <= tolerance

    @staticmethod
    def _is_false_break(
        candle: Candle,
        level_price: float,
        tolerance: float,
        is_resistance: bool,
    ) -> bool:
        """
        Return True when the candle clears the level by more than
        tolerance on the wrong side, but closes back on the level's
        side.
        """

        if is_resistance:
            return (
                candle.high > level_price + tolerance
                and candle.close < level_price
            )

        return (
            candle.low < level_price - tolerance
            and candle.close > level_price
        )

    def _score_level_approach(
        self,
        reference_candles: list[Candle],
        level_price: float,
        level_side: str,
        window: int | None = None,
    ) -> LevelApproachContext:
        """
        Approach Context v1.

        Score how price approached one daily level over the last
        `window` reference candles (default level_approach_window),
        i.e. only candles known before the trigger candle:
        - distance to the level is measured from each candle's
          close, on the approach side only (below resistance, above
          support);
        - candle size is measured as (high - low) / close;
        - is_compression is True when all window closes stay on the
          approach side, the last close is within
          level_approach_max_distance_percent of the level, every
          consecutive close is strictly closer to the level than the
          previous one, at least level_approach_min_smaller_range_count
          consecutive candle ranges shrink, distance to the level
          dropped by at least level_approach_min_distance_reduction_percent,
          and candle range dropped by at least
          level_approach_min_range_reduction_percent;
        - is_large_bar_approach is True when the last candle sits
          within level_approach_max_distance_percent of the level and
          its range is at least level_approach_large_bar_multiplier
          times the median range of the preceding candles in the
          window.

        This context is observation-only: it is attached to signal
        metadata but does not affect which setup fires, signal.score,
        setup priority, or any existing threshold.
        """

        window = window or self.level_approach_window

        is_resistance = level_side == "resistance"

        analyzed_candles = reference_candles[-window:]

        if len(analyzed_candles) < window:
            return LevelApproachContext(
                bar_count=len(analyzed_candles),
                closer_close_count=0,
                smaller_range_count=0,
                distance_reduction_percent=0.0,
                range_reduction_percent=0.0,
                is_compression=False,
                is_large_bar_approach=False,
            )

        distances = [
            self._approach_distance_percent(
                candle=candle,
                level_price=level_price,
                is_resistance=is_resistance,
            )
            for candle in analyzed_candles
        ]

        ranges = [
            self._approach_range_percent(
                candle=candle,
            )
            for candle in analyzed_candles
        ]

        closer_close_count = sum(
            1
            for index in range(1, len(distances))
            if distances[index] < distances[index - 1]
        )

        smaller_range_count = sum(
            1
            for index in range(1, len(ranges))
            if ranges[index] < ranges[index - 1]
        )

        distance_reduction_percent = self._reduction_percent(
            start_value=distances[0],
            end_value=distances[-1],
        )

        range_reduction_percent = self._reduction_percent(
            start_value=ranges[0],
            end_value=ranges[-1],
        )

        all_on_approach_side = all(
            self._is_on_approach_side(
                candle=candle,
                level_price=level_price,
                is_resistance=is_resistance,
            )
            for candle in analyzed_candles
        )

        last_distance_within_reach = (
            distances[-1] <= self.level_approach_max_distance_percent
        )

        is_compression = (
            all_on_approach_side
            and last_distance_within_reach
            and closer_close_count == len(analyzed_candles) - 1
            and smaller_range_count
            >= self.level_approach_min_smaller_range_count
            and distance_reduction_percent
            >= self.level_approach_min_distance_reduction_percent
            and range_reduction_percent
            >= self.level_approach_min_range_reduction_percent
        )

        preceding_ranges = ranges[:-1]

        is_large_bar_approach = (
            last_distance_within_reach
            and ranges[-1]
            >= self.level_approach_large_bar_multiplier
            * self._median(preceding_ranges)
        )

        return LevelApproachContext(
            bar_count=len(analyzed_candles),
            closer_close_count=closer_close_count,
            smaller_range_count=smaller_range_count,
            distance_reduction_percent=round(
                distance_reduction_percent,
                4,
            ),
            range_reduction_percent=round(
                range_reduction_percent,
                4,
            ),
            is_compression=is_compression,
            is_large_bar_approach=is_large_bar_approach,
        )

    @staticmethod
    def _approach_distance_percent(
        candle: Candle,
        level_price: float,
        is_resistance: bool,
    ) -> float:
        """
        Return the distance from the candle's close to the level, on
        the approach side (positive while price has not crossed the
        level yet).
        """

        if is_resistance:
            return (
                level_price - candle.close
            ) / level_price * 100

        return (
            candle.close - level_price
        ) / level_price * 100

    @staticmethod
    def _approach_range_percent(
        candle: Candle,
    ) -> float:
        """
        Return the candle's high-low range as a percent of its close.
        """

        if candle.close <= 0:
            return 0.0

        return (
            candle.high - candle.low
        ) / candle.close * 100

    @staticmethod
    def _is_on_approach_side(
        candle: Candle,
        level_price: float,
        is_resistance: bool,
    ) -> bool:
        """
        Return True when the candle's close has not yet crossed the
        level (below resistance, above support).
        """

        if is_resistance:
            return candle.close < level_price

        return candle.close > level_price

    @staticmethod
    def _reduction_percent(
        start_value: float,
        end_value: float,
    ) -> float:
        """
        Return how much end_value shrank from start_value, as a
        percent of start_value. Never negative: a value that grew
        (or a non-positive starting value) contributes zero.
        """

        if start_value <= 0:
            return 0.0

        return max(
            0.0,
            (start_value - end_value) / start_value * 100,
        )

    @staticmethod
    def _median(
        values: list[float],
    ) -> float:
        """
        Return the median of values. Returns 0.0 for an empty list.
        """

        if not values:
            return 0.0

        ordered = sorted(values)
        count = len(ordered)
        midpoint = count // 2

        if count % 2 == 1:
            return ordered[midpoint]

        return (
            ordered[midpoint - 1]
            + ordered[midpoint]
        ) / 2

    def _score_false_break_confirmation(
        self,
        signal_candle: Candle,
        level_price: float,
        level_side: str,
    ) -> FalseBreakContext:
        """
        Confirmed false breakout v2.

        Score how decisively signal_candle rejected level_price:
        - penetration_percent: how far the candle pierced past the
          level (high past resistance, or low past support);
        - reclaim_percent: how far the close pulled back inside the
          level;
        - close_position_percent: where the close sits within the
          candle's own high-low range, (close - low) / (high - low)
          * 100 - low for a resistance rejection (close near the
          candle low), high for a support rejection (close near the
          candle high);
        - is_confirmed: True only when penetration, reclaim, close
          position, and close direction all agree the rejection was
          decisive, not just a bare legacy-threshold clear.

        A zero-range candle (high <= low) returns is_confirmed=False
        without raising.
        """

        if signal_candle.high <= signal_candle.low:
            return FalseBreakContext(
                penetration_percent=0.0,
                reclaim_percent=0.0,
                close_position_percent=0.0,
                is_confirmed=False,
            )

        close_position_percent = (
            (signal_candle.close - signal_candle.low)
            / (signal_candle.high - signal_candle.low)
            * 100
        )

        is_resistance = level_side == "resistance"

        if is_resistance:
            penetration_percent = (
                (signal_candle.high - level_price)
                / level_price
                * 100
            )

            reclaim_percent = (
                (level_price - signal_candle.close)
                / level_price
                * 100
            )

            is_confirmed = (
                penetration_percent
                >= self.false_break_min_penetration_percent
                and reclaim_percent
                >= self.false_break_min_reclaim_percent
                and close_position_percent
                <= self.false_break_max_close_position_percent
                and signal_candle.close < signal_candle.open
            )

        else:
            penetration_percent = (
                (level_price - signal_candle.low)
                / level_price
                * 100
            )

            reclaim_percent = (
                (signal_candle.close - level_price)
                / level_price
                * 100
            )

            is_confirmed = (
                penetration_percent
                >= self.false_break_min_penetration_percent
                and reclaim_percent
                >= self.false_break_min_reclaim_percent
                and close_position_percent
                >= self.false_break_min_close_position_percent
                and signal_candle.close > signal_candle.open
            )

        return FalseBreakContext(
            penetration_percent=penetration_percent,
            reclaim_percent=reclaim_percent,
            close_position_percent=close_position_percent,
            is_confirmed=is_confirmed,
        )

    @staticmethod
    def _entry_candles_after_daily_close(
        entry_candles: list[Candle],
        daily_close_time: datetime,
    ) -> list[Candle]:
        """
        Timestamp alignment v1 - keep only entry-timeframe candles
        that opened strictly after the daily signal candle's own
        close_time, so an entry candle that opened before the daily
        candle even closed can never confirm that daily setup.

        No sorting, no timezone normalization, no try/except: this
        trusts entry_candles to already be Candle instances with
        timezone-aware open_time (see models/candle.py), the same as
        every other candle comparison in this file.
        """

        return [
            candle
            for candle in entry_candles
            if candle.open_time > daily_close_time
        ]

    def _score_mtf_entry_confirmation(
        self,
        signal: Signal,
        entry_candles: list[Candle],
    ) -> MTFEntryConfirmation:
        """
        1D level -> 1h Confirmation Context v1.

        Reads only the last two CLOSED entry-timeframe candles:
        entry_candles[-2] as the confirmation candle and
        entry_candles[-3] as the prior candle. entry_candles[-1] is
        treated as potentially unclosed and is never read.

        Fewer than three entry candles means there is no closed
        confirmation candle to read yet, so this returns
        confirmation_type="insufficient_data" without raising.
        """

        setup_type = signal.metadata["setup_type"]
        expected_pattern = self._MTF_EXPECTED_PATTERN_BY_SETUP_TYPE.get(
            setup_type, "unknown",
        )

        if len(entry_candles) < 3:
            return MTFEntryConfirmation(
                expected_pattern=expected_pattern,
                confirmation_type="insufficient_data",
                analyzed_candle_count=len(entry_candles),
                is_confirmed=False,
                touched_level=False,
                crossed_level=False,
                retested_level=False,
                penetration_percent=0.0,
                distance_from_level_percent=0.0,
                close_position_percent=0.0,
                confirmation_candle_open_time=None,
            )

        level = signal.metadata["level_price"]
        last_candle = entry_candles[-2]
        previous_candle = entry_candles[-3]

        if last_candle.high <= last_candle.low:
            close_position_percent = 50.0
        else:
            close_position_percent = (
                (last_candle.close - last_candle.low)
                / (last_candle.high - last_candle.low)
                * 100
            )

        is_decisive_long = (
            last_candle.close > last_candle.open
            and close_position_percent
            >= self.mtf_confirmation_close_position_long_percent
        )
        is_decisive_short = (
            last_candle.close < last_candle.open
            and close_position_percent
            <= self.mtf_confirmation_close_position_short_percent
        )

        touched_level, crossed_level, retested_level = (
            self._mtf_level_interaction_flags(
                level, previous_candle, last_candle, signal.direction,
            )
        )

        if signal.direction == "SHORT":
            penetration_percent = (
                (last_candle.high - level) / level * 100
            )
        else:
            penetration_percent = (
                (level - last_candle.low) / level * 100
            )

        distance_from_level_percent = self._percent_distance(
            last_candle.close, level,
        )

        if expected_pattern == "continuation":
            confirmation_type, is_confirmed = (
                self._score_continuation_confirmation(
                    signal.direction,
                    level,
                    previous_candle,
                    last_candle,
                    is_decisive_long,
                    is_decisive_short,
                )
            )
        elif expected_pattern == "bounce":
            confirmation_type, is_confirmed = (
                self._score_bounce_confirmation(
                    signal.direction,
                    level,
                    last_candle,
                    is_decisive_long,
                    is_decisive_short,
                )
            )
        elif expected_pattern == "false_break_reclaim":
            confirmation_type, is_confirmed = (
                self._score_false_break_reclaim_confirmation(
                    signal.direction,
                    level,
                    last_candle,
                    is_decisive_long,
                    is_decisive_short,
                )
            )
        else:
            confirmation_type = "unsupported_setup"
            is_confirmed = False

        return MTFEntryConfirmation(
            expected_pattern=expected_pattern,
            confirmation_type=confirmation_type,
            analyzed_candle_count=2,
            is_confirmed=is_confirmed,
            touched_level=touched_level,
            crossed_level=crossed_level,
            retested_level=retested_level,
            penetration_percent=penetration_percent,
            distance_from_level_percent=distance_from_level_percent,
            close_position_percent=close_position_percent,
            confirmation_candle_open_time=last_candle.open_time,
        )

    def _score_continuation_confirmation(
        self,
        direction: str,
        level: float,
        previous_candle: Candle,
        last_candle: Candle,
        is_decisive_long: bool,
        is_decisive_short: bool,
    ) -> tuple[str, bool]:
        """
        LONG breakout confirms via breakout_close (a decisive close
        clearing the level by the 0.05% threshold) or retest_hold (a
        decisive close holding above the level after dipping back
        into the 0.15% tolerance band). SHORT breakdown mirrors both
        below the level.
        """

        tolerance = self.mtf_confirmation_tolerance_percent
        breakout_threshold = (
            self.mtf_confirmation_breakout_threshold_percent
        )

        if direction == "LONG":
            breakout_close = (
                previous_candle.close <= level
                and last_candle.close
                > self._above_level(level, breakout_threshold)
                and is_decisive_long
            )

            if breakout_close:
                return "breakout_close", True

            retest_hold = (
                previous_candle.close > level
                and last_candle.low
                <= self._above_level(level, tolerance)
                and last_candle.close > level
                and is_decisive_long
            )

            if retest_hold:
                return "retest_hold_long", True

            return "breakout_close", False

        breakdown_close = (
            previous_candle.close >= level
            and last_candle.close
            < self._below_level(level, breakout_threshold)
            and is_decisive_short
        )

        if breakdown_close:
            return "breakdown_close", True

        retest_hold = (
            previous_candle.close < level
            and last_candle.high
            >= self._below_level(level, tolerance)
            and last_candle.close < level
            and is_decisive_short
        )

        if retest_hold:
            return "retest_hold_short", True

        return "breakdown_close", False

    def _score_bounce_confirmation(
        self,
        direction: str,
        level: float,
        last_candle: Candle,
        is_decisive_long: bool,
        is_decisive_short: bool,
    ) -> tuple[str, bool]:
        """
        A support/resistance bounce confirms when the confirmation
        candle's touch stays inside the 0.15% tolerance band, closes
        back on the setup's side of the level, and closes decisively.
        """

        tolerance = self.mtf_confirmation_tolerance_percent

        if direction == "LONG":
            is_confirmed = (
                self._below_level(level, tolerance)
                <= last_candle.low
                <= self._above_level(level, tolerance)
                and last_candle.close > level
                and is_decisive_long
            )

            return "support_rejection", is_confirmed

        is_confirmed = (
            self._below_level(level, tolerance)
            <= last_candle.high
            <= self._above_level(level, tolerance)
            and last_candle.close < level
            and is_decisive_short
        )

        return "resistance_rejection", is_confirmed

    def _score_false_break_reclaim_confirmation(
        self,
        direction: str,
        level: float,
        last_candle: Candle,
        is_decisive_long: bool,
        is_decisive_short: bool,
    ) -> tuple[str, bool]:
        """
        A false breakout/breakdown reclaim confirms when the
        confirmation candle pierces past the level intraday but
        closes back on the other side of it, decisively.
        """

        if direction == "SHORT":
            is_confirmed = (
                last_candle.high > level
                and last_candle.close < level
                and is_decisive_short
            )

            return "false_breakout_reclaim", is_confirmed

        is_confirmed = (
            last_candle.low < level
            and last_candle.close > level
            and is_decisive_long
        )

        return "false_breakdown_reclaim", is_confirmed

    @staticmethod
    def _mtf_level_interaction_flags(
        level: float,
        previous_candle: Candle,
        last_candle: Candle,
        direction: str,
    ) -> tuple[bool, bool, bool]:
        """
        General-purpose level-interaction flags for the confirmation
        candle, read from the side of the level that `direction`
        cares about (LONG watches the low approaching from above,
        SHORT watches the high approaching from below):
        - touched_level: the confirmation candle's relevant side came
          within the 0.15% tolerance band of the level;
        - crossed_level: the raw level sits inside the confirmation
          candle's high-low range (the level was pierced intracandle);
        - retested_level: the prior candle had already closed beyond
          the level in `direction`'s favor, and the confirmation
          candle's relevant side came back within the 0.15% tolerance
          band - a genuine retest, not just an initial break.
        """

        tolerance = DailyLevelsStrategy.mtf_confirmation_tolerance_percent

        if direction == "LONG":
            touched_level = (
                last_candle.low
                <= DailyLevelsStrategy._above_level(level, tolerance)
            )
            retested_level = (
                previous_candle.close > level and touched_level
            )
        else:
            touched_level = (
                last_candle.high
                >= DailyLevelsStrategy._below_level(level, tolerance)
            )
            retested_level = (
                previous_candle.close < level and touched_level
            )

        crossed_level = last_candle.low <= level <= last_candle.high

        return touched_level, crossed_level, retested_level

    @staticmethod
    def _above_level(
        level: float,
        percent: float,
    ) -> float:
        return level * (
            1 + percent / 100
        )

    @staticmethod
    def _below_level(
        level: float,
        percent: float,
    ) -> float:
        return level * (
            1 - percent / 100
        )

    @staticmethod
    def _percent_distance(
        price: float,
        level: float,
    ) -> float:
        if level <= 0:
            return 0.0

        return abs(
            price - level,
        ) / level * 100
