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

        setup = (
            self._detect_false_breakout_short(
                signal_candle=signal_candle,
                previous_candle=previous_candle,
                resistance=resistance,
                support=support,
                level_range_percent=level_range_percent,
            )
            or self._detect_false_breakdown_long(
                signal_candle=signal_candle,
                previous_candle=previous_candle,
                resistance=resistance,
                support=support,
                level_range_percent=level_range_percent,
            )
            or self._detect_breakout_long(
                signal_candle=signal_candle,
                previous_candle=previous_candle,
                resistance=resistance,
                support=support,
                level_range_percent=level_range_percent,
            )
            or self._detect_breakdown_short(
                signal_candle=signal_candle,
                previous_candle=previous_candle,
                resistance=resistance,
                support=support,
                level_range_percent=level_range_percent,
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
            ),
        )

    def _detect_breakdown_short(
        self,
        signal_candle: Candle,
        previous_candle: Candle,
        resistance: float,
        support: float,
        level_range_percent: float,
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
            ),
        )

    def _detect_false_breakout_short(
        self,
        signal_candle: Candle,
        previous_candle: Candle,
        resistance: float,
        support: float,
        level_range_percent: float,
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
            ),
        )

    def _detect_false_breakdown_long(
        self,
        signal_candle: Candle,
        previous_candle: Candle,
        resistance: float,
        support: float,
        level_range_percent: float,
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
    ) -> dict:
        """
        Build metadata for scan journal and research trade storage.
        """

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
        }

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