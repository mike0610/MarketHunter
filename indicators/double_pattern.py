"""
MarketHunter

indicators/double_pattern.py
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from indicators.pivot_detector import PivotDetector
from models.candle import Candle


PatternKind = Literal[
    "double_bottom",
    "double_top",
]


@dataclass(slots=True)
class DoublePatternSignal:
    kind: PatternKind
    direction: str
    first_index: int
    second_index: int
    level: float
    neckline: float
    tolerance_percent: float
    bars_between: int
    confirmed: bool


class DoublePatternDetector:
    """
    Detect confirmed double top / double bottom patterns.

    Bullish double bottom:
    - two swing lows near the same level
    - enough bars between them
    - price closes above neckline

    Bearish double top:
    - two swing highs near the same level
    - enough bars between them
    - price closes below neckline
    """

    def __init__(
        self,
        *,
        tolerance_percent: float = 0.75,
        min_bars_between: int = 4,
        max_bars_between: int = 80,
        pivot_left: int = 3,
        pivot_right: int = 3,
    ) -> None:
        if tolerance_percent <= 0:
            raise ValueError(
                "Tolerance percent must be positive."
            )

        if min_bars_between < 1:
            raise ValueError(
                "Minimum bars between pivots must be positive."
            )

        if max_bars_between < min_bars_between:
            raise ValueError(
                "Maximum bars between pivots must be >= minimum."
            )

        self.tolerance_percent = tolerance_percent
        self.min_bars_between = min_bars_between
        self.max_bars_between = max_bars_between
        self.pivot_left = pivot_left
        self.pivot_right = pivot_right
        self.pivots = PivotDetector()

    def bullish(
        self,
        candles: list[Candle],
    ) -> bool:
        signal = self.latest_bullish(candles)

        return bool(
            signal is not None
            and signal.confirmed
        )

    def bearish(
        self,
        candles: list[Candle],
    ) -> bool:
        signal = self.latest_bearish(candles)

        return bool(
            signal is not None
            and signal.confirmed
        )

    def latest_bullish(
        self,
        candles: list[Candle],
    ) -> DoublePatternSignal | None:
        if len(candles) < (
            self.pivot_left
            + self.pivot_right
            + self.min_bars_between
            + 2
        ):
            return None

        lows = self.pivots.swing_lows(
            candles,
            left=self.pivot_left,
            right=self.pivot_right,
        )

        for second_index in reversed(lows):
            for first_index in reversed(lows):
                if first_index >= second_index:
                    continue

                bars_between = second_index - first_index

                if bars_between < self.min_bars_between:
                    continue

                if bars_between > self.max_bars_between:
                    break

                first_low = candles[first_index].low
                second_low = candles[second_index].low

                tolerance = self._distance_percent(
                    first_low,
                    second_low,
                )

                if tolerance > self.tolerance_percent:
                    continue

                neckline = max(
                    candle.high
                    for candle in candles[
                        first_index:second_index + 1
                    ]
                )

                confirmed = candles[-1].close > neckline

                return DoublePatternSignal(
                    kind="double_bottom",
                    direction="LONG",
                    first_index=first_index,
                    second_index=second_index,
                    level=(first_low + second_low) / 2,
                    neckline=neckline,
                    tolerance_percent=tolerance,
                    bars_between=bars_between,
                    confirmed=confirmed,
                )

        return None

    def latest_bearish(
        self,
        candles: list[Candle],
    ) -> DoublePatternSignal | None:
        if len(candles) < (
            self.pivot_left
            + self.pivot_right
            + self.min_bars_between
            + 2
        ):
            return None

        highs = self.pivots.swing_highs(
            candles,
            left=self.pivot_left,
            right=self.pivot_right,
        )

        for second_index in reversed(highs):
            for first_index in reversed(highs):
                if first_index >= second_index:
                    continue

                bars_between = second_index - first_index

                if bars_between < self.min_bars_between:
                    continue

                if bars_between > self.max_bars_between:
                    break

                first_high = candles[first_index].high
                second_high = candles[second_index].high

                tolerance = self._distance_percent(
                    first_high,
                    second_high,
                )

                if tolerance > self.tolerance_percent:
                    continue

                neckline = min(
                    candle.low
                    for candle in candles[
                        first_index:second_index + 1
                    ]
                )

                confirmed = candles[-1].close < neckline

                return DoublePatternSignal(
                    kind="double_top",
                    direction="SHORT",
                    first_index=first_index,
                    second_index=second_index,
                    level=(first_high + second_high) / 2,
                    neckline=neckline,
                    tolerance_percent=tolerance,
                    bars_between=bars_between,
                    confirmed=confirmed,
                )

        return None

    @staticmethod
    def _distance_percent(
        first: float,
        second: float,
    ) -> float:
        base = abs(first)

        if base <= 0:
            return 0.0

        return abs(first - second) / base * 100
