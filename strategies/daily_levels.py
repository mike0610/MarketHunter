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

        score = min(
            score,
            78.0,
        )

        return DailyLevelSetup(
            direction="LONG",
            setup_type="daily_breakout",
            level_name="daily_resistance",
            level_price=resistance,
            score=score,
            reasons=[
                "Daily close confirmed above previous resistance.",
                "Breakout is based only on 1D levels.",
                "No indicators used.",
            ],
            metadata=self._metadata(
                setup_type="daily_breakout",
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

        score = min(
            score,
            78.0,
        )

        return DailyLevelSetup(
            direction="SHORT",
            setup_type="daily_breakdown",
            level_name="daily_support",
            level_price=support,
            score=score,
            reasons=[
                "Daily close confirmed below previous support.",
                "Breakdown is based only on 1D levels.",
                "No indicators used.",
            ],
            metadata=self._metadata(
                setup_type="daily_breakdown",
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

        score = min(
            score,
            79.0,
        )

        return DailyLevelSetup(
            direction="SHORT",
            setup_type="daily_false_breakout",
            level_name="daily_resistance",
            level_price=resistance,
            score=score,
            reasons=[
                "Daily candle swept previous resistance and closed back below it.",
                "False breakout is confirmed by daily close.",
                "No indicators used.",
            ],
            metadata=self._metadata(
                setup_type="daily_false_breakout",
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

        score = min(
            score,
            79.0,
        )

        return DailyLevelSetup(
            direction="LONG",
            setup_type="daily_false_breakdown",
            level_name="daily_support",
            level_price=support,
            score=score,
            reasons=[
                "Daily candle swept previous support and closed back above it.",
                "False breakdown is confirmed by daily close.",
                "No indicators used.",
            ],
            metadata=self._metadata(
                setup_type="daily_false_breakdown",
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
