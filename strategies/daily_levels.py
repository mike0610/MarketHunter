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

        setup = (
            self._detect_false_breakout_short(
                signal_candle=signal_candle,
                previous_candle=previous_candle,
                resistance=resistance,
                support=support,
                level_range_percent=level_range_percent,
                resistance_quality=resistance_quality,
                support_quality=support_quality,
            )
            or self._detect_false_breakdown_long(
                signal_candle=signal_candle,
                previous_candle=previous_candle,
                resistance=resistance,
                support=support,
                level_range_percent=level_range_percent,
                resistance_quality=resistance_quality,
                support_quality=support_quality,
            )
            or self._detect_breakout_long(
                signal_candle=signal_candle,
                previous_candle=previous_candle,
                resistance=resistance,
                support=support,
                level_range_percent=level_range_percent,
                resistance_quality=resistance_quality,
                support_quality=support_quality,
            )
            or self._detect_breakdown_short(
                signal_candle=signal_candle,
                previous_candle=previous_candle,
                resistance=resistance,
                support=support,
                level_range_percent=level_range_percent,
                resistance_quality=resistance_quality,
                support_quality=support_quality,
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
    ) -> dict:
        """
        Build metadata for scan journal and research trade storage.
        """

        level_quality = (
            resistance_quality
            if level_name == "daily_resistance"
            else support_quality
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
